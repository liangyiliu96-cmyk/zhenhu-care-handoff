"""路由层 API 契约冒烟测试 — P2-4

使用 conftest.py 的 client fixture 对核心只读端点做 HTTP 层冒烟。
纯 GET 请求 + state_store 预设状态，验证 200 且不崩溃。
"""

import os
import sys
from pathlib import Path
import pytest

os.environ["SKIP_BRIDGE"] = "true"
os.environ["DOCTOR_AUTO_APPROVE"] = "true"
os.environ["GRAPH_MODE"] = "classic"
os.environ["APP_ENV"] = "dev"

PROJ_SRC = Path(__file__).resolve().parent.parent / "src"
if str(PROJ_SRC) not in sys.path:
    sys.path.insert(0, str(PROJ_SRC))


# ═══════════════════════════════════════════════════════════
# Fixture: 最小患者状态（所有可选字段设为非 None）
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def seeded_patient(isolated_state_store):
    """注入一个假患者，保证 GET 端点不因字段为 None 而崩。"""
    from zhenhu.inpatient.routes.state_store import set_state
    from zhenhu.inpatient.agent.graph import default_state

    state = default_state()
    pid = "smoke-test-001"
    state["patient_id"] = pid
    state["phase"] = "monitoring"
    state["disease_template"] = {"disease_id": "hypertension", "name": "高血压"}
    state["vital_signs"] = [
        {"systolic_mmhg": 140, "diastolic_mmhg": 90, "heart_rate": 78, "spo2": 98,
         "respiratory_rate": 16, "temperature": 36.5, "timestamp": "2026-07-17T10:00:00"}
    ]
    state["lab_results"] = [
        {"name": "K+", "value": 4.2, "unit": "mmol/L"},
        {"name": "Na+", "value": 140, "unit": "mmol/L"},
    ]
    state["risk_level"] = "medium"
    state["document_chain"] = ["intake_note", "risk_assessment", "daily_round_note"]
    state["handoff_items"] = [{"type": "medication", "content": "继续口服降压药"}]
    state["ddx_list"] = [
        {"diagnosis": "原发性高血压", "likelihood": "high", "key_findings": ["BP 140/90"]}
    ]
    state["round_count"] = 1
    state["news2_score"] = 2
    state["news2_risk"] = "low"
    state["qsofa_score"] = 0
    state["qsofa_risk"] = "low"
    state["clinical_alerts"] = ["[NEWS2=2] low风险"]
    # 关键：默认为 None 的字段需显式设为非 None 值，防止 dashboard 等端点崩
    state["nursing_records"] = None  # P2-4: 验证 dashboard None 防御
    state["nursing_alerts"] = None
    state["medication_adjustments"] = []
    state["medication_alerts"] = []
    state["latest_round"] = {"assessment": "稳定"}
    state["latest_lab_review"] = {"interpretation": "正常"}
    state["history_data"] = {"chief_complaint": "头痛头晕"}
    state["hpi_narrative"] = "患者于3天前无明显诱因出现头痛"
    state["pe_narrative"] = "生命体征平稳，心肺听诊未见异常"
    state["pe_data"] = {}
    state["ros_findings"] = {}
    state["discharge_orders"] = ""
    state["shift_summary"] = "患者体征稳定，继续当前治疗"

    set_state(pid, state)
    return pid


