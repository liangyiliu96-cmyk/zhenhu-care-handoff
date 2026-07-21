"""Signed discharge PDF export audit regressions."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_signed_discharge_export_is_doctor_only_and_audited(client, isolated_state_store, monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import outbox
    from zhenhu.inpatient.models import AuditLog
    from zhenhu.inpatient.routes.state_store import set_state

    async def skip_delivery(event_id: str):
        return False

    monkeypatch.setattr(outbox, "deliver_outbox_event", skip_delivery)
    patient_id = f"pdf-export-{uuid4()}"
    set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "confirm",
        "discharge_sign_status": "signed",
        "patient_access": {"department": "cardiology"},
    })
    doctor_headers = {
        "x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology",
    }

    nurse = await client.post(
        f"/inpatient/{patient_id}/discharge-summary/export-audit",
        headers={"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "cardiology"},
    )
    doctor = await client.post(
        f"/inpatient/{patient_id}/discharge-summary/export-audit", headers=doctor_headers,
    )

    assert nurse.status_code == 403
    assert doctor.status_code == 200
    async with main.async_session_factory() as session:
        audit = await session.scalar(
            select(AuditLog).where(AuditLog.action_type == "discharge_pdf_export_requested")
        )
    assert audit is not None
    assert audit.actor_role == "doctor"
    assert audit.action_detail["patient_id"] == patient_id
    assert audit.action_detail["discharge_sign_status"] == "signed"


@pytest.mark.asyncio
async def test_unsigned_discharge_summary_allows_audited_draft_but_rejects_final_export(client, isolated_state_store):
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"pdf-unsigned-{uuid4()}"
    set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "review",
        "discharge_sign_status": "pending",
        "patient_access": {"department": "cardiology"},
    })

    final_response = await client.post(
        f"/inpatient/{patient_id}/discharge-summary/export-audit",
        headers={"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"},
    )
    draft_response = await client.post(
        f"/inpatient/{patient_id}/discharge-summary/export-audit",
        json={"export_kind": "draft"},
        headers={"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"},
    )

    assert final_response.status_code == 409
    assert final_response.json()["error"]["message"] == "出院小结尚未完成医生签字"
    assert draft_response.status_code == 200
    assert draft_response.json()["data"]["export_kind"] == "draft"
