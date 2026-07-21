"""Patient department isolation regression tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_patient_record_is_hidden_from_other_departments():
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"access-{uuid4()}"
    set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "monitoring",
        "patient_access": {"department": "cardiology", "attending_doctor_id": "doctor-1", "care_team_ids": []},
    })

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        denied = await client.get(
            f"/inpatient/{patient_id}/rounds",
            headers={"x-role": "doctor", "x-user-id": "doctor-2", "x-department": "oncology"},
        )
        allowed = await client.get(
            f"/inpatient/{patient_id}/rounds",
            headers={"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"},
        )

    assert denied.status_code == 403
    assert allowed.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["dashboard", "timeline", "vital-trends", "lab-trends"])
async def test_patient_read_projections_enforce_department_access(suffix: str):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"projection-access-{suffix}-{uuid4()}"
    set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "monitoring",
        "patient_access": {"department": "cardiology"},
    })
    denied_headers = {"x-role": "doctor", "x-user-id": "doctor-2", "x-department": "oncology"}

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get(f"/inpatient/{patient_id}/{suffix}", headers=denied_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_nursing_and_query_endpoints_enforce_patient_department_access():
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"clinical-read-access-{uuid4()}"
    set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "monitoring",
        "nursing_records": [{"action": "护理记录"}],
        "patient_access": {"department": "cardiology"},
    })
    headers = {"x-role": "doctor", "x-user-id": "doctor-2", "x-department": "oncology"}

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        nursing = await client.get(f"/inpatient/{patient_id}/nursing", headers=headers)
        query = await client.post(f"/inpatient/{patient_id}/query", json={"question": "患者情况如何？"}, headers=headers)

    assert nursing.status_code == 403
    assert query.status_code == 403


@pytest.mark.asyncio
async def test_patient_list_excludes_other_departments():
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    allowed_id = f"access-allowed-{uuid4()}"
    denied_id = f"access-denied-{uuid4()}"
    set_state(allowed_id, {"patient_id": allowed_id, "phase": "monitoring", "patient_access": {"department": "cardiology"}})
    set_state(denied_id, {"patient_id": denied_id, "phase": "monitoring", "patient_access": {"department": "oncology"}})

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get(
            "/patients?limit=200",
            headers={"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "cardiology"},
        )

    assert response.status_code == 200
    patient_ids = {item["patient_id"] for item in response.json()["data"]["patients"]}
    assert allowed_id in patient_ids
    assert denied_id not in patient_ids


@pytest.mark.asyncio
async def test_assistant_cannot_read_patient_id_supplied_in_request_body():
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"assistant-access-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "patient_access": {"department": "cardiology"}})

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/assistant/chat",
            json={"message": "summarize", "patient_id": patient_id, "role": "doctor"},
            headers={"x-role": "doctor", "x-user-id": "doctor-2", "x-department": "oncology"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assistant_session_is_private_to_its_creator(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import assistant as assistant_engine

    async def fake_chat(message, role="patient", session_id=None, patient_id="", actor_id=""):
        session_id = session_id or assistant_engine.create_session(
            role, patient_id, owner_id=actor_id
        )
        return {"answer": "ok", "session_id": session_id}

    monkeypatch.setattr(assistant_engine, "chat", fake_chat)
    owner_headers = {"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"}
    other_headers = {"x-role": "doctor", "x-user-id": "doctor-2", "x-department": "cardiology"}

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        created = await client.post("/assistant/chat", json={"message": "hello"}, headers=owner_headers)
        session_id = created.json()["data"]["session_id"]
        denied = await client.get(f"/assistant/session/{session_id}", headers=other_headers)
        allowed = await client.get(f"/assistant/session/{session_id}", headers=owner_headers)
        reset_denied = await client.post(f"/assistant/session/{session_id}/reset", headers=other_headers)

    assert created.status_code == 200
    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert reset_denied.status_code == 403


@pytest.mark.asyncio
async def test_patient_bound_assistant_session_rechecks_department_access(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import assistant as assistant_engine
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"assistant-session-access-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "patient_access": {"department": "cardiology"}})

    async def fake_chat(message, role="patient", session_id=None, patient_id="", actor_id=""):
        session_id = session_id or assistant_engine.create_session(
            role, patient_id, owner_id=actor_id
        )
        return {"answer": "ok", "session_id": session_id}

    monkeypatch.setattr(assistant_engine, "chat", fake_chat)
    cardiology_headers = {"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"}
    oncology_headers = {"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "oncology"}

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        created = await client.post(
            "/assistant/chat", json={"message": "hello", "patient_id": patient_id}, headers=cardiology_headers
        )
        session_id = created.json()["data"]["session_id"]
        denied = await client.get(f"/assistant/session/{session_id}", headers=oncology_headers)
        rebound = await client.post(
            "/assistant/chat", json={"message": "hello", "session_id": session_id, "patient_id": "another-patient"},
            headers=cardiology_headers,
        )

    assert created.status_code == 200
    assert denied.status_code == 403
    assert rebound.status_code == 409


@pytest.mark.asyncio
async def test_non_clinical_role_cannot_read_patient_record():
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"non-clinical-access-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "patient_access": {"department": "cardiology"}})

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get(
            f"/inpatient/{patient_id}/rounds",
            headers={"x-role": "administrator", "x-user-id": "admin-1", "x-department": "cardiology"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ward_aggregate_endpoints_exclude_other_departments():
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    cardiology_id = f"ward-cardiology-{uuid4()}"
    oncology_id = f"ward-oncology-{uuid4()}"
    set_state(cardiology_id, {
        "patient_id": cardiology_id, "risk_level": "high",
        "patient_access": {"department": "cardiology"},
        "pending_review": {"review_id": "review-cardiology", "type": "doctor_confirm", "payload": {}},
    })
    set_state(oncology_id, {
        "patient_id": oncology_id, "risk_level": "high",
        "patient_access": {"department": "oncology"},
        "pending_review": {"review_id": "review-oncology", "type": "doctor_confirm", "payload": {}},
    })
    headers = {"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"}

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        overview = await client.get("/ward/overview", headers=headers)
        pending = await client.get("/reviews/pending", headers=headers)

    overview_ids = {item["patient_id"] for item in overview.json()["data"]["patients"]}
    pending_ids = {item["patient_id"] for item in pending.json()["data"]["reviews"]}
    assert cardiology_id in overview_ids
    assert oncology_id not in overview_ids
    assert cardiology_id in pending_ids
    assert oncology_id not in pending_ids


@pytest.mark.asyncio
async def test_all_ward_aggregates_apply_department_filter_before_query_filtering():
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    cardiology_id = f"aggregate-cardiology-{uuid4()}"
    oncology_id = f"aggregate-oncology-{uuid4()}"
    common = {
        "phase": "monitoring",
        "risk_level": "high",
        "news2_score": 7,
        "patient_data": {"name": "Visible patient"},
        "clinical_alerts": ["high risk"],
        "pending_review": {"review_id": "pending", "type": "doctor_confirm", "payload": {}},
        "disease_template": {"department": "cardiology", "name": "cardiology"},
    }
    set_state(cardiology_id, {**common, "patient_id": cardiology_id, "patient_access": {"department": "cardiology"}})
    set_state(oncology_id, {
        **common,
        "patient_id": oncology_id,
        "patient_data": {"name": "Hidden patient"},
        "disease_template": {"department": "oncology", "name": "oncology"},
        "patient_access": {"department": "oncology"},
    })
    headers = {"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"}

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        shift_report = await client.get("/ward/shift-report", headers=headers)
        insights = await client.get("/ward/insights", headers=headers)
        visit_order = await client.get("/ward/visit-order", headers=headers)
        priority = await client.get("/ward/priority", headers=headers)
        patients = await client.get("/ward/patients?department=oncology", headers=headers)
        pending = await client.get("/ward/pending?department=oncology", headers=headers)
        alerts = await client.get("/ward/workspace/alerts?department=oncology", headers=headers)

    assert shift_report.status_code == 200
    shift_ids = {item["patient_id"] for item in shift_report.json()["data"]["high_focus"]}
    assert cardiology_id in shift_ids
    assert oncology_id not in shift_ids
    assert insights.json()["data"]["stats"]["total_active"] >= 1
    visit_ids = {item["patient_id"] for item in visit_order.json()["data"]["visit_order"]}
    priority_ids = {item["patient_id"] for item in priority.json()["data"]["top_patients"]}
    assert cardiology_id in visit_ids
    assert oncology_id not in visit_ids
    assert oncology_id not in priority_ids
    patient_ids = {item["patient_id"] for item in patients.json()["data"]["patients"]}
    pending_ids = {item["patient_id"] for item in pending.json()["data"]["pending"]}
    alert_ids = {item["patient_id"] for item in alerts.json()["data"]["alerts"]}
    assert cardiology_id not in patient_ids
    assert oncology_id not in patient_ids
    assert cardiology_id not in pending_ids
    assert oncology_id not in pending_ids
    assert cardiology_id not in alert_ids
    assert oncology_id not in alert_ids
