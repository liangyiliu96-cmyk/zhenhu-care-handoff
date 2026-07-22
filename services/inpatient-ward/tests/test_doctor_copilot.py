from zhenhu.inpatient.services.doctor_copilot import build_pre_round_brief
from zhenhu.inpatient.routes import doctor_copilot
from request_helpers import doctor_request
import pytest


def test_pre_round_brief_uses_only_current_patient_facts():
    brief = build_pre_round_brief(
        {
            "patient_id": "patient-current",
            "state_version": 7,
            "vital_signs": [
                {
                    "timestamp": "2026-07-22T08:00:00Z",
                    "heart_rate": 112,
                    "spo2": 95,
                }
            ],
            "lab_results": [
                {
                    "name": "肌酐",
                    "value": "155",
                    "timestamp": "2026-07-22T07:00:00Z",
                }
            ],
            "clinical_alerts": [
                {
                    "id": "alert-current",
                    "message": "心率增快，需要复核",
                    "status": "active",
                }
            ],
            "other_patient_payload": {"patient_id": "patient-other", "message": "不得泄露"},
        }
    )

    assert brief["patient_id"] == "patient-current"
    assert brief["state_version"] == 7
    assert all(item["facts"] for item in brief["attention_items"])
    assert "patient-other" not in str(brief)
    assert "不得泄露" not in str(brief)


def test_pre_round_brief_marks_missing_history_as_questions_not_facts():
    brief = build_pre_round_brief(
        {
            "patient_id": "patient-history-gap",
            "state_version": 2,
            "history_data": {"chief_complaint": "活动后气促"},
        }
    )

    gap_fields = {item["field"] for item in brief["history_gaps"]}

    assert "hpi_narrative" in gap_fields
    assert "allergies" in gap_fields
    assert all(item["status"] == "needs_input" for item in brief["history_gaps"])


@pytest.mark.asyncio
async def test_pre_round_route_returns_a_read_only_current_version_brief(monkeypatch):
    monkeypatch.setattr(
        doctor_copilot,
        "get_state",
        lambda patient_id: {"patient_id": patient_id, "state_version": 9},
    )

    response = await doctor_copilot.get_pre_round("patient-route", doctor_request())

    assert response.data["patient_id"] == "patient-route"
    assert response.data["state_version"] == 9
