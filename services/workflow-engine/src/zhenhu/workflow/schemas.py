"""Pydantic v2 请求/响应 Schema —— workflow-engine 服务。

所有 API 出入参均由此定义，确保类型安全。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


# ============================================================================
# 统一响应包装
# ============================================================================

T = TypeVar("T")


class UnifiedResponse(BaseModel, Generic[T]):
    """统一 API 响应格式。

    Attributes:
        request_id: 请求关联 ID（透传自 X-Request-ID）。
        data: 响应载荷。
        error: 错误信息，成功时为 None。
    """

    request_id: str = Field(..., description="请求关联 ID")
    data: T | None = Field(default=None, description="响应载荷")
    error: str | None = Field(default=None, description="错误信息")


# ============================================================================
# 病例
# ============================================================================


class CaseCreate(BaseModel):
    """创建病例请求体。

    Attributes:
        input_snapshot_id: 输入快照标识（来自 fhir-adapter）。
    """

    input_snapshot_id: str = Field(..., min_length=1, max_length=256, description="输入快照标识")


class CaseResponse(BaseModel):
    """病例响应体。"""

    case_id: str = Field(..., description="病例 ID")
    state: str = Field(..., description="当前状态")
    input_snapshot_id: str | None = Field(default=None, description="输入快照标识")
    workflow_version: str = Field(default="0.2.0", description="工作流版本")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")

    model_config = {"from_attributes": True}


# ============================================================================
# 风险项
# ============================================================================


class RiskItemResponse(BaseModel):
    """风险项响应体。"""

    risk_id: str = Field(..., description="风险项 ID")
    case_id: str = Field(..., description="所属病例 ID")
    category: str = Field(..., description="风险分类")
    severity: str = Field(..., description="严重度")
    severity_label: str = Field(..., description="严重度标签")
    title: str = Field(..., description="风险标题")
    summary: str = Field(..., description="风险摘要")
    status: str = Field(default="pending", description="审核状态")
    decision: str | None = Field(default=None, description="审核决定")
    decision_note: str | None = Field(default=None, description="审核备注")
    evidence_snippet: str | None = Field(default=None, description="证据摘录")
    citation_excerpt: str | None = Field(default=None, description="引用摘录")
    citation_document_id: str | None = Field(default=None, description="引用文档 ID")
    created_at: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}


class ReviewRequest(BaseModel):
    """审核风险项请求体。

    Attributes:
        action: 审核动作 —— confirm / reject / escalate。
        note: 审核备注（可选）。
    """

    action: str = Field(
        ..., pattern=r"^(confirm|reject|escalate)$", description="审核动作"
    )
    note: str | None = Field(default=None, max_length=1024, description="审核备注")


# ============================================================================
# 分析
# ============================================================================


class AnalyseResponse(BaseModel):
    """分析完成后的响应体。"""

    case_id: str = Field(..., description="病例 ID")
    state: str = Field(..., description="分析后的病例状态")
    risk_items: list[RiskItemResponse] = Field(
        default_factory=list, description="风险项列表"
    )


# ============================================================================
# 任务草稿
# ============================================================================


class TaskDraftResponse(BaseModel):
    """任务草稿响应体。"""

    draft_id: str = Field(..., description="任务草稿 ID")
    case_id: str = Field(..., description="所属病例 ID")
    status: str = Field(..., description="草稿状态")
    sop_version: str | None = Field(default=None, description="SOP 版本")
    tasks_json: str | None = Field(default=None, description="任务列表 JSON")
    created_at: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}


class SupplementRequest(BaseModel):
    """补充任务执行信息请求体。

    Attributes:
        result: 执行结果描述。
        note: 补充说明（可选）。
    """

    result: str = Field(..., min_length=1, description="执行结果描述")
    note: str = Field(default="", description="补充说明")


class SupplementResponse(BaseModel):
    """补充任务执行信息响应体。"""

    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态")
    execution_result: str = Field(..., description="执行结果")
    execution_note: str = Field(default="", description="执行说明")


class KnowledgeChangedHookRequest(BaseModel):
    """知识变更钩子请求体。

    Attributes:
        document_id: 发生变更的知识文档 ID。
    """

    document_id: str = Field(..., min_length=1, description="知识文档 ID")


class KnowledgeChangedHookResponse(BaseModel):
    """知识变更钩子响应体。"""

    blocked_count: int = Field(..., description="受影响的病例数量")


class SimulatedPublishResponse(BaseModel):
    """模拟发布响应体。"""

    state: str = Field(..., description="发布后的病例状态")


# ============================================================================
# 审计
# ============================================================================


class AuditEventResponse(BaseModel):
    """审计事件响应体。"""

    audit_id: str = Field(..., description="审计 ID")
    case_id: str = Field(..., description="病例 ID")
    actor: str = Field(..., description="操作人")
    event_type: str = Field(..., description="事件类型")
    title: str = Field(..., description="事件标题")
    detail: str | None = Field(default=None, description="详情")
    before_state: str | None = Field(default=None, description="转移前状态")
    after_state: str | None = Field(default=None, description="转移后状态")
    occurred_at: datetime = Field(..., description="发生时间")

    model_config = {"from_attributes": True}


# ============================================================================
# 错误
# ============================================================================


class ErrorDetail(BaseModel):
    """结构化错误详情。"""

    code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误描述")
    details: dict[str, Any] | None = Field(default=None, description="附加详情")
