from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


def _request(user: dict):
    return type("Request", (), {"state": type("State", (), {"user_info": user})()})()


def test_development_manager_capabilities(monkeypatch):
    from zhenhu.inpatient.services.management_access import management_capabilities

    monkeypatch.setenv("APP_ENV", "dev")
    result = management_capabilities(_request({"role": "doctor", "title": "科主任"}))

    assert result["writes_enabled"] is True
    assert all(result["operations"].values())


def test_non_manager_cannot_execute_management_operation():
    from zhenhu.inpatient.services.management_access import require_management_operation

    with pytest.raises(HTTPException) as exc:
        require_management_operation(_request({"role": "doctor", "title": "主治医师"}), "clear_expired")
    assert exc.value.status_code == 403


def test_production_requires_switch_and_permission_claim(monkeypatch):
    from zhenhu.inpatient.services.management_access import management_capabilities

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MANAGEMENT_OPERATIONS_ENABLED", "true")
    denied = management_capabilities(_request({"role": "doctor", "title": "科主任", "claims": {}}))
    allowed = management_capabilities(_request({"role": "doctor", "title": "科主任", "claims": {"permissions": ["zhenhu:admin:write"]}}))

    assert denied["writes_enabled"] is False
    assert allowed["writes_enabled"] is True


@pytest.mark.asyncio
async def test_clear_expired_is_audited_for_department_manager(client):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.models import AuditLog

    headers = {
        "x-role": "nurse",
        "x-user-id": "11111111-1111-1111-1111-111111111111",
        "x-title": quote("护士长"),
        "x-request-id": "management-operation-1",
    }
    response = await client.post("/inpatient/clear-expired", headers=headers)

    assert response.status_code == 200
    audit_id = response.json()["data"]["audit_id"]
    async with main.async_session_factory() as session:
        audit = await session.scalar(select(AuditLog).where(AuditLog.id == audit_id))
    assert audit is not None
    assert audit.actor_role == "nurse"
    assert audit.action_type == "expired_state_cleared"
    assert audit.target_table == "system_operations"


@pytest.mark.asyncio
async def test_regular_doctor_cannot_reindex_knowledge(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import rag_engine

    called = False

    def fake_index_all():
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(rag_engine, "index_all", fake_index_all)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/admin/rag/reindex", headers={"x-role": "doctor", "x-title": quote("主治医师")})

    assert response.status_code == 403
    assert called is False


@pytest.mark.asyncio
async def test_department_manager_can_reindex_selected_layers(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import rag_engine

    called_with = None

    def fake_index_all(layers=None):
        nonlocal called_with
        called_with = layers
        return {"L1": 6, "L5": 25}

    async def fake_audit(**_kwargs):
        return "audit-rag-reindex"

    monkeypatch.setattr(rag_engine, "index_all", fake_index_all)
    monkeypatch.setattr("zhenhu.inpatient.agent.audit.write_management_audit_event", fake_audit)
    headers = {"x-role": "doctor", "x-user-id": "manager-1", "x-title": quote("\u79d1\u4e3b\u4efb")}
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/admin/rag/reindex?layers=l1,L5", headers=headers)

    assert response.status_code == 200
    assert called_with == ["L1", "L5"]
    assert response.json()["data"]["total"] == 31


@pytest.mark.asyncio
async def test_reindex_runs_blocking_index_work_in_a_threadpool(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import rag_engine
    from zhenhu.inpatient.routes import rag_admin

    calls = []

    def fake_index_all(layers=None):
        return {layer: 1 for layer in layers or ["L1"]}

    async def fake_run_in_threadpool(function, *args):
        calls.append((function, args))
        return function(*args)

    async def fake_audit(**_kwargs):
        return "audit-rag-threadpool"

    monkeypatch.setattr(rag_engine, "index_all", fake_index_all)
    monkeypatch.setattr(rag_admin, "run_in_threadpool", fake_run_in_threadpool, raising=False)
    monkeypatch.setattr("zhenhu.inpatient.agent.audit.write_management_audit_event", fake_audit)
    headers = {"x-role": "doctor", "x-user-id": "manager-1", "x-title": quote("科主任")}
    monkeypatch.setattr("zhenhu.inpatient.services.management_access.require_management_operation", lambda *_args, **_kwargs: None)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/admin/rag/reindex?layers=L1")

    assert response.status_code == 200
    assert calls == [(fake_index_all, (["L1"],))]


def test_reindex_rejects_a_second_concurrent_request_without_touching_milvus(monkeypatch):
    from zhenhu.inpatient.agent import rag_engine

    class BusyLock:
        def acquire(self, blocking=False):
            assert blocking is False
            return False

    class Client:
        def flush(self, **_kwargs):
            raise AssertionError("Milvus must not be touched while a rebuild is active")

    monkeypatch.setattr(rag_engine, "_reindex_lock", BusyLock(), raising=False)
    monkeypatch.setattr(rag_engine, "build_index_documents", lambda: {"L1": []})
    monkeypatch.setattr(rag_engine, "_reset_collections", lambda _layers: None)
    monkeypatch.setattr(rag_engine, "collection_row_count", lambda _collection: 0)
    monkeypatch.setattr(rag_engine, "_c", lambda: Client())

    with pytest.raises(rag_engine.RagIndexError, match="RAG_REINDEX_IN_PROGRESS"):
        rag_engine.index_all(["L1"])


@pytest.mark.asyncio
async def test_reindex_rejects_unknown_layer_before_indexing(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import rag_engine

    monkeypatch.setattr(rag_engine, "index_all", lambda *_args, **_kwargs: pytest.fail("must not index"))
    headers = {"x-role": "nurse", "x-user-id": "manager-2", "x-title": quote("护士长")}
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/admin/rag/reindex?layers=L99", headers=headers)

    assert response.status_code == 422
    assert "L99" in response.text
