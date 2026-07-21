from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_alert_can_be_acknowledged_and_resolved():
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.models import init_db
    from zhenhu.inpatient.routes.state_store import set_state

    await init_db()
    patient_id = f"alert-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "clinical_alerts": [{"alert_id": "a-1", "message": "critical", "status": "open"}]})
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        acknowledged = await client.post(
            f"/inpatient/{patient_id}/alerts/a-1/acknowledge",
            headers={"x-role": "doctor", "x-user-id": "doctor-1"},
        )
        repeated_acknowledgement = await client.post(
            f"/inpatient/{patient_id}/alerts/a-1/acknowledge",
            headers={"x-role": "doctor", "x-user-id": "doctor-1"},
        )
        resolved = await client.post(
            f"/inpatient/{patient_id}/alerts/a-1/resolve",
            headers={"x-role": "doctor", "x-user-id": "doctor-1"},
        )
        listing = await client.get(f"/inpatient/{patient_id}/alerts", headers={"x-role": "doctor"})

    assert acknowledged.status_code == 200
    assert acknowledged.json()["data"]["alert"]["status"] == "acknowledged"
    assert acknowledged.json()["data"]["alert"]["acknowledged_by"] == "doctor-1"
    assert repeated_acknowledgement.status_code == 200
    assert repeated_acknowledgement.json()["data"]["state_version"] == acknowledged.json()["data"]["state_version"]
    assert resolved.status_code == 200
    assert resolved.json()["data"]["alert"]["status"] == "resolved"
    assert listing.json()["data"]["alerts"][0]["status"] == "resolved"


@pytest.mark.asyncio
async def test_alert_lifecycle_rejects_stale_state_version_and_non_doctor():
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.models import init_db
    from zhenhu.inpatient.routes.state_store import get_state, set_state, update_state

    await init_db()
    patient_id = f"alert-version-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "clinical_alerts": [{"alert_id": "a-1", "message": "critical", "status": "open"}]})
    stale_version = get_state(patient_id)["state_version"]
    update_state(patient_id, {"phase": "monitoring"})
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        forbidden = await client.post(f"/inpatient/{patient_id}/alerts/a-1/acknowledge", headers={"x-role": "nurse"})
        conflict = await client.post(
            f"/inpatient/{patient_id}/alerts/a-1/acknowledge",
            json={"expected_version": stale_version},
            headers={"x-role": "doctor"},
        )

    assert forbidden.status_code == 403
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "STATE_VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_ward_alert_aggregation_preserves_structured_critical_alert():
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"ward-alert-{uuid4()}"
    set_state(patient_id, {
        "patient_id": patient_id,
        "patient_data": {"name": "Structured alert patient"},
        "clinical_alerts": [{
            "alert_id": "critical-1",
            "message": "Critical lab: K=6.8",
            "severity": "critical",
            "status": "open",
        }],
    })
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/ward/alerts?severity=critical", headers={"x-role": "doctor"})

    assert response.status_code == 200
    alert = next(item for item in response.json()["data"]["alerts"] if item["patient_id"] == patient_id)
    assert alert["is_critical"] is True
    assert alert["alert"]["alert_id"] == "critical-1"


def test_graph_boundary_normalizes_legacy_alerts_and_preserves_lifecycle_fields():
    from zhenhu.inpatient.agent.graph import validate_state

    result = validate_state({
        "clinical_alerts": [
            "[并发症] AKI warning",
            "[并发症] AKI warning",
            {"alert_id": "a-1", "message": "Critical lab: K=6.8", "status": "acknowledged", "acknowledged_by": "doctor-1"},
        ],
    }, entry_point="plan_turn")

    assert len(result["clinical_alerts"]) == 2
    complication, critical = result["clinical_alerts"]
    assert complication["source"] == "complication"
    assert complication["status"] == "open"
    assert critical["alert_id"] == "a-1"
    assert critical["acknowledged_by"] == "doctor-1"
