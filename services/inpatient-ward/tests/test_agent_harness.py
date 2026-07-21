"""Harness 安全护栏测试。合并迁入。"""

import pytest, asyncio
# 合并迁入: 替换 app.src.zhenhu 路径
from zhenhu.inpatient.agent.harness import (
    check_source_type,
    fallback_to_template,
    validate_llm_output,
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


def test_validate_llm_output_keeps_only_valid_handoff_items():
    valid, errors = validate_llm_output("handoff", [
        {"type": "followup", "content": "七日内心内科复诊并携带血压记录"},
        {"type": "unsupported", "content": "this must be rejected"},
        "not-an-object",
    ])

    assert valid == [{"type": "followup", "content": "七日内心内科复诊并携带血压记录"}]
    assert len(errors) == 2


def test_validate_llm_output_rejects_unsafe_medication_draft():
    valid, errors = validate_llm_output("medication_adjustment", [
        {"drug_name": "阿司匹林", "action": "hold", "rationale": "活动性出血风险需要医生确认"},
        {"drug_name": "", "action": "increase", "rationale": "short"},
    ])

    assert valid[0]["action"] == "hold"
    assert valid[0]["requires_doctor_confirmation"] is True
    assert len(errors) == 1


def test_validate_llm_output_rejects_invalid_ddx_reviewer_addition():
    valid, errors = validate_llm_output("ddx", [
        {"diagnosis": "肺炎", "likelihood": "high", "icd10": "J18.9"},
        {"diagnosis": "", "likelihood": "certain"},
    ])

    assert valid == [{"diagnosis": "肺炎", "likelihood": "high", "icd10": "J18.9"}]
    assert len(errors) == 1


def test_check_source_type_ignores_non_finite_score():
    result = check_source_type([{"score": float("nan")}, {"score": 0.8}], threshold=0.6)

    assert result == {"source_type": "source_knowledge", "count": 1}


def test_loop_collect_routes_lab_event_to_lab_knowledge(monkeypatch):
    from zhenhu.inpatient.agent import loop

    calls = []

    async def fake_collect(query, caller, top_k=3):
        calls.append((query, caller, top_k))
        return []

    async def fake_api_data(state):
        return {}

    monkeypatch.setattr("zhenhu.inpatient.agent.llm_utils._rag_collect", fake_collect)
    monkeypatch.setattr("zhenhu.inpatient.agent.clinical_external.collect_api_data", fake_api_data)

    asyncio.run(loop._loop_collect({
        "phase": "monitoring",
        "event_type": "lab",
        "disease_template": {"name": "肺炎"},
    }))

    assert calls == [("肺炎 lab_review", "lab_review", 3)]


def test_loop_collect_routes_vitals_event_to_monitoring_knowledge(monkeypatch):
    from zhenhu.inpatient.agent import loop

    calls = []

    async def fake_collect(query, caller, top_k=3):
        calls.append((query, caller, top_k))
        return []

    async def fake_api_data(state):
        return {}

    monkeypatch.setattr("zhenhu.inpatient.agent.llm_utils._rag_collect", fake_collect)
    monkeypatch.setattr("zhenhu.inpatient.agent.clinical_external.collect_api_data", fake_api_data)

    asyncio.run(loop._loop_collect({
        "phase": "monitoring",
        "event_type": "vitals",
        "disease_template": {"name": "心力衰竭"},
    }))

    assert calls == [("心力衰竭 monitoring", "monitoring", 3)]


class TestBridge:
    """臻护桥接测试(无真实服务时返回降级状态)。"""

    def test_bridge_discharge_unavailable(self):
        from zhenhu.inpatient.hooks.zhenhu_bridge import bridge_discharge_to_zhenhu

        result = asyncio.run(bridge_discharge_to_zhenhu([], "test-001"))
        assert result["status"] in ("bridge_unavailable", "bridge_skipped")

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


def test_validate_rejects_unknown_handoff_type_and_non_object_items():
    items = [
        {"type": "supplement", "content": "This must not enter the handoff."},
        "not-an-object",
    ]

    valid, errors = validate_handoff_items(items)

    assert valid == []
    assert len(errors) == 2

def test_source_score_boundary():
    results = [{"score": 0.59}]
    result = check_source_type(results, threshold=0.6)
    assert result["source_type"] == "source_none"

def test_source_score_exact_threshold():
    results = [{"score": 0.6}]
    result = check_source_type(results, threshold=0.6)
    assert result["source_type"] == "source_knowledge"


def test_source_score_accepts_numeric_strings_and_ignores_invalid_scores():
    results = [{"score": "0.8"}, {"score": "not-a-number"}]

    result = check_source_type(results, threshold=0.6)

    assert result == {"source_type": "source_knowledge", "count": 1}


def test_fallback_discards_malformed_template_instructions():
    template = {
        "handoff_instructions": [
            {"type": "followup", "content": "Please return to cardiology within seven days."},
            {"type": "supplement", "content": "Unsupported instruction type."},
            "not-an-instruction",
        ]
    }

    result = fallback_to_template(template)

    assert result["handoff_items"] == [
        {
            "type": "followup",
            "content": "Please return to cardiology within seven days.",
            "source": "disease_template_fallback",
        }
    ]


# ============================================================================
# 事件驱动路由测试
# ============================================================================


def test_event_routing_after_monitoring_discharge():
    """查房完成+approved → stroke_antithrombotic（v1.3: 出院签字前卒中抗栓检查）。"""
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
    assert result == "stroke_antithrombotic"


def test_event_routing_after_monitoring_stay():
    """查房完成后进入监测节点，由其后置路由结束本轮。"""
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


def test_monitoring_result_discharge_ignores_pre_monitoring_medication_route():
    """监测已批准出院时不能重新进入调药分流。"""
    from zhenhu.inpatient.agent.graph import after_monitoring_result

    state = {
        "discharge_decision": "approved",
        "disease_template": {
            "vital_signs": [{"name": "heart_rate", "alert_above": 100}],
        },
        "vital_signs": [{"heart_rate": 120}],
    }

    assert after_monitoring_result(state) == "stroke_antithrombotic"


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
    assert result["status"] in ("bridge_unavailable", "bridge_skipped")


def test_bridge_plan_definition_no_template():
    """无template参数时仍能降级。"""
    from zhenhu.inpatient.hooks.zhenhu_bridge import bridge_discharge_to_zhenhu

    result = asyncio.run(bridge_discharge_to_zhenhu([], "test-002"))
    assert result["status"] in ("bridge_unavailable", "bridge_skipped")


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


def test_turn_journal_is_bounded_and_does_not_keep_clinical_text():
    from zhenhu.inpatient.agent.loop import _append_turn_journal

    result = {"document_chain": ["monitoring"], "agent_turn_journal": []}
    input_state = {
        "patient_id": "patient-1", "state_version": 4, "phase": "monitoring",
        "vital_signs": [{"spo2": 91, "free_text": "must not be journaled"}],
        "lab_results": [], "medication_adjustments": [], "document_chain": ["monitoring"],
    }
    for index in range(35):
        result = _append_turn_journal(
            result, turn_id=f"turn-{index}", entry_strategy="monitoring:vitals",
            input_state=input_state, latency_ms=21, collect_ctx={"rag_hits": {"monitoring": [{}]}},
        )

    journal = result["agent_turn_journal"]
    assert len(journal) == 30
    assert journal[-1]["rag_hit_count"] == 1
    assert "free_text" not in str(journal)


def test_nursing_monitoring_does_not_start_a_new_discharge_workflow(monkeypatch):
    """护理录入可刷新出院条件，但不能自行进入交接/签字链路。"""
    from zhenhu.inpatient.agent import nodes_handoff, nodes_monitoring
    from zhenhu.inpatient.agent.loop import PatientAgentLoop

    async def monitoring_ready_for_discharge(_state):
        return {
            "phase": "monitoring",
            "discharge_decision": "approved",
            "discharge_criteria_check": {"all_met": True},
        }

    async def handoff_must_not_run(_state):
        raise AssertionError("nursing entry must not initiate handoff")

    monkeypatch.setattr(nodes_monitoring, "node_monitoring", monitoring_ready_for_discharge)
    monkeypatch.setattr(nodes_handoff, "node_handoff", handoff_must_not_run)

    result = asyncio.run(PatientAgentLoop().plan_monitoring_turn({
        "patient_id": "nursing-fast-path",
        "phase": "monitoring",
        "disease_template": {},
        "vital_signs": [{"spo2": 98, "heart_rate": 74}],
        "discharge_decision": None,
    }, event_type="nursing", collect=False))

    assert result["discharge_criteria_check"]["all_met"] is True
    assert result.get("discharge_decision") is None


def test_audit_hook():
    """on_node_enter/exit 正确记录事件。"""
    from zhenhu.inpatient.agent.harness import AgentAuditHook

    hook = AgentAuditHook()
    hook.on_node_enter("admission", {"phase": "start"})
    hook.on_node_exit("admission", {"phase": "admission"})
    assert len(hook.events) == 2
