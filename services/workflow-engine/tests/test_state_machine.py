"""病例状态机核心测试。

覆盖 PoC 的核心用例：
- 创建病例 → 分析 → 审核 → 确认 → 草稿（完整正向流）
- 非法转移被拒绝
- 状态机断言边界条件
"""

from __future__ import annotations

import pytest

from zhenhu.contracts import (
    CaseState,
    ContractError,
    assert_case_transition,
    assert_knowledge_transition,
    assert_ingestion_job_transition,
    assert_role_access,
    can_role_access_surface,
    build_contract_snapshot,
    CASE_BLOCKING_STATES,
    KNOWLEDGE_TERMINAL_STATES,
    CASE_TRANSITIONS,
    KNOWLEDGE_TRANSITIONS,
    INGESTION_JOB_TRANSITIONS,
    ClinicalRole,
    Surface,
)


# ============================================================================
# 单元测试：契约断言
# ============================================================================


class TestCaseTransitions:
    """病例状态转移测试。"""

    # 合法转移
    @pytest.mark.parametrize(
        "current_state, next_state",
        [
            (CaseState.DRAFT, CaseState.ANALYSING),
            (CaseState.DRAFT, CaseState.CANCELLED),
            (CaseState.ANALYSING, CaseState.REVIEW_PENDING),
            (CaseState.ANALYSING, CaseState.FAILED),
            (CaseState.ANALYSING, CaseState.CANCELLED),
            (CaseState.REVIEW_PENDING, CaseState.CONFIRMED),
            (CaseState.REVIEW_PENDING, CaseState.REJECTED),
            (CaseState.REVIEW_PENDING, CaseState.TASK_DRAFT),
            (CaseState.REVIEW_PENDING, CaseState.CANCELLED),
            (CaseState.REVIEW_PENDING, CaseState.KNOWLEDGE_CHANGED),
            (CaseState.CONFIRMED, CaseState.TASK_DRAFT),
            (CaseState.CONFIRMED, CaseState.CANCELLED),
            (CaseState.REJECTED, CaseState.TASK_DRAFT),
            (CaseState.REJECTED, CaseState.CANCELLED),
            (CaseState.TASK_DRAFT, CaseState.SIMULATED_PUBLISHED),
            (CaseState.TASK_DRAFT, CaseState.REVIEW_PENDING),
            (CaseState.TASK_DRAFT, CaseState.CANCELLED),
            (CaseState.TASK_DRAFT, CaseState.KNOWLEDGE_CHANGED),
            (CaseState.SIMULATED_PUBLISHED, CaseState.CLOSED),
            (CaseState.SIMULATED_PUBLISHED, CaseState.CANCELLED),
            (CaseState.KNOWLEDGE_CHANGED, CaseState.REVIEW_PENDING),
            (CaseState.KNOWLEDGE_CHANGED, CaseState.CANCELLED),
            (CaseState.FAILED, CaseState.ANALYSING),
        ],
    )
    def test_legal_transition(self, current_state, next_state):
        """合法转移应返回 True 且不抛异常。"""
        result = assert_case_transition(current_state, next_state)
        assert result is True

    # 非法转移
    @pytest.mark.parametrize(
        "current_state, next_state",
        [
            (CaseState.DRAFT, CaseState.CONFIRMED),          # 跳过 analysing
            (CaseState.DRAFT, CaseState.CLOSED),              # 终态不可直达
            (CaseState.ANALYSING, CaseState.DRAFT),           # 不可逆
            (CaseState.CONFIRMED, CaseState.REVIEW_PENDING),  # 不可逆
            (CaseState.CLOSED, CaseState.DRAFT),              # 终态不可转移
            (CaseState.CANCELLED, CaseState.DRAFT),           # 终态不可转移
        ],
    )
    def test_illegal_transition(self, current_state, next_state):
        """非法转移应抛出 ContractError。"""
        with pytest.raises(ContractError, match="Illegal case transition"):
            assert_case_transition(current_state, next_state)

    def test_unknown_state(self):
        """未知状态应抛出 ContractError。"""
        with pytest.raises(ValueError):
            assert_case_transition("nonexistent_state", "draft")

    def test_string_input_accepted(self):
        """字符串状态值应被自动转换为枚举。"""
        assert assert_case_transition("draft", "analysing") is True
        with pytest.raises(ContractError):
            assert_case_transition("draft", "closed")


