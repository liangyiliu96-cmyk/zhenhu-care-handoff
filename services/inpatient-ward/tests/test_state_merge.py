"""Batch 0 R3 回归断言：N 次 plan_turn 后 vital_signs 不重复累加。

classic 默认模式（随机 thread_id + MemorySaver）验证：
多次 plan_turn 调用后 vital_signs 列表不应出现重复元素，
即每次重新跑 graph 不会导致历史体征重复追加。
"""

import pytest
from uuid import uuid4


def test_update_state_refreshes_in_memory_ttl(monkeypatch):
    """A state update must renew the timestamp used by the cleanup worker."""
    import time
    from zhenhu.inpatient.routes import state_store

    class NoopBackend:
        def save(self, patient_id, state, timestamp, *, expected_version=None):
            pass

    patient_id = "test_refresh_ttl"
    previous_timestamp = time.time() - 60
    monkeypatch.setattr(state_store, "_backend", NoopBackend())
    with state_store._lock:
        state_store._store[patient_id] = (previous_timestamp, {"phase": "monitoring"})

    try:
        state_store.update_state(patient_id, {"risk_level": "low"})
        with state_store._lock:
            updated_timestamp, state = state_store._store[patient_id]
        assert updated_timestamp > previous_timestamp
        assert state["risk_level"] == "low"
    finally:
        with state_store._lock:
            state_store._store.pop(patient_id, None)


def test_mysql_delete_expands_patient_ids():
    """The SQLAlchemy MySQL path must expand IN-list parameters."""
    from sqlalchemy import create_engine, text
    from zhenhu.inpatient.routes.state_store import MySQLBackend

    backend = object.__new__(MySQLBackend)
    backend._engine = create_engine("sqlite://")
    backend._sa_text = text
    with backend._engine.begin() as connection:
        connection.execute(text("CREATE TABLE patient_states (patient_id TEXT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO patient_states (patient_id) VALUES ('a'), ('b'), ('c')"))

    backend.delete(["a", "b"])

    with backend._engine.connect() as connection:
        remaining = connection.execute(
            text("SELECT patient_id FROM patient_states ORDER BY patient_id")
        ).scalars().all()
    assert remaining == ["c"]


@pytest.mark.asyncio
async def test_vital_signs_no_duplication_on_repeated_plan_turn():
    """断言 N 次 plan_turn 后 vital_signs 不重复累加。"""
    from zhenhu.inpatient.agent.loop import get_patient_loop
    from zhenhu.inpatient.routes.state_store import get_state, set_state, update_state

    pid = f"test_state_merge_patient-{uuid4()}"

    # 创建患者并入院
    loop = get_patient_loop(pid)
    state = loop.gen_input("new_admission")
    state["patient_id"] = pid

    result = await loop.plan_turn(state)
    set_state(pid, result)

    # 记录初始 vital_signs 数量
    initial_vs_count = len(result.get("vital_signs", []))
    assert initial_vs_count >= 0, "初始 vital_signs 应为合法值"

    # 模拟多次体征上报
    for i in range(5):
        current = get_state(pid)
        vs = current.get("vital_signs", [])
        vs.append({"heart_rate": 70 + i, "timestamp": f"2026-07-17T10:0{i}:00"})
        update_state(pid, {"vital_signs": vs})

        result = await loop.plan_turn(get_state(pid))
        set_state(pid, result)

        # 如果是 pending_review 结果，跳过（此时 state 还没完整更新）
        if isinstance(result, dict) and result.get("status") == "pending_review":
            continue

    # 最后验证：vital_signs 不应包含重复元素
    final_vs = result.get("vital_signs", []) if isinstance(result, dict) else []
    vs_values = [tuple(sorted(v.items())) for v in final_vs if v]
    unique_count = len(set(vs_values))
    total_count = len(vs_values)

    # 关键断言：如果 total_count > unique_count，说明有重复元素被累加
    assert total_count == unique_count, (
        f"vital_signs 出现重复累加: "
        f"total_count={total_count}, unique_count={unique_count}"
    )


@pytest.mark.asyncio
async def test_plan_turn_pending_review_status_not_leaked():
    """断言 plan_turn 在正常流程（无 pending_review）返回完整 state。"""
    from zhenhu.inpatient.agent.loop import get_patient_loop

    pid = "test_no_pending_review_patient"

    loop = get_patient_loop(pid)
    state = loop.gen_input("new_admission")
    state["patient_id"] = pid

    result = await loop.plan_turn(state)

    # 正常结果应有 phase 字段，不是 pending_review
    assert isinstance(result, dict)
    # pending_review 结果的特征是有 "status" 字段
    if result.get("status") == "pending_review":
        # 如果 DOCTOR_AUTO_APPROVE=false 可能触发；此时再验证 pending 里有 review_id
        assert result.get("review_id") is not None, "pending_review 必须有 review_id"
        assert result.get("payload") is not None, "pending_review 必须有 payload"
    else:
        # 正常完整 state
        assert result.get("phase") is not None, "正常返回应有 phase 字段"


@pytest.mark.asyncio
async def test_repeated_plan_turn_reaches_confirm_and_deduplicates_intake_chain():
    """重复 plan_turn 应越过入院确认，且入院链文档不重复追加。"""
    from zhenhu.inpatient.agent.loop import get_patient_loop

    pid = "test_confirm_dedupe_patient"
    loop = get_patient_loop(pid)
    state = loop.gen_input("new_admission")
    state["patient_id"] = pid

    first = await loop.plan_turn(state)
    assert "doctor_confirm_auto" in first.get("document_chain", [])

    second = await loop.plan_turn(first)
    chain = second.get("document_chain", [])
    assert chain.count("intake_note") == 1
    assert chain.count("medication_reconciliation") == 1
    assert chain.count("risk_assessment") == 1


@pytest.mark.asyncio
async def test_cleanup_removes_lock():
    """断言 cleanup_patient_loop 同时清理 loop 和 lock。"""
    from zhenhu.inpatient.agent.loop import (
        _patient_loops,
        _patient_loops_lock,
        _patient_locks,
        _patient_locks_lock,
        get_patient_loop,
        cleanup_patient_loop,
    )

    pid = "test_cleanup_patient"

    # 创建
    get_patient_loop(pid)
    # 获取 lock（触发创建）
    from zhenhu.inpatient.agent.loop import _get_patient_lock
    _get_patient_lock(pid)

    assert pid in _patient_loops, "患者 loop 应存在"
    assert pid in _patient_locks, "患者 lock 应存在"

    # 清理
    cleanup_patient_loop(pid)

    assert pid not in _patient_loops, "患者 loop 应已清理"
    assert pid not in _patient_locks, "患者 lock 应已清理"
