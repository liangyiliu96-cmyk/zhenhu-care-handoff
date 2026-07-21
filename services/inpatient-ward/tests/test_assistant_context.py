"""Assistant patient-context regression coverage."""

from __future__ import annotations


def test_assistant_context_reads_the_canonical_patient_state(isolated_state_store):
    from zhenhu.inpatient.agent.assistant import _patient_context
    from zhenhu.inpatient.routes.state_store import set_state

    set_state("assistant-context-patient", {
        "patient_id": "assistant-context-patient",
        "disease_template": {"name": "心力衰竭"},
        "risk_level": "medium",
        "news2_score": 4,
        "vital_signs": [{"spo2": 96, "systolic_mmhg": 118, "diastolic_mmhg": 74, "heart_rate": 76, "temperature": 36.5}],
        "medication_adjustments": [{"medication": "呋塞米"}],
        "ddx_list": [{"diagnosis": "急性失代偿性心力衰竭"}],
        "discharge_readiness": {"score": 70},
    })

    context = _patient_context("assistant-context-patient", include_readiness=True)

    assert "心力衰竭" in context
    assert "呋塞米" in context
    assert "出院准备度:70" in context
