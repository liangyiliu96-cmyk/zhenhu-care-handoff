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
    assert citations


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
