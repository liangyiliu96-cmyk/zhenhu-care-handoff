"""Application route contract regression tests."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from zhenhu.inpatient.services.api_contract import validate_unique_routes


def test_route_contract_rejects_duplicate_method_and_path():
    app = FastAPI()

    @app.get("/same")
    async def first():
        return {}

    @app.get("/same")
    async def second():
        return {}

    with pytest.raises(RuntimeError, match="Duplicate API routes"):
        validate_unique_routes(app)


def test_route_contract_accepts_distinct_methods_and_paths():
    app = FastAPI()

    @app.get("/patients")
    async def get_patients():
        return {}

    @app.post("/patients")
    async def create_patient():
        return {}

    validate_unique_routes(app)


@pytest.mark.asyncio
async def test_v1_aliases_keep_patient_access_and_paginate_results(isolated_state_store):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = "api-v1-cardiology"
    set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "monitoring",
        "patient_access": {"department": "cardiology"},
    })
    headers = {"x-role": "doctor", "x-user-id": "doctor-v1", "x-department": "cardiology"}
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        patients = await client.get("/v1/patients?limit=1&offset=0", headers=headers)
        rounds = await client.get(f"/v1/inpatient/{patient_id}/rounds", headers=headers)

    assert patients.status_code == 200
    assert patients.json()["data"]["pagination"]["limit"] == 1
    assert rounds.status_code == 200
