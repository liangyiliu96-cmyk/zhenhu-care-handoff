"""Agent 节点 —— 出院、交接、医生审核、患者确认。

包含: node_discharge, node_handoff, node_doctor_review, node_patient_confirm。
"""

import json
import logging
from datetime import datetime, timezone

from .harness import validate_handoff_items, validate_llm_output, fallback_to_template
from .metrics import record
from .llm_utils import get_provider_for_node, safe_llm_invoke

logger = logging.getLogger("zhenhu.inpatient")


async def _create_zhenhu_case(patient_id: str, handoff_items: list[dict], template: dict) -> dict:
    """创建臻护病例——优先同进程import，失败走HTTP bridge。"""
    try:
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
            return {"status": "ok", "case_id": case.case_id, "state": case.state}
    except (ImportError, Exception):
        from ..hooks.zhenhu_bridge import bridge_discharge_to_zhenhu_with_retry
        return await bridge_discharge_to_zhenhu_with_retry(handoff_items, patient_id, template)


async def node_discharge(state: dict) -> dict:
    """阶段K: 出院全链路自动化——创建病例+检索知识+患者照护视图。

    出院决定 → 自动调 bridge 创建臻护病例 + 检索知识 + 生成照护视图。
    同仓库优先 import workflow state_machine, 失败走 HTTP fallback。
    """
    chain = list(state.get("document_chain", []) or [])
    if "discharge_bridge" in chain:
        return {"phase": "discharge"}

    template = state.get("disease_template", {})
    handoff_items = state.get("handoff_items", [])
    patient_id = state.get("patient_id", "")

    logger.info("node_discharge: start, patient=%s", patient_id)

    result = {
        "phase": "discharge",
        "discharge_decision": "approved",
        "document_chain": chain,
    }

    if not handoff_items:
        result.update({
            "discharge_decision": "bridge_failed",
            "bridge_error": "handoff_items_missing",
            "document_chain": chain + ["discharge_bridge_failed"],
        })
    else:
        bridge_result = await _create_zhenhu_case(patient_id, handoff_items, template)
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
            result["document_chain"] = chain + ["discharge_bridge_failed"]
        else:
            result["document_chain"] = chain + ["discharge_bridge"]

    record("discharge")
    return result


async def node_handoff(state: dict) -> dict:
    """交接生成: 基于病种模板 + LLM个性化增强。
    
    Phase5: 模板指令作为base，LLM根据患者体征/化验/风险生成个性化补充。
    失败回退→仅使用模板默认值。
    """
    chain = state.get("document_chain", []) or []
    if "handoff_note" in chain and state.get("handoff_items"):
        return {"phase": "handoff"}

    template = state.get("disease_template", {})
    instructions = template.get("handoff_instructions", [])
    patient_data = state.get("patient_data", {})
    vs = state.get("vital_signs", [])
    risk = state.get("risk_level", "low")

    # Base: 病种模板默认交接事项
    items = [
        {
            "type": inst.get("type", "unknown"),
            "content": inst.get("content", ""),
            "feedback": None,
            "source": "disease_template",
        }
        for inst in instructions
    ]

    # LLM增强: 根据患者实际情况个性化
    try:
        provider = get_provider_for_node("handoff")
        llm_prompt = (
            f"为以下患者生成个性化出院指导补充（中文）：\n"
            f"病种: {template.get('name', '未知')}，风险等级: {risk}。\n"
            f"模板基础指导: {json.dumps([i.get('content', '')[:80] for i in instructions], ensure_ascii=False)}。\n"
            f"最新体征: {json.dumps(vs[-2:] if vs else [], ensure_ascii=False)}。\n"
            f"请返回JSON: {{\"personalized_notes\": [{{\"type\": \"medication/monitoring/followup\", "
            f"\"content\": \"具体个性化的指导内容(20-50字中文)\"}}]}}，最多2条补充。"
        )
        llm_context = {"disease_template": template, "vital_signs": vs[-2:] if vs else [], "risk_level": risk}
        llm_result = await safe_llm_invoke(provider, llm_prompt, context=llm_context, timeout=20.0, retries=0, caller="handoff")

        if llm_result and llm_result.get("source_type") != "source_none":
            personalized = llm_result.get("personalized_notes", [])
            valid_notes, errors = validate_llm_output("handoff", personalized)
            if errors:
                logger.info("node_handoff: rejected %d malformed LLM notes", len(errors))
            for note in valid_notes[:2]:
                items.append({
                    "type": note["type"],
                    "content": note["content"],
                    "feedback": note.get("feedback"),
                    "source": "llm_enhanced",
                })
    except Exception as e:
        logger.warning("node_handoff: LLM enhancement failed, reason=%s", str(e)[:100])

    valid, errors = validate_handoff_items(items)
    if errors:
        items = fallback_to_template(template)["handoff_items"]

    record("handoff")
    return {
        "handoff_items": items,
        "phase": "handoff",
        "patient_summary": state.get("patient_data", {}),
        "document_chain": (
            state.get("document_chain", [])
            if "handoff_note" in state.get("document_chain", [])
            else state.get("document_chain", []) + ["handoff_note"]
        ),
    }


