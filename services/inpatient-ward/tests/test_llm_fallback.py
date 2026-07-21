from __future__ import annotations

import pytest

from zhenhu.inpatient.agent.llm_utils import FailoverProvider, clear_provider_cache, get_provider_for_node, safe_llm_invoke


class _FailingProvider:
    async def invoke(self, _prompt: str, context=None):
        return {"error": "primary unavailable", "source_type": "source_none"}


class _WorkingProvider:
    async def invoke(self, _prompt: str, context=None):
        return {"summary": "local draft", "source_type": "source_knowledge"}


@pytest.mark.asyncio
async def test_failover_provider_uses_ollama_result_after_primary_error():
    provider = FailoverProvider(_FailingProvider(), _WorkingProvider(), "nursing")

    result = await safe_llm_invoke(provider, "create a nursing draft", retries=0, caller="nursing")

    assert result == {"summary": "local draft", "source_type": "source_knowledge"}


@pytest.mark.asyncio
async def test_safe_invoke_treats_provider_error_payload_as_failure():
    result = await safe_llm_invoke(_FailingProvider(), "unavailable", retries=0, caller="nursing")

    assert result is None


def test_provider_factory_uses_local_fallback_without_deepseek_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_FALLBACK_CALLERS", "nursing")
    clear_provider_cache()

    provider = get_provider_for_node("nursing")

    assert isinstance(provider, FailoverProvider)
    assert provider.primary is None
    assert provider.fallback is not None
