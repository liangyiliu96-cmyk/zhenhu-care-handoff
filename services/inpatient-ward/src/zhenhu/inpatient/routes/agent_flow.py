"""Read-only Agent/LLM workflow projection for clinical users."""

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse
from ..services.agent_flow import build_agent_flow
from ..services.patient_access import PatientAccessDeniedError, require_patient_access
from .state_store import get_state

router = APIRouter(prefix="/inpatient", tags=["agent-flow"])


@router.get("/{patient_id}/agent-flow")
async def get_agent_flow(patient_id: str, request: Request):
    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc
    state = get_state(patient_id)
    if not state:
        raise HTTPException(status_code=404, detail="未找到患者状态")
    user_info = getattr(request.state, "user_info", {})
    audience = "nurse" if user_info.get("role") == "nurse" else "clinical"
    return UnifiedResponse(data={"patient_id": patient_id, **build_agent_flow(state, audience=audience)})
