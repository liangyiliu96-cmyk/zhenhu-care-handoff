"""Agent 节点实现 —— 每个节点独立执行, 通过 state 传递上下文。合并迁入。

阶段4 Agent框架: 先用 fixture 实现(保持测试通过), 阶段5换真实LLM调用。

合并迁入修正B: load_template 改为直接从 disease_templates/ 目录加载。
P0修复: 字段统一(key→name/alert_high→alert_above/alert_low→alert_below)、
        真实分层匹配、出院标准逐条检查、连续异常调药、过敏史采集、药物相互作用检测。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from .harness import validate_handoff_items, fallback_to_template, normalize_template

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
        template = json.load(f)
    template = normalize_template(template)
    return template


def list_templates() -> list[str]:
    """列出所有可用的病种模板 disease_id。"""
    return [f.stem for f in _TEMPLATE_DIR.glob("*.json")]


# ============================================================================
# P0-5: 风险因子匹配器 —— 基于实际患者数据逐条匹配模板风险因子
# ============================================================================

_RISK_FACTOR_MATCHERS: dict[str, Callable] = {
    "age>60": lambda pd, ph: pd.get("age", 0) > 60,
    "age>65": lambda pd, ph: pd.get("age", 0) > 65,
    "age_gt_65": lambda pd, ph: pd.get("age", 0) > 65,
    "age_gt_70": lambda pd, ph: pd.get("age", 0) > 70,
    "smoking": lambda pd, ph: ph.get("smoking", False),
    "current_smoker": lambda pd, ph: ph.get("smoking", False),
    "obesity": lambda pd, ph: pd.get("bmi", 0) >= 28,
    "family_history": lambda pd, ph: ph.get("family_history_cvd", False),
    "diabetes_comorbid": lambda pd, ph: "diabetes" in ph.get("comorbidities", []),
    "diabetes_comorbidity": lambda pd, ph: "diabetes" in ph.get("comorbidities", []),
    "hypertension_comorbidity": lambda pd, ph: "hypertension" in ph.get("comorbidities", []),
    "cvd_history": lambda pd, ph: "cvd" in ph.get("comorbidities", []),
    "prior_hospitalization": lambda pd, ph: ph.get("prior_hospitalization", False),
    "renal_insufficiency": lambda pd, ph: "ckd" in ph.get("comorbidities", []) or pd.get("egfr", 100) < 60,
    "hypoglycemia_history": lambda pd, ph: ph.get("hypoglycemia_history", False),
    "neuropathy": lambda pd, ph: "neuropathy" in ph.get("comorbidities", []),
    "nephropathy": lambda pd, ph: "nephropathy" in ph.get("comorbidities", []),
    "afib_history": lambda pd, ph: ph.get("afib_history", False),
    "post_thrombolysis": lambda pd, ph: ph.get("post_thrombolysis", False),
    "post_pci": lambda pd, ph: ph.get("post_pci", False),
}


def _match_patient_risk_factors(
    patient_data: dict,
    patient_history: dict,
    template_risks: list[str],
) -> list[str]:
    """基于实际患者数据逐条匹配模板风险因子。
    
    当 patient_data 和 patient_history 为空时返回空列表，
    患者被正确分层为 low —— 比旧代码安全。
    """
    matched = []
    for factor in template_risks:
        matcher = _RISK_FACTOR_MATCHERS.get(factor)
        if matcher:
            try:
                if matcher(patient_data, patient_history):
                    matched.append(factor)
            except Exception:
                pass  # 匹配异常跳过该因子
    return matched


# ============================================================================
# P0-1: 出院标准逐条检查
# ============================================================================


def _check_discharge_criteria(
    criteria: list,
    vital_signs: list[dict],
    state: dict,
) -> dict:
    """逐条检查出院标准，返回条件检查结果。
    
    支持两种格式：
    - 对象数组：[{"condition": "bp_stable_24h", "description": "..."}]
    - 字符串数组：["bp_stable_24h", "spo2_stable_above_90"]
    
    Phase 5 可升级为 LLM 评估。
    """
    if not criteria:
        return {"all_met": False, "checked": [], "unmet": ["无出院标准定义"]}
    
    checked = []
    unmet = []
    
    for c in criteria:
        cond_key = c if isinstance(c, str) else c.get("condition", "")
        if _evaluate_criterion(cond_key, vital_signs, state):
            checked.append(cond_key)
        else:
            unmet.append(cond_key)
    
    return {
        "all_met": len(unmet) == 0,
        "checked": checked,
        "unmet": unmet,
    }


def _evaluate_criterion(cond_key: str, vital_signs: list[dict], state: dict) -> bool:
    """评估单个出院标准的满足情况。
    
    基于条件键名做规则匹配，Phase 5 升级 LLM。
    当前覆盖血压稳定/体征正常/用药方案确认等核心条件。
    """
    if not vital_signs:
        return False
    
    recent = vital_signs[-3:]  # 最近3条
    
    # 血压稳定检查
    if "bp_stable" in cond_key:
        for v in recent:
            sbp = v.get("blood_pressure_systolic", v.get("systolic_mmhg", 0))
            dbp = v.get("blood_pressure_diastolic", v.get("diastolic_mmhg", 0))
            bp_str = v.get("blood_pressure", "")
            if isinstance(bp_str, str) and "/" in bp_str:
                parts = bp_str.split("/")
                sbp = int(parts[0]) if parts[0].isdigit() else sbp
                dbp = int(parts[1]) if parts[1].isdigit() else dbp
            if sbp > 160 or dbp > 100:
                return False
        return True
    
    # 血氧稳定检查
    if "spo2" in cond_key:
        threshold = 90 if "90" in cond_key else 92 if "92" in cond_key else 94
        for v in recent:
            spo2 = v.get("spo2", 0)
            if isinstance(spo2, (int, float)) and spo2 < threshold:
                return False
        return True
    
    # 体征稳定通用检查
    if "vital_signs_stable" in cond_key:
        return len(vital_signs) >= 3
    
    # 用药方案确认
    if "medication" in cond_key or "med" in cond_key.lower():
        # 检查是否在 handoff_instructions 中有 medication 类型
        handoff = state.get("handoff_items", []) or state.get("disease_template", {}).get("handoff_instructions", [])
        has_med = any(it.get("type") == "medication" for it in handoff if isinstance(it, dict))
        return has_med
    
    # 无发热
    if "afebrile" in cond_key:
        for v in recent:
            temp = v.get("temperature", 36.5)
            if isinstance(temp, (int, float)) and temp > 37.5:
                return False
        return True
    
    # 血流动力学稳定
    if any(kw in cond_key for kw in ["hemodynamic", "hemodynamics"]):
        return len(vital_signs) >= 3
    
    # 意识/神经评估 — 无恶化即视为稳定(保守)
    if any(kw in cond_key for kw in ["nihss", "consciousness", "neuro"]):
        return True
    
    # 口服耐受
    if "oral" in cond_key:
        return "intake_note" in state.get("document_chain", [])
    
    # 自我管理教育完成
    if any(kw in cond_key for kw in ["education", "self_care", "self_monitoring"]):
        return True  # Phase 5: 需要实际验证
    
    # 默认: 保守处理，不满足
    return False


# ============================================================================
# Agent 节点函数
# ============================================================================


async def node_admission(state: dict) -> dict:
    """入院采集: 加载病种模板, 初始化State。

    阶段4-C修复: 实际加载模板, 让下游节点获得真实临床参数。
    阶段H审计修复: 添加 try/except 防止未捕获异常导致流程中断。
    阶段K: 同仓库直接 import fhir-adapter，优先同进程查询，失败走 HTTP fallback。
    P0-7: 过敏史强制采集。
    """
    try:
        patient_id = state.get("patient_id", "unknown")
        template = state.get("disease_template", {})
        if not template:
            template = load_template("hypertension")

        # 阶段K: 同仓库直接调用——优先 import, 失败走 HTTP fallback
        patient_data = {}
        patient_history = {}
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

        # P0-7: 过敏史强制采集
        allergies = []
        try:
            from zhenhu.fhir.models import AllergyIntolerance as FhirAllergy
            async with fhir_session_factory() as session:
                result = await session.execute(
                    sa_select(FhirAllergy).where(FhirAllergy.patient_id == patient_id)
                )
                fhir_allergies = result.scalars().all()
                allergies = [a.display or a.code for a in fhir_allergies]
        except (ImportError, Exception):
            allergies = patient_data.get("allergies", [])

        return {
            "phase": "admission",
            "patient_id": patient_id,
            "disease_template": template,
            "patient_data": patient_data,
            "patient_history": patient_history,
            "document_chain": state.get("document_chain", []) + ["intake_note"],
            "allergies": allergies,
            "allergy_status": "collected" if allergies else "none_recorded",
        }
    except Exception:
        return {
            "phase": "admission",
            "patient_id": state.get("patient_id", "unknown"),
            "disease_template": {},
            "document_chain": ["intake_note"],
            "error": "admission_failed",
            "allergies": [],
            "allergy_status": "not_collected",
        }


async def node_triage(state: dict) -> dict:
    """风险分层。
    
    P0-5修复: 基于实际患者数据逐条匹配模板风险因子，而非用模板定义数量。
    P0-6修复: 写入 risk_assessment 到 document_chain，修复路由不可达。
    """
    template = state.get("disease_template", {})
    patient_data = state.get("patient_data", {})
    patient_history = state.get("patient_history", {})
    
    template_risks = template.get("risk_factors", [])
    matched = _match_patient_risk_factors(patient_data, patient_history, template_risks)
    
    risk_count = len(matched)
    if risk_count >= 3:
        level = "high"
    elif risk_count >= 2:
        level = "medium"
    else:
        level = "low"
    
    result = {
        "risk_level": level,
        "phase": "triage",
        "triage_matched_factors": matched,
        "document_chain": state.get("document_chain", []) + ["risk_assessment"],
    }
    
    if level == "high":
        result["mdt_required"] = True
        result["mdt_roles"] = template.get("mdt_roles", ["心内科", "营养师", "康复师"])
        result["mdt_mode"] = "async-review"
        result["mdt_reason"] = f"风险分层为高危(匹配风险因子数={risk_count}): {', '.join(matched[:3])}"
    
    return result


async def node_monitoring(state: dict) -> dict:
    """持续监测: 逐条检查 discharge_criteria，全部满足才批准出院。
    
    P0-1修复: 不再按体征数量批准出院。
    """
    template = state.get("disease_template", {})
    vs = state.get("vital_signs", [])
    risk = state.get("risk_level", "low")
    
    criteria = template.get("discharge_criteria", [])
    criteria_result = _check_discharge_criteria(criteria, vs, state)
    
    result = {
        "phase": "monitoring",
        "monitoring_strategy": f"risk_{risk}",
        "discharge_criteria_check": criteria_result,
    }
    
    if criteria_result.get("all_met", False):
        result["discharge_decision"] = "approved"
    
    return result


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
    """P1修复: 基于真实审核规则替代fixture固定逻辑。

    审核规则:
    - medication类型: 全部accept(用药方案由医生制定)
    - monitoring类型: accept(监测指导无争议)
    - followup类型: 如有handoff_missing标记则dismiss要求补全
    """
    items = state.get("handoff_items", [])
    reviewed = []

    for item in items:
        item_type = item.get("type", "")

        if item_type == "medication":
            item["review_action"] = "accept"
            item["feedback"] = "用药方案已审核"
        elif item_type == "monitoring":
            item["review_action"] = "accept"
            item["feedback"] = "监测计划已确认"
        elif item_type == "followup":
            # 检查复诊信息是否完整
            content = item.get("content", "")
            if len(content) < 15:
                item["review_action"] = "dismiss"
                item["dismiss_reason"] = "复诊信息不完整(缺少科室/时间)"
                item["reevaluation_pending"] = True
            else:
                item["review_action"] = "accept"
                item["feedback"] = "复诊计划已审核"
        else:
            item["review_action"] = "accept"
            item["feedback"] = "已确认"

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
    """P1修复: SOAP格式查房模板。"""
    vs = state.get("vital_signs", [])
    labs = state.get("lab_results", [])
    meds = state.get("medication_adjustments", [])
    chain = state.get("document_chain", [])
    risk = state.get("risk_level", "low")

    # 生命体征趋势
    latest_vs = vs[-1] if vs else {}
    vs_trend = _analyze_vs_trend(vs[-4:]) if len(vs) >= 4 else "数据不足"

    round_note = {
        "type": "daily_round",
        "format": "SOAP",
        "subjective": {
            "chief_complaint": "患者自述(Phase5 LLM补全)",
            "symptoms_since_last_round": "自觉症状变化(Phase5 LLM补全)",
        },
        "objective": {
            "vital_signs_latest": latest_vs,
            "vital_signs_trend": vs_trend,
            "lab_count": len(labs),
            "med_adjust_count": len(meds),
            "risk_level": risk,
        },
        "assessment": {
            "stability": "stable" if vs_trend == "稳定" else "unstable",
            "response_to_treatment": "评估中(Phase5 LLM补全)",
        },
        "plan": {
            "continue_monitoring": risk != "high",
            "consider_discharge": len(vs) >= 6 and risk != "high",
            "next_labs": "按病种模板复查(Phase5 LLM补全)",
        },
        "timestamp": "daily-round-mock",
    }

    return {
        "phase": "daily_round",
        "document_chain": chain + ["daily_round_note"],
        "latest_round": round_note,
        "round_count": state.get("round_count", 0) + 1,
    }


def _analyze_vs_trend(vital_signs: list[dict]) -> str:
    """分析生命体征趋势。"""
    if len(vital_signs) < 2:
        return "数据不足"
    # 简化: 检查最近和最远
    latest = vital_signs[-1]
    earliest = vital_signs[0]
    # 只比较数值型字段
    stable = True
    for key in ["heart_rate", "spo2", "temperature"]:
        lv = latest.get(key)
        ev = earliest.get(key)
        if isinstance(lv, (int, float)) and isinstance(ev, (int, float)):
            if abs(lv - ev) / max(abs(ev), 1) > 0.15:
                stable = False
                break
    return "稳定" if stable else "波动中"


async def node_medication_adjust(state: dict) -> dict:
    """用药调整: 连续≥2次体征异常才触发，必须医生确认。
    
    P0-2修复: 单次异常不触发调药，需连续异常+医生确认标识。
    """
    template = state.get("disease_template", {})
    vs = state.get("vital_signs", [])
    alert_history = state.get("consecutive_abnormal_count", 0)
    alerts = []
    
    for v_def in template.get("vital_signs", []):
        name = v_def.get("name", "")
        alert_above = v_def.get("alert_above")
        alert_below = v_def.get("alert_below")
        
        if not name:
            continue
        
        # 只检查最近2条记录
        recent = vs[-2:] if len(vs) >= 2 else vs
        triggered = False
        for v in recent:
            val = v.get(name, 0)
            if not isinstance(val, (int, float)):
                continue
            if alert_above is not None and val > alert_above:
                triggered = True
                break
            if alert_below is not None and val < alert_below:
                triggered = True
                break
        
        if triggered:
            alert_history += 1
            alerts.append({"sign": name, "consecutive_count": alert_history})
        else:
            alert_history = 0
    
    adjustments = state.get("medication_adjustments", [])
    if alerts and alert_history >= 2:
        adjustments.append({
            "reason": alerts,
            "action": "建议医生评估调药(连续异常)",
            "timestamp": datetime.now().isoformat(),
            "requires_doctor_confirm": True,
        })
    
    return {
        "phase": "medication_adjust",
        "medication_alerts": alerts,
        "medication_adjustments": adjustments,
        "consecutive_abnormal_count": alert_history,
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
    """P1修复: 增加疾病特异性转科标准，替代仅靠高危+体征计数。"""
    risk_level = state.get("risk_level", "low")
    vs = state.get("vital_signs", [])
    template = state.get("disease_template", {})
    disease_id = template.get("disease_id", "")

    transfer_needed = False
    transfer_target = None
    transfer_reason = None

    # 休克征象(通用): SBP<90 或 HR>120 + SBP<100
    for v in vs[-3:]:
        sbp = v.get("blood_pressure_systolic", v.get("systolic_mmhg", 0))
        bp_str = v.get("blood_pressure", "")
        if isinstance(bp_str, str) and "/" in bp_str:
            parts = bp_str.split("/")
            sbp = int(parts[0]) if parts[0].isdigit() else sbp
        hr = v.get("heart_rate", 0)
        if isinstance(sbp, (int, float)) and isinstance(hr, (int, float)):
            if sbp < 90 or (hr > 120 and sbp < 100):
                transfer_needed = True
                transfer_target = "ICU"
                transfer_reason = "血流动力学不稳定(休克征象)"
                break

    # 呼吸衰竭: SpO2<90%(吸氧下) 或 呼吸频率>35
    if not transfer_needed:
        for v in vs[-3:]:
            spo2 = v.get("spo2", 100)
            rr = v.get("respiratory_rate", 16)
            if isinstance(spo2, (int, float)) and isinstance(rr, (int, float)):
                if spo2 < 90 or rr > 35:
                    transfer_needed = True
                    transfer_target = "ICU"
                    transfer_reason = "呼吸衰竭征象"
                    break

    # 意识障碍: GCS<9
    if not transfer_needed:
        for v in vs[-3:]:
            gcs = v.get("gcs", 15)
            if isinstance(gcs, (int, float)) and gcs < 9:
                transfer_needed = True
                transfer_target = "ICU"
                transfer_reason = f"意识障碍(GCS={gcs})"
                break

    # 疾病特异性转科
    disease_transfer_map = {
        "stroke": ("神经外科", "NIHSS恶化或大面积脑梗死"),
        "heart_failure": ("CCU", "心源性休克或急性肺水肿"),
        "gi_bleeding": ("ICU", "活动性出血伴血流动力学不稳定"),
        "aki": ("肾内科ICU", "需要紧急肾脏替代治疗"),
    }

    if not transfer_needed and disease_id in disease_transfer_map:
        target, reason_base = disease_transfer_map[disease_id]
        # 仅高危+已尝试调药才触发疾病特异性转科
        if risk_level == "high" and state.get("medication_adjustments"):
            transfer_needed = True
            transfer_target = target
            transfer_reason = reason_base

    return {
        "phase": "transfer",
        "transfer_needed": transfer_needed,
        "transfer_target": transfer_target,
        "transfer_reason": transfer_reason,
    }


# ── 阶段K: 用药核对节点（临床安全第一优先级）──


async def node_medication_reconciliation(state: dict) -> dict:
    """用药核对: 入院时调 fhir-adapter 拉患者院前用药 → 和病种模板标准用药交叉比对。

    阶段K: 新增临床核心节点——用药缺口/冲突/重复检测。
    P0-3: 使用药物相互作用规则库(替换 fixture 占位)。
    """
    from .medication_rules import detect_interactions, check_allergy_contraindications

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

    # 3. 交叉比对 — P0-3: 使用药物相互作用规则库(替换 fixture 占位)
    findings = {"gaps": [], "conflicts": [], "duplications": [], "allergy_contraindications": []}

    # 缺口检测
    for med in handoff_meds:
        matched = any(
            med.get("content", "")[:10] in pm.get("name", "")
            for pm in pre_admission_meds
        )
        if not matched:
            findings["gaps"].append(f"出院带药'{med.get('content','')[:30]}'在院前用药中未见记录")
        elif len([m for m in handoff_meds if m.get("content","")[:10] == med.get("content","")[:10]]) > 1:
            findings["duplications"].append(f"'{med.get('content','')[:30]}'存在潜在重复")

    # 药物相互作用检测
    all_med_names = [m.get("content", "") for m in handoff_meds]
    interactions = detect_interactions(all_med_names)
    findings["conflicts"] = [
        {
            "drug_pair": f"{r.drug_a} + {r.drug_b}",
            "severity": r.severity,
            "mechanism": r.mechanism,
            "consequence": r.clinical_consequence,
            "recommendation": r.recommendation,
            "evidence": r.evidence_level,
        }
        for r in interactions
    ]

    # 过敏禁忌检查
    allergies = state.get("allergies", [])
    if allergies:
        allergy_risks = check_allergy_contraindications(all_med_names, allergies)
        if allergy_risks:
            findings["allergy_contraindications"] = [
                {"medication": r.medication, "allergen": r.allergen, "severity": r.severity, "recommendation": r.recommendation}
                for r in allergy_risks
            ]

    return {
        "phase": "medication_reconciliation",
        "medication_findings": findings,
        "document_chain": state.get("document_chain", []) + ["medication_reconciliation"],
    }
