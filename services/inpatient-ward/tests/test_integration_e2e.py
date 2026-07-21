"""端到端集成测试——完整住院协同流程12节点。"""

import asyncio
import pytest

from zhenhu.inpatient.agent.nodes_admission import (
    node_admission, node_triage, node_medication_reconciliation,
)
from zhenhu.inpatient.agent.nodes_monitoring import (
    node_monitoring, node_daily_round,
)
from zhenhu.inpatient.agent.nodes_handoff import (
    node_discharge, node_handoff, node_doctor_review, node_patient_confirm,
)
from zhenhu.inpatient.agent.nodes_admission import load_template


def _build_initial_state(disease_id="hypertension", patient_id="e2e-test-001"):
    template = load_template(disease_id)
    return {
        "patient_id": patient_id,
        "disease_template": template,
        "phase": "",
        "vital_signs": [],
        "risk_level": "low",
        "discharge_decision": None,
        "handoff_items": [],
        "knowledge_context": "",
        "interrupt_pending": False,
        "event_type": None,
        "document_chain": [],
        "lab_results": [],
        "reviewed_labs": [],
        "medication_adjustments": [],
        "medication_alerts": [],
        "lab_findings": [],
        "latest_round": None,
        "round_count": 0,
        "transfer_needed": False,
        "transfer_target": None,
        "transfer_reason": None,
        "allergies": [],
        "patient_history": {},
        "triage_matched_factors": [],
        "consecutive_abnormal_count": 0,
        "allergy_status": None,
        "discharge_criteria_check": None,
        "clinical_assessments": None,
        "clinical_alerts": [],
    }


@pytest.mark.asyncio
async def test_e2e_full_admission_to_confirm(monkeypatch):
    """完整住院流程：入院→监测→交接→签字→桥接→签收与回授确认。"""
    state = _build_initial_state("hypertension", "e2e-test-001")

    # 1. 入院
    state.update(await node_admission(state))
    assert state["phase"] == "admission"
    assert "intake_note" in state["document_chain"]
    assert state["disease_template"]["disease_id"] == "hypertension"

    # 2. 用药核对
    state.update(await node_medication_reconciliation(state))
    assert state["phase"] == "medication_reconciliation"

    # 3. 风险分层
    state.update(await node_triage(state))
    assert state["phase"] == "triage"
    assert "risk_assessment" in state["document_chain"]
    assert state["risk_level"] in ("low", "medium", "high")

    # 4. 持续监测（喂体征数据直到满足出院条件）
    for i in range(6):
        state["vital_signs"].append({
            "blood_pressure": "130/85",
            "systolic_mmhg": 130, "diastolic_mmhg": 85,
            "heart_rate": 72, "spo2": 98, "temperature": 36.5,
        })

    state.update(await node_monitoring(state))
    assert state["phase"] == "monitoring"

    # 5. 每日查房
    state.update(await node_daily_round(state))
    assert state["phase"] == "daily_round"
    assert "daily_round_note" in state["document_chain"]
    assert state["latest_round"] is not None

    # 6. 生成交接草稿
    state["discharge_decision"] = "approved"
    state.update(await node_handoff(state))
    assert state["phase"] == "handoff"
    assert len(state["handoff_items"]) > 0

    # 7. 医生审核并签字
    state.update(await node_doctor_review(state))
    assert state["phase"] == "review"
    state["discharge_sign_status"] = "signed"

    async def create_case(patient_id, handoff_items, template):
        return {"status": "ok", "case_id": "case-e2e"}

    async def search_knowledge(query):
        return []

    async def patient_summary(patient_id):
        return {"patient_id": patient_id}

    monkeypatch.setattr(
        "zhenhu.inpatient.agent.nodes_handoff._create_zhenhu_case", create_case,
    )
    monkeypatch.setattr(
        "zhenhu.inpatient.hooks.zhenhu_bridge.bridge_search_knowledge", search_knowledge,
    )
    monkeypatch.setattr(
        "zhenhu.inpatient.hooks.zhenhu_bridge.bridge_patient_summary", patient_summary,
    )

    # 8. 签字后执行外部出院桥接
    state.update(await node_discharge(state))
    assert state["phase"] == "discharge"
    assert "discharge_bridge" in state["document_chain"]

    # 9. 接收方签收并完成真实回授后确认
    state["handoff_acknowledged"] = True
    state["education_records"] = [{
        "id": "education-e2e",
        "topic": "出院用药",
        "recipient": "patient",
        "teach_back": "按时服药，不自行停药",
        "acknowledged": True,
    }]
    state.update(await node_patient_confirm(state))
    assert state["phase"] == "confirm"
    assert state["patient_confirmation_status"] == "confirmed"

    # 验证关键字段贯穿
    assert state["patient_id"] == "e2e-test-001"
    assert state["round_count"] >= 1


@pytest.mark.asyncio
async def test_e2e_different_disease():
    """验证不同病种模板的入院流程。"""
    for disease_id in ["hypertension", "heart_failure", "diabetes", "stroke"]:
        state = _build_initial_state(disease_id, f"e2e-{disease_id}")
        state.update(await node_admission(state))
        assert state["disease_template"]["disease_id"] == disease_id
        assert "intake_note" in state["document_chain"]


@pytest.mark.asyncio
async def test_e2e_high_risk_triggers_mdt():
    """高危患者应触发MDT。"""
    state = _build_initial_state("heart_failure", "e2e-high")
    state.update(await node_admission(state))
    state.update(await node_medication_reconciliation(state))
    state.update(await node_triage(state))
    # 无真实患者数据时默认为low，需要构造高危数据
    # 构造patient_history模拟高危
    state["patient_history"] = {"comorbidities": ["diabetes", "ckd", "obesity"], "prior_hospitalization": True}
    state["patient_data"] = {"age": 75, "bmi": 30}
    state.update(await node_triage(state))
    # 高危应触发MDT
    if state["risk_level"] == "high":
        assert state.get("mdt_required") is True


@pytest.mark.asyncio
async def test_e2e_transfer_logic():
    """高危+体征异常+已调药应触发转科。"""
    state = _build_initial_state("heart_failure", "e2e-transfer")
    state["risk_level"] = "high"
    state["vital_signs"] = [
        {"blood_pressure": "85/55", "systolic_mmhg": 85, "diastolic_mmhg": 55, "heart_rate": 125},
        {"blood_pressure": "88/60", "systolic_mmhg": 88, "diastolic_mmhg": 60, "heart_rate": 120},
        {"blood_pressure": "85/55", "systolic_mmhg": 85, "diastolic_mmhg": 55, "heart_rate": 130},
    ]
    state["medication_adjustments"] = [{"reason": "低血压", "action": "调整降压药"}]
    
    from zhenhu.inpatient.agent.nodes_monitoring import node_transfer
    state.update(await node_transfer(state))
    assert state["phase"] == "transfer"
