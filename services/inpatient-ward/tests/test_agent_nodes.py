"""Agent 节点独立测试。合并迁入。"""
import pytest, asyncio
# 合并迁入: 替换 app.src.zhenhu 路径
from zhenhu.inpatient.agent.nodes import (
    node_admission, node_triage, node_monitoring, node_discharge,
    node_handoff, node_doctor_review, node_patient_confirm,
    node_daily_round, node_medication_adjust, node_lab_review, node_transfer,
    node_medication_reconciliation,
)
from zhenhu.inpatient.agent.nodes_clinical import node_nursing, node_shift_summary
from zhenhu.inpatient.agent.graph import (
    after_discharge_bridge,
    after_doctor_confirm,
    after_doctor_discharge_sign,
)

def test_node_admission_initializes():
    state = {}
    result = asyncio.run(node_admission(state))
    assert result["phase"] == "admission"

def test_node_triage_risk_low_on_empty():
    result = asyncio.run(node_triage({"vital_signs": [], "disease_template": {}}))
    assert result["risk_level"] == "low"

def test_node_triage_risk_high_on_many_factors():
    """P0-5修复: 使用真实风险因子名+患者数据匹配≥3个因子 → high"""
    result = asyncio.run(node_triage({
        "vital_signs": [{"bp": "120/80"}],
        "disease_template": {"risk_factors": ["age>60", "smoking", "obesity", "diabetes_comorbid"]},
        "patient_data": {"age": 65, "bmi": 30},
        "patient_history": {"smoking": True, "comorbidities": ["diabetes"]},
    }))
    assert result["risk_level"] == "high"
    assert len(result.get("triage_matched_factors", [])) >= 3

def test_node_monitoring_triggers_discharge():
    """P0-1修复: 需提供discharge_criteria并全部满足才approved"""
    tpl = {"discharge_criteria": [
        {"condition": "bp_stable_24h", "description": "血压24小时稳定"},
        {"condition": "vital_signs_stable", "description": "生命体征稳定≥3条"},
    ]}
    vs = [
        {"blood_pressure_systolic": 130, "blood_pressure_diastolic": 80},
        {"blood_pressure_systolic": 128, "blood_pressure_diastolic": 78},
        {"blood_pressure_systolic": 132, "blood_pressure_diastolic": 82},
    ]
    result = asyncio.run(node_monitoring({
        "disease_template": tpl,
        "vital_signs": vs,
    }))
    assert result["discharge_decision"] == "approved"
    assert result["discharge_criteria_check"]["all_met"] is True
    assert result["discharge_criteria_check"]["met_count"] == result["discharge_criteria_check"]["total_count"]
    assert all(item["met"] for item in result["discharge_criteria_check"]["details"])

def test_node_handoff_generates_items(monkeypatch):
    """交接节点：模板指令作为 base，不依赖 LLM；mock 掉增强调用确保确定性。"""
    async def _noop_llm(_provider, _prompt, **_kwargs):
        return {"source_type": "source_none", "personalized_notes": []}

    monkeypatch.setattr(
        "zhenhu.inpatient.agent.nodes_handoff.safe_llm_invoke",
        _noop_llm,
    )
    tpl = {"handoff_instructions":[{"type":"medication","content":"请按医嘱规律服用降压药物"}]}
    result = asyncio.run(node_handoff({"disease_template": tpl}))
    assert len(result["handoff_items"]) >= 1
    assert result["handoff_items"][0]["type"] == "medication"
    assert result["handoff_items"][0]["source"] == "disease_template"

def test_node_handoff_empty_template(monkeypatch):
    """空模板不生成任何交接事项。"""
    async def _noop_llm(_provider, _prompt, **_kwargs):
        return {"source_type": "source_none", "personalized_notes": []}

    monkeypatch.setattr(
        "zhenhu.inpatient.agent.nodes_handoff.safe_llm_invoke",
        _noop_llm,
    )
    result = asyncio.run(node_handoff({"disease_template": {}}))
    assert result["handoff_items"] == []

def test_node_doctor_review_approves():
    result = asyncio.run(node_doctor_review({}))
    assert result["discharge_decision"] == "approved"
    assert result["interrupt_pending"] == False


