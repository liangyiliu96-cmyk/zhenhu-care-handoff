from __future__ import annotations

import pytest
from fastapi import Request


def _request(user_info: dict) -> Request:
    request = Request({"type": "http", "headers": []})
    request.state.user_info = user_info
    return request


@pytest.mark.asyncio
async def test_regular_clinician_org_response_includes_only_own_department_leadership(monkeypatch):
    from zhenhu.inpatient.routes import admin, state_store

    staff = [
        {"name": "心内科主任", "department": "心内科", "role": "doctor", "title": "科主任"},
        {"name": "心内科护士长", "department": "心内科", "role": "nurse", "title": "护士长"},
        {"name": "心内科医生", "department": "心内科", "role": "doctor", "title": "主治医师"},
        {"name": "呼吸科主任", "department": "呼吸科", "role": "doctor", "title": "科主任"},
        {"name": "呼吸科护士长", "department": "呼吸科", "role": "nurse", "title": "护士长"},
    ]
    monkeypatch.setattr(state_store, "get_org_all", lambda: staff)
    monkeypatch.setattr(state_store, "get_org_by_department", lambda department: {
        "department": department,
        "doctors": [member for member in staff if member["department"] == department and member["role"] == "doctor"],
        "nurses": [member for member in staff if member["department"] == department and member["role"] == "nurse"],
    })

    response = await admin.get_org_structure(_request({
        "role": "doctor",
        "title": "主治医师",
        "department": "心内科",
    }))

    leadership = response.data["leadership"]
    assert leadership["department"] == "心内科"
    assert leadership["medical_director"]["name"] == "心内科主任"
    assert leadership["head_nurse"]["name"] == "心内科护士长"
    assert all(member["department"] == "心内科" for member in response.data["department_chain"]["team"])


@pytest.mark.asyncio
async def test_department_manager_org_response_uses_own_department_leadership(monkeypatch):
    from zhenhu.inpatient.routes import admin, state_store

    staff = [
        {"name": "心内科主任", "department": "心内科", "role": "doctor", "title": "科主任"},
        {"name": "心内科护士长", "department": "心内科", "role": "nurse", "title": "护士长"},
        {"name": "呼吸科主任", "department": "呼吸科", "role": "doctor", "title": "科主任"},
        {"name": "呼吸科护士长", "department": "呼吸科", "role": "nurse", "title": "护士长"},
    ]
    monkeypatch.setattr(state_store, "get_org_all", lambda: staff)
    monkeypatch.setattr(state_store, "get_org_summary", lambda: {"total_departments": 2, "total_staff": 4})

    response = await admin.get_org_structure(_request({
        "role": "nurse",
        "title": "护士长",
        "department": "呼吸科",
    }))

    leadership = response.data["leadership"]
    assert response.data["your_department"] == "呼吸科"
    assert leadership["medical_director"]["name"] == "呼吸科主任"
    assert leadership["head_nurse"]["name"] == "呼吸科护士长"
