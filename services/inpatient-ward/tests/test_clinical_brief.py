from zhenhu.inpatient.services.assistant_action_drafts import validate_action_payload
from zhenhu.inpatient.services.clinical_brief import build_clinical_brief


def test_clinical_brief_groups_alerts_and_exposes_round_focus_without_mutation():
    state = {
        "vital_signs": [
            {"heart_rate": 88, "spo2": 97, "timestamp": "2026-07-20T08:00:00"},
            {"heart_rate": 116, "spo2": 89, "timestamp": "2026-07-20T12:00:00"},
        ],
        "clinical_alerts": ["SpO2持续下降", "心率升高"],
        "lab_results": [{"name": "肌酐", "value": 88, "unit": "umol/L"}, {"name": "肌酐", "value": 126, "unit": "umol/L"}],
        "disease_template": {"name": "心力衰竭"},
    }

    brief = build_clinical_brief(state)

    assert brief["generated_by"] == "rule_based_clinical_brief"
    assert brief["alert_groups"][0]["urgency"] == "high"
    assert brief["lab_changes"][0]["name"] == "肌酐"
    assert state["vital_signs"][1]["spo2"] == 89


def test_clinical_brief_does_not_create_discharge_blockers_before_discharge_starts():
    brief = build_clinical_brief({
        "discharge_criteria_check": {"all_met": True},
        "handoff_acknowledged": True,
        "disease_template": {},
    })

    assert brief["discharge_blockers"] == []


def test_clinical_brief_exposes_only_current_discharge_stage_blockers():
    brief = build_clinical_brief({
        "phase": "handoff",
        "discharge_sign_status": "signed",
        "discharge_criteria_check": {
            "all_met": False,
            "unmet": ["vital_signs_stable"],
            "details": [{
                "key": "vital_signs_stable",
                "label": "生命体征保持稳定",
                "met": False,
                "category": "monitoring",
                "action": "补充最新体征并重新评估",
            }],
        },
        "handoff_acknowledged": False,
        "follow_up_contact": {},
    })

    assert brief["discharge_blockers"] == [
        {
            "key": "vital_signs_stable",
            "reason": "生命体征保持稳定",
            "action": "补充最新体征并重新评估",
            "target": "monitoring",
            "status": "blocking",
        },
        {
            "key": "handoff_acknowledgement",
            "reason": "交接事项尚未签收",
            "action": "在交接闭环状态中确认接收方签收",
            "target": "handoff",
            "status": "blocking",
        },
        {
            "key": "follow_up_contact",
            "reason": "未登记随访联系电话",
            "action": "取得患者授权后补录随访联系电话",
            "target": "contact",
            "status": "blocking",
        },
    ]


def test_clinical_brief_uses_contact_completion_bit_without_copying_phone_data():
    brief = build_clinical_brief({
        "phase": "handoff",
        "discharge_sign_status": "signed",
        "discharge_criteria_check": {"all_met": True},
        "handoff_acknowledged": True,
        "follow_up_contact_registered": True,
    })

    assert not any(item["key"] == "follow_up_contact" for item in brief["discharge_blockers"])


def test_new_action_draft_payloads_remain_plans_until_approved():
    mdt = validate_action_payload("mdt_request", {"reason": "多学科评估治疗方案", "specialties": ["心内科", "肾内科"]})
    education = validate_action_payload("education_plan", {"topic": "出院后用药", "recipient": "family", "key_points": ["按时服药"]})

    assert mdt["specialties"] == ["心内科", "肾内科"]
    assert education["recipient"] == "family"
    assert "acknowledged" not in education
