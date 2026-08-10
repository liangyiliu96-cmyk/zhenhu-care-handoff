"""Agent节点——兼容聚合入口。各节点已拆分到独立文件。

文件层级（P1-4优化后）:
- llm_utils.py: LLM 工具层（safe_llm_invoke, 缓存, DDxItem）
- nodes_checkpoints.py: 医生三卡点（confirm/med_confirm/discharge_sign）
- nodes_clinical.py: 临床节点（history_taking/pe/ddx/nursing/shift_summary）
- nodes_admission.py: 入院/分诊/用药核对
- nodes_monitoring.py: 监测/查房/调药/检验/转科
- nodes_handoff.py: 出院/交接/审核/确认
- nodes_scoring.py: 临床评分（NEWS2/qSOFA/...）

本模块为再导出聚合入口（graph.py/loop.py/routes 均从本模块导入），
"未使用"的 import 均为对外再导出，故文件级关闭 F401。
"""
# ruff: noqa: F401
from .nodes_admission import (
    load_template, list_templates,
    node_admission, node_triage, node_medication_reconciliation,
    _RISK_FACTOR_MATCHERS, _match_patient_risk_factors
)
from .nodes_monitoring import (
    node_monitoring, node_daily_round, node_medication_adjust,
    node_lab_review, node_transfer, _analyze_vs_trend,
)
from .nodes_handoff import (
    node_discharge, node_handoff, node_doctor_review, node_patient_confirm,
)
# P1-4: 三卡点从独立文件导入
from .nodes_checkpoints import (
    node_doctor_confirm, node_doctor_med_confirm, node_doctor_discharge_sign,
)
