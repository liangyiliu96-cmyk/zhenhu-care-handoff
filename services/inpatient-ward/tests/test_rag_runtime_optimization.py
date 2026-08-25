from __future__ import annotations

from urllib.parse import quote

import pytest
from httpx import ASGITransport, AsyncClient


def test_runtime_cache_falls_back_to_memory(monkeypatch):
    from zhenhu.inpatient.services import runtime_cache

    monkeypatch.setenv("RUNTIME_CACHE_DISABLE", "true")
    cache = runtime_cache.RuntimeCache()

    cache.set_json("test:cache", {"value": 1}, 60)

    assert cache.get_json("test:cache") == {"value": 1}
    assert cache.status()["backend"] == "memory"


def test_runtime_cache_retries_redis_after_an_initial_connection_failure(monkeypatch):
    from zhenhu.inpatient.services import runtime_cache

    calls = 0

    class Client:
        def ping(self):
            return True

    class RedisFactory:
        @staticmethod
        def from_url(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ConnectionError("Redis still starting")
            return Client()

    monkeypatch.delenv("RUNTIME_CACHE_DISABLE", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "redis", type("RedisModule", (), {"Redis": RedisFactory})())
    cache = runtime_cache.RuntimeCache()
    cache._redis_retry_seconds = 0

    assert cache.redis_client() is None
    assert cache.redis_client() is not None
    assert cache.status()["backend"] == "redis"


def test_medication_intent_routes_to_allowed_medication_layers():
    from zhenhu.inpatient.agent.assistant import classify_intent

    intent = classify_intent("华法林和抗生素联用需要如何调整剂量？", ["L2", "L5", "L6", "L11"])

    assert intent["name"] == "medication"
    assert intent["layers"] == ["L5", "L11", "L6"]


@pytest.mark.parametrize("message", ["你好", "你好呀！", "您好！", " Hi ", "你是谁呢？", "谢谢你啦。"])
def test_pure_smalltalk_does_not_request_rag_layers(message):
    from zhenhu.inpatient.agent.assistant import classify_intent

    intent = classify_intent(message, ["L1", "L5", "L9"])

    assert intent["name"] == "smalltalk"
    assert intent["layers"] == []
    assert intent["confidence"] == 0.99


def test_professional_question_with_greeting_prefix_keeps_clinical_intent():
    from zhenhu.inpatient.agent.assistant import classify_intent

    intent = classify_intent("你好，请问华法林和抗生素联用需要注意什么？", ["L2", "L5", "L6", "L11"])

    assert intent["name"] == "medication"
    assert intent["layers"] == ["L5", "L11", "L6"]


@pytest.mark.parametrize("message", ["帮我写一首诗", "今天股市怎么样", "你喜欢什么颜色", "怎么做蛋炒饭"])
def test_non_clinical_general_questions_do_not_request_rag_layers(message):
    from zhenhu.inpatient.agent.assistant import classify_intent

    intent = classify_intent(message, ["L1", "L5", "L9"])

    assert intent["name"] == "general_chat"
    assert intent["layers"] == []


@pytest.mark.parametrize("message", ["该患者目前最关键的行动建议？", "失眠怎么办？", "血压高需要怎么记录？"])
def test_general_clinical_questions_still_request_scoped_rag_layers(message):
    from zhenhu.inpatient.agent.assistant import classify_intent

    intent = classify_intent(message, ["L1", "L5", "L9"])

    assert intent["name"] == "general"
    assert intent["layers"] == ["L1", "L5", "L9"]


def test_general_answer_cache_excludes_likely_patient_identifiers():
    from zhenhu.inpatient.agent.assistant import _is_general_cache_safe

    assert _is_general_cache_safe("华法林和甲硝唑联用需要注意什么") is True
    assert _is_general_cache_safe("患者张某的住院号是 12345678，如何调整用药") is False


@pytest.mark.asyncio
async def test_assistant_retrieval_uses_intent_layers(monkeypatch):
    from zhenhu.inpatient.agent import assistant, rag_engine

    requested_layers = []

    async def fake_search(_query, *, layer=None, **_kwargs):
        requested_layers.append(layer)
        return [{"layer": "L6", "score": 0.8, "topic": "血钾", "text": "血钾监测", "source": "lab_reference"}]

    monkeypatch.setattr(rag_engine, "search", fake_search)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["血钾化验异常怎么办"])

    sources, citations, intent = await assistant._retrieve_sources("血钾化验异常怎么办", assistant.ROLE_CONFIG["doctor"])

    assert intent["name"] == "laboratory"
    assert requested_layers == [["L6", "L1"]]
    assert sources[0]["layer"] == "L6"
    assert sources[0]["source"] == "lab_reference"
    assert sources[0]["document_version"] == "unversioned"
    assert intent["evidence_diagnostics"]["status"] == "ok"
    assert citations


