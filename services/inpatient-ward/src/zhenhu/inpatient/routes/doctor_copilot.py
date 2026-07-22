"""Read-only, evidence-linked preparation for a doctor's patient review."""

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse
from ..services.doctor_copilot import build_pre_round_brief
from ..services.patient_access import PatientAccessDeniedError, require_patient_access
from .state_store import get_state


router = APIRouter(prefix="/inpatient", tags=["doctor-copilot"])


@router.get("/{patient_id}/doctor-copilot/pre-round")
async def get_pre_round(patient_id: str, request: Request):
    """Return a non-persistent pre-round brief for the current patient state."""

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc
    state = get_state(patient_id)
    if not state:
        raise HTTPException(status_code=404, detail="未找到患者状态")
    return UnifiedResponse(data=build_pre_round_brief(state))
