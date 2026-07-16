"""Harness 安全护栏测试。合并迁入。"""

import pytest, asyncio
# 合并迁入: 替换 app.src.zhenhu 路径
from zhenhu.inpatient.agent.harness import (
    check_source_type,
    fallback_to_template,
    validate_handoff_items,
)


def test_validate_valid_items():
    items = [{"type": "medication", "content": "降压药服用方案"}]
    valid, errors = validate_handoff_items(items)
    assert len(valid) == 1
    assert len(errors) == 0


def test_validate_invalid_item_empty_content():
    items = [{"type": "medication", "content": "ab"}]
    valid, errors = validate_handoff_items(items)
    assert len(errors) == 1


def test_source_type_knowledge():
    results = [{"chunk_id": "c1", "score": 0.9}]
    result = check_source_type(results, threshold=0.6)
    assert result["source_type"] == "source_knowledge"


def test_source_type_none():
    result = check_source_type([], threshold=0.6)
    assert result["source_type"] == "source_none"


def test_source_type_none_low_score():
    results = [{"chunk_id": "c1", "score": 0.3}]
    result = check_source_type(results, threshold=0.6)
    assert result["source_type"] == "source_none"


def test_fallback_uses_template():
    template = {"handoff_instructions": [{"type": "medication", "content": "降压药方案"}]}
    result = fallback_to_template(template)
    assert result["source_type"] == "source_none"
    assert len(result["handoff_items"]) == 1


def test_fallback_empty_template():
    result = fallback_to_template({})
    assert result["handoff_items"] == []


class TestBridge:
    """臻护桥接测试(无真实服务时返回降级状态)。"""

    def test_bridge_discharge_unavailable(self):
        from zhenhu.inpatient.hooks.zhenhu_bridge import bridge_discharge_to_zhenhu

        result = asyncio.run(bridge_discharge_to_zhenhu([], "test-001"))
        assert result["status"] == "bridge_unavailable"

    def test_bridge_search_unavailable(self):
        from zhenhu.inpatient.hooks.zhenhu_bridge import bridge_search_knowledge

        results = asyncio.run(bridge_search_knowledge("test"))
        assert results == []

    def test_bridge_patient_unavailable(self):
        from zhenhu.inpatient.hooks.zhenhu_bridge import bridge_patient_summary

        summary = asyncio.run(bridge_patient_summary("test"))
        assert summary["name"] == "***"


def test_validate_empty_list():
    valid, errors = validate_handoff_items([])
    assert valid == []
    assert errors == []

def test_validate_missing_field():
    items = [{"type": "medication"}]
    valid, errors = validate_handoff_items(items)
    assert len(errors) == 1

def test_source_score_boundary():
    results = [{"score": 0.59}]
    result = check_source_type(results, threshold=0.6)
    assert result["source_type"] == "source_none"

def test_source_score_exact_threshold():
    results = [{"score": 0.6}]
    result = check_source_type(results, threshold=0.6)
    assert result["source_type"] == "source_knowledge"


# ============================================================================
# 事件驱动路由测试
# ============================================================================


def test_event_routing_after_monitoring_discharge():
    """查房完成+approved → discharge。"""
    from zhenhu.inpatient.agent.graph import after_monitoring

    state = {
        "document_chain": ["intake_note", "risk_assessment", "daily_round_note"],
        "discharge_decision": "approved",
        "lab_results": [],
        "reviewed_labs": [],
        "disease_template": {},
        "vital_signs": [],
        "risk_level": "low",
    }
    result = after_monitoring(state)
    assert result == "discharge"


def test_event_routing_after_monitoring_stay():
    """查房完成+未approved → monitoring。"""
    from zhenhu.inpatient.agent.graph import after_monitoring

    state = {
        "document_chain": ["intake_note", "risk_assessment", "daily_round_note"],
        "discharge_decision": "pending",
        "lab_results": [],
        "reviewed_labs": [],
        "disease_template": {},
        "vital_signs": [],
        "risk_level": "low",
    }
    result = after_monitoring(state)
    assert result == "monitoring"


def test_event_routing_after_monitoring_to_triage():
    """intake完成但无risk_assessment → triage。"""
    from zhenhu.inpatient.agent.graph import after_monitoring

    state = {
        "document_chain": ["intake_note"],
        "discharge_decision": "approved",
    }
    result = after_monitoring(state)
    assert result == "triage"


def test_event_routing_after_monitoring_default():
    """无doc chain → 默认monitoring。"""
    from zhenhu.inpatient.agent.graph import after_monitoring

    state = {"document_chain": [], "discharge_decision": "approved"}
    result = after_monitoring(state)
    assert result == "monitoring"


# ============================================================================
# PlanDefinition 桥接测试
# ============================================================================


def test_bridge_plan_definition_construct():
    """验证bridge传入template时构造PlanDefinition。"""
    from zhenhu.inpatient.hooks.zhenhu_bridge import bridge_discharge_to_zhenhu

    items = [
        {"type": "medication", "content": "降压药方案"},
        {"type": "monitoring", "content": "每日自测血压"},
    ]
    template = {"name": "高血压"}
    result = asyncio.run(bridge_discharge_to_zhenhu(items, "test-001", template))
    assert result["status"] == "bridge_unavailable"


def test_bridge_plan_definition_no_template():
    """无template参数时仍能降级。"""
    from zhenhu.inpatient.hooks.zhenhu_bridge import bridge_discharge_to_zhenhu

    result = asyncio.run(bridge_discharge_to_zhenhu([], "test-002"))
    assert result["status"] == "bridge_unavailable"


# ============================================================================
# AgentLoop + 熔断器 + 审计钩子 测试
# ============================================================================


def test_circuit_breaker_closed_initially():
    """初始状态为 CLOSED。"""
    from zhenhu.inpatient.agent.harness import CircuitBreaker

    cb = CircuitBreaker()
    assert cb._state == "CLOSED"


def test_circuit_breaker_opens_after_failures():
    """连续失败后熔断器打开。"""
    from zhenhu.inpatient.agent.harness import CircuitBreaker, CircuitBreakerOpenError

    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
    for _ in range(2):
        try:
            cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
    with pytest.raises(CircuitBreakerOpenError):
        cb.call(lambda: 1)


def test_agent_loop_push_and_gen_input():
    """push事件 + gen_input策略路由。"""
    from zhenhu.inpatient.agent.loop import AgentLoop, AgentEvent

    loop = AgentLoop()
    loop.push(AgentEvent(event_type="vital_sign"))
    state = loop.gen_input("new_admission")
    assert state["phase"] == "admission"


def test_agent_loop_traces_limit():
    """traces 属性最多保留 100 条。"""
    from zhenhu.inpatient.agent.loop import AgentLoop

    loop = AgentLoop()
    for i in range(150):
        loop._traces.append(type("obj", (object,), {"turn_id": str(i)})())
    assert len(loop.traces) == 100


def test_audit_hook():
    """on_node_enter/exit 正确记录事件。"""
    from zhenhu.inpatient.agent.harness import AgentAuditHook

    hook = AgentAuditHook()
    hook.on_node_enter("admission", {"phase": "start"})
    hook.on_node_exit("admission", {"phase": "admission"})
    assert len(hook.events) == 2
