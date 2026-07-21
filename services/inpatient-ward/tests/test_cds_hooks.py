"""CDS Hooks contract regressions."""

import pytest


def _patient_state(patient_id: str) -> dict:
    return {
        "patient_id": patient_id,
        "phase": "monitoring",
        "disease_template": {"disease_id": "hypertension"},
        "risk_level": "low",
        "news2_score": 0,
        "qsofa_score": 0,
        "ddx_list": [],
        "document_chain": [],
        "medication_findings": {
            "conflicts": [{"drug_pair": "drug-a + drug-b", "severity": "severe"}],
            "gaps": [],
            "during_stay_changes": [],
        },
        "clinical_alerts": [],
        "handoff_acknowledged": True,
        "discharge_criteria_check": {"all_met": True, "unmet": []},
    }


@pytest.mark.asyncio
async def test_cds_discovery_uses_the_actual_request_base(client):
    response = await client.get("/cds-services")

    assert response.status_code == 200
    assert len(response.json()["services"]) == 4


@pytest.mark.asyncio
async def test_cds_status_is_manager_only_and_reports_all_handlers(client):
    denied = await client.get(
        "/cds-services/status",
        headers={"x-role": "doctor", "x-title": "%E4%B8%BB%E6%B2%BB%E5%8C%BB%E5%B8%88"},
    )
    allowed = await client.get(
        "/cds-services/status",
        headers={"x-role": "nurse", "x-title": "%E6%8A%A4%E5%A3%AB%E9%95%BF"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    data = allowed.json()["data"]
    assert data["standard"] == "HL7 CDS Hooks 1.1"
    assert data["service_count"] == 4
    assert data["discovery_url"] == "http://test/cds-services"
    assert all(item["endpoint"].startswith("http://test/cds-services/") for item in data["services"])


@pytest.mark.asyncio
async def test_static_cds_service_path_does_not_require_query_service_id(
    client, isolated_state_store,
):
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = "cds-route-test"
    set_state(patient_id, _patient_state(patient_id))

    response = await client.post(
        "/cds-services/zhenhu-admission-confirm",
        json={"hook": "patient-view", "context": {"patientId": patient_id}},
    )

    assert response.status_code == 200
    assert len(response.json()["cards"]) == 1


@pytest.mark.asyncio
async def test_cds_medication_card_awaits_rag_search(
    client, isolated_state_store, monkeypatch,
):
    from zhenhu.inpatient.agent import rag_engine
    from zhenhu.inpatient.routes.state_store import set_state

    async def fake_search(query: str, **kwargs):
        assert query == "drug-a + drug-b"
        return [{"text": "evidence-from-rag"}]

    monkeypatch.setattr(rag_engine, "search", fake_search)
    patient_id = "cds-rag-test"
    set_state(patient_id, _patient_state(patient_id))

    response = await client.post(
        "/cds-services/zhenhu-medication-confirm",
        json={"hook": "order-select", "context": {"patientId": patient_id}},
    )

    assert response.status_code == 200
    assert "evidence-from-rag" in response.json()["cards"][0]["detail"]
