"""Application-level API contract checks."""

from __future__ import annotations

from collections import defaultdict

from fastapi import FastAPI
from fastapi.responses import JSONResponse


def validate_unique_routes(app: FastAPI) -> None:
    """Fail startup when two handlers claim the same HTTP method and path."""
    claimed: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set())
        if not path:
            continue
        for method in methods - {"HEAD", "OPTIONS"}:
            claimed[(method, path)].append(route.name)

    duplicates = [
        f"{method} {path} ({', '.join(names)})"
        for (method, path), names in claimed.items()
        if len(names) > 1
    ]
    if duplicates:
        raise RuntimeError("Duplicate API routes: " + "; ".join(sorted(duplicates)))


def state_version_conflict_response(current_version: int, request_id: str | None = None) -> JSONResponse:
    """Return the version-conflict representation used by both API versions."""
    return JSONResponse(
        status_code=409,
        content={
            "request_id": request_id or "unknown",
            "data": None,
            "error": {
                "code": "STATE_VERSION_CONFLICT",
                "message": "Patient state changed before this write completed; refresh and retry.",
                "current_version": current_version,
            },
        },
    )