# ═══════════════════════════════════════════════════════════
# System endpoints
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_check(client):
    """GET /health → 200"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    """GET /metrics → 200"""
    resp = await client.get("/metrics")
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════
# Stateless read endpoints
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_patients(client):
    """GET /patients → 200"""
    resp = await client.get("/patients")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ward_overview(client):
    """GET /ward/overview → 200"""
    resp = await client.get("/ward/overview")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ward_priority_uses_deterministic_default(client, seeded_patient):
    """GET /ward/priority 默认不依赖 LLM，且返回可解释排序结果。"""
    resp = await client.get("/ward/priority")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["top_patients"]
    assert data["reasoning"] == "按告警、NEWS2、低氧和风险等级排序"


@pytest.mark.asyncio
async def test_ward_lab_summary_returns_abnormal_results(client, seeded_patient):
    """GET /ward/lab-summary → 可供病区看板显示的异常检验契约。"""
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    state = get_state(seeded_patient)
    assert state is not None
    state["disease_template"]["lab_reference"] = {"K+": {"low": 3.5, "high": 5.3}}
    state["lab_results"] = [{"name": "K+", "value": 6.1, "unit": "mmol/L"}]
    set_state(seeded_patient, state)

    resp = await client.get("/ward/lab-summary")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    lab = data["abnormal_labs"][0]
    assert lab["patient_id"] == seeded_patient
    assert lab["lab_name"] == "K+"
    assert lab["direction"] == "high"
    assert lab["ref_range"] == "3.5-5.3"


@pytest.mark.asyncio
async def test_pending_reviews(client):
    """GET /reviews/pending → 200"""
    resp = await client.get("/reviews/pending")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_monitoring_overdue(client, seeded_patient):
    """GET /monitoring/overdue → 可补录护理的并发安全契约。"""
    resp = await client.get("/monitoring/overdue")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    patient = data["patients"][0]
    assert patient["patient_id"] == seeded_patient
    assert isinstance(patient["state_version"], int)
    assert patient["department"] == "未知"
    assert isinstance(patient["alert_count"], int)


@pytest.mark.asyncio
async def test_nursing_records(client, seeded_patient):
    """GET /inpatient/{id}/nursing → 返回已保存的护理事实。"""
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    state = get_state(seeded_patient)
    assert state is not None
    state["nursing_records"] = [{"action": "翻身并完成皮肤评估", "intake_ml": 300, "output_ml": 200}]
    set_state(seeded_patient, state)

    response = await client.get(
        f"/inpatient/{seeded_patient}/nursing",
        headers={"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"patient_id": seeded_patient, "total": 1, "records": state["nursing_records"]}


@pytest.mark.asyncio
async def test_nurse_board(client):
    """GET /nurse/tasks → 200"""
    resp = await client.get("/nurse/tasks")
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════
# Stateful read endpoints (依赖 seeded_patient)
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_dashboard(client, seeded_patient):
    """GET /inpatient/{id}/dashboard → 200"""
    resp = await client.get(f"/inpatient/{seeded_patient}/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data or isinstance(data, dict)


@pytest.mark.asyncio
async def test_rounds(client, seeded_patient):
    """GET /inpatient/{id}/rounds → 200"""
    resp = await client.get(f"/inpatient/{seeded_patient}/rounds")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["rounds"] == [data["latest_soap"]]
    assert data["latest_soap"]["review_status"] == "requires_clinician_review"
    assert data["latest_soap"]["generation_source"] == "agent_generated_legacy"


@pytest.mark.asyncio
async def test_round_review_marks_a_legacy_summary_as_clinician_checked(client, seeded_patient):
    """旧摘要没有 round_number 时，也应能按 round_count 完成医生核对。"""
    from zhenhu.inpatient.routes.state_store import get_state

    version = get_state(seeded_patient)["state_version"]
    response = await client.post(
        f"/inpatient/{seeded_patient}/rounds/1/review",
        json={"expected_version": version, "comment": "已结合原始监测核对"},
        headers={"x-role": "doctor", "x-user-id": "doctor-rounds"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["round"]["round_number"] == 1
    assert data["round"]["review_status"] == "reviewed"
    assert get_state(seeded_patient)["latest_round"]["reviewed_by"] == "doctor-rounds"


@pytest.mark.asyncio
async def test_round_edit_preserves_agent_draft_and_records_doctor_revision(client, seeded_patient):
    """医生可修订生成内容，同时必须保留原始 Agent 草稿用于追溯。"""
    from zhenhu.inpatient.routes.state_store import get_state

    version = get_state(seeded_patient)["state_version"]
    response = await client.post(
        f"/inpatient/{seeded_patient}/rounds/1/edit",
        json={
            "subjective": "头晕较前缓解", "objective": "血压 135/82 mmHg", "assessment": "降压治疗有效", "plan": "继续晨晚血压监测", "attention": "警惕体位性低血压", "expected_version": version,
        },
        headers={"x-role": "doctor", "x-user-id": "doctor-rounds"},
    )

    assert response.status_code == 200
    edited = response.json()["data"]["round"]
    assert edited["doctor_revision"]["attention"] == "警惕体位性低血压"
    assert edited["agent_draft"]["assessment"] == "稳定"
    assert edited["edited_by"] == "doctor-rounds"


@pytest.mark.asyncio
async def test_round_generation_uses_the_agent_node_and_persists_a_new_round(client, seeded_patient, monkeypatch):
    """医生从工作台触发时，必须调用现有 daily_round 节点并写入临床事务。"""
    from zhenhu.inpatient.agent import nodes_monitoring
    from zhenhu.inpatient.routes.state_store import get_state

    async def deterministic_daily_round(state):
        round_number = int(state["round_count"]) + 1
        record = {
            "type": "daily_round",
            "format": "SOAP",
            "round_number": round_number,
            "timestamp": "2026-07-21T08:00:00+08:00",
            "subjective": {"chief_complaint": "症状缓解"},
            "objective": {"vital_signs_trend": "稳定"},
            "assessment": {"response_to_treatment": "治疗有效"},
            "plan": {"next_labs": "复查电解质"},
            "generation_source": "rule_based",
            "review_status": "requires_clinician_review",
            "ai_recommendation": "继续监测血压。",
            "citations": [],
        }
        return {
            "latest_round": record,
            "round_history": [*(state.get("round_history") or []), record],
            "round_count": round_number,
            "last_round_input_counts": {"vitals": 1, "labs": 2, "medications": 0},
        }

    monkeypatch.setattr(nodes_monitoring, "node_daily_round", deterministic_daily_round)
    version = get_state(seeded_patient)["state_version"]
    response = await client.post(
        f"/inpatient/{seeded_patient}/rounds/generate",
        json={"expected_version": version},
        headers={"x-role": "doctor", "x-user-id": "doctor-rounds"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["round"]["round_number"] == 2
    assert data["round"]["review_status"] == "requires_clinician_review"
    assert get_state(seeded_patient)["round_count"] == 2
    assert [record["round_number"] for record in get_state(seeded_patient)["round_history"]] == [1, 2]


@pytest.mark.asyncio
async def test_round_write_rejects_nurse_and_stale_state_version(client, seeded_patient):
    """生成查房仅允许医生写入，并遵守共享状态版本约束。"""
    from zhenhu.inpatient.routes.state_store import get_state

    version = get_state(seeded_patient)["state_version"]
    nurse_response = await client.post(
        f"/inpatient/{seeded_patient}/rounds/generate",
        json={"expected_version": version},
        headers={"x-role": "nurse", "x-user-id": "nurse-rounds"},
    )
    stale_response = await client.post(
        f"/inpatient/{seeded_patient}/rounds/1/review",
        json={"expected_version": version + 1},
        headers={"x-role": "doctor", "x-user-id": "doctor-rounds"},
    )

    assert nurse_response.status_code == 403
    assert stale_response.status_code == 409


@pytest.mark.asyncio
async def test_workflow_brief_generation_persists_a_doctor_confirmed_draft(client, seeded_patient, monkeypatch):
    """协同草稿可使用 LLM/RAG，但不得直接创建 MDT 或随访任务。"""
    from zhenhu.inpatient.agent import workflow_briefs
    from zhenhu.inpatient.routes.state_store import get_state

    async def fake_deep_invoke(*_args, **_kwargs):
        return {"response": "- 会前重点：复核异常检验\n- 讨论容量管理", "_rag_citations": [{"citation_id": "mdt-evidence"}]}

    monkeypatch.setattr(workflow_briefs, "deep_invoke", fake_deep_invoke)
    version = get_state(seeded_patient)["state_version"]
    response = await client.post(
        f"/inpatient/{seeded_patient}/workflow-briefs/mdt",
        json={"expected_version": version},
        headers={"x-role": "doctor", "x-user-id": "doctor-brief"},
    )

    assert response.status_code == 200
    brief = response.json()["data"]["brief"]
    assert brief["generation_source"] == "llm_rag"
    assert brief["citations"][0]["citation_id"] == "mdt-evidence"
    state = get_state(seeded_patient)
    assert state["workflow_briefs"]["mdt"]["content"].startswith("- 会前重点")
    assert state.get("mdt_requests", []) == []


@pytest.mark.asyncio
async def test_nurse_can_generate_follow_up_brief_but_not_mdt_or_transfer(client, seeded_patient, monkeypatch):
    """护士仅可生成低风险随访脚本，不能生成医生主导的协同草稿。"""
    from zhenhu.inpatient.agent import workflow_briefs
    from zhenhu.inpatient.routes.state_store import get_state

    async def fake_deep_invoke(*_args, **_kwargs):
        return {"response": "- 核对症状变化\n- 核对用药依从性", "_rag_citations": []}

    monkeypatch.setattr(workflow_briefs, "deep_invoke", fake_deep_invoke)
    version = get_state(seeded_patient)["state_version"]
    headers = {"x-role": "nurse", "x-user-id": "nurse-brief"}

    follow_up = await client.post(
        f"/inpatient/{seeded_patient}/workflow-briefs/follow_up",
        json={"expected_version": version},
        headers=headers,
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["data"]["brief"]["kind"] == "follow_up"
    assert get_state(seeded_patient)["workflow_briefs"]["follow_up"]["content"].startswith("- 核对症状")

    next_version = get_state(seeded_patient)["state_version"]
    for kind in ("mdt", "transfer"):
        response = await client.post(
            f"/inpatient/{seeded_patient}/workflow-briefs/{kind}",
            json={"expected_version": next_version},
            headers=headers,
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_scores(client, seeded_patient):
    """GET /inpatient/{id}/scores → 200"""
    resp = await client.get(f"/inpatient/{seeded_patient}/scores")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["news2"] == {
        "score": 2,
        "risk": "low",
        "status": "available",
        "basis": ["已由临床规则节点计算；当前状态未保存细项。"],
    }
    assert data["padua"]["status"] == "not_available"
    assert data["padua"]["reason"] == "尚未完成该评分的规则计算"


@pytest.mark.asyncio
async def test_template_detail_exposes_read_only_clinical_path(client):
    response = await client.get("/inpatient/templates/heart_failure")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["disease_id"] == "heart_failure"
    assert data["monitoring_interval_hours"] == 2
    assert data["discharge_criteria"]
    assert data["followup_questions"]


@pytest.mark.asyncio
async def test_vital_trends(client, seeded_patient):
    """GET /inpatient/{id}/vital-trends → 200"""
    resp = await client.get(f"/inpatient/{seeded_patient}/vital-trends")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_lab_trends(client, seeded_patient):
    """GET /inpatient/{id}/lab-trends → 200"""
    resp = await client.get(f"/inpatient/{seeded_patient}/lab-trends")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ward_workload(client):
    """GET /ward/workload → 200"""
    resp = await client.get("/ward/workload")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ward_overview_by_department(client):
    """GET /ward/overview?by=department → 200"""
    resp = await client.get("/ward/overview?by=department")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_department_checklist(client):
    """GET /nurse/department-checklist?department=骨科 → 200"""
    resp = await client.get("/nurse/department-checklist?department=骨科")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_nurse_tasks_by_department(client, seeded_patient):
    """GET /nurse/tasks?department=心内科 → 200"""
    resp = await client.get("/nurse/tasks?department=心内科")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_acknowledge_handoff(client, seeded_patient):
    """POST /inpatient/discharge/{id}/acknowledge-handoff → 200"""
    resp = await client.post(f"/inpatient/discharge/{seeded_patient}/acknowledge-handoff")
    assert resp.status_code == 200
    assert resp.json()["data"]["handoff_acknowledged"] is True

    from zhenhu.inpatient.routes.state_store import get_state

    version_after_first = get_state(seeded_patient)["state_version"]
    replay = await client.post(f"/inpatient/discharge/{seeded_patient}/acknowledge-handoff")

    assert replay.status_code == 200
    assert replay.json()["data"]["idempotent"] is True
    assert get_state(seeded_patient)["state_version"] == version_after_first


@pytest.mark.asyncio
async def test_lab_workflow_result_is_persisted(client, seeded_patient, monkeypatch):
    from zhenhu.inpatient.routes import monitoring
    from zhenhu.inpatient.routes.state_store import get_state

    class StubLoop:
        async def plan_turn(self, state):
            return {
                **state,
                "latest_lab_review": {"interpretation": "Potassium is within range."},
                "document_chain": [*state.get("document_chain", []), "lab_review"],
            }

    async def fake_commit(request, patient_id, state, **kwargs):
        return state.get("state_version", 0) + 1

    from zhenhu.inpatient.agent import loop as agent_loop

    from zhenhu.inpatient.services import clinical_facade

    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())
    monkeypatch.setattr(clinical_facade.clinical_workflow_facade, "commit", fake_commit)

    response = await client.post(
        f"/inpatient/monitoring/{seeded_patient}/labs",
        json={"name": "K", "value": 4.2},
        headers={"x-role": "nurse"},
    )

    assert response.status_code == 200
    state = get_state(seeded_patient)
    assert state["latest_lab_review"]["interpretation"] == "Potassium is within range."
    assert state["document_chain"][-1] == "lab_review"


@pytest.mark.asyncio
async def test_lab_workflow_persists_full_snapshot_when_review_is_pending(
    client, seeded_patient, monkeypatch,
):
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.routes import monitoring
    from zhenhu.inpatient.routes.state_store import get_state

    pending_snapshot = {
        **get_state(seeded_patient),
        "interrupt_pending": True,
        "pending_review": {
            "review_id": "review-lab-follow-up",
            "type": "med_confirm",
            "payload": {"reason": "abnormal result requires review"},
        },
        "lab_checkpoint_marker": "preserved",
    }

    class StubLoop:
        async def plan_turn(self, state):
            return {
                "status": "pending_review",
                "review_id": "review-lab-follow-up",
                "payload": pending_snapshot["pending_review"],
            }

        def pending_state_snapshot(self):
            return pending_snapshot

    async def fake_commit(request, patient_id, state, **kwargs):
        return state.get("state_version", 0) + 1

    from zhenhu.inpatient.services import clinical_facade

    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())
    monkeypatch.setattr(clinical_facade.clinical_workflow_facade, "commit", fake_commit)

    response = await client.post(
        f"/inpatient/monitoring/{seeded_patient}/labs",
        json={"name": "K", "value": 6.2},
        headers={"x-role": "nurse"},
    )

    assert response.status_code == 200
    persisted = get_state(seeded_patient)
    assert persisted["interrupt_pending"] is True
    assert persisted["pending_review"]["review_id"] == "review-lab-follow-up"
    assert persisted["lab_checkpoint_marker"] == "preserved"


@pytest.mark.asyncio
async def test_vitals_pending_review_returns_the_checkpoint_type(
    client, seeded_patient, monkeypatch,
):
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.agent import nodes_monitoring
    from zhenhu.inpatient.routes import monitoring

    pending_review = {
        "review_id": "review-vitals",
        "type": "med_confirm",
        "payload": {"reason": "requires confirmation"},
    }

    class StubLoop:
        async def plan_turn(self, state):
            self._state = state
            return {
                "status": "pending_review",
                "review_id": "review-vitals",
                "payload": pending_review,
            }

        def pending_state_snapshot(self):
            return {**self._state, "interrupt_pending": True, "pending_review": pending_review}

    async def fake_commit(request, patient_id, state, **kwargs):
        return state.get("state_version", 0) + 1

    async def approve_discharge(state):
        return {"discharge_decision": "approved"}

    from zhenhu.inpatient.services import clinical_facade

    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())
    monkeypatch.setattr(clinical_facade.clinical_workflow_facade, "commit", fake_commit)
    monkeypatch.setattr(nodes_monitoring, "node_monitoring", approve_discharge)

    response = await client.post(
        f"/inpatient/monitoring/{seeded_patient}/vitals",
        json={"heart_rate": 120},
        headers={"x-role": "nurse"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["review_type"] == "med_confirm"


@pytest.mark.asyncio
async def test_lab_discharge_continuation_reports_and_persists_pending_review(
    client, seeded_patient, monkeypatch,
):
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.routes import monitoring
    from zhenhu.inpatient.routes.state_store import get_state

    pending_snapshot = {
        **get_state(seeded_patient),
        "phase": "discharge",
        "interrupt_pending": True,
        "pending_review": {
            "review_id": "review-discharge-sign",
            "type": "discharge_sign",
            "payload": {"reason": "discharge needs signature"},
        },
        "discharge_checkpoint_marker": "preserved",
    }

    class StubLoop:
        def __init__(self):
            self.calls = 0

        async def plan_turn(self, state):
            self.calls += 1
            if self.calls == 1:
                return {**state, "phase": "discharge", "discharge_decision": "approved"}
            return {
                "status": "pending_review",
                "review_id": "review-discharge-sign",
                "payload": pending_snapshot["pending_review"],
            }

        def pending_state_snapshot(self):
            return pending_snapshot

    loop = StubLoop()

    async def fake_commit(request, patient_id, state, **kwargs):
        return state.get("state_version", 0) + 1

    from zhenhu.inpatient.services import clinical_facade

    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: loop)
    monkeypatch.setattr(clinical_facade.clinical_workflow_facade, "commit", fake_commit)

    response = await client.post(
        f"/inpatient/monitoring/{seeded_patient}/labs",
        json={"name": "K", "value": 4.2},
        headers={"x-role": "nurse"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["pending_review"] is True
    persisted = get_state(seeded_patient)
    assert persisted["interrupt_pending"] is True
    assert persisted["pending_review"]["review_id"] == "review-discharge-sign"
    assert persisted["discharge_checkpoint_marker"] == "preserved"


@pytest.mark.asyncio
async def test_review_persists_full_snapshot_when_next_review_is_pending(
    seeded_patient, monkeypatch,
):
    """审核恢复后再次卡点时，完整的新审核状态必须留在状态库中。"""
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.routes import review
    from zhenhu.inpatient.routes.route_schemas import ReviewRequest
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    state = get_state(seeded_patient)
    state["pending_review"] = {
        "review_id": "review-doctor-confirm",
        "type": "doctor_confirm",
        "payload": {},
    }
    state["interrupt_pending"] = True
    set_state(seeded_patient, state)

    next_pending = {
        **get_state(seeded_patient),
        "phase": "monitoring",
        "interrupt_pending": True,
        "pending_review": {
            "review_id": "review-med-confirm",
            "type": "med_confirm",
            "payload": {"reason": "dose adjustment requires confirmation"},
        },
        "next_checkpoint_marker": "preserved",
    }

    class StubLoop:
        async def plan_turn(self, state):
            return {
                "status": "pending_review",
                "review_id": "review-med-confirm",
                "payload": next_pending["pending_review"],
            }

        def pending_state_snapshot(self):
            return next_pending

    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())
    response = await review.submit_review(
        seeded_patient,
        ReviewRequest(review_type="doctor_confirm", decision="approved"),
    )

    assert response.data["status"] == "pending_review"
    persisted = get_state(seeded_patient)
    assert persisted["interrupt_pending"] is True
    assert persisted["pending_review"]["review_id"] == "review-med-confirm"
    assert persisted["next_checkpoint_marker"] == "preserved"


@pytest.mark.asyncio
async def test_review_rejects_a_decision_invalid_for_its_checkpoint(
    seeded_patient, monkeypatch,
):
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.routes import review
    from zhenhu.inpatient.routes.route_schemas import ReviewRequest
    from zhenhu.inpatient.routes.state_store import get_state

    class StubLoop:
        async def plan_turn(self, state):
            raise AssertionError("invalid review decisions must not run the graph")

    state_before = get_state(seeded_patient)
    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())

    response = await review.submit_review(
        seeded_patient,
        ReviewRequest(review_type="doctor_confirm", decision="signed"),
    )

    assert response.error.code == "INVALID_REVIEW_DECISION"
    assert get_state(seeded_patient) == state_before


@pytest.mark.asyncio
async def test_review_rejects_a_decision_for_a_different_pending_checkpoint(
    seeded_patient, monkeypatch,
):
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.routes import review
    from zhenhu.inpatient.routes.route_schemas import ReviewRequest
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    class StubLoop:
        async def plan_turn(self, state):
            raise AssertionError("a mismatched checkpoint must not run the graph")

    state = get_state(seeded_patient)
    state["interrupt_pending"] = True
    state["pending_review"] = {"review_id": "review-med", "type": "med_confirm", "payload": {}}
    set_state(seeded_patient, state)
    state_before = get_state(seeded_patient)
    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: StubLoop())

    response = await review.submit_review(
        seeded_patient,
        ReviewRequest(review_type="doctor_confirm", decision="approved"),
    )

    assert response.error.code == "REVIEW_TYPE_MISMATCH"
    assert get_state(seeded_patient) == state_before


@pytest.mark.asyncio
async def test_stateful_review_mode_is_rejected_without_mutating_patient_state(
    seeded_patient, monkeypatch,
):
    from zhenhu.inpatient.routes import review
    from zhenhu.inpatient.routes.route_schemas import ReviewRequest
    from zhenhu.inpatient.routes.state_store import get_state

    state_before = get_state(seeded_patient)
    monkeypatch.setattr(review, "get_graph_mode", lambda: "stateful")

    response = await review.submit_review(
        seeded_patient,
        ReviewRequest(review_type="doctor_confirm", decision="approved"),
    )

    assert response.error.code == "STATEFUL_GRAPH_MODE_UNAVAILABLE"
    assert get_state(seeded_patient) == state_before


@pytest.mark.asyncio
async def test_admission_persists_full_snapshot_when_initial_review_is_pending(
    client, isolated_state_store, monkeypatch,
):
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.routes import admission
    from zhenhu.inpatient.routes.state_store import get_state
    from zhenhu.inpatient.services import clinical_facade

    patient_id = "admission-pending-snapshot"

    class StubLoop:
        def __init__(self):
            self._snapshot = None

        def gen_input(self, strategy):
            return {"phase": "admission", "document_chain": []}

        async def plan_turn(self, state):
            self._snapshot = {
                **state,
                "interrupt_pending": True,
                "pending_review": {
                    "review_id": "review-admission",
                    "type": "doctor_confirm",
                    "payload": {"reason": "initial assessment requires review"},
                },
                "admission_checkpoint_marker": "preserved",
            }
            return {
                "status": "pending_review",
                "review_id": "review-admission",
                "payload": self._snapshot["pending_review"],
            }

        def pending_state_snapshot(self):
            return self._snapshot

    async def fake_commit(request, patient_id, state, **kwargs):
        return state.get("state_version", 0) + 1

    monkeypatch.setattr(admission, "get_patient_loop", lambda _: StubLoop())
    monkeypatch.setattr(clinical_facade.clinical_workflow_facade, "commit", fake_commit)

    response = await client.post(
        f"/inpatient/admissions?patient_id={patient_id}",
        headers={"x-role": "doctor"},
    )

    assert response.status_code == 200
    persisted = get_state(patient_id)
    assert persisted["interrupt_pending"] is True
    assert persisted["pending_review"]["review_id"] == "review-admission"
    assert persisted["admission_checkpoint_marker"] == "preserved"


@pytest.mark.asyncio
async def test_discharge_summary_completeness(client, seeded_patient):
    """GET /inpatient/{id}/discharge-summary → 200, 含 completeness"""
    # 先设 discharge_decision=approved 以便准入
    from zhenhu.inpatient.routes.state_store import get_state, set_state
    state = get_state(seeded_patient)
    if state:
        state["discharge_decision"] = "approved"
        set_state(seeded_patient, state)
    resp = await client.get(f"/inpatient/{seeded_patient}/discharge-summary?narrative=true")
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())
    assert "completeness" in data, f"No completeness in response: {list(data.keys())}"


@pytest.mark.asyncio
async def test_ai_summary(client):
    """GET /ward/ai-summary → 200"""
    resp = await client.get("/ward/ai-summary")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_shift_report(client):
    """GET /ward/shift-report → 200"""
    resp = await client.get("/ward/shift-report")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patient_timeline(client, seeded_patient):
    """GET /inpatient/{id}/timeline → 200"""
    resp = await client.get(f"/inpatient/{seeded_patient}/timeline")
    assert resp.status_code == 200
    assert "events" in resp.json().get("data", {})


@pytest.mark.asyncio
async def test_nurse_ai_priority(client, seeded_patient):
    """GET /nurse/ai-priority uses the deterministic fast path by default."""
    resp = await client.get("/nurse/ai-priority")
    assert resp.status_code == 200
    assert resp.json()["data"]["source"] == "rules"


@pytest.mark.asyncio
async def test_clinical_note_narrative(client, seeded_patient):
    """GET /inpatient/{id}/clinical-note?narrative=true → 200"""
    resp = await client.get(f"/inpatient/{seeded_patient}/clinical-note?narrative=true")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ward_insights(client):
    """GET /ward/insights → 200"""
    resp = await client.get("/ward/insights")
    assert resp.status_code == 200