@pytest.mark.asyncio
async def test_assistant_retrieval_prefers_patient_scope_then_falls_back_broad(
    monkeypatch, isolated_state_store,
):
    from zhenhu.inpatient.agent import assistant, rag_engine
    from zhenhu.inpatient.routes.state_store import set_state

    patient_id = "rag-scope-patient"
    set_state(patient_id, {
        "patient_id": patient_id,
        "state_version": 7,
        "risk_level": "high",
        "disease_template": {"disease_id": "heart_failure", "department": "心内科"},
    })
    calls = []

    async def fake_search(_query, *, layer=None, disease_id=None, department=None, **_kwargs):
        calls.append({"layer": layer, "disease_id": disease_id, "department": department})
        if disease_id or department:
            return []
        return [{
            "layer": "L5",
            "score": 0.81,
            "topic": "利尿剂与低钾风险",
            "text": "使用利尿剂时需要监测血钾。",
            "source": "drug_interaction",
            "version": "2026-07-20",
        }]

    monkeypatch.setattr(rag_engine, "search", fake_search)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["利尿剂用药注意什么"])

    sources, citations, intent = await assistant._retrieve_sources(
        "利尿剂用药注意什么",
        assistant.ROLE_CONFIG["doctor"],
        role="doctor",
        patient_id=patient_id,
    )

    assert calls[0]["disease_id"] == "heart_failure"
    assert calls[0]["department"] == "心内科"
    assert calls[-1]["disease_id"] is None
    assert calls[-1]["department"] is None
    assert sources[0]["document_version"] == "2026-07-20"
    assert citations[0]["document_version"] == "2026-07-20"
    assert intent["evidence_diagnostics"]["attempted_scopes"] == [
        "patient_disease_department",
        "patient_disease",
        "patient_department",
        "broad",
    ]
    assert intent["evidence_diagnostics"]["patient_scope"]["status"]["risk_level"] == "high"


@pytest.mark.asyncio
async def test_assistant_retrieval_filters_local_fallback_by_evidence_graph(
    monkeypatch, isolated_state_store,
):
    from zhenhu.inpatient.agent import assistant, rag_engine
    from zhenhu.inpatient.routes.state_store import set_state
    from zhenhu.inpatient.services import evidence_graph

    patient_id = "rag-graph-patient"
    set_state(patient_id, {
        "patient_id": patient_id,
        "state_version": 3,
        "disease_template": {"disease_id": "heart_failure", "department": "心内科"},
    })

    def fake_disease_evidence(disease_id, **_kwargs):
        assert disease_id == "heart_failure"
        return {
            "disease_id": disease_id,
            "evidence": [{
                "layer": "L5",
                "source": "drug_interaction",
                "topic": "利尿剂与低钾风险",
                "version": "2026-07-20",
            }],
            "rules": [{"id": "rule-1"}],
        }

    async def fake_search(*_args, **_kwargs):
        return [
            {
                "layer": "L5",
                "score": 0.84,
                "topic": "利尿剂与低钾风险",
                "text": "使用利尿剂时需要监测血钾。",
                "source": "drug_interaction",
                "version": "2026-07-20",
            },
            {
                "layer": "L5",
                "score": 0.92,
                "topic": "泛化用药建议",
                "text": "这条未进入当前病种证据图谱。",
                "source": "drug_interaction",
                "version": "2026-07-20",
            },
        ]

    monkeypatch.setattr(evidence_graph, "disease_evidence", fake_disease_evidence)
    monkeypatch.setattr(rag_engine, "search", fake_search)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["利尿剂用药注意什么"])

    sources, citations, intent = await assistant._retrieve_sources(
        "利尿剂用药注意什么",
        assistant.ROLE_CONFIG["doctor"],
        role="doctor",
        patient_id=patient_id,
    )

    assert [source["topic"] for source in sources] == ["利尿剂与低钾风险"]
    assert citations[0]["topic"] == "利尿剂与低钾风险"
    assert intent["evidence_diagnostics"]["graph_context"] == {
        "status": "ok",
        "disease_id": "heart_failure",
        "evidence_count": 1,
        "rule_count": 1,
    }
    assert intent["evidence_diagnostics"]["rejected"]["graph_mismatch"] == 1


