"""Agent节点——兼容聚合入口。各节点已拆分到 nodes_admission/nodes_monitoring/nodes_handoff。"""
from .nodes_admission import (
    load_template, list_templates,
    node_admission, node_triage, node_medication_reconciliation,
    _RISK_FACTOR_MATCHERS, _match_patient_risk_factors,
    _check_discharge_criteria, _evaluate_criterion,
)
from .nodes_monitoring import (
    node_monitoring, node_daily_round, node_medication_adjust,
    node_lab_review, node_transfer, _analyze_vs_trend,
)
from .nodes_handoff import (
    node_discharge, node_handoff, node_doctor_review, node_patient_confirm,
)
