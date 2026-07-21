"""Read-only clinician workload reduction briefing endpoint."""

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse
from ..services.clinical_brief import build_clinical_brief
from ..services.patient_access import PatientAccessDeniedError, require_patient_access
from .state_store import get_state

router = APIRouter(prefix="/inpatient", tags=["clinical-brief"])


@router.get("/{patient_id}/clinical-brief")
async def get_clinical_brief(patient_id: str, request: Request):
    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc
    state = get_state(patient_id)
    if not state:
        raise HTTPException(status_code=404, detail="未找到患者状态")
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "state_version": int(state.get("state_version", 0)),
        **build_clinical_brief(state),
    })
