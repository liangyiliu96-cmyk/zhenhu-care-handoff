"""临床智能助手 API。"""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from ..schemas import UnifiedResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])

_PUBLIC_CLIENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_PUBLIC_RATE_WINDOW_SECONDS = 60
_PUBLIC_RATE_LIMIT = int(os.environ.get("PUBLIC_ASSISTANT_RATE_LIMIT", "8"))
_public_requests: dict[str, deque[float]] = defaultdict(deque)
_public_requests_lock = Lock()


@router.post("/chat")
async def chat(request: Request, body: dict):
    message = _require_message(body)
    session_id = body.get("session_id")
    patient_id = body.get("patient_id", "")
    actor_id = _require_session_actor(request)
    actor_role = _actor_role(request)
    session = _require_session_access(request, session_id, actor_id)
    assistant_mode = _resolve_assistant_mode(actor_role, body.get("assistant_mode"), session)
    session_patient_id = str(session.get("patient_id") or "") if session else ""
    if session_patient_id:
        if patient_id and patient_id != session_patient_id:
            raise HTTPException(status_code=409, detail="Assistant session is already bound to another patient")
        patient_id = session_patient_id
    _require_patient_access(request, patient_id)
    from ..agent.assistant import chat as do_chat
    return UnifiedResponse(data=await do_chat(
        message, role=assistant_mode, session_id=session_id, patient_id=patient_id, actor_id=actor_id
    ))


@router.post("/chat/stream")
async def chat_stream(request: Request):
    """流式输出 — SSE 格式, 逐 token 推送。"""
    body = await request.json()
    message = _require_message(body)
    session_id = body.get("session_id")
    patient_id = body.get("patient_id", "")
    actor_id = _require_session_actor(request)
    actor_role = _actor_role(request)
    session = _require_session_access(request, session_id, actor_id)
    assistant_mode = _resolve_assistant_mode(actor_role, body.get("assistant_mode"), session)
    session_patient_id = str(session.get("patient_id") or "") if session else ""
    if session_patient_id:
        if patient_id and patient_id != session_patient_id:
            raise HTTPException(status_code=409, detail="Assistant session is already bound to another patient")
        patient_id = session_patient_id
    _require_patient_access(request, patient_id)
    from ..agent.assistant import chat_stream as do_stream
    return StreamingResponse(
        do_stream(message, role=assistant_mode, session_id=session_id, patient_id=patient_id, actor_id=actor_id),
        media_type="text/event-stream",
    )


@router.get("/quick-questions")
async def get_quick_questions(
    request: Request,
    assistant_mode: str | None = None,
    role: str | None = None,
    context: str = "patient",
):
    """获取角色的预设快捷问题。"""
    from ..agent.assistant import quick_questions_for

    mode = _resolve_assistant_mode(_actor_role(request), assistant_mode or role, None)
    normalized_context = "general" if context == "general" else "patient"
    return UnifiedResponse(data={
        "role": mode,
        "assistant_mode": mode,
        "context": normalized_context,
        "questions": quick_questions_for(mode, normalized_context),
    })


@router.get("/public/quick-questions")
async def get_public_quick_questions():
    from ..agent.assistant import quick_questions_for

    return UnifiedResponse(data={
        "role": "patient",
        "assistant_mode": "patient",
        "context": "general",
        "questions": quick_questions_for("patient", "general"),
    })


@router.post("/public/chat/stream")
async def public_chat_stream(request: Request):
    body = await request.json()
    message = _require_message(body, max_chars=1000)
    client_id = request.headers.get("x-assistant-client", "").strip()
    if not _PUBLIC_CLIENT_PATTERN.fullmatch(client_id):
        raise HTTPException(status_code=400, detail="Public assistant client id is invalid")
    _enforce_public_rate_limit(request, client_id)

    actor_id = f"public:{client_id}"
    session_id = body.get("session_id")
    session = _require_session_access(request, session_id, actor_id)
    if session and (session.get("assistant_mode") or session.get("role")) != "patient":
        raise HTTPException(status_code=409, detail="Assistant session is bound to another mode")

    from ..agent.assistant import chat_stream as do_stream

    return StreamingResponse(
        do_stream(message, role="patient", session_id=session_id, patient_id="", actor_id=actor_id),
        media_type="text/event-stream",
    )


