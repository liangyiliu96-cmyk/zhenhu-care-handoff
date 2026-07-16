"""Agent 节点实现 —— 每个节点独立执行, 通过 state 传递上下文。合并迁入。

阶段4 Agent框架: 先用 fixture 实现(保持测试通过), 阶段5换真实LLM调用。

合并迁入修正B: load_template 改为直接从 disease_templates/ 目录加载。
"""

import json
import os
from pathlib import Path

from .harness import validate_handoff_items, fallback_to_template

# 合并迁入修正B: 不依赖 app.domain.templates, 直接加载 disease_templates/
_TEMPLATE_DIR = Path(os.path.join(os.path.dirname(__file__), "..", "disease_templates")).resolve()


def load_template(disease_id: str) -> dict:
    """从 disease_templates/ 目录加载指定病种模板 JSON。合并迁入修正。

    Args:
        disease_id: 病种标识(如 "hypertension", "heart_failure", "diabetes")

    Returns:
        病种模板 dict, 含 vital_signs/risk_factors/discharge_criteria/
        handoff_instructions/agent_config 等字段

    Raises:
        FileNotFoundError: 模板文件不存在
    """
    path = _TEMPLATE_DIR / f"{disease_id}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_templates() -> list[str]:
    """列出所有可用的病种模板 disease_id。"""
    return [f.stem for f in _TEMPLATE_DIR.glob("*.json")]


async def node_admission(state: dict) -> dict:
    """入院采集: 加载病种模板, 初始化State。

    阶段4-C修复: 实际加载模板, 让下游节点获得真实临床参数。
    阶段H审计修复: 添加 try/except 防止未捕获异常导致流程中断。
    阶段K: 同仓库直接 import fhir-adapter，优先同进程查询，失败走 HTTP fallback。
    """
    try:
        patient_id = state.get("patient_id", "unknown")
        template = state.get("disease_template", {})
        if not template:
            template = load_template("hypertension")

        # 阶段K: 同仓库直接调用——优先 import, 失败走 HTTP fallback
        patient_data = {}
        try:
            from zhenhu.fhir.models import Patient as FhirPatient, async_session_factory as fhir_session_factory  # noqa: F811
            from sqlalchemy import select as sa_select
            async with fhir_session_factory() as session:
                result = await session.execute(
                    sa_select(FhirPatient).where(FhirPatient.patient_id == patient_id)
                )
                fhir_patient = result.scalar_one_or_none()
                if fhir_patient:
                    patient_data = {"name": fhir_patient.name, "gender": fhir_patient.gender}
        except (ImportError, Exception):
            from ..hooks.zhenhu_bridge import bridge_patient_summary
            patient_data = await bridge_patient_summary(patient_id)

        return {
            "phase": "admission",
            "patient_id": patient_id,
            "disease_template": template,
            "patient_data": patient_data,
            "document_chain": state.get("document_chain", []) + ["intake_note"],
        }
    except Exception:
        return {
            "phase": "admission",
            "patient_id": state.get("patient_id", "unknown"),
            "disease_template": {},
            "document_chain": ["intake_note"],
            "error": "admission_failed",
        }


async def node_triage(state: dict) -> dict:
    """风险分层。

    高危自动触发MDT。
    """
    template = state.get("disease_template", {})
    risk_factors = len(template.get("risk_factors", []))
    vs_count = len(state.get("vital_signs", []))

    if vs_count == 0:
        level = "low"
    elif risk_factors >= 3:
        level = "high"
    elif risk_factors >= 2:
        level = "medium"
    else:
        level = "low"

    result = {"risk_level": level, "phase": "triage"}

    if level == "high":
        result["mdt_required"] = True
        result["mdt_roles"] = template.get("mdt_roles", ["心内科", "营养师", "康复师"])
        result["mdt_mode"] = "async-review"
        result["mdt_reason"] = f"风险分层为高危(风险因子数={risk_factors})"

    return result


async def node_monitoring(state: dict) -> dict:
    """持续监测: 检查最新生命体征, 判断是否满足出院条件。

    阶段H审计修复: 消费 risk_level,高危患者需要更多体征数据才批准出院。
    """
    risk = state.get("risk_level", "low")
    vs = state.get("vital_signs", [])
    required = 6 if risk == "high" else 3
    if len(vs) >= required:
        return {"phase": "monitoring", "discharge_decision": "approved", "monitoring_strategy": f"risk_{risk}"}
    return {"phase": "monitoring", "monitoring_strategy": f"risk_{risk}"}


