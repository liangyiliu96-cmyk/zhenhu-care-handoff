"""inpatient-ward 测试 fixtures。合并迁入。

提供 SQLite :memory: 数据库和 FastAPI AsyncClient,
参照 workflow-engine/fhir-adapter conftest 模式。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """启用 SQLite 外键约束强制。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def _create_test_engine(db_url: str = "sqlite+aiosqlite:///:memory:"):
    """创建测试引擎并注册 SQLite FK pragma。"""
    engine = create_async_engine(db_url, echo=False)
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)
    return engine


@pytest.fixture
async def client():
    """创建 AsyncClient 用于测试 FastAPI app（每次测试干净 :memory: 库）。

    数据库使用 SQLite :memory:，确保测试间隔离。
    """
    import os
    from zhenhu.inpatient.main import app  # 合并迁入: 替换旧 app.src.zhenhu 路径
    from zhenhu.inpatient.models import Base  # 合并迁入: 替换旧 app.db.base 路径
    import zhenhu.inpatient.models as m

    # 强制使用 :memory: 数据库
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    m.async_engine = _create_test_engine()
    m.async_session_factory = async_sessionmaker(m.async_engine, class_=AsyncSession, expire_on_commit=False)

    async with m.async_engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with m.async_engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.drop_all)
