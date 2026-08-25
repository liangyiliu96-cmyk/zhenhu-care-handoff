"""SQLAlchemy ORM 模型 —— knowledge-orchestrator 数据层。

定义知识文档、分块、入库任务、引用、生命周期事件五个实体。
阶段 0 使用 SQLite :memory: 进行测试。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Float,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from zhenhu.contracts import get_session as _contracts_get_session  # 阶段J审计修复

import os
import tempfile

# 测试用临时文件数据库；生产环境通过 DATABASE_URL 环境变量覆盖
_test_db = os.path.join(tempfile.gettempdir(), "zhenhu_knowledge_test.db")
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


class KnowledgeDocument(Base):
    """知识文档实体 —— 对照需求 §4.4 知识版本状态。

    知识文档是知识管理的核心资产，经过导入、审核、发布后进入可检索状态。
    每个文档包含多个分块（chunk），用于细粒度检索。
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("DOC-"),
        comment="知识文档唯一标识"
    )
    title: Mapped[str] = mapped_column(
        String(256), nullable=False,
        comment="知识文档标题"
    )
    version: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="文档版本号"
    )
    owner: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="文档归属部门/组织"
    )
    layer: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True,
        comment="知识层级：L1-L16 或业务扩展层"
    )
    disease_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True,
        comment="适用病种 ID"
    )
    department: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True,
        comment="适用科室"
    )
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", index=True,
        comment="证据来源类型：guideline/systematic_review/drug_label/institutional_sop/primary_study/unknown"
    )
    evidence_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown",
        comment="证据等级：A/B/C/unknown，不对缺失元数据强行分级"
    )
    guideline_year: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True,
        comment="指南或来源年份"
    )
    source_credibility: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5,
        comment="来源可信度启发式分值，仅用于排序与提示，不替代临床评价"
    )
    evidence_metadata_origin: Mapped[str] = mapped_column(
        String(16), nullable=False, default="inferred",
        comment="循证元数据来源：declared/inferred"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="review_pending", index=True,
        comment="文档状态：review_pending/published/expired/withdrawn/superseded/archived/review_rejected"
    )
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True,
        comment="生效起始日期"
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True,
        comment="生效截止日期"
    )
    source_format: Mapped[str | None] = mapped_column(
        String(8), nullable=True,
        comment="源文件格式：txt/md/pdf/docx"
    )
    source_mime: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="源文件 MIME 类型"
    )
    source_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="源文件 SHA-256 摘要"
    )
    source_byte_length: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="源文件字节数"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="内容摘要（SHA-256）用于去重"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow,
        comment="最后更新时间"
    )

    # 关联：文档 → 分块（一对多）
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan"
    )
    # 关联：文档 → 生命周期事件（一对多）
    lifecycle_events: Mapped[list["KnowledgeLifecycleEvent"]] = relationship(
        "KnowledgeLifecycleEvent", back_populates="document", cascade="all, delete-orphan"
    )
    # 关联：文档 → 入库任务（一对多）
    ingestion_jobs: Mapped[list["KnowledgeIngestionJob"]] = relationship(
        "KnowledgeIngestionJob", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocument(document_id={self.document_id!r}, title={self.title!r}, status={self.status!r})>"


class KnowledgeChunk(Base):
    """知识分块实体 —— 文档的细粒度检索单元。

    每个文档被拆分为多个固定长度的文本块，用于全文搜索和向量检索。
    分块是不可变的最小存储单元。
    """

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("CHUNK-"),
        comment="分块唯一标识"
    )
    document_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("knowledge_documents.document_id"), nullable=False, index=True,
        comment="所属文档 ID（FK）"
    )
    location: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="分块位置坐标（如页码、段落号）"
    )
    text: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="分块文本内容"
    )
    chunking_version: Mapped[str | None] = mapped_column(
        String(16), nullable=True,
        comment="分块策略版本"
    )
    vector_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="向量索引 ID（Milvus）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, comment="创建时间"
    )

    # 反向关联
    document: Mapped["KnowledgeDocument"] = relationship("KnowledgeDocument", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<KnowledgeChunk(chunk_id={self.chunk_id!r}, document_id={self.document_id!r})>"


class KnowledgeIngestionJob(Base):
    """知识入库任务实体 —— 异步解析与导入任务。

    入库任务分为排队（queued）→ 解析中（parsing）→ 待审核（review_pending）/ 失败（failed）。
    失败的任务可以被重试（queued）。
    """

    __tablename__ = "knowledge_ingestion_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("JOB-"),
        comment="任务唯一标识"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", index=True,
        comment="任务状态：queued/parsing/review_pending/failed"
    )
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        comment="尝试次数"
    )
    document_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("knowledge_documents.document_id"), nullable=True,
        comment="产出的文档 ID（FK）"
    )
    input_title: Mapped[str | None] = mapped_column(
        String(256), nullable=True,
        comment="导入源标题"
    )
    input_version: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
        comment="导入源版本"
    )
    input_owner: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="导入源归属"
    )
    source_file_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="源文件名"
    )
    error_code: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
        comment="错误码"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="错误详情"
    )
    error_retryable: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True,
        comment="是否可重试"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="开始时间"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间"
    )

    # 反向关联
    document: Mapped["KnowledgeDocument | None"] = relationship(
        "KnowledgeDocument", back_populates="ingestion_jobs"
    )

    def __repr__(self) -> str:
        return f"<KnowledgeIngestionJob(job_id={self.job_id!r}, status={self.status!r})>"


