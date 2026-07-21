"""Assistant quick-question context boundary coverage."""

from __future__ import annotations


def test_general_quick_questions_do_not_imply_patient_context():
    from zhenhu.inpatient.agent.assistant import quick_questions_for

    general = quick_questions_for("doctor", "general")
    patient = quick_questions_for("doctor", "patient")

    assert general
    assert all("该患者" not in item for item in general)
    assert any("该患者" in item for item in patient)