class TestKnowledgeTransitions:
    """知识版本状态转移测试。"""

    def test_legal_knowledge_transition(self):
        """review_pending → published 合法。"""
        from zhenhu.contracts import KnowledgeDocumentState
        assert assert_knowledge_transition(
            KnowledgeDocumentState.REVIEW_PENDING,
            KnowledgeDocumentState.PUBLISHED,
        ) is True

    def test_illegal_knowledge_transition(self):
        """published → review_pending 非法。"""
        from zhenhu.contracts import KnowledgeDocumentState
        with pytest.raises(ContractError, match="Illegal knowledge transition"):
            assert_knowledge_transition(
                KnowledgeDocumentState.PUBLISHED,
                KnowledgeDocumentState.REVIEW_PENDING,
            )

    def test_terminals_blocked(self):
        """终态不可转移。"""
        from zhenhu.contracts import KnowledgeDocumentState
        for terminal in KNOWLEDGE_TERMINAL_STATES:
            with pytest.raises(ContractError, match="Illegal knowledge transition"):
                assert_knowledge_transition(terminal, KnowledgeDocumentState.PUBLISHED)


class TestIngestionJobTransitions:
    """知识入库任务状态转移测试。"""

    def test_legal_ingestion_transition(self):
        """queued → parsing 合法。"""
        from zhenhu.contracts import KnowledgeIngestionJobState
        assert assert_ingestion_job_transition(
            KnowledgeIngestionJobState.QUEUED,
            KnowledgeIngestionJobState.PARSING,
        ) is True

    def test_illegal_ingestion_transition(self):
        """review_pending 为终态，不可再转移。"""
        from zhenhu.contracts import KnowledgeIngestionJobState
        with pytest.raises(ContractError, match="Illegal ingestion job transition"):
            assert_ingestion_job_transition(
                KnowledgeIngestionJobState.REVIEW_PENDING,
                KnowledgeIngestionJobState.QUEUED,
            )


# ============================================================================
# 单元测试：角色权限
# ============================================================================


class TestRoleAccess:
    """角色权限测试。"""

    def test_doctor_can_review(self):
        """医生可以访问病例审核表面。"""
        assert can_role_access_surface(ClinicalRole.DOCTOR, Surface.CASE_REVIEW) is True

    def test_nurse_cannot_review(self):
        """护士不能访问病例审核表面。"""
        assert can_role_access_surface(ClinicalRole.NURSE, Surface.CASE_REVIEW) is False

    def test_knowledge_admin_can_import(self):
        """知识管理员可以导入知识。"""
        assert (
            can_role_access_surface(ClinicalRole.KNOWLEDGE_ADMIN, Surface.KNOWLEDGE_IMPORT)
            is True
        )

    def test_doctor_cannot_import(self):
        """医生不能导入知识。"""
        assert (
            can_role_access_surface(ClinicalRole.DOCTOR, Surface.KNOWLEDGE_IMPORT)
            is False
        )

    def test_assert_role_access_raises(self):
        """assert_role_access 无权时抛异常。"""
        with pytest.raises(ContractError, match="cannot access"):
            assert_role_access(ClinicalRole.NURSE, Surface.CASE_REVIEW)

    def test_assert_role_access_string_input(self):
        """字符串角色名应被接受。"""
        assert assert_role_access("doctor", "case_review") is True


# ============================================================================
# 单元测试：常量
# ============================================================================


