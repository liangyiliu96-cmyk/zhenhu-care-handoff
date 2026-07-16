"""住院协同 FastAPI 应用入口 —— 合并迁入。

挂载臻护共享中间件: RequestIdMiddleware + setup_error_handlers。
lifespan + async engine + 路由注册。

合并迁入修正A: 删除本地 middleware.py, 改用 zhenhu.contracts.middleware。
合并迁入修正A: 移除 app.config/app.db 依赖, 改用自包含 models。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GzipMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.middleware.trustedhost import TrustedHostMiddleware

# 合并迁入修正A: 使用共享 contracts 中间件, 不再引用本地 middleware.py
from zhenhu.contracts.middleware import RequestIdMiddleware, setup_error_handlers
from zhenhu.contracts import get_session as _contracts_get_session  # 阶段J审计修复
from zhenhu.contracts.agent import set_ai_provider, DeepSeekProvider, RuleBasedProvider
# 合并迁入修正: 路由导入改为相对路径
from .routes.admission import router as admission_router
from .routes.monitoring import router as monitoring_router
from .routes.discharge import router as discharge_router
from .routes.admin import router as admin_router

VERSION = "0.3.0"

# 结构化日志配置
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# 阶段5: DeepSeek LLM 接入（API key 通过环境变量 DEEPSEEK_API_KEY 传入；不可用时回退 RuleBasedProvider）
deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
if deepseek_key:
    try:
        set_ai_provider(DeepSeekProvider(
            api_key=deepseek_key,
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            temperature=0.3,
        ))
    except Exception:
        set_ai_provider(RuleBasedProvider())  # 回退
else:
    set_ai_provider(RuleBasedProvider())

# 合并迁入修正: SQLite 数据库引擎(移除 app.config.settings 依赖)
ASYNC_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./zhenhu_inpatient.db")
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
    max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
    pool_recycle=int(os.environ.get("DB_POOL_RECYCLE", "3600")),  # 1小时回收
    pool_pre_ping=True,  # 连接前验证
    pool_timeout=30,  # 等待连接超时30秒
)
async_session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:  # 阶段J审计修复: 委托 contracts 统一实现
    """FastAPI Depends: 注入数据库会话 —— 阶段J审计修复。"""
    async for session in _contracts_get_session(async_session_factory):
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期：启动建表 → 关闭释放连接。"""
    from .models import Base

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # startup: 输出路由表
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            logger.info("Route: %s %s", route.methods, route.path)

    logger.info("inpatient-ward started")
    yield

    # 优雅关闭
    logger.info("inpatient-ward shutting down...")
    await async_engine.dispose()
    logger.info("inpatient-ward stopped")


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

# Gzip 压缩中间件
app.add_middleware(GzipMiddleware, minimum_size=1000)

# 臻护请求 ID 中间件（透传/注入 X-Request-ID）
app.add_middleware(RequestIdMiddleware)

# 臻护统一错误处理
setup_error_handlers(app)

# TrustedHost 中间件（生产环境用，开发环境可通过环境变量关闭）
allowed_hosts = os.environ.get("ALLOWED_HOSTS", "*")
if allowed_hosts != "*":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts.split(","),
    )

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
        "service": "inpatient-ward",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Prometheus metrics 端点 ──
from zhenhu.inpatient.agent.metrics import get_metrics


@app.get("/metrics", tags=["system"])
async def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(get_metrics())
