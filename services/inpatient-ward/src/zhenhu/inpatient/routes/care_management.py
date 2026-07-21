"""HTTP boundary for medication, MDT, education, and follow-up coordination."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from ..schemas import UnifiedResponse
from ..services.care_management import CareManagementService, CareRecordNotFoundError, InvalidCareTransitionError
from ..services.patient_state import PatientNotFoundError
from .route_schemas import EducationAcknowledgementRequest, FollowUpTaskRequest, FollowUpTaskUpdateRequest, InvestigationOrderRequest, InvestigationOrderStatusRequest, MDTDecisionRequest, MDTRequest, MedicationOrderRequest, MedicationOrderStatusRequest

router = APIRouter(prefix="/inpatient", tags=["care-management"])
_service = CareManagementService()


@router.get("/follow-up-overview")
async def get_follow_up_overview(request: Request, status: str | None = None, limit: int = 50, offset: int = 0):
    """Aggregate post-discharge follow-up work without exposing inaccessible patient records.

    The readmission field is a transparent rule-based follow-up priority, not a
    predictive model or a clinical diagnosis.
    """
    from .state_store import is_post_discharge_state, list_states
    from ..services.patient_access import can_access_patient_state

    user = getattr(request.state, "user_info", {})
    now = datetime.now(timezone.utc)
    records = list_states()
    patients: list[dict[str, Any]] = []

    for patient_id, state in records.items():
        if not isinstance(state, dict) or not can_access_patient_state(state, user):
            continue
        if not is_post_discharge_state(state):
            continue

        tasks = [_follow_up_task(task, now) for task in state.get("follow_up_tasks", []) if isinstance(task, dict)]
        open_tasks = [task for task in tasks if task["is_open"]]
        overdue_count = sum(task["is_overdue"] for task in open_tasks)
        abnormal_count = sum(task["has_abnormal_feedback"] for task in tasks)
        risk_level, risk_basis = _follow_up_risk(state)
        patient_data = state.get("patient_data", {}) or {}
        template = state.get("disease_template", {}) or {}
        patients.append({
            "patient_id": patient_id,
            "name": patient_data.get("name") or patient_id[:10],
            "disease": template.get("name") or template.get("disease_id") or "unknown",
            "department": template.get("department") or "未指定科室",
            "discharge_status": state.get("discharge_sign_status") or state.get("phase") or "unknown",
            "follow_up_status": "overdue" if overdue_count else "pending" if open_tasks else "completed" if tasks else "unplanned",
            "pending_task_count": len(open_tasks),
            "overdue_task_count": overdue_count,
            "abnormal_feedback_count": abnormal_count,
            "feedback_status": "abnormal" if abnormal_count else "unreported",
            "readmission_risk": risk_level,
            "risk_method": "rule_based_follow_up_priority",
            "risk_basis": risk_basis,
            "next_due_at": min((task["due_at"] for task in open_tasks if task["due_at"]), default=None),
            "tasks": tasks,
        })

    if status in {"pending", "overdue", "abnormal", "high_risk"}:
        patients = [patient for patient in patients if _matches_follow_up_status(patient, status)]

    rank = {"high": 0, "medium": 1, "low": 2}
    patients.sort(key=lambda patient: (
        0 if patient["overdue_task_count"] else 1,
        0 if patient["abnormal_feedback_count"] else 1,
        rank.get(patient["readmission_risk"], 3),
        patient["next_due_at"] or "9999-12-31T23:59:59+00:00",
        patient["name"],
    ))
    page = patients[offset:offset + max(1, min(limit, 200))]
    from ..services.follow_up_contacts import follow_up_contact_service
    contact_summaries = await follow_up_contact_service.summaries([patient["patient_id"] for patient in page])
    for patient in page:
        patient["contact"] = contact_summaries.get(patient["patient_id"], {
            "has_contact": False,
            "follow_up_consent": False,
            "preferred_channel": None,
            "masked_mobile_phone": None,
        })
    return UnifiedResponse(data={
        "summary": {
            "total_patients": len(patients),
            "pending_follow_ups": sum(patient["pending_task_count"] for patient in patients),
            "overdue_follow_ups": sum(patient["overdue_task_count"] for patient in patients),
            "abnormal_feedbacks": sum(patient["abnormal_feedback_count"] for patient in patients),
            "high_readmission_risk": sum(patient["readmission_risk"] == "high" for patient in patients),
        },
        "risk_method": "rule_based_follow_up_priority",
        "filters": {"status": status},
        "patients": page,
        "pagination": {"limit": limit, "offset": offset, "returned": len(page), "has_more": offset + limit < len(patients)},
    })


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _follow_up_task(task: dict[str, Any], now: datetime) -> dict[str, Any]:
    task_status = str(task.get("status") or "pending").lower()
    due_at = task.get("due_at") if isinstance(task.get("due_at"), str) else None
    due = _parse_timestamp(due_at)
    is_open = task_status not in {"completed", "cancelled", "canceled"}
    feedback_level = str(task.get("feedback_level") or task.get("patient_feedback_level") or "").lower()
    abnormal = bool(task.get("abnormal_feedback")) or feedback_level in {"abnormal", "warning", "critical", "high"}
    return {
        "id": str(task.get("id") or ""),
        "title": str(task.get("title") or "随访任务"),
        "due_at": due_at,
        "assignee": task.get("assignee"),
        "status": task_status,
        "note": task.get("note") or "",
        "is_open": is_open,
        "is_overdue": bool(is_open and due and due < now),
        "has_abnormal_feedback": abnormal,
    }


def _follow_up_risk(state: dict[str, Any]) -> tuple[str, list[str]]:
    basis: list[str] = []
    risk = str(state.get("risk_level") or "").lower()
    alerts = state.get("clinical_alerts", []) or []
    history = state.get("patient_history", {}) or {}
    comorbidities = history.get("comorbidities", []) or []
    if risk == "high" or alerts:
        if risk == "high":
            basis.append("住院期间高风险分层")
        if alerts:
            basis.append("住院期间存在临床告警")
        return "high", basis
    if risk == "medium" or history.get("prior_hospitalization") or len(comorbidities) >= 2:
        if risk == "medium":
            basis.append("住院期间中风险分层")
        if history.get("prior_hospitalization"):
            basis.append("既往住院史")
        if len(comorbidities) >= 2:
            basis.append("多病共存")
        return "medium", basis
    return "low", ["未发现规则升级条件"]


def _matches_follow_up_status(patient: dict[str, Any], status: str) -> bool:
    return (
        status == "pending" and patient["pending_task_count"] > 0
        or status == "overdue" and patient["overdue_task_count"] > 0
        or status == "abnormal" and patient["abnormal_feedback_count"] > 0
        or status == "high_risk" and patient["readmission_risk"] == "high"
    )


@router.get("/{patient_id}/care-management")
async def get_care_management(patient_id: str):
    try:
        care = await _service.get_care_management(patient_id)
        return UnifiedResponse(data={"patient_id": patient_id, "care_management": care})
    except PatientNotFoundError:
        return _not_found()


@router.post("/{patient_id}/care/medication-orders")
async def add_medication_order(patient_id: str, body: MedicationOrderRequest, request: Request = None):
    try:
        order = await _service.add_medication_order(patient_id, body.model_dump(), request, body.expected_version)
        return UnifiedResponse(data={"patient_id": patient_id, "medication_order": order})
    except PatientNotFoundError:
        return _not_found()


@router.patch("/{patient_id}/care/medication-orders/{order_id}")
async def update_medication_order(patient_id: str, order_id: str, body: MedicationOrderStatusRequest, request: Request = None):
    try:
        order = await _service.update_medication_order(patient_id, order_id, body.status, body.note, request, body.expected_version)
        return UnifiedResponse(data={"patient_id": patient_id, "medication_order": order})
    except PatientNotFoundError:
        return _not_found()
    except CareRecordNotFoundError:
        return _missing("MEDICATION_ORDER_NOT_FOUND")
    except InvalidCareTransitionError as exc:
        return UnifiedResponse(error={"code": "INVALID_ORDER_TRANSITION", "message": str(exc)})


@router.post("/{patient_id}/care/investigation-orders")
async def add_investigation_order(patient_id: str, body: InvestigationOrderRequest, request: Request = None):
    try:
        order = await _service.add_investigation_order(patient_id, body.model_dump(), request, body.expected_version)
        return UnifiedResponse(data={"patient_id": patient_id, "investigation_order": order})
    except PatientNotFoundError:
        return _not_found()


@router.patch("/{patient_id}/care/investigation-orders/{order_id}")
async def update_investigation_order(patient_id: str, order_id: str, body: InvestigationOrderStatusRequest, request: Request = None):
    try:
        order = await _service.update_investigation_order(patient_id, order_id, body.status, body.note, request, body.expected_version)
        return UnifiedResponse(data={"patient_id": patient_id, "investigation_order": order})
    except PatientNotFoundError:
        return _not_found()
    except CareRecordNotFoundError:
        return _missing("INVESTIGATION_ORDER_NOT_FOUND")
    except InvalidCareTransitionError as exc:
        return UnifiedResponse(error={"code": "INVALID_INVESTIGATION_TRANSITION", "message": str(exc)})


@router.post("/{patient_id}/care/mdt-requests")
async def create_mdt_request(patient_id: str, body: MDTRequest, request: Request = None):
    try:
        mdt_request = await _service.create_mdt_request(patient_id, body.model_dump(), request, body.expected_version)
        return UnifiedResponse(data={"patient_id": patient_id, "mdt_request": mdt_request})
    except PatientNotFoundError:
        return _not_found()


@router.patch("/{patient_id}/care/mdt-requests/{request_id}")
async def resolve_mdt_request(patient_id: str, request_id: str, body: MDTDecisionRequest, request: Request = None):
    try:
        mdt_request = await _service.resolve_mdt_request(patient_id, request_id, body.decision, body.summary, request, body.expected_version)
        return UnifiedResponse(data={"patient_id": patient_id, "mdt_request": mdt_request})
    except PatientNotFoundError:
        return _not_found()
    except CareRecordNotFoundError:
        return _missing("MDT_REQUEST_NOT_FOUND")
    except InvalidCareTransitionError as exc:
        return UnifiedResponse(error={"code": "INVALID_MDT_TRANSITION", "message": str(exc)})


@router.post("/{patient_id}/care/education-records")
async def acknowledge_education(patient_id: str, body: EducationAcknowledgementRequest, request: Request = None):
    try:
        record = await _service.acknowledge_education(patient_id, body.model_dump(), request, body.expected_version)
        return UnifiedResponse(data={"patient_id": patient_id, "education_record": record})
    except PatientNotFoundError:
        return _not_found()


@router.post("/{patient_id}/care/follow-up-tasks")
async def create_follow_up_task(patient_id: str, body: FollowUpTaskRequest, request: Request = None):
    try:
        task = await _service.create_follow_up_task(patient_id, body.model_dump(), request, body.expected_version)
        return UnifiedResponse(data={"patient_id": patient_id, "follow_up_task": task})
    except PatientNotFoundError:
        return _not_found()


@router.patch("/{patient_id}/care/follow-up-tasks/{task_id}")
async def update_follow_up_task(patient_id: str, task_id: str, body: FollowUpTaskUpdateRequest, request: Request = None):
    try:
        task = await _service.update_follow_up_task(patient_id, task_id, body.status, body.note, request, body.expected_version)
        return UnifiedResponse(data={"patient_id": patient_id, "follow_up_task": task})
    except PatientNotFoundError:
        return _not_found()
    except CareRecordNotFoundError:
        return _missing("FOLLOW_UP_TASK_NOT_FOUND")
    except InvalidCareTransitionError as exc:
        return UnifiedResponse(error={"code": "INVALID_TASK_TRANSITION", "message": str(exc)})


def _not_found() -> UnifiedResponse:
    return UnifiedResponse(error={"code": "NOT_FOUND", "message": "Patient workflow state was not found"})


def _missing(code: str) -> UnifiedResponse:
    return UnifiedResponse(error={"code": code, "message": "The requested care record was not found"})
