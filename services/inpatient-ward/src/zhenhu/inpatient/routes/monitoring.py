"""Vital-sign and laboratory monitoring endpoints."""

import logging

from fastapi import APIRouter, BackgroundTasks, Request

from ..schemas import UnifiedResponse

_logger = logging.getLogger("zhenhu.monitoring")
from .route_schemas import LabResultsRequest, VitalSignsRequest

router = APIRouter(prefix="/inpatient", tags=["monitoring"])

_VITAL_RANGES = {
    "heart_rate": (20, 300),
    "spo2": (50, 100),
    "temperature": (34.0, 43.0),
    "systolic_mmhg": (50, 300),
    "diastolic_mmhg": (20, 200),
}

_CRITICAL_THRESHOLDS = {
    "\u949e": (3.0, 6.0),
    "\u94a0": (120, 155),
    "\u8840\u7cd6": (2.8, 25.0),
    "\u9499": (1.6, 3.5),
    "pH": (7.20, 7.60),
    "\u4e73\u9178": (0, 4.0),
    "\u767d\u7ec6\u80de": (1.0, 30.0),
    "\u8840\u5c0f\u677f": (20, 1000),
}


@router.post("/monitoring/{patient_id}/vitals")
async def report_vital_signs(patient_id: str, vital_data: VitalSignsRequest, request: Request, bg: BackgroundTasks):
    """Record one vital-sign observation and persist its derived workflow state."""
    from ..agent.nodes_monitoring import node_monitoring
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    vital_dict = vital_data.model_dump(exclude_none=True)
    expected_version = vital_dict.pop("expected_version", None)
    error = _validate_vital_ranges(vital_dict)
    if error is not None:
        return UnifiedResponse(error={"code": "INVALID_VITAL_RANGE", "message": error})

    def apply(state: dict) -> None:
        _assert_not_pending(state, "vital signs")
        existing = state.get("vital_signs", []) or []
        if existing:
            last = existing[-1]
            fields = ("heart_rate", "spo2", "temperature", "systolic_mmhg", "diastolic_mmhg")
            if all(vital_dict.get(key) is None or vital_dict.get(key) == last.get(key) for key in fields):
                raise _MonitoringInputError("DUPLICATE_VITAL", "vital signs duplicate the latest observation")
            current_ts, last_ts = vital_dict.get("timestamp", ""), last.get("timestamp", "")
            if current_ts and last_ts and current_ts < last_ts:
                raise _MonitoringInputError("OUT_OF_ORDER_VITAL", "vital-sign timestamp precedes the latest observation")
        state["vital_signs"] = [*existing, vital_dict]

    async def plan_monitoring(state: dict, loop) -> dict:
        focused_planner = getattr(loop, "plan_monitoring_turn", None)
        if callable(focused_planner):
            return await focused_planner(state, event_type="vitals")
        state.update(await node_monitoring(state))
        return await loop.plan_turn(state)

    try:
        result, _ = await patient_state_service.plan_clinical(
            request,
            patient_id,
            apply,
            action_type="vital_signs_reported",
            detail={"field_count": len(vital_dict)},
            idempotency_scope="vital_signs_reported",
            planner=plan_monitoring,
            expected_version=expected_version,
        )
    except PatientNotFoundError:
        return _not_found(patient_id)
    except _MonitoringInputError as exc:
        return UnifiedResponse(error={"code": exc.code, "message": exc.message})

    bg.add_task(_fhir_sync_vital, patient_id, vital_dict)
    return _vital_response(patient_id, result, await patient_state_service.read(patient_id))


async def _fhir_sync_vital(patient_id: str, vital_dict: dict):
    """Background task: sync vital signs to FHIR adapter."""
    try:
        from ..agent.fhir_sync import sync_observation

        await sync_observation(patient_id, {
            "name": "vital_sign",
            "value": vital_dict.get("heart_rate") or vital_dict.get("spo2") or vital_dict.get("temperature") or 0,
            "unit": "",
        })
    except Exception:
        pass


async def _fhir_sync_lab(patient_id: str, lab_dict: dict):
    """Background task: sync lab result to FHIR adapter."""
    try:
        from ..agent.fhir_sync import sync_observation

        await sync_observation(patient_id, {
            "name": str(lab_dict.get("name", "lab_result")),
            "value": str(lab_dict.get("value", "")),
            "unit": str(lab_dict.get("unit", "")),
        })
    except Exception:
        pass


