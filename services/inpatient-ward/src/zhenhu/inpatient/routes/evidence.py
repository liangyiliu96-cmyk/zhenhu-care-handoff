"""Read-only traceability view for RAG-supported clinical evidence."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/inpatient", tags=["clinical-evidence"])


@router.get("/{patient_id}/evidence")
async def get_patient_evidence(patient_id: str):
    """Return the bounded citation chain persisted with the patient state."""
    from .state_store import get_state

    state = get_state(patient_id)
    if state is None:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": "Patient state was not found."})
    citations = [item for item in (state.get("clinical_evidence") or []) if isinstance(item, dict)]
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "citations": citations,
        "count": len(citations),
    })


@router.get("/{patient_id}/evidence-graph")
async def get_patient_evidence_graph(patient_id: str, request: Request, focus: str = "", limit: int = 10):
    """Return the bounded graph pathway for one authorized patient's disease."""
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Patient access is denied") from exc

    from .state_store import get_state

    state = get_state(patient_id)
    if state is None:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": "Patient state was not found."})
    template = state.get("disease_template") if isinstance(state.get("disease_template"), dict) else {}
    disease_id = str(template.get("disease_id") or state.get("disease_id") or "").strip()
    if not disease_id:
        return UnifiedResponse(data={"patient_id": patient_id, "available": False, "reason": "No disease template is bound to this patient.", "evidence": [], "rules": []})

    from ..services.evidence_graph import EvidenceGraphUnavailable, disease_evidence

    try:
        graph = disease_evidence(disease_id, focus=focus, limit=limit)
    except EvidenceGraphUnavailable:
        return UnifiedResponse(data={"patient_id": patient_id, "disease_id": disease_id, "available": False, "reason": "Evidence graph is unavailable.", "evidence": [], "rules": []})
    return UnifiedResponse(data={"patient_id": patient_id, "available": True, **graph})
