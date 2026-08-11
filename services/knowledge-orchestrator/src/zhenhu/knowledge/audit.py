"""知识操作审计辅助函数 —— 记录非文档生命周期类操作的不可变审计事件。

与 inpatient-ward 的 audit.py 对齐：审计写入与业务事务同库同事务，
随调用方 commit 一起落库；不提供修改/删除入口（INSERT-only 证据链）。

文档导入/状态变更/版本流转由 KnowledgeLifecycleEvent 负责（state_machine.py），
本模块负责通用操作审计（检索、运行时重置删除等），写入 KnowledgeAuditLog。

字段映射（对齐 inpatient AuditLog）：
  action_type   → 操作类型（如 knowledge_search / knowledge_deleted）
  actor         → 操作者角色
  resource_type → 资源类型
  resource_id   → 资源 ID
  detail        → 结构化元数据（JSON 编码）
  session_id    → 请求 ID
  occurred_at   → 发生时间
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.knowledge.models import KnowledgeAuditLog


async def record_audit_log(
    session: AsyncSession,
    *,
    action_type: str,
    actor: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> KnowledgeAuditLog:
    """写入一条知识操作审计（与调用方处于同一事务，随调用方 commit 落库）。

    Args:
        session: 当前数据库会话（与业务写入共用事务）。
        action_type: 操作类型。
        actor: 操作者角色标识。
        resource_type: 资源类型。
        resource_id: 资源 ID。
        detail: 结构化元数据（会被 JSON 编码存入 Text 列）。
        request_id: 请求 ID。

    Returns:
        已加入会话但尚未提交的 KnowledgeAuditLog 实例。
    """
    audit = KnowledgeAuditLog(
        action_type=action_type,
        actor=actor,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=json.dumps(detail, ensure_ascii=False) if detail else None,
        session_id=request_id,
    )
    session.add(audit)
    await session.flush()
    return audit
