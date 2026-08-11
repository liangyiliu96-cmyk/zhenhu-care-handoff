"""病例审计辅助函数 —— 记录病例生命周期关键操作的不可变审计事件。

与 inpatient-ward 的 audit.py 对齐：审计写入与业务事务同库同事务，
随调用方 commit 一起落库；不提供修改/删除入口（INSERT-only 证据链）。

workflow-engine 的审计主表为 AuditEvent（models.py），字段映射：
  actor            → 操作人角色
  event_type       → 操作类型（action）
  case_id          → 资源 ID（resource_id，类型固定为 case/risk）
  before/after_state → 转移前后状态
  detail           → 元数据（含 request_id 等结构化信息）
  occurred_at      → 发生时间（timestamp）
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.workflow.models import AuditEvent

# 与 models.py / state_machine.py 保持一致的版本号
WORKFLOW_VERSION = "0.2.0"


async def record_case_audit(
    session: AsyncSession,
    *,
    case_id: str,
    actor: str,
    event_type: str,
    title: str,
    detail: str | None = None,
    before_state: str | None = None,
    after_state: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    """写入一条病例审计事件（与调用方处于同一事务，随调用方 commit 落库）。

    Args:
        session: 当前数据库会话（与业务写入共用事务）。
        case_id: 病例 ID（审计资源 ID）。
        actor: 操作人角色。
        event_type: 事件类型（如 case_created / risk_reviewed）。
        title: 审计事件标题。
        detail: 事件详情（可携带结构化元数据）。
        before_state: 转移前状态。
        after_state: 转移后状态。
        request_id: 请求 ID，作为元数据写入 detail。

    Returns:
        已加入会话但尚未提交的 AuditEvent 实例。
    """
    payload = detail
    if request_id:
        meta = f"request_id={request_id}"
        payload = f"{payload} | {meta}" if payload else meta

    audit = AuditEvent(
        case_id=case_id,
        actor=actor,
        event_type=event_type,
        title=title,
        detail=payload,
        before_state=before_state,
        after_state=after_state,
        workflow_version=WORKFLOW_VERSION,
    )
    session.add(audit)
    await session.flush()
    return audit