def test_node_doctor_review_all_accept():
    """2项全accept应approved。"""
    state = {"handoff_items": [
        {"type": "medication", "content": "降压药方案"},
        {"type": "monitoring", "content": "每日测血压"},
    ]}
    result = asyncio.run(node_doctor_review(state))
    assert result["discharge_decision"] == "approved"
    assert result["phase"] == "review"
    for item in result["handoff_items"]:
        assert item["review_action"] == "accept"


def test_node_doctor_review_pending_stops_automatic_review(monkeypatch):
    """外部审核未完成时不得回退为自动规则审批。"""
    async def pending_review(items):
        return {
            "action": "pending",
            "pending_review": {"review_id": "review-handoff", "status": "pending"},
        }

    monkeypatch.setattr(
        "zhenhu.inpatient.agent.interrupt.request_doctor_review",
        pending_review,
    )
    state = {"handoff_items": [
        {"type": "medication", "content": "降压药方案"},
        {"type": "monitoring", "content": "每日测血压"},
        {"type": "followup", "content": "7天内复诊"},
    ]}
    result = asyncio.run(node_doctor_review(state))
    assert result["interrupt_pending"] is True
    assert result["pending_review"]["type"] == "discharge_sign"
    assert result["pending_review"]["payload"]["handoff_items"] == state["handoff_items"]


def test_node_triage_mdt_on_high_risk():
    """高危(>=3风险因子)自动触发MDT。P0-5修复: 使用真实因子名+患者数据"""
    state = {
        "vital_signs": [{"bp": "120/80"}],
        "disease_template": {
            "risk_factors": ["age>60", "smoking", "obesity", "diabetes_comorbid"],
            "mdt_roles": ["心内科", "营养师", "社区医生"],
        },
        "patient_data": {"age": 65, "bmi": 30},
        "patient_history": {"smoking": True, "comorbidities": ["diabetes"]},
    }
    result = asyncio.run(node_triage(state))
    assert result["risk_level"] == "high"
    assert result["mdt_required"] is True
    assert "心内科" in result["mdt_roles"]
    assert result["mdt_mode"] == "async-review"
    assert "高危" in result["mdt_reason"]


def test_node_triage_no_mdt_on_medium_risk():
    """中危不触发MDT。P0-5修复: 使用真实因子名+患者数据匹配2个因子"""
    state = {
        "vital_signs": [{"bp": "120/80"}],
        "disease_template": {"risk_factors": ["age>60", "smoking"]},
        "patient_data": {"age": 65},
        "patient_history": {"smoking": True},
    }
    result = asyncio.run(node_triage(state))
    assert result["risk_level"] == "medium"
    assert "mdt_required" not in result

def test_node_patient_confirm_waits_for_real_teach_back():
    result = asyncio.run(node_patient_confirm({
        "discharge_sign_status": "signed",
        "document_chain": ["discharge_bridge"],
        "handoff_acknowledged": False,
        "education_records": [],
    }))
    assert result["patient_confirmation_status"] == "pending"
    assert set(result["patient_confirmation_requirements"]) == {
        "handoff_acknowledgement", "teach_back",
    }
    assert "confirm_note" not in result.get("document_chain", [])


def test_node_patient_confirm_uses_persisted_recipient_evidence():
    result = asyncio.run(node_patient_confirm({
        "discharge_sign_status": "signed",
        "document_chain": ["handoff_note", "discharge_bridge"],
        "handoff_acknowledged": True,
        "education_records": [{
            "id": "education-1",
            "topic": "用药指导",
            "recipient": "patient",
            "teach_back": "每天早晨服药，不能自行停药",
            "acknowledged": True,
            "acknowledged_at": "2026-07-20T08:00:00+00:00",
        }],
    }))
    assert result["patient_confirmation_status"] == "confirmed"
    assert result["patient_confirmation_evidence"][0]["education_record_id"] == "education-1"
    assert "confirm_note" in result["document_chain"]


def test_node_discharge_checks_criteria():
    """缺少交接事项时不得伪造桥接成功。"""
    tpl = {"discharge_criteria": ["bp_stable_24h", "medication_confirmed"]}
    result = asyncio.run(node_discharge({"disease_template": tpl, "vital_signs": []}))
    assert result["phase"] == "discharge"
    assert result["discharge_decision"] == "bridge_failed"
    assert result["bridge_error"] == "handoff_items_missing"


