"""出院小结端点 — GET /inpatient/{patient_id}/discharge-summary。

聚合五项已有数据，零 LLM 依赖，零副作用。
可选参数 ?narrative=true 触发 LLM 生成"住院经过"叙事段落。
"""

import json
import logging

from fastapi import APIRouter, Body, HTTPException, Query, Request

from ..schemas import UnifiedResponse
from ..services.clinical_alerts import alert_message
from .route_schemas import DischargeSummaryResponse
from ..agent.llm_utils import get_provider_for_node, safe_llm_invoke

logger = logging.getLogger("zhenhu.inpatient")

router = APIRouter(prefix="/inpatient", tags=["discharge"])

_COURSE_LABELS = {
    "intake_note": "完成入院病史采集",
    "physical_exam_note": "完成入院体格检查",
    "risk_assessment": "完成住院风险分层",
    "daily_round_note": "完成阶段性查房评估",
    "nursing_note": "完成护理观察与记录",
    "lab_review": "完成检验结果复核",
    "med_reviewed": "完成用药方案复核",
    "handoff_note": "完成出院交接事项整理，等待医生签字确认",
    "discharge_signed": "医生已完成出院签字",
    "discharge_bridge": "出院协同病例已创建",
    "confirm_note": "患者或照护者已完成确认",
}


@router.post("/{patient_id}/discharge-summary/export-audit")
async def audit_discharge_pdf_export(
    patient_id: str,
    request: Request,
    payload: dict[str, str] | None = Body(default=None),
):
    """Audit a doctor-requested final or clearly marked draft discharge export."""
    from .state_store import get_state
    from ..agent.audit import write_audit_event
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    user = getattr(request.state, "user_info", {}) or {}
    if "doctor" not in set(user.get("roles") or []):
        raise HTTPException(status_code=403, detail="出院文书仅限医生导出")
    try:
        require_patient_access(patient_id, user)
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc
    state = get_state(patient_id)
    if state is None:
        raise HTTPException(status_code=404, detail="未找到患者状态")
    export_kind = (payload or {}).get("export_kind", "final")
    if export_kind not in {"draft", "final"}:
        raise HTTPException(status_code=422, detail="export_kind 仅支持 draft 或 final")
    signed = state.get("discharge_sign_status") in {"signed", "approved"}
    if export_kind == "final" and not signed:
        raise HTTPException(status_code=409, detail="出院小结尚未完成医生签字")

    audit_id = await write_audit_event(
        action_type="discharge_pdf_export_requested" if export_kind == "final" else "discharge_pdf_draft_export_requested",
        patient_id=patient_id,
        detail={
            "state_version": state.get("state_version", 0),
            "discharge_sign_status": state.get("discharge_sign_status"),
            "export_kind": export_kind,
            "is_signed": signed,
            "summary_last_updated": state.get("last_updated", ""),
        },
        request=request,
    )
    return UnifiedResponse(data={"audit_id": audit_id, "state_version": state.get("state_version", 0), "export_kind": export_kind})


