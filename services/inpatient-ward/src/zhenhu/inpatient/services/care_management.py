"""Explicit lifecycle tracking for post-discharge and multidisciplinary care."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from fastapi import Request

from .patient_state import PatientStateService

_ORDER_TRANSITIONS = {
    "draft": {"active", "cancelled"},
    "active": {"held", "discontinued"},
    "held": {"active", "discontinued"},
    "cancelled": set(),
    "discontinued": set(),
}

_INVESTIGATION_TRANSITIONS = {
    "ordered": {"scheduled", "completed", "cancelled"},
    "scheduled": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class CareRecordNotFoundError(Exception):
    """Raised when a lifecycle record does not belong to the patient."""


class InvalidCareTransitionError(Exception):
    """Raised when a lifecycle transition violates its state machine."""


class CareManagementService:
    """Owns non-LLM clinical coordination records and their transitions."""

    def __init__(self, patient_state: PatientStateService | None = None):
        self._patient_state = patient_state or PatientStateService()

    async def _mutate(
        self,
        patient_id: str,
        operation: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        request: Request | None,
        action_type: str,
        detail: Callable[[dict[str, Any]], dict[str, Any]],
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        if request is None:
            return await self._patient_state.mutate(patient_id, operation, expected_version=expected_version)
        return await self._patient_state.mutate_clinical(
            request,
            patient_id,
            operation,
            action_type=action_type,
            detail=detail,
            idempotency_scope=action_type,
            expected_version=expected_version,
        )

    async def add_medication_order(
        self, patient_id: str, payload: dict[str, Any], request: Request | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        def operation(state: dict[str, Any]) -> dict[str, Any]:
            order = build_medication_order(payload)
            state.setdefault("medication_orders", []).append(order)
            return order
        return await self._mutate(
            patient_id, operation, request=request, action_type="medication_order_created",
            detail=lambda order: {"order_id": order["id"], "medication": order["medication"], "status": order["status"]},
            expected_version=expected_version,
        )

    async def add_investigation_order(
        self, patient_id: str, payload: dict[str, Any], request: Request | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        def operation(state: dict[str, Any]) -> dict[str, Any]:
            order = build_investigation_order(payload)
            state.setdefault("investigation_orders", []).append(order)
            return order
        return await self._mutate(
            patient_id, operation, request=request, action_type="investigation_order_created",
            detail=lambda order: {"order_id": order["id"], "test_name": order["test_name"], "status": order["status"]},
            expected_version=expected_version,
        )

    async def update_investigation_order(
        self, patient_id: str, order_id: str, status: str, note: str = "", request: Request | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        def operation(state: dict[str, Any]) -> dict[str, Any]:
            order = _find(state.get("investigation_orders", []), order_id, "investigation order")
            if status not in _INVESTIGATION_TRANSITIONS.get(order["status"], set()):
                raise InvalidCareTransitionError(f"{order['status']} -> {status}")
            order.update(status=status, status_note=note, updated_at=_now())
            return order
        return await self._mutate(
            patient_id, operation, request=request, action_type="investigation_order_updated",
            detail=lambda order: {"order_id": order["id"], "status": order["status"]},
            expected_version=expected_version,
        )

    async def update_medication_order(
        self, patient_id: str, order_id: str, status: str, note: str = "", request: Request | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        def operation(state: dict[str, Any]) -> dict[str, Any]:
            order = _find(state.get("medication_orders", []), order_id, "medication order")
            if status not in _ORDER_TRANSITIONS.get(order["status"], set()):
                raise InvalidCareTransitionError(f"{order['status']} -> {status}")
            order.update(status=status, status_note=note, updated_at=_now())
            return order
        return await self._mutate(
            patient_id, operation, request=request, action_type="medication_order_updated",
            detail=lambda order: {"order_id": order["id"], "status": order["status"]},
            expected_version=expected_version,
        )

    async def create_mdt_request(
        self, patient_id: str, payload: dict[str, Any], request: Request | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        def operation(state: dict[str, Any]) -> dict[str, Any]:
            request = _record({"reason": payload["reason"], "specialties": payload["specialties"], "status": "requested", "decision": None, "summary": "", "resolved_at": None})
            state.setdefault("mdt_requests", []).append(request)
            return request
        return await self._mutate(
            patient_id, operation, request=request, action_type="mdt_request_created",
            detail=lambda mdt_request: {"mdt_request_id": mdt_request["id"], "specialties": mdt_request["specialties"]},
            expected_version=expected_version,
        )

    async def resolve_mdt_request(
        self, patient_id: str, request_id: str, decision: str, summary: str = "", request: Request | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        def operation(state: dict[str, Any]) -> dict[str, Any]:
            request = _find(state.get("mdt_requests", []), request_id, "MDT request")
            if request["status"] != "requested":
                raise InvalidCareTransitionError(f"MDT request is already {request['status']}")
            request.update(status="resolved", decision=decision, summary=summary, resolved_at=_now())
            return request
        return await self._mutate(
            patient_id, operation, request=request, action_type="mdt_request_resolved",
            detail=lambda mdt_request: {"mdt_request_id": mdt_request["id"], "decision": mdt_request["decision"]},
            expected_version=expected_version,
        )

    async def acknowledge_education(
        self, patient_id: str, payload: dict[str, Any], request: Request | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        def operation(state: dict[str, Any]) -> dict[str, Any]:
            record = _record({"topic": payload["topic"], "recipient": payload["recipient"], "teach_back": payload.get("teach_back") or "", "acknowledged": True, "acknowledged_at": _now()})
            state.setdefault("education_records", []).append(record)
            if state.get("patient_confirmation_status") == "pending" or "discharge_bridge" in (state.get("document_chain") or []):
                from ..agent.nodes_handoff import evaluate_patient_confirmation

                state.update(evaluate_patient_confirmation(state))
            return record
        record = await self._mutate(
            patient_id, operation, request=request, action_type="education_acknowledged",
            detail=lambda record: {"education_record_id": record["id"], "recipient": record["recipient"]},
            expected_version=expected_version,
        )
        state = await self._patient_state.read(patient_id)
        if state.get("patient_confirmation_status") == "confirmed":
            from ..agent.loop import cleanup_patient_loop

            cleanup_patient_loop(patient_id)
        return record

    async def create_follow_up_task(
        self, patient_id: str, payload: dict[str, Any], request: Request | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        def operation(state: dict[str, Any]) -> dict[str, Any]:
            task = build_follow_up_task(payload)
            state.setdefault("follow_up_tasks", []).append(task)
            return task
        return await self._mutate(
            patient_id, operation, request=request, action_type="follow_up_task_created",
            detail=lambda task: {"follow_up_task_id": task["id"], "due_at": task["due_at"]},
            expected_version=expected_version,
        )

    async def update_follow_up_task(
        self, patient_id: str, task_id: str, status: str, note: str = "", request: Request | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        def operation(state: dict[str, Any]) -> dict[str, Any]:
            task = _find(state.get("follow_up_tasks", []), task_id, "follow-up task")
            if task["status"] != "pending" or status not in {"completed", "cancelled"}:
                raise InvalidCareTransitionError(f"{task['status']} -> {status}")
            task.update(status=status, note=note, completed_at=_now() if status == "completed" else None)
            return task
        return await self._mutate(
            patient_id, operation, request=request, action_type="follow_up_task_updated",
            detail=lambda task: {"follow_up_task_id": task["id"], "status": task["status"]},
            expected_version=expected_version,
        )

    async def get_care_management(self, patient_id: str) -> dict[str, list[dict[str, Any]]]:
        state = await self._patient_state.read(patient_id)
        return {
            key: list(state.get(key, []))
            for key in (
                "medication_orders", "investigation_orders", "mdt_requests",
                "education_plans", "education_records", "follow_up_tasks",
            )
        }


def build_medication_order(
    payload: dict[str, Any], *, status: str = "draft", source_draft_id: str | None = None,
) -> dict[str, Any]:
    return _record({
        "medication": payload["medication"], "dose": payload["dose"],
        "frequency": payload["frequency"], "route": payload.get("route") or "PO",
        "indication": payload.get("indication") or "", "status": status,
        "status_note": "", "updated_at": _now(), "source_draft_id": source_draft_id,
    })


def build_investigation_order(
    payload: dict[str, Any], *, status: str = "ordered", source_draft_id: str | None = None,
) -> dict[str, Any]:
    return _record({
        "test_name": payload["test_name"], "priority": payload.get("priority") or "routine",
        "reason": payload["reason"], "timing": payload.get("timing") or "",
        "instructions": payload.get("instructions") or "", "status": status,
        "status_note": "", "updated_at": _now(), "source_draft_id": source_draft_id,
    })


def build_follow_up_task(payload: dict[str, Any], *, source_draft_id: str | None = None) -> dict[str, Any]:
    return _record({
        "title": payload["title"], "due_at": payload["due_at"],
        "assignee": payload.get("assignee") or None, "status": "pending", "note": "",
        "completed_at": None, "source_draft_id": source_draft_id,
    })


def build_mdt_request(payload: dict[str, Any], *, source_draft_id: str | None = None) -> dict[str, Any]:
    return _record({
        "reason": payload["reason"], "specialties": payload["specialties"], "status": "requested",
        "decision": None, "summary": "", "resolved_at": None, "source_draft_id": source_draft_id,
    })


def build_education_plan(payload: dict[str, Any], *, source_draft_id: str | None = None) -> dict[str, Any]:
    """Create a plan only; it must not be mistaken for a completed education record."""
    return _record({
        "topic": payload["topic"], "recipient": payload.get("recipient") or "patient",
        "key_points": payload.get("key_points") or [], "status": "planned",
        "source_draft_id": source_draft_id,
    })


def _find(records: list[dict[str, Any]], record_id: str, label: str) -> dict[str, Any]:
    for record in records:
        if record.get("id") == record_id:
            return record
    raise CareRecordNotFoundError(f"{label} {record_id}")


def _record(values: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    return {"id": str(uuid4()), "created_at": now, **values}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