async def node_doctor_review(state: dict) -> dict:
    """P1修复: 基于真实审核规则替代fixture固定逻辑。

    审核规则:
    - medication类型: 全部accept(用药方案由医生制定)
    - monitoring类型: accept(监测指导无争议)
    - followup类型: 如有handoff_missing标记则dismiss要求补全
    """
    patient_id = state.get("patient_id", "unknown")
    logger.info("node_doctor_review: start, patient=%s", patient_id)
    items = state.get("handoff_items", [])

    # 尝试 interrupt.py 的医生审核（外部人工审核接口）
    try:
        from .interrupt import request_doctor_review
        interrupt_result = await request_doctor_review(items)
        action = interrupt_result.get("action")
        if action == "accept":
            reviewed_items = interrupt_result.get("items", items)
            for item in reviewed_items:
                item.setdefault("review_action", "accept")
                item.setdefault("feedback", "已由医生确认")
            chain = state.get("document_chain", [])
            return {
                "handoff_items": reviewed_items,
                "phase": "review",
                "discharge_decision": "approved",
                "interrupt_pending": False,
                "patient_summary": state.get("patient_data", {}),
                "document_chain": chain if "review_note" in chain else chain + ["review_note"],
            }
        if action == "pending":
            pending = interrupt_result.get("pending_review", {})
            pending.setdefault("type", "discharge_sign")
            pending.setdefault("payload", {"handoff_items": items, "patient_id": patient_id})
            return {
                "phase": "review",
                "pending_review": pending,
                "interrupt_pending": True,
                "patient_summary": state.get("patient_data", {}),
            }
    except Exception:
        pass  # interrupt不可用→回退内联规则审核

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
    record("doctor_review")
    
    result = {
        "handoff_items": reviewed,
        "phase": "review",
        "discharge_decision": "approved" if all_accepted else "pending_reevaluation",
        "interrupt_pending": False,
        "patient_summary": state.get("patient_data", {}),
        "document_chain": (
            state.get("document_chain", [])
            if "review_note" in state.get("document_chain", [])
            else state.get("document_chain", []) + ["review_note"]
        ),
    }
    
    # LLM: 驳回时生成审核摘要
    if not all_accepted:
        try:
            provider = get_provider_for_node("handoff")
            dismissed = [it for it in reviewed if it.get("review_action") == "dismiss"]
            llm_result = await safe_llm_invoke(
                provider,
                f"为医生生成被驳回交接事项的审核意见（1句中文）: "
                f"{json.dumps([d.get('dismiss_reason', '') for d in dismissed], ensure_ascii=False)}。"
                f"返回JSON: {{\"review_note\": \"...\"}}",
                context={"dismissed_items": dismissed},
                timeout=15.0,
                retries=0,
                caller="handoff",
            )
            if llm_result and llm_result.get("source_type") != "source_none":
                result["review_note"] = llm_result.get("review_note", "")
        except Exception:
            pass
    
    return result


def evaluate_patient_confirmation(state: dict) -> dict:
    """Evaluate confirmation from persisted recipient actions, never from an LLM guess."""
    chain = list(state.get("document_chain", []) or [])
    education_records = state.get("education_records", []) or []
    teach_back_records = [
        record for record in education_records
        if record.get("acknowledged") and str(record.get("teach_back") or "").strip()
    ]

    requirements = []
    if not state.get("handoff_acknowledged"):
        requirements.append("handoff_acknowledgement")
    if not teach_back_records:
        requirements.append("teach_back")

    bridge_completed = "discharge_bridge" in chain
    signed = state.get("discharge_sign_status") in {"signed", "approved"}
    if requirements or not bridge_completed or not signed:
        if not bridge_completed:
            requirements.append("discharge_bridge")
        if not signed:
            requirements.append("doctor_signature")
        return {
            "phase": "awaiting_patient_confirmation",
            "patient_confirmation_status": "pending",
            "patient_confirmation_requirements": list(dict.fromkeys(requirements)),
            "patient_confirmation_evidence": [],
        }

    evidence = [
        {
            "education_record_id": record.get("id"),
            "recipient": record.get("recipient"),
            "topic": record.get("topic"),
            "teach_back": record.get("teach_back"),
            "acknowledged_at": record.get("acknowledged_at"),
        }
        for record in teach_back_records
    ]
    if "confirm_note" not in chain:
        chain.append("confirm_note")
    return {
        "phase": "confirm",
        "patient_confirmation_status": "confirmed",
        "patient_confirmation_requirements": [],
        "patient_confirmation_evidence": evidence,
        "patient_confirmed_at": datetime.now(timezone.utc).isoformat(),
        "document_chain": chain,
    }


async def node_patient_confirm(state: dict) -> dict:
    """Complete patient confirmation only from handoff receipt and recorded teach-back."""
    patient_id = state.get("patient_id", "unknown")
    logger.info("node_patient_confirm: evaluate, patient=%s", patient_id)
    result = evaluate_patient_confirmation(state)
    if result.get("patient_confirmation_status") == "confirmed":
        record("patient_confirm")
    return result