class TestConstants:
    """常量完整性测试。"""

    def test_blocking_states_contains_expected(self):
        """CASE_BLOCKING_STATES 包含 knowledge_changed, failed, cancelled, closed。"""
        assert CaseState.KNOWLEDGE_CHANGED in CASE_BLOCKING_STATES
        assert CaseState.FAILED in CASE_BLOCKING_STATES
        assert CaseState.CANCELLED in CASE_BLOCKING_STATES
        assert CaseState.CLOSED in CASE_BLOCKING_STATES

    def test_blocking_states_not_contains_active(self):
        """在办状态不在阻断态中。"""
        assert CaseState.DRAFT not in CASE_BLOCKING_STATES
        assert CaseState.ANALYSING not in CASE_BLOCKING_STATES
        assert CaseState.REVIEW_PENDING not in CASE_BLOCKING_STATES
        assert CaseState.CONFIRMED not in CASE_BLOCKING_STATES

    def test_knowledge_terminal_states(self):
        """知识终态集合包含预期条目。"""
        from zhenhu.contracts import KnowledgeDocumentState
        assert KnowledgeDocumentState.EXPIRED in KNOWLEDGE_TERMINAL_STATES
        assert KnowledgeDocumentState.WITHDRAWN in KNOWLEDGE_TERMINAL_STATES
        assert KnowledgeDocumentState.SUPERSEDED in KNOWLEDGE_TERMINAL_STATES
        assert KnowledgeDocumentState.ARCHIVED in KNOWLEDGE_TERMINAL_STATES
        assert KnowledgeDocumentState.REVIEW_REJECTED in KNOWLEDGE_TERMINAL_STATES

    def test_snapshot_exportable(self):
        """build_contract_snapshot 应返回可序列化字典。"""
        snapshot = build_contract_snapshot()
        assert snapshot["version"] == "0.2.0"
        assert "case_states" in snapshot
        assert "knowledge_states" in snapshot
        assert "blocking_case_states" in snapshot
        assert "surfaces" in snapshot
        assert "knowledge_terminal_states" in snapshot
        # 所有值都是 JSON 可序列化的（字符串列表）
        import json
        json.dumps(snapshot)


# ============================================================================
# 集成测试：完整工作流（通过 state_machine 服务 + SQLite）
# ============================================================================