@pytest.mark.asyncio
async def test_assistant_retrieval_marks_graph_unavailable_as_degraded(
    monkeypatch, isolated_state_store,
):
    from zhenhu.inpatient.agent import assistant, rag_engine
    from zhenhu.inpatient.routes.state_store import set_state
    from zhenhu.inpatient.services import evidence_graph

    patient_id = "rag-graph-unavailable-patient"
    set_state(patient_id, {
        "patient_id": patient_id,
        "state_version": 4,
        "disease_template": {"disease_id": "heart_failure", "department": "心内科"},
    })

    def unavailable_graph(*_args, **_kwargs):
        raise evidence_graph.EvidenceGraphUnavailable("not configured")

    async def fake_search(*_args, **_kwargs):
        return [{
            "layer": "L5",
            "score": 0.84,
            "topic": "利尿剂与低钾风险",
            "text": "使用利尿剂时需要监测血钾。",
            "source": "drug_interaction",
            "version": "2026-07-20",
        }]

    monkeypatch.setattr(evidence_graph, "disease_evidence", unavailable_graph)
    monkeypatch.setattr(rag_engine, "search", fake_search)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["利尿剂用药注意什么"])

    sources, citations, intent = await assistant._retrieve_sources(
        "利尿剂用药注意什么",
        assistant.ROLE_CONFIG["doctor"],
        role="doctor",
        patient_id=patient_id,
    )

    assert sources
    assert citations
    assert intent["evidence_diagnostics"]["status"] == "ok"
    assert intent["evidence_diagnostics"]["degraded"] is True
    assert intent["evidence_diagnostics"]["graph_context"]["status"] == "unavailable"
    assert intent["evidence_diagnostics"]["degradation_reasons"] == [
        "evidence_graph_unavailable:EvidenceGraphUnavailable",
    ]


@pytest.mark.asyncio
async def test_assistant_retrieval_reports_low_relevance_without_sources(monkeypatch):
    from zhenhu.inpatient.agent import assistant, rag_engine

    async def fake_search(*_args, **_kwargs):
        return [{
            "layer": "L6",
            "score": 0.05,
            "topic": "血钾",
            "text": "血钾参考范围。",
            "source": "lab_reference",
            "version": "2026-07-20",
        }]

    monkeypatch.setattr(rag_engine, "search", fake_search)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["血钾化验异常怎么办"])

    sources, citations, intent = await assistant._retrieve_sources(
        "血钾化验异常怎么办",
        assistant.ROLE_CONFIG["doctor"],
        role="doctor",
    )

    assert sources == []
    assert citations == []
    assert intent["evidence_diagnostics"]["status"] == "low_relevance"
    assert intent["evidence_diagnostics"]["rejected"]["low_score"] == 1


@pytest.mark.asyncio
async def test_assistant_retrieval_rejects_high_score_unrelated_hit(monkeypatch):
    from zhenhu.inpatient.agent import assistant, rag_engine

    async def fake_search(*_args, **_kwargs):
        return [{
            "layer": "L5",
            "score": 0.91,
            "topic": "地高辛与低钾风险",
            "text": "低钾可增加地高辛中毒风险。",
            "source": "drug_interaction",
            "version": "2026-07-20",
        }]

    monkeypatch.setattr(rag_engine, "search", fake_search)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["华法林与阿司匹林相互作用"])

    sources, citations, intent = await assistant._retrieve_sources(
        "华法林与阿司匹林相互作用",
        assistant.ROLE_CONFIG["doctor"],
        role="doctor",
    )

    assert sources == []
    assert citations == []
    assert intent["evidence_diagnostics"]["status"] == "low_relevance"
    assert intent["evidence_diagnostics"]["rejected"]["lexical_mismatch"] == 1