@router.post("/monitoring/{patient_id}/labs")
async def report_lab_results(patient_id: str, lab_data: LabResultsRequest, request: Request, bg: BackgroundTasks):
    """Record one laboratory result and persist its derived workflow state."""
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    lab_dict = lab_data.model_dump(exclude_none=True)
    expected_version = lab_dict.pop("expected_version", None)

    def apply(state: dict) -> None:
        _assert_not_pending(state, "laboratory results")
        updates = {"lab_results": [*state.get("lab_results", []), lab_dict]}
        critical_alert = _critical_lab_alert(lab_dict)
        if critical_alert is not None:
            from ..services.clinical_alerts import canonicalize_alerts

            updates["clinical_alerts"] = canonicalize_alerts(
                [*(state.get("clinical_alerts", []) or []), critical_alert]
            )
        state.update(updates)

    async def plan_monitoring(state: dict, loop) -> dict:
        focused_planner = getattr(loop, "plan_monitoring_turn", None)
        if callable(focused_planner):
            return await focused_planner(state, event_type="lab")
        result = await loop.plan_turn(state)
        if result.get("status") == "pending_review" or result.get("discharge_decision") != "approved":
            return result
        state.clear()
        state.update(result)
        state["discharge_decision"] = "approved"
        return await loop.plan_turn(state)

    try:
        result, _ = await patient_state_service.plan_clinical(
            request,
            patient_id,
            apply,
            action_type="lab_result_reported",
            detail={"lab_name": str(lab_dict.get("name", ""))[:100]},
            idempotency_scope="lab_result_reported",
            planner=plan_monitoring,
            expected_version=expected_version,
        )
    except PatientNotFoundError:
        return _not_found(patient_id)
    except _MonitoringInputError as exc:
        return UnifiedResponse(error={"code": exc.code, "message": exc.message})

    bg.add_task(_fhir_sync_lab, patient_id, lab_dict)
    return _lab_response(patient_id, result, await patient_state_service.read(patient_id))


def _validate_vital_ranges(vital_dict: dict) -> str | None:
    errors = []
    for field, (low, high) in _VITAL_RANGES.items():
        value = vital_dict.get(field)
        if value is not None and not low <= value <= high:
            errors.append(f"{field}={value} is outside [{low}, {high}]")

    blood_pressure = vital_dict.get("blood_pressure")
    if blood_pressure and isinstance(blood_pressure, str):
        try:
            systolic, diastolic = (int(value) for value in blood_pressure.split("/"))
        except (TypeError, ValueError):
            errors.append("blood_pressure must be systolic/diastolic")
        else:
            if not 50 <= systolic <= 300:
                errors.append(f"blood_pressure systolic={systolic} is outside [50, 300]")
            if not 20 <= diastolic <= 200:
                errors.append(f"blood_pressure diastolic={diastolic} is outside [20, 200]")
    return "; ".join(errors) if errors else None


def _critical_lab_alert(lab: dict) -> str | None:
    name, value = lab.get("name", ""), lab.get("value")
    threshold = _CRITICAL_THRESHOLDS.get(name)
    if threshold is None or value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    low, high = threshold
    if low <= numeric_value <= high:
        return None
    return f"[critical lab] {name}={value} (reference range {low}-{high})"


def _assert_not_pending(state: dict, resource: str) -> None:
    if state.get("interrupt_pending"):
        raise _MonitoringInputError("PATIENT_PENDING_REVIEW", f"patient is pending review; cannot submit {resource}")


def _vital_response(patient_id: str, result: dict, persisted_state: dict) -> UnifiedResponse:
    if result.get("status") == "pending_review":
        return UnifiedResponse(data={
            "patient_id": patient_id,
            "vitals_count": len(persisted_state.get("vital_signs", [])),
            "phase": persisted_state.get("phase"),
            "pending_review": True,
            "review_id": result.get("review_id"),
            "review_type": result.get("payload", {}).get("type"),
            "pending_payload": result.get("payload"),
        })
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "vitals_count": len(result.get("vital_signs", [])),
        "phase": result.get("phase"),
        "auto_discharge": result.get("discharge_decision") == "approved",
        "discharge_decision": result.get("discharge_decision"),
        "handoff_items": result.get("handoff_items", []),
        "alerts": result.get("clinical_alerts", []),
    })


def _lab_response(patient_id: str, result: dict, persisted_state: dict) -> UnifiedResponse:
    if result.get("status") == "pending_review":
        return UnifiedResponse(data={
            "patient_id": patient_id,
            "lab_count": len(persisted_state.get("lab_results", [])),
            "phase": persisted_state.get("phase"),
            "pending_review": True,
            "review_id": result.get("review_id"),
            "review_type": result.get("payload", {}).get("type"),
            "pending_payload": result.get("payload"),
        })
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "lab_count": len(result.get("lab_results", [])),
        "phase": result.get("phase"),
        "auto_discharge": result.get("discharge_decision") == "approved",
        "discharge_decision": result.get("discharge_decision"),
        "handoff_items": result.get("handoff_items", []),
    })


def _not_found(patient_id: str) -> UnifiedResponse:
    return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"patient state not found: {patient_id}"})


class _MonitoringInputError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
