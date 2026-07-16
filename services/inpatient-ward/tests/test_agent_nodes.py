"""Agent 节点独立测试。合并迁入。"""
import pytest, asyncio
# 合并迁入: 替换 app.src.zhenhu 路径
from zhenhu.inpatient.agent.nodes import (
    node_admission, node_triage, node_monitoring, node_discharge,
    node_handoff, node_doctor_review, node_patient_confirm,
    node_daily_round, node_medication_adjust, node_lab_review, node_transfer,
    node_medication_reconciliation,
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

def test_node_handoff_generates_items():
    tpl = {"handoff_instructions":[{"type":"medication","content":"降压药"}]}
    result = asyncio.run(node_handoff({"disease_template": tpl}))
    assert len(result["handoff_items"]) == 1

def test_node_handoff_empty_template():
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


def test_node_doctor_review_dismiss_triggers_reevaluation():
    """3项时第3项dismiss触发pending_reevaluation。"""
    state = {"handoff_items": [
        {"type": "medication", "content": "降压药方案"},
        {"type": "monitoring", "content": "每日测血压"},
        {"type": "followup", "content": "7天内复诊"},
    ]}
    result = asyncio.run(node_doctor_review(state))
    assert result["discharge_decision"] == "pending_reevaluation"
    assert result["handoff_items"][0]["review_action"] == "accept"
    assert result["handoff_items"][1]["review_action"] == "accept"
    assert result["handoff_items"][2]["review_action"] == "dismiss"
    assert result["handoff_items"][2]["dismiss_reason"] is not None
    assert result["handoff_items"][2]["reevaluation_pending"] is True


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

def test_node_patient_confirm_marks_all():
    result = asyncio.run(node_patient_confirm({"handoff_items":[{"type":"m","feedback":None}]}))
    assert result["handoff_items"][0]["feedback"] == "已理解"


def test_node_discharge_checks_criteria():
    """阶段K: 出院全链路自动化——无handoff_items时不触发bridge调用。"""
    tpl = {"discharge_criteria": ["bp_stable_24h", "medication_confirmed"]}
    result = asyncio.run(node_discharge({"disease_template": tpl, "vital_signs": []}))
    assert result["phase"] == "discharge"
    assert result["discharge_decision"] == "approved"


def test_node_discharge_approves_after_enough_vitals():
    """阶段K: 出院全链路——有handoff_items时触发bridge+知识+照护视图链（无真实服务时bridge_failed）。"""
    tpl = {
        "discharge_criteria": ["bp_stable_24h"],
        "handoff_instructions": [{"type": "medication", "content": "氨氯地平片 5mg 每日一次"}],
    }
    vs = [{}, {}, {}, {}, {}, {}]
    items = [{"type": "medication", "content": "氨氯地平片 5mg 每日一次"}]
    result = asyncio.run(node_discharge({
        "disease_template": tpl,
        "vital_signs": vs,
        "handoff_items": items,
    }))
    # 阶段K: bridge试图创建病例; 无真实服务时 decision 为 bridge_failed
    assert "bridge_result" in result
    assert result.get("knowledge_context") is not None
    assert result.get("patient_summary") is not None


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
