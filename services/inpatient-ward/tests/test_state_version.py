"""Optimistic version checks for patient state mutations."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from uuid import uuid4

import pytest


def test_sqlite_backend_rejects_stale_compare_and_swap():
    from zhenhu.inpatient.routes.state_store import SQLiteBackend, StateVersionConflictError

    with TemporaryDirectory() as directory:
        backend = SQLiteBackend(str(Path(directory) / "state.db"))
        now = time()
        backend.save("patient-cas", {"patient_id": "patient-cas", "state_version": 1}, now)
        backend.save(
            "patient-cas",
            {"patient_id": "patient-cas", "phase": "monitoring", "state_version": 2},
            now,
            expected_version=1,
        )

        with pytest.raises(StateVersionConflictError):
            backend.save(
                "patient-cas",
                {"patient_id": "patient-cas", "phase": "discharge", "state_version": 2},
                now,
                expected_version=1,
            )

        assert backend.load_all(ttl=3600)["patient-cas"][1]["state_version"] == 2


def test_sqlite_backend_recovers_expired_pending_review_state():
    from zhenhu.inpatient.routes.state_store import SQLiteBackend

    with TemporaryDirectory() as directory:
        backend = SQLiteBackend(str(Path(directory) / "state.db"))
        expired = time() - 7200
        backend.save(
            "pending-review",
            {
                "patient_id": "pending-review",
                "interrupt_pending": True,
                "pending_review": {"review_id": "review-1", "type": "doctor_confirm"},
                "state_version": 1,
            },
            expired,
        )
        backend.save(
            "ordinary-state",
            {"patient_id": "ordinary-state", "state_version": 1},
            expired,
        )

        restored = backend.load_all(ttl=60)

    assert restored["pending-review"][1]["pending_review"]["review_id"] == "review-1"
    assert "ordinary-state" not in restored


def test_sqlite_backend_recovers_post_discharge_state_within_follow_up_window(monkeypatch):
    from zhenhu.inpatient.routes import state_store

    monkeypatch.setattr(state_store, "_get_post_discharge_ttl", lambda: 90 * 24 * 60 * 60)
    with TemporaryDirectory() as directory:
        backend = state_store.SQLiteBackend(str(Path(directory) / "state.db"))
        expired_for_active_ward = time() - 7200
        backend.save(
            "post-discharge",
            {
                "patient_id": "post-discharge",
                "phase": "completed",
                "discharge_sign_status": "signed",
                "follow_up_tasks": [{"id": "task-1", "status": "pending"}],
                "state_version": 1,
            },
            expired_for_active_ward,
        )

        restored = backend.load_all(ttl=60)

    assert restored["post-discharge"][1]["follow_up_tasks"][0]["id"] == "task-1"


def test_pending_review_is_not_expired_from_the_in_memory_store(
    isolated_state_store, monkeypatch,
):
    from zhenhu.inpatient.routes import state_store

    patient_id = f"pending-memory-{uuid4()}"
    state_store.set_state(patient_id, {
        "patient_id": patient_id,
        "interrupt_pending": True,
        "pending_review": {"review_id": "review-memory", "type": "med_confirm"},
    })
    with state_store._lock:
        _, state = state_store._store[patient_id]
        state_store._store[patient_id] = (time() - 7200, state)
    monkeypatch.setattr(state_store, "_get_ttl", lambda: 60)

    assert state_store.force_cleanup() == 0
    assert state_store.get_state(patient_id)["pending_review"]["review_id"] == "review-memory"


def test_post_discharge_state_is_openable_from_follow_up_within_retention_window(
    isolated_state_store, monkeypatch,
):
    from zhenhu.inpatient.routes import state_store

    patient_id = f"post-discharge-memory-{uuid4()}"
    state_store.set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "completed",
        "discharge_sign_status": "signed",
        "follow_up_tasks": [{"id": "follow-up-memory", "status": "pending"}],
    })
    with state_store._lock:
        _, state = state_store._store[patient_id]
        state_store._store[patient_id] = (time() - 7200, state)
    monkeypatch.setattr(state_store, "_get_ttl", lambda: 60)
    monkeypatch.setattr(state_store, "_get_post_discharge_ttl", lambda: 90 * 24 * 60 * 60)

    assert state_store.force_cleanup() == 0
    assert patient_id in state_store.list_states()
    assert state_store.get_state(patient_id)["follow_up_tasks"][0]["id"] == "follow-up-memory"


@pytest.mark.asyncio
async def test_patient_state_mutation_rejects_stale_expected_version():
    from zhenhu.inpatient.routes.state_store import get_state, set_state, update_state
    from zhenhu.inpatient.services.patient_state import PatientStateService, StateVersionConflictError

    patient_id = f"version-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    current_version = get_state(patient_id)["state_version"]

    service = PatientStateService()
    await service.mutate(patient_id, lambda state: state.update(phase="discharge"), expected_version=current_version)

    with pytest.raises(StateVersionConflictError):
        await service.mutate(patient_id, lambda state: state.update(phase="monitoring"), expected_version=current_version)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,payload", [
    ("vitals", {"heart_rate": 75}),
    ("labs", {"name": "K", "value": 4.2}),
])
async def test_monitoring_writes_reject_stale_expected_version(endpoint, payload):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import get_state, set_state, update_state

    patient_id = f"version-monitoring-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    stale_version = get_state(patient_id)["state_version"]
    update_state(patient_id, {"phase": "monitoring"})

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/monitoring/{patient_id}/{endpoint}",
            json={**payload, "expected_version": stale_version},
            headers={"x-role": "nurse"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_VERSION_CONFLICT"


def test_state_store_increments_state_version_for_every_write():
    from zhenhu.inpatient.routes.state_store import get_state, set_state, update_state

    patient_id = f"version-store-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id})
    initial_version = get_state(patient_id)["state_version"]
    update_state(patient_id, {"phase": "monitoring"})

    assert get_state(patient_id)["state_version"] == initial_version + 1


@pytest.mark.asyncio
async def test_doctor_command_returns_conflict_for_stale_state_version(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import audit
    from zhenhu.inpatient.models import init_db
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    # ASGITransport does not run the application's lifespan hook.
    await init_db()
    patient_id = f"version-command-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    version = get_state(patient_id)["state_version"]

    async def skip_audit(**kwargs):
        return "audit-test"

    monkeypatch.setattr(audit, "write_audit_event", skip_audit)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        first = await client.post(
            f"/inpatient/{patient_id}/command",
            json={"action": "hold", "reason": "version test", "expected_version": version},
            headers={"x-role": "doctor"},
        )
        stale = await client.post(
            f"/inpatient/{patient_id}/command",
            json={"action": "resume", "reason": "version test", "expected_version": version},
            headers={"x-role": "doctor"},
        )

    assert first.status_code == 200
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_database_cas_conflict_uses_the_shared_http_409_contract(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import audit
    from zhenhu.inpatient.models import init_db
    from zhenhu.inpatient.routes import state_store

    await init_db()
    patient_id = f"version-cas-http-{uuid4()}"
    state_store.set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})

    class ConflictingBackend:
        def save(self, patient_id, state, timestamp, *, expected_version=None):
            raise state_store.StateVersionConflictError(patient_id)

    async def skip_audit(**kwargs):
        return "audit-test"

    monkeypatch.setattr(audit, "write_audit_event", skip_audit)
    monkeypatch.setattr(state_store, "_backend", ConflictingBackend())

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            f"/inpatient/{patient_id}/command",
            json={"action": "hold", "reason": "cas test"},
            headers={"x-role": "doctor"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_VERSION_CONFLICT"
    assert response.json()["error"]["current_version"] == 1


@pytest.mark.asyncio
async def test_transactional_state_conflict_uses_the_shared_http_409_contract(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from zhenhu.inpatient import main
    from zhenhu.inpatient.models import Base, ClinicalWorkflowState
    from zhenhu.inpatient.routes import state_store

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(main, "async_session_factory", session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    patient_id = f"version-transactional-http-{uuid4()}"
    state_store.set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    legacy_state = state_store.get_state(patient_id)
    async with session_factory() as session:
        session.add(ClinicalWorkflowState(
            patient_id=patient_id,
            state_json={"patient_id": patient_id, "phase": "monitoring", "state_version": 2},
            state_version=2,
        ))
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=main.app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/inpatient/{patient_id}/command",
            json={"action": "hold", "reason": "transactional cas", "expected_version": legacy_state["state_version"]},
            headers={"x-role": "doctor"},
        )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "STATE_VERSION_CONFLICT"
    assert payload["error"]["current_version"] == 2
    await engine.dispose()