class KnowledgeCitation(Base):
    """知识引用实体 —— 检索结果的不可变审计记录。

    每次 AI 分析引用知识库内容时，生成一条固定引用记录。
    记录坐标（location）、原文摘录（excerpt）和检索策略版本。
    """

    __tablename__ = "knowledge_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    citation_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("CITE-"),
        comment="引用唯一标识"
    )
    document_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("knowledge_documents.document_id"), nullable=True, index=True,
        comment="被引用文档 ID（FK）"
    )
    chunk_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("knowledge_chunks.chunk_id"), nullable=True,
        comment="被引用分块 ID（FK）"
    )
    location: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="知识源坐标（如章节、段落）"
    )
    coordinates: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="详细坐标信息"
    )
    excerpt: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="引用原文摘录"
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
        comment="检索时间"
    )
    retrieval_strategy_version: Mapped[str | None] = mapped_column(
        String(16), nullable=True,
        comment="检索策略版本"
    )

    def __repr__(self) -> str:
        return f"<KnowledgeCitation(citation_id={self.citation_id!r})>"


class KnowledgeLifecycleEvent(Base):
    """知识生命周期事件实体 —— 不可变审计证据链。

    记录知识文档从导入、发布、过期到归档的所有状态转移事件。
    采用 INSERT-only 策略，不修改已写入的审计记录。
    """

    __tablename__ = "knowledge_lifecycle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("KAUDIT-"),
        comment="审计事件唯一标识"
    )
    document_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("knowledge_documents.document_id"), nullable=True, index=True,
        comment="所属文档 ID（FK）"
    )
    event_type: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="事件类型：knowledge_imported/knowledge_status_changed 等"
    )
    actor: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="操作者角色标识"
    )
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="事件详情"
    )
    before_state: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
        comment="转移前状态"
    )
    after_state: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
        comment="转移后状态"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, comment="发生时间"
    )

    # 反向关联
    document: Mapped["KnowledgeDocument | None"] = relationship(
        "KnowledgeDocument", back_populates="lifecycle_events"
    )

    def __repr__(self) -> str:
        return f"<KnowledgeLifecycleEvent(audit_id={self.audit_id!r}, event_type={self.event_type!r})>"


class KnowledgeAuditLog(Base):
    """知识操作审计日志 —— 非文档生命周期类操作的不可变审计记录。

    覆盖检索操作、运行时重置删除等通用操作；文档导入/状态变更/版本流转由
    KnowledgeLifecycleEvent 负责。参考 inpatient AuditLog 模式：
    记录 action_type、actor、resource_type/resource_id、detail、session_id。
    采用 INSERT-only 策略，不修改已写入的审计记录。
    """

    __tablename__ = "knowledge_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("KAUDIT-"),
        comment="审计事件唯一标识"
    )
    action_type: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="操作类型：knowledge_search/knowledge_deleted 等"
    )
    actor: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="操作者角色标识"
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
        comment="资源类型：knowledge/search"
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="资源 ID"
    )
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="事件详情（JSON 编码）"
    )
    session_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="请求 ID（session）"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
        comment="发生时间"
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeAuditLog(audit_id={self.audit_id!r}, "
            f"action_type={self.action_type!r})>"
        )


async def init_db() -> None:
    """初始化数据库表结构。"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # 阶段J审计修复: 委托 contracts 统一实现
    """获取一个新的异步数据库会话（用于依赖注入） —— 阶段J审计修复。"""
    async for session in _contracts_get_session(async_session_factory):
        yield session
