"""Pydantic v2 请求/响应 Schema —— knowledge-orchestrator 服务。

所有 API 出入参均由此定义，确保类型安全。
阶段J审计修复: UnifiedResponse/ErrorDetail 统一迁移至 zhenhu.contracts。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from zhenhu.contracts import ErrorDetail, UnifiedResponse  # noqa: F401 — 阶段J审计修复; 经本模块再导出


# ============================================================================
# 知识文档
# ============================================================================


class ImportDocumentRequest(BaseModel):
    """知识文档导入请求体（JSON 模式，不含文件内容）。

    Attributes:
        title: 文档标题。
        version: 文档版本号。
        owner: 归属部门。
        content: 文档正文（纯文本）。
        effective_from: 生效起始日期（ISO 8601）。
        effective_until: 生效截止日期（ISO 8601）。
        source_format: 源格式（txt/md）。
    """

    title: str = Field(..., min_length=1, max_length=256, description="文档标题")
    version: str = Field(..., min_length=1, max_length=32, description="版本号")
    owner: str = Field(..., min_length=1, max_length=64, description="归属部门")
    content: str = Field(..., min_length=1, description="文档正文")
    effective_from: str = Field(
        ..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="生效起始日期（YYYY-MM-DD）"
    )
    effective_until: str = Field(
        ..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="生效截止日期（YYYY-MM-DD）"
    )
    source_format: str = Field(
        default="txt", pattern=r"^(txt|md)$", description="源文件格式"
    )


class DocumentResponse(BaseModel):
    """知识文档响应体（不包含分块明细）。"""

    document_id: str = Field(..., description="文档 ID")
    title: str = Field(..., description="文档标题")
    version: str = Field(..., description="版本号")
    status: str = Field(..., description="当前状态")
    owner: str = Field(..., description="归属部门")
    effective_from: str | None = Field(default=None, description="生效起始日期")
    effective_until: str | None = Field(default=None, description="生效截止日期")
    source_format: str | None = Field(default=None, description="源格式")
    chunk_count: int = Field(default=0, description="分块数量")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")

    model_config = {"from_attributes": True}


class DocumentImportResponse(BaseModel):
    """导入响应体（返回入库任务）。"""

    job_id: str = Field(..., description="入库任务 ID")
    status: str = Field(..., description="任务状态")


class DocumentTransitionRequest(BaseModel):
    """知识文档状态转移请求体。

    Attributes:
        next_state: 目标状态。
    """

    next_state: str = Field(..., min_length=1, max_length=32, description="目标状态")


class DocumentTransitionResponse(BaseModel):
    """知识文档状态转移响应体。"""

    document_id: str = Field(..., description="文档 ID")
    status: str = Field(..., description="转移后状态")


class DocumentListResponse(BaseModel):
    """分页文档列表响应体。"""

    items: list[DocumentResponse] = Field(default_factory=list, description="文档列表")
    total: int = Field(..., description="总数")
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页条数")


# ============================================================================
# 知识分块
# ============================================================================


class ChunkResponse(BaseModel):
    """知识分块响应体。"""

    chunk_id: str = Field(..., description="分块 ID")
    document_id: str = Field(..., description="所属文档 ID")
    text: str = Field(..., description="分块文本")
    location: str | None = Field(default=None, description="分块坐标")
    created_at: datetime | None = Field(default=None, description="创建时间")

    model_config = {"from_attributes": True}


# ============================================================================
# 检索
# ============================================================================


class SearchResultItem(BaseModel):
    """检索结果单条记录。"""

    chunk_id: str = Field(..., description="分块 ID")
    document_id: str = Field(..., description="所属文档 ID")
    text: str = Field(..., description="匹配文本")
    score: float = Field(..., description="相关度评分（0~1）")
    location: str | None = Field(default=None, description="分块坐标")
    citation: dict[str, Any] = Field(default_factory=dict, description="引用信息")


class SearchResponse(BaseModel):
    """检索响应体。"""

    results: list[SearchResultItem] = Field(default_factory=list, description="检索结果")


# ============================================================================
# 入库任务
# ============================================================================


class IngestionJobResponse(BaseModel):
    """入库任务响应体。"""

    job_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态")
    attempt: int = Field(..., description="尝试次数")
    document_id: str | None = Field(default=None, description="产出的文档 ID")
    input_title: str | None = Field(default=None, description="导入标题")
    input_version: str | None = Field(default=None, description="导入版本")
    input_owner: str | None = Field(default=None, description="导入归属")
    source_file_name: str | None = Field(default=None, description="源文件名")
    error_code: str | None = Field(default=None, description="错误码")
    error_message: str | None = Field(default=None, description="错误描述")
    error_retryable: bool | None = Field(default=None, description="是否可重试")
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")

    model_config = {"from_attributes": True}


class IngestionJobListResponse(BaseModel):
    """分页入库任务列表。"""

    items: list[IngestionJobResponse] = Field(default_factory=list, description="任务列表")
    total: int = Field(..., description="总数")
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页条数")


# ============================================================================
# 审计 / 生命周期
# ============================================================================


class LifecycleEventResponse(BaseModel):
    """知识生命周期事件响应体。"""

    audit_id: str = Field(..., description="审计事件 ID")
    document_id: str | None = Field(default=None, description="文档 ID")
    event_type: str = Field(..., description="事件类型")
    actor: str = Field(..., description="操作者")
    detail: str | None = Field(default=None, description="事件详情")
    before_state: str | None = Field(default=None, description="转移前状态")
    after_state: str | None = Field(default=None, description="转移后状态")
    occurred_at: datetime = Field(..., description="发生时间")

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    """分页审计事件列表。"""

    items: list[LifecycleEventResponse] = Field(default_factory=list, description="审计事件列表")
    total: int = Field(..., description="总数")
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页条数")


# ============================================================================
# Reset
# ============================================================================


class ResetResponse(BaseModel):
    """运行时重置响应体。"""

    status: str = Field(default="reset", description="重置结果")
    sample_count: int = Field(..., description="预置样例数量")