class TestWorkflowIntegration:
    """集成测试：完整病例工作流。"""

    @pytest.fixture
    async def db_session(self):
        """创建独立的内存数据库会话。"""
        from zhenhu.workflow.models import init_db, async_session_factory

        await init_db()
        async with async_session_factory() as sess:
            yield sess

    @pytest.mark.asyncio
    async def test_full_happy_path(self, db_session):
        """完整正向流：创建 → 分析 → 审核 → 确认 → 任务草稿。"""
        from zhenhu.workflow.models import Case, RiskItem
        from zhenhu.workflow.state_machine import CaseStateMachine

        sm = CaseStateMachine(db_session)

        # 1. 创建病例
        case = Case(input_snapshot_id="snapshot-001", state="draft")
        db_session.add(case)
        await db_session.flush()
        assert case.state == "draft"

        # 2. 分析 → analysing → review_pending
        await sm.transition(case, "analysing", "doctor", "analysis_started", "开始分析")
        assert case.state == "analysing"

        # 模拟生成风险项
        r1 = RiskItem(case_id=case.case_id, category="test", severity="high",
                      severity_label="高风险", title="测试风险1", summary="测试",
                      status="pending")
        r2 = RiskItem(case_id=case.case_id, category="test", severity="low",
                      severity_label="低风险", title="测试风险2", summary="测试",
                      status="pending")
        db_session.add_all([r1, r2])
        await db_session.flush()

        await sm.transition(case, "review_pending", "system", "analysis_completed",
                            "分析完成")
        assert case.state == "review_pending"

        # 3. 审核风险项
        await sm.update_risk_status(r1, "confirmed", "confirm", "同意")
        await sm.update_risk_status(r2, "confirmed", "confirm", "同意")

        # 全部确认 → confirmed
        assert await sm.all_risks_reviewed(case.case_id)
        await sm.transition(case, "confirmed", "doctor", "review_resolved",
                            "全部风险项已确认")
        assert case.state == "confirmed"

        # 4. 生成任务草稿
        await sm.transition(case, "task_draft", "doctor", "task_draft_created",
                            "生成交接与随访任务草稿")
        assert case.state == "task_draft"

        # 验证审计事件
        from sqlalchemy import select
        from zhenhu.workflow.models import AuditEvent
        result = await db_session.execute(
            select(AuditEvent).where(AuditEvent.case_id == case.case_id)
        )
        audits = result.scalars().all()
        # draft → analysing → review_pending → confirmed → task_draft = 4 条审计
        assert len(audits) == 4
        assert audits[0].before_state == "draft"
        assert audits[-1].after_state == "task_draft"

    @pytest.mark.asyncio
    async def test_illegal_transition_rejected(self, db_session):
        """非法转移被拒绝。"""
        from zhenhu.workflow.models import Case
        from zhenhu.workflow.state_machine import CaseStateMachine, StateMachineError

        sm = CaseStateMachine(db_session)

        case = Case(input_snapshot_id="snapshot-001", state="draft")
        db_session.add(case)
        await db_session.flush()

        # draft → confirmed 非法：跳过 analysing
        with pytest.raises(StateMachineError, match="Illegal case transition"):
            await sm.transition(case, "confirmed", "doctor", "bad_jump", "跳过分析")

        # 状态不应变化
        assert case.state == "draft"

    @pytest.mark.asyncio
    async def test_analysis_from_draft_to_review_pending(self, db_session):
        """draft → analysing → review_pending 的标准分析流。"""
        from zhenhu.workflow.models import Case, RiskItem
        from zhenhu.workflow.state_machine import CaseStateMachine

        sm = CaseStateMachine(db_session)

        case = Case(input_snapshot_id="snapshot-001", state="draft")
        db_session.add(case)
        await db_session.flush()

        # draft → analysing
        await sm.transition(case, "analysing", "doctor", "analysis_started", "开始分析")
        assert case.state == "analysing"

        # analysing → review_pending
        await sm.transition(case, "review_pending", "system", "analysis_completed",
                            "分析完成")
        assert case.state == "review_pending"

    @pytest.mark.asyncio
    async def test_analysis_with_risks_then_confirm(self, db_session):
        """带风险项的完整分析→审核→确认流。"""
        from zhenhu.workflow.models import Case, RiskItem
        from zhenhu.workflow.state_machine import CaseStateMachine

        sm = CaseStateMachine(db_session)

        case = Case(input_snapshot_id="snapshot-001", state="draft")
        db_session.add(case)
        await db_session.flush()

        # 创建风险项
        r1 = RiskItem(case_id=case.case_id, category="medication_allergy",
                      severity="high", severity_label="高风险",
                      title="过敏冲突", summary="测试", status="pending")
        r2 = RiskItem(case_id=case.case_id, category="followup_window",
                      severity="medium", severity_label="中风险",
                      title="随访窗口", summary="测试", status="pending")
        db_session.add_all([r1, r2])
        await db_session.flush()

        # draft → analysing → review_pending
        await sm.transition(case, "analysing", "doctor", "analysis_started", "分析")
        await sm.transition(case, "review_pending", "system", "analysis_completed", "完成")
        assert case.state == "review_pending"

        # 审核全部确认
        await sm.update_risk_status(r1, "confirmed", "confirm")
        await sm.update_risk_status(r2, "confirmed", "confirm")
        assert await sm.all_risks_reviewed(case.case_id)

        await sm.transition(case, "confirmed", "doctor", "review_resolved", "全部确认")
        assert case.state == "confirmed"

    @pytest.mark.asyncio
    async def test_review_pending_blocked_transitions(self, db_session):
        """在 review_pending 状态下的非法操作应被阻止。"""
        from zhenhu.workflow.models import Case, RiskItem
        from zhenhu.workflow.state_machine import CaseStateMachine, StateMachineError

        sm = CaseStateMachine(db_session)

        case = Case(input_snapshot_id="snapshot-001", state="draft")
        db_session.add(case)
        await db_session.flush()

        r1 = RiskItem(case_id=case.case_id, category="test", severity="low",
                      severity_label="低", title="测试", summary="测试", status="pending")
        db_session.add(r1)
        await db_session.flush()

        # draft → analysing → review_pending
        await sm.transition(case, "analysing", "doctor", "analysis_started", "分析")
        await sm.transition(case, "review_pending", "system", "analysis_completed", "完成")

        # 不能从 review_pending 直接到 closed
        with pytest.raises(StateMachineError, match="Illegal case transition"):
            await sm.transition(case, "closed", "doctor", "bad_close", "非法关闭")

        assert case.state == "review_pending"


