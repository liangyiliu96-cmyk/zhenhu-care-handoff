"""Pydantic schemas + UnifiedResponse —— 合并迁入。

阶段J审计修复: UnifiedResponse/ErrorDetail 统一迁移至 zhenhu.contracts。
"""

from __future__ import annotations

from zhenhu.contracts import ErrorDetail, UnifiedResponse  # 阶段J审计修复

__all__ = [
    "ErrorDetail",
    "UnifiedResponse",
]
