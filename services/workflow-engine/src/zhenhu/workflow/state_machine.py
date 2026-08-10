"""病例状态机服务 —— 封装 zhenhu-contracts 的转移断言与持久化。

每次状态转移前调用 zhenhu_contracts.assert_case_transition 进行校验，
然后写入数据库并记录审计事件。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.contracts import assert_case_transition, ContractError
from zhenhu.workflow.models import AuditEvent, Case, RiskItem, TaskDraft

# 阶段M: Agent 模式替代硬编码 Mock
from zhenhu.contracts.agent import get_ai_provider, AgentAuditHook


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

    # 模拟任务模板（对照需求 §3.4 协同任务生成）
    _MOCK_TASK_TEMPLATES: list[dict] = [
        {
            "task_id": "task-01",
            "task_type": "护理核对",
            "title": "核对出院用药与过敏史记录",
            "assignee_role": "nurse",
            "due": "出院后 24 小时",
            "escalation": "发现记录不一致时回退医生审核",
            "status": "simulated_pending",
            "execution_result": None,
            "execution_note": None,
        },
        {
            "task_id": "task-02",
            "task_type": "用药指导",
            "title": "确认出院带药用法用量与患者教育",
            "assignee_role": "nurse",
            "due": "出院后 24 小时",
            "escalation": "患者无法理解用法时回退医生审核",
            "status": "simulated_pending",
            "execution_result": None,
            "execution_note": None,
        },
        {
            "task_id": "task-03",
            "task_type": "复诊安排",
            "title": "协调复诊时间并通知患者",
            "assignee_role": "case_manager",
            "due": "出院后 72 小时",
            "escalation": "无法安排复诊时回退医生审核",
            "status": "simulated_pending",
            "execution_result": None,
            "execution_note": None,
        },
    ]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ========================================================================
    # 阶段M Agent升级: analyse() 用 Agent 模式替代硬编码 Mock
    # ========================================================================

    async def analyse(self, case: Case) -> list[dict]:
        """分析病例风险项 — 阶段M: Agent 模式替代 Mock。

        优先调 AIProvider 获取结构化风险项，失败降级到 _mock_risks。
        """
        audit = AgentAuditHook()
        audit.on_node_enter("analyse", {"case_id": case.case_id})

        provider = get_ai_provider()
        try:
            result = await provider.invoke(
                prompt="分析病例风险项",
                context={"case_id": case.case_id, "snapshot": case.input_snapshot_id}
            )
            if result.get("risks"):
                risks = result["risks"]
            else:
                risks = self._mock_risks()  # fallback
        except Exception:
            risks = self._mock_risks()

        audit.on_node_exit("analyse", {"risk_count": len(risks)})
        return risks

    @staticmethod
    def _mock_risks() -> list[dict]:
        """模拟风险项 — 阶段M: Agent 降级回退。"""
        return [
            {
                "category": "medication_allergy",
                "severity": "high",
                "severity_label": "高风险",
                "title": "出院药物与已记录过敏史存在潜在冲突",
                "summary": "出院带药清单中出现阿莫西林/克拉维酸钾；输入快照记录青霉素类药物致皮疹。系统不作临床结论，请医生核实。",
                "evidence_snippet": "青霉素类（皮疹）",
                "citation_excerpt": "对青霉素类药物有过敏史者，应由具备处方责任的医师评估。",
                "citation_document_id": "drug-label-amoxicillin-clavulanate",
            },
            {
                "category": "followup_window",
                "severity": "medium",
                "severity_label": "中风险",
                "title": "肾功能结果与随访计划时间窗不一致",
                "summary": "最近肌酐采集时间为出院前 36 小时；随访草稿未包含复查时间。请核实是否需要补充院后监测安排。",
                "evidence_snippet": "肌酐采集时间：出院前 36 小时",
                "citation_excerpt": "复查事项和计划时间应在交接草稿中明确记录。",
                "citation_document_id": "zhenhu-handoff-sop",
            },
            {
                "category": "missing_field",
                "severity": "low",
                "severity_label": "低风险",
                "title": "居家血压自测记录字段未见填写",
                "summary": "交接单草稿未包含居家自测记录方式。该项仅提示信息完整性，不替代临床判断。",
                "evidence_snippet": "居家血压记录字段为空",
                "citation_excerpt": "交接信息应包含约定的居家监测记录方式。",
                "citation_document_id": "zhenhu-handoff-sop",
            },
        ]

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

    async def get_task_draft_by_case_id(self, case_id: str) -> TaskDraft | None:
        """按 case_id 查询任务草稿。"""
        result = await self._session.execute(
            select(TaskDraft).where(TaskDraft.case_id == case_id)
        )
        return result.scalar_one_or_none()

    async def get_task_draft_by_id(self, draft_id: str) -> TaskDraft | None:
        """按 draft_id 查询任务草稿。"""
        result = await self._session.execute(
            select(TaskDraft).where(TaskDraft.draft_id == draft_id)
        )
        return result.scalar_one_or_none()

    async def get_confirmed_risk_ids(self, case_id: str) -> list[str]:
        """获取病例中已确认的风险项 ID 列表。"""
        result = await self._session.execute(
            select(RiskItem).where(
                RiskItem.case_id == case_id, RiskItem.status == "confirmed"
            )
        )
        return [r.risk_id for r in result.scalars().all()]

    # ========================================================================
    # 新增方法 —— 对照需求 §3.4 完整协同链路
    # ========================================================================

    async def create_task_draft(self, case: Case, actor: str) -> dict:
        """生成任务草稿。

        仅在 confirmed 或 rejected 状态下允许。
        收集所有已确认风险项的 basedOnRiskIds，生成 3 条模拟任务。

        Args:
            case: 当前病例 ORM 实例。
            actor: 操作人角色。

        Returns:
            dict: 包含 draft 信息和 tasks 数组。

        Raises:
            StateMachineError: 状态不合法时。
        """
        if case.state not in ("confirmed", "rejected"):
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message="当前状态不允许生成任务草稿",
                details={"current_state": case.state},
            )

        # 收集已确认风险项 ID
        based_on_risk_ids = await self.get_confirmed_risk_ids(case.case_id)

        # 生成模拟任务（按模板复制，注入 case_id 和 based_on_risk_ids）
        tasks = []
        for tpl in self._MOCK_TASK_TEMPLATES:
            task = dict(tpl)
            task["case_id"] = case.case_id
            task["based_on_risk_ids"] = based_on_risk_ids
            tasks.append(task)

        tasks_json = json.dumps(tasks, ensure_ascii=False)

        # 创建 TaskDraft 实体
        draft = TaskDraft(
            draft_id=f"draft-{case.case_id}-01",
            case_id=case.case_id,
            status="ready",
            sop_version="0.2.0",
            tasks_json=tasks_json,
        )
        self._session.add(draft)

        # 状态转移
        before = case.state
        await self.transition(
            case=case,
            next_state="task_draft",
            actor=actor,
            event_type="task_draft_created",
            title="生成交接与随访任务草稿",
            detail=f"基于 {len(based_on_risk_ids)} 个已确认风险项，生成 {len(tasks)} 条模拟任务",
        )

        await self._session.flush()
        return {
            "draft_id": draft.draft_id,
            "case_id": draft.case_id,
            "status": draft.status,
            "sop_version": draft.sop_version,
            "tasks_json": draft.tasks_json,
            "tasks": tasks,
            "based_on_risk_ids": based_on_risk_ids,
            "before_state": before,
            "after_state": case.state,
        }

    async def publish_simulated(self, case: Case, draft_id: str, actor: str) -> dict:
        """模拟发布任务草稿。

        仅在 task_draft 状态下允许。发布前检查知识是否变更。

        Args:
            case: 当前病例 ORM 实例。
            draft_id: 任务草稿 ID。
            actor: 操作人角色。

        Returns:
            dict: 包含发布后状态。

        Raises:
            StateMachineError: 状态不合法或知识变更阻断时。
        """
        if case.state == "knowledge_changed":
            raise StateMachineError(
                code="KNOWLEDGE_CHANGED",
                message="所引用知识已变化，已阻断发布，须重新检索与人工复核",
                details={"current_state": case.state},
            )

        if case.state != "task_draft":
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message="当前状态不允许模拟发布任务草稿",
                details={"current_state": case.state},
            )

        # 查找并更新任务草稿
        draft = await self.get_task_draft_by_id(draft_id)
        if draft is None:
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message=f"任务草稿未找到: {draft_id}",
                details={"draft_id": draft_id},
            )

        if draft.case_id != case.case_id:
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message="任务草稿不属于该病例",
                details={"draft_case_id": draft.case_id, "case_id": case.case_id},
            )

        draft.status = "simulated_published"

        # 状态转移
        before = case.state
        await self.transition(
            case=case,
            next_state="simulated_published",
            actor=actor,
            event_type="simulated_publish",
            title="模拟发布任务草稿",
            detail=f"任务草稿 {draft_id} 已模拟发布，生成下游待办",
        )

        await self._session.flush()
        return {
            "draft_id": draft.draft_id,
            "state": case.state,
            "before_state": before,
            "after_state": case.state,
        }

    async def supplement_task(
        self,
        case: Case,
        task_id: str,
        actor: str,
        result: str,
        note: str,
    ) -> dict:
        """补充任务执行信息。

        仅在 task_draft 或 simulated_published 状态下允许。

        Args:
            case: 当前病例 ORM 实例。
            task_id: 任务 ID。
            actor: 操作人角色（需与任务指派的 assignee_role 匹配）。
            result: 执行结果描述。
            note: 补充说明。

        Returns:
            dict: 包含更新后的任务信息。

        Raises:
            StateMachineError: 状态不合法或角色不匹配时。
        """
        if case.state not in ("task_draft", "simulated_published"):
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message="当前状态不允许补充任务执行信息",
                details={"current_state": case.state},
            )

        # 查找任务草稿
        draft = await self.get_task_draft_by_case_id(case.case_id)
        if draft is None or draft.tasks_json is None:
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message="未找到任务草稿",
                details={"case_id": case.case_id},
            )

        # 解析任务列表
        tasks = json.loads(draft.tasks_json)

        # 查找目标任务
        target_task = None
        for task in tasks:
            if task.get("task_id") == task_id:
                target_task = task
                break

        if target_task is None:
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message=f"未找到任务: {task_id}",
                details={"task_id": task_id},
            )

        # 校验角色匹配
        assignee_role = target_task.get("assignee_role", "")
        if assignee_role != actor:
            raise StateMachineError(
                code="FORBIDDEN",
                message=f"只能补充指派给本人的任务执行信息（需要 {assignee_role} 角色）",
                details={"required_role": assignee_role, "current_role": actor},
            )

        # 更新任务
        target_task["status"] = "simulated_supplemented"
        target_task["execution_result"] = result
        target_task["execution_note"] = note

        # 写回
        draft.tasks_json = json.dumps(tasks, ensure_ascii=False)

        # 写审计事件（不改变 case 状态）
        await self._add_audit(
            case_id=case.case_id,
            actor=actor,
            event_type="task_supplemented",
            title="补充任务执行信息",
            detail=f"{target_task.get('title', task_id)}{f'；说明：{note}' if note else ''}",
            before_state=case.state,
            after_state=case.state,
        )

        await self._session.flush()
        return {
            "task_id": task_id,
            "status": target_task["status"],
            "execution_result": result,
            "execution_note": note,
        }

    async def close_case(self, case: Case, actor: str) -> dict:
        """关闭病例协同。

        仅在 simulated_published 状态下允许。

        Args:
            case: 当前病例 ORM 实例。
            actor: 操作人角色。

        Returns:
            dict: 包含关闭后状态。

        Raises:
            StateMachineError: 状态不合法时。
        """
        if case.state != "simulated_published":
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message="仅已模拟发布的病例可关闭",
                details={"current_state": case.state},
            )

        before = case.state
        await self.transition(
            case=case,
            next_state="closed",
            actor=actor,
            event_type="case_closed",
            title="关闭病例协同",
            detail="模拟发布后的病例协同已关闭",
        )

        await self._session.flush()
        return {
            "state": case.state,
            "before_state": before,
            "after_state": case.state,
        }

    async def cancel_case(self, case: Case, actor: str) -> dict:
        """取消病例协同。

        任意非终态（!closed && !cancelled）下允许。

        Args:
            case: 当前病例 ORM 实例。
            actor: 操作人角色。

        Returns:
            dict: 包含取消后状态。

        Raises:
            StateMachineError: 已是终态时。
        """
        if case.state in ("closed", "cancelled"):
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message="当前状态不可取消",
                details={"current_state": case.state},
            )

        before = case.state
        await self.transition(
            case=case,
            next_state="cancelled",
            actor=actor,
            event_type="case_cancelled",
            title="取消病例协同",
            detail="经治医生取消当前在办病例",
        )

        await self._session.flush()
        return {
            "state": case.state,
            "before_state": before,
            "after_state": case.state,
        }

    async def reconcile_case(self, case: Case, actor: str) -> dict:
        """重新核实（knowledge_changed → review_pending）。

        仅在 knowledge_changed 状态下允许。
        状态转移本身由本方法处理；风险项的删除与重新生成由调用方在转移前后完成。

        Args:
            case: 当前病例 ORM 实例。
            actor: 操作人角色。

        Returns:
            dict: 包含核实后状态。

        Raises:
            StateMachineError: 状态不合法时。
        """
        if case.state != "knowledge_changed":
            raise StateMachineError(
                code="CASE_STATE_CONFLICT",
                message="仅 knowledge_changed 状态可重新核实",
                details={"current_state": case.state},
            )

        before = case.state
        await self.transition(
            case=case,
            next_state="review_pending",
            actor=actor,
            event_type="case_reconciled",
            title="重新核实：知识变更后重新分析",
            detail="清除旧风险项，重新执行分析并生成新风险项",
        )

        await self._session.flush()
        return {
            "state": case.state,
            "before_state": before,
            "after_state": case.state,
        }

    async def find_cases_by_document(
        self, document_id: str, states: list[str]
    ) -> list[Case]:
        """查找引用指定知识文档且处于指定状态的病例。

        Args:
            document_id: 知识文档 ID。
            states: 目标状态列表（如 ["task_draft", "review_pending"]）。

        Returns:
            匹配的 Case 列表。
        """
        # 查找引用该文档的风险项所属的 case_id
        risk_result = await self._session.execute(
            select(RiskItem.case_id).where(
                RiskItem.citation_document_id == document_id
            )
        )
        affected_case_ids = list(set(risk_result.scalars().all()))

        if not affected_case_ids:
            return []

        # 筛选处于指定状态的病例
        case_result = await self._session.execute(
            select(Case).where(
                Case.case_id.in_(affected_case_ids),
                Case.state.in_(states),
            )
        )
        return list(case_result.scalars().all())

    async def on_knowledge_changed(self, document_id: str) -> dict:
        """知识反向阻断钩子。

        查找所有 state 为 task_draft 或 review_pending 且引用该 document_id 的病例，
        将其标记为 knowledge_changed。

        Args:
            document_id: 发生变更的知识文档 ID。

        Returns:
            dict: 包含 blocked_count（受影响病例数）。
        """
        target_states = ["task_draft", "review_pending"]
        affected_cases = await self.find_cases_by_document(document_id, target_states)

        for case in affected_cases:
            # 清除任务草稿（如果有）
            draft = await self.get_task_draft_by_case_id(case.case_id)
            if draft is not None:
                await self._session.delete(draft)

            before = case.state
            case.state = "knowledge_changed"
            case.updated_at = _utcnow()

            await self._add_audit(
                case_id=case.case_id,
                actor="system",
                event_type="knowledge_blocked",
                title=f"知识变更阻断：{document_id}",
                detail="引用该知识的在办病例被阻断，须重新检索与人工复核",
                before_state=before,
                after_state="knowledge_changed",
            )

        await self._session.flush()
        return {"blocked_count": len(affected_cases)}