@pytest.mark.asyncio
async def test_assistant_retrieval_prefers_published_knowledge_orchestrator(monkeypatch):
    from zhenhu.inpatient.agent import assistant, rag_engine
    from zhenhu.inpatient.services import knowledge_orchestrator

    monkeypatch.setenv("KNOWLEDGE_ORCHESTRATOR_RAG_ENABLED", "true")

    async def fake_orchestrator(query, *, top_k, allowed_layers, role, intent_name, disease_id=None, department=None):
        assert query == "利尿剂用药注意什么"
        assert top_k == assistant.RAG_TOP_K
        assert list(allowed_layers) == ["L5", "L11", "L6"]
        assert role == "doctor"
        assert intent_name == "medication"
        assert disease_id is None
        assert department is None
        return [{
            "layer": "L5",
            "score": 0.88,
            "topic": "利尿剂用药治理文档",
            "text": "利尿剂治疗期间需要监测血钾和肾功能。",
            "source": "knowledge-orchestrator",
            "version": "2026.08",
            "document_status": "published",
            "document_id": "DOC-1",
            "chunk_id": "CHUNK-1",
            "retrieval_backend": "knowledge-orchestrator",
        }]

    async def unexpected_local_search(*_args, **_kwargs):
        pytest.fail("published orchestrator evidence should be preferred over local Milvus")

    monkeypatch.setattr(knowledge_orchestrator, "search_published_knowledge", fake_orchestrator)
    monkeypatch.setattr(rag_engine, "search", unexpected_local_search)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["利尿剂用药注意什么"])

    sources, citations, intent = await assistant._retrieve_sources(
        "利尿剂用药注意什么",
        assistant.ROLE_CONFIG["doctor"],
        role="doctor",
    )

    assert sources[0]["source"] == "knowledge-orchestrator"
    assert sources[0]["document_status"] == "published"
    assert citations[0]["document_id"] == "DOC-1"
    assert citations[0]["chunk_id"] == "CHUNK-1"
    assert intent["evidence_diagnostics"]["retrieval_backends"] == ["knowledge-orchestrator"]


@pytest.mark.asyncio
async def test_assistant_retrieval_filters_orchestrator_hits_when_graph_has_orchestrator_keys(
    monkeypatch, isolated_state_store,
):
    from zhenhu.inpatient.agent import assistant
    from zhenhu.inpatient.routes.state_store import set_state
    from zhenhu.inpatient.services import evidence_graph, knowledge_orchestrator

    monkeypatch.setenv("KNOWLEDGE_ORCHESTRATOR_RAG_ENABLED", "true")
    patient_id = "rag-ko-graph-patient"
    set_state(patient_id, {
        "patient_id": patient_id,
        "state_version": 5,
        "disease_template": {"disease_id": "heart_failure", "department": "心内科"},
    })

    def fake_disease_evidence(disease_id, **_kwargs):
        assert disease_id == "heart_failure"
        return {
            "disease_id": disease_id,
            "evidence": [{
                "layer": "L5",
                "source": "knowledge-orchestrator",
                "topic": "心衰利尿剂图谱来源",
                "version": "2026.08",
            }],
            "rules": [],
        }

    async def fake_orchestrator(*_args, **_kwargs):
        return [
            {
                "layer": "L5",
                "score": 0.9,
                "topic": "心衰利尿剂图谱来源",
                "text": "利尿剂治疗期间需要监测血钾和肾功能。",
                "source": "knowledge-orchestrator",
                "version": "2026.08",
                "document_status": "published",
                "retrieval_backend": "knowledge-orchestrator",
            },
            {
                "layer": "L5",
                "score": 0.95,
                "topic": "未进入当前病种图谱的中台文档",
                "text": "这条不应作为当前病种引用。",
                "source": "knowledge-orchestrator",
                "version": "2026.08",
                "document_status": "published",
                "retrieval_backend": "knowledge-orchestrator",
            },
        ]

    monkeypatch.setattr(evidence_graph, "disease_evidence", fake_disease_evidence)
    monkeypatch.setattr(knowledge_orchestrator, "search_published_knowledge", fake_orchestrator)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["利尿剂用药注意什么"])

    sources, citations, intent = await assistant._retrieve_sources(
        "利尿剂用药注意什么",
        assistant.ROLE_CONFIG["doctor"],
        role="doctor",
        patient_id=patient_id,
    )

    assert [source["topic"] for source in sources] == ["心衰利尿剂图谱来源"]
    assert citations[0]["topic"] == "心衰利尿剂图谱来源"
    assert intent["evidence_diagnostics"]["rejected"]["graph_mismatch"] == 1


