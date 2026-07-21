"""Small request builders for direct route-handler unit tests."""

from __future__ import annotations

from fastapi import Request


def doctor_request() -> Request:
    """Build the authenticated clinical context required by protected reads."""
    request = Request({"type": "http", "headers": []})
    request.state.user_info = {
        "roles": ["doctor"],
        "auth_mode": "header",
    }
    return request
