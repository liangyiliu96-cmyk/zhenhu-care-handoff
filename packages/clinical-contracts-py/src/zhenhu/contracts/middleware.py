"""统一错误处理中间件 —— 三服务共享。

将所有异常统一转换为 UnifiedResponse 格式：
  {"request_id": "...", "data": null, "error": {"code": "...", "message": "..."}}

request_id 从 request.state 提取（需配合 RequestIdMiddleware 注入）。
"""

from __future__ import annotations

import uuid
import logging

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """注入 request_id 到 request.state，透传 X-Request-ID 响应头。

    若请求头已包含 X-Request-ID 则复用，否则生成新的 UUID。
    """

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def setup_error_handlers(app):
    """在 FastAPI app 上注册统一错误处理。

    将所有异常统一转换为：
      {"request_id": "...", "data": null, "error": {"code": "...", "message": "..."}}

    - HTTPException with dict detail containing "code" → 透传 detail 到 error 字段
    - HTTPException with string detail → 包装为 HTTP_ERROR
    - 其他未捕获异常 → INTERNAL_ERROR（500），记录日志
    """

    @app.exception_handler(Exception)
    async def unified_unexpected_error(request: Request, exc: Exception):
        """兜底：未预期的非 HTTPException 异常 → 500。"""
        rid = getattr(request.state, "request_id", None) or "unknown"
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "request_id": rid,
                "data": None,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务端发生未预期错误",
                },
            },
        )

    @app.exception_handler(HTTPException)
    async def unified_http_error(request: Request, exc: HTTPException):
        """HTTPException → UnifiedResponse error 格式。"""
        rid = getattr(request.state, "request_id", None) or "unknown"
        detail = exc.detail

        if isinstance(detail, dict) and "code" in detail:
            return JSONResponse(
                status_code=exc.status_code,
                content={"request_id": rid, "data": None, "error": detail},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "request_id": rid,
                "data": None,
                "error": {"code": "HTTP_ERROR", "message": str(detail)},
            },
        )
