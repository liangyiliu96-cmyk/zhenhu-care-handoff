"""FastAPI 应用入口 —— knowledge-orchestrator 服务。

提供知识文档导入、状态机管理、混合检索和反向阻断钩子的 REST API。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from zhenhu.knowledge.routes import documents_router, search_router, admin_router

VERSION = "0.2.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理：启动时初始化数据库，关闭时清理连接。"""
    from zhenhu.knowledge.models import init_db

    await init_db()
    yield


app = FastAPI(
    title="臻护 Knowledge Orchestrator",
    description="知识管理与编排服务：文档导入、版本状态机、混合检索、反向阻断钩子",
    version=VERSION,
    lifespan=lifespan,
)

# CORS 配置 —— 阶段 0 允许本地前端开发跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(admin_router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """为每个请求注入 X-Request-ID（若上游已传则透传）。"""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc):
    """500 统一错误处理。"""
    return JSONResponse(
        status_code=500,
        content={
            "request_id": getattr(request.state, "request_id", "unknown"),
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务内部错误",
                "details": str(exc),
            },
        },
    )


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """健康检查端点。

    Returns:
        {"status": "ok", "version": "0.2.0", "timestamp": "..."}
    """
    return {
        "status": "ok",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
