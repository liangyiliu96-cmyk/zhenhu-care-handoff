"""pytest 配置与共享 fixtures。

为 knowledge-orchestrator 提供 SQLite :memory: 数据库会话支持。
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def db_session():
    """创建独立的内存数据库会话，每次测试后自动回滚。

    每个测试用例都获得一个干净的数据库环境。
    """
    from zhenhu.knowledge.models import (
        init_db,
        async_session_factory,
        async_engine,
        Base,
    )

    # 重建全部表
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        yield session

    # 清理
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def sample_document_data():
    """标准测试用文档数据。"""
    return {
        "title": "测试知识文档",
        "version": "0.1",
        "owner": "测试部门",
        "content": "这是测试正文内容。用于验证知识文档的导入、分块、状态转移和检索功能。",
        "effective_from": "2026-01-01",
        "effective_until": "2027-01-01",
        "source_format": "txt",
    }
