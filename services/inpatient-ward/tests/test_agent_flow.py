from zhenhu.inpatient.services.agent_flow import active_pending_review, build_agent_flow


def test_agent_flow_separates_llm_drafts_from_human_review_and_commits():
    flow = build_agent_flow({
        "document_chain": ["history_note", "ddx_note", "daily_round_note"],
        "vital_signs": [{"heart_rate": 110}],
        "clinical_evidence": [{"title": "心衰指南", "source": "L2", "excerpt": "监测容量状态"}],
        "ddx_list": [{"diagnosis": "急性心衰", "likelihood": "high"}],
        "latest_round": {"assessment": "容量负荷增加"},
        "assistant_action_drafts": [{"id": "draft-1", "draft_type": "investigation_order", "status": "pending", "citations": []}],
        "pending_review": {"type": "med_confirm"},
        "medication_orders": [{"id": "order-1", "status": "active"}],
    })

    assert flow["flow_status"] == "waiting_review"
    assert flow["pending_review"] == {"review_type": "med_confirm", "review_id": "", "label": "用药调整审核"}
    assert next(stage for stage in flow["stages"] if stage["id"] == "review")["status"] == "pending"
    assert any(item["title"] == "检查医嘱草稿" and item["status"] == "待医生审核" for item in flow["generated_artifacts"])
    assert any(stage["id"] == "commit" and stage["status"] == "completed" for stage in flow["stages"])


def test_agent_flow_does_not_claim_llm_or_evidence_when_state_has_none():
    flow = build_agent_flow({"document_chain": [], "disease_template": {}})

    assert flow["flow_status"] == "ready"
    assert next(stage for stage in flow["stages"] if stage["id"] == "evidence")["status"] == "idle"
    assert flow["generated_artifacts"] == []


def test_agent_flow_projects_recent_turns_without_exposing_input_fingerprint():
    flow = build_agent_flow({
        "agent_turn_journal": [{
            "turn_id": "turn-1", "occurred_at": "2026-07-21T08:00:00+00:00",
            "entry_strategy": "monitoring:vitals", "status": "completed", "latency_ms": 42,
            "input_fingerprint": "sensitive-operational-value", "rag_hit_count": 2,
            "knowledge_gap": False, "node_path": ["monitoring", "daily_round"],
        }],
    })

    assert flow["turn_journal"] == [{
        "turn_id": "turn-1", "occurred_at": "2026-07-21T08:00:00+00:00",
        "entry_strategy": "monitoring:vitals", "status": "completed", "latency_ms": 42,
        "rag_hit_count": 2, "knowledge_gap": False, "node_count": 2, "error_message": "",
    }]


def test_agent_flow_ignores_stale_prerequisite_review_after_discharge_signature():
    state = {
        "pending_review": {"type": "med_confirm", "review_id": "stale-review"},
        "med_confirm_status": "pending",
        "discharge_sign_status": "signed",
    }

    assert active_pending_review(state) is None
    flow = build_agent_flow(state)
    assert flow["flow_status"] == "ready"
    assert flow["pending_review"] is None


def test_nursing_agent_flow_projects_nurse_confirmation_and_audited_completion():
    flow = build_agent_flow({
        "vital_signs": [{"timestamp": "2026-07-21T08:00:00+00:00", "spo2": 91}],
        "nursing_records": [{
            "timestamp": "2026-07-21T08:00:00+00:00",
            "source": "agent",
            "nursing_actions": "加强氧疗巡视并复测血氧",
            "alerts": ["血氧下降"],
            "citations": [{"title": "护理规范"}],
        }],
        "clinical_evidence": [{"title": "护理规范", "source": "L8", "excerpt": "低氧血症护理要点"}],
    }, audience="nurse")

    assert flow["flow_status"] == "waiting_review"
    assert [stage["id"] for stage in flow["stages"]] == ["collect", "evidence", "reason", "review", "commit"]
    assert next(stage for stage in flow["stages"] if stage["id"] == "review")["title"] == "护士复核与任务执行"
    assert any(item["title"] == "智能护理建议" and item["status"] == "待护士复核" for item in flow["generated_artifacts"])
    assert "护士复核" in flow["safety_boundary"]

    flow_after_completion = build_agent_flow({
        "vital_signs": [{"timestamp": "2026-07-21T08:00:00+00:00", "spo2": 91}],
        "nursing_records": [{"timestamp": "2026-07-21T08:00:00+00:00", "source": "agent", "nursing_actions": "复测血氧"}],
        "nursing_task_completions": [{"completed_at": "2026-07-21T08:10:00+00:00"}],
    }, audience="nurse")

    assert flow_after_completion["flow_status"] == "ready"
    assert next(stage for stage in flow_after_completion["stages"] if stage["id"] == "review")["status"] == "completed"


async def test_agent_flow_route_uses_nurse_projection_for_nurse_identity(client, isolated_state_store):
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = "nurse-agent-flow"
    set_state(patient_id, {
        "patient_id": patient_id,
        "patient_access": {"department": "cardiology"},
        "vital_signs": [{"timestamp": "2026-07-21T08:00:00+00:00", "spo2": 91}],
        "nursing_records": [{"timestamp": "2026-07-21T08:00:00+00:00", "source": "agent", "nursing_actions": "复测血氧"}],
    })

    response = await client.get(
        f"/inpatient/{patient_id}/agent-flow",
        headers={"x-role": "nurse", "x-user-id": "nurse-1", "x-department": "cardiology"},
    )

    assert response.status_code == 200
    stages = response.json()["data"]["stages"]
    assert next(stage for stage in stages if stage["id"] == "review")["title"] == "护士复核与任务执行"
