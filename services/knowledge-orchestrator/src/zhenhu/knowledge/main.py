"""FastAPI 应用入口 —— knowledge-orchestrator 服务。

提供知识文档导入、状态机管理、混合检索和反向阻断钩子的 REST API。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from zhenhu.contracts.middleware import RequestIdMiddleware, setup_error_handlers
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

# 请求 ID 中间件（透传/注入 X-Request-ID）
app.add_middleware(RequestIdMiddleware)

# 统一错误处理
setup_error_handlers(app)

# 注册路由
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(admin_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """健康检查端点。

    Returns:
        {"status": "ok", "version": "0.2.0", "timestamp": "..."}
    """
    return {
        "status": "ok",
        "service": "knowledge-orchestrator",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
