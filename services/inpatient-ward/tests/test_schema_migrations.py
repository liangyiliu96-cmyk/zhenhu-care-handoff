"""Schema migration baseline regression tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_schema_migrations_record_versions_and_create_transactional_tables():
    from zhenhu.inpatient.services.schema_migrations import run_schema_migrations

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await run_schema_migrations(engine)
    await run_schema_migrations(engine)

    async with engine.connect() as connection:
        versions = list((await connection.scalars(
            text("SELECT version FROM schema_migrations ORDER BY version")
        )).all())
        state_table = await connection.scalar(text(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'clinical_workflow_states'"
        ))
        outbox_table = await connection.scalar(text(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'outbox_events'"
        ))
        contact_table = await connection.scalar(text(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'follow_up_contacts'"
        ))

    assert versions == [
        "0001_legacy_baseline",
        "0002_transactional_clinical_state",
        "0003_audit_nurse_role",
        "0004_follow_up_contacts",
    ]
    assert state_table == "clinical_workflow_states"
    assert outbox_table == "outbox_events"
    assert contact_table == "follow_up_contacts"
    await engine.dispose()


@pytest.mark.asyncio
async def test_audit_role_migration_preserves_existing_audits_and_allows_nurse():
    from zhenhu.inpatient.services.schema_migrations import run_schema_migrations

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.execute(text("""
            CREATE TABLE audit_logs (
                id VARCHAR(36) PRIMARY KEY,
                actor_id VARCHAR(36),
                actor_role VARCHAR(16) NOT NULL,
                action_type VARCHAR(100) NOT NULL,
                target_table VARCHAR(100),
                target_record_id VARCHAR(36),
                action_detail JSON,
                session_id VARCHAR(100),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT ck_audit_log_actor_role CHECK (
                    actor_role IN ('patient', 'family', 'caregiver', 'doctor', 'coordinator', 'supervisor', 'system')
                )
            )
        """))
        await connection.execute(text("""
            INSERT INTO audit_logs (
                id, actor_role, action_type, created_at, updated_at
            ) VALUES ('legacy-audit', 'doctor', 'legacy_action', '2026-07-18 00:00:00', '2026-07-18 00:00:00')
        """))

    await run_schema_migrations(engine)

    async with engine.begin() as connection:
        preserved = await connection.scalar(text(
            "SELECT action_type FROM audit_logs WHERE id = 'legacy-audit'"
        ))
        await connection.execute(text("""
            INSERT INTO audit_logs (
                id, actor_role, action_type, created_at, updated_at
            ) VALUES ('nurse-audit', 'nurse', 'vital_signs_reported', '2026-07-18 00:00:00', '2026-07-18 00:00:00')
        """))

    assert preserved == "legacy_action"
    await engine.dispose()


@pytest.mark.asyncio
async def test_audit_role_migration_uses_mysql_constraint_ddl():
    from zhenhu.inpatient.services.schema_migrations import _upgrade_audit_actor_role_constraint

    class MysqlConnection:
        dialect = SimpleNamespace(name="mysql")

        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(str(statement))

    connection = MysqlConnection()
    await _upgrade_audit_actor_role_constraint(connection)

    assert connection.statements == [
        "ALTER TABLE audit_logs DROP CHECK ck_audit_log_actor_role",
        "ALTER TABLE audit_logs ADD CONSTRAINT ck_audit_log_actor_role "
        "CHECK (actor_role IN ('patient', 'family', 'caregiver', 'doctor', 'nurse', "
        "'coordinator', 'supervisor', 'system'))",
    ]
