"""Opt-in MySQL integration coverage for the transactional clinical tables.

Set ZHENHU_MYSQL_TEST_DATABASE_URL to an isolated disposable MySQL schema,
for example mysql+asyncmy://zhenhu:test@localhost:3307/zhenhu_integration.
The test intentionally does not use the production DATABASE_URL.
"""

from __future__ import annotations

import os
from time import time
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url


MYSQL_TEST_URL = os.environ.get("ZHENHU_MYSQL_TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.mysql_integration


@pytest.mark.asyncio
async def test_mysql_migrations_and_transactional_clinical_commit():
    if not MYSQL_TEST_URL:
        pytest.skip("ZHENHU_MYSQL_TEST_DATABASE_URL is not configured")

    from zhenhu.inpatient.models import AuditLog, ClinicalWorkflowState, OutboxEvent
    from zhenhu.inpatient.services.schema_migrations import run_schema_migrations
    from zhenhu.inpatient.services.transactional_state import commit_clinical_mutation

    engine = create_async_engine(MYSQL_TEST_URL, pool_pre_ping=True)
    patient_id = f"mysql-integration-{uuid4()}"
    action_type = f"mysql_integration_{uuid4().hex}"
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    committed = False
    try:
        await run_schema_migrations(engine)
        async with session_factory() as session:
            version = await commit_clinical_mutation(
                session,
                patient_id=patient_id,
                state={"patient_id": patient_id, "phase": "monitoring"},
                expected_version=0,
                actor_id="mysql-integration",
                actor_role="system",
                action_type=action_type,
                detail={"source": "pytest"},
                idempotency_key=f"mysql-integration:{patient_id}",
            )
        committed = True

        async with session_factory() as session:
            state = await session.get(ClinicalWorkflowState, patient_id)
            audit_count = await session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action_type == action_type
            ))
            outbox_count = await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.idempotency_key == f"mysql-integration:{patient_id}"
            ))

        assert version == 1
        assert state is not None
        assert state.state_json["state_version"] == 1
        assert audit_count == 1
        assert outbox_count == 1
    finally:
        if committed:
            async with session_factory() as session:
                async with session.begin():
                    state = await session.get(ClinicalWorkflowState, patient_id)
                    if state is not None:
                        await session.delete(state)
                    await session.execute(OutboxEvent.__table__.delete().where(
                        OutboxEvent.idempotency_key == f"mysql-integration:{patient_id}"
                    ))
                    await session.execute(AuditLog.__table__.delete().where(
                        AuditLog.action_type == action_type
                    ))
        await engine.dispose()


def test_mysql_state_backend_recovers_expired_pending_review(monkeypatch):
    if not MYSQL_TEST_URL:
        pytest.skip("ZHENHU_MYSQL_TEST_DATABASE_URL is not configured")

    from zhenhu.inpatient.routes.state_store import MySQLBackend

    url = make_url(MYSQL_TEST_URL)
    monkeypatch.setenv("MYSQL_HOST", url.host or "127.0.0.1")
    monkeypatch.setenv("MYSQL_PORT", str(url.port or 3306))
    monkeypatch.setenv("MYSQL_USER", url.username or "")
    monkeypatch.setenv("MYSQL_PASSWORD", url.password or "")
    monkeypatch.setenv("MYSQL_DATABASE", url.database or "")

    backend = MySQLBackend()
    pending_id = f"mysql-pending-{uuid4()}"
    ordinary_id = f"mysql-ordinary-{uuid4()}"
    try:
        expired = time() - 7200
        backend.save(pending_id, {
            "patient_id": pending_id,
            "state_version": 1,
            "interrupt_pending": True,
            "pending_review": {"review_id": "review-mysql", "type": "doctor_confirm"},
        }, expired)
        backend.save(ordinary_id, {
            "patient_id": ordinary_id,
            "state_version": 1,
        }, expired)

        restored = backend.load_all(ttl=60)

        assert restored[pending_id][1]["pending_review"]["review_id"] == "review-mysql"
        assert ordinary_id not in restored
    finally:
        backend.delete([pending_id, ordinary_id])
        backend._engine.dispose()
