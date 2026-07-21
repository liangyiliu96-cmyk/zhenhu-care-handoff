"""Patient round generation, review, and history endpoints.

The Agent creates a structured SOAP draft. A doctor must explicitly review it
before it is treated as a clinician-checked summary.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse
from .route_schemas import RoundEditRequest, RoundGenerateRequest, RoundReviewRequest

router = APIRouter(prefix="/inpatient", tags=["rounds"])


def _as_round_number(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _round_number(record: dict, *, fallback: int | None = None) -> int | None:
    return _as_round_number(record.get("round_number")) or fallback


def _project_round(record: dict, *, latest: bool, state: dict, fallback_round_number: int | None = None) -> dict:
    """补齐旧查房记录的展示元数据，不回写历史状态。"""
    projected = dict(record)
    resolved_round_number = _round_number(projected, fallback=fallback_round_number)
    if resolved_round_number is not None:
        projected.setdefault("round_number", resolved_round_number)
    projected.setdefault("generation_source", "agent_generated_legacy")
    projected.setdefault("review_status", "requires_clinician_review")
    projected.setdefault("citations", [])
    projected.setdefault("doctor_revision", {})
    projected.setdefault(
        "source_nodes",
        ["vital_signs", "lab_results", "medication_adjustments", "daily_round_agent"],
    )
    if latest:
        projected.setdefault("ai_recommendation", state.get("ai_recommendation") or "")
    else:
        projected.setdefault("ai_recommendation", "")
    return projected


def _require_patient_read_access(request: Request, patient_id: str) -> None:
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc


def _require_doctor_write_access(request: Request, patient_id: str) -> dict:
    _require_patient_read_access(request, patient_id)
    user_info = getattr(request.state, "user_info", {}) or {}
    if user_info.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="仅医生可生成或核对查房摘要")
    return user_info


@router.get("/{patient_id}/rounds")
async def get_rounds(patient_id: str, request: Request):
    _require_patient_read_access(request, patient_id)
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(
            error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"}
        )

    round_data = state.get("latest_round") or {}
    history = [item for item in (state.get("round_history") or []) if isinstance(item, dict)]
    if not history and round_data:
        history = [round_data]
    history.sort(key=lambda item: _round_number(item, fallback=0) or 0)
    projected_history = [
        _project_round(
            item,
            latest=index == len(history) - 1,
            state=state,
            fallback_round_number=index + 1,
        )
        for index, item in enumerate(history)
    ]
    projected_latest = _project_round(
        round_data,
        latest=True,
        state=state,
        fallback_round_number=_as_round_number(state.get("round_count")) or len(history),
    ) if round_data else {}
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "state_version": int(state.get("state_version", 0)),
        "round_count": state.get("round_count", 0),
        "total": len(projected_history),
        "rounds": projected_history,
        "latest_soap": projected_latest,
        "phase": state.get("phase"),
    })


@router.post("/{patient_id}/rounds/generate")
async def generate_round(patient_id: str, body: RoundGenerateRequest, request: Request):
    """Generate and persist a fresh SOAP draft through the existing Agent node."""
    _require_doctor_write_access(request, patient_id)
    from ..agent.nodes_monitoring import node_daily_round
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    def prepare(state: dict) -> None:
        # A doctor-initiated new round is time-based and may use unchanged inputs.
        state.pop("last_round_input_counts", None)
        # Older states kept only latest_round. Preserve that clinical note before
        # node_daily_round appends the newly generated record to history.
        history = [dict(item) for item in (state.get("round_history") or []) if isinstance(item, dict)]
        latest = state.get("latest_round")
        if isinstance(latest, dict) and latest:
            latest_record = dict(latest)
            latest_round_number = _round_number(
                latest_record,
                fallback=_as_round_number(state.get("round_count")) or len(history) + 1,
            )
            if latest_round_number is not None:
                latest_record.setdefault("round_number", latest_round_number)
            known_rounds = {_round_number(item, fallback=index + 1) for index, item in enumerate(history)}
            if latest_round_number not in known_rounds:
                history.append(latest_record)
        state["round_history"] = history

    async def generate(state: dict, _loop) -> dict:
        updates = await node_daily_round(state)
        return {**state, **updates}

    try:
        await patient_state_service.plan_clinical(
            request,
            patient_id,
            prepare,
            action_type="round_summary_generated",
            detail={"source": "doctor_rounds_workspace"},
            idempotency_scope="round_summary_generated",
            planner=generate,
            expected_version=body.expected_version,
        )
        state = await patient_state_service.read(patient_id)
    except PatientNotFoundError:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"})

    latest = _project_round(state.get("latest_round") or {}, latest=True, state=state)
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "state_version": int(state.get("state_version", 0)),
        "round": latest,
    })


@router.post("/{patient_id}/rounds/{round_number}/review")
async def review_round(patient_id: str, round_number: int, body: RoundReviewRequest, request: Request):
    """Mark one generated SOAP summary as checked by the current doctor."""
    user_info = _require_doctor_write_access(request, patient_id)
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    reviewed_at = datetime.now(timezone.utc).isoformat()
    reviewed_by = str(user_info.get("actor_id") or user_info.get("user_id") or user_info.get("sub") or "doctor")

    def apply(state: dict) -> dict:
        history = [dict(item) for item in (state.get("round_history") or []) if isinstance(item, dict)]
        target_index = next(
            (index for index, item in enumerate(history) if _round_number(item, fallback=index + 1) == round_number),
            None,
        )
        latest = dict(state.get("latest_round") or {})
        latest_round_number = _round_number(
            latest,
            fallback=_as_round_number(state.get("round_count")) or len(history),
        )
        if target_index is None and latest_round_number != round_number:
            raise _RoundNotFoundError(round_number)

        current = history[target_index] if target_index is not None else latest
        idempotent = current.get("review_status") == "reviewed"
        reviewed = {
            **current,
            "review_status": "reviewed",
            "reviewed_at": current.get("reviewed_at") or reviewed_at,
            "reviewed_by": current.get("reviewed_by") or reviewed_by,
            "review_comment": body.comment.strip() or current.get("review_comment") or "",
        }
        reviewed["round_number"] = _round_number(
            reviewed,
            fallback=(target_index + 1 if target_index is not None else latest_round_number),
        )
        if target_index is not None:
            history[target_index] = reviewed
            state["round_history"] = history
        if latest_round_number == round_number:
            state["latest_round"] = reviewed
        return {"round": reviewed, "idempotent": idempotent}

    try:
        result = await patient_state_service.mutate_clinical(
            request,
            patient_id,
            apply,
            action_type="round_summary_reviewed",
            detail=lambda item: {"round_number": round_number, "reviewed_by": reviewed_by, "idempotent": item["idempotent"]},
            idempotency_scope="round_summary_reviewed",
            should_commit=lambda item: not item["idempotent"],
            expected_version=body.expected_version,
        )
        state = await patient_state_service.read(patient_id)
    except PatientNotFoundError:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"})
    except _RoundNotFoundError:
        return UnifiedResponse(error={"code": "ROUND_NOT_FOUND", "message": f"未找到第 {round_number} 次查房记录"})

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "state_version": int(state.get("state_version", 0)),
        "round": _project_round(result["round"], latest=True, state=state),
        "idempotent": result["idempotent"],
    })


class _RoundNotFoundError(Exception):
    pass


@router.post("/{patient_id}/rounds/{round_number}/edit")
async def edit_round(patient_id: str, round_number: int, body: RoundEditRequest, request: Request):
    """Store a doctor-authored revision without losing the Agent draft."""
    user_info = _require_doctor_write_access(request, patient_id)
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    edited_at = datetime.now(timezone.utc).isoformat()
    edited_by = str(user_info.get("actor_id") or user_info.get("user_id") or user_info.get("sub") or "doctor")
    revision = {
        "subjective": body.subjective,
        "objective": body.objective,
        "assessment": body.assessment,
        "plan": body.plan,
        "attention": body.attention,
    }

    def apply(state: dict) -> dict:
        history = [dict(item) for item in (state.get("round_history") or []) if isinstance(item, dict)]
        target_index = next(
            (index for index, item in enumerate(history) if _round_number(item, fallback=index + 1) == round_number),
            None,
        )
        latest = dict(state.get("latest_round") or {})
        latest_round_number = _round_number(
            latest,
            fallback=_as_round_number(state.get("round_count")) or len(history),
        )
        if target_index is None and latest_round_number != round_number:
            raise _RoundNotFoundError(round_number)

        current = history[target_index] if target_index is not None else latest
        agent_draft = current.get("agent_draft")
        if not isinstance(agent_draft, dict):
            agent_draft = {
                "subjective": current.get("subjective"),
                "objective": current.get("objective"),
                "assessment": current.get("assessment"),
                "plan": current.get("plan"),
                "ai_recommendation": current.get("ai_recommendation"),
            }
        edited = {
            **current,
            "round_number": _round_number(current, fallback=(target_index + 1 if target_index is not None else latest_round_number)),
            "agent_draft": agent_draft,
            "doctor_revision": revision,
            "edited_at": edited_at,
            "edited_by": edited_by,
        }
        if target_index is not None:
            history[target_index] = edited
            state["round_history"] = history
        if latest_round_number == round_number:
            state["latest_round"] = edited
        return {"round": edited}

    try:
        result = await patient_state_service.mutate_clinical(
            request,
            patient_id,
            apply,
            action_type="round_summary_edited",
            detail=lambda item: {"round_number": round_number, "edited_by": edited_by, "fields": [key for key, value in revision.items() if value]},
            idempotency_scope="round_summary_edited",
            expected_version=body.expected_version,
        )
        state = await patient_state_service.read(patient_id)
    except PatientNotFoundError:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"})
    except _RoundNotFoundError:
        return UnifiedResponse(error={"code": "ROUND_NOT_FOUND", "message": f"未找到第 {round_number} 次查房记录"})

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "state_version": int(state.get("state_version", 0)),
        "round": _project_round(result["round"], latest=True, state=state),
    })
