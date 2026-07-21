"""Patient-level clinical-alert lifecycle endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from ..schemas import UnifiedResponse
from ..services.clinical_alerts import canonicalize_alerts
from .route_schemas import AlertLifecycleRequest

router = APIRouter(prefix="/inpatient", tags=["alerts"])


@router.get("/{patient_id}/alerts")
async def list_patient_alerts(patient_id: str):
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": "Patient state not found"})
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "state_version": state.get("state_version", 0),
        "alerts": canonicalize_alerts(state.get("clinical_alerts")),
    })


@router.post("/{patient_id}/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(patient_id: str, alert_id: str, request: Request, body: AlertLifecycleRequest | None = None):
    return await _transition_alert(patient_id, alert_id, "acknowledged", request, body)


@router.post("/{patient_id}/alerts/{alert_id}/resolve")
async def resolve_alert(patient_id: str, alert_id: str, request: Request, body: AlertLifecycleRequest | None = None):
    return await _transition_alert(patient_id, alert_id, "resolved", request, body)


async def _transition_alert(patient_id: str, alert_id: str, target_status: str, request: Request, body: AlertLifecycleRequest | None):
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    expected_version = body.expected_version if body is not None else None

    def transition(state: dict) -> tuple[dict, bool]:
        alerts = canonicalize_alerts(state.get("clinical_alerts"))
        alert = next((item for item in alerts if item["alert_id"] == alert_id), None)
        if alert is None:
            raise LookupError(alert_id)
        if alert["status"] == target_status:
            return alert, False

        timestamp = datetime.now(timezone.utc).isoformat()
        actor = getattr(request.state, "user_info", {})
        actor_id = actor.get("actor_id") or actor.get("role") or "doctor"
        if target_status == "acknowledged" and alert["status"] != "resolved":
            alert["status"] = "acknowledged"
            alert.setdefault("acknowledged_at", timestamp)
            alert.setdefault("acknowledged_by", actor_id)
        elif target_status == "resolved":
            alert["status"] = "resolved"
            alert.setdefault("resolved_at", timestamp)
            alert.setdefault("resolved_by", actor_id)
        state["clinical_alerts"] = alerts
        return alert, True

    try:
        alert, _ = await patient_state_service.mutate_clinical(
            request,
            patient_id,
            transition,
            action_type=f"clinical_alert_{target_status}",
            detail=lambda item: {"alert_id": alert_id, "status": item[0]["status"]},
            idempotency_scope=f"alert:{alert_id}:{target_status}",
            should_commit=lambda item: item[1],
            expected_version=expected_version,
        )
    except PatientNotFoundError:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": "Patient state not found"})
    except LookupError:
        return UnifiedResponse(error={"code": "ALERT_NOT_FOUND", "message": "Clinical alert not found"})

    from .state_store import get_state

    state = get_state(patient_id)
    return UnifiedResponse(data={"patient_id": patient_id, "state_version": state["state_version"], "alert": alert})