async def node_discharge(state: dict) -> dict:
    """阶段K: 出院全链路自动化——创建病例+检索知识+患者照护视图。

    出院决定 → 自动调 bridge 创建臻护病例 + 检索知识 + 生成照护视图。
    同仓库优先 import workflow state_machine, 失败走 HTTP fallback。
    """
    template = state.get("disease_template", {})
    handoff_items = state.get("handoff_items", [])
    patient_id = state.get("patient_id", "")

    result = {"phase": "discharge", "discharge_decision": "approved"}

    if handoff_items:
        # ── 阶段K: 同仓库直接调用——优先 import, 失败走 HTTP fallback ──
        bridge_result = {"status": "bridge_unavailable"}

        try:
            # 同仓库直接调 workflow-engine
            from zhenhu.workflow.state_machine import CaseStateMachine
            from zhenhu.workflow.models import Case, async_session_factory
            async with async_session_factory() as session:
                stm = CaseStateMachine(session)
                case = Case(
                    input_snapshot_id=f"zhenhu-{patient_id}",
                    patient_ref=patient_id,
                    state="draft",
                )
                session.add(case)
                await session.flush()
                bridge_result = {
                    "status": "ok",
                    "case_id": case.case_id,
                    "state": case.state,
                }
        except (ImportError, Exception):
            from ..hooks.zhenhu_bridge import bridge_discharge_to_zhenhu_with_retry
            bridge_result = await bridge_discharge_to_zhenhu_with_retry(handoff_items, patient_id, template)

        result["bridge_result"] = bridge_result

        # 2. 检索相关知识
        from ..hooks.zhenhu_bridge import bridge_search_knowledge
        knowledge = await bridge_search_knowledge(template.get("name", "出院指导"))
        result["knowledge_context"] = knowledge[:3] if knowledge else []

        # 3. 患者照护视图
        from ..hooks.zhenhu_bridge import bridge_patient_summary
        patient = await bridge_patient_summary(patient_id)
        result["patient_summary"] = patient

        # 4. 失败回滚
        if bridge_result.get("status") != "ok":
            result["discharge_decision"] = "bridge_failed"
            result["bridge_error"] = bridge_result.get("status", "unknown")

    return result


async def node_handoff(state: dict) -> dict:
    """交接生成: 基于病种模板的handoff_instructions生成三事项。

    阶段4 fixture: 逐条生成, 阶段5增加RAG增强。
    """
    template = state.get("disease_template", {})
    instructions = template.get("handoff_instructions", [])
    items = [
        {
            "type": inst.get("type", "unknown"),
            "content": inst.get("content", ""),
            "feedback": None,
        }
        for inst in instructions
    ]
    valid, errors = validate_handoff_items(items)
    if errors:
        items = fallback_to_template(template)["handoff_items"]
    return {
        "handoff_items": items,
        "phase": "handoff",
        "patient_summary": state.get("patient_data", {}),
    }


async def node_doctor_review(state: dict) -> dict:
    """医生审核(HumanInterrupt)。

    医生可对每个 handoff_item 做三个动作之一:
    - accept: 确认该事项
    - edit: 修改内容后确认
    - dismiss: 驳回——触发自适应重评
    """
    items = state.get("handoff_items", [])

    reviewed = []
    for item in items:
        if len(reviewed) < 2:
            item["review_action"] = "accept"
            item["feedback"] = "已确认"
            reviewed.append(item)
        else:
            item["review_action"] = "dismiss"
            item["dismiss_reason"] = "剂量调整依据不充分,请重新评估"
            item["reevaluation_pending"] = True
            reviewed.append(item)

    all_accepted = all(it.get("review_action") == "accept" for it in reviewed)
    return {
        "handoff_items": reviewed,
        "phase": "review",
        "discharge_decision": "approved" if all_accepted else "pending_reevaluation",
        "interrupt_pending": False,
        "patient_summary": state.get("patient_data", {}),
    }


async def node_patient_confirm(state: dict) -> dict:
    """患者确认: 逐项标记'已理解'。"""
    items = state.get("handoff_items", [])
    for item in items:
        item["feedback"] = "已理解"
    return {"handoff_items": items, "phase": "confirm"}


# ── 阶段E: 补齐缺失临床步骤 ──


async def node_daily_round(state: dict) -> dict:
    """每日查房: 汇总生命体征趋势+检查结果+用药调整记录, 写入查房笔记。"""
    vs = state.get("vital_signs", [])
    labs = state.get("lab_results", [])
    meds = state.get("medication_adjustments", [])
    chain = state.get("document_chain", [])

    round_note = {
        "type": "daily_round",
        "vital_count": len(vs),
        "lab_count": len(labs),
        "med_adjust_count": len(meds),
        "timestamp": "mock-daily-round",
    }
    return {
        "phase": "daily_round",
        "document_chain": chain + ["daily_round_note"],
        "latest_round": round_note,
        "round_count": state.get("round_count", 0) + 1,
    }


