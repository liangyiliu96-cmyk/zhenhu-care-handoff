from zhenhu.inpatient.services.doctor_copilot import build_pre_round_brief, build_progress_note_draft
from zhenhu.inpatient.routes import doctor_copilot
from zhenhu.inpatient.routes.doctor_copilot import ProgressNoteDraftRequest
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


def test_pre_round_brief_uses_canonical_state_fields_before_marking_history_gaps():
    brief = build_pre_round_brief(
        {
            "patient_id": "patient-canonical-history",
            "history_data": {"chief_complaint": "胸痛", "hpi_narrative": "胸痛 2 小时"},
            "allergies": ["无已知药物过敏"],
            "ros_findings": {"cardiovascular": "否认心悸"},
            "patient_history": {"comorbidities": {"hypertension": "高血压"}},
        }
    )

    gap_fields = {item["field"] for item in brief["history_gaps"]}

    assert {"allergies", "pmh", "ros_findings"}.isdisjoint(gap_fields)


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


@pytest.mark.asyncio
async def test_progress_note_route_rejects_stale_state_version(monkeypatch):
    monkeypatch.setattr(
        doctor_copilot,
        "get_state",
        lambda patient_id: {"patient_id": patient_id, "state_version": 9},
    )

    with pytest.raises(Exception) as exc_info:
        await doctor_copilot.generate_progress_note(
            "patient-route",
            ProgressNoteDraftRequest(expected_version=8),
            doctor_request(),
        )

    assert getattr(exc_info.value, "status_code", None) == 409


def test_progress_note_draft_never_fills_unsupported_assessment_or_plan():
    draft = build_progress_note_draft({"patient_id": "patient-note", "state_version": 3})

    assert draft["patient_id"] == "patient-note"
    assert draft["state_version"] == 3
    assert draft["sections"]["assessment"]["text"] == "待医生补充"
    assert draft["sections"]["assessment"]["status"] == "needs_input"
    assert draft["sections"]["plan"]["facts"] == []


def test_progress_note_draft_links_subjective_and_objective_to_source_facts():
    draft = build_progress_note_draft(
        {
            "patient_id": "patient-note-facts",
            "state_version": 5,
            "history_data": {"chief_complaint": "活动后气促"},
            "vital_signs": [{"timestamp": "2026-07-22T08:00:00Z", "heart_rate": 96, "spo2": 97}],
            "lab_results": [{"name": "肌酐", "value": "120", "timestamp": "2026-07-22T07:30:00Z"}],
        }
    )

    assert draft["sections"]["subjective"]["facts"][0]["source_type"] == "history"
    assert {fact["source_type"] for fact in draft["sections"]["objective"]["facts"]} == {"vital_sign", "lab_result"}
    assert "活动后气促" in draft["sections"]["subjective"]["text"]
