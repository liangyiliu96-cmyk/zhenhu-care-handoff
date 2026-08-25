"""Client-side adapter for governed knowledge-orchestrator retrieval."""

from __future__ import annotations

import os
from typing import Any, Iterable

import httpx


class KnowledgeOrchestratorUnavailable(RuntimeError):
    """Raised when governed knowledge retrieval cannot be reached."""


def is_knowledge_orchestrator_rag_enabled() -> bool:
    return os.environ.get("KNOWLEDGE_ORCHESTRATOR_RAG_ENABLED", "").strip().lower() in {"1", "true", "yes"}


async def search_published_knowledge(
    query: str,
    *,
    top_k: int,
    allowed_layers: Iterable[str],
    role: str,
    intent_name: str,
    disease_id: str | None = None,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """Search published knowledge documents and normalize them to RAG hit shape."""
    if not is_knowledge_orchestrator_rag_enabled():
        return []
    from ..hooks.zhenhu_bridge import KNOWLEDGE_URL, SKIP_BRIDGE

    if SKIP_BRIDGE:
        return []
    normalized_query = query.strip()
    if not normalized_query:
        return []

    timeout = float(os.environ.get("KNOWLEDGE_ORCHESTRATOR_RAG_TIMEOUT_SECONDS", "2.0"))
    try:
        layers = ",".join(layer for layer in allowed_layers if layer)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{KNOWLEDGE_URL.rstrip('/')}/knowledge/search",
                params={
                    "q": normalized_query,
                    "top_k": max(1, min(int(top_k), 20)),
                    "layers": layers,
                    "disease_id": disease_id or "",
                    "department": department or "",
                },
                headers={"X-User-Role": role or "system"},
            )
    except Exception as exc:
        raise KnowledgeOrchestratorUnavailable(type(exc).__name__) from exc
    if response.status_code != 200:
        raise KnowledgeOrchestratorUnavailable(f"HTTP_{response.status_code}")

    payload = response.json()
    results = ((payload.get("data") or {}).get("results") or []) if isinstance(payload, dict) else []
    primary_layer = next(iter(allowed_layers), "")
    return [_normalize_result(item, primary_layer=primary_layer, intent_name=intent_name) for item in results if isinstance(item, dict)]


def _normalize_result(item: dict[str, Any], *, primary_layer: str, intent_name: str) -> dict[str, Any]:
    citation = item.get("citation") if isinstance(item.get("citation"), dict) else {}
    title = _text(citation.get("document_title") or item.get("document_title") or item.get("document_id") or "知识文档")
    document_id = _text(item.get("document_id"))
    chunk_id = _text(item.get("chunk_id"))
    return {
        "layer": _text(citation.get("layer") or primary_layer),
        "score": float(item.get("score") or 0),
        "source": "knowledge-orchestrator",
        "topic": title,
        "category": _text(citation.get("category") or f"orchestrator:{intent_name or 'general'}"),
        "disease_id": _text(citation.get("disease_id") or item.get("disease_id")),
        "department": _text(citation.get("department") or item.get("department")),
        "version": _text(citation.get("document_version") or item.get("document_version")),
        "indexed_at": citation.get("indexed_at") or item.get("indexed_at"),
        "text": _text(item.get("text"))[:500],
        "document_id": document_id,
        "chunk_id": chunk_id,
        "location": _text(item.get("location") or citation.get("coordinates")),
        "document_status": _text(citation.get("document_status") or item.get("document_status") or "published"),
        "source_type": _text(citation.get("source_type") or item.get("source_type") or "unknown"),
        "evidence_level": _text(citation.get("evidence_level") or item.get("evidence_level") or "unknown"),
        "guideline_year": citation.get("guideline_year") or item.get("guideline_year"),
        "source_credibility": float(citation.get("source_credibility") or item.get("source_credibility") or 0.5),
        "evidence_metadata_origin": _text(citation.get("evidence_metadata_origin") or item.get("evidence_metadata_origin") or "inferred"),
        "conflict_detected": bool(citation.get("conflict_detected") or item.get("conflict_detected")),
        "conflict_group": _text(citation.get("conflict_group") or item.get("conflict_group")),
        "conflict_note": _text(citation.get("conflict_note") or item.get("conflict_note")),
        "retrieval_strategy_version": _text(citation.get("retrieval_strategy_version") or "knowledge-orchestrator-search"),
        "retrieval_backend": "knowledge-orchestrator",
    }


def _text(value: Any) -> str:
    return str(value or "").strip()
