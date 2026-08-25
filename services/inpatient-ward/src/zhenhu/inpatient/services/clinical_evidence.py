"""Stable citation objects for RAG-supported clinical output."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def build_rag_citations(
    hits: list[dict[str, Any]],
    *,
    retrieval_diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert retrieval hits into bounded, stable, audit-safe citation records."""
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    retrieved_at = datetime.now(timezone.utc).isoformat()
    diagnostics = retrieval_diagnostics or {}
    for hit in hits:
        excerpt = str(hit.get("text") or "").strip()[:300]
        source = str(hit.get("source") or "unknown")[:100]
        topic = str(hit.get("topic") or "untitled")[:200]
        version = str(hit.get("version") or "unversioned")[:100]
        layer = str(hit.get("layer") or "unknown")[:32]
        fingerprint = json.dumps(
            {"layer": layer, "source": source, "topic": topic, "version": version, "excerpt": excerpt},
            ensure_ascii=False,
            sort_keys=True,
        )
        citation_id = f"rag:{hashlib.sha256(fingerprint.encode()).hexdigest()[:24]}"
        if citation_id in seen:
            continue
        seen.add(citation_id)
        citations.append({
            "citation_id": citation_id,
            "knowledge_layer": layer,
            "source": source,
            "topic": topic,
            "document_id": hit.get("document_id"),
            "chunk_id": hit.get("chunk_id"),
            "document_version": version,
            "document_status": hit.get("document_status") or "published",
            "location": hit.get("location"),
            "indexed_at": hit.get("indexed_at"),
            "retrieved_at": retrieved_at,
            "retrieval_score": hit.get("score"),
            "retrieval_backend": hit.get("retrieval_backend") or "local-milvus",
            "retrieval_strategy_version": hit.get("retrieval_strategy_version"),
            "retrieval_policy_version": diagnostics.get("policy_version"),
            "evidence_status": diagnostics.get("status"),
            "source_type": hit.get("source_type") or "unknown",
            "evidence_level": hit.get("evidence_level") or "unknown",
            "guideline_year": hit.get("guideline_year"),
            "source_credibility": hit.get("source_credibility", 0.5),
            "evidence_metadata_origin": hit.get("evidence_metadata_origin") or "inferred",
            "conflict_detected": bool(hit.get("conflict_detected")),
            "conflict_group": hit.get("conflict_group"),
            "conflict_note": hit.get("conflict_note"),
            "excerpt": excerpt,
        })
    return citations


def merge_rag_citations(
    existing: list[dict[str, Any]] | None,
    additions: list[dict[str, Any]] | None,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Append citations once while retaining a bounded patient evidence trail."""
    merged = [item for item in (existing or []) if isinstance(item, dict)]
    seen = {item.get("citation_id") for item in merged if item.get("citation_id")}
    for citation in additions or []:
        if not isinstance(citation, dict):
            continue
        citation_id = citation.get("citation_id")
        if citation_id and citation_id in seen:
            continue
        merged.append(citation)
        if citation_id:
            seen.add(citation_id)
    return merged[-limit:]