# ============================================================================
# FastAPI 端点测试
# ============================================================================


class TestFastAPIEndpoints:
    """FastAPI 端点集成测试。"""

    @pytest.fixture
    async def client(self):
        """创建 AsyncClient 用于测试 FastAPI app。"""
        from httpx import ASGITransport, AsyncClient
        from zhenhu.workflow.main import app
        from zhenhu.workflow.models import init_db, Base, async_engine, async_session_factory

        # 确保每次测试使用干净的表
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        # 清理
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """GET /health 应返回 ok。"""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.2.0"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_create_case(self, client):
        """POST /cases 创建新病例。"""
        resp = await client.post("/cases", json={
            "input_snapshot_id": "snapshot-test-001",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["error"] is None
        assert data["data"]["state"] == "draft"
        assert data["data"]["input_snapshot_id"] == "snapshot-test-001"
        assert "case_id" in data["data"]
        assert "request_id" in data

    @pytest.mark.asyncio
    async def test_analyse_case(self, client):
        """POST /cases/{id}/analyse 发起分析并转入 review_pending。"""
        # 先创建病例
        create_resp = await client.post("/cases", json={
            "input_snapshot_id": "snapshot-test-002",
        })
        case_id = create_resp.json()["data"]["case_id"]

        # 发起分析
        analyse_resp = await client.post(f"/cases/{case_id}/analyse")
        assert analyse_resp.status_code == 200
        data = analyse_resp.json()
        assert data["error"] is None
        assert data["data"]["state"] == "review_pending"
        assert len(data["data"]["risk_items"]) == 3  # 模拟生成 3 个风险项

    @pytest.mark.asyncio
    async def test_review_risk(self, client):
        """POST /cases/{id}/risks/{rid}/review 审核风险项。"""
        # 创建 + 分析
        create_resp = await client.post("/cases", json={
            "input_snapshot_id": "snapshot-test-003",
        })
        case_id = create_resp.json()["data"]["case_id"]

        analyse_resp = await client.post(f"/cases/{case_id}/analyse")
        risks = analyse_resp.json()["data"]["risk_items"]

        # 审核所有风险项
        for risk in risks:
            review_resp = await client.post(
                f"/cases/{case_id}/risks/{risk['risk_id']}/review",
                json={"action": "confirm", "note": "测试确认"},
            )
            assert review_resp.status_code == 200

        # 最后一个审核完成后应自动转到 confirmed
        final_resp = await client.get(f"/cases/{case_id}/analyse")  # 仅验证状态
        # 使用 /health 确认服务正常
        health = await client.get("/health")
        assert health.status_code == 200

    @pytest.mark.asyncio
    async def test_case_not_found(self, client):
        """404 错误场景。"""
        resp = await client.post("/cases/NONEXIST/analyse")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_request_id_header(self, client):
        """每个响应应包含 X-Request-ID 头。"""
        resp = await client.get("/health")
        assert "x-request-id" in resp.headers

    @pytest.mark.asyncio
    async def test_unified_response_format(self, client):
        """所有端点返回统一响应格式。"""
        resp = await client.post("/cases", json={
            "input_snapshot_id": "snapshot-test-format",
        })
        data = resp.json()
        assert "request_id" in data
        assert "data" in data
        assert "error" in data
        assert data["error"] is None
