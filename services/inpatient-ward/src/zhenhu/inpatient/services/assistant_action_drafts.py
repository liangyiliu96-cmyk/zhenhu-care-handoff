"""Human-reviewed clinical action drafts created from assistant suggestions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import Request
from pydantic import ValidationError

from ..routes.route_schemas import (
    FollowUpActionDraftPayload,
    InvestigationActionDraftPayload,
    MedicationActionDraftPayload,
    MdtActionDraftPayload,
    EducationPlanActionDraftPayload,
)
from .care_management import build_education_plan, build_follow_up_task, build_investigation_order, build_medication_order, build_mdt_request
from .patient_state import PatientStateService

_PAYLOAD_MODELS = {
    "medication_order": MedicationActionDraftPayload,
    "investigation_order": InvestigationActionDraftPayload,
    "follow_up_task": FollowUpActionDraftPayload,
    "mdt_request": MdtActionDraftPayload,
    "education_plan": EducationPlanActionDraftPayload,
}


class AssistantActionDraftNotFoundError(Exception):
    """Raised when a draft does not belong to the requested patient."""


class AssistantActionDraftTransitionError(Exception):
    """Raised when an immutable or terminal draft is changed."""


class AssistantActionDraftPayloadError(Exception):
    """Raised when an extracted or edited payload is not executable."""


class AssistantActionDraftService:
    """Persist suggestions and execute them only after explicit doctor approval."""

    def __init__(self, patient_state: PatientStateService | None = None):
        self._patient_state = patient_state or PatientStateService()

    async def list(self, patient_id: str) -> dict[str, Any]:
        state = await self._patient_state.read(patient_id)
        return {
            "patient_id": patient_id,
            "state_version": int(state.get("state_version", 0)),
            "drafts": list(state.get("assistant_action_drafts", [])),
        }

    async def create_many(
        self,
        patient_id: str,
        suggestions: list[dict[str, Any]],
        *,
        request: Request,
        session_id: str,
        source_message_id: str,
        citations: list[dict[str, Any]],
        expected_version: int,
    ) -> dict[str, Any]:
        actor_id = _actor_id(request)
        normalized: list[dict[str, Any]] = []
        for suggestion in suggestions:
            try:
                item = _normalize_suggestion(suggestion)
            except AssistantActionDraftPayloadError:
                continue
            if item is not None:
                normalized.append(item)
        if not normalized:
            raise AssistantActionDraftPayloadError("助手建议中没有可转换的临床操作草稿")

        def operation(state: dict[str, Any]) -> dict[str, Any]:
            records = state.setdefault("assistant_action_drafts", [])
            existing = {record.get("draft_key"): record for record in records}
            created: list[dict[str, Any]] = []
            for item in normalized:
                draft_key = _draft_key(session_id, source_message_id, item)
                if draft_key in existing:
                    created.append(existing[draft_key])
                    continue
                now = _now()
                draft = {
                    "id": str(uuid4()),
                    "draft_key": draft_key,
                    "draft_type": item["draft_type"],
                    "status": "pending",
                    "payload": item["payload"],
                    "rationale": item["rationale"],
                    "citations": _sanitize_citations(citations),
                    "session_id": session_id,
                    "source_message_id": source_message_id,
                    "created_by": actor_id,
                    "updated_by": actor_id,
                    "created_at": now,
                    "updated_at": now,
                    "base_state_version": int(state.get("state_version", 0)),
                    "decision_comment": "",
                    "decided_at": None,
                    "decided_by": None,
                    "execution": None,
                }
                records.append(draft)
                existing[draft_key] = draft
                created.append(draft)
            return {"drafts": created, "changed": False}

        # The operation's changed flag is corrected by comparing list lengths to avoid
        # turning a repeated generation request into a second clinical commit.
        def operation_with_change(state: dict[str, Any]) -> dict[str, Any]:
            before = len(state.get("assistant_action_drafts", []))
            result = operation(state)
            result["changed"] = len(state.get("assistant_action_drafts", [])) > before
            return result

        result = await self._patient_state.mutate_clinical(
            request,
            patient_id,
            operation_with_change,
            action_type="assistant_action_drafts_created",
            detail=lambda value: {
                "draft_ids": [draft["id"] for draft in value["drafts"]],
                "draft_types": [draft["draft_type"] for draft in value["drafts"]],
                "session_id": session_id,
                "source_message_id": source_message_id,
            },
            idempotency_scope=f"assistant-action-drafts:{source_message_id}",
            should_commit=lambda value: value["changed"],
            expected_version=expected_version,
        )
        return await self._with_state_version(patient_id, {"drafts": result["drafts"], "idempotent": not result["changed"]})

    async def update(
        self,
        patient_id: str,
        draft_id: str,
        payload: dict[str, Any],
        rationale: str,
        *,
        request: Request,
        expected_version: int,
    ) -> dict[str, Any]:
        actor_id = _actor_id(request)

        def operation(state: dict[str, Any]) -> dict[str, Any]:
            draft = _find_draft(state, draft_id)
            if draft.get("status") != "pending":
                raise AssistantActionDraftTransitionError("已批准或已驳回的操作草稿不可编辑")
            draft["payload"] = validate_action_payload(str(draft.get("draft_type")), payload)
            draft["rationale"] = rationale.strip()
            draft["updated_by"] = actor_id
            draft["updated_at"] = _now()
            return draft

        draft = await self._patient_state.mutate_clinical(
            request,
            patient_id,
            operation,
            action_type="assistant_action_draft_updated",
            detail=lambda value: {"draft_id": value["id"], "draft_type": value["draft_type"]},
            idempotency_scope=f"assistant-action-draft:{draft_id}:update",
            expected_version=expected_version,
        )
        return await self._with_state_version(patient_id, {"draft": draft})

    async def approve(
        self,
        patient_id: str,
        draft_id: str,
        comment: str,
        *,
        request: Request,
        expected_version: int,
    ) -> dict[str, Any]:
        current = await self._patient_state.read(patient_id)
        current_draft = _find_draft(current, draft_id)
        if current_draft.get("status") == "approved":
            return {
                "patient_id": patient_id,
                "state_version": int(current.get("state_version", 0)),
                "draft": current_draft,
                "execution": current_draft.get("execution"),
                "idempotent": True,
            }
        actor_id = _actor_id(request)

        def operation(state: dict[str, Any]) -> dict[str, Any]:
            draft = _find_draft(state, draft_id)
            if draft.get("status") != "pending":
                raise AssistantActionDraftTransitionError("仅待审核草稿可以批准")
            payload = validate_action_payload(str(draft.get("draft_type")), draft.get("payload") or {})
            if draft["draft_type"] == "medication_order":
                record = build_medication_order(payload, status="active", source_draft_id=draft_id)
                state.setdefault("medication_orders", []).append(record)
                record_type = "medication_order"
            elif draft["draft_type"] == "investigation_order":
                record = build_investigation_order(payload, source_draft_id=draft_id)
                state.setdefault("investigation_orders", []).append(record)
                record_type = "investigation_order"
            elif draft["draft_type"] == "follow_up_task":
                record = build_follow_up_task(payload, source_draft_id=draft_id)
                state.setdefault("follow_up_tasks", []).append(record)
                record_type = "follow_up_task"
            elif draft["draft_type"] == "mdt_request":
                record = build_mdt_request(payload, source_draft_id=draft_id)
                state.setdefault("mdt_requests", []).append(record)
                record_type = "mdt_request"
            else:
                record = build_education_plan(payload, source_draft_id=draft_id)
                state.setdefault("education_plans", []).append(record)
                record_type = "education_plan"
            execution = {"record_type": record_type, "record_id": record["id"], "status": record["status"]}
            now = _now()
            draft.update(
                status="approved",
                payload=payload,
                decision_comment=comment.strip(),
                decided_at=now,
                decided_by=actor_id,
                updated_at=now,
                updated_by=actor_id,
                execution=execution,
            )
            return {"draft": draft, "execution": execution}

        result = await self._patient_state.mutate_clinical(
            request,
            patient_id,
            operation,
            action_type="assistant_action_draft_approved",
            detail=lambda value: {
                "draft_id": value["draft"]["id"],
                "draft_type": value["draft"]["draft_type"],
                **value["execution"],
            },
            idempotency_scope=f"assistant-action-draft:{draft_id}:approve",
            expected_version=expected_version,
        )
        return await self._with_state_version(patient_id, {**result, "idempotent": False})

    async def reject(
        self,
        patient_id: str,
        draft_id: str,
        comment: str,
        *,
        request: Request,
        expected_version: int,
    ) -> dict[str, Any]:
        current = await self._patient_state.read(patient_id)
        current_draft = _find_draft(current, draft_id)
        if current_draft.get("status") == "rejected":
            return {
                "patient_id": patient_id,
                "state_version": int(current.get("state_version", 0)),
                "draft": current_draft,
                "idempotent": True,
            }
        actor_id = _actor_id(request)

        def operation(state: dict[str, Any]) -> dict[str, Any]:
            draft = _find_draft(state, draft_id)
            if draft.get("status") != "pending":
                raise AssistantActionDraftTransitionError("仅待审核草稿可以驳回")
            now = _now()
            draft.update(
                status="rejected",
                decision_comment=comment.strip(),
                decided_at=now,
                decided_by=actor_id,
                updated_at=now,
                updated_by=actor_id,
            )
            return draft

        draft = await self._patient_state.mutate_clinical(
            request,
            patient_id,
            operation,
            action_type="assistant_action_draft_rejected",
            detail=lambda value: {"draft_id": value["id"], "draft_type": value["draft_type"]},
            idempotency_scope=f"assistant-action-draft:{draft_id}:reject",
            expected_version=expected_version,
        )
        return await self._with_state_version(patient_id, {"draft": draft, "idempotent": False})

    async def _with_state_version(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        state = await self._patient_state.read(patient_id)
        return {"patient_id": patient_id, "state_version": int(state.get("state_version", 0)), **data}


def validate_action_payload(draft_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    model = _PAYLOAD_MODELS.get(draft_type)
    if model is None:
        raise AssistantActionDraftPayloadError(f"不支持的操作草稿类型: {draft_type}")
    try:
        return model.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise AssistantActionDraftPayloadError(str(exc)) from exc


def _normalize_suggestion(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    draft_type = str(item.get("draft_type") or item.get("type") or "").strip()
    if draft_type not in _PAYLOAD_MODELS:
        return None
    return {
        "draft_type": draft_type,
        "payload": validate_action_payload(draft_type, item.get("payload") or {}),
        "rationale": str(item.get("rationale") or "").strip()[:2000],
    }


def _find_draft(state: dict[str, Any], draft_id: str) -> dict[str, Any]:
    for draft in state.get("assistant_action_drafts", []):
        if draft.get("id") == draft_id:
            return draft
    raise AssistantActionDraftNotFoundError(draft_id)


def _draft_key(session_id: str, source_message_id: str, item: dict[str, Any]) -> str:
    raw = json.dumps(item, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{session_id}:{source_message_id}:{raw}".encode("utf-8")).hexdigest()


def _sanitize_citations(citations: list[dict[str, Any]]) -> list[dict[str, str]]:
    allowed = ("source", "title", "excerpt", "content", "citation", "version", "layer", "topic")
    return [
        {key: str(item[key])[:2000] for key in allowed if item.get(key) is not None}
        for item in citations[:20]
        if isinstance(item, dict)
    ]


def _actor_id(request: Request) -> str:
    actor_id = str((getattr(request.state, "user_info", {}) or {}).get("actor_id") or "").strip()
    if not actor_id:
        raise AssistantActionDraftTransitionError("操作草稿需要已认证的医生身份")
    return actor_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


assistant_action_draft_service = AssistantActionDraftService()
