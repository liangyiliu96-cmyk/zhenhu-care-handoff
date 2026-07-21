"""新端点 API 测试 — v1.1 Dashboard/Command/Discharge/Review edits

测试 v1.1 新增端点的关键路径:
  - GET  /inpatient/{id}/dashboard   (Dashboard)
  - POST /inpatient/{id}/command     (Command)
  - POST /inpatient/discharge/{id} (Discharge)
  - POST /inpatient/review/{id}      (Review edits)

运行方式:
    SKIP_BRIDGE=true python -m pytest tests/test_new_endpoints.py -v
"""

import os
import sys
from pathlib import Path

# ── 环境变量（必须在任何 zhenhu 导入前设置）──
os.environ["SKIP_BRIDGE"] = "true"
os.environ["DOCTOR_AUTO_APPROVE"] = "true"
os.environ["GRAPH_MODE"] = "classic"
os.environ["APP_ENV"] = "dev"

# 确保项目路径在 sys.path 中
PROJ_SRC = Path(__file__).resolve().parent.parent / "src"
if str(PROJ_SRC) not in sys.path:
    sys.path.insert(0, str(PROJ_SRC))

import pytest

from request_helpers import doctor_request

from zhenhu.inpatient.routes.state_store import get_state, set_state
from zhenhu.inpatient.agent.loop import cleanup_patient_loop


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def test_patient_state(isolated_state_store):
    """创建一个已完成入院的患者状态（monitoring 阶段）。"""
    state = {
        "patient_id": "test-d1-001",
        "phase": "monitoring",
        "disease_template": {
            "name": "高血压",
            "disease_id": "hypertension",
            "lab_reference": {
                "肌酐": {"low": 44, "high": 133},
            },
        },
        "vital_signs": [
            {
                "timestamp": "T1",
                "heart_rate": 78,
                "spo2": 98,
                "temperature": 36.5,
                "systolic_mmhg": 140,
                "diastolic_mmhg": 90,
            },
            {
                "timestamp": "T2",
                "heart_rate": 76,
                "spo2": 97,
                "temperature": 36.6,
                "systolic_mmhg": 138,
                "diastolic_mmhg": 88,
            },
        ],
        "lab_results": [
            {"name": "肌酐", "value": 132, "unit": "μmol/L"},
        ],
        "medication_adjustments": [
            {"drug": "氨氯地平", "dose": "5mg"},
        ],
        "handoff_items": [
            {"type": "medication", "content": "降压药方案"},
        ],
        "ddx_list": [
            {"diagnosis": "原发性高血压", "icd10": "I10", "likelihood": "high"},
            {"diagnosis": "继发性高血压", "icd10": "I15", "likelihood": "moderate"},
        ],
        "clinical_alerts": ["肌酐轻度升高"],
        "nursing_alerts": [],
        "interrupt_pending": False,
        "round_count": 5,
        "document_chain": [
            "intake_note", "history_note", "pe_note", "ddx_note",
            "med_rec_note", "risk_assessment", "doctor_confirm_auto",
            "daily_round_note", "nursing_note", "lab_review",
        ],
        "risk_level": "medium",
        "discharge_decision": None,
        "doctor_confirm_status": "approved",
        "med_confirm_status": None,
        "discharge_sign_status": None,
        "nursing_records": [{"action": "翻身"}],
        "nursing_status": "正常",
        "latest_round": {"assessment": "血压控制不佳"},
        "allergies": ["青霉素"],
        "hpi_narrative": "患者自述头痛3天",
        "pe_narrative": "BP 140/90，心率78",
        "history_data": {"chief_complaint": "头痛"},
        "pe_data": {"pe_narrative": "BP 140/90，心率78"},
        "pending_review": None,
        "ddx_reviewed": False,
        "discharge_reeval_after_rounds": None,
        "discharge_reject_history": [],
        "doctor_command": None,
        "doctor_command_reason": None,
        "doctor_command_context": None,
        "last_updated": "2026-01-01T00:00:00",
    }
    set_state("test-d1-001", state)
    yield state
    # 清理：移除患者 AgentLoop 实例和 asyncio.Lock
    cleanup_patient_loop("test-d1-001")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Dashboard 端点测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDashboardEndpoint:
    """GET /inpatient/{patient_id}/dashboard"""

    @pytest.mark.asyncio
    async def test_dashboard_returns_404_for_unknown_patient(self):
        """不存在患者返回 NOT_FOUND。"""
        from zhenhu.inpatient.routes.dashboard import get_dashboard
        result = await get_dashboard("nonexistent-patient", doctor_request())
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("error", {}).get("code") == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_dashboard_returns_full_response(self, test_patient_state):
        """存在患者返回完整 DashboardResponse 含 vital_trend/ddx/meds。"""
        from zhenhu.inpatient.routes.dashboard import get_dashboard
        result = await get_dashboard("test-d1-001", doctor_request())
        data = result.model_dump() if hasattr(result, 'model_dump') else result

        # 基础字段
        assert data.get("data", {}).get("patient_id") == "test-d1-001"
        assert data["data"]["phase"] == "monitoring"

        # vital_trend：最近体征趋势
        assert len(data["data"]["vital_trend"]) > 0
        assert "vital_trend_direction" in data["data"]

        # ddx_top3
        assert len(data["data"]["ddx_top3"]) > 0

        # medication_current
        assert len(data["data"]["medication_current"]) > 0

        # complication_alerts
        assert isinstance(data["data"]["complication_alerts"], list)
        assert "handoff_acknowledged" in data["data"]
        assert "patient_confirmation_status" in data["data"]
        assert "patient_confirmation_requirements" in data["data"]
        assert "bridge_status" in data["data"]

    @pytest.mark.asyncio
    async def test_dashboard_empty_state_response(self, isolated_state_store):
        """患者存在但无数据时返回空字段而非报错。"""
        from zhenhu.inpatient.routes.dashboard import get_dashboard
        minimal_state = {
            "patient_id": "test-d1-empty",
            "phase": "admission",
            "disease_template": {},
            "vital_signs": [],
            "lab_results": [],
            "medication_adjustments": [],
            "ddx_list": [],
            "clinical_alerts": [],
            "nursing_alerts": [],
            "handoff_items": [],
            "document_chain": [],
            "latest_round": None,
        }
        set_state("test-d1-empty", minimal_state)
        try:
            result = await get_dashboard("test-d1-empty", doctor_request())
            data = result.model_dump() if hasattr(result, 'model_dump') else result
            assert data.get("data", {}).get("patient_id") == "test-d1-empty"
            assert data["data"]["vital_trend"] == []
            assert data["data"]["ddx_top3"] == []
            assert data["data"]["medication_current"] == []
        finally:
            cleanup_patient_loop("test-d1-empty")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Command 端点测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommandEndpoint:
    """POST /inpatient/{patient_id}/command"""

    @pytest.mark.asyncio
    async def test_command_hold(self, test_patient_state):
        """hold 命令返回 status="held"。"""
        from zhenhu.inpatient.routes.command import submit_command
        from zhenhu.inpatient.routes.route_schemas import DoctorCommandRequest

        body = DoctorCommandRequest(action="hold", reason="等待会诊")
        result = await submit_command("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("data", {}).get("status") == "held"
        assert data["data"]["action"] == "hold"

    @pytest.mark.asyncio
    async def test_command_hold_preserves_reason(self, test_patient_state):
        """hold 命令响应中包含 reason 信息。"""
        from zhenhu.inpatient.routes.command import submit_command
        from zhenhu.inpatient.routes.route_schemas import DoctorCommandRequest

        body = DoctorCommandRequest(action="hold", reason="等待心内科会诊结果")
        result = await submit_command("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert "等待心内科会诊结果" in data.get("data", {}).get("message", "")

    @pytest.mark.asyncio
    async def test_command_resume(self, test_patient_state):
        """resume 命令正常执行（executed 或 pending_review 或 circuit_open）。"""
        from zhenhu.inpatient.routes.command import submit_command
        from zhenhu.inpatient.routes.route_schemas import DoctorCommandRequest

        body = DoctorCommandRequest(action="resume", reason="恢复监测")
        result = await submit_command("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("data", {}).get("status") in (
            "executed", "pending_review", "circuit_open"
        )

    @pytest.mark.asyncio
    async def test_command_consult(self, test_patient_state):
        """consult 命令记录会诊请求。"""
        from zhenhu.inpatient.routes.command import submit_command
        from zhenhu.inpatient.routes.route_schemas import DoctorCommandRequest

        body = DoctorCommandRequest(action="consult", target="心内科", reason="血压控制不佳")
        result = await submit_command("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("data", {}).get("status") == "executed"
        assert data["data"]["action"] == "consult"

        # 验证 state 中已记录会诊请求
        state = get_state("test-d1-001")
        alerts = state.get("clinical_alerts", [])
        assert any("会诊请求" in alert["message"] for alert in alerts)

    @pytest.mark.asyncio
    async def test_command_unknown_action_pydantic_rejected(self):
        """Literal 类型限制：无效 action 在 Pydantic 层被 ValidationError 拦截。"""
        from pydantic import ValidationError
        from zhenhu.inpatient.routes.route_schemas import DoctorCommandRequest

        with pytest.raises(ValidationError):
            DoctorCommandRequest(action="invalid_action", reason="test")

    @pytest.mark.asyncio
    async def test_command_missing_action_pydantic_rejected(self):
        """空/缺失 action 在 Pydantic 层被 ValidationError 拦截。"""
        from pydantic import ValidationError
        from zhenhu.inpatient.routes.route_schemas import DoctorCommandRequest

        with pytest.raises(ValidationError):
            DoctorCommandRequest(reason="no action provided")

    @pytest.mark.asyncio
    async def test_command_missing_reason_ok(self):
        """reason 可选字段，不提供应正常构造。"""
        from zhenhu.inpatient.routes.route_schemas import DoctorCommandRequest

        body = DoctorCommandRequest(action="consult", target="心内科")
        assert body.reason == ""

    @pytest.mark.asyncio
    async def test_command_not_found_patient(self):
        """不存在的患者返回 NOT_FOUND。"""
        from zhenhu.inpatient.routes.command import submit_command
        from zhenhu.inpatient.routes.route_schemas import DoctorCommandRequest

        body = DoctorCommandRequest(action="hold", reason="测试")
        result = await submit_command("nonexistent-cmd", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("error", {}).get("code") == "NOT_FOUND"
        cleanup_patient_loop("nonexistent-cmd")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Discharge 端点测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDischargeEndpoint:
    """POST /inpatient/discharge/{patient_id}"""

    @pytest.mark.asyncio
    async def test_discharge_initiate_not_found(self):
        """不存在患者返回 NOT_FOUND。"""
        from zhenhu.inpatient.routes.discharge import initiate_discharge
        result = await initiate_discharge("nonexistent-dc")
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("error", {}).get("code") == "NOT_FOUND"
        cleanup_patient_loop("nonexistent-dc")

    @pytest.mark.asyncio
    async def test_discharge_initiate_existing_patient(self, test_patient_state):
        """存在患者正常发起出院流程。"""
        from zhenhu.inpatient.routes.discharge import initiate_discharge
        result = await initiate_discharge("test-d1-001")
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("data", {}).get("patient_id") == "test-d1-001"

    @pytest.mark.asyncio
    async def test_discharge_initiate_includes_phase(self, test_patient_state):
        """正式出院端点返回流程字段并复用 command 事务。"""
        from zhenhu.inpatient.routes.discharge import initiate_discharge
        result = await initiate_discharge("test-d1-001")
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert "phase" in data.get("data", {})
        assert "handoff_items" in data.get("data", {})
        assert data["data"]["workflow_endpoint"].endswith("/discharge/test-d1-001")
        assert data["data"]["command_endpoint"].endswith("/command")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Review edits 端点测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestReviewEdits:
    """POST /inpatient/review/{patient_id}"""

    @pytest.mark.asyncio
    async def test_review_with_edits(self, test_patient_state):
        """提交含 edits 的审核（HPI 编辑）。"""
        from zhenhu.inpatient.routes.review import submit_review
        from zhenhu.inpatient.routes.route_schemas import ReviewRequest, EditPayload

        body = ReviewRequest(
            review_type="doctor_confirm",
            decision="approved",
            edits=EditPayload(hpi_narrative="医生修改后的HPI叙事"),
        )
        result = await submit_review("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("data", {}).get("decision") == "approved"

        # 确认 state 中的 HPI 已被更新
        state = get_state("test-d1-001")
        assert state is not None

    @pytest.mark.asyncio
    async def test_review_with_ddx_edits(self, test_patient_state):
        """提交含 DDx 编辑的审核。"""
        from zhenhu.inpatient.routes.review import submit_review
        from zhenhu.inpatient.routes.route_schemas import ReviewRequest, EditPayload, DDxEditItem

        body = ReviewRequest(
            review_type="doctor_confirm",
            decision="approved",
            edits=EditPayload(
                ddx_edits=[
                    DDxEditItem(
                        action="add",
                        item={"diagnosis": "肾性高血压", "icd10": "I15.1", "likelihood": "moderate"}
                    ),
                ]
            ),
        )
        result = await submit_review("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("data", {}).get("decision") == "approved"

    @pytest.mark.asyncio
    async def test_review_reject_with_reason(self, test_patient_state):
        """拒签 + reject_reason。"""
        from zhenhu.inpatient.routes.review import submit_review
        from zhenhu.inpatient.routes.route_schemas import ReviewRequest

        body = ReviewRequest(
            review_type="discharge_sign",
            decision="rejected",
            reject_reason="血压未稳定，暂缓出院",
        )
        result = await submit_review("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("data", {}).get("decision") == "rejected"

    @pytest.mark.asyncio
    async def test_review_handoff_edits(self, test_patient_state):
        """提交含 handoff_edits 的出院签字。"""
        from zhenhu.inpatient.routes.review import submit_review
        from zhenhu.inpatient.routes.route_schemas import ReviewRequest, HandoffEditItem

        body = ReviewRequest(
            review_type="discharge_sign",
            decision="signed",
            handoff_edits=[
                HandoffEditItem(
                    action="add",
                    item={"type": "medication", "content": "出院带药：氨氯地平5mg qd"}
                ),
            ],
        )
        result = await submit_review("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("data", {}).get("decision") == "signed"

    @pytest.mark.asyncio
    async def test_review_with_pe_edit(self, test_patient_state):
        """提交含 PE 编辑的审核。"""
        from zhenhu.inpatient.routes.review import submit_review
        from zhenhu.inpatient.routes.route_schemas import ReviewRequest, EditPayload

        body = ReviewRequest(
            review_type="doctor_confirm",
            decision="approved",
            edits=EditPayload(pe_narrative="医生修正：双肺呼吸音清，无啰音"),
        )
        result = await submit_review("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("data", {}).get("decision") == "approved"

    @pytest.mark.asyncio
    async def test_review_not_found_patient(self):
        """不存在的患者返回 NOT_FOUND。"""
        from zhenhu.inpatient.routes.review import submit_review
        from zhenhu.inpatient.routes.route_schemas import ReviewRequest

        body = ReviewRequest(review_type="doctor_confirm", decision="approved")
        result = await submit_review("nonexistent-review", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("error", {}).get("code") == "NOT_FOUND"
        cleanup_patient_loop("nonexistent-review")

    @pytest.mark.asyncio
    async def test_review_invalid_type(self, test_patient_state):
        """未知 review_type 返回 INVALID_REVIEW_TYPE。"""
        from zhenhu.inpatient.routes.review import submit_review
        from zhenhu.inpatient.routes.route_schemas import ReviewRequest

        body = ReviewRequest(review_type="unknown_type", decision="approved")
        result = await submit_review("test-d1-001", body)
        data = result.model_dump() if hasattr(result, 'model_dump') else result
        assert data.get("error", {}).get("code") == "INVALID_REVIEW_TYPE"
