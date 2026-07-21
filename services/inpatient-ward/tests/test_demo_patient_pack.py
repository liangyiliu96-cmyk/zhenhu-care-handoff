from __future__ import annotations

from urllib.parse import quote

import pytest

def test_demo_pack_contains_ten_patients_per_department():
    from zhenhu.inpatient.routes.demo_patient_pack import (
        DEMO_DEPARTMENTS,
        DEMO_PATIENT_IDS,
        build_demo_patient_states,
    )

    states = build_demo_patient_states()

    assert DEMO_DEPARTMENTS == {"心内科": 10, "呼吸科": 10}
    assert len(DEMO_PATIENT_IDS) == 20
    assert len(states) == 20
    assert {state["department"] for state in states.values()} == {"心内科", "呼吸科"}
    assert all(state["demo_seed"] is True for state in states.values())
    assert all(state["patient_data"]["is_demo_patient"] is True for state in states.values())
    assert all(state["disease_template"]["department"] == state["department"] for state in states.values())
    assert all(state["clinical_evidence"] for state in states.values())
    assert all(state["latest_round"]["citations"] == state["clinical_evidence"] for state in states.values())
    assert all(citation["source"] == "disease_template" for state in states.values() for citation in state["clinical_evidence"])
    assert all(isinstance(state["news2_score"], int) and state["news2_risk"] for state in states.values())
    assert all(isinstance(state["qsofa_score"], int) and state["qsofa_risk"] for state in states.values())
    assert all(isinstance(state["padua_score"], int) and state["padua_risk"] for state in states.values())
    assert all(state["clinical_score_details"]["source"] == "demo_deterministic_projection" for state in states.values())
    assert all(state["clinical_score_details"]["news2"]["basis"] for state in states.values())


def test_demo_pack_keeps_pre_discharge_patients_out_of_the_discharge_workflow():
    from zhenhu.inpatient.routes.demo_patient_pack import build_demo_patient_states

    state = build_demo_patient_states()["demo-card-acs-monitor"]
    criteria = state["discharge_criteria_check"]

    assert state["phase"] == "monitoring"
    assert state["discharge_sign_status"] == ""
    assert criteria["all_met"] is False
    assert criteria["details"]
    assert criteria["unmet"] == [detail["key"] for detail in criteria["details"] if not detail["met"]]


def test_demo_patient_state_is_retained_across_development_server_restarts(monkeypatch):
    from zhenhu.inpatient.routes.state_store import _should_retain_state

    monkeypatch.setenv("APP_ENV", "dev")

    assert _should_retain_state({"demo_seed": True, "phase": "monitoring"}, age_seconds=86_400, active_ttl=1)


@pytest.mark.asyncio
async def test_demo_reset_requires_manager_confirmation_and_reseeds_twenty_patients(client):
    unauthorized = await client.post("/inpatient/fixtures/reset-demo", json={"confirmed": True})
    assert unauthorized.status_code == 403

    headers = {"x-role": "doctor", "x-title": quote("科主任"), "x-department": quote("心内科")}
    unconfirmed = await client.post("/inpatient/fixtures/reset-demo", headers=headers, json={"confirmed": False})
    assert unconfirmed.status_code == 422

    from zhenhu.inpatient.routes.state_store import get_state, set_state

    set_state("legacy-dirty-patient", {"patient_id": "legacy-dirty-patient", "phase": "completed"})
    response = await client.post("/inpatient/fixtures/reset-demo", headers=headers, json={"confirmed": True, "purge_runtime": True})
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 20
    assert payload["by_department"] == {"心内科": 10, "呼吸科": 10}
    assert payload["purge_runtime"] is True
    assert payload["audit_id"]
    assert get_state("legacy-dirty-patient") is None

    doctor_view = await client.get("/ward/overview", headers=headers)
    assert doctor_view.status_code == 200
    assert doctor_view.json()["data"]["total"] == 10

    nurse_headers = {"x-role": "nurse", "x-title": quote("护士长"), "x-department": quote("呼吸科")}
    nurse_view = await client.get("/nurse/tasks", headers=nurse_headers)
    assert nurse_view.status_code == 200
    assert nurse_view.json()["data"]["total"] >= 7

    follow_up_view = await client.get("/inpatient/follow-up-overview", headers=headers)
    assert follow_up_view.status_code == 200
    follow_up_patient = next(item for item in follow_up_view.json()["data"]["patients"] if item["patient_id"] == "demo-card-hf-followup")
    assert follow_up_patient["contact"]["has_contact"] is True
    assert follow_up_patient["contact"]["masked_mobile_phone"]
    handoff_state = get_state("demo-card-hf-followup")
    assert handoff_state["bridge_result"]["status"] == "ok"
    assert handoff_state["handoff_acknowledged"] is False
    assert handoff_state["patient_confirmation_requirements"] == ["handoff_acknowledgement", "teach_back"]
    assert "discharge_bridge" in handoff_state["document_chain"]

    evidence_view = await client.get("/inpatient/demo-card-acs-monitor/evidence", headers=headers)
    assert evidence_view.status_code == 200
    evidence = evidence_view.json()["data"]
    assert evidence["count"] == 1
    assert evidence["citations"][0]["source"] == "disease_template"

    scores_view = await client.get("/inpatient/demo-card-chest-pain/scores", headers=headers)
    assert scores_view.status_code == 200
    scores = scores_view.json()["data"]
    assert scores["score_source"] == "demo_deterministic_projection"
    assert scores["news2"]["status"] == "available"
    assert scores["news2"]["score"] is not None
    assert scores["news2"]["basis"]
