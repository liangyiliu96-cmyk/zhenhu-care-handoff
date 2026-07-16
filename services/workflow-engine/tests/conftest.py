"""workflow-engine 测试 fixtures —— 阶段J审计修复。

参考 fhir-adapter conftest 模式，提供共享 DB 和 AsyncClient。
不删除测试文件中的内联 fixture——二者共存，conftest 作为推荐方式。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zhenhu.workflow.main import app
from zhenhu.workflow.models import Base

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def engine():
    """创建测试用 SQLite :memory: 引擎并初始化表结构。"""
    e = create_async_engine(TEST_DB)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest.fixture
async def session(engine):
    """创建测试用异步数据库会话。"""
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


@pytest.fixture
async def client(engine):
    """创建 FastAPI AsyncClient（每次测试干净 :memory: 库）。"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