def test_node_discharge_runs_bridge_after_handoff(monkeypatch):
    """签字后的出院副作用成功后写入可追踪文档事件。"""
    async def create_case(patient_id, handoff_items, template):
        return {"status": "ok", "case_id": "case-1"}

    async def search_knowledge(query):
        return []

    async def patient_summary(patient_id):
        return {"patient_id": patient_id}

    monkeypatch.setattr(
        "zhenhu.inpatient.agent.nodes_handoff._create_zhenhu_case",
        create_case,
    )
    monkeypatch.setattr(
        "zhenhu.inpatient.hooks.zhenhu_bridge.bridge_search_knowledge",
        search_knowledge,
    )
    monkeypatch.setattr(
        "zhenhu.inpatient.hooks.zhenhu_bridge.bridge_patient_summary",
        patient_summary,
    )
    tpl = {
        "discharge_criteria": ["bp_stable_24h"],
        "handoff_instructions": [{"type": "medication", "content": "氨氯地平片 5mg 每日一次"}],
    }
    vs = [{}, {}, {}, {}, {}, {}]
    result = asyncio.run(node_discharge({
        "disease_template": tpl,
        "vital_signs": vs,
        "patient_id": "patient-1",
        "handoff_items": tpl["handoff_instructions"],
        "document_chain": ["discharge_signed"],
    }))
    assert result["phase"] == "discharge"
    assert result["discharge_decision"] == "approved"
    assert "discharge_bridge" in result["document_chain"]


def test_node_discharge_idempotent_guard():
    """桥接完成标记存在时不得重复创建外部病例。"""
    result = asyncio.run(node_discharge({
        "handoff_items": [{"type": "medication", "content": "跳过"}],
        "document_chain": ["discharge_bridge"],
    }))
    assert result.get("phase") == "discharge"


def test_node_admission_loads_template():
    """入院时加载病种模板。"""
    result = asyncio.run(node_admission({"patient_id": "test-001", "disease_template": {}}))
    assert "disease_template" in result
    assert result["disease_template"] != {}
    assert "intake_note" in result["document_chain"]


# ── 阶段E: 补齐缺失临床步骤 ──


def test_node_daily_round_adds_to_chain():
    """查房节点将查房笔记写入document_chain。"""
    result = asyncio.run(node_daily_round({"vital_signs": [], "lab_results": [], "medication_adjustments": [], "document_chain": [], "round_count": 0}))
    assert "daily_round_note" in result["document_chain"]
    assert result["round_count"] == 1
    assert result["round_history"] == [result["latest_round"]]
    assert result["latest_round"]["generation_source"] in {"rule_based", "llm_assisted"}
    assert result["latest_round"]["review_status"] == "requires_clinician_review"
    assert "daily_round_agent" in result["latest_round"]["source_nodes"]


def test_node_daily_round_is_incremental_not_single_use():
    base = {
        "vital_signs": [{"heart_rate": 80}],
        "lab_results": [],
        "medication_adjustments": [],
        "document_chain": ["daily_round_note"],
        "round_count": 1,
        "last_round_input_counts": {"vitals": 1, "labs": 0, "medications": 0},
    }
    assert asyncio.run(node_daily_round(base)) == {}
    updated = {**base, "vital_signs": [*base["vital_signs"], {"heart_rate": 88}]}
    result = asyncio.run(node_daily_round(updated))
    assert result["round_count"] == 2
    assert result["round_history"][-1]["round_number"] == 2
    assert result["latest_round"]["round_number"] == 2


def test_node_medication_adjust_on_alert():
    """体征突破警报阈值时触发用药调整。"""
    tpl = {"vital_signs": [{"name": "spo2", "alert_below": 90}]}
    result = asyncio.run(node_medication_adjust({"disease_template": tpl, "vital_signs": [{"spo2": 85}], "medication_adjustments": []}))
    assert len(result["medication_alerts"]) == 1


