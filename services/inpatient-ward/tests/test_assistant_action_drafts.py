"""Clinical assistant suggestion to doctor-approved action workflow."""

from __future__ import annotations

from uuid import uuid4

import pytest


def _assistant_session(patient_id: str, actor_id: str, answer: str) -> str:
    from zhenhu.inpatient.agent.assistant import add_message, create_session

    session_id = create_session("doctor", patient_id, owner_id=actor_id)
    add_message(session_id, "user", "请给出下一步建议")
    add_message(session_id, "assistant", answer)
    return session_id


@pytest.mark.asyncio
async def test_doctor_can_edit_and_approve_assistant_medication_draft(
    client, isolated_state_store, monkeypatch,
):
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    patient_id = f"assistant-draft-{uuid4()}"
    actor_id = "doctor-action-draft"
    answer = "建议使用氨氯地平 5 mg，每日一次口服，用于控制血压。"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    session_id = _assistant_session(patient_id, actor_id, answer)

    async def extracted(_source_text: str):
        return [{
            "draft_type": "medication_order",
            "payload": {
                "medication": "氨氯地平", "dose": "5 mg", "frequency": "qd",
                "route": "PO", "indication": "控制血压",
            },
            "rationale": "血压仍高于目标值",
        }]

    monkeypatch.setattr(
        "zhenhu.inpatient.routes.assistant_action_drafts.extract_action_draft_suggestions",
        extracted,
    )
    headers = {"x-role": "doctor", "x-user-id": actor_id}
    version = get_state(patient_id)["state_version"]
    generated = await client.post(
        f"/inpatient/{patient_id}/assistant-action-drafts/generate",
        json={
            "session_id": session_id,
            "source_text": answer,
            "citations": [{"title": "高血压指南", "excerpt": "可使用长效钙通道阻滞剂", "version": "2024"}],
            "expected_version": version,
        },
        headers=headers,
    )
    assert generated.status_code == 200
    generated_data = generated.json()["data"]
    draft = generated_data["drafts"][0]
    assert draft["status"] == "pending"
    assert draft["citations"][0]["version"] == "2024"
    assert get_state(patient_id).get("medication_orders", []) == []

    edited = await client.patch(
        f"/inpatient/{patient_id}/assistant-action-drafts/{draft['id']}",
        json={
            "payload": {**draft["payload"], "dose": "2.5 mg"},
            "rationale": "高龄患者从低剂量开始",
            "expected_version": generated_data["state_version"],
        },
        headers=headers,
    )
    assert edited.status_code == 200
    edited_data = edited.json()["data"]
    assert edited_data["draft"]["payload"]["dose"] == "2.5 mg"

    approval_body = {"comment": "已核对肾功能和既往用药", "expected_version": edited_data["state_version"]}
    approval_headers = {**headers, "Idempotency-Key": f"approve-{draft['id']}"}
    approved = await client.post(
        f"/inpatient/{patient_id}/assistant-action-drafts/{draft['id']}/approve",
        json=approval_body,
        headers=approval_headers,
    )
    replayed = await client.post(
        f"/inpatient/{patient_id}/assistant-action-drafts/{draft['id']}/approve",
        json=approval_body,
        headers=approval_headers,
    )

    assert approved.status_code == 200
    assert replayed.status_code == 200
    assert replayed.json()["data"]["idempotent"] is True
    state = get_state(patient_id)
    assert state["assistant_action_drafts"][0]["status"] == "approved"
    assert len(state["medication_orders"]) == 1
    assert state["medication_orders"][0]["status"] == "active"
    assert state["medication_orders"][0]["source_draft_id"] == draft["id"]


