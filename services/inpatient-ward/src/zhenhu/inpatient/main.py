"""住院协同 FastAPI 应用入口 —— 合并迁入。

挂载臻护共享中间件: RequestIdMiddleware + setup_error_handlers。
lifespan + async engine + 路由注册。

合并迁入修正A: 删除本地 middleware.py, 改用 zhenhu.contracts.middleware。
合并迁入修正A: 移除 app.config/app.db 依赖, 改用自包含 models。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 合并迁入修正A: 使用共享 contracts 中间件, 不再引用本地 middleware.py
from zhenhu.contracts.middleware import RequestIdMiddleware, setup_error_handlers
# 合并迁入修正: 路由导入改为相对路径
from .routes.admission import router as admission_router
from .routes.monitoring import router as monitoring_router
from .routes.discharge import router as discharge_router
from .routes.admin import router as admin_router

VERSION = "0.3.0"

# 合并迁入修正: SQLite 数据库引擎(移除 app.config.settings 依赖)
ASYNC_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./zhenhu_inpatient.db")
async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """获取异步数据库会话。"""
    async with async_session_factory() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理：启动时初始化数据库表。"""
    from .models import Base

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="臻护住院协同",
    description="通用住院协同模块 —— 病种模板化 + Agent 编排",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 臻护请求 ID 中间件（透传/注入 X-Request-ID）
app.add_middleware(RequestIdMiddleware)

# 臻护统一错误处理
setup_error_handlers(app)

# 注册路由
app.include_router(admission_router)
app.include_router(monitoring_router)
app.include_router(discharge_router)
app.include_router(admin_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """健康检查端点。"""
    return {
        "status": "ok",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
