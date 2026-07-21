"""Development fixture contract coverage for the doctor patient-detail workflow."""

from __future__ import annotations

import pytest
from urllib.parse import quote


@pytest.mark.asyncio
async def test_dashboard_care_fixture_exposes_one_complete_patient_detail(client, isolated_state_store):
    headers = {"x-role": "doctor", "x-department": quote("心内科")}

    loaded = await client.post("/inpatient/fixtures/load/dashboard-care", headers=headers)

    assert loaded.status_code == 200
    patient_id = loaded.json()["data"]["patient_id"]
    dashboard = await client.get(f"/inpatient/{patient_id}/dashboard", headers=headers)
    care = await client.get(f"/inpatient/{patient_id}/care-management", headers=headers)
    labs = await client.get(f"/inpatient/{patient_id}/lab-trends", headers=headers)

    assert dashboard.json()["data"]["patient_name"] == "演示患者-李安宁"
    assert dashboard.json()["data"]["state_version"] == loaded.json()["data"]["state_version"]
    assert care.json()["data"]["care_management"]["medication_orders"][0]["status"] == "draft"
    assert care.json()["data"]["care_management"]["mdt_requests"][0]["status"] == "requested"
    assert care.json()["data"]["care_management"]["follow_up_tasks"][0]["status"] == "pending"
    assert labs.json()["data"]["total_labs"] == 4
    assert labs.json()["data"]["lab_trends"]["creatinine"]["total_count"] == 2


@pytest.mark.asyncio
async def test_dashboard_care_fixture_accepts_canonical_vital_write(client, isolated_state_store, monkeypatch):
    monkeypatch.setenv("DOCTOR_AUTO_APPROVE", "false")
    headers = {"x-role": "doctor", "x-department": quote("心内科")}
    loaded = await client.post("/inpatient/fixtures/load/dashboard-care", headers=headers)
    patient_id = loaded.json()["data"]["patient_id"]
    version = loaded.json()["data"]["state_version"]

    response = await client.post(
        f"/inpatient/monitoring/{patient_id}/vitals",
        headers=headers,
        json={
            "systolic_mmhg": 118,
            "diastolic_mmhg": 76,
            "blood_pressure": "118/76",
            "heart_rate": 72,
            "spo2": 98,
            "temperature": 36.6,
            "expected_version": version,
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert response.json()["data"]["vitals_count"] == 4
    dashboard = await client.get(f"/inpatient/{patient_id}/dashboard", headers=headers)
    assert dashboard.json()["data"]["state_version"] == version + 1
    summary = await client.get(f"/inpatient/{patient_id}/discharge-summary", headers=headers)
    summary_data = summary.json()["data"]
    assert "handoff_note" not in summary_data["hospital_course"]
    assert summary_data["follow_up_plan"]
    assert summary_data["completeness"]["coverage"] == 1.0
    assert "warning" not in summary_data["completeness"]