@pytest.mark.asyncio
async def test_investigation_draft_approval_creates_formal_order(client, isolated_state_store, monkeypatch):
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    patient_id = f"assistant-investigation-{uuid4()}"
    actor_id = "doctor-investigation"
    answer = "建议今天急查血钾，评估利尿治疗后的电解质变化。"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    session_id = _assistant_session(patient_id, actor_id, answer)

    async def extracted(_source_text: str):
        return [{
            "draft_type": "investigation_order",
            "payload": {
                "test_name": "血钾", "priority": "urgent", "reason": "利尿后电解质监测",
                "timing": "today", "instructions": "采血前核对补钾治疗",
            },
            "rationale": "利尿剂可能导致低钾",
        }]

    monkeypatch.setattr(
        "zhenhu.inpatient.routes.assistant_action_drafts.extract_action_draft_suggestions",
        extracted,
    )
    headers = {"x-role": "doctor", "x-user-id": actor_id}
    response = await client.post(
        f"/inpatient/{patient_id}/assistant-action-drafts/generate",
        json={
            "session_id": session_id, "source_text": answer, "citations": [],
            "expected_version": get_state(patient_id)["state_version"],
        },
        headers=headers,
    )
    data = response.json()["data"]
    draft = data["drafts"][0]
    approved = await client.post(
        f"/inpatient/{patient_id}/assistant-action-drafts/{draft['id']}/approve",
        json={"comment": "同意", "expected_version": data["state_version"]},
        headers=headers,
    )

    assert approved.status_code == 200
    order = get_state(patient_id)["investigation_orders"][0]
    assert order["test_name"] == "血钾"
    assert order["status"] == "ordered"
    assert order["priority"] == "urgent"


@pytest.mark.asyncio
async def test_rejected_follow_up_draft_does_not_create_task(client, isolated_state_store, monkeypatch):
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    patient_id = f"assistant-reject-{uuid4()}"
    actor_id = "doctor-reject"
    answer = "建议 2026-08-01 09:00 随访血压。"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    session_id = _assistant_session(patient_id, actor_id, answer)

    async def extracted(_source_text: str):
        return [{
            "draft_type": "follow_up_task",
            "payload": {"title": "随访血压", "due_at": "2026-08-01T09:00:00+08:00", "assignee": "随访护士"},
            "rationale": "观察降压效果",
        }]

    monkeypatch.setattr(
        "zhenhu.inpatient.routes.assistant_action_drafts.extract_action_draft_suggestions",
        extracted,
    )
    headers = {"x-role": "doctor", "x-user-id": actor_id}
    generated = await client.post(
        f"/inpatient/{patient_id}/assistant-action-drafts/generate",
        json={
            "session_id": session_id, "source_text": answer, "citations": [],
            "expected_version": get_state(patient_id)["state_version"],
        },
        headers=headers,
    )
    data = generated.json()["data"]
    draft = data["drafts"][0]
    rejected = await client.post(
        f"/inpatient/{patient_id}/assistant-action-drafts/{draft['id']}/reject",
        json={"comment": "已有同类随访安排", "expected_version": data["state_version"]},
        headers=headers,
    )

    assert rejected.status_code == 200
    state = get_state(patient_id)
    assert state["assistant_action_drafts"][0]["status"] == "rejected"
    assert state.get("follow_up_tasks", []) == []


@pytest.mark.asyncio
async def test_action_drafts_reject_nurse_and_unbound_assistant_text(client, isolated_state_store):
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    patient_id = f"assistant-access-{uuid4()}"
    actor_id = "doctor-access"
    answer = "建议复查血常规。"
    set_state(patient_id, {"patient_id": patient_id, "phase": "monitoring"})
    session_id = _assistant_session(patient_id, actor_id, answer)

    nurse = await client.get(
        f"/inpatient/{patient_id}/assistant-action-drafts",
        headers={"x-role": "nurse", "x-user-id": "nurse-access"},
    )
    forged = await client.post(
        f"/inpatient/{patient_id}/assistant-action-drafts/generate",
        json={
            "session_id": session_id, "source_text": "伪造的助手建议", "citations": [],
            "expected_version": get_state(patient_id)["state_version"],
        },
        headers={"x-role": "doctor", "x-user-id": actor_id},
    )

    assert nurse.status_code == 403
    assert forged.status_code == 409
    assert get_state(patient_id).get("assistant_action_drafts", []) == []
