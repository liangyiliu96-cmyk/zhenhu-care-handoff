"""Sensitive patient contact endpoints for authorized follow-up work."""

from fastapi import APIRouter, HTTPException, Request

from ..agent.audit import write_audit_event
from ..schemas import UnifiedResponse
from ..services.follow_up_contacts import FollowUpContactConfigurationError, follow_up_contact_service
from ..services.patient_access import PatientAccessDeniedError, require_patient_access
from .route_schemas import FollowUpContactRequest
from .state_store import StateVersionConflictError, update_state

router = APIRouter(prefix="/inpatient", tags=["follow-up-contact"])


@router.get("/{patient_id}/follow-up-contact")
async def get_follow_up_contact(patient_id: str, request: Request):
    _require_access(patient_id, request)
    contact = await follow_up_contact_service.get(patient_id)
    try:
        await write_audit_event(action_type="follow_up_contact_viewed", patient_id=patient_id, detail={"has_contact": bool(contact and contact.get("mobile_phone")), "fields": ["follow_up_contact"]}, request=request)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="联系方式访问审计不可用") from exc
    return UnifiedResponse(data={"patient_id": patient_id, "contact": contact or {"follow_up_consent": False, "contact_version": 0}})


@router.post("/admissions/{patient_id}/follow-up-contact")
async def save_follow_up_contact(patient_id: str, data: FollowUpContactRequest, request: Request):
    _require_access(patient_id, request)
    try:
        contact = await follow_up_contact_service.save(patient_id, data.model_dump(), data.expected_contact_version)
    except ValueError as exc:
        if str(exc) == "CONTACT_VERSION_CONFLICT":
            raise HTTPException(status_code=409, detail="联系方式已被其他操作者更新，请刷新后重试") from exc
        raise
    except FollowUpContactConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        update_state(patient_id, {"follow_up_contact_registered": bool(contact.get("mobile_phone"))})
    except StateVersionConflictError:
        # The encrypted contact is already committed.  A concurrent clinical
        # update will refresh the dashboard on its next state write.
        pass
    try:
        await write_audit_event(action_type="follow_up_contact_updated", patient_id=patient_id, detail={"follow_up_consent": contact["follow_up_consent"], "preferred_channel": contact.get("preferred_channel"), "has_mobile_phone": bool(contact.get("mobile_phone")), "has_alternate_contact": bool(contact.get("alternate_contact_phone"))}, request=request)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="联系方式更新审计不可用") from exc
    return UnifiedResponse(data={"patient_id": patient_id, "contact": contact})


def _require_access(patient_id: str, request: Request) -> None:
    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者联系方式") from exc
