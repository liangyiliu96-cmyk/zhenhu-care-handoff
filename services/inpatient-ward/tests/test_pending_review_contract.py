"""Regression coverage for the review queue consumed by the doctor workbench."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_pending_review_reads_expose_actionable_review_metadata(client, isolated_state_store):
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    patient_id = "workbench-review-contract"
    set_state(patient_id, {
        "patient_id": patient_id,
        "patient_access": {"department": "cardiology"},
        "disease_template": {"department": "cardiology", "name": "冠心病"},
        "patient_data": {"name": "测试患者"},
        "pending_review": {
            "review_id": "review-contract-1",
            "type": "doctor_confirm",
            "payload": {"chief_complaint": "胸痛", "ddx_list": [{"diagnosis": "ACS"}]},
        },
    })
    version = get_state(patient_id)["state_version"]
    headers = {"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"}

    detailed = await client.get("/reviews/pending", headers=headers)
    ward = await client.get("/ward/pending", headers=headers)
    patients = await client.get("/ward/patients", headers=headers)

    review = detailed.json()["data"]["reviews"][0]
    ward_item = ward.json()["data"]["pending"][0]
    assert review["state_version"] == version
    assert ward_item["state_version"] == version
    assert ward_item["items"] == [{
        "type": "ddx_confirm",
        "label": "入院诊断确认",
        "review_type": "doctor_confirm",
        "review_id": "review-contract-1",
        "payload": {"chief_complaint": "胸痛", "ddx_list": [{"diagnosis": "ACS"}]},
    }]
    assert ward_item["name"] == "测试患者"
    assert patients.json()["data"]["patients"][0]["name"] == "测试患者"
