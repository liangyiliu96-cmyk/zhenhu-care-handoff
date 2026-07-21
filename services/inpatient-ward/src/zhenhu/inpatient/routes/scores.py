"""临床评分面板端点 — GET /inpatient/{patient_id}/scores。

返回 NEWS2/qSOFA/Padua 评分及 VTE/卒中/MDT 状态，纯读 state_store，零副作用。
"""

from fastapi import APIRouter

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/inpatient", tags=["scores"])


def _score_payload(state: dict, score_key: str, risk_key: str, detail_key: str) -> dict:
    details = state.get("clinical_score_details")
    details = details if isinstance(details, dict) else {}
    detail = details.get(detail_key)
    detail = detail if isinstance(detail, dict) else {}
    score = state.get(score_key)
    risk = state.get(risk_key)
    basis = [str(item) for item in detail.get("basis", []) if str(item).strip()]

    if score is None:
        reason = "尚无体征数据，无法计算该评分" if not state.get("vital_signs") else "尚未完成该评分的规则计算"
        return {"score": None, "risk": None, "status": "not_available", "reason": reason, "basis": []}

    if not basis:
        basis = ["已由临床规则节点计算；当前状态未保存细项。"]
    return {"score": score, "risk": risk, "status": "available", "basis": basis}


@router.get("/{patient_id}/scores")
async def get_scores(patient_id: str):
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(
            error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"}
        )

    doc_chain = state.get("document_chain") or []

    score_details = state.get("clinical_score_details")
    score_details = score_details if isinstance(score_details, dict) else {}

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "news2": _score_payload(state, "news2_score", "news2_risk", "news2"),
        "qsofa": _score_payload(state, "qsofa_score", "qsofa_risk", "qsofa"),
        "padua": _score_payload(state, "padua_score", "padua_risk", "padua"),
        "score_source": score_details.get("source"),
        "calculated_at": score_details.get("calculated_at"),
        "vte_prophylaxis": "checked" if "vte_check" in doc_chain else "pending",
        "stroke_antithrombotic": state.get("stroke_antithrombotic_status") or ("checked" if "stroke_at_check" in doc_chain else "pending"),
        "mdt": "triggered" if "mdt_triggered" in doc_chain else "not triggered",
    })
