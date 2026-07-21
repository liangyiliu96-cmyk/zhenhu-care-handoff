"""Application facade for durable clinical workflow mutations."""

from __future__ import annotations

from typing import Any

from fastapi import Request


class ClinicalWorkflowFacade:
    """Own the common transaction boundary used by clinical write routes."""

    async def commit(
        self,
        request: Request,
        patient_id: str,
        state: dict[str, Any],
        *,
        action_type: str,
        detail: dict[str, Any],
        idempotency_scope: str,
    ) -> int:
        from ..agent.audit import audit_context_from_request
        from ..main import async_session_factory
        from .transactional_state import commit_clinical_mutation

        context = audit_context_from_request(request)
        idempotency_source = request.headers.get("Idempotency-Key") or context["request_id"] or patient_id
        async with async_session_factory() as session:
            return await commit_clinical_mutation(
                session,
                patient_id=patient_id,
                state=state,
                expected_version=state.get("state_version"),
                actor_id=context["actor_id"],
                actor_role=context["actor_role"],
                action_type=action_type,
                detail=detail,
                idempotency_key=f"clinical-state:{patient_id}:{idempotency_scope}:{idempotency_source}",
                request_id=context["request_id"],
            )


clinical_workflow_facade = ClinicalWorkflowFacade()
