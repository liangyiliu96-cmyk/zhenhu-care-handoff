"""Evidence-constrained retrieval policy for clinical RAG answers.

This layer keeps role, patient, source, score, and version rules out of the
raw Milvus adapter.  It is intentionally deterministic so operators can tell
why evidence was accepted, filtered, or degraded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


POLICY_VERSION = "evidence-constrained-rag-2026-08-25.1"


SearchFn = Callable[..., Awaitable[list[dict[str, Any]]]]
RerankFn = Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]]


@dataclass(frozen=True)
class EvidenceScope:
    role: str
    allowed_layers: tuple[str, ...]
    intent_name: str
    intent_label: str
    patient_id: str = ""
    disease_id: str = ""
    department: str = ""
    patient_status: dict[str, Any] = field(default_factory=dict)
    graph_context: dict[str, Any] = field(default_factory=dict)
    graph_evidence_keys: tuple[str, ...] = ()
    required_knowledge_version: str = ""
    patient_context_enabled: bool = False


@dataclass(frozen=True)
class EvidenceRetrievalResult:
    hits: list[dict[str, Any]]
    diagnostics: dict[str, Any]


def build_evidence_scope(
    *,
    role: str,
    allowed_layers: list[str],
    intent: dict[str, Any],
    patient_id: str = "",
    patient_context_enabled: bool = False,
) -> EvidenceScope:
    """Build the permitted retrieval scope from identity and patient state."""
    disease_id = ""
    department = ""
    patient_status: dict[str, Any] = {}
    if patient_id and patient_context_enabled:
        try:
            from ..routes.state_store import get_state

            state = get_state(patient_id) or {}
        except Exception:
            state = {}
        template = state.get("disease_template") if isinstance(state.get("disease_template"), dict) else {}
        disease_id = _text(template.get("disease_id") or state.get("disease_id"))
        department = _text(template.get("department") or state.get("department"))
        patient_status = {
            "state_version": state.get("state_version", ""),
            "risk_level": state.get("risk_level", ""),
            "news2_score": state.get("news2_score", ""),
            "discharge_readiness": (state.get("discharge_readiness") or {}).get("score", "")
            if isinstance(state.get("discharge_readiness"), dict)
            else "",
            "active_alert_count": len(state.get("clinical_alerts") or []),
        }
    graph_context, graph_evidence_keys = _build_graph_context(disease_id) if disease_id else ({}, ())

    return EvidenceScope(
        role=role,
        allowed_layers=tuple(allowed_layers),
        intent_name=_text(intent.get("name")),
        intent_label=_text(intent.get("label")),
        patient_id=patient_id if patient_context_enabled else "",
        disease_id=disease_id,
        department=department,
        patient_status={key: value for key, value in patient_status.items() if value != ""},
        graph_context=graph_context,
        graph_evidence_keys=graph_evidence_keys,
        required_knowledge_version=_text(os.environ.get("RAG_REQUIRED_KNOWLEDGE_VERSION")),
        patient_context_enabled=patient_context_enabled,
    )


async def retrieve_evidence(
    *,
    queries: list[str],
    scope: EvidenceScope,
    search_fn: SearchFn,
    top_k: int,
    min_score: float,
    final_k: int,
    rerank_fn: RerankFn,
) -> EvidenceRetrievalResult:
    """Run scoped retrieval with fail-closed filtering and explicit diagnosis."""
    attempts = _attempts(scope)
    raw_hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    errors: list[str] = []
    attempted_scopes: list[str] = []

    for attempt in attempts:
        attempted_scopes.append(attempt["name"])
        scoped_new_hits = 0
        scoped_usable_hits = 0
        for query in queries[:3]:
            try:
                hits = await search_fn(
                    query,
                    layer=list(scope.allowed_layers),
                    top_k=top_k,
                    disease_id=attempt.get("disease_id") or None,
                    department=attempt.get("department") or None,
                )
            except Exception as exc:
                errors.append(f"{attempt['name']}:{type(exc).__name__}")
                continue
            for hit in hits or []:
                if str(hit.get("layer") or "") not in scope.allowed_layers:
                    continue
                key = _hit_key(hit)
                if key in seen:
                    continue
                seen.add(key)
                raw_hits.append(hit)
                scoped_new_hits += 1
                if (
                    _lifecycle_allowed(hit)
                    and _graph_allowed(hit, scope)
                    and _version_allowed(hit, scope.required_knowledge_version)
                    and float(hit.get("score") or 0) >= min_score
                ):
                    scoped_usable_hits += 1
        # If patient-scoped usable evidence exists, keep it authoritative instead of
        # mixing in broad matches. Broad fallback only runs when scoped evidence
        # has no usable candidate at all.
        if scoped_new_hits and scoped_usable_hits and attempt["name"] != "broad":
            break

    lifecycle_filtered, lifecycle_rejected = _filter_by_lifecycle(raw_hits)
    graph_filtered, graph_rejected = _filter_by_graph(lifecycle_filtered, scope)
    version_filtered, version_rejected = _filter_by_version(graph_filtered, scope.required_knowledge_version)
    scored_hits = [hit for hit in version_filtered if float(hit.get("score") or 0) >= min_score]
    ranked_hits = rerank_fn(" ".join(queries[:1]), scored_hits) if len(scored_hits) > final_k else scored_hits
    accepted = ranked_hits[:final_k]

    status = "ok"
    if errors and not raw_hits:
        status = "index_error"
    elif not raw_hits:
        status = "no_evidence"
    elif lifecycle_rejected and not lifecycle_filtered:
        status = "lifecycle_mismatch"
    elif graph_rejected and not graph_filtered:
        status = "graph_mismatch"
    elif version_rejected and not version_filtered:
        status = "version_mismatch"
    elif not scored_hits:
        status = "low_relevance"

    degradation_reasons = sorted({
        reason
        for hit in raw_hits
        if (reason := _text(hit.get("fallback_reason")))
    })
    graph_status = _text(scope.graph_context.get("status")) if isinstance(scope.graph_context, dict) else ""
    if scope.patient_context_enabled and scope.disease_id and graph_status == "unavailable":
        graph_error = _text(scope.graph_context.get("error")) or "unknown"
        degradation_reasons.append(f"evidence_graph_unavailable:{graph_error}")
    diagnostics = {
        "policy_version": POLICY_VERSION,
        "status": status,
        "role": scope.role,
        "intent": scope.intent_name,
        "allowed_layers": list(scope.allowed_layers),
        "attempted_scopes": attempted_scopes,
        "patient_scope": {
            "patient_id": scope.patient_id,
            "disease_id": scope.disease_id,
            "department": scope.department,
            "status": scope.patient_status,
        },
        "graph_context": scope.graph_context,
        "knowledge_version": scope.required_knowledge_version,
        "raw_count": len(raw_hits),
        "accepted_count": len(accepted),
        "retrieval_backends": sorted({_text(hit.get("retrieval_backend") or "local-milvus") for hit in raw_hits}),
        "degradation_reasons": degradation_reasons,
        "rejected": {
            "low_score": max(0, len(version_filtered) - len(scored_hits)),
            "version_mismatch": version_rejected,
            "lifecycle_mismatch": lifecycle_rejected,
            "graph_mismatch": graph_rejected,
        },
        "errors": errors,
        "degraded": status != "ok" or bool(degradation_reasons),
    }
    return EvidenceRetrievalResult(hits=accepted, diagnostics=diagnostics)


def evidence_sources_from_hits(hits: list[dict[str, Any]], diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    """Build prompt-safe sources while preserving traceability metadata."""
    sources: list[dict[str, Any]] = []
    for hit in hits:
        sources.append({
            "layer": hit.get("layer"),
            "topic": hit.get("topic"),
            "text": str(hit.get("text") or "")[:300],
            "source": hit.get("source") or "unknown",
            "category": hit.get("category") or "",
            "document_version": hit.get("version") or "unversioned",
            "indexed_at": hit.get("indexed_at"),
            "retrieval_score": hit.get("score"),
            "disease_id": hit.get("disease_id") or "",
            "department": hit.get("department") or "",
            "document_id": hit.get("document_id") or "",
            "chunk_id": hit.get("chunk_id") or "",
            "location": hit.get("location") or "",
            "document_status": hit.get("document_status") or "published",
            "retrieval_strategy_version": hit.get("retrieval_strategy_version") or "",
            "retrieval_backend": hit.get("retrieval_backend") or "local-milvus",
            "retrieval_policy_version": diagnostics.get("policy_version", POLICY_VERSION),
        })
    return sources


def skipped_diagnostics(*, role: str, intent: dict[str, Any], allowed_layers: list[str]) -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "status": "skipped",
        "role": role,
        "intent": intent.get("name"),
        "allowed_layers": allowed_layers,
        "attempted_scopes": [],
        "raw_count": 0,
        "accepted_count": 0,
        "retrieval_backends": [],
        "degradation_reasons": [],
        "graph_context": {},
        "rejected": {"low_score": 0, "version_mismatch": 0, "lifecycle_mismatch": 0, "graph_mismatch": 0},
        "errors": [],
        "degraded": False,
    }


def error_diagnostics(*, role: str, intent: dict[str, Any], allowed_layers: list[str], exc: Exception) -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "status": "index_error",
        "role": role,
        "intent": intent.get("name"),
        "allowed_layers": allowed_layers,
        "attempted_scopes": [],
        "raw_count": 0,
        "accepted_count": 0,
        "retrieval_backends": [],
        "degradation_reasons": [],
        "graph_context": {},
        "rejected": {"low_score": 0, "version_mismatch": 0, "lifecycle_mismatch": 0, "graph_mismatch": 0},
        "errors": [type(exc).__name__],
        "degraded": True,
    }


def _attempts(scope: EvidenceScope) -> list[dict[str, str]]:
    attempts: list[dict[str, str]] = []
    if scope.patient_context_enabled and scope.disease_id and scope.department:
        attempts.append({"name": "patient_disease_department", "disease_id": scope.disease_id, "department": scope.department})
    if scope.patient_context_enabled and scope.disease_id:
        attempts.append({"name": "patient_disease", "disease_id": scope.disease_id})
    if scope.patient_context_enabled and scope.department:
        attempts.append({"name": "patient_department", "department": scope.department})
    attempts.append({"name": "broad"})
    return attempts


def _filter_by_version(hits: list[dict[str, Any]], required_version: str) -> tuple[list[dict[str, Any]], int]:
    if not required_version:
        return hits, 0
    accepted = [hit for hit in hits if _text(hit.get("version")) == required_version]
    return accepted, len(hits) - len(accepted)


def _filter_by_lifecycle(hits: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    accepted = [hit for hit in hits if _lifecycle_allowed(hit)]
    return accepted, len(hits) - len(accepted)


def _filter_by_graph(hits: list[dict[str, Any]], scope: EvidenceScope) -> tuple[list[dict[str, Any]], int]:
    accepted = [hit for hit in hits if _graph_allowed(hit, scope)]
    return accepted, len(hits) - len(accepted)


def _graph_allowed(hit: dict[str, Any], scope: EvidenceScope) -> bool:
    if not scope.graph_evidence_keys:
        return True
    key = _graph_key(hit)
    if key in set(scope.graph_evidence_keys):
        return True
    backend = _text(hit.get("retrieval_backend") or "local-milvus")
    if backend == "knowledge-orchestrator" and not any("|knowledge-orchestrator|" in graph_key for graph_key in scope.graph_evidence_keys):
        return True
    return False


def _lifecycle_allowed(hit: dict[str, Any]) -> bool:
    status = _text(hit.get("document_status"))
    return not status or status == "published"


def _version_allowed(hit: dict[str, Any], required_version: str) -> bool:
    return not required_version or _text(hit.get("version")) == required_version


def _hit_key(hit: dict[str, Any]) -> str:
    return "|".join(
        _text(hit.get(key)) for key in ("layer", "source", "topic", "version")
    ) + "|" + _text(hit.get("text"))[:120]


def _graph_key(hit: dict[str, Any]) -> str:
    return "|".join(_text(hit.get(key)) for key in ("layer", "source", "topic", "version"))


def _build_graph_context(disease_id: str) -> tuple[dict[str, Any], tuple[str, ...]]:
    try:
        from ..services.evidence_graph import disease_evidence

        graph = disease_evidence(disease_id, limit=50)
    except Exception as exc:
        return {"status": "unavailable", "disease_id": disease_id, "error": type(exc).__name__}, ()
    evidence_items = [item for item in graph.get("evidence", []) if isinstance(item, dict)] if isinstance(graph, dict) else []
    return (
        {
            "status": "ok",
            "disease_id": disease_id,
            "evidence_count": len(evidence_items),
            "rule_count": len(graph.get("rules", [])) if isinstance(graph, dict) else 0,
        },
        tuple(_graph_key(item) for item in evidence_items),
    )


def _text(value: Any) -> str:
    return str(value or "").strip()
