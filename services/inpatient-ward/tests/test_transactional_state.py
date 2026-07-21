"""Atomic clinical state, audit, and outbox persistence tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from uuid import uuid4


@pytest.mark.asyncio
async def test_clinical_state_audit_and_outbox_commit_in_one_transaction():
    from zhenhu.inpatient.models import AuditLog, Base, ClinicalWorkflowState, OutboxEvent
    from zhenhu.inpatient.services.transactional_state import commit_clinical_mutation

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        version = await commit_clinical_mutation(
            session,
            patient_id="transactional-state-1",
            state={"patient_id": "transactional-state-1", "phase": "monitoring"},
            expected_version=None,
            actor_id="11111111-1111-1111-1111-111111111111",
            actor_role="doctor",
            action_type="doctor_command",
            detail={"action": "hold"},
            idempotency_key="transactional-state-1",
            request_id="request-transactional-1",
        )

    assert version == 1
    async with session_factory() as session:
        state = await session.get(ClinicalWorkflowState, "transactional-state-1")
        audits = list(await session.scalars(select(AuditLog)))
        events = list(await session.scalars(select(OutboxEvent)))
    assert state.state_version == 1
    assert state.state_json["state_version"] == 1
    assert len(audits) == 1
    assert len(events) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_transactional_commit_catches_up_to_a_newer_legacy_state_version():
    from zhenhu.inpatient.models import Base, ClinicalWorkflowState
    from zhenhu.inpatient.services.transactional_state import commit_clinical_mutation

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add(ClinicalWorkflowState(
            patient_id="state-catchup",
            state_json={"patient_id": "state-catchup", "state_version": 1},
            state_version=1,
        ))
        await session.commit()

    async with session_factory() as session:
        version = await commit_clinical_mutation(
            session,
            patient_id="state-catchup",
            state={"patient_id": "state-catchup", "state_version": 3},
            expected_version=3,
            actor_id=None,
            actor_role="coordinator",
            action_type="vital_signs_reported",
            detail={},
            idempotency_key="state-catchup",
        )

    assert version == 4
    async with session_factory() as session:
        assert (await session.get(ClinicalWorkflowState, "state-catchup")).state_version == 4
    await engine.dispose()


@pytest.mark.asyncio
async def test_hold_command_uses_the_transactional_state_boundary(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.models import AuditLog, Base, ClinicalWorkflowState, OutboxEvent
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(main, "async_session_factory", session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    patient_id = f"transactional-hold-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/{patient_id}/command",
            json={"action": "hold", "reason": "test"},
            headers={"x-role": "doctor", "x-user-id": "11111111-1111-1111-1111-111111111111"},
        )

    assert response.status_code == 200
    async with session_factory() as session:
        assert await session.get(ClinicalWorkflowState, patient_id) is not None
        assert len(list(await session.scalars(select(AuditLog)))) == 1
        assert len(list(await session.scalars(select(OutboxEvent)))) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_consult_command_uses_the_transactional_state_boundary(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import outbox
    from zhenhu.inpatient.models import AuditLog, Base, ClinicalWorkflowState, OutboxEvent
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(main, "async_session_factory", session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def no_delivery(*args, **kwargs):
        return False

    monkeypatch.setattr(outbox, "deliver_outbox_event", no_delivery)
    patient_id = f"transactional-consult-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/{patient_id}/command",
            json={"action": "consult", "reason": "test", "target": "cardiology"},
            headers={"x-role": "doctor", "x-user-id": "11111111-1111-1111-1111-111111111111"},
        )

    assert response.status_code == 200
    async with session_factory() as session:
        state = await session.get(ClinicalWorkflowState, patient_id)
        audits = list(await session.scalars(select(AuditLog)))
        events = list(await session.scalars(select(OutboxEvent)))
    assert state is not None
    assert state.state_json["document_chain"][-1] == "consult_requested"
    assert len(audits) == 1
    assert audits[0].target_table == "clinical_workflow_states"
    assert len(events) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_hold_command_delegates_persistence_to_the_clinical_facade(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state
    from zhenhu.inpatient.services import clinical_facade

    patient_id = f"facade-hold-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    calls = []

    async def fake_commit(request, patient_id, state, *, action_type, detail, idempotency_scope):
        calls.append({
            "patient_id": patient_id,
            "action_type": action_type,
            "detail": detail,
            "idempotency_scope": idempotency_scope,
        })
        return state["state_version"] + 1

    monkeypatch.setattr(clinical_facade.clinical_workflow_facade, "commit", fake_commit)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/{patient_id}/command",
            json={"action": "hold", "reason": "facade test"},
            headers={"x-role": "doctor"},
        )

    assert response.status_code == 200
    assert calls == [{
        "patient_id": patient_id,
        "action_type": "doctor_command",
        "detail": {"action": "hold", "target": None, "reason": "facade test"},
        "idempotency_scope": "hold",
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,payload,action_type", [
    ("vitals", {"heart_rate": 80}, "vital_signs_reported"),
    ("labs", {"name": "K", "value": 4.2}, "lab_result_reported"),
])
async def test_monitoring_input_delegates_initial_write_to_clinical_facade(
    monkeypatch, endpoint, payload, action_type
):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent.loop import PatientAgentLoop
    from zhenhu.inpatient.routes.state_store import set_state
    from zhenhu.inpatient.services import clinical_facade

    patient_id = f"facade-monitoring-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    calls = []

    async def fake_commit(request, patient_id, state, *, action_type, detail, idempotency_scope):
        calls.append((patient_id, action_type, detail, idempotency_scope))
        return state["state_version"] + 1

    async def no_graph_work(self, state):
        return state

    monkeypatch.setattr(clinical_facade.clinical_workflow_facade, "commit", fake_commit)
    monkeypatch.setattr(PatientAgentLoop, "plan_turn", no_graph_work)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/monitoring/{patient_id}/{endpoint}",
            json=payload,
            headers={"x-role": "nurse"},
        )

    assert response.status_code == 200
    assert calls[0][0] == patient_id
    assert calls[0][1] == action_type
    assert calls[0][3] == action_type


@pytest.mark.asyncio
async def test_care_management_write_delegates_to_the_clinical_facade(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state
    from zhenhu.inpatient.services import clinical_facade

    patient_id = f"facade-care-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    calls = []

    async def fake_commit(request, patient_id, state, *, action_type, detail, idempotency_scope):
        calls.append((patient_id, action_type, detail, idempotency_scope))
        return state["state_version"] + 1

    monkeypatch.setattr(clinical_facade.clinical_workflow_facade, "commit", fake_commit)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/{patient_id}/care/medication-orders",
            json={"medication": "amlodipine", "dose": "5 mg", "frequency": "qd"},
            headers={"x-role": "doctor"},
        )

    assert response.status_code == 200
    assert calls[0][0] == patient_id
    assert calls[0][1] == "medication_order_created"
    assert calls[0][2]["status"] == "draft"
    assert calls[0][3] == "medication_order_created"


@pytest.mark.asyncio
async def test_discharge_initiation_delegates_to_the_clinical_facade(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.routes.state_store import get_state, set_state
    from zhenhu.inpatient.services import clinical_facade

    patient_id = f"facade-discharge-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    calls = []

    class StubLoop:
        traces = []

        async def plan_turn(self, state):
            return {**state, "phase": "discharge", "handoff_items": []}

    async def fake_commit(request, patient_id, state, *, action_type, detail, idempotency_scope):
        calls.append((patient_id, action_type, detail, idempotency_scope))
        return state["state_version"] + 1

    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())
    monkeypatch.setattr(clinical_facade.clinical_workflow_facade, "commit", fake_commit)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        version = get_state(patient_id)["state_version"]
        response = await client.post(
            f"/inpatient/discharge/{patient_id}",
            json={"reason": "患者符合出院条件", "expected_version": version},
            headers={"x-role": "doctor"},
        )

    assert response.status_code == 200
    assert calls == [(patient_id, "doctor_command", {"action": "discharge", "target": None, "reason": "患者符合出院条件"}, "discharge")]


@pytest.mark.asyncio
async def test_plan_persists_the_full_snapshot_for_pending_review(
    isolated_state_store, monkeypatch,
):
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.routes.state_store import get_state, set_state
    from zhenhu.inpatient.services.patient_state import patient_state_service

    patient_id = f"pending-snapshot-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    full_snapshot = {
        "patient_id": patient_id,
        "phase": "monitoring",
        "interrupt_pending": True,
        "pending_review": {
            "review_id": "review-next",
            "type": "med_confirm",
            "payload": {"reason": "requires confirmation"},
        },
        "graph_derived_marker": "must-persist",
    }

    class StubLoop:
        traces = []

        async def plan_turn(self, state):
            return {
                "status": "pending_review",
                "review_id": "review-next",
                "payload": full_snapshot["pending_review"],
            }

        def pending_state_snapshot(self):
            return full_snapshot

    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())

    result, _ = await patient_state_service.plan(patient_id, lambda state: None)

    assert result["status"] == "pending_review"
    persisted = get_state(patient_id)
    assert persisted["interrupt_pending"] is True
    assert persisted["pending_review"]["review_id"] == "review-next"
    assert persisted["graph_derived_marker"] == "must-persist"


@pytest.mark.asyncio
async def test_lab_monitoring_commits_derived_state_to_the_transactional_projection(
    isolated_state_store, monkeypatch,
):
    """The final graph result must not exist only in the hot state store."""
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.models import AuditLog, Base, ClinicalWorkflowState, OutboxEvent
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(main, "async_session_factory", session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    patient_id = f"transactional-monitoring-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})

    class StubLoop:
        traces = []

        async def plan_turn(self, state):
            return {
                **state,
                "latest_lab_review": {"interpretation": "within range"},
                "document_chain": [*state.get("document_chain", []), "lab_review"],
            }

    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/monitoring/{patient_id}/labs",
            json={"name": "K", "value": 4.2},
            headers={"x-role": "nurse"},
        )

    assert response.status_code == 200
    hot_state = get_state(patient_id)
    async with session_factory() as session:
        projection = await session.get(ClinicalWorkflowState, patient_id)
        audits = list(await session.scalars(select(AuditLog)))
        events = list(await session.scalars(select(OutboxEvent)))
    assert projection is not None
    assert projection.state_json["latest_lab_review"]["interpretation"] == "within range"
    assert projection.state_json["document_chain"][-1] == "lab_review"
    assert projection.state_json["state_version"] == hot_state["state_version"]
    assert projection.state_version == hot_state["state_version"]
    assert [audit.action_type for audit in audits] == ["lab_result_reported"]
    assert len(events) == 1
    await engine.dispose()
