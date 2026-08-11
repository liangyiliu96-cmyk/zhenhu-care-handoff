"""Alembic 迁移环境 —— fhir-adapter 服务。

- target_metadata 使用 zhenhu.fhir.models.Base.metadata，
  保证 autogenerate 与 ORM 模型完全一致。
- 数据库 URL 优先取环境变量 DATABASE_URL，未设置时回退到 models.DATABASE_URL
  （与 models.py 的默认值一致：SQLite 测试库）。
- 使用异步引擎执行迁移（参考 SQLAlchemy Alembic async 模板）。
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ----------------------------------------------------------------------------
# 路径注入：允许通过 `alembic` CLI（服务根目录）或编程式调用两种方式运行
# ----------------------------------------------------------------------------
_SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_SERVICE_ROOT, "src")
_CONTRACTS_SRC = os.path.normpath(
    os.path.join(_SERVICE_ROOT, "..", "..", "packages", "clinical-contracts-py", "src")
)
for _p in (_SRC, _CONTRACTS_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 导入全部模型，保证 Base.metadata 聚合完整（autogenerate 可见）
from zhenhu.fhir import models  # noqa: E402
from zhenhu.fhir.models import Base  # noqa: E402

config = context.config

# DATABASE_URL 环境变量优先，未设置时回退到 models.py 默认（SQLite 测试库）
_database_url = os.environ.get("DATABASE_URL") or models.DATABASE_URL
config.set_main_option("sqlalchemy.url", _database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode（生成 SQL 脚本，不连接数据库）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with an async engine. """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
