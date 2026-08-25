"""Neo4j-backed, read-only clinical evidence graph.

The graph is derived from governed knowledge sources and disease templates. It
does not store patient identifiers, clinical state, or workflow decisions.
"""

from __future__ import annotations

import hashlib
import json
import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


GRAPH_NAMESPACE = "clinical_evidence_v1"
GRAPH_BUILD_ID = "build:clinical_evidence_v1"
logger = logging.getLogger("zhenhu.evidence_graph")


class EvidenceGraphUnavailable(RuntimeError):
    """Raised when the optional Neo4j graph has not been configured."""


@dataclass(frozen=True)
class EvidenceGraphConfig:
    uri: str
    username: str
    password: str
    database: str

    @property
    def configured(self) -> bool:
        return bool(self.uri and self.username and self.password)


def graph_config() -> EvidenceGraphConfig:
    return EvidenceGraphConfig(
        uri=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687").strip(),
        username=os.environ.get("NEO4J_USERNAME", "").strip(),
        password=os.environ.get("NEO4J_PASSWORD", ""),
        database=os.environ.get("NEO4J_DATABASE", "neo4j").strip() or "neo4j",
    )


@lru_cache(maxsize=1)
def _driver():
    config = graph_config()
    if not config.configured:
        raise EvidenceGraphUnavailable("Neo4j evidence graph is not configured")
    from neo4j import GraphDatabase

    return GraphDatabase.driver(config.uri, auth=(config.username, config.password))


def close_evidence_graph() -> None:
    """Close the cached driver during controlled process shutdown."""
    if _driver.cache_info().currsize:
        _driver().close()
    _driver.cache_clear()


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _stable_id(*parts: str) -> str:
    material = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_templates() -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    template_dir = _source_root() / "disease_templates"
    for path in sorted(template_dir.glob("*.json")):
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        if isinstance(payload, dict) and _text(payload.get("disease_id")):
            templates.append(payload)
    return templates


def build_evidence_documents() -> list[dict[str, str]]:
    """Adapt the authoritative RAG source into stable graph evidence nodes."""
    from ..agent.rag_engine import build_index_documents

    records: list[dict[str, str]] = []
    for layer, documents in build_index_documents().items():
        for document in documents:
            text = _text(document.get("text"))
            topic = _text(document.get("topic"))
            if not text or not topic:
                continue
            records.append({
                "id": _stable_id(layer, _text(document.get("source")), topic, text),
                "layer": layer,
                "source": _text(document.get("source")),
                "category": _text(document.get("category")),
                "topic": topic,
                "text": text,
                "disease_id": _text(document.get("disease_id")),
                "department": _text(document.get("department")),
                "version": _text(document.get("version")),
                "source_type": _text(document.get("source_type")) or "unknown",
                "evidence_level": _text(document.get("evidence_level")) or "unknown",
                "guideline_year": _text(document.get("guideline_year")),
                "source_credibility": _text(document.get("source_credibility")) or "0.5",
                "evidence_metadata_origin": _text(document.get("evidence_metadata_origin")) or "inferred",
            })
    records.extend(_fetch_knowledge_orchestrator_evidence_documents())
    return records


