"""Clinical decision audit trail regression tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_review_persists_request_actor_and_decision(monkeypatch):
    """A review decision must have a durable local audit record."""
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.models import AuditLog, Base, ClinicalWorkflowState, OutboxEvent
    from zhenhu.inpatient.routes.state_store import set_state

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(main, "async_engine", engine)
    monkeypatch.setattr(main, "async_session_factory", session_factory)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    patient_id = f"audit-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "admission"})

    class StubLoop:
        async def plan_turn(self, state):
            return state

    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/review/{patient_id}",
            json={"review_type": "doctor_confirm", "decision": "approved", "comment": "confirmed"},
            headers={
                "x-role": "doctor",
                "x-user-id": "11111111-1111-1111-1111-111111111111",
                "x-request-id": "request-audit-001",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "resumed"

    async with session_factory() as session:
        audit = (await session.scalars(select(AuditLog))).one()
        state = await session.get(ClinicalWorkflowState, patient_id)
        events = list(await session.scalars(select(OutboxEvent)))

    assert audit.actor_id == "11111111-1111-1111-1111-111111111111"
    assert audit.actor_role == "doctor"
    assert audit.action_type == "review"
    assert audit.target_record_id is None
    assert audit.session_id == "request-audit-001"
    assert audit.action_detail["patient_id"] == patient_id
    assert audit.action_detail["review_type"] == "doctor_confirm"
    assert audit.action_detail["decision"] == "approved"
    assert audit.target_table == "clinical_workflow_states"
    assert state is not None
    assert state.state_json["doctor_confirm_status"] == "approved"
    assert len(events) == 1

    await engine.dispose()


def test_production_rejects_demo_header_auth(monkeypatch):
    """A production deployment cannot rely on forgeable role headers."""
    from zhenhu.inpatient.middleware.auth import validate_auth_configuration

    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError, match="verified authentication provider"):
        validate_auth_configuration()


def test_direct_discharge_is_disabled_by_default(monkeypatch):
    """The legacy direct-discharge bypass cannot be re-enabled by environment."""
    from zhenhu.inpatient.agent.config import is_direct_discharge_enabled

    monkeypatch.delenv("ENABLE_DIRECT_DISCHARGE", raising=False)

    assert is_direct_discharge_enabled() is False
    monkeypatch.setenv("ENABLE_DIRECT_DISCHARGE", "true")
    assert is_direct_discharge_enabled() is False


def test_audit_context_preserves_the_authenticated_nurse_role():
    """Nurse actions must remain attributable to the authenticated clinician."""
    from starlette.requests import Request
    from zhenhu.inpatient.agent.audit import audit_context_from_request

    request = Request({"type": "http", "headers": []})
    request.state.user_info = {"actor_id": "11111111-1111-1111-1111-111111111111", "role": "nurse"}

    context = audit_context_from_request(request)

    assert context["actor_role"] == "nurse"
    assert context["actor_id"] == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_command_persists_request_actor_and_action(monkeypatch):
    """A doctor command must have a durable local audit record."""
    from zhenhu.inpatient import main
    from zhenhu.inpatient.models import AuditLog, Base
    from zhenhu.inpatient.routes.state_store import set_state

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(main, "async_engine", engine)
    monkeypatch.setattr(main, "async_session_factory", session_factory)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    patient_id = f"audit-command-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/{patient_id}/command",
            json={"action": "hold", "reason": "awaiting consultation"},
            headers={
                "x-role": "doctor",
                "x-user-id": "22222222-2222-2222-2222-222222222222",
                "x-request-id": "request-command-audit-001",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "held"

    async with session_factory() as session:
        audit = (await session.scalars(select(AuditLog))).one()

    assert audit.actor_id == "22222222-2222-2222-2222-222222222222"
    assert audit.action_type == "doctor_command"
    assert audit.action_detail["patient_id"] == patient_id
    assert audit.action_detail["action"] == "hold"
    assert audit.session_id == "request-command-audit-001"

    await engine.dispose()


@pytest.mark.asyncio
async def test_patient_command_rejects_nurse_role():
    """The dynamic patient command route is doctor-only."""
    from zhenhu.inpatient import main

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/audit-command-{uuid4()}/command",
            json={"action": "hold", "reason": "role check"},
            headers={"x-role": "nurse"},
        )

    assert response.status_code == 403