@router.get("/session/{session_id}")
async def get_session(session_id: str, request: Request):
    actor_id = _require_session_actor(request)
    _require_session_access(request, session_id, actor_id)
    from ..agent.assistant import get_session as gs
    sess = gs(session_id)
    if not sess: return UnifiedResponse(data={"error": "会话不存在或已过期"})
    return UnifiedResponse(data=sess)


@router.post("/session/{session_id}/reset")
async def reset_session(session_id: str, request: Request):
    actor_id = _require_session_actor(request)
    _require_session_access(request, session_id, actor_id)
    from ..agent.assistant import reset_session as rs; rs(session_id)
    return UnifiedResponse(data={"status": "reset"})


@router.get("/sessions")
async def list_sessions(request: Request):
    """List only the current clinical actor's resumable sessions."""
    actor_id = _require_session_actor(request)
    _actor_role(request)
    from ..agent.assistant import sessions_for_owner
    return UnifiedResponse(data={"sessions": sessions_for_owner(actor_id)})


def _require_patient_access(request: Request, patient_id: str) -> None:
    if not patient_id:
        return
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc


def _require_session_actor(request: Request) -> str:
    actor_id = str((getattr(request.state, "user_info", {}) or {}).get("actor_id") or "").strip()
    if not actor_id:
        raise HTTPException(status_code=401, detail="Assistant session endpoints require an authenticated user")
    return actor_id


def _actor_role(request: Request) -> str:
    role = str((getattr(request.state, "user_info", {}) or {}).get("role") or "").strip()
    if role not in {"doctor", "nurse"}:
        raise HTTPException(status_code=403, detail="Assistant access requires a clinical identity")
    return role


def _resolve_assistant_mode(actor_role: str, requested_mode: object, session: dict | None) -> str:
    from ..agent.assistant import ASSISTANT_MODE_ACCESS

    session_mode = str((session or {}).get("assistant_mode") or (session or {}).get("role") or "").strip()
    mode = str(requested_mode or session_mode or actor_role).strip()
    if session_mode and mode != session_mode:
        raise HTTPException(status_code=409, detail="Assistant session is already bound to another mode")
    if mode not in ASSISTANT_MODE_ACCESS.get(actor_role, set()):
        raise HTTPException(status_code=403, detail="This clinical identity cannot use the requested assistant mode")
    return mode


def _require_message(body: dict, *, max_chars: int = 4000) -> str:
    message = str(body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="消息不能为空")
    if len(message) > max_chars:
        raise HTTPException(status_code=422, detail=f"消息不能超过 {max_chars} 个字符")
    return message


def _require_session_access(request: Request, session_id: str | None, actor_id: str) -> dict:
    if not session_id:
        return {}
    from ..agent.assistant import can_access_session, get_session

    if not can_access_session(session_id, actor_id):
        raise HTTPException(status_code=403, detail="Assistant session is not accessible to this user")
    session = get_session(session_id) or {}
    patient_id = str(session.get("patient_id") or "")
    _require_patient_access(request, patient_id)
    return session


def _enforce_public_rate_limit(request: Request, client_id: str) -> None:
    address = request.client.host if request.client else "unknown"
    key = f"{address}:{client_id}"
    now = time.monotonic()
    with _public_requests_lock:
        bucket = _public_requests[key]
        while bucket and now - bucket[0] >= _PUBLIC_RATE_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= _PUBLIC_RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Public assistant rate limit exceeded")
        bucket.append(now)
