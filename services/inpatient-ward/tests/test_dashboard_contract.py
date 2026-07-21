"""Doctor dashboard read-model contract coverage."""

from __future__ import annotations

import asyncio

import pytest

from request_helpers import doctor_request


@pytest.mark.asyncio
async def test_dashboard_exposes_patient_identity_and_state_version(isolated_state_store, monkeypatch):
    from zhenhu.inpatient.routes import dashboard
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    async def no_checklist(_state):
        return []

    monkeypatch.setattr(dashboard, "_compute_checklist", no_checklist)
    patient_id = "dashboard-contract-patient"
    set_state(patient_id, {
        "patient_id": patient_id,
        "patient_data": {"name": "测试患者"},
        "disease_template": {"name": "冠心病"},
        "phase": "monitoring",
        "doctor_command": "hold",
        "pending_review": {"type": "med_confirm", "review_id": "review-med-1"},
    })

    response = await dashboard.get_dashboard(patient_id, doctor_request())
    data = response.data

    assert data["patient_name"] == "测试患者"
    assert data["state_version"] == get_state(patient_id)["state_version"]
    assert data["is_on_hold"] is True
    assert data["pending_review_type"] == "med_confirm"
    assert data["pending_review_id"] == "review-med-1"
    assert data["discharge_blockers"] == []


@pytest.mark.asyncio
async def test_dashboard_checklist_does_not_invoke_an_llm_on_read():
    from zhenhu.inpatient.routes.dashboard import _compute_checklist

    items = await asyncio.wait_for(_compute_checklist({"vital_signs": []}), timeout=0.1)

    assert items


@pytest.mark.asyncio
async def test_dashboard_hides_stale_prerequisite_review_after_discharge_signature(isolated_state_store):
    from zhenhu.inpatient.routes import dashboard
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = "dashboard-stale-review"
    set_state(patient_id, {
        "patient_id": patient_id,
        "patient_data": {"name": "已签字患者"},
        "pending_review": {"type": "med_confirm", "review_id": "stale-review"},
        "med_confirm_status": "pending",
        "discharge_sign_status": "signed",
    })

    response = await dashboard.get_dashboard(patient_id, doctor_request())
    assert response.data["pending_review_type"] == ""
    assert response.data["pending_review_id"] == ""