@router.get("/{patient_id}/discharge-summary")
async def get_discharge_summary(patient_id: str, narrative: bool = Query(default=False)):
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(
            error={"code": "NOT_FOUND", "message": f"未找到患者状态: {patient_id}"}
        )

    # 1. 住院经过：只输出临床可读内容，不泄露内部节点名称。
    timeline = state.get("document_chain", []) or []
    hospital_course = _build_hospital_course(state, timeline)

    # 2. 出院诊断
    diagnoses = state.get("ddx_list", []) or []

    # 3. 出院带药
    medications = [
        m for m in (state.get("medication_adjustments", []) or [])
        if isinstance(m, dict)
    ]

    # 4. 随访计划
    handoff_items = state.get("handoff_items", []) or []
    follow_up = [h for h in handoff_items if h.get("type") in {"follow_up", "followup"}]

    # 5. 住院期间关键事件
    alerts = state.get("clinical_alerts", []) or []
    reject_history = state.get("discharge_reject_history") or []
    reject_reasons = [r.get("reason", "") for r in reject_history if r.get("reason")]

    # 6. LLM 生成住院经过叙事段落（仅在 narrative=true 时触发）
    narrative_text = ""
    if narrative:
        try:
            provider = get_provider_for_node("discharge_summary")
            hpi = state.get("hpi_narrative") or ""
            pe = state.get("pe_narrative") or ""
            diagnosis = diagnoses[0].get("diagnosis", "") if diagnoses else ""

            vital_signs = state.get("vital_signs", [])
            latest_vs = vital_signs[-1] if vital_signs else {}

            timeline_str = " → ".join(timeline[-10:])
            prompt = (
                f"生成约200字的中文住院经过叙事段落：\n"
                f"入院诊断: {diagnosis}\n"
                f"现病史: {hpi[:300]}\n"
                f"关键事件: {timeline_str}\n"
                f"出院时体征: {json.dumps(latest_vs, ensure_ascii=False)[:200]}\n"
                f"仅返回叙事段落，不要其他内容。"
            )
            result = await safe_llm_invoke(provider, prompt, timeout=15.0, retries=0, caller="discharge_summary")
            if result:
                narrative_text = result.get("response") or result.get("hpi_narrative", "")
        except Exception:
            narrative_text = ""

    response = DischargeSummaryResponse(
        patient_id=patient_id,
        primary_diagnosis=(diagnoses[0].get("diagnosis", "") if diagnoses else ""),
        secondary_diagnoses=[d.get("diagnosis", "") for d in diagnoses[1:]] if len(diagnoses) > 1 else [],
        hospital_course=hospital_course,
        discharge_medications=medications,
        follow_up_plan=follow_up,
        critical_events=[alert_message(alert) for alert in alerts] + [f"拒签: {r}" for r in reject_reasons],
        discharge_decision=state.get("discharge_decision", ""),
        handoff_summary=handoff_items,
        last_updated=state.get("last_updated", ""),
        narrative=narrative_text,
    )

    # ##2 出院小结完整性 QA
    from ..agent.harness import validate_discharge_summary
    criteria = (state.get("disease_template") or {}).get("discharge_criteria", [])
    qa_text = "\n".join([
        narrative_text,
        *hospital_course,
        *[str(item.get("content", "")) for item in handoff_items if isinstance(item, dict)],
    ])
    completeness_check = validate_discharge_summary(qa_text, criteria)

    # 覆盖不足→在响应中标注 warning，不修改 state（GET 端点无副作用）
    if (
        completeness_check["coverage"] < 0.7
        and completeness_check["missing"]
        and state.get("discharge_decision") == "approved"
    ):
        missing_items = "; ".join(completeness_check["missing"][:3])
        completeness_check["warning"] = (
            f"出院小结覆盖不足({completeness_check['coverage']:.0%})，"
            f"建议医生复核以下缺失项: {missing_items}"
        )

    result = response.model_dump()
    result["completeness"] = completeness_check
    return UnifiedResponse(data=result)


def _build_hospital_course(state: dict, timeline: list[str]) -> list[str]:
    course: list[str] = []
    hpi = state.get("hpi_narrative") or (state.get("history_data") or {}).get("hpi_narrative")
    if hpi:
        course.append(f"入院情况：{hpi}")

    latest_round = state.get("latest_round") or {}
    if isinstance(latest_round, dict):
        assessment = latest_round.get("assessment")
        plan = latest_round.get("plan")
        if isinstance(assessment, str) and assessment:
            course.append(f"阶段评估：{assessment}")
        if isinstance(plan, str) and plan:
            course.append(f"治疗计划：{plan}")

    for node in timeline:
        label = _COURSE_LABELS.get(node)
        if label and label not in course:
            course.append(label)

    criteria = (state.get("disease_template") or {}).get("discharge_criteria", []) or []
    descriptions = {
        item.get("condition"): item.get("description")
        for item in criteria
        if isinstance(item, dict) and item.get("condition") and item.get("description")
    }
    checked = (state.get("discharge_criteria_check") or {}).get("checked", []) or []
    for condition in checked:
        description = descriptions.get(condition)
        if description:
            course.append(f"出院条件已确认：{description}")

    return course or ["住院经过尚待医生补充"]
