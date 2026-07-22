"""Read-only, evidence-linked preparation for a doctor's patient review."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..schemas import UnifiedResponse
from ..services.doctor_copilot import build_pre_round_brief, build_progress_note_draft
from ..services.patient_access import PatientAccessDeniedError, require_patient_access
from .state_store import get_state


router = APIRouter(prefix="/inpatient", tags=["doctor-copilot"])


class ProgressNoteDraftRequest(BaseModel):
    expected_version: int = Field(ge=1)


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


@router.post("/{patient_id}/doctor-copilot/progress-note-draft")
async def generate_progress_note(patient_id: str, body: ProgressNoteDraftRequest, request: Request):
    """Build a read-only, fact-bound SOAP draft for clinician editing."""

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc
    state = get_state(patient_id)
    if not state:
        raise HTTPException(status_code=404, detail="未找到患者状态")
    current_version = int(state.get("state_version") or 0)
    if body.expected_version != current_version:
        raise HTTPException(status_code=409, detail="患者状态已更新，请刷新后重新生成草稿")
    return UnifiedResponse(data=build_progress_note_draft(state))
