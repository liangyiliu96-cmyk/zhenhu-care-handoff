"""Outbox persistence for FHIR audit synchronization."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_audit_and_fhir_outbox_intent_commit_together(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import outbox
    from zhenhu.inpatient.agent.audit import write_audit_event
    from zhenhu.inpatient.models import AuditLog, Base, OutboxEvent

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(main, "async_session_factory", session_factory)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def no_delivery(*args, **kwargs):
        return False

    monkeypatch.setattr(outbox, "deliver_outbox_event", no_delivery)
    request = SimpleNamespace(state=SimpleNamespace(
        user_info={"actor_id": "11111111-1111-1111-1111-111111111111", "role": "doctor"},
        request_id="outbox-request-001",
    ))

    await write_audit_event(
        action_type="review",
        patient_id="patient-outbox-001",
        detail={"decision": "approved"},
        request=request,
    )

    async with session_factory() as session:
        audits = list(await session.scalars(select(AuditLog)))
        events = list(await session.scalars(select(OutboxEvent)))

    assert len(audits) == 1
    assert len(events) == 1
    assert events[0].event_type == "fhir_audit_event"
    assert events[0].status == "pending"
    assert events[0].payload["action"] == "review"
    assert events[0].payload["detail"]["patient_ref"] == "Patient/patient-outbox-001"

    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_fhir_delivery_remains_pending_for_retry(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import fhir_sync, outbox
    from zhenhu.inpatient.models import Base, OutboxEvent

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(main, "async_session_factory", session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    event_id = str(uuid4())
    async with session_factory() as session:
        session.add(OutboxEvent(
            id=event_id,
            event_type="fhir_audit_event",
            idempotency_key=f"test-{event_id}",
            status="pending",
            attempts=0,
            payload={"action": "review", "actor": "doctor-1", "detail": {"patient_ref": "Patient/patient-1"}},
        ))
        await session.commit()

    async def failed_delivery(**kwargs):
        raise RuntimeError("fhir unavailable")

    monkeypatch.setattr(fhir_sync, "sync_audit_event", failed_delivery)

    assert await outbox.deliver_outbox_event(event_id) is False

    async with session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
    assert event.status == "pending"
    assert event.attempts == 1
    assert event.last_error == "fhir unavailable"
    assert event.next_attempt_at is not None

    await engine.dispose()
