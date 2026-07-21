"""Authorization policy for high-impact management operations."""

from __future__ import annotations

import os
from collections.abc import Iterable

from fastapi import HTTPException, Request


def management_capabilities(request: Request) -> dict[str, object]:
    user = getattr(request.state, "user_info", {}) or {}
    is_manager = _is_manager(user)
    production = os.environ.get("APP_ENV", "dev").strip().lower() == "production"
    enabled = os.environ.get("MANAGEMENT_OPERATIONS_ENABLED", "false").strip().lower() == "true"
    permissions = _permissions(user)
    production_grant = "zhenhu:admin:write" in permissions or "zhenhu:admin:*" in permissions
    writes_allowed = is_manager and (not production or (enabled and production_grant))
    if not is_manager:
        authorization_reason = "manager_role_required"
    elif production and not enabled:
        authorization_reason = "production_switch_disabled"
    elif production and not production_grant:
        authorization_reason = "permission_claim_missing"
    else:
        authorization_reason = "authorized"
    return {
        "is_manager": is_manager,
        "environment": "production" if production else "development",
        "auth_mode": str(user.get("auth_mode") or "unknown"),
        "writes_enabled": writes_allowed,
        "production_switch_enabled": enabled if production else True,
        "authorization_reason": authorization_reason,
        "required_permission": "zhenhu:admin:write" if production else None,
        "operations": {
            "rag_reindex": writes_allowed,
            "organization_seed": writes_allowed,
            "seed_all": writes_allowed,
            "clear_expired": writes_allowed,
            "demo_patient_reset": writes_allowed and not production,
            "database_stats": is_manager,
            "evidence_graph_rebuild": writes_allowed,
        },
    }


def require_management_operation(request: Request, operation: str, *, write: bool = True) -> None:
    capabilities = management_capabilities(request)
    if not capabilities["is_manager"]:
        raise HTTPException(status_code=403, detail="该操作仅限科主任或护士长")
    if write and not capabilities["operations"].get(operation):
        raise HTTPException(status_code=403, detail="生产运维写操作未获授权")


def _is_manager(user: dict) -> bool:
    role = str(user.get("role") or "").lower()
    title = str(user.get("title") or "")
    return role in {"doctor", "nurse"} and any(value in title for value in ("科主任", "主任医师", "护士长"))


def _permissions(user: dict) -> set[str]:
    claims = user.get("claims") if isinstance(user.get("claims"), dict) else {}
    values: Iterable[object] = [claims.get("permissions"), claims.get("scope")]
    result: set[str] = set()
    for value in values:
        if isinstance(value, str):
            result.update(item.strip() for item in value.replace(",", " ").split() if item.strip())
        elif isinstance(value, (list, tuple, set)):
            result.update(str(item).strip() for item in value if str(item).strip())
    return result
