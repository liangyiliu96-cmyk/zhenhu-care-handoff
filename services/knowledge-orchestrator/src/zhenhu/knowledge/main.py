"""FastAPI 应用入口 —— knowledge-orchestrator 服务。

提供知识文档导入、状态机管理、混合检索和反向阻断钩子的 REST API。
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from zhenhu.contracts.middleware import RequestIdMiddleware, setup_error_handlers
from zhenhu.knowledge.routes import documents_router, search_router, admin_router
from zhenhu.knowledge.middleware.auth import role_middleware, validate_auth_configuration

VERSION = "0.2.0"

# 服务根目录（.../services/knowledge-orchestrator）
_SERVICE_ROOT = Path(__file__).resolve().parents[3]


def _should_run_migrations() -> bool:
    """生产环境（APP_ENV=production 或 DATABASE_URL 为 mysql）执行 Alembic 迁移。

    测试/开发（SQLite）保持原 create_all 路径，确保现有测试不受影响。
    """
    env = os.environ.get("APP_ENV", "").lower()
    db_url = os.environ.get("DATABASE_URL", "").lower()
    return env == "production" or "mysql" in db_url


async def _run_migrations() -> None:
    """编程式执行 Alembic 迁移至最新版本（alembic upgrade head）。

    对既有 create_all 遗留库（无 alembic_version）做幂等引导：
    1. 检测 alembic_version 表是否存在；
    2. 无 alembic_version 且库内已有业务表（legacy 库）→ 先用
       Base.metadata.create_all(checkfirst=True) 幂等补表（补缺失新表如
       knowledge_audit_logs，不重建已有表），再 alembic stamp head 标记基线；
    3. 之后正常 upgrade head（幂等）。
    全新空库仍走 upgrade head 由迁移脚本建表；已迁移库直接 upgrade head。

    env.py 内部使用 asyncio.run() 驱动异步引擎，因此必须在独立线程中执行，
    避免与当前运行中的事件循环冲突（FastAPI lifespan 运行在事件循环内）。
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect as sa_inspect

    from zhenhu.knowledge.models import Base, async_engine

    async def _existing_tables() -> set[str]:
        async with async_engine.connect() as conn:
            def _get(sync_conn):
                return set(sa_inspect(sync_conn).get_table_names())
            return await conn.run_sync(_get)

    tables = await _existing_tables()
    # legacy 库：库内已有业务表但尚未纳入 Alembic 管理
    is_legacy = "alembic_version" not in tables and bool(tables)

    if is_legacy:
        # 幂等补表：补缺失表（如 knowledge_audit_logs），不重建已有表
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    def _migrate() -> None:
        cfg = Config(str(_SERVICE_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(_SERVICE_ROOT / "migrations"))
        if is_legacy:
            command.stamp(cfg, "head")
        command.upgrade(cfg, "head")

    await asyncio.to_thread(_migrate)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理：启动时初始化数据库，关闭时清理连接。"""
    from zhenhu.knowledge.models import init_db

    if _should_run_migrations():
        await _run_migrations()
    else:
        # 测试/开发（SQLite）回退：仍走 create_all，不强制测试走 Alembic
        await init_db()
    yield


app = FastAPI(
    title="臻护 Knowledge Orchestrator",
    description="知识管理与编排服务：文档导入、版本状态机、混合检索、反向阻断钩子",
    version=VERSION,
    lifespan=lifespan,
)

validate_auth_configuration()

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

# 统一鉴权中间件（header 开发演示 / oidc 生产强制）
app.middleware("http")(role_middleware)

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
