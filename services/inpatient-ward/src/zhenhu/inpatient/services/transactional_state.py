"""Single-database transaction boundary for clinical state, audit, and outbox."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.outbox import enqueue_fhir_audit_event
from ..models import AuditActorRole, AuditLog, ClinicalWorkflowState


class TransactionalStateConflictError(Exception):
    """Raised when the authoritative state has moved past the expected version."""

    def __init__(self, patient_id: str, current_version: int):
        super().__init__(patient_id)
        self.patient_id = patient_id
        self.current_version = current_version


async def commit_clinical_mutation(
    session: AsyncSession,
    *,
    patient_id: str,
    state: dict[str, Any],
    expected_version: int | None,
    actor_id: str | None,
    actor_role: str,
    action_type: str,
    detail: dict[str, Any],
    idempotency_key: str,
    request_id: str | None = None,
) -> int:
    """Persist a state version, its audit fact, and FHIR intent atomically."""
    safe_state = deepcopy(state)
    async with session.begin():
        existing = await session.scalar(
            select(ClinicalWorkflowState)
            .where(ClinicalWorkflowState.patient_id == patient_id)
            .with_for_update()
        )
        current_version = existing.state_version if existing is not None else (expected_version or 0)
        if expected_version is not None and expected_version != current_version:
            # Legacy graph writes are still mirrored through state_store during
            # migration. A locked route has already validated that newer version,
            # so the transactional projection may safely catch up to it.
            if existing is not None and expected_version > current_version:
                current_version = expected_version
            else:
                raise TransactionalStateConflictError(patient_id, current_version)
        next_version = current_version + 1
        safe_state["state_version"] = next_version
        if existing is None:
            session.add(ClinicalWorkflowState(
                patient_id=patient_id,
                state_json=safe_state,
                state_version=next_version,
            ))
        else:
            existing.state_json = safe_state
            existing.state_version = next_version

        audit = AuditLog(
            id=str(uuid4()),
            actor_id=actor_id,
            actor_role=AuditActorRole(actor_role),
            action_type=action_type,
            target_table="clinical_workflow_states",
            target_record_id=None,
            action_detail={"patient_id": patient_id, "state_version": next_version, **detail},
            session_id=request_id,
        )
        session.add(audit)
        await enqueue_fhir_audit_event(
            session,
            action=action_type,
            actor=actor_id or "system",
            patient_id=patient_id,
            detail=detail,
            idempotency_key=idempotency_key,
        )
    return next_version
