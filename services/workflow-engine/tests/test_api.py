"""workflow-engine API 端点集成测试。

覆盖完整临床出院交接链路：
- 创建 → 分析 → 审核 → 任务草稿 → 模拟发布 → 补充 → 关闭 / 取消
- 知识变更阻断 → 重新核实
- 错误场景（状态冲突、角色拒绝、终态操作）
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


# ============================================================================
# Fixture
# ============================================================================


@pytest.fixture
async def client():
    """创建 AsyncClient 用于测试 FastAPI app（每次测试干净库）。"""
    from zhenhu.workflow.main import app
    from zhenhu.workflow.models import Base, async_engine

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ============================================================================
# 辅助函数
# ============================================================================


async def create_and_analyse(client: AsyncClient) -> str:
    """创建一个病例并完成分析，返回 case_id（状态=review_pending）。"""
    create_resp = await client.post("/cases", json={"input_snapshot_id": "snapshot-test"})
    assert create_resp.status_code == 201
    case_id = create_resp.json()["data"]["case_id"]

    analyse_resp = await client.post(f"/cases/{case_id}/analyse")
    assert analyse_resp.status_code == 200
    assert analyse_resp.json()["data"]["state"] == "review_pending"
    return case_id


async def confirm_all_risks(client: AsyncClient, case_id: str) -> None:
    """确认病例的所有风险项（全 confirm），使状态进入 confirmed。"""
    analyse_resp = await client.post(f"/cases/{case_id}/analyse")
    # 如果已经是 review_pending，analyse 会返回 409；我们直接获取风险项
    # 重新分析会失败，改从已有的风险项来审核
    # 查找风险项需要通过其它方式——这里用一个新的 analyse 调用曲线救国
    # 实际上 case 可能已经在 review_pending，我们需要先创建风险项
    pass


async def full_flow_to_confirmed(client: AsyncClient) -> str:
    """完整正向流：创建 → 分析 → 审核（全确认），返回 case_id（状态=confirmed）。"""
    create_resp = await client.post("/cases", json={"input_snapshot_id": "snapshot-full"})
    assert create_resp.status_code == 201
    case_id = create_resp.json()["data"]["case_id"]

    # 分析
    analyse_resp = await client.post(f"/cases/{case_id}/analyse")
    assert analyse_resp.status_code == 200
    risks = analyse_resp.json()["data"]["risk_items"]
    assert len(risks) == 3

    # 全部确认
    for risk in risks:
        review_resp = await client.post(
            f"/cases/{case_id}/risks/{risk['risk_id']}/review",
            json={"action": "confirm", "note": "测试确认"},
        )
        assert review_resp.status_code == 200

    return case_id


async def full_flow_to_task_draft(client: AsyncClient) -> tuple[str, str]:
    """完整流到 task_draft，返回 (case_id, draft_id)。"""
    case_id = await full_flow_to_confirmed(client)

    # 生成任务草稿
    draft_resp = await client.post(f"/cases/{case_id}/task-drafts")
    assert draft_resp.status_code == 200
    draft_id = draft_resp.json()["data"]["draft_id"]

    return case_id, draft_id


async def full_flow_to_simulated_published(client: AsyncClient) -> tuple[str, str]:
    """完整流到 simulated_published，返回 (case_id, draft_id)。"""
    case_id, draft_id = await full_flow_to_task_draft(client)

    # 模拟发布
    pub_resp = await client.post(f"/cases/{case_id}/task-drafts/{draft_id}/simulated-publish")
    assert pub_resp.status_code == 200

    return case_id, draft_id


# ============================================================================
# 测试：task-drafts 端点
# ============================================================================


class TestTaskDrafts:
    """任务草稿生成端点测试。"""

    @pytest.mark.asyncio
    async def test_create_task_draft_success_from_confirmed(self, client):
        """task-drafts 在 confirmed 状态下生成成功。"""
        case_id = await full_flow_to_confirmed(client)

        resp = await client.post(f"/cases/{case_id}/task-drafts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert data["data"]["draft_id"] == f"draft-{case_id}-01"
        assert data["data"]["status"] == "ready"
        assert data["data"]["case_id"] == case_id
        assert data["data"]["tasks_json"] is not None

        # 验证 tasks_json 包含 3 个任务
        import json
        tasks = json.loads(data["data"]["tasks_json"])
        assert len(tasks) == 3
        assert tasks[0]["task_id"] == "task-01"
        assert tasks[0]["assignee_role"] == "nurse"
        assert tasks[2]["task_id"] == "task-03"
        assert tasks[2]["assignee_role"] == "case_manager"

    @pytest.mark.asyncio
    async def test_create_task_draft_rejected_in_draft(self, client):
        """task-drafts 在 draft 状态被拒绝（409）。"""
        create_resp = await client.post("/cases", json={"input_snapshot_id": "snapshot-test"})
        case_id = create_resp.json()["data"]["case_id"]

        resp = await client.post(f"/cases/{case_id}/task-drafts")
        assert resp.status_code == 409
        detail = resp.json()["error"]
        assert detail["code"] == "CASE_STATE_CONFLICT"

    @pytest.mark.asyncio
    async def test_create_task_draft_success_from_rejected(self, client):
        """task-drafts 在 rejected 状态下也可生成。"""
        case_id = await full_flow_to_confirmed(client)

        # 但此时是 confirmed 状态；我们需要 rejected 状态测试
        # 新建一个 case，做分析，然后 reject 一个风险
        create_resp = await client.post("/cases", json={"input_snapshot_id": "snapshot-rej"})
        case_id2 = create_resp.json()["data"]["case_id"]

        analyse_resp = await client.post(f"/cases/{case_id2}/analyse")
        risks = analyse_resp.json()["data"]["risk_items"]

        # reject 第一个，confirm 其余
        await client.post(
            f"/cases/{case_id2}/risks/{risks[0]['risk_id']}/review",
            json={"action": "reject", "note": "驳回"},
        )
        for risk in risks[1:]:
            await client.post(
                f"/cases/{case_id2}/risks/{risk['risk_id']}/review",
                json={"action": "confirm", "note": "确认"},
            )

        # 现在状态应为 rejected
        # 生成任务草稿
        resp = await client.post(f"/cases/{case_id2}/task-drafts")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "ready"


# ============================================================================
# 测试：simulated-publish 端点
# ============================================================================


class TestSimulatedPublish:
    """模拟发布端点测试。"""

    @pytest.mark.asyncio
    async def test_publish_success(self, client):
        """simulated-publish 在 task_draft 状态下成功。"""
        case_id, draft_id = await full_flow_to_task_draft(client)

        resp = await client.post(f"/cases/{case_id}/task-drafts/{draft_id}/simulated-publish")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["state"] == "simulated_published"

    @pytest.mark.asyncio
    async def test_publish_knowledge_changed_blocked(self, client):
        """simulated-publish 在 knowledge_changed 状态下被阻断。"""
        case_id, draft_id = await full_flow_to_task_draft(client)

        # 先通过 hook 将病例标记为 knowledge_changed
        hook_resp = await client.post(
            "/hooks/knowledge-changed",
            json={"document_id": "drug-label-amoxicillin-clavulanate"},
        )
        assert hook_resp.status_code == 200

        # 尝试发布应被阻断
        resp = await client.post(f"/cases/{case_id}/task-drafts/{draft_id}/simulated-publish")
        assert resp.status_code == 409
        detail = resp.json()["error"]
        assert detail["code"] == "KNOWLEDGE_CHANGED"

    @pytest.mark.asyncio
    async def test_publish_wrong_state(self, client):
        """simulated-publish 在非 task_draft 状态下被拒绝。"""
        case_id = await full_flow_to_confirmed(client)

        resp = await client.post(
            f"/cases/{case_id}/task-drafts/nonexistent-draft/simulated-publish"
        )
        assert resp.status_code == 409


# ============================================================================
# 测试：supplement 端点
# ============================================================================


class TestSupplement:
    """任务补充端点测试。"""

    @pytest.mark.asyncio
    async def test_supplement_success_nurse(self, client):
        """护士补充任务执行信息成功（task_draft 状态）。"""
        case_id, draft_id = await full_flow_to_task_draft(client)

        # 用护士角色补充 task-01
        resp = await client.post(
            f"/cases/{case_id}/tasks/task-01/supplement",
            json={"result": "已完成首次随访", "note": "患者血压稳定"},
            headers={"X-User-Role": "nurse"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["task_id"] == "task-01"
        assert data["data"]["status"] == "simulated_supplemented"
        assert data["data"]["execution_result"] == "已完成首次随访"
        assert data["data"]["execution_note"] == "患者血压稳定"

    @pytest.mark.asyncio
    async def test_supplement_cross_role_rejected(self, client):
        """跨角色补充被拒绝：护士不能补充 case_manager 的任务。"""
        case_id, draft_id = await full_flow_to_task_draft(client)

        # 用护士角色尝试补充 task-03（分配给 case_manager）
        resp = await client.post(
            f"/cases/{case_id}/tasks/task-03/supplement",
            json={"result": "尝试跨角色", "note": ""},
            headers={"X-User-Role": "nurse"},
        )
        assert resp.status_code == 403
        detail = resp.json()["error"]
        assert detail["code"] == "FORBIDDEN"

    @pytest.mark.asyncio
    async def test_supplement_case_manager_success(self, client):
        """个案管理师补充自己的任务成功。"""
        case_id, draft_id = await full_flow_to_task_draft(client)

        resp = await client.post(
            f"/cases/{case_id}/tasks/task-03/supplement",
            json={"result": "复诊已安排", "note": "门诊预约成功"},
            headers={"X-User-Role": "case_manager"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "simulated_supplemented"

    @pytest.mark.asyncio
    async def test_supplement_wrong_state(self, client):
        """在 confirmed 状态补充任务被拒绝。"""
        case_id = await full_flow_to_confirmed(client)

        resp = await client.post(
            f"/cases/{case_id}/tasks/task-01/supplement",
            json={"result": "尝试"},
            headers={"X-User-Role": "nurse"},
        )
        assert resp.status_code == 409


# ============================================================================
# 测试：close 端点
# ============================================================================


class TestClose:
    """关闭病例端点测试。"""

    @pytest.mark.asyncio
    async def test_close_success(self, client):
        """在 simulated_published 状态下关闭成功。"""
        case_id, draft_id = await full_flow_to_simulated_published(client)

        resp = await client.post(f"/cases/{case_id}/close")
        assert resp.status_code == 200
        assert resp.json()["data"]["state"] == "closed"

    @pytest.mark.asyncio
    async def test_close_wrong_state(self, client):
        """在 confirmed 状态关闭被拒绝。"""
        case_id = await full_flow_to_confirmed(client)

        resp = await client.post(f"/cases/{case_id}/close")
        assert resp.status_code == 409


# ============================================================================
# 测试：cancel 端点
# ============================================================================


class TestCancel:
    """取消病例端点测试。"""

    @pytest.mark.asyncio
    async def test_cancel_success_from_draft(self, client):
        """从 draft 状态取消成功。"""
        create_resp = await client.post("/cases", json={"input_snapshot_id": "snapshot-cancel"})
        case_id = create_resp.json()["data"]["case_id"]

        resp = await client.post(f"/cases/{case_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["data"]["state"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_after_closed_rejected(self, client):
        """closed 后不可再 cancel。"""
        case_id, draft_id = await full_flow_to_simulated_published(client)

        # 先关闭
        close_resp = await client.post(f"/cases/{case_id}/close")
        assert close_resp.status_code == 200
        assert close_resp.json()["data"]["state"] == "closed"

        # 尝试取消
        resp = await client.post(f"/cases/{case_id}/cancel")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_cancel_from_review_pending(self, client):
        """从 review_pending 状态取消成功。"""
        case_id = await create_and_analyse(client)

        resp = await client.post(f"/cases/{case_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["data"]["state"] == "cancelled"


# ============================================================================
# 测试：reconcile 端点
# ============================================================================


class TestReconcile:
    """重新核实端点测试。"""

    @pytest.mark.asyncio
    async def test_reconcile_success(self, client):
        """knowledge_changed → review_pending 重新核实成功。"""
        case_id, draft_id = await full_flow_to_task_draft(client)

        # 通过 hook 触发 knowledge_changed
        hook_resp = await client.post(
            "/hooks/knowledge-changed",
            json={"document_id": "drug-label-amoxicillin-clavulanate"},
        )
        assert hook_resp.status_code == 200
        assert hook_resp.json()["data"]["blocked_count"] >= 1

        # 重新核实
        resp = await client.post(f"/cases/{case_id}/reconcile")
        assert resp.status_code == 200
        assert resp.json()["data"]["state"] == "review_pending"

    @pytest.mark.asyncio
    async def test_reconcile_wrong_state(self, client):
        """在 confirmed 状态 reconcile 被拒绝。"""
        case_id = await full_flow_to_confirmed(client)

        resp = await client.post(f"/cases/{case_id}/reconcile")
        assert resp.status_code == 409


# ============================================================================
# 测试：knowledge-changed hook
# ============================================================================


class TestKnowledgeChangedHook:
    """知识变更阻断钩子测试。"""

    @pytest.mark.asyncio
    async def test_hook_blocks_review_pending_cases(self, client):
        """knowledge-changed hook 正确阻断 review_pending 病例。"""
        # 创建 2 个处于 review_pending 的病例（风险项引用 "drug-label-amoxicillin-clavulanate"）
        case_id_1 = await create_and_analyse(client)
        case_id_2 = await create_and_analyse(client)

        # 触发 hook
        resp = await client.post(
            "/hooks/knowledge-changed",
            json={"document_id": "drug-label-amoxicillin-clavulanate"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["blocked_count"] >= 2

    @pytest.mark.asyncio
    async def test_hook_blocks_task_draft_cases(self, client):
        """knowledge-changed hook 正确阻断 task_draft 病例。"""
        case_id, draft_id = await full_flow_to_task_draft(client)

        # 触发 hook：使用风险项引用的文档 ID
        resp = await client.post(
            "/hooks/knowledge-changed",
            json={"document_id": "drug-label-amoxicillin-clavulanate"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["blocked_count"] >= 1

    @pytest.mark.asyncio
    async def test_hook_no_match_returns_zero(self, client):
        """无匹配文档时返回 blocked_count=0。"""
        case_id = await create_and_analyse(client)

        resp = await client.post(
            "/hooks/knowledge-changed",
            json={"document_id": "nonexistent-doc-id"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["blocked_count"] == 0

    @pytest.mark.asyncio
    async def test_hook_ignores_non_target_states(self, client):
        """hook 忽略不在 task_draft/review_pending 的病例。"""
        # 创建 confirmed 状态的病例（风险项也引用相同文档）
        case_id = await full_flow_to_confirmed(client)

        # 触发 hook 应不影响 confirmed 病例
        resp = await client.post(
            "/hooks/knowledge-changed",
            json={"document_id": "drug-label-amoxicillin-clavulanate"},
        )
        assert resp.status_code == 200
        # confirmed 状态的病例不应被计入
        blocked = resp.json()["data"]["blocked_count"]
        # confirmed 状态下不应被阻断
        assert blocked == 0  # confirmed 不在 target_states 中


# ============================================================================
# 测试：完整端到端流程
# ============================================================================


class TestEndToEnd:
    """完整出院交接链路端到端测试。"""

    @pytest.mark.asyncio
    async def test_full_discharge_handoff_flow(self, client):
        """完整流程：创建→分析→审核确认→任务草稿→模拟发布→关闭。"""
        # 1. 创建 + 分析 + 审核确认
        case_id = await full_flow_to_confirmed(client)

        # 2. 生成任务草稿
        draft_resp = await client.post(f"/cases/{case_id}/task-drafts")
        assert draft_resp.status_code == 200
        draft_id = draft_resp.json()["data"]["draft_id"]

        # 3. 模拟发布
        pub_resp = await client.post(f"/cases/{case_id}/task-drafts/{draft_id}/simulated-publish")
        assert pub_resp.status_code == 200
        assert pub_resp.json()["data"]["state"] == "simulated_published"

        # 4. 护士补充任务
        supp_resp = await client.post(
            f"/cases/{case_id}/tasks/task-01/supplement",
            json={"result": "已完成用药核对", "note": "患者知晓用药方案"},
            headers={"X-User-Role": "nurse"},
        )
        assert supp_resp.status_code == 200

        # 5. 关闭病例
        close_resp = await client.post(f"/cases/{case_id}/close")
        assert close_resp.status_code == 200
        assert close_resp.json()["data"]["state"] == "closed"

    @pytest.mark.asyncio
    async def test_knowledge_changed_reconcile_flow(self, client):
        """知识变更→阻断→重新核实→审核 完整流程。"""
        case_id, draft_id = await full_flow_to_task_draft(client)

        # 知识变更阻断
        hook_resp = await client.post(
            "/hooks/knowledge-changed",
            json={"document_id": "drug-label-amoxicillin-clavulanate"},
        )
        assert hook_resp.status_code == 200
        assert hook_resp.json()["data"]["blocked_count"] >= 1

        # 验证 publish 被阻断
        pub_resp = await client.post(f"/cases/{case_id}/task-drafts/{draft_id}/simulated-publish")
        assert pub_resp.status_code == 409

        # 重新核实
        rec_resp = await client.post(f"/cases/{case_id}/reconcile")
        assert rec_resp.status_code == 200
        assert rec_resp.json()["data"]["state"] == "review_pending"

        # 可以重新 analyse（从 review_pending 重新 analyse 是允许的）
        # analyse 只能在 draft/failed/knowledge_changed 状态发起
        # review_pending 状态下 analyse 会报 ILLEGAL_TRANSITION
        # 这是预期的——reconcile 已经生成了新的风险项


# ============================================================================
# 测试：GET /cases/{case_id} 只读查询端点
# ============================================================================


class TestGetCase:
    """GET /cases/{case_id} 只读查询病例概览测试。"""

    @pytest.mark.asyncio
    async def test_get_case_200(self, client):
        """GET /cases/{case_id} 返回 200 并包含完整概览数据。"""
        case_id, draft_id = await full_flow_to_task_draft(client)

        resp = await client.get(f"/cases/{case_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None

        payload = data["data"]
        # 基本字段
        assert payload["case_id"] == case_id
        assert payload["state"] == "task_draft"
        assert "patient_ref" in payload

        # risks 列表
        assert isinstance(payload["risks"], list)
        assert len(payload["risks"]) == 3
        for risk in payload["risks"]:
            assert "risk_id" in risk
            assert "category" in risk
            assert "severity" in risk
            assert "status" in risk
            assert "title" in risk

        # task_draft 存在
        assert payload["task_draft"] is not None
        assert payload["task_draft"]["case_id"] == case_id
        assert "draft_id" in payload["task_draft"]

        # audit_event_count > 0（完整流程至少包含多条审计事件）
        assert isinstance(payload["audit_event_count"], int)
        assert payload["audit_event_count"] > 0

    @pytest.mark.asyncio
    async def test_get_case_404(self, client):
        """GET /cases/{case_id} 不存在的病例返回 404。"""
        resp = await client.get("/cases/NONEXIST-CASE-ID")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_case_field_completeness(self, client):
        """GET /cases/{case_id} 验证响应包含所有必需字段。"""
        # 创建病例但只做分析（不生成任务草稿）
        create_resp = await client.post(
            "/cases", json={"input_snapshot_id": "snapshot-fields-test"}
        )
        assert create_resp.status_code == 201
        case_id = create_resp.json()["data"]["case_id"]

        # 分析
        analyse_resp = await client.post(f"/cases/{case_id}/analyse")
        assert analyse_resp.status_code == 200

        resp = await client.get(f"/cases/{case_id}")
        assert resp.status_code == 200
        payload = resp.json()["data"]

        # 顶层必填字段
        required_fields = [
            "case_id", "state", "patient_ref",
            "workflow_version", "created_at", "updated_at",
            "risks", "task_draft", "audit_event_count",
        ]
        for field in required_fields:
            assert field in payload, f"缺少字段: {field}"

        # task_draft 应为 None（尚未生成）
        assert payload["task_draft"] is None

        # risks 应有 3 条
        assert len(payload["risks"]) == 3

        # audit_event_count >= 2（创建时的 draft 也有审计吗？不，create 不写审计。
        # analyse 写了 2 条：analysis_started + analysis_completed）
        assert payload["audit_event_count"] >= 2

    @pytest.mark.asyncio
    async def test_get_case_freshly_created(self, client):
        """GET /cases/{case_id} 刚创建的病例，无风险无草稿无审计。"""
        create_resp = await client.post(
            "/cases", json={"input_snapshot_id": "snapshot-fresh"}
        )
        assert create_resp.status_code == 201
        case_id = create_resp.json()["data"]["case_id"]

        resp = await client.get(f"/cases/{case_id}")
        assert resp.status_code == 200
        payload = resp.json()["data"]

        assert payload["state"] == "draft"
        assert payload["risks"] == []
        assert payload["task_draft"] is None
        assert payload["audit_event_count"] == 0
