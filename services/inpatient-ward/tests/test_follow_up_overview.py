from datetime import datetime, timezone

import pytest

from zhenhu.inpatient.routes.care_management import _follow_up_risk, _follow_up_task, _matches_follow_up_status


def test_follow_up_task_marks_open_past_due_task_as_overdue():
    task = _follow_up_task({"id": "t-1", "title": "复诊", "status": "pending", "due_at": "2026-01-01T09:00:00+00:00"}, datetime(2026, 1, 2, tzinfo=timezone.utc))

    assert task["is_open"] is True
    assert task["is_overdue"] is True


def test_follow_up_risk_is_explicitly_rule_based():
    risk, basis = _follow_up_risk({"risk_level": "medium", "patient_history": {"prior_hospitalization": True, "comorbidities": ["a", "b"]}})

    assert risk == "medium"
    assert "住院期间中风险分层" in basis
    assert _matches_follow_up_status({"pending_task_count": 1, "overdue_task_count": 0, "abnormal_feedback_count": 0, "readmission_risk": "medium"}, "pending")


@pytest.mark.asyncio
async def test_follow_up_overview_uses_only_canonical_openable_states(monkeypatch, client):
    from zhenhu.inpatient.routes import state_store

    monkeypatch.setattr(state_store, "list_states", lambda: {})

    response = await client.get("/inpatient/follow-up-overview", headers={"x-role": "doctor", "x-user-id": "follow-up-doctor"})

    assert response.status_code == 200
    assert response.json()["data"]["patients"] == []
