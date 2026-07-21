"""Nursing task completion, audit, idempotency, and KPI regression tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select


def _seed_patient(*, department: str = "cardiology") -> str:
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"nursing-task-{uuid4()}"
    set_state(patient_id, {
        "patient_id": patient_id,
        "phase": "monitoring",
        "patient_data": {"name": "护理测试患者"},
        "patient_access": {"department": department},
        "disease_template": {
            "name": "心力衰竭",
            "department": department,
            "monitoring_interval_hours": 1,
        },
        "vital_signs": [{
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
            "heart_rate": 82,
            "spo2": 96,
        }],
        "clinical_alerts": [],
        "nursing_records": [],
        "nursing_task_completions": [],
    })
    return patient_id


async def _vital_task(client, patient_id: str, headers: dict[str, str]) -> tuple[dict, int]:
    response = await client.get("/nurse/tasks", headers=headers)
    assert response.status_code == 200
    patient = next(item for item in response.json()["data"]["tasks"] if item["patient_id"] == patient_id)
    task = next(item for item in patient["task_items"] if item["task_type"] == "vital_signs")
    return task, patient["state_version"]


@pytest.mark.asyncio
async def test_nurse_completes_task_once_and_kpi_reads_same_audited_fact(client, isolated_state_store):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.models import AuditLog
    from zhenhu.inpatient.routes.state_store import get_state, update_state

    patient_id = _seed_patient()
    headers = {
        "x-role": "nurse",
        "x-user-id": "nurse-1001",
        "x-user-name": "%E6%B5%8B%E8%AF%95%E6%8A%A4%E5%A3%AB",
        "x-department": "cardiology",
    }
    task, version = await _vital_task(client, patient_id, headers)
    payload = {
        "task_type": task["task_type"],
        "task_key": task["task_key"],
        "note": "已完成床旁测量并核对",
        "expected_version": version,
    }
    write_headers = {**headers, "Idempotency-Key": f"complete-{patient_id}"}

    completed = await client.post(
        f"/nurse/tasks/{patient_id}/complete", json=payload, headers=write_headers
    )
    replay = await client.post(
        f"/nurse/tasks/{patient_id}/complete", json=payload, headers=write_headers
    )

    assert completed.status_code == 200
    assert completed.json()["data"]["completion"]["task_key"] == task["task_key"]
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    state = get_state(patient_id)
    assert state is not None
    assert len(state["nursing_task_completions"]) == 1

    async with main.async_session_factory() as session:
        audits = list((await session.scalars(
            select(AuditLog).where(AuditLog.action_type == "nursing_task_completed")
        )).all())
    assert len(audits) == 1
    assert audits[0].actor_role == "nurse"
    assert audits[0].action_detail["task_key"] == task["task_key"]

    update_state(patient_id, {"phase": "discharge"})
    kpi = await client.get("/nurse/kpi", headers=headers)
    assert kpi.status_code == 200
    data = kpi.json()["data"]
    assert data["completed_tasks"] == 1
    assert data["by_type"]["vital_signs"] == {"open": 0, "completed": 1}
    assert data["recent_completions"][0]["patient_id"] == patient_id


@pytest.mark.asyncio
async def test_nursing_kpi_is_readable_by_department_director(client, isolated_state_store):
    _seed_patient()

    response = await client.get(
        "/nurse/kpi",
        headers={"x-role": "doctor", "x-title": "%E7%A7%91%E4%B8%BB%E4%BB%BB", "x-user-id": "director-1", "x-department": "cardiology"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["scope"]["patient_count"] == 1


@pytest.mark.asyncio
async def test_department_checklist_defaults_to_the_nurses_department(client, isolated_state_store):
    response = await client.get(
        "/nurse/department-checklist",
        headers={"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "%E5%BF%83%E5%86%85%E7%A7%91"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["department"] == "心内科"
    assert "出入量记录" in data["checklist"][1]


@pytest.mark.asyncio
async def test_checklist_execution_projects_rule_status_and_persists_shift_confirmation(client, isolated_state_store):
    _seed_patient(department="心内科")
    headers = {"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "%E5%BF%83%E5%86%85%E7%A7%91"}

    before = await client.get("/nurse/checklist-execution", headers=headers)
    assert before.status_code == 200
    rule = before.json()["data"]["rules"][0]
    assert rule["rule_id"]
    assert rule["status"] in {"action_required", "not_triggered"}

    confirmed = await client.post(
        f"/nurse/checklist-rules/{rule['rule_id']}/confirm",
        json={"note": "已完成本班制度核对"},
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "confirmed"

    after = await client.get("/nurse/checklist-execution", headers=headers)
    confirmed_rule = next(item for item in after.json()["data"]["rules"] if item["rule_id"] == rule["rule_id"])
    assert confirmed_rule["status"] == "confirmed"
    assert confirmed_rule["confirmation"]["actor_id"] == "nurse-1"


@pytest.mark.asyncio
async def test_completion_requires_nurse_role_and_patient_department(client, isolated_state_store):
    patient_id = _seed_patient()
    nurse_headers = {"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "cardiology"}
    task, version = await _vital_task(client, patient_id, nurse_headers)
    payload = {"task_type": task["task_type"], "task_key": task["task_key"], "expected_version": version}

    doctor = await client.post(
        f"/nurse/tasks/{patient_id}/complete",
        json=payload,
        headers={"x-role": "doctor", "x-user-id": "doctor-1", "x-department": "cardiology"},
    )
    other_department = await client.post(
        f"/nurse/tasks/{patient_id}/complete",
        json=payload,
        headers={"x-role": "nurse", "x-user-id": "nurse-2", "x-department": "oncology"},
    )

    assert doctor.status_code == 403
    assert other_department.status_code == 403


@pytest.mark.asyncio
async def test_completion_rejects_stale_state_version(client, isolated_state_store):
    from zhenhu.inpatient.routes.state_store import update_state

    patient_id = _seed_patient()
    headers = {"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "cardiology"}
    task, version = await _vital_task(client, patient_id, headers)
    update_state(patient_id, {"risk_level": "high"})

    response = await client.post(
        f"/nurse/tasks/{patient_id}/complete",
        json={"task_type": task["task_type"], "task_key": task["task_key"], "expected_version": version},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_manual_nursing_records_are_not_republished_as_pending_actions(client, isolated_state_store):
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    patient_id = _seed_patient()
    state = get_state(patient_id)
    assert state is not None
    state["nursing_records"] = [{"nursing_actions": "已完成翻身和皮肤检查", "source": "manual"}]
    set_state(patient_id, state)
    headers = {"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "cardiology"}

    response = await client.get("/nurse/tasks", headers=headers)

    patient = next(item for item in response.json()["data"]["tasks"] if item["patient_id"] == patient_id)
    assert patient["pending_nursing_actions"] == []
    assert all(item["task_type"] != "nursing_action" for item in patient["task_items"])


@pytest.mark.asyncio
async def test_task_board_uses_four_hour_default_monitoring_interval(client, isolated_state_store):
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    patient_id = _seed_patient()
    state = get_state(patient_id)
    assert state is not None
    state["disease_template"].pop("monitoring_interval_hours")
    state["vital_signs"][-1]["timestamp"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    set_state(patient_id, state)
    headers = {"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "cardiology"}

    response = await client.get("/nurse/tasks", headers=headers)

    patient = next(item for item in response.json()["data"]["tasks"] if item["patient_id"] == patient_id)
    assert patient["vital_signs_due"] is False


@pytest.mark.asyncio
async def test_nursing_entry_updates_vital_fact_and_clears_overdue_queue(client, isolated_state_store, monkeypatch):
    from zhenhu.inpatient.agent import loop as agent_loop
    from zhenhu.inpatient.routes.state_store import get_state

    patient_id = _seed_patient()
    state = get_state(patient_id)
    assert state is not None

    class StubLoop:
        traces = []

        def __init__(self):
            self.event_types: list[str] = []
            self.collect_modes: list[bool] = []

        async def plan_turn(self, current_state):
            raise AssertionError("nursing entry must not replay the admission graph")

        async def plan_monitoring_turn(self, current_state, *, event_type: str, collect: bool = True):
            self.event_types.append(event_type)
            self.collect_modes.append(collect)
            return current_state

    loop = StubLoop()
    monkeypatch.setattr(agent_loop, "get_patient_loop", lambda _: loop)
    headers = {"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "cardiology"}
    response = await client.post(
        f"/inpatient/admissions/{patient_id}/nursing",
        json={
            "vital_signs": {"heart_rate": 74, "spo2": 98},
            "intake_ml": 200,
            "output_ml": 150,
            "nursing_actions": "完成床旁测量",
            "expected_version": state["state_version"],
        },
        headers=headers,
    )

    assert response.status_code == 200
    persisted = get_state(patient_id)
    assert persisted is not None
    assert persisted["vital_signs"][-1]["heart_rate"] == 74
    assert persisted["vital_signs"][-1]["source"] == "nursing_record"
    assert persisted["nursing_records"][-1]["source"] == "manual"
    assert loop.event_types == ["nursing"]
    assert loop.collect_modes == [False]
    overdue = await client.get("/monitoring/overdue", headers=headers)
    overdue_ids = {item["patient_id"] for item in overdue.json()["data"]["patients"]}
    assert patient_id not in overdue_ids