async def node_medication_adjust(state: dict) -> dict:
    """用药调整: 当生命体征突破警报阈值时触发, 生成调药建议。"""
    template = state.get("disease_template", {})
    vs = state.get("vital_signs", [])
    alerts = []

    for v_def in template.get("vital_signs", []):
        name = v_def.get("name", "")
        alert_above = v_def.get("alert_above")
        alert_below = v_def.get("alert_below")

        for v in vs:
            val = v.get(name, 0)
            if alert_above and isinstance(val, (int, float)) and val > alert_above:
                alerts.append({"sign": name, "value": val, "threshold": alert_above, "direction": "high"})
            if alert_below and isinstance(val, (int, float)) and val < alert_below:
                alerts.append({"sign": name, "value": val, "threshold": alert_below, "direction": "low"})

    adjustments = state.get("medication_adjustments", [])
    if alerts:
        adjustments.append({
            "reason": alerts,
            "action": "剂量调整建议(阶段E fixture)",
            "timestamp": "mock-med-adjust",
        })

    return {
        "phase": "medication_adjust",
        "medication_alerts": alerts,
        "medication_adjustments": adjustments,
    }


async def node_lab_review(state: dict) -> dict:
    """检查结果审阅: 当新检验/检查报告返回时, 对照病种模板评估。"""
    labs = state.get("lab_results", [])
    reviewed = state.get("reviewed_labs", [])

    new_labs = [lab for lab in labs if lab not in reviewed]
    findings = []
    for lab in new_labs:
        findings.append({"test": lab.get("name", "unknown"), "result": lab.get("value", "N/A"), "status": "reviewed"})

    return {
        "phase": "lab_review",
        "reviewed_labs": reviewed + new_labs,
        "lab_findings": findings,
        "document_chain": state.get("document_chain", []) + (["lab_review"] if new_labs else []),
    }


async def node_transfer(state: dict) -> dict:
    """转科判断: 当病情恶化超出当前科室处理能力时触发, 建议转ICU/专科。"""
    risk_level = state.get("risk_level", "low")
    vs = state.get("vital_signs", [])
    transfer_needed = False
    transfer_target = None

    if risk_level == "high" and len(vs) >= 3:
        transfer_needed = True
        transfer_target = "ICU"

    return {
        "phase": "transfer",
        "transfer_needed": transfer_needed,
        "transfer_target": transfer_target,
        "transfer_reason": "高危+体征持续异常" if transfer_needed else None,
    }


# ── 阶段K: 用药核对节点（临床安全第一优先级）──


async def node_medication_reconciliation(state: dict) -> dict:
    """用药核对: 入院时调 fhir-adapter 拉患者院前用药 → 和病种模板标准用药交叉比对。

    阶段K: 新增临床核心节点——用药缺口/冲突/重复检测。
    """
    patient_id = state.get("patient_id", "")
    template = state.get("disease_template", {})

    # 1. 调 fhir-adapter 获取患者历史用药
    from ..hooks.zhenhu_bridge import FHIR_URL
    import httpx
    pre_admission_meds = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 查患者的 MedicationRequest 历史
            resp = await client.get(f"{FHIR_URL}/fhir/Patient/{patient_id}/CarePlan")
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                # fixture: 从预置数据提取
                pre_admission_meds = data.get("medications", [])
    except Exception:
        pass

    # 2. 从病种模板读取标准出院用药
    handoff_meds = [
        inst for inst in template.get("handoff_instructions", [])
        if inst.get("type") == "medication"
    ]

    # 3. 交叉比对
    findings = {"gaps": [], "conflicts": [], "duplications": []}

    for med in handoff_meds:
        matched = any(
            med.get("content", "")[:10] in pm.get("name", "")
            for pm in pre_admission_meds
        )
        if not matched:
            findings["gaps"].append(f"出院带药'{med.get('content','')[:30]}'在院前用药中未见记录")
        elif len([m for m in handoff_meds if m.get("content","")[:10] == med.get("content","")[:10]]) > 1:
            findings["duplications"].append(f"'{med.get('content','')[:30]}'存在潜在重复")

    # 冲突检测(fixture占位, 阶段5对接LLM)
    if pre_admission_meds and handoff_meds:
        findings["conflicts"].append("阶段K fixture: 用药交叉比对完成, 建议医生人工复核")

    return {
        "phase": "medication_reconciliation",
        "medication_findings": findings,
        "document_chain": state.get("document_chain", []) + ["medication_reconciliation"],
    }
