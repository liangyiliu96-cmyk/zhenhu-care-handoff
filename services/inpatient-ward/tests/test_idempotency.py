"""Durable Idempotency-Key storage regression tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request
from starlette.responses import StreamingResponse

from zhenhu.inpatient.models import Base, IdempotencyRecord
from zhenhu.inpatient.services.idempotency import (
    IdempotencyKeyConflictError,
    complete_request,
    reserve_request,
)


@pytest.mark.asyncio
async def test_idempotency_reservation_replays_completed_request():
    with TemporaryDirectory() as directory:
        engine = create_async_engine(f"sqlite+aiosqlite:///{Path(directory) / 'idempotency.db'}")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            first = await reserve_request(session, scope="doctor:POST:/write", key="key-1", fingerprint="a")
            assert first.is_new
            await complete_request(session, record_id=first.record.id, response_status=201, response_body={"data": {"id": "1"}})

        async with session_factory() as session:
            replay = await reserve_request(session, scope="doctor:POST:/write", key="key-1", fingerprint="a")
            assert not replay.is_new
            assert replay.record.status == "completed"
            assert replay.record.response_status == 201
            assert replay.record.response_body == {"data": {"id": "1"}}

        async with session_factory() as session:
            with pytest.raises(IdempotencyKeyConflictError):
                await reserve_request(session, scope="doctor:POST:/write", key="key-1", fingerprint="different")
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_idempotency_reservations_leave_one_request_owner():
    with TemporaryDirectory() as directory:
        engine = create_async_engine(f"sqlite+aiosqlite:///{Path(directory) / 'concurrent-idempotency.db'}")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async def reserve_once():
            async with session_factory() as session:
                return await reserve_request(session, scope="doctor:POST:/write", key="same-key", fingerprint="same")

        first, second = await asyncio.gather(reserve_once(), reserve_once())

        assert sum(item.is_new for item in (first, second)) == 1
        assert {item.record.status for item in (first, second)} == {"processing"}
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_write_replays_completed_response_without_second_state_mutation(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import audit
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    with TemporaryDirectory() as directory:
        engine = create_async_engine(f"sqlite+aiosqlite:///{Path(directory) / 'http-idempotency.db'}")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        monkeypatch.setattr(main, "async_session_factory", session_factory)

        async def skip_audit(**kwargs):
            return "audit-test"

        monkeypatch.setattr(audit, "write_audit_event", skip_audit)
        patient_id = f"idempotency-http-{uuid4()}"
        set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
        headers = {"x-role": "doctor", "Idempotency-Key": "command-hold-1"}

        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
            first = await client.post(
                f"/inpatient/{patient_id}/command",
                json={"action": "hold", "reason": "idempotency test"},
                headers=headers,
            )
            version_after_first = get_state(patient_id)["state_version"]
            replay = await client.post(
                f"/inpatient/{patient_id}/command",
                json={"action": "hold", "reason": "idempotency test"},
                headers=headers,
            )

        assert first.status_code == 200
        assert replay.status_code == 200
        assert replay.headers["Idempotency-Replayed"] == "true"
        assert replay.json() == first.json()
        assert get_state(patient_id)["state_version"] == version_after_first
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_idempotency_does_not_reserve_key_for_validation_error(monkeypatch):
    from zhenhu.inpatient import main

    with TemporaryDirectory() as directory:
        engine = create_async_engine(f"sqlite+aiosqlite:///{Path(directory) / 'http-idempotency-error.db'}")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        monkeypatch.setattr(main, "async_session_factory", session_factory)
        headers = {"x-role": "doctor", "Idempotency-Key": "invalid-command-key"}
        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.post("/inpatient/example/command", json={}, headers=headers)

        assert response.status_code == 422
        async with session_factory() as session:
            record = await session.scalar(select(IdempotencyRecord).where(
                IdempotencyRecord.idempotency_key == "invalid-command-key"
            ))
        assert record is None
        await engine.dispose()


@pytest.mark.asyncio
async def test_idempotency_does_not_buffer_or_reserve_sse_responses(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.middleware.idempotency import IdempotencyMiddleware

    with TemporaryDirectory() as directory:
        engine = create_async_engine(f"sqlite+aiosqlite:///{Path(directory) / 'idempotency-sse.db'}")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(main, "async_session_factory", session_factory)

        body_sent = False

        async def stream():
            nonlocal body_sent
            body_sent = True
            yield b"data: first\n\n"

        streaming_response = StreamingResponse(stream(), media_type="text/event-stream")

        async def call_next(_):
            return streaming_response

        async def receive():
            return {"type": "http.request", "body": b'{"message":"hello"}', "more_body": False}

        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/assistant/chat/stream",
            "headers": [(b"idempotency-key", b"stream-key")],
        }, receive)

        middleware = IdempotencyMiddleware(main.app)
        result = await middleware.dispatch(request, call_next)

        assert result is streaming_response
        assert body_sent is False
        async with session_factory() as session:
            record = await session.scalar(select(IdempotencyRecord).where(
                IdempotencyRecord.idempotency_key == "stream-key"
            ))
        assert record is None
        await engine.dispose()
