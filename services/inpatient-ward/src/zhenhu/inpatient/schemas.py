"""Pydantic schemas + UnifiedResponse —— 合并迁入。

对齐臻护 UnifiedResponse[Data] 统一响应格式。
"""

from __future__ import annotations

from typing import Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """统一错误详情 —— 与 middleware error 格式完全一致。"""

    code: str
    message: str


class UnifiedResponse(BaseModel, Generic[T]):
    """统一 API 响应格式 —— 合并迁入: 对齐臻护 contracts。

    由 RequestIdMiddleware 自动注入 request_id。
    异常由 setup_error_handlers 统一包装为 error 字段。
    """

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    data: T | None = None
    error: ErrorDetail | None = None
