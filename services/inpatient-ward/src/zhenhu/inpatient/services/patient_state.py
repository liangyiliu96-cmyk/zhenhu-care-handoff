"""Shared mutation boundary for patient workflow state."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import Request

from ..routes.state_store import StateVersionConflictError

T = TypeVar("T")


class PatientNotFoundError(Exception):
    """Raised when a workflow operation targets an unknown patient."""


class PatientStateService:
    """Serializes state mutations without coupling routes to storage details."""

    async def read(self, patient_id: str) -> dict[str, Any]:
        """Load a patient state without advancing its optimistic-lock version."""
        from ..routes.state_store import get_state

        state = get_state(patient_id)
        if state is None:
            raise PatientNotFoundError(patient_id)
        return state

    async def mutate(
        self,
        patient_id: str,
        operation: Callable[[dict[str, Any]], T],
        *,
        expected_version: int | None = None,
    ) -> T:
        from ..agent.loop import get_patient_lock
        from ..routes.state_store import get_state, set_state

        lock = get_patient_lock(patient_id)
        async with lock:
            state = get_state(patient_id)
            if state is None:
                raise PatientNotFoundError(patient_id)
            _assert_expected_version(state, expected_version)
            result = operation(state)
            set_state(patient_id, state)
            return result

    async def mutate_clinical(
        self,
        request: Request,
        patient_id: str,
        operation: Callable[[dict[str, Any]], T],
        *,
        action_type: str,
        detail: Callable[[T], dict[str, Any]],
        idempotency_scope: str,
        should_commit: Callable[[T], bool] | None = None,
        expected_version: int | None = None,
    ) -> T:
        """Commit a non-LLM mutation with state, audit, and outbox together."""
        from ..agent.loop import get_patient_lock
        from ..routes.state_store import get_state, set_state
        from .clinical_facade import clinical_workflow_facade

        lock = get_patient_lock(patient_id)
        async with lock:
            state = get_state(patient_id)
            if state is None:
                raise PatientNotFoundError(patient_id)
            _assert_expected_version(state, expected_version)
            result = operation(state)
            if should_commit is not None and not should_commit(result):
                return result
            state["state_version"] = await clinical_workflow_facade.commit(
                request,
                patient_id,
                state,
                action_type=action_type,
                detail=detail(result),
                idempotency_scope=idempotency_scope,
            )
            set_state(patient_id, state)
            return result

    async def plan(
        self,
        patient_id: str,
        operation: Callable[[dict[str, Any]], None],
        *,
        finalize: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        expected_version: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Apply a mutation and resume the graph under the same patient lock."""
        from ..agent.loop import get_patient_lock, get_patient_loop, resolve_pending_state
        from ..routes.state_store import get_state, set_state

        lock = get_patient_lock(patient_id)
        async with lock:
            state = get_state(patient_id)
            if state is None:
                raise PatientNotFoundError(patient_id)
            _assert_expected_version(state, expected_version)
            operation(state)
            loop = get_patient_loop(patient_id)
            result = await loop.plan_turn(state)
            persisted_state = (
                resolve_pending_state(loop, state, result)
                if result.get("status") == "pending_review"
                else result
            )
            if finalize is not None:
                finalize(persisted_state, result)
            set_state(patient_id, persisted_state)
            return result, len(loop.traces)

    async def plan_clinical(
        self,
        request: Request,
        patient_id: str,
        operation: Callable[[dict[str, Any]], None],
        *,
        action_type: str,
        detail: dict[str, Any],
        idempotency_scope: str,
        finalize: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        planner: Callable[[dict[str, Any], Any], Awaitable[dict[str, Any]]] | None = None,
        expected_version: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Run workflow derivation, then atomically persist its selected state."""
        from ..agent.loop import get_patient_lock, get_patient_loop, resolve_pending_state
        from ..routes.state_store import get_state, set_state
        from .clinical_facade import clinical_workflow_facade

        lock = get_patient_lock(patient_id)
        async with lock:
            state = get_state(patient_id)
            if state is None:
                raise PatientNotFoundError(patient_id)
            _assert_expected_version(state, expected_version)
            operation(state)
            loop = get_patient_loop(patient_id)
            result = await planner(state, loop) if planner is not None else await loop.plan_turn(state)
            persisted_state = (
                resolve_pending_state(loop, state, result)
                if result.get("status") == "pending_review"
                else result
            )
            if finalize is not None:
                finalize(persisted_state, result)
            persisted_state["state_version"] = await clinical_workflow_facade.commit(
                request,
                patient_id,
                persisted_state,
                action_type=action_type,
                detail=detail,
                idempotency_scope=idempotency_scope,
            )
            set_state(patient_id, persisted_state)
            return result, len(getattr(loop, "traces", []))


def _assert_expected_version(state: dict[str, Any], expected_version: int | None) -> None:
    if expected_version is None:
        return
    try:
        current_version = int(state.get("state_version", 0))
    except (TypeError, ValueError):
        current_version = 0
    if expected_version != current_version:
        raise StateVersionConflictError(
            f"expected state_version={expected_version}, current state_version={current_version}"
        )


patient_state_service = PatientStateService()
