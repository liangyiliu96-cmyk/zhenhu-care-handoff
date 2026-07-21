"""Clinical evidence graph source and safe-degradation coverage."""


def test_template_rules_cover_discharge_medication_monitoring_and_care_tasks():
    from zhenhu.inpatient.services.evidence_graph import build_rule_documents

    rules = build_rule_documents()
    labels = {rule["label"] for rule in rules}
    relationships = {rule["relationship"] for rule in rules}

    assert rules
    assert {"DischargeCriterion", "MedicationRule", "MonitoringRule", "CareTask"} <= labels
    assert {"HAS_DISCHARGE_CRITERION", "HAS_MEDICATION_RULE", "HAS_MONITORING_RULE", "HAS_CARE_TASK"} <= relationships
    assert all(rule["disease_id"] and rule["content"] and rule["id"] for rule in rules)


def test_graph_status_is_safe_when_configuration_is_absent(monkeypatch):
    from zhenhu.inpatient.services import evidence_graph

    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    evidence_graph._driver.cache_clear()

    status = evidence_graph.evidence_graph_status()

    assert status["configured"] is False
    assert status["reachable"] is False
    assert status["nodes"] == {}


def test_disease_graph_projection_returns_bounded_clickable_nodes_and_edges():
    from zhenhu.inpatient.services.evidence_graph import _project_disease_subgraph

    projection = _project_disease_subgraph(
        "heart_failure",
        {
            "evidence": [
                {"id": "e-1", "layer": "L5", "source": "指南 A", "category": "心衰", "topic": "容量管理", "text": "每日评估容量状态", "version": "2025"},
                {"id": "e-2", "layer": "L5", "source": "指南 A", "category": "心衰", "topic": "利尿剂", "text": "根据容量状态调整", "version": "2025"},
            ],
            "rules": [
                {"id": "r-1", "relation": "HAS_MONITORING_RULE", "labels": ["ClinicalRule", "MonitoringRule"], "key": "weight", "content": "每日监测体重"},
            ],
        },
        disease_name="心力衰竭",
        department="心内科",
    )

    nodes = {node["id"]: node for node in projection["nodes"]}
    edge_relations = {(edge["source"], edge["relation"], edge["target"]) for edge in projection["edges"]}

    assert nodes["disease:heart_failure"]["label"] == "心力衰竭"
    assert nodes["e-1"]["kind"] == "evidence"
    assert nodes["source:指南 A"]["kind"] == "source"
    assert nodes["layer:L5"]["kind"] == "layer"
    assert len([node for node in projection["nodes"] if node["id"] == "source:指南 A"]) == 1
    assert ("e-1", "ABOUT_DISEASE", "disease:heart_failure") in edge_relations
    assert ("disease:heart_failure", "HAS_MONITORING_RULE", "r-1") in edge_relations
    assert ("disease:heart_failure", "OWNED_BY_DEPARTMENT", "department:心内科") in edge_relations
