"""LangGraph StateGraph —— 住院协同11节点Agent编排。合并迁入。

自动模式: admission -> triage -> monitoring -> daily_round/medication_adjust/lab_review/transfer -> discharge -> handoff
人工审核: doctor_review(HumanInterrupt) -> patient_confirm

阶段4 Agent框架, 阶段E: 补齐4个缺失临床节点。
P0修复: 路由策略层重写(P0-6)、InpatientState 新增字段(P0-1/P0-2/P0-5/P0-7)。
"""

from typing import TypedDict

try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph
    _HAS_LANGGRAPH = True
except ImportError:
    _HAS_LANGGRAPH = False
    MemorySaver = None  # type: ignore
    END = "end"  # type: ignore
    StateGraph = None  # type: ignore


class InpatientState(TypedDict):
    """住院协同 Agent 状态 Schema。"""

    patient_id: str
    disease_template: dict  # 当前病种模板
    phase: str  # admission|triage|monitoring|discharge|handoff|review|confirm|daily_round|medication_adjust|lab_review|transfer
    vital_signs: list[dict]  # 生命体征记录
    risk_level: str  # low|medium|high
    discharge_decision: str | None  # pending|approved|rejected|pending_reevaluation
    handoff_items: list[dict]  # 交接事项列表
    knowledge_context: str  # RAG检索聚合上下文
    interrupt_pending: bool  # 是否等待人工审核
    event_type: str | None  # 当前触发的事件类型
    document_chain: list[str]  # 已生成的文档链
    lab_results: list[dict]  # 检验/检查结果列表
    reviewed_labs: list[dict]  # 已审阅的检验结果
    medication_adjustments: list[dict]  # 用药调整记录
    medication_alerts: list[dict]  # 用药警报
    lab_findings: list[dict]  # 检验审阅发现
    latest_round: dict | None  # 最近一次查房笔记
    round_count: int  # 查房次数
    transfer_needed: bool  # 是否需要转科
    transfer_target: str | None  # 转科目标
    transfer_reason: str | None  # 转科原因
    allergies: list[str]  # P0-7: 过敏史列表
    patient_history: dict | None  # P0-5: 患者病史
    triage_matched_factors: list[str]  # P0-5: 实际匹配的风险因子
    consecutive_abnormal_count: int  # P0-2: 连续异常计数
    allergy_status: str | None  # P0-7: 过敏史采集状态
    discharge_criteria_check: dict | None  # P0-1: 出院标准检查结果


def after_monitoring(state: InpatientState) -> str:
    """基于文档链决定下一步(策略路由层)。
    
    P0-6修复: 
    - R3: transfer 移到 medication 之后，并增加调药已尝试条件
    - R1/R2: node_triage 现在写 risk_assessment 到 document_chain，修复不可达路由
    """
    chain = state.get("document_chain", [])
    labs = state.get("lab_results", [])
    template = state.get("disease_template", {})
    vs = state.get("vital_signs", [])
    
    # 条件1: 有新检验结果 → lab_review 审阅
    if labs and len(labs) > len(state.get("reviewed_labs", [])):
        return "lab_review"
    
    # 条件2: 体征突破警报 → medication_adjust（在 transfer 之前）
    for v_def in template.get("vital_signs", []):
        alert_above = v_def.get("alert_above")
        alert_below = v_def.get("alert_below")
        name = v_def.get("name", "")
        if not name:
            continue
        for v in vs[-3:]:
            val = v.get(name, 0)
            if not isinstance(val, (int, float)):
                continue
            if (alert_above is not None and val > alert_above) or \
               (alert_below is not None and val < alert_below):
                return "medication"
    
    # 条件3: 高危 + 体征持续异常 + 调药已尝试 → transfer
    if (state.get("risk_level") == "high"
        and len(vs) >= 3
        and state.get("medication_adjustments")):
        return "transfer"
    
    # 条件4: 入院完成未分层 → triage
    if "intake_note" in chain and "risk_assessment" not in chain:
        return "triage"
    
    # 条件5: 查房完成 + approved → discharge
    if "daily_round_note" in chain and state.get("discharge_decision") == "approved":
        return "discharge"
    
    # 条件6: 已分层未查房 → daily_round
    if "risk_assessment" in chain and "daily_round_note" not in chain:
        return "daily_round"
    
    # 默认: 持续监测
    return "monitoring"


def after_transfer(state: InpatientState) -> str:
    """转科后路由 —— 需要转科则结束, 否则继续监测。"""
    if state.get("transfer_needed"):
        return "end"
    return "monitoring"


def build_inpatient_graph():
    """构建住院协同11节点StateGraph, 带checkpoint和HumanInterrupt。

    若 langgraph 未安装则返回 None。
    """
    if not _HAS_LANGGRAPH:
        return None
    builder = StateGraph(InpatientState)

    from .nodes import (
        node_admission,
        node_daily_round,
        node_discharge,
        node_doctor_review,
        node_handoff,
        node_lab_review,
        node_medication_adjust,
        node_medication_reconciliation,
        node_monitoring,
        node_patient_confirm,
        node_transfer,
        node_triage,
    )

    builder.add_node("admission", node_admission)
    builder.add_node("medication_reconciliation", node_medication_reconciliation)
    builder.add_node("triage", node_triage)
    builder.add_node("monitoring", node_monitoring)
    builder.add_node("discharge", node_discharge)
    builder.add_node("handoff", node_handoff)
    builder.add_node("doctor_review", node_doctor_review)
    builder.add_node("patient_confirm", node_patient_confirm)

    builder.add_node("daily_round", node_daily_round)
    builder.add_node("medication_adjust", node_medication_adjust)
    builder.add_node("lab_review", node_lab_review)
    builder.add_node("transfer", node_transfer)

    # 自动模式链路
    builder.set_entry_point("admission")
    builder.add_edge("admission", "medication_reconciliation")
    builder.add_edge("medication_reconciliation", "triage")
    builder.add_edge("triage", "monitoring")

    builder.add_conditional_edges(
        "monitoring",
        after_monitoring,
        {
            "discharge": "discharge",
            "triage": "triage",
            "monitoring": "monitoring",
            "daily_round": "daily_round",
            "transfer": "transfer",
            "lab_review": "lab_review",
            "medication": "medication_adjust",
        },
    )

    builder.add_edge("daily_round", "monitoring")
    builder.add_edge("medication_adjust", "monitoring")
    builder.add_edge("lab_review", "monitoring")
    builder.add_conditional_edges(
        "transfer",
        after_transfer,
        {
            "monitoring": "monitoring",
            "end": END,
        },
    )

    builder.add_edge("discharge", "handoff")
    builder.add_edge("handoff", "doctor_review")
    builder.add_edge("doctor_review", "patient_confirm")
    builder.add_edge("patient_confirm", END)

    return builder.compile(checkpointer=MemorySaver())


# 全局graph实例(开发阶段用MemorySaver, 若无langgraph则为None)
inpatient_graph = build_inpatient_graph()
