"""FastAPI 应用入口 —— workflow-engine 服务。

提供病例协同工作流的 REST API，包括病例创建、分析、审核和状态机管理。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from zhenhu.workflow.routes import cases_router, hooks_router

VERSION = "0.2.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理：启动时初始化数据库，关闭时清理连接。"""
    from zhenhu.workflow.models import init_db

    await init_db()
    yield


app = FastAPI(
    title="臻护 Workflow Engine",
    description="病例协同工作流引擎：状态机 + Agent 编排 + 审核流",
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
app.include_router(cases_router)
app.include_router(hooks_router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """为每个请求注入 X-Request-ID（若上游已传则透传）。"""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


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
