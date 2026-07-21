from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_doctor_can_select_clinical_assistant_modes(client, monkeypatch):
    from zhenhu.inpatient.agent import assistant as assistant_engine

    async def fake_chat(message, role="patient", session_id=None, patient_id="", actor_id=""):
        session_id = session_id or assistant_engine.create_session(role, patient_id, owner_id=actor_id)
        return {"answer": "ok", "assistant_mode": role, "session_id": session_id}

    monkeypatch.setattr(assistant_engine, "chat", fake_chat)
    headers = {"x-role": "doctor", "x-user-id": "mode-doctor"}

    for mode in ("doctor", "pharmacist", "integrative", "patient"):
        response = await client.post(
            "/assistant/chat",
            json={"message": "hello", "assistant_mode": mode},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["assistant_mode"] == mode


@pytest.mark.asyncio
async def test_nurse_mode_policy_rejects_pharmacist(client, monkeypatch):
    from zhenhu.inpatient.agent import assistant as assistant_engine

    async def fake_chat(message, role="patient", session_id=None, patient_id="", actor_id=""):
        session_id = session_id or assistant_engine.create_session(role, patient_id, owner_id=actor_id)
        return {"answer": "ok", "assistant_mode": role, "session_id": session_id}

    monkeypatch.setattr(assistant_engine, "chat", fake_chat)
    headers = {"x-role": "nurse", "x-user-id": "mode-nurse"}

    allowed = await client.post(
        "/assistant/chat",
        json={"message": "hello", "assistant_mode": "patient"},
        headers=headers,
    )
    denied = await client.post(
        "/assistant/chat",
        json={"message": "hello", "assistant_mode": "pharmacist"},
        headers=headers,
    )

    assert allowed.status_code == 200
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_assistant_session_cannot_switch_modes(client, monkeypatch):
    from zhenhu.inpatient.agent import assistant as assistant_engine

    async def fake_chat(message, role="patient", session_id=None, patient_id="", actor_id=""):
        session_id = session_id or assistant_engine.create_session(role, patient_id, owner_id=actor_id)
        return {"answer": "ok", "assistant_mode": role, "session_id": session_id}

    monkeypatch.setattr(assistant_engine, "chat", fake_chat)
    headers = {"x-role": "doctor", "x-user-id": "mode-session-doctor"}
    created = await client.post(
        "/assistant/chat",
        json={"message": "hello", "assistant_mode": "pharmacist"},
        headers=headers,
    )
    session_id = created.json()["data"]["session_id"]

    switched = await client.post(
        "/assistant/chat",
        json={"message": "hello", "assistant_mode": "integrative", "session_id": session_id},
        headers=headers,
    )

    assert switched.status_code == 409


@pytest.mark.asyncio
async def test_public_assistant_is_fixed_to_patient_mode(client, monkeypatch):
    from zhenhu.inpatient.agent import assistant as assistant_engine

    calls = []

    async def fake_stream(message, role="patient", session_id=None, patient_id="", actor_id=""):
        calls.append({
            "message": message,
            "role": role,
            "patient_id": patient_id,
            "actor_id": actor_id,
        })
        session_id = session_id or assistant_engine.create_session(role, patient_id, owner_id=actor_id)
        yield f'data: {{"token":"ok","done":true,"session_id":"{session_id}"}}\n\n'

    monkeypatch.setattr(assistant_engine, "chat_stream", fake_stream)
    response = await client.post(
        "/assistant/public/chat/stream",
        json={"message": "hello", "assistant_mode": "doctor", "patient_id": "must-not-pass"},
        headers={"x-assistant-client": "public-client-0001"},
    )

    assert response.status_code == 200
    assert calls == [{
        "message": "hello",
        "role": "patient",
        "patient_id": "",
        "actor_id": "public:public-client-0001",
    }]


@pytest.mark.asyncio
async def test_quick_questions_follow_authorized_mode(client):
    doctor = await client.get(
        "/assistant/quick-questions?assistant_mode=integrative&context=general",
        headers={"x-role": "doctor", "x-user-id": "quick-doctor"},
    )
    nurse_denied = await client.get(
        "/assistant/quick-questions?assistant_mode=integrative&context=general",
        headers={"x-role": "nurse", "x-user-id": "quick-nurse"},
    )
    public = await client.get("/assistant/public/quick-questions")

    assert doctor.status_code == 200
    assert doctor.json()["data"]["assistant_mode"] == "integrative"
    assert nurse_denied.status_code == 403
    assert public.status_code == 200
    assert public.json()["data"]["assistant_mode"] == "patient"
