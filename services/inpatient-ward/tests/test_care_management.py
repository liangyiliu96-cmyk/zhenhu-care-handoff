"""Tests for the explicit medication, MDT, education, and follow-up lifecycle."""

from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_reading_care_management_does_not_mutate_patient_state_version():
    from zhenhu.inpatient.routes.state_store import get_state, set_state
    from zhenhu.inpatient.services.care_management import CareManagementService

    patient_id = f"care-read-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    version_before = get_state(patient_id)["state_version"]

    care = await CareManagementService().get_care_management(patient_id)

    assert care == {
        "medication_orders": [], "investigation_orders": [], "mdt_requests": [],
        "education_plans": [], "education_records": [], "follow_up_tasks": [],
    }
    assert get_state(patient_id)["state_version"] == version_before


def _data(response):
    return response.model_dump()["data"]


@pytest.mark.asyncio
async def test_care_lifecycle_tracks_orders_mdt_education_and_follow_up():
    from zhenhu.inpatient.routes.care_management import (
        acknowledge_education,
        add_medication_order,
        create_follow_up_task,
        create_mdt_request,
        get_care_management,
        resolve_mdt_request,
        update_follow_up_task,
        update_medication_order,
    )
    from zhenhu.inpatient.routes.route_schemas import (
        EducationAcknowledgementRequest,
        FollowUpTaskRequest,
        FollowUpTaskUpdateRequest,
        MDTDecisionRequest,
        MDTRequest,
        MedicationOrderRequest,
        MedicationOrderStatusRequest,
    )
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"care-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})

    order = _data(await add_medication_order(
        patient_id,
        MedicationOrderRequest(medication="amlodipine", dose="5 mg", frequency="qd"),
    ))["medication_order"]
    assert order["status"] == "draft"

    activated = _data(await update_medication_order(
        patient_id,
        order["id"],
        MedicationOrderStatusRequest(status="active"),
    ))["medication_order"]
    assert activated["status"] == "active"

    mdt = _data(await create_mdt_request(
        patient_id,
        MDTRequest(reason="high-risk deterioration", specialties=["cardiology", "nutrition"]),
    ))["mdt_request"]
    resolved = _data(await resolve_mdt_request(
        patient_id,
        mdt["id"],
        MDTDecisionRequest(decision="accepted", summary="continue monitoring"),
    ))["mdt_request"]
    assert resolved["status"] == "resolved"
    assert resolved["decision"] == "accepted"

    task = _data(await create_follow_up_task(
        patient_id,
        FollowUpTaskRequest(title="blood pressure follow-up", due_at="2026-08-01T09:00:00+08:00"),
    ))["follow_up_task"]
    completed = _data(await update_follow_up_task(
        patient_id,
        task["id"],
        FollowUpTaskUpdateRequest(status="completed", note="patient contacted"),
    ))["follow_up_task"]
    assert completed["status"] == "completed"

    education = _data(await acknowledge_education(
        patient_id,
        EducationAcknowledgementRequest(topic="medication safety", recipient="patient", teach_back="understood"),
    ))["education_record"]
    assert education["acknowledged"] is True

    care = _data(await get_care_management(patient_id))["care_management"]
    assert len(care["medication_orders"]) == 1
    assert len(care["mdt_requests"]) == 1
    assert len(care["follow_up_tasks"]) == 1
    assert len(care["education_records"]) == 1


@pytest.mark.asyncio
async def test_care_management_exposes_planned_education_from_an_approved_assistant_draft():
    from zhenhu.inpatient.routes.state_store import set_state
    from zhenhu.inpatient.services.care_management import CareManagementService

    patient_id = f"care-education-plan-{uuid4()}"
    plan = {
        "id": "education-plan-1",
        "topic": "起搏器术后宣教",
        "recipient": "patient",
        "key_points": ["伤口观察", "复诊时间"],
        "status": "planned",
        "source_draft_id": "assistant-draft-1",
    }
    set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "monitoring",
        "education_plans": [plan],
    })

    care = await CareManagementService().get_care_management(patient_id)

    assert care["education_plans"] == [plan]


@pytest.mark.asyncio
async def test_teach_back_completes_waiting_patient_confirmation():
    from zhenhu.inpatient.routes.care_management import acknowledge_education
    from zhenhu.inpatient.routes.route_schemas import EducationAcknowledgementRequest
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    patient_id = f"care-confirm-{uuid4()}"
    set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "awaiting_patient_confirmation",
        "document_chain": ["handoff_note", "review_note", "discharge_bridge"],
        "discharge_sign_status": "signed",
        "handoff_acknowledged": True,
        "patient_confirmation_status": "pending",
        "education_records": [],
    })

    await acknowledge_education(
        patient_id,
        EducationAcknowledgementRequest(
            topic="出院用药",
            recipient="patient",
            teach_back="每天早晨服药，出现头晕及时联系医生",
        ),
    )

    state = get_state(patient_id)
    assert state["patient_confirmation_status"] == "confirmed"
    assert "confirm_note" in state["document_chain"]
    assert state["patient_confirmation_evidence"][0]["teach_back"]


@pytest.mark.asyncio
async def test_medication_order_rejects_invalid_state_transition():
    from zhenhu.inpatient.routes.care_management import add_medication_order, update_medication_order
    from zhenhu.inpatient.routes.route_schemas import MedicationOrderRequest, MedicationOrderStatusRequest
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"care-invalid-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    order = _data(await add_medication_order(
        patient_id,
        MedicationOrderRequest(medication="metformin", dose="500 mg", frequency="bid"),
    ))["medication_order"]

    response = await update_medication_order(
        patient_id,
        order["id"],
        MedicationOrderStatusRequest(status="held"),
    )

    assert response.error.code == "INVALID_ORDER_TRANSITION"


@pytest.mark.asyncio
async def test_investigation_order_tracks_ordered_to_completed_lifecycle():
    from zhenhu.inpatient.routes.care_management import add_investigation_order, update_investigation_order
    from zhenhu.inpatient.routes.route_schemas import InvestigationOrderRequest, InvestigationOrderStatusRequest
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"care-investigation-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    order = _data(await add_investigation_order(
        patient_id,
        InvestigationOrderRequest(test_name="serum potassium", reason="diuretic monitoring", priority="urgent"),
    ))["investigation_order"]
    completed = _data(await update_investigation_order(
        patient_id,
        order["id"],
        InvestigationOrderStatusRequest(status="completed", note="result available"),
    ))["investigation_order"]

    assert order["status"] == "ordered"
    assert completed["status"] == "completed"


@pytest.mark.asyncio
async def test_care_write_rejects_a_stale_patient_state_version(client, isolated_state_store):
    from zhenhu.inpatient.routes.state_store import get_state, set_state, update_state

    patient_id = f"care-stale-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    stale_version = get_state(patient_id)["state_version"]
    update_state(patient_id, {"risk_level": "medium"})

    response = await client.post(
        f"/inpatient/{patient_id}/care/medication-orders",
        json={
            "medication": "amlodipine",
            "dose": "5 mg",
            "frequency": "qd",
            "expected_version": stale_version,
        },
        headers={"x-role": "doctor"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_VERSION_CONFLICT"
    assert get_state(patient_id).get("medication_orders", []) == []


@pytest.mark.asyncio
async def test_care_lifecycle_patch_requires_doctor_role(client, isolated_state_store):
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"care-role-{uuid4()}"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})

    response = await client.patch(
        f"/inpatient/{patient_id}/care/medication-orders/not-used",
        json={"status": "active", "note": "unauthorized attempt"},
        headers={"x-role": "nurse"},
    )

    assert response.status_code == 403
