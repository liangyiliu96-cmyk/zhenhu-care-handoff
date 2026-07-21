"""Doctor-initiated clinical workflow commands."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import UnifiedResponse
from .route_schemas import DoctorCommandRequest

router = APIRouter(prefix="/inpatient", tags=["command"])

_PLANNED_ACTIONS = {"discharge", "transfer", "resume"}
_VALID_ACTIONS = _PLANNED_ACTIONS | {"consult", "hold"}


@router.post("/{patient_id}/command")
async def submit_command(patient_id: str, body: DoctorCommandRequest, request: Request = None):
    """Apply a doctor command through the clinical state transaction boundary."""
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    action = body.action
    if action not in _VALID_ACTIONS:
        return UnifiedResponse(error={"code": "INVALID_COMMAND", "message": f"未知命令: {action}"})

    def apply(state: dict) -> dict:
        state["doctor_command"] = action
        state["doctor_command_reason"] = body.reason
        state["doctor_command_context"] = body.context or {}
        if action == "discharge":
            state["discharge_decision"] = "approved"
        elif action == "transfer":
            state["transfer_needed"] = True
            state["transfer_target"] = body.target
            state["transfer_reason"] = body.reason
        elif action == "consult":
            from ..services.clinical_alerts import normalize_alerts

            state.setdefault("clinical_alerts", []).append(
                f"[会诊请求] {body.target or '未指定科室'}: {body.reason}"
            )
            state["clinical_alerts"] = normalize_alerts(state.get("clinical_alerts"))
            state.setdefault("document_chain", []).append("consult_requested")
            _clear_command(state)
        return state

    try:
        if action in _PLANNED_ACTIONS:
            if request is None:
                result, _ = await patient_state_service.plan(
                    patient_id, apply, finalize=lambda state, _: _clear_command(state),
                    expected_version=body.expected_version,
                )
            else:
                result, _ = await patient_state_service.plan_clinical(
                    request,
                    patient_id,
                    apply,
                    action_type="doctor_command",
                    detail=_command_detail(action, body),
                    idempotency_scope=action,
                    finalize=lambda state, _: _clear_command(state),
                    expected_version=body.expected_version,
                )
        elif request is None:
            result = await patient_state_service.mutate(
                patient_id, apply, expected_version=body.expected_version,
            )
        else:
            result = await patient_state_service.mutate_clinical(
                request,
                patient_id,
                apply,
                action_type="doctor_command",
                detail=lambda _: _command_detail(action, body),
                idempotency_scope=action,
                expected_version=body.expected_version,
            )
    except PatientNotFoundError:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到患者状态: {patient_id}"})

    if action == "hold":
        return UnifiedResponse(data={
            "patient_id": patient_id,
            "action": action,
            "status": "held",
            "phase": result.get("phase", "unknown"),
            "message": f"患者已暂停监测，原因: {body.reason}",
        })
    if action == "consult":
        return UnifiedResponse(data={
            "patient_id": patient_id,
            "action": action,
            "status": "executed",
            "phase": result.get("phase", "unknown"),
            "message": f"会诊请求已记录: {body.target or '未指定科室'}",
        })
    if isinstance(result, dict) and result.get("status") == "pending_review":
        return UnifiedResponse(data={
            "patient_id": patient_id,
            "action": action,
            "status": "pending_review",
            "phase": result.get("phase", "unknown"),
            "review_id": result.get("review_id"),
            "payload": result.get("payload"),
            "message": f"已进入{result.get('review_id', '')}审核",
        })
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "action": action,
        "status": "executed",
        "phase": result.get("phase", "unknown") if isinstance(result, dict) else "unknown",
        "message": f"命令 {action} 已执行",
    })


def _clear_command(state: dict) -> None:
    state["doctor_command"] = None
    state["doctor_command_reason"] = None
    state["doctor_command_context"] = None


def _command_detail(action: str, body: DoctorCommandRequest) -> dict:
    return {"action": action, "target": body.target, "reason": (body.reason or "")[:200]}