def _fetch_knowledge_orchestrator_evidence_documents() -> list[dict[str, str]]:
    if os.environ.get("KNOWLEDGE_ORCHESTRATOR_GRAPH_SOURCE_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        return []
    try:
        from ..hooks.zhenhu_bridge import KNOWLEDGE_URL, SKIP_BRIDGE
    except Exception as exc:
        logger.info("Evidence graph knowledge source unavailable: %s", type(exc).__name__)
        return []
    if SKIP_BRIDGE:
        return []

    import httpx

    timeout = float(os.environ.get("KNOWLEDGE_ORCHESTRATOR_GRAPH_TIMEOUT_SECONDS", "5.0"))
    size = max(1, min(int(os.environ.get("KNOWLEDGE_ORCHESTRATOR_GRAPH_PAGE_SIZE", "500")), 1000))
    records: list[dict[str, str]] = []
    try:
        with httpx.Client(timeout=timeout) as client:
            page = 1
            while True:
                response = client.get(
                    f"{KNOWLEDGE_URL.rstrip('/')}/knowledge/runtime/evidence-graph-source",
                    params={"page": page, "size": size},
                    headers={"X-User-Role": "system"},
                )
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") if isinstance(payload, dict) else {}
                items = data.get("items", []) if isinstance(data, dict) else []
                for item in items:
                    if isinstance(item, dict):
                        records.append(_knowledge_orchestrator_graph_record(item))
                total = int(data.get("total") or 0) if isinstance(data, dict) else 0
                if not items or len(records) >= total:
                    break
                page += 1
    except Exception as exc:
        logger.warning("Evidence graph knowledge-orchestrator source skipped: %s", type(exc).__name__)
        return []
    return records


def _knowledge_orchestrator_graph_record(item: dict[str, Any]) -> dict[str, str]:
    document_id = _text(item.get("document_id"))
    chunk_id = _text(item.get("chunk_id"))
    stable_id = _text(item.get("id")) or _stable_id("knowledge-orchestrator", document_id, chunk_id)
    return {
        "id": stable_id,
        "layer": _text(item.get("layer")),
        "source": "knowledge-orchestrator",
        "category": _text(item.get("category")),
        "topic": _text(item.get("topic")),
        "text": _text(item.get("text")),
        "disease_id": _text(item.get("disease_id")),
        "department": _text(item.get("department")),
        "version": _text(item.get("version")),
        "source_type": _text(item.get("source_type")),
        "evidence_level": _text(item.get("evidence_level")),
        "guideline_year": _text(item.get("guideline_year")),
        "source_credibility": _text(item.get("source_credibility")),
        "evidence_metadata_origin": _text(item.get("evidence_metadata_origin")),
    }


def build_rule_documents() -> list[dict[str, str]]:
    """Extract explicit pathway rules from disease templates without inference."""
    records: list[dict[str, str]] = []
    for template in _load_templates():
        disease_id = _text(template.get("disease_id"))
        disease_name = _text(template.get("name")) or disease_id
        department = _text(template.get("department"))

        for item in template.get("discharge_criteria", []):
            if isinstance(item, dict):
                content = _text(item.get("description") or item.get("condition"))
                if content:
                    records.append(_rule_record(disease_id, disease_name, department, "DischargeCriterion", "HAS_DISCHARGE_CRITERION", _text(item.get("condition")), content))

        for item in template.get("handoff_instructions", []):
            if not isinstance(item, dict):
                continue
            kind, content = _text(item.get("type")), _text(item.get("content"))
            if not content:
                continue
            label, relationship = {
                "monitoring": ("MonitoringRule", "HAS_MONITORING_RULE"),
                "medication": ("MedicationRule", "HAS_MEDICATION_RULE"),
            }.get(kind, ("CareTask", "HAS_CARE_TASK"))
            records.append(_rule_record(disease_id, disease_name, department, label, relationship, kind, content))

        for item in template.get("complication_monitoring", []):
            if not isinstance(item, dict):
                continue
            complication = _text(item.get("complication"))
            watches = "; ".join(_text(value) for value in item.get("watch", []) if _text(value))
            content = "; ".join(part for part in (complication, watches) if part)
            if content:
                records.append(_rule_record(disease_id, disease_name, department, "MonitoringRule", "HAS_MONITORING_RULE", complication, content))

        medication_protocol = template.get("medication_protocol")
        if isinstance(medication_protocol, dict):
            for group, entries in medication_protocol.items():
                for value in entries if isinstance(entries, list) else [entries]:
                    content = _text(value)
                    if content:
                        records.append(_rule_record(disease_id, disease_name, department, "MedicationRule", "HAS_MEDICATION_RULE", _text(group), content))

        for variable in template.get("monitoring_variables", []):
            if isinstance(variable, dict):
                name = _text(variable.get("name"))
                if name:
                    records.append(_rule_record(disease_id, disease_name, department, "MonitoringRule", "HAS_MONITORING_RULE", name, name))
    return records


def _rule_record(disease_id: str, disease_name: str, department: str, label: str, relationship: str, rule_key: str, content: str) -> dict[str, str]:
    return {
        "id": _stable_id(disease_id, label, rule_key, content),
        "disease_id": disease_id,
        "disease_name": disease_name,
        "department": department,
        "label": label,
        "relationship": relationship,
        "rule_key": rule_key or content,
        "content": content,
    }


_CONSTRAINTS = (
    "CREATE CONSTRAINT evidence_graph_evidence_id IF NOT EXISTS FOR (node:Evidence) REQUIRE node.id IS UNIQUE",
    "CREATE CONSTRAINT evidence_graph_disease_id IF NOT EXISTS FOR (node:Disease) REQUIRE node.id IS UNIQUE",
    "CREATE CONSTRAINT evidence_graph_rule_id IF NOT EXISTS FOR (node:ClinicalRule) REQUIRE node.id IS UNIQUE",
)


def rebuild_evidence_graph() -> dict[str, Any]:
    """Rebuild the dedicated knowledge namespace from source-controlled inputs."""
    config = graph_config()
    if not config.configured:
        raise EvidenceGraphUnavailable("Neo4j evidence graph is not configured")

    evidence_records = build_evidence_documents()
    rule_records = build_rule_documents()
    rebuilt_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "rebuilt_at": rebuilt_at,
        "evidence_count": len(evidence_records),
        "rule_count": len(rule_records),
        "evidence_sources": json.dumps(_evidence_source_counts(evidence_records), ensure_ascii=False),
        "knowledge_source_enabled": os.environ.get("KNOWLEDGE_ORCHESTRATOR_GRAPH_SOURCE_ENABLED", "").strip().lower() in {"1", "true", "yes"},
    }
    with _driver().session(database=config.database) as session:
        for statement in _CONSTRAINTS:
            session.run(statement).consume()
        session.execute_write(_replace_namespace, evidence_records, rule_records, metadata)
    return {
        "evidence": len(evidence_records),
        "evidence_sources": _evidence_source_counts(evidence_records),
        "rules": len(rule_records),
        "diseases": len({item["disease_id"] for item in rule_records}),
        "rebuilt_at": rebuilt_at,
        "knowledge_source_enabled": metadata["knowledge_source_enabled"],
    }


