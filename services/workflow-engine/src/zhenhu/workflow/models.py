"""SQLAlchemy ORM 模型 —— workflow-engine 数据层。

定义病例、风险项、任务草稿、审计事件四个核心实体。
阶段 0 使用 SQLite :memory: 进行测试。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

import os
import tempfile

# 测试用临时文件数据库；生产环境通过 DATABASE_URL 环境变量覆盖
_test_db = os.path.join(tempfile.gettempdir(), "zhenhu_workflow_test.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{_test_db}")

async_engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def _new_id(prefix: str = "") -> str:
    """生成带前缀的唯一标识符。"""
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class Case(Base):
    """病例实体 —— 对照需求 §3.4 病例状态机。"""

    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, default=lambda: _new_id("CASE-")
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    input_snapshot_id: Mapped[str] = mapped_column(String(64), nullable=True)
    workflow_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="0.2.0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # 关联
    risk_items: Mapped[list["RiskItem"]] = relationship(
        "RiskItem", back_populates="case", cascade="all, delete-orphan"
    )
    task_drafts: Mapped[list["TaskDraft"]] = relationship(
        "TaskDraft", back_populates="case", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent", back_populates="case", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Case(case_id={self.case_id!r}, state={self.state!r})>"


class RiskItem(Base):
    """风险项实体 —— 分析结果中待医生审核的风险点。"""

    __tablename__ = "risk_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    risk_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, default=lambda: _new_id("RISK-")
    )
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.case_id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    severity_label: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_document_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # 反向关联
    case: Mapped["Case"] = relationship("Case", back_populates="risk_items")

    def __repr__(self) -> str:
        return f"<RiskItem(risk_id={self.risk_id!r}, status={self.status!r})>"


class TaskDraft(Base):
    """交接/随访任务草稿实体。"""

    __tablename__ = "task_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, default=lambda: _new_id("DRAFT-")
    )
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.case_id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    sop_version: Mapped[str] = mapped_column(String(32), nullable=True)
    tasks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # 反向关联
    case: Mapped["Case"] = relationship("Case", back_populates="task_drafts")

    def __repr__(self) -> str:
        return f"<TaskDraft(draft_id={self.draft_id!r}, status={self.status!r})>"


class AuditEvent(Base):
    """审计事件实体 —— 不可变证据链。"""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, default=lambda: _new_id("AUDIT-")
    )
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.case_id"), nullable=False, index=True
    )
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    after_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    workflow_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="0.2.0"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # 反向关联
    case: Mapped["Case"] = relationship("Case", back_populates="audit_events")

    # 复合索引：按病例 + 时间查询审计轨迹
    __table_args__ = (
        Index("idx_audit_case_ts", "case_id", "occurred_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditEvent(audit_id={self.audit_id!r}, event_type={self.event_type!r})>"


async def init_db() -> None:
    """初始化数据库表结构。"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """获取一个新的异步数据库会话（用于依赖注入）。"""
    async with async_session_factory() as session:
        yield session
