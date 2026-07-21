"""Small versioned schema runner for application-owned clinical tables."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from ..models import AuditLog, Base, ClinicalWorkflowState, FollowUpContact, IdempotencyRecord, OutboxEvent

_metadata = MetaData()
_schema_migrations = Table(
    "schema_migrations",
    _metadata,
    Column("version", String(64), primary_key=True),
    Column("applied_at", DateTime, nullable=False),
)

_BASELINE_VERSION = "0001_legacy_baseline"
_TRANSACTIONAL_STATE_VERSION = "0002_transactional_clinical_state"
_AUDIT_NURSE_ROLE_VERSION = "0003_audit_nurse_role"
_FOLLOW_UP_CONTACT_VERSION = "0004_follow_up_contacts"


async def run_schema_migrations(engine: AsyncEngine) -> None:
    """Apply known schema revisions once and persist their version markers."""
    async with engine.begin() as connection:
        await connection.run_sync(_schema_migrations.create, checkfirst=True)
        applied = set((await connection.scalars(select(_schema_migrations.c.version))).all())

        if _BASELINE_VERSION not in applied:
            # Existing deployments predate version tracking. create_all is
            # check-first, so it establishes a durable baseline without data loss.
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(_schema_migrations.insert().values(
                version=_BASELINE_VERSION,
                applied_at=_utc_now(),
            ))

        if _TRANSACTIONAL_STATE_VERSION not in applied:
            for table in (
                ClinicalWorkflowState.__table__,
                OutboxEvent.__table__,
                IdempotencyRecord.__table__,
            ):
                await connection.run_sync(table.create, checkfirst=True)
            await connection.execute(_schema_migrations.insert().values(
                version=_TRANSACTIONAL_STATE_VERSION,
                applied_at=_utc_now(),
            ))

        if _AUDIT_NURSE_ROLE_VERSION not in applied:
            await _upgrade_audit_actor_role_constraint(connection)
            await connection.execute(_schema_migrations.insert().values(
                version=_AUDIT_NURSE_ROLE_VERSION,
                applied_at=_utc_now(),
            ))

        if _FOLLOW_UP_CONTACT_VERSION not in applied:
            await connection.run_sync(FollowUpContact.__table__.create, checkfirst=True)
            await connection.execute(_schema_migrations.insert().values(
                version=_FOLLOW_UP_CONTACT_VERSION,
                applied_at=_utc_now(),
            ))


async def _upgrade_audit_actor_role_constraint(connection) -> None:
    """Allow the authenticated nurse role without losing existing audit facts."""
    dialect = connection.dialect.name
    if dialect == "sqlite":
        columns = "id, actor_id, actor_role, action_type, target_table, target_record_id, action_detail, session_id, created_at, updated_at"
        await connection.execute(text(
            f"CREATE TEMP TABLE audit_logs_nurse_upgrade AS SELECT {columns} FROM audit_logs"
        ))
        await connection.execute(text("DROP TABLE audit_logs"))
        await connection.run_sync(lambda sync_connection: AuditLog.__table__.create(sync_connection))
        await connection.execute(text(
            f"INSERT INTO audit_logs ({columns}) SELECT {columns} FROM audit_logs_nurse_upgrade"
        ))
        await connection.execute(text("DROP TABLE audit_logs_nurse_upgrade"))
    elif dialect == "mysql":
        await connection.execute(text("ALTER TABLE audit_logs DROP CHECK ck_audit_log_actor_role"))
        await connection.execute(text(
            "ALTER TABLE audit_logs ADD CONSTRAINT ck_audit_log_actor_role "
            "CHECK (actor_role IN ('patient', 'family', 'caregiver', 'doctor', 'nurse', "
            "'coordinator', 'supervisor', 'system'))"
        ))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
