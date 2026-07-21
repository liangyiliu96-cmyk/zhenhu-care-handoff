"""Discharge compatibility and handoff acknowledgement routes."""

import logging

from fastapi import APIRouter, Request

from ..schemas import UnifiedResponse
from .route_schemas import DischargeInitiationRequest, DoctorCommandRequest

logger = logging.getLogger("zhenhu.inpatient")

router = APIRouter(prefix="/inpatient", tags=["discharge"])
@router.post("/discharge/{patient_id}")
async def initiate_discharge(
    patient_id: str,
    request: Request = None,
    body: DischargeInitiationRequest | None = None,
) -> UnifiedResponse:
    """Start the formal discharge workflow through the doctor-command boundary."""
    from .command import submit_command
    from .state_store import get_state

    response = await submit_command(
        patient_id,
        DoctorCommandRequest(
            action="discharge",
            reason=(body.reason.strip() if body and body.reason.strip() else "医生发起出院流程"),
            expected_version=body.expected_version if body else None,
        ),
        request,
    )
    if response.error:
        return response
    state = get_state(patient_id) or {}
    data = dict(response.data or {})
    data.update({
        "handoff_items": state.get("handoff_items", []),
        "workflow_endpoint": f"/inpatient/discharge/{patient_id}",
        "command_endpoint": f"/inpatient/{patient_id}/command",
    })
    logger.info("Discharge workflow started through doctor command: patient_id=%s", patient_id)
    return UnifiedResponse(data=data)


# ##4 交接确认签收
@router.post("/discharge/{patient_id}/acknowledge-handoff")
async def acknowledge_handoff(patient_id: str, request: Request):
    """接收方确认签收交接事项。"""
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    def acknowledge(state: dict) -> tuple[int, bool, str | None]:
        already_acknowledged = bool(state.get("handoff_acknowledged"))
        state["handoff_acknowledged"] = True
        if state.get("patient_confirmation_status") == "pending" or "discharge_bridge" in (state.get("document_chain") or []):
            from ..agent.nodes_handoff import evaluate_patient_confirmation

            state.update(evaluate_patient_confirmation(state))
        return (
            len(state.get("handoff_items", [])),
            not already_acknowledged,
            state.get("patient_confirmation_status"),
        )

    try:
        handoff_items, committed, confirmation_status = await patient_state_service.mutate_clinical(
            request,
            patient_id,
            acknowledge,
            action_type="handoff_acknowledged",
            detail=lambda result: {"handoff_items": result[0], "patient_confirmation_status": result[2]},
            idempotency_scope="handoff_acknowledged",
            should_commit=lambda result: result[1],
        )
    except PatientNotFoundError:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": "患者入院记录不存在"})

    from .state_store import get_state

    state = get_state(patient_id) or {}
    if confirmation_status == "confirmed":
        from ..agent.loop import cleanup_patient_loop

        cleanup_patient_loop(patient_id)

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "handoff_acknowledged": True,
        "handoff_items": handoff_items,
        "patient_confirmation_status": confirmation_status,
        "state_version": state.get("state_version", 0),
        "idempotent": not committed,
    })