def _evidence_source_counts(records: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        source = _text(record.get("source")) or "unknown"
        counts[source] = counts.get(source, 0) + 1
    return dict(sorted(counts.items()))


def _clear_namespace(tx: Any) -> None:
    tx.run("MATCH (node:ZhenhuKnowledge {namespace: $namespace}) DETACH DELETE node", namespace=GRAPH_NAMESPACE).consume()


def _replace_namespace(
    tx: Any,
    evidence_records: list[dict[str, str]],
    rule_records: list[dict[str, str]],
    metadata: dict[str, Any],
) -> None:
    """Keep the destructive reset and all replacements in one graph transaction."""
    _clear_namespace(tx)
    for record in evidence_records:
        _merge_evidence(tx, record)
    for record in rule_records:
        _merge_rule(tx, record)
    tx.run(
        """
        MERGE (build:EvidenceGraphBuild:ZhenhuKnowledge {id: $build_id})
        SET build.namespace = $namespace,
            build.rebuilt_at = $rebuilt_at,
            build.evidence_count = $evidence_count,
            build.rule_count = $rule_count,
            build.evidence_sources = $evidence_sources,
            build.knowledge_source_enabled = $knowledge_source_enabled
        """,
        **metadata,
        build_id=GRAPH_BUILD_ID,
        namespace=GRAPH_NAMESPACE,
    ).consume()


def _merge_evidence(tx: Any, record: dict[str, str]) -> None:
    tx.run(
        """
        MERGE (e:Evidence:ZhenhuKnowledge {id: $id})
        SET e.namespace = $namespace, e.layer = $layer, e.source = $source,
            e.category = $category, e.topic = $topic, e.text = $text, e.version = $version,
            e.source_type = $source_type, e.evidence_level = $evidence_level,
            e.guideline_year = $guideline_year, e.source_credibility = $source_credibility,
            e.evidence_metadata_origin = $evidence_metadata_origin
        MERGE (layer:KnowledgeLayer:ZhenhuKnowledge {id: $layer_id})
        SET layer.namespace = $namespace, layer.name = $layer
        MERGE (source:EvidenceSource:ZhenhuKnowledge {id: $source_id})
        SET source.namespace = $namespace, source.name = $source
        MERGE (category:EvidenceCategory:ZhenhuKnowledge {id: $category_id})
        SET category.namespace = $namespace, category.name = $category
        MERGE (e)-[:IN_LAYER]->(layer)
        MERGE (e)-[:SOURCED_FROM]->(source)
        MERGE (e)-[:IN_CATEGORY]->(category)
        FOREACH (_ IN CASE WHEN $disease_id = '' THEN [] ELSE [1] END |
          MERGE (d:Disease:ZhenhuKnowledge {id: $disease_id})
          ON CREATE SET d.namespace = $namespace, d.name = $disease_id
          MERGE (e)-[:ABOUT_DISEASE]->(d)
        )
        FOREACH (_ IN CASE WHEN $department = '' THEN [] ELSE [1] END |
          MERGE (department:Department:ZhenhuKnowledge {id: $department_id})
          SET department.namespace = $namespace, department.name = $department
          MERGE (e)-[:APPLIES_TO]->(department)
        )
        """,
        **record,
        namespace=GRAPH_NAMESPACE,
        layer_id=f"layer:{record['layer']}",
        source_id=f"source:{record['source']}",
        category_id=f"category:{record['category']}",
        department_id=f"department:{record['department']}",
    ).consume()


def _merge_rule(tx: Any, record: dict[str, str]) -> None:
    label = record["label"]
    if label not in {"DischargeCriterion", "MedicationRule", "MonitoringRule", "CareTask"}:
        raise ValueError(f"Unsupported evidence graph rule label: {label}")
    relationship = record["relationship"]
    query = f"""
        MERGE (d:Disease:ZhenhuKnowledge {{id: $disease_id}})
        SET d.namespace = $namespace, d.name = $disease_name
        MERGE (r:ClinicalRule:{label}:ZhenhuKnowledge {{id: $id}})
        SET r.namespace = $namespace, r.key = $rule_key, r.content = $content
        MERGE (d)-[:{relationship}]->(r)
        FOREACH (_ IN CASE WHEN $department = '' THEN [] ELSE [1] END |
          MERGE (department:Department:ZhenhuKnowledge {{id: $department_id}})
          SET department.namespace = $namespace, department.name = $department
          MERGE (d)-[:OWNED_BY_DEPARTMENT]->(department)
        )
    """
    tx.run(query, **record, namespace=GRAPH_NAMESPACE, department_id=f"department:{record['department']}").consume()


def evidence_graph_status() -> dict[str, Any]:
    """Return safe status without exposing credentials or source text."""
    config = graph_config()
    status: dict[str, Any] = {
        "configured": config.configured,
        "database": config.database,
        "reachable": False,
        "nodes": {},
        "relationships": 0,
        "last_rebuild": None,
        "needs_rebuild": False,
    }
    if not config.configured:
        return status
    try:
        with _driver().session(database=config.database) as session:
            status["reachable"] = bool(session.run("RETURN 1 AS ready").single()["ready"])
            labels = session.run(
                "MATCH (node:ZhenhuKnowledge {namespace: $namespace}) UNWIND labels(node) AS label RETURN label, count(*) AS count",
                namespace=GRAPH_NAMESPACE,
            )
            status["nodes"] = {record["label"]: record["count"] for record in labels if record["label"] != "ZhenhuKnowledge"}
            status["relationships"] = session.run(
                "MATCH (:ZhenhuKnowledge {namespace: $namespace})-[relationship]->(:ZhenhuKnowledge {namespace: $namespace}) RETURN count(relationship) AS count",
                namespace=GRAPH_NAMESPACE,
            ).single()["count"]
            build = session.run(
                """
                MATCH (build:EvidenceGraphBuild:ZhenhuKnowledge {id: $build_id, namespace: $namespace})
                RETURN build.rebuilt_at AS rebuilt_at, build.evidence_count AS evidence_count,
                       build.rule_count AS rule_count, build.evidence_sources AS evidence_sources,
                       build.knowledge_source_enabled AS knowledge_source_enabled
                """,
                build_id=GRAPH_BUILD_ID,
                namespace=GRAPH_NAMESPACE,
            ).single()
            if build:
                try:
                    sources = json.loads(build["evidence_sources"] or "{}")
                except (TypeError, ValueError):
                    sources = {}
                status["last_rebuild"] = {
                    "rebuilt_at": build["rebuilt_at"],
                    "evidence": build["evidence_count"] or 0,
                    "rules": build["rule_count"] or 0,
                    "evidence_sources": sources,
                    "knowledge_source_enabled": bool(build["knowledge_source_enabled"]),
                }
            _merge_knowledge_sync_status(status)
    except Exception as exc:
        status["error"] = type(exc).__name__
    return status


def _merge_knowledge_sync_status(status: dict[str, Any]) -> None:
    """Add governed knowledge freshness without making graph health depend on it."""
    if os.environ.get("KNOWLEDGE_ORCHESTRATOR_GRAPH_SOURCE_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        status["knowledge_sync"] = {"enabled": False}
        return
    last_rebuild = status.get("last_rebuild") or {}
    since = last_rebuild.get("rebuilt_at")
    try:
        from ..hooks.zhenhu_bridge import KNOWLEDGE_URL, SKIP_BRIDGE
    except Exception:
        status["knowledge_sync"] = {"enabled": False, "reason": "bridge_unavailable"}
        return
    if SKIP_BRIDGE:
        status["knowledge_sync"] = {"enabled": False, "reason": "bridge_disabled"}
        return
    try:
        import httpx

        timeout = float(os.environ.get("KNOWLEDGE_ORCHESTRATOR_GRAPH_TIMEOUT_SECONDS", "5.0"))
        with httpx.Client(timeout=timeout) as client:
            response = client.get(
                f"{KNOWLEDGE_URL.rstrip('/')}/knowledge/runtime/evidence-graph-status",
                params={"since": since} if since else {},
                headers={"X-User-Role": "system"},
            )
            response.raise_for_status()
            payload = response.json()
            sync = payload.get("data") if isinstance(payload, dict) else {}
            status["knowledge_sync"] = {"enabled": True, **(sync if isinstance(sync, dict) else {})}
            status["needs_rebuild"] = bool(status["knowledge_sync"].get("requires_rebuild"))
    except Exception as exc:
        status["knowledge_sync"] = {"enabled": True, "status": "unknown", "reason": type(exc).__name__}


def _project_disease_subgraph(
    disease_id: str,
    graph: dict[str, Any],
    *,
    disease_name: str = "",
    department: str = "",
) -> dict[str, Any]:
    """Project a bounded Neo4j disease subgraph into browser-safe nodes and edges."""
    root_id = f"disease:{disease_id}"
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()

    def add_node(node_id: str, kind: str, label: str, **detail: Any) -> None:
        if not node_id or node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({"id": node_id, "kind": kind, "label": label or node_id, **detail})

    def add_edge(source: str, relation: str, target: str) -> None:
        if not source or not relation or not target:
            return
        edge_id = f"{source}|{relation}|{target}"
        if edge_id in edge_ids:
            return
        edge_ids.add(edge_id)
        edges.append({"id": edge_id, "source": source, "target": target, "relation": relation})

    add_node(root_id, "disease", disease_name or disease_id, disease_id=disease_id, department=department)
    if department:
        department_id = f"department:{department}"
        add_node(department_id, "department", department)
        add_edge(root_id, "OWNED_BY_DEPARTMENT", department_id)

    for evidence in graph.get("evidence") or []:
        if not isinstance(evidence, dict):
            continue
        evidence_id = _text(evidence.get("id"))
        if not evidence_id:
            continue
        source = _text(evidence.get("source"))
        layer = _text(evidence.get("layer"))
        add_node(
            evidence_id,
            "evidence",
            _text(evidence.get("topic")) or "临床证据",
            source=source,
            layer=layer,
            category=_text(evidence.get("category")),
            text=_text(evidence.get("text")),
            version=_text(evidence.get("version")),
            source_type=_text(evidence.get("source_type")),
            evidence_level=_text(evidence.get("evidence_level")),
            guideline_year=_text(evidence.get("guideline_year")),
            source_credibility=_text(evidence.get("source_credibility")),
            evidence_metadata_origin=_text(evidence.get("evidence_metadata_origin")),
        )
        add_edge(evidence_id, "ABOUT_DISEASE", root_id)
        if source:
            source_id = f"source:{source}"
            add_node(source_id, "source", source)
            add_edge(evidence_id, "SOURCED_FROM", source_id)
        if layer:
            layer_id = f"layer:{layer}"
            add_node(layer_id, "layer", layer)
            add_edge(evidence_id, "IN_LAYER", layer_id)

    for rule in graph.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        relation = _text(rule.get("relation"))
        content = _text(rule.get("content"))
        key = _text(rule.get("key"))
        rule_id = _text(rule.get("id")) or _stable_id(disease_id, relation, key, content)
        add_node(
            rule_id,
            "rule",
            content or key or "临床规则",
            key=key,
            content=content,
            labels=[_text(label) for label in rule.get("labels", []) if _text(label)],
            relation=relation,
        )
        add_edge(root_id, relation or "HAS_CLINICAL_RULE", rule_id)

    return {"disease_id": disease_id, "root_id": root_id, "nodes": nodes, "edges": edges}


def disease_graph_visualization(disease_id: str, focus: str = "", limit: int = 12) -> dict[str, Any]:
    """Return a small, interactive graph projection without exposing Neo4j access."""
    normalized_disease = disease_id.strip()
    if not normalized_disease:
        raise ValueError("disease_id is required")
    config = graph_config()
    if not config.configured:
        raise EvidenceGraphUnavailable("Neo4j evidence graph is not configured")

    safe_limit = max(1, min(int(limit), 16))
    graph = disease_evidence(normalized_disease, focus=focus, limit=safe_limit)
    with _driver().session(database=config.database) as session:
        record = session.run(
            """
            MATCH (d:Disease:ZhenhuKnowledge {id: $disease_id, namespace: $namespace})
            OPTIONAL MATCH (d)-[:OWNED_BY_DEPARTMENT]->(department:Department:ZhenhuKnowledge {namespace: $namespace})
            RETURN d.name AS disease_name, head(collect(department.name)) AS department
            """,
            disease_id=normalized_disease,
            namespace=GRAPH_NAMESPACE,
        ).single()

    return _project_disease_subgraph(
        normalized_disease,
        graph,
        disease_name=_text(record["disease_name"]) if record else "",
        department=_text(record["department"]) if record else "",
    )


def disease_evidence(disease_id: str, focus: str = "", limit: int = 12) -> dict[str, Any]:
    """Read evidence and explicit pathway rules associated with one disease."""
    normalized_disease = disease_id.strip()
    if not normalized_disease:
        raise ValueError("disease_id is required")
    config = graph_config()
    if not config.configured:
        raise EvidenceGraphUnavailable("Neo4j evidence graph is not configured")
    safe_limit = max(1, min(int(limit), 30))
    normalized_focus = focus.strip().lower()
    with _driver().session(database=config.database) as session:
        evidence = session.run(
            """
            MATCH (d:Disease:ZhenhuKnowledge {id: $disease_id})<-[:ABOUT_DISEASE]-(e:Evidence:ZhenhuKnowledge)
            WHERE $focus = '' OR toLower(e.topic + ' ' + e.text) CONTAINS $focus
            RETURN e.id AS id, e.layer AS layer, e.source AS source, e.category AS category,
             e.topic AS topic, e.text AS text, e.version AS version,
                    e.source_type AS source_type, e.evidence_level AS evidence_level,
                    e.guideline_year AS guideline_year, e.source_credibility AS source_credibility,
                    e.evidence_metadata_origin AS evidence_metadata_origin
            ORDER BY e.layer, e.topic LIMIT $limit
            """,
            disease_id=normalized_disease,
            focus=normalized_focus,
            limit=safe_limit,
        )
        rules = session.run(
            """
            MATCH (d:Disease:ZhenhuKnowledge {id: $disease_id})-[relationship]->(r:ClinicalRule:ZhenhuKnowledge)
            WHERE $focus = '' OR toLower(r.key + ' ' + r.content) CONTAINS $focus
            RETURN r.id AS id, type(relationship) AS relation, labels(r) AS labels, r.key AS key, r.content AS content
            ORDER BY relation, key LIMIT $limit
            """,
            disease_id=normalized_disease,
            focus=normalized_focus,
            limit=safe_limit,
        )
        return {"disease_id": normalized_disease, "evidence": [dict(record) for record in evidence], "rules": [dict(record) for record in rules]}
