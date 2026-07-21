"""Traceable clinical evidence citation regression tests."""

from __future__ import annotations

from uuid import uuid4

import pytest


def test_rag_hits_are_converted_to_stable_traceable_citations():
    from zhenhu.inpatient.services.clinical_evidence import build_rag_citations

    citations = build_rag_citations([{
        "layer": "L5",
        "source": "drug_interaction",
        "topic": "warfarin and aspirin",
        "version": "2026-07-18",
        "indexed_at": 1_784_000_000,
        "score": 0.92,
        "text": "Combination increases bleeding risk.",
    }])

    assert len(citations) == 1
    citation = citations[0]
    assert citation["citation_id"].startswith("rag:")
    assert citation["source"] == "drug_interaction"
    assert citation["document_version"] == "2026-07-18"
    assert citation["retrieval_score"] == 0.92
    assert citation["excerpt"] == "Combination increases bleeding risk."


@pytest.mark.asyncio
async def test_patient_evidence_endpoint_returns_traceable_citations():
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = f"evidence-{uuid4()}"
    set_state(patient_id, {
        "patient_id": patient_id,
        "clinical_evidence": [{
            "citation_id": "rag:example",
            "source": "drug_interaction",
            "document_version": "2026-07-18",
            "excerpt": "Example evidence.",
        }],
    })

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get(
            f"/inpatient/{patient_id}/evidence",
            headers={"x-role": "doctor"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["citations"][0]["citation_id"] == "rag:example"


@pytest.mark.asyncio
async def test_daily_round_persists_rag_citations_with_its_recommendation(monkeypatch):
    from zhenhu.inpatient.agent import nodes_monitoring

    async def fake_safe_invoke(*args, **kwargs):
        return {}

    async def fake_deep_invoke(*args, **kwargs):
        return {
            "response": "Prioritize potassium reassessment.",
            "_rag_citations": [{"citation_id": "rag:daily-round", "source": "electrolyte"}],
        }

    monkeypatch.setattr(nodes_monitoring, "safe_llm_invoke", fake_safe_invoke)
    monkeypatch.setattr(nodes_monitoring, "get_cached_provider", lambda: object(), raising=False)
    monkeypatch.setattr(nodes_monitoring, "get_provider_for_node", lambda _: object())
    from zhenhu.inpatient.agent import llm_utils
    monkeypatch.setattr(llm_utils, "deep_invoke", fake_deep_invoke)

    result = await nodes_monitoring.node_daily_round({
        "patient_id": "daily-evidence",
        "vital_signs": [{"heart_rate": 80}],
        "lab_results": [],
        "medication_adjustments": [],
        "document_chain": [],
        "disease_template": {"name": "Test disease"},
        "clinical_evidence": [{"citation_id": "rag:existing"}],
    })

    assert result["ai_recommendation"] == "Prioritize potassium reassessment."
    assert [item["citation_id"] for item in result["clinical_evidence"]] == ["rag:existing", "rag:daily-round"]


@pytest.mark.asyncio
async def test_news2_persists_rag_citations_with_its_suggestion(monkeypatch):
    from zhenhu.inpatient.agent import nodes_scoring

    async def fake_deep_invoke(*args, **kwargs):
        return {
            "response": "Escalate clinical review.",
            "_rag_citations": [{"citation_id": "rag:news2", "source": "news2-guidance"}],
        }

    monkeypatch.setattr(nodes_scoring, "get_cached_provider", lambda: object(), raising=False)
    monkeypatch.setattr(nodes_scoring, "deep_invoke", fake_deep_invoke, raising=False)

    result = await nodes_scoring.node_news2({
        "patient_id": "news2-evidence",
        "vital_signs": [{
            "respiratory_rate": 30,
            "spo2": 85,
            "temperature": 40.0,
            "systolic_mmhg": 85,
            "heart_rate": 140,
            "gcs": 15,
        }],
        "clinical_evidence": [{"citation_id": "rag:existing"}],
    })

    assert "Escalate clinical review." in result["clinical_alerts"][-1]
    assert [item["citation_id"] for item in result["clinical_evidence"]] == ["rag:existing", "rag:news2"]


@pytest.mark.asyncio
async def test_qsofa_persists_rag_citations_with_its_suggestion(monkeypatch):
    from zhenhu.inpatient.agent import nodes_scoring

    async def fake_deep_invoke(*args, **kwargs):
        return {
            "response": "Initiate sepsis evaluation.",
            "_rag_citations": [{"citation_id": "rag:qsofa", "source": "sepsis-guidance"}],
        }

    monkeypatch.setattr(nodes_scoring, "get_cached_provider", lambda: object(), raising=False)
    monkeypatch.setattr(nodes_scoring, "deep_invoke", fake_deep_invoke, raising=False)

    result = await nodes_scoring.node_qsofa({
        "patient_id": "qsofa-evidence",
        "vital_signs": [{"respiratory_rate": 24, "systolic_mmhg": 90, "gcs": 15}],
        "clinical_evidence": [{"citation_id": "rag:existing"}],
    })

    assert "Initiate sepsis evaluation." in result["clinical_alerts"][-1]
    assert [item["citation_id"] for item in result["clinical_evidence"]] == ["rag:existing", "rag:qsofa"]


@pytest.mark.asyncio
async def test_medication_adjustment_persists_rag_citations(monkeypatch):
    from zhenhu.inpatient.agent import nodes_monitoring

    async def fake_safe_invoke(*args, **kwargs):
        return {"source_type": "source_knowledge"}

    async def fake_deep_invoke(*args, **kwargs):
        return {
            "suggestion": "Review antihypertensive treatment.",
            "urgency": "urgent",
            "_rag_citations": [{"citation_id": "rag:medication", "source": "medication-guidance"}],
        }

    monkeypatch.setattr(nodes_monitoring, "get_cached_provider", lambda: object(), raising=False)
    monkeypatch.setattr(nodes_monitoring, "safe_llm_invoke", fake_safe_invoke)
    monkeypatch.setattr(nodes_monitoring, "deep_invoke", fake_deep_invoke, raising=False)
    result = await nodes_monitoring.node_medication_adjust({
        "patient_id": "medication-evidence",
        "vital_signs": [{"heart_rate": 120}, {"heart_rate": 125}],
        "disease_template": {
            "name": "Test disease",
            "vital_signs": [{"name": "heart_rate", "alert_above": 100}],
        },
        "consecutive_abnormal_count": 1,
        "clinical_evidence": [{"citation_id": "rag:existing"}],
    })

    assert result["medication_adjustments"][0]["urgency"] == "urgent"
    assert [item["citation_id"] for item in result["clinical_evidence"]] == ["rag:existing", "rag:medication"]


@pytest.mark.asyncio
async def test_lab_review_persists_rag_citations(monkeypatch):
    from zhenhu.inpatient.agent import nodes_monitoring

    async def fake_safe_invoke(*args, **kwargs):
        return {"source_type": "source_knowledge"}

    async def fake_deep_invoke(*args, **kwargs):
        return {
            "interpretation": "Potassium is elevated.",
            "recommendation": "Repeat the measurement.",
            "_rag_citations": [{"citation_id": "rag:lab", "source": "electrolyte-guidance"}],
        }

    monkeypatch.setattr(nodes_monitoring, "get_cached_provider", lambda: object(), raising=False)
    monkeypatch.setattr(nodes_monitoring, "safe_llm_invoke", fake_safe_invoke)
    monkeypatch.setattr(nodes_monitoring, "deep_invoke", fake_deep_invoke, raising=False)
    result = await nodes_monitoring.node_lab_review({
        "patient_id": "lab-evidence",
        "lab_results": [{"name": "K", "value": 6.2, "unit": "mmol/L"}],
        "reviewed_labs": [],
        "disease_template": {"name": "Test disease", "lab_reference": {"K": {"low": 3.5, "high": 5.5}}},
        "clinical_evidence": [{"citation_id": "rag:existing"}],
    })

    assert result["lab_findings"][0]["interpretation"] == "Potassium is elevated."
    assert [item["citation_id"] for item in result["clinical_evidence"]] == ["rag:existing", "rag:lab"]


@pytest.mark.asyncio
async def test_transfer_rationale_persists_rag_citations(monkeypatch):
    from zhenhu.inpatient.agent import nodes_monitoring

    async def fake_safe_invoke(*args, **kwargs):
        return {"source_type": "source_knowledge"}

    async def fake_deep_invoke(*args, **kwargs):
        return {
            "rationale": "Escalate for hemodynamic instability.",
            "_rag_citations": [{"citation_id": "rag:transfer", "source": "critical-care-guidance"}],
        }

    monkeypatch.setattr(nodes_monitoring, "get_cached_provider", lambda: object(), raising=False)
    monkeypatch.setattr(nodes_monitoring, "safe_llm_invoke", fake_safe_invoke)
    monkeypatch.setattr(nodes_monitoring, "deep_invoke", fake_deep_invoke, raising=False)
    result = await nodes_monitoring.node_transfer({
        "patient_id": "transfer-evidence",
        "vital_signs": [{"systolic_mmhg": 80, "heart_rate": 130}],
        "disease_template": {"disease_id": "heart_failure"},
        "clinical_evidence": [{"citation_id": "rag:existing"}],
    })

    assert result["transfer_needed"] is True
    assert [item["citation_id"] for item in result["clinical_evidence"]] == ["rag:existing", "rag:transfer"]


@pytest.mark.asyncio
async def test_nursing_record_persists_rag_citations(monkeypatch):
    from zhenhu.inpatient.agent import nodes_clinical

    async def fake_deep_invoke(*args, **kwargs):
        return {
            "nursing_actions": "Reassess respiratory status.",
            "alerts": ["Escalate if hypoxia persists."],
            "_rag_citations": [{"citation_id": "rag:nursing", "source": "nursing-guidance"}],
        }

    monkeypatch.setattr(nodes_clinical, "get_cached_provider", lambda: object())
    monkeypatch.setattr(nodes_clinical, "deep_invoke", fake_deep_invoke)

    result = await nodes_clinical.node_nursing({
        "patient_id": "nursing-evidence",
        "vital_signs": [{"spo2": 88, "timestamp": "2026-07-19T10:00:00Z"}],
        "medication_adjustments": [],
        "disease_template": {},
        "clinical_evidence": [{"citation_id": "rag:existing"}],
    })

    assert result["nursing_records"][0]["citations"][0]["citation_id"] == "rag:nursing"
    assert [item["citation_id"] for item in result["clinical_evidence"]] == ["rag:existing", "rag:nursing"]


@pytest.mark.asyncio
async def test_shift_summary_persists_rag_citations(monkeypatch):
    from zhenhu.inpatient.agent import nodes_clinical

    async def fake_deep_invoke(*args, **kwargs):
        return {
            "response": "Escalate observation and hand over the respiratory risk.",
            "_rag_citations": [{"citation_id": "rag:handover", "source": "handover-guidance"}],
        }

    monkeypatch.setattr(nodes_clinical, "get_cached_provider", lambda: object())
    monkeypatch.setattr(nodes_clinical, "deep_invoke", fake_deep_invoke)

    result = await nodes_clinical.node_shift_summary({
        "patient_id": "handover-evidence",
        "document_chain": ["daily_round_note"],
        "vital_signs": [{"spo2": 88, "heart_rate": 120}],
        "clinical_alerts": ["a", "b", "c"],
        "disease_template": {"name": "Test disease"},
        "round_count": 1,
        "news2_score": 6,
        "clinical_evidence": [{"citation_id": "rag:existing"}],
    })

    assert result["shift_summary_citations"][0]["citation_id"] == "rag:handover"
    assert [item["citation_id"] for item in result["clinical_evidence"]] == ["rag:existing", "rag:handover"]


@pytest.mark.asyncio
async def test_patient_query_returns_rag_citations_without_mutating_patient_state(
    monkeypatch, isolated_state_store,
):
    """Open-ended clinical answers expose the evidence used for the answer."""
    from zhenhu.inpatient.routes import query
    from zhenhu.inpatient.routes.route_schemas import QueryRequest
    from zhenhu.inpatient.routes.state_store import get_state, set_state

    patient_id = f"query-evidence-{uuid4()}"
    state = {
        "patient_id": patient_id,
        "disease_template": {"name": "Test disease"},
        "clinical_evidence": [{"citation_id": "rag:existing"}],
    }
    set_state(patient_id, state)
    state_before_query = get_state(patient_id)

    async def fake_deep_invoke(*args, **kwargs):
        assert kwargs["caller"] == "patient_query"
        assert kwargs["rag_query"] == "What follow-up is appropriate?"
        return {
            "response": "Repeat the relevant assessment and document the result.",
            "_rag_citations": [{"citation_id": "rag:patient-query", "source": "follow-up-guidance"}],
        }

    monkeypatch.setattr(query, "get_provider_for_node", lambda _: object())
    monkeypatch.setattr(query, "deep_invoke", fake_deep_invoke)

    request = type("Request", (), {"state": type("State", (), {"user_info": {"roles": ["doctor"], "auth_mode": "header"}})()})()
    response = await query.query_patient(
        patient_id, QueryRequest(question="What follow-up is appropriate?"), request
    )

    assert response.data["answer"] == "Repeat the relevant assessment and document the result."
    assert response.data["citations"] == [{"citation_id": "rag:patient-query", "source": "follow-up-guidance"}]
    assert get_state(patient_id) == state_before_query


def test_legacy_pending_review_side_store_is_disabled():
    """Review checkpoints have one authoritative state store."""
    from zhenhu.inpatient.agent.persistence import persist_pending_review

    with pytest.raises(RuntimeError, match="retired"):
        persist_pending_review("patient-1", {"type": "doctor_confirm"})
