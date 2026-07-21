"""HTTP integration for durable Idempotency-Key request replay."""

from __future__ import annotations

import hashlib
import json

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..services.idempotency import (
    IdempotencyKeyConflictError,
    abandon_request,
    complete_request,
    reserve_request,
)

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Replay completed JSON write responses when the caller supplies a key."""

    async def dispatch(self, request: Request, call_next):
        key = request.headers.get("Idempotency-Key", "").strip()
        if request.method not in _WRITE_METHODS or not key:
            return await call_next(request)
        if len(key) > 100:
            return _error(400, "IDEMPOTENCY_KEY_INVALID", "Idempotency-Key must be at most 100 characters")

        raw_body = await request.body()
        fingerprint = hashlib.sha256(raw_body).hexdigest()
        scope = _scope(request)
        from ..main import async_session_factory

        async with async_session_factory() as session:
            try:
                reservation = await reserve_request(
                    session, scope=scope, key=key, fingerprint=fingerprint
                )
            except IdempotencyKeyConflictError:
                return _error(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was already used for a different request")

            if not reservation.is_new:
                record = reservation.record
                if record.status == "completed" and record.response_body is not None:
                    response = JSONResponse(record.response_body, status_code=record.response_status or 200)
                    response.headers["Idempotency-Replayed"] = "true"
                    return response
                return _error(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS", "An identical request is already processing")

            record_id = reservation.record.id

        try:
            response = await call_next(request)
            if response.media_type == "text/event-stream":
                async with async_session_factory() as session:
                    await abandon_request(session, record_id=record_id)
                return response
            body = b"".join([chunk async for chunk in response.body_iterator])
        except BaseException:
            async with async_session_factory() as session:
                await abandon_request(session, record_id=record_id)
            raise

        content_type = response.headers.get("content-type", "")
        try:
            payload = json.loads(body) if "application/json" in content_type else None
        except (TypeError, ValueError):
            payload = None
        # Only successful business responses are safe to replay. Validation,
        # authorization, and optimistic-lock errors may be corrected before a
        # retry, so retaining their key would turn a transient failure into a
        # permanent client-side dead end.
        if isinstance(payload, dict) and 200 <= response.status_code < 300:
            async with async_session_factory() as session:
                await complete_request(
                    session,
                    record_id=record_id,
                    response_status=response.status_code,
                    response_body=payload,
                )
        else:
            async with async_session_factory() as session:
                await abandon_request(session, record_id=record_id)

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(body, status_code=response.status_code, headers=headers, media_type=response.media_type)


def _scope(request: Request) -> str:
    user = getattr(request.state, "user_info", {})
    actor_id = user.get("actor_id") or request.headers.get("x-user-id", "")
    if not actor_id:
        actor_id = hashlib.sha256(request.headers.get("authorization", "").encode()).hexdigest()
    return f"{actor_id}:{request.method}:{request.url.path}"


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": None, "error": {"code": code, "message": message}},
    )