@pytest.mark.asyncio
async def test_assistant_retrieval_falls_back_to_local_milvus_when_orchestrator_unavailable(monkeypatch):
    from zhenhu.inpatient.agent import assistant, rag_engine
    from zhenhu.inpatient.services import knowledge_orchestrator

    monkeypatch.setenv("KNOWLEDGE_ORCHESTRATOR_RAG_ENABLED", "true")

    async def unavailable_orchestrator(*_args, **_kwargs):
        raise knowledge_orchestrator.KnowledgeOrchestratorUnavailable("connection_failed")

    async def fake_local_search(*_args, **_kwargs):
        return [{
            "layer": "L5",
            "score": 0.82,
            "topic": "本地利尿剂用药规则",
            "text": "本地规则：利尿剂治疗期间需要监测电解质。",
            "source": "drug_interaction",
            "version": "2026-07-20",
        }]

    monkeypatch.setattr(knowledge_orchestrator, "search_published_knowledge", unavailable_orchestrator)
    monkeypatch.setattr(rag_engine, "search", fake_local_search)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["利尿剂用药注意什么"])

    sources, citations, intent = await assistant._retrieve_sources(
        "利尿剂用药注意什么",
        assistant.ROLE_CONFIG["doctor"],
        role="doctor",
    )

    assert sources[0]["retrieval_backend"] == "local-milvus-fallback"
    assert citations[0]["retrieval_backend"] == "local-milvus-fallback"
    assert intent["evidence_diagnostics"]["retrieval_backends"] == ["local-milvus-fallback"]
    assert intent["evidence_diagnostics"]["status"] == "ok"
    assert intent["evidence_diagnostics"]["degraded"] is True
    assert intent["evidence_diagnostics"]["degradation_reasons"] == [
        "knowledge_orchestrator_unavailable:connection_failed",
    ]


@pytest.mark.asyncio
async def test_assistant_retrieval_rejects_non_published_lifecycle_evidence(monkeypatch):
    from zhenhu.inpatient.agent import assistant, rag_engine

    async def fake_search(*_args, **_kwargs):
        return [{
            "layer": "L5",
            "score": 0.9,
            "topic": "已撤回用药文档",
            "text": "这条知识不应被引用。",
            "source": "knowledge-orchestrator",
            "version": "2026.08",
            "document_status": "withdrawn",
            "retrieval_backend": "knowledge-orchestrator",
        }]

    monkeypatch.setattr(rag_engine, "search", fake_search)
    monkeypatch.setattr(assistant, "_expand_query", lambda _message: ["利尿剂用药注意什么"])

    sources, citations, intent = await assistant._retrieve_sources(
        "利尿剂用药注意什么",
        assistant.ROLE_CONFIG["doctor"],
        role="doctor",
    )

    assert sources == []
    assert citations == []
    assert intent["evidence_diagnostics"]["status"] == "lifecycle_mismatch"
    assert intent["evidence_diagnostics"]["rejected"]["lifecycle_mismatch"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["doctor", "nurse", "pharmacist", "patient", "integrative"])
async def test_smalltalk_skips_rag_for_every_assistant_mode(monkeypatch, role):
    from zhenhu.inpatient.agent import assistant, rag_engine

    async def unexpected_search(*_args, **_kwargs):
        pytest.fail("pure smalltalk must not invoke RAG retrieval")

    monkeypatch.setattr(rag_engine, "search", unexpected_search)

    sources, citations, intent = await assistant._retrieve_sources("你好！", assistant.ROLE_CONFIG[role])

    assert sources == []
    assert citations == []
    assert intent["name"] == "smalltalk"


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["帮我写一首诗", "今天股市怎么样", "怎么做蛋炒饭"])
async def test_non_clinical_general_chat_skips_rag(monkeypatch, message):
    from zhenhu.inpatient.agent import assistant, rag_engine

    async def unexpected_search(*_args, **_kwargs):
        pytest.fail("non-clinical open chat must not invoke RAG retrieval")

    monkeypatch.setattr(rag_engine, "search", unexpected_search)

    sources, citations, intent = await assistant._retrieve_sources(message, assistant.ROLE_CONFIG["doctor"])

    assert sources == []
    assert citations == []
    assert intent["name"] == "general_chat"
    assert intent["evidence_diagnostics"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_manager_can_preview_rag_retrieval(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.agent import rag_engine

    async def fake_search(query, *, layer=None, top_k=5, **_kwargs):
        assert query == "检验异常"
        assert layer == ["L6"]
        assert top_k == 5
        return [{"layer": "L6", "score": 0.88, "topic": "血钾", "text": "危急值"}]

    monkeypatch.setattr(rag_engine, "search", fake_search)
    monkeypatch.setattr(rag_engine, "rag_runtime_status", lambda: {"index_revision": "9"})
    headers = {"x-role": "doctor", "x-user-id": "manager-preview", "x-title": quote("科主任")}
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/admin/rag/preview?query=%E6%A3%80%E9%AA%8C%E5%BC%82%E5%B8%B8&layers=L6", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["index_revision"] == "9"
    assert data["count"] == 1
