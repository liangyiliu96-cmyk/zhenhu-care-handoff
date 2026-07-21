"""Doctor-reviewed operation drafts derived from clinical assistant replies."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..agent.assistant import (
    assistant_message_reference,
    can_access_session,
    extract_action_draft_suggestions,
    get_session,
)
from ..schemas import UnifiedResponse
from ..services.assistant_action_drafts import (
    AssistantActionDraftNotFoundError,
    AssistantActionDraftPayloadError,
    AssistantActionDraftTransitionError,
    assistant_action_draft_service,
    validate_action_payload,
)
from ..services.patient_access import PatientAccessDeniedError, require_patient_access
from ..services.patient_state import PatientNotFoundError
from .route_schemas import (
    AssistantActionDraftCreateRequest,
    AssistantActionDraftDecisionRequest,
    AssistantActionDraftGenerateRequest,
    AssistantActionDraftUpdateRequest,
)

router = APIRouter(prefix="/inpatient", tags=["assistant-action-drafts"])


@router.get("/{patient_id}/assistant-action-drafts")
async def list_action_drafts(patient_id: str, request: Request):
    _require_doctor_patient(request, patient_id)
    try:
        return UnifiedResponse(data=await assistant_action_draft_service.list(patient_id))
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到患者状态") from exc


@router.post("/{patient_id}/assistant-action-drafts/generate")
async def generate_action_drafts(patient_id: str, body: AssistantActionDraftGenerateRequest, request: Request):
    actor_id = _require_doctor_patient(request, patient_id)
    source_message_id = _require_source_message(body.session_id, patient_id, body.source_text, actor_id)
    suggestions = await extract_action_draft_suggestions(body.source_text)
    try:
        result = await assistant_action_draft_service.create_many(
            patient_id,
            suggestions,
            request=request,
            session_id=body.session_id,
            source_message_id=source_message_id,
            citations=body.citations,
            expected_version=body.expected_version,
        )
        return UnifiedResponse(data=result)
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到患者状态") from exc
    except AssistantActionDraftPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{patient_id}/assistant-action-drafts")
async def create_action_draft(patient_id: str, body: AssistantActionDraftCreateRequest, request: Request):
    actor_id = _require_doctor_patient(request, patient_id)
    source_message_id = _require_source_message(body.session_id, patient_id, body.source_text, actor_id)
    try:
        suggestion = {
            "draft_type": body.draft_type,
            "payload": validate_action_payload(body.draft_type, body.payload),
            "rationale": body.rationale,
        }
        result = await assistant_action_draft_service.create_many(
            patient_id,
            [suggestion],
            request=request,
            session_id=body.session_id,
            source_message_id=source_message_id,
            citations=body.citations,
            expected_version=body.expected_version,
        )
        return UnifiedResponse(data=result)
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到患者状态") from exc
    except AssistantActionDraftPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{patient_id}/assistant-action-drafts/{draft_id}")
async def update_action_draft(
    patient_id: str, draft_id: str, body: AssistantActionDraftUpdateRequest, request: Request,
):
    _require_doctor_patient(request, patient_id)
    try:
        result = await assistant_action_draft_service.update(
            patient_id,
            draft_id,
            body.payload,
            body.rationale,
            request=request,
            expected_version=body.expected_version,
        )
        return UnifiedResponse(data=result)
    except Exception as exc:
        _raise_draft_error(exc)


@router.post("/{patient_id}/assistant-action-drafts/{draft_id}/approve")
async def approve_action_draft(
    patient_id: str, draft_id: str, body: AssistantActionDraftDecisionRequest, request: Request,
):
    _require_doctor_patient(request, patient_id)
    try:
        result = await assistant_action_draft_service.approve(
            patient_id,
            draft_id,
            body.comment,
            request=request,
            expected_version=body.expected_version,
        )
        return UnifiedResponse(data=result)
    except Exception as exc:
        _raise_draft_error(exc)


@router.post("/{patient_id}/assistant-action-drafts/{draft_id}/reject")
async def reject_action_draft(
    patient_id: str, draft_id: str, body: AssistantActionDraftDecisionRequest, request: Request,
):
    _require_doctor_patient(request, patient_id)
    try:
        result = await assistant_action_draft_service.reject(
            patient_id,
            draft_id,
            body.comment,
            request=request,
            expected_version=body.expected_version,
        )
        return UnifiedResponse(data=result)
    except Exception as exc:
        _raise_draft_error(exc)


def _require_doctor_patient(request: Request, patient_id: str) -> str:
    user = getattr(request.state, "user_info", {}) or {}
    if user.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="操作草稿仅允许医生审核")
    actor_id = str(user.get("actor_id") or "").strip()
    if not actor_id:
        raise HTTPException(status_code=401, detail="操作草稿需要已认证的医生身份")
    try:
        require_patient_access(patient_id, user)
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc
    return actor_id


def _require_source_message(session_id: str, patient_id: str, source_text: str, actor_id: str) -> str:
    if not can_access_session(session_id, actor_id):
        raise HTTPException(status_code=403, detail="助手会话不属于当前医生")
    session = get_session(session_id) or {}
    if str(session.get("patient_id") or "") != patient_id:
        raise HTTPException(status_code=409, detail="助手会话与当前患者不匹配")
    reference = assistant_message_reference(session_id, source_text)
    if not reference:
        raise HTTPException(status_code=409, detail="该建议不是当前助手会话中的有效回复")
    return reference


def _raise_draft_error(exc: Exception) -> None:
    if isinstance(exc, PatientNotFoundError):
        raise HTTPException(status_code=404, detail="未找到患者状态") from exc
    if isinstance(exc, AssistantActionDraftNotFoundError):
        raise HTTPException(status_code=404, detail="未找到操作草稿") from exc
    if isinstance(exc, AssistantActionDraftPayloadError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, AssistantActionDraftTransitionError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc
