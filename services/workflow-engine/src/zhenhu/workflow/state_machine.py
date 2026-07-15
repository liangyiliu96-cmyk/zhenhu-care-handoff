"""病例状态机服务 —— 封装 zhenhu-contracts 的转移断言与持久化。

每次状态转移前调用 zhenhu_contracts.assert_case_transition 进行校验，
然后写入数据库并记录审计事件。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.contracts import assert_case_transition, ContractError
from zhenhu.workflow.models import AuditEvent, Case, RiskItem, TaskDraft


def _utcnow() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


class StateMachineError(Exception):
    """状态机业务异常。"""

    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


class CaseStateMachine:
    """病例状态机服务。

    封装所有合法的病例状态转移逻辑，每次转移：
    1. 调用 zhenhu_contracts.assert_case_transition 校验合法性。
    2. 更新 case.state 和 case.updated_at。
    3. 写入一条 AuditEvent。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _add_audit(
        self,
        case_id: str,
        actor: str,
        event_type: str,
        title: str,
        detail: str | None,
        before_state: str,
        after_state: str,
    ) -> AuditEvent:
        """写入审计事件。"""
        audit = AuditEvent(
            case_id=case_id,
            actor=actor,
            event_type=event_type,
            title=title,
            detail=detail,
            before_state=before_state,
            after_state=after_state,
            workflow_version="0.2.0",
        )
        self._session.add(audit)
        return audit

    async def transition(
        self,
        case: Case,
        next_state: str,
        actor: str,
        event_type: str,
        title: str,
        detail: str | None = None,
    ) -> Case:
        """执行状态转移。

        Args:
            case: 当前病例 ORM 实例。
            next_state: 目标状态。
            actor: 操作人角色。
            event_type: 事件类型（如 analysis_started, review_resolved）。
            title: 审计事件标题。
            detail: 审计事件详情（可选）。

        Returns:
            更新后的 Case 实例。

        Raises:
            StateMachineError: 当转移不合法时。
        """
        before = case.state

        # 1. 契约断言
        try:
            assert_case_transition(before, next_state)
        except ContractError as exc:
            raise StateMachineError(
                code="ILLEGAL_TRANSITION",
                message=str(exc),
                details={"current_state": before, "next_state": next_state},
            ) from exc

        # 2. 更新状态
        case.state = next_state
        case.updated_at = _utcnow()

        # 3. 审计
        await self._add_audit(
            case_id=case.case_id,
            actor=actor,
            event_type=event_type,
            title=title,
            detail=detail,
            before_state=before,
            after_state=next_state,
        )

        await self._session.flush()
        return case

    async def get_case_by_id(self, case_id: str) -> Case | None:
        """按 case_id 查询病例。"""
        result = await self._session.execute(
            select(Case).where(Case.case_id == case_id)
        )
        return result.scalar_one_or_none()

    async def get_risks_by_case_id(self, case_id: str) -> list[RiskItem]:
        """查询病例的所有风险项。"""
        result = await self._session.execute(
            select(RiskItem).where(RiskItem.case_id == case_id)
        )
        return list(result.scalars().all())

    async def get_pending_risks(self, case_id: str) -> list[RiskItem]:
        """查询病例中待审核的风险项。"""
        result = await self._session.execute(
            select(RiskItem).where(
                RiskItem.case_id == case_id, RiskItem.status == "pending"
            )
        )
        return list(result.scalars().all())

    async def all_risks_reviewed(self, case_id: str) -> bool:
        """检查病例的所有风险项是否已全部审核。"""
        pending = await self.get_pending_risks(case_id)
        return len(pending) == 0

    async def any_risk_rejected(self, case_id: str) -> bool:
        """检查病例是否有被驳回的风险项。"""
        result = await self._session.execute(
            select(RiskItem).where(
                RiskItem.case_id == case_id, RiskItem.status == "rejected"
            )
        )
        return result.scalar_one_or_none() is not None

    async def update_risk_status(
        self,
        risk: RiskItem,
        status: str,
        decision: str,
        note: str | None = None,
    ) -> RiskItem:
        """更新风险项审核状态。"""
        risk.status = status
        risk.decision = decision
        risk.decision_note = note
        await self._session.flush()
        return risk
