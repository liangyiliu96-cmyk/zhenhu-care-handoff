"""Transactional outbox delivery for FHIR audit events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import OutboxEvent


def _db_now() -> datetime:
    """Return UTC time in the naive form used by the existing SQL DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def enqueue_fhir_audit_event(
    session: AsyncSession,
    *,
    action: str,
    actor: str,
    patient_id: str,
    detail: dict[str, Any],
    idempotency_key: str,
) -> str:
    """Add a FHIR audit intent to the caller's current database transaction."""
    existing = await session.scalar(
        select(OutboxEvent.id).where(OutboxEvent.idempotency_key == idempotency_key)
    )
    if existing:
        return existing
    event_id = str(uuid4())
    session.add(OutboxEvent(
        id=event_id,
        event_type="fhir_audit_event",
        idempotency_key=idempotency_key,
        status="pending",
        attempts=0,
        payload={
            "action": action,
            "actor": actor,
            "detail": {"patient_ref": f"Patient/{patient_id}", **detail},
        },
    ))
    return event_id


async def deliver_outbox_event(event_id: str) -> bool:
    """Attempt one delivery and leave failures durably pending for retry."""
    from ..main import async_session_factory

    async with async_session_factory() as session:
        event = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update()
        )
        if event is None or event.status == "delivered":
            return event is not None
        now = _db_now()
        if event.status == "processing" and event.next_attempt_at and event.next_attempt_at > now:
            return False
        event.status = "processing"
        event.attempts += 1
        event.last_error = None
        # A crashed worker leaves a short lease, after which another worker can retry.
        event.next_attempt_at = now + timedelta(seconds=60)
        await session.commit()
        payload = dict(event.payload)
        idempotency_key = event.idempotency_key

    try:
        from .fhir_sync import sync_audit_event

        await sync_audit_event(
            action=payload["action"],
            actor=payload["actor"],
            detail=payload["detail"],
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        await _mark_delivery_failure(event_id, str(exc))
        return False

    async with async_session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        if event is None:
            return False
        event.status = "delivered"
        event.delivered_at = _db_now()
        event.next_attempt_at = None
        event.last_error = None
        await session.commit()
    return True


async def deliver_pending_outbox_events(limit: int = 100) -> int:
    """Retry due events; one failed event never blocks later independent events."""
    from ..main import async_session_factory

    now = _db_now()
    async with async_session_factory() as session:
        event_ids = list(await session.scalars(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.status.in_(("pending", "processing")),
                (OutboxEvent.next_attempt_at.is_(None)) | (OutboxEvent.next_attempt_at <= now),
            )
            .order_by(OutboxEvent.created_at)
            .limit(limit)
        ))
    delivered = 0
    for event_id in event_ids:
        delivered += int(await deliver_outbox_event(event_id))
    return delivered


async def _mark_delivery_failure(event_id: str, error: str) -> None:
    from ..main import async_session_factory

    async with async_session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        if event is None:
            return
        event.status = "pending"
        event.last_error = error[:1000]
        delay_seconds = min(300, 2 ** min(event.attempts, 8))
        event.next_attempt_at = _db_now() + timedelta(seconds=delay_seconds)
        await session.commit()
