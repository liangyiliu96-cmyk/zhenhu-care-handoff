"""Durable audit events for clinically meaningful user actions."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import Request

from ..models import AuditActorRole, AuditLog

_AUDIT_ROLES = {role.value for role in AuditActorRole}


def audit_context_from_request(request: Request) -> dict[str, str | None]:
    """Extract the bounded, persisted part of a request identity."""
    user_info = getattr(request.state, "user_info", {}) or {}
    supplied_actor_id = user_info.get("actor_id")
    actor_id = None
    if supplied_actor_id:
        try:
            actor_id = str(UUID(str(supplied_actor_id)))
        except (TypeError, ValueError, AttributeError):
            pass

    role = str(user_info.get("role") or "system").lower()
    return {
        "actor_id": actor_id,
        "actor_role": role if role in _AUDIT_ROLES else AuditActorRole.SYSTEM.value,
        "request_id": _bounded_text(getattr(request.state, "request_id", None), 100),
        "external_actor_id": _bounded_text(supplied_actor_id, 100) if not actor_id else None,
    }


async def write_audit_event(
    *,
    action_type: str,
    patient_id: str,
    detail: dict[str, Any],
    request: Request,
) -> str:
    """Commit a local audit fact before optional downstream synchronization."""
    from ..main import async_session_factory

    context = audit_context_from_request(request)
    action_detail = {"patient_id": patient_id, **detail}
    if context["external_actor_id"]:
        action_detail["external_actor_id"] = context["external_actor_id"]

    audit = AuditLog(
        id=str(uuid4()),
        actor_id=context["actor_id"],
        actor_role=context["actor_role"],
        action_type=action_type,
        target_table="patient_state",
        # Patient state identifiers are not guaranteed to be UUIDs.
        target_record_id=None,
        action_detail=action_detail,
        session_id=context["request_id"],
    )
    idempotency_source = request.headers.get("idempotency-key") if hasattr(request, "headers") else None
    idempotency_source = _bounded_text(idempotency_source or context["request_id"] or str(uuid4()), 100)
    event_id: str
    async with async_session_factory() as session:
        session.add(audit)
        from .outbox import enqueue_fhir_audit_event

        actor = context["actor_id"] or context["external_actor_id"] or "unknown"
        event_id = await enqueue_fhir_audit_event(
            session,
            action=action_type,
            actor=actor,
            patient_id=patient_id,
            detail=detail,
            idempotency_key=f"fhir-audit:{action_type}:{patient_id}:{idempotency_source}",
        )
        await session.commit()
    from .outbox import deliver_outbox_event

    await deliver_outbox_event(event_id)
    return audit.id


async def write_management_audit_event(
    *,
    action_type: str,
    detail: dict[str, Any],
    request: Request,
) -> str:
    """Persist a non-patient administrative operation without emitting a FHIR patient event."""
    from ..main import async_session_factory

    context = audit_context_from_request(request)
    action_detail = dict(detail)
    if context["external_actor_id"]:
        action_detail["external_actor_id"] = context["external_actor_id"]
    audit = AuditLog(
        id=str(uuid4()),
        actor_id=context["actor_id"],
        actor_role=context["actor_role"],
        action_type=action_type,
        target_table="system_operations",
        target_record_id=None,
        action_detail=action_detail,
        session_id=context["request_id"],
    )
    async with async_session_factory() as session:
        session.add(audit)
        await session.commit()
    return audit.id


def _bounded_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None
