"""知识文档状态机服务 —— 封装 zhenhu-contracts 的转移断言并持久化生命周期事件。

每次状态转移前调用 zhenhu_contracts.assert_knowledge_transition 进行校验，
然后写入数据库并记录生命周期审计事件。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.contracts import assert_knowledge_transition, ContractError


def _utcnow() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


class StateMachineError(Exception):
    """状态机业务异常。"""

    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


class KnowledgeStateMachine:
    """知识文档状态机服务。

    封装所有合法的知识版本状态转移逻辑，每次转移：
    1. 调用 zhenhu_contracts.assert_knowledge_transition 校验合法性。
    2. 更新 document.status 和 document.updated_at。
    3. 写入一条 KnowledgeLifecycleEvent。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def transition(
        self,
        document,
        next_state: str,
        actor: str = "knowledge_admin",
        reason: str = "",
    ):
        """执行知识状态转移。

        Args:
            document: 当前 KnowledgeDocument ORM 实例。
            next_state: 目标状态，须通过 assert_knowledge_transition 校验。
            actor: 操作者标识（如 knowledge_admin）。
            reason: 转移原因，写入 lifecycle_event 的 detail 字段。

        Returns:
            更新后的 KnowledgeDocument 实例。

        Raises:
            StateMachineError: 当转移不合法时。
        """
        from zhenhu.knowledge.models import KnowledgeLifecycleEvent

        before = document.status

        # 1. 契约断言
        try:
            assert_knowledge_transition(before, next_state)
        except ContractError as exc:
            raise StateMachineError(
                code="ILLEGAL_TRANSITION",
                message=str(exc),
                details={"current_state": before, "next_state": next_state},
            ) from exc

        # 2. 更新状态
        document.status = next_state
        document.updated_at = _utcnow()

        # 3. 写入生命周期事件（不可变审计记录）
        event = KnowledgeLifecycleEvent(
            document_id=document.document_id,
            event_type="knowledge_status_changed",
            actor=actor,
            detail=reason or f"知识文档状态从 {before} 转移到 {next_state}",
            before_state=before,
            after_state=next_state,
        )
        self._session.add(event)

        await self._session.flush()
        return document

    async def record_import_event(
        self,
        document_id: str,
        actor: str,
        detail: str,
    ):
        """记录知识导入事件（不改变状态，仅写入审计记录）。

        Args:
            document_id: 文档 ID。
            actor: 操作者。
            detail: 导入详情。
        """
        from zhenhu.knowledge.models import KnowledgeLifecycleEvent

        event = KnowledgeLifecycleEvent(
            document_id=document_id,
            event_type="knowledge_imported",
            actor=actor,
            detail=detail,
            before_state=None,
            after_state="review_pending",
        )
        self._session.add(event)
        await self._session.flush()
        return event