def test_node_medication_adjust_no_alert():
    """体征正常时不触发用药警报。"""
    tpl = {"vital_signs": [{"name": "spo2", "alert_below": 90}]}
    result = asyncio.run(node_medication_adjust({"disease_template": tpl, "vital_signs": [{"spo2": 95}], "medication_adjustments": []}))
    assert len(result["medication_alerts"]) == 0


def test_node_lab_review():
    """检验结果审阅节点正确标记新检验。"""
    result = asyncio.run(node_lab_review({"lab_results": [{"name": "K", "value": 5.8}], "reviewed_labs": [], "document_chain": []}))
    assert len(result["lab_findings"]) == 1
    assert "lab_review" in result["document_chain"]


def test_node_lab_review_processes_later_identical_results():
    first = {"name": "K", "value": 5.8, "unit": "mmol/L"}
    state = {
        "lab_results": [first, dict(first)],
        "reviewed_labs": [first],
        "reviewed_lab_count": 1,
        "document_chain": ["lab_review"],
    }
    result = asyncio.run(node_lab_review(state))
    assert len(result["lab_findings"]) == 1
    assert result["reviewed_lab_count"] == 2


def test_nursing_and_shift_summary_repeat_by_round():
    state = {
        "patient_id": "patient-1",
        "round_count": 2,
        "nursing_last_round": 1,
        "nursing_records": [{"round_number": 1}],
        "shift_summary_last_round": 1,
        "shift_summaries": [{"round_number": 1}],
        "document_chain": ["daily_round_note", "nursing_note", "shift_summary"],
        "vital_signs": [{"heart_rate": 82, "spo2": 97}],
        "disease_template": {"department": ""},
    }
    nursing = asyncio.run(node_nursing(state))
    assert len(nursing["nursing_records"]) == 2
    assert nursing["nursing_last_round"] == 2
    state.update(nursing)
    shift = asyncio.run(node_shift_summary(state))
    assert len(shift["shift_summaries"]) == 2
    assert shift["shift_summary_last_round"] == 2


def test_checkpoint_and_discharge_routes_stop_at_safety_boundaries():
    assert after_doctor_confirm({"pending_review": {"type": "doctor_confirm"}}) == "end"
    assert after_doctor_confirm({"doctor_confirm_status": "approved"}) == "batch_scoring"
    assert after_doctor_discharge_sign({"discharge_sign_status": "signed"}) == "discharge"
    assert after_discharge_bridge({"discharge_decision": "bridge_failed"}) == "end"


def test_node_transfer_high_risk():
    """高危+多体征异常触发转科ICU。"""
    result = asyncio.run(node_transfer({"risk_level": "high", "vital_signs": [{},{},{}]}))
    assert result["transfer_needed"] == True
    assert result["transfer_target"] == "ICU"


def test_node_transfer_low_risk():
    """低危不触发转科。"""
    result = asyncio.run(node_transfer({"risk_level": "low", "vital_signs": []}))
    assert result["transfer_needed"] == False


# ── 阶段K: 用药核对节点 ──


def test_node_medication_reconciliation_adds_findings():
    """阶段K: 用药核对——交叉比对模板用药与院前记录, 生成 findings。"""
    tpl = {
        "handoff_instructions": [
            {"type": "medication", "content": "氨氯地平片 5mg 每日一次"},
            {"type": "monitoring", "content": "每日测血压"},
        ],
    }
    result = asyncio.run(node_medication_reconciliation({
        "patient_id": "test-001",
        "disease_template": tpl,
        "document_chain": [],
    }))
    assert result["phase"] == "medication_reconciliation"
    assert "medication_findings" in result
    assert "medication_reconciliation" in result["document_chain"]
    assert "gaps" in result["medication_findings"]


def test_node_medication_reconciliation_no_meds():
    """阶段K: 无用药类型 handoff_instructions 时空 findings。"""
    tpl = {
        "handoff_instructions": [
            {"type": "monitoring", "content": "每日测血压"},
        ],
    }
    result = asyncio.run(node_medication_reconciliation({
        "patient_id": "test-001",
        "disease_template": tpl,
        "document_chain": [],
    }))
    assert result["phase"] == "medication_reconciliation"
    assert result["medication_findings"]["gaps"] == []
    assert result["medication_findings"]["conflicts"] == []
    assert result["medication_findings"]["duplications"] == []
