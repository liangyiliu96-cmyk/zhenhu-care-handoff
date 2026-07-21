"""Neo4j-backed, read-only clinical evidence graph.

The graph is derived only from versioned RAG sources and disease templates. It
does not store patient identifiers, clinical state, or workflow decisions.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


GRAPH_NAMESPACE = "clinical_evidence_v1"


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
            })
    return records


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


def rebuild_evidence_graph() -> dict[str, int]:
    """Rebuild the dedicated knowledge namespace from source-controlled inputs."""
    config = graph_config()
    if not config.configured:
        raise EvidenceGraphUnavailable("Neo4j evidence graph is not configured")

    evidence_records = build_evidence_documents()
    rule_records = build_rule_documents()
    with _driver().session(database=config.database) as session:
        for statement in _CONSTRAINTS:
            session.run(statement).consume()
        session.execute_write(_replace_namespace, evidence_records, rule_records)
    return {
        "evidence": len(evidence_records),
        "rules": len(rule_records),
        "diseases": len({item["disease_id"] for item in rule_records}),
    }


def _clear_namespace(tx: Any) -> None:
    tx.run("MATCH (node:ZhenhuKnowledge {namespace: $namespace}) DETACH DELETE node", namespace=GRAPH_NAMESPACE).consume()


def _replace_namespace(tx: Any, evidence_records: list[dict[str, str]], rule_records: list[dict[str, str]]) -> None:
    """Keep the destructive reset and all replacements in one graph transaction."""
    _clear_namespace(tx)
    for record in evidence_records:
        _merge_evidence(tx, record)
    for record in rule_records:
        _merge_rule(tx, record)


def _merge_evidence(tx: Any, record: dict[str, str]) -> None:
    tx.run(
        """
        MERGE (e:Evidence:ZhenhuKnowledge {id: $id})
        SET e.namespace = $namespace, e.layer = $layer, e.source = $source,
            e.category = $category, e.topic = $topic, e.text = $text, e.version = $version
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
    status: dict[str, Any] = {"configured": config.configured, "database": config.database, "reachable": False, "nodes": {}, "relationships": 0}
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
    except Exception as exc:
        status["error"] = type(exc).__name__
    return status


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
                   e.topic AS topic, e.text AS text, e.version AS version
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
