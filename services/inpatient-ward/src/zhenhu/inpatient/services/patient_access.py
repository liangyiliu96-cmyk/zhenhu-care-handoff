"""Patient ownership metadata and department access policy."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from typing import Any


class PatientAccessDeniedError(Exception):
    """Raised when a clinical identity is outside the patient's department."""


def bind_patient_access(state: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
    """Attach immutable-at-creation ownership metadata to a new patient state."""
    existing = state.get("patient_access") or {}
    template = state.get("disease_template") or {}
    department = _normalize(existing.get("department") or template.get("department"))
    actor_id = (user or {}).get("actor_id")
    care_team_ids = _string_set(existing.get("care_team_ids", []))
    if actor_id:
        care_team_ids.add(str(actor_id))
    state["patient_access"] = {
        "department": department or None,
        "attending_doctor_id": existing.get("attending_doctor_id") or actor_id or None,
        "care_team_ids": sorted(care_team_ids),
    }
    return state["patient_access"]


def can_access_patient_state(state: dict[str, Any] | None, user: dict[str, Any]) -> bool:
    """Return whether the authenticated identity may access a patient state."""
    if state is None:
        return True  # Preserve route-level NOT_FOUND behavior without leaking metadata.
    roles = _string_set(user.get("roles", []))
    if not roles.intersection({"doctor", "nurse"}):
        return False
    access = state.get("patient_access") or {}
    template = state.get("disease_template") or {}
    patient_department = _normalize(access.get("department") or template.get("department"))
    user_departments = _string_set(user.get("departments", []))
    if not patient_department or not user_departments:
        return _is_legacy_dev_header_request(user)
    return patient_department in user_departments


def require_patient_access(patient_id: str, user: dict[str, Any]) -> None:
    from ..routes.state_store import get_state

    if not can_access_patient_state(get_state(patient_id), user):
        raise PatientAccessDeniedError(patient_id)


def iter_accessible_patient_states(
    entries: Iterable[tuple[str, tuple[float, dict[str, Any]]]],
    user: dict[str, Any],
    *,
    now: float,
    ttl: int,
) -> Iterator[tuple[str, float, dict[str, Any]]]:
    """Yield only non-expired states visible to the current clinical identity."""
    for patient_id, (updated_at, state) in entries:
        if now - updated_at > ttl or not isinstance(state, dict):
            continue
        if can_access_patient_state(state, user):
            yield patient_id, updated_at, state


def _is_legacy_dev_header_request(user: dict[str, Any]) -> bool:
    return user.get("auth_mode") == "header" and os.environ.get("APP_ENV", "dev").lower() == "dev"


def _normalize(value: object) -> str:
    return str(value or "").strip().lower()


def _string_set(value: object) -> set[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = []
    return {str(item).strip().lower() for item in values if str(item).strip()}
