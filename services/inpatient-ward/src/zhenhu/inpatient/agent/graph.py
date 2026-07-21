"""LangGraph StateGraph —— 住院协同19节点Agent编排（v1.3 流程扩展）。合并迁入。

自动模式: admission → history_taking → physical_exam → ddx → medication_reconciliation → triage → doctor_confirm → monitoring → news2 → qsofa → (路由) daily_round → nursing → lab_review → monitoring(循环)
分段: medication_adjust → doctor_med_confirm → monitoring | transfer
出院: discharge → doctor_discharge_sign → handoff → doctor_review → patient_confirm

阶段4 Agent框架, 阶段E: 补齐4个缺失临床节点。
P0修复: 路由策略层重写(P0-6)、InpatientState 新增字段(P0-1/P0-2/P0-5/P0-7)。
v1.3: 流程扩展 + 7新节点 + 3卡点 stub。
"""

from typing import TypedDict

try:
    from langgraph.checkpoint.memory import MemorySaver
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        _HAS_SQLITE_SAVER = True
    except ImportError:
        _HAS_SQLITE_SAVER = False
    from langgraph.graph import END, StateGraph
    _HAS_LANGGRAPH = True
except ImportError:
    _HAS_LANGGRAPH = False
    _HAS_SQLITE_SAVER = False
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
    clinical_evidence: list[dict] | None  # Stable citations supporting clinical LLM output
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
    round_history: list[dict]  # 历次 SOAP 查房记录
    transfer_needed: bool  # 是否需要转科
    transfer_target: str | None  # 转科目标
    transfer_reason: str | None  # 转科原因
    allergies: list[str]  # P0-7: 过敏史列表
    patient_history: dict | None  # P0-5: 患者病史
    triage_matched_factors: list[str]  # P0-5: 实际匹配的风险因子
    consecutive_abnormal_count: int  # P0-2: 连续异常计数
    allergy_status: str | None  # P0-7: 过敏史采集状态 (v1.3占位, 待Phase后续)
    discharge_criteria_check: dict | None  # P0-1: 出院标准检查结果
    clinical_assessments: dict | None   # M4-M7入院评估结果
    clinical_alerts: list[str | dict]   # 评估产生的临床警报（兼容历史字符串）
    history_data: dict | None           # v1.3: 病史采集 (CC + HPI + PMH + FH + SH)
    hpi_narrative: str | None           # v1.3: LLM 生成的 HPI 叙事
    ros_findings: dict | None           # v1.3: 系统回顾发现
    pe_data: dict | None                # v1.3: 体格检查各系统记录
    pe_narrative: str | None            # v1.3: LLM 生成的 PE 叙事
    ddx_list: list[dict] | None         # v1.3: 鉴别诊断 TOP N DDx
    ddx_unavailable: bool | None        # v1.3: DDx LLM 降级标记
    nursing_records: list[dict] | None  # v1.3: 护理记录 MAR+I/O+护理措施
    nursing_alerts: list[str] | None    # v1.3: 护理异常报告
    pending_review: dict | None         # v1.3: 医生介入审核挂起 {review_id, checkpoint, payload}
    doctor_confirm_status: str | None   # v1.3: ①入院确认 pending|approved|rejected
    med_confirm_status: str | None      # v1.3: ②调药确认 pending|approved|rejected
    discharge_sign_status: str | None   # v1.3: ③出院签字 pending|signed|rejected
    ddx_reviewed: bool | None                    # v1.1 P1a: DDx 已由医生审阅 sentinel
    discharge_reeval_after_rounds: int | None    # v1.1 P1b: 重评估窗口（round数）
    discharge_reject_history: list[dict] | None  # v1.1 P1b: 拒签历史
    doctor_command: str | None                   # v1.1 P2a: 医生主动命令
    doctor_command_reason: str | None            # v1.1 P2a: 命令原因
    doctor_command_context: dict | None          # v1.1 P2a: 命令上下文
    news2_score: int | None                      # A1: NEWS2 早期预警总分
    news2_risk: str | None                       # A1: NEWS2 风险等级 low|medium|high
    qsofa_score: int | None                      # A2: qSOFA 脓毒症筛查总分
    qsofa_risk: str | None                       # A2: qSOFA 风险等级 low|high
    padua_score: int | None                      # A6: Padua VTE 风险评分总分
    padua_risk: str | None                       # A6: Padua VTE 风险等级 low|high
    shift_summary: str | None                    # #1: LLM 每日交班摘要
    shift_summary_citations: list[dict] | None   # RAG evidence used for the handover summary
    shift_summaries: list[dict] | None           # 历次交班摘要
    shift_summary_last_round: int | None         # 最近生成交班摘要的查房轮次
    discharge_orders: str | None                 # #4: LLM 出院医嘱
    weight_kg: float | None                      # ##3: 体重(kg)
    height_cm: float | None                      # ##3: 身高(cm)
    bmi: float | None                            # ##3: BMI(kg/m²)
    handoff_acknowledged: bool | None            # ##4: 交接确认签收
    ai_recommendation: str | None                # 方案1: LLM临床决策推荐
    last_round_input_counts: dict | None          # 最近查房消费的体征/检验/调药计数
    nursing_last_round: int | None               # 最近生成护理记录的查房轮次
    reviewed_lab_count: int                      # 已审阅检验结果数量（追加式游标）
    patient_confirmation_status: str | None      # pending|confirmed
    patient_confirmation_evidence: list[dict] | None
    patient_confirmation_requirements: list[str] | None
    patient_confirmed_at: str | None


def default_state() -> dict:
    """返回 InpatientState 默认值 dict。gen_input 和 tests 共用单一事实源。

    与 InpatientState TypedDict 字段保持严格同步。
    """
    return {
        "patient_id": "new",
        "disease_template": {},
        "phase": "admission",
        "vital_signs": [],
        "lab_results": [],
        "medication_adjustments": [],
        "reviewed_labs": [],
        "risk_level": "low",
        "discharge_decision": None,
        "handoff_items": [],
        "document_chain": [],
        "event_type": "admission_start",
        "interrupt_pending": False,
        "round_count": 0,
        "round_history": [],
        "knowledge_context": "",
        "clinical_evidence": [],
        "medication_alerts": [],
        "lab_findings": [],
        "transfer_needed": False,
        "transfer_target": None,
        "transfer_reason": None,
        "latest_round": None,
        "allergies": [],
        "patient_history": {},
        "triage_matched_factors": [],
        "consecutive_abnormal_count": 0,
        "allergy_status": None,  # P0-7: 过敏史采集状态 (v1.3占位, 待Phase后续)
        "discharge_criteria_check": None,
        "clinical_assessments": None,
        "clinical_alerts": [],
        "history_data": None,
        "hpi_narrative": None,
        "ros_findings": None,
        "pe_data": None,
        "pe_narrative": None,
        "ddx_list": None,
        "ddx_unavailable": None,
        "nursing_records": None,
        "nursing_alerts": None,
        "pending_review": None,
        "doctor_confirm_status": None,
        "med_confirm_status": None,
        "discharge_sign_status": None,
        "ddx_reviewed": None,
        "discharge_reeval_after_rounds": None,
        "discharge_reject_history": None,
        "doctor_command": None,
        "doctor_command_reason": None,
        "doctor_command_context": None,
        "news2_score": None,
        "news2_risk": None,
        "qsofa_score": None,
        "qsofa_risk": None,
        "padua_score": None,
        "padua_risk": None,
        "shift_summary": None,
        "shift_summary_citations": None,
        "shift_summaries": [],
        "shift_summary_last_round": None,
        "discharge_orders": None,
        "weight_kg": None,
        "height_cm": None,
        "bmi": None,
        "handoff_acknowledged": None,
        "ai_recommendation": None,
        "last_round_input_counts": None,
        "nursing_last_round": None,
        "reviewed_lab_count": 0,
        "patient_confirmation_status": None,
        "patient_confirmation_evidence": [],
        "patient_confirmation_requirements": [],
        "patient_confirmed_at": None,
    }


def after_medication_adjust(state: InpatientState) -> str:
    """调药确认路由（v1.3 §十 10.5）—— 有调药方案则需医生确认卡点②。"""
    if state.get("medication_adjustments") and len(state["medication_adjustments"]) > 0:
        return "doctor_med_confirm"
    return "monitoring"


def after_doctor_confirm(state: InpatientState) -> str:
    """Stop the classic graph at the admission review checkpoint."""
    if state.get("pending_review") or state.get("interrupt_pending"):
        return "end"
    if state.get("doctor_confirm_status") == "approved":
        return "batch_scoring"
    return "end"


def after_doctor_med_confirm(state: InpatientState) -> str:
    """Resume monitoring only after the medication decision is approved."""
    if state.get("pending_review") or state.get("interrupt_pending"):
        return "end"
    if state.get("med_confirm_status") == "approved":
        return "monitoring"
    return "end"


def after_doctor_discharge_sign(state: InpatientState) -> str:
    """Run external discharge effects only after an explicit signature."""
    if state.get("pending_review") or state.get("interrupt_pending"):
        return "end"
    if state.get("discharge_sign_status") in {"signed", "approved"}:
        return "discharge"
    return "end"


def after_discharge_bridge(state: InpatientState) -> str:
    """Do not advance to patient confirmation when the external bridge failed."""
    if state.get("discharge_decision") == "bridge_failed":
        return "end"
    return "patient_confirm"


def _has_new_round_inputs(state: InpatientState) -> bool:
    """Return whether new clinical observations arrived since the last SOAP round."""
    previous = state.get("last_round_input_counts") or {}
    current = {
        "vitals": len(state.get("vital_signs") or []),
        "labs": len(state.get("lab_results") or []),
        "medications": len(state.get("medication_adjustments") or []),
    }
    if not previous:
        # Migration path for snapshots created before incremental round cursors existed.
        state["last_round_input_counts"] = current
        return False
    return any(current[key] > int(previous.get(key, -1)) for key in current)


def after_monitoring(state: InpatientState) -> str:
    """基于文档链决定下一步(策略路由层)。
    
    P0-6修复: 
    - R3: transfer 移到 medication 之后，并增加调药已尝试条件
    - R1/R2: node_triage 现在写 risk_assessment 到 document_chain，修复不可达路由
    P0-1修复:
    - 出院路由(条件5)移到体征警报(条件2)之前，避免慢性病患者被体征达标
      永远触发 medication_adjust 死循环
    - 体征阈值比较加 float() 类型安全转换，防止模板字符串阈值触发 TypeError
    - 已存在 medication_adjustments 时跳过再次路由到 medication
    """
    chain = state.get("document_chain", [])
    labs = state.get("lab_results", [])
    template = state.get("disease_template", {})
    vs = state.get("vital_signs", [])

    # ── P2a: 医生命令优先路由（在现有路由之前）──
    command = state.get("doctor_command")
    if command == "discharge":
        return "handoff"
    if command == "transfer":
        return "transfer"
    # resume: 清除命令标志由 command.py 负责，此处正常执行后续路由
    
    # 条件1: 有新检验结果 → lab_review 审阅
    if labs and len(labs) > len(state.get("reviewed_labs", [])):
        return "lab_review"
    
    # 条件3: 高危 + 体征持续异常 + 调药已尝试 → transfer
    if (state.get("risk_level") == "high"
        and len(vs) >= 3
        and state.get("medication_adjustments")):
        return "transfer"
    
    # 条件4: 入院完成未分层 → triage
    if "intake_note" in chain and "risk_assessment" not in chain:
        return "triage"
    
    # 条件5: 查房完成 + approved → stroke_antithrombotic（v1.3: 出院签字前卒中抗栓检查）
    # P0-1: 出院路由必须在体征警报之前，避免慢性病患者循环卡死
    if "daily_round_note" in chain and state.get("discharge_decision") == "approved":
        return "stroke_antithrombotic"

    # ── P1b: 重评估窗口 ──
    # 医生拒签后，等待 reeval_after_rounds 到期重新发起出院评估
    if state.get("discharge_decision") == "pending_reevaluation":
        current_round = state.get("round_count", 0)
        reeval_after = state.get("discharge_reeval_after_rounds")
        if reeval_after is not None and current_round >= reeval_after:
            # 窗口到期 → 重新发起出院评估
            return "doctor_discharge_sign"

    # 条件2: 体征突破警报 → medication_adjust（MUST be before END to be reachable）
    # P0-1 加防护: 已存在调药记录且医生已确认，不再重复路由到 medication
    if not state.get("medication_adjustments") or not state.get("med_confirm_status"):
        for v_def in template.get("vital_signs", []):
            alert_above = v_def.get("alert_above")
            alert_below = v_def.get("alert_below")
            name = v_def.get("name", "")
            if not name:
                continue
            # P0-2: 跳过非数值阈值（如血压复合值 "180/110"）
            def _to_float(v):
                if v is None:
                    return None
                if isinstance(v, (int, float)):
                    return float(v)
                if isinstance(v, str):
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        return None  # 跳过如 "180/110" 等复合值
                return None

            alert_above_f = _to_float(alert_above)
            alert_below_f = _to_float(alert_below)

            for v in vs[-3:]:
                val = v.get(name, 0)
                if not isinstance(val, (int, float)):
                    continue
                val_f = float(val)
                if (alert_above_f is not None and val_f > alert_above_f) or \
                   (alert_below_f is not None and val_f < alert_below_f):
                    return "medication"

    # 条件5b: 查房已完成后，下一次外部体征仍应进入监测节点。
    if "daily_round_note" in chain and "risk_assessment" in chain:
        if _has_new_round_inputs(state):
            return "daily_round"
        return "monitoring"
    
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


def after_monitoring_result(state: InpatientState) -> str:
    """监测完成后，仅在出院标准达标时进入签字链。"""
    if state.get("discharge_decision") == "approved":
        return "stroke_antithrombotic"
    return END  # type: ignore


def build_inpatient_graph():
    """构建住院协同19节点StateGraph（v1.3 流程扩展）, 带checkpoint和HumanInterrupt。

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
    from .nodes_clinical import (
        node_history_taking,
        node_physical_exam,
        node_ddx,
        node_nursing,
        node_shift_summary,
    )
    from .nodes_checkpoints import (  # P1-4: 三卡点独立
        node_doctor_confirm,
        node_doctor_med_confirm,
        node_doctor_discharge_sign,
    )
    from .nodes_scoring import node_stroke_antithrombotic, node_mdt_trigger
    from .nodes_batch import node_batch_scoring  # v0.3: 并行评分

    builder.add_node("admission", node_admission)
    builder.add_node("history_taking", node_history_taking)
    builder.add_node("physical_exam", node_physical_exam)
    builder.add_node("ddx", node_ddx)
    builder.add_node("medication_reconciliation", node_medication_reconciliation)
    builder.add_node("triage", node_triage)
    builder.add_node("doctor_confirm", node_doctor_confirm)
    builder.add_node("batch_scoring", node_batch_scoring)  # v0.3: padua+vte+news2+qsofa 并行
    builder.add_node("stroke_antithrombotic", node_stroke_antithrombotic)
    builder.add_node("mdt_trigger", node_mdt_trigger)
    builder.add_node("monitoring", node_monitoring)
    builder.add_node("daily_round", node_daily_round)
    builder.add_node("nursing", node_nursing)
    builder.add_node("shift_summary", node_shift_summary)
    builder.add_node("lab_review", node_lab_review)
    builder.add_node("medication_adjust", node_medication_adjust)
    builder.add_node("doctor_med_confirm", node_doctor_med_confirm)
    builder.add_node("transfer", node_transfer)
    builder.add_node("discharge", node_discharge)
    builder.add_node("doctor_discharge_sign", node_doctor_discharge_sign)
    builder.add_node("handoff", node_handoff)
    builder.add_node("doctor_review", node_doctor_review)
    builder.add_node("patient_confirm", node_patient_confirm)

    # ── v1.3 §十 流程扩展边（替换语义，非新增）──
    builder.set_entry_point("admission")

    # 入院链: admission → history_taking → physical_exam → ddx → medication_reconciliation → triage
    builder.add_edge("admission", "history_taking")
    builder.add_edge("history_taking", "physical_exam")
    builder.add_edge("physical_exam", "ddx")
    builder.add_edge("ddx", "medication_reconciliation")
    builder.add_edge("medication_reconciliation", "triage")
    builder.add_edge("triage", "doctor_confirm")

    # 并行评分: doctor_confirm → batch_scoring(padua+vte+news2+qsofa并行) → mdt_trigger
    builder.add_conditional_edges(
        "doctor_confirm",
        after_doctor_confirm,
        {"batch_scoring": "batch_scoring", "end": END},
    )
    builder.add_edge("batch_scoring", "mdt_trigger")
    builder.add_conditional_edges(
        "mdt_trigger",
        after_monitoring,
        {
            "stroke_antithrombotic": "stroke_antithrombotic",  # v1.3: approved → 卒中抗栓检查 → ③出院签字
            "doctor_discharge_sign": "doctor_discharge_sign",
            "handoff": "handoff",
            "triage": "triage",
            "monitoring": "monitoring",
            "daily_round": "daily_round",
            "transfer": "transfer",
            "lab_review": "lab_review",
            "medication": "medication_adjust",
            END: END,
        },
    )

    # 查房→护理→交班摘要→检验→监测: daily_round → nursing → shift_summary → lab_review → monitoring
    builder.add_edge("daily_round", "nursing")
    builder.add_edge("nursing", "shift_summary")
    builder.add_edge("shift_summary", "lab_review")
    builder.add_edge("lab_review", "monitoring")
    builder.add_conditional_edges(
        "monitoring",
        after_monitoring_result,
        {
            "stroke_antithrombotic": "stroke_antithrombotic",
            "doctor_discharge_sign": "doctor_discharge_sign",
            END: END,
        },
    )

    # 卒中抗栓 → 交接草稿 → 出院签字。签字卡点必须能看到完整交接内容。
    builder.add_edge("stroke_antithrombotic", "handoff")

    # 调药确认卡点: medication_adjust → 条件边 doctor_med_confirm(②) → monitoring
    builder.add_conditional_edges(
        "medication_adjust",
        after_medication_adjust,
        {
            "doctor_med_confirm": "doctor_med_confirm",
            "monitoring": "monitoring",
        },
    )
    builder.add_conditional_edges(
        "doctor_med_confirm",
        after_doctor_med_confirm,
        {"monitoring": "monitoring", "end": END},
    )

    # 转科路由
    builder.add_conditional_edges(
        "transfer",
        after_transfer,
        {
            "monitoring": "monitoring",
            "end": END,
        },
    )

    # 出院链: handoff → doctor_discharge_sign(③) → discharge bridge → patient_confirm
    # doctor_review 保留为兼容节点，但不再构成第二套重复人工审核协议。
    builder.add_edge("handoff", "doctor_discharge_sign")
    builder.add_conditional_edges(
        "doctor_discharge_sign",
        after_doctor_discharge_sign,
        {"discharge": "discharge", "end": END},
    )
    builder.add_conditional_edges(
        "discharge",
        after_discharge_bridge,
        {"patient_confirm": "patient_confirm", "end": END},
    )
    builder.add_edge("patient_confirm", END)

    import logging
    _logger = logging.getLogger(__name__)

    from .config import get_checkpoint_db
    # 优先 SQLite 持久化（支持流程中断恢复），回退 MemorySaver
    checkpoint_db = get_checkpoint_db()
    checkpointer = MemorySaver()  # 默认 MemorySaver
    if _HAS_SQLITE_SAVER and checkpoint_db:
        try:
            import sqlite3
            conn = sqlite3.connect(checkpoint_db, check_same_thread=False)
            checkpointer = SqliteSaver(conn)  # type: ignore
        except Exception as _e:
            _logger.warning(
                "SqliteSaver 构造失败，回退 MemorySaver: %s。"
                "请确认 langgraph-checkpoint-sqlite 已安装且版本对齐（§16.2）。", _e
            )
            checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# 全局graph实例(开发阶段用MemorySaver, 若无langgraph则为None)
inpatient_graph = build_inpatient_graph()


# ============================================================================
# P0-3: InpatientState 运行时校验层
# ============================================================================
# InpatientState 是 TypedDict（50+ 字段），运行时无类型/字段校验。
# 字段拼写错误在节点间静默失败，导致数据不一致。
# validate_state() 在校验入口点检查关键字段，缺失时自动修复默认值 + log warning。
# ============================================================================

import logging as _logging

_state_logger = _logging.getLogger(__name__)

# 关键字段及其类型/默认值（来自 default_state()）
_STATE_DEFAULTS: dict[str, tuple[type, object]] = {
    "patient_id": (str, "unknown"),
    "phase": (str, "admission"),
    "vital_signs": (list, []),
    "risk_level": (str, "low"),
    "discharge_decision": (type(None), None),
    "handoff_items": (list, []),
    "document_chain": (list, []),
    "event_type": (str, "unknown"),
    "interrupt_pending": (bool, False),
    "round_count": (int, 0),
    "round_history": (list, []),
    "knowledge_context": (str, ""),
    "clinical_evidence": (list, []),
    "lab_results": (list, []),
    "reviewed_labs": (list, []),
    "medication_adjustments": (list, []),
    "medication_alerts": (list, []),
    "lab_findings": (list, []),
    "latest_round": (dict, None),  # type: ignore
    "transfer_needed": (bool, False),
    "transfer_target": (str, None),  # type: ignore
    "transfer_reason": (str, None),  # type: ignore
    "allergies": (list, []),
    "patient_history": (dict, None),  # type: ignore
    "triage_matched_factors": (list, []),
    "consecutive_abnormal_count": (int, 0),
    "allergy_status": (str, None),  # type: ignore
    "discharge_criteria_check": (dict, None),  # type: ignore
    "clinical_assessments": (dict, None),  # type: ignore
    "clinical_alerts": (list, []),
    "history_data": (dict, None),  # type: ignore
    "hpi_narrative": (str, None),  # type: ignore
    "ros_findings": (dict, None),  # type: ignore
    "pe_data": (dict, None),  # type: ignore
    "pe_narrative": (str, None),  # type: ignore
    "ddx_list": (list, None),  # type: ignore
    "ddx_unavailable": (bool, None),  # type: ignore
    "nursing_records": (list, None),  # type: ignore
    "nursing_alerts": (list, None),  # type: ignore
    "pending_review": (dict, None),  # type: ignore
    "doctor_confirm_status": (str, None),  # type: ignore
    "med_confirm_status": (str, None),  # type: ignore
    "discharge_sign_status": (str, None),  # type: ignore
    "ddx_reviewed": (bool, None),  # type: ignore
    "discharge_reeval_after_rounds": (int, None),  # type: ignore
    "discharge_reject_history": (list, None),  # type: ignore
    "doctor_command": (str, None),  # type: ignore
    "doctor_command_reason": (str, None),  # type: ignore
    "doctor_command_context": (dict, None),  # type: ignore
    "news2_score": (int, None),  # type: ignore
    "news2_risk": (str, None),  # type: ignore
    "qsofa_score": (int, None),  # type: ignore
    "qsofa_risk": (str, None),  # type: ignore
    "padua_score": (int, None),  # type: ignore
    "padua_risk": (str, None),  # type: ignore
    "shift_summary": (str, None),  # type: ignore
    "shift_summary_citations": (list, None),  # type: ignore
    "shift_summaries": (list, []),
    "shift_summary_last_round": (int, None),  # type: ignore
    "discharge_orders": (str, None),  # type: ignore
    "weight_kg": (float, None),  # type: ignore
    "height_cm": (float, None),  # type: ignore
    "bmi": (float, None),  # type: ignore
    "handoff_acknowledged": (bool, None),  # type: ignore
    "ai_recommendation": (str, None),  # type: ignore
    "last_round_input_counts": (dict, None),  # type: ignore
    "nursing_last_round": (int, None),  # type: ignore
    "reviewed_lab_count": (int, 0),
    "patient_confirmation_status": (str, None),  # type: ignore
    "patient_confirmation_evidence": (list, []),
    "patient_confirmation_requirements": (list, []),
    "patient_confirmed_at": (str, None),  # type: ignore
    "workflow_briefs": (dict, {}),
    "agent_turn_status": (str, None),  # type: ignore
    "agent_turn_journal": (list, []),
}


def validate_state(state: dict, entry_point: str = "unknown") -> dict:
    """校验并修复 InpatientState 关键字段。

    对缺失字段自动补充默认值，对类型错误 log warning 但不阻断流程。
    返回修复后的 state dict（原地修改 + 返回同一引用）。

    Args:
        state: 待校验的状态 dict
        entry_point: 调用点标识（gen_input / plan_turn / resume）

    Returns:
        修复后的 state dict（与输入为同一对象）
    """
    fixes: list[str] = []

    for field_name, (expected_type, default_val) in _STATE_DEFAULTS.items():
        if field_name not in state:
            state[field_name] = default_val
            fixes.append(f"{field_name}=缺失→默认值")
            continue

        val = state[field_name]
        # None 总是被接受（大多数字段可为 None）
        if val is None:
            # 但如果默认值不是 None（如 list/dict 的 []），保留 None
            # ——这通常是业务语义的"未初始化"，不强制转换
            continue

        # 类型检查（宽松：仅对 int/bool 做严格检查，str/list/dict 接受子类）
        if expected_type in (int, bool, str):
            if not isinstance(val, expected_type):
                _state_logger.warning(
                    "validate_state[%s]: 字段 %s 类型错误 (期望 %s, 实际 %s=%r)，自动修复",
                    entry_point, field_name, expected_type.__name__, type(val).__name__, val
                )
                try:
                    if expected_type == bool and isinstance(val, (int, str)):
                        # QA B2修复: bool('false') → True 的陷阱
                        if isinstance(val, str):
                            state[field_name] = val.lower() in ("true", "1", "yes")
                        else:
                            state[field_name] = bool(val)
                    elif expected_type == int and isinstance(val, (float, str)):
                        state[field_name] = int(float(val))
                    else:
                        state[field_name] = expected_type(val)
                except (ValueError, TypeError):
                    state[field_name] = default_val
                    _state_logger.warning(
                        "validate_state[%s]: 字段 %s 类型转换失败，回退默认值", entry_point, field_name
                    )
                fixes.append(f"{field_name}=类型修复")

    if fixes:
        _state_logger.warning(
            "validate_state[%s]: 自动修复 %d 处 (%s)", entry_point, len(fixes), ", ".join(fixes[:5])
        )

    # ##1 Canonicalize and deduplicate alerts at the graph boundary.
    if entry_point == "plan_turn" and state.get("clinical_alerts"):
        from ..services.clinical_alerts import normalize_alerts

        alerts = state["clinical_alerts"]
        normalized = normalize_alerts(alerts)
        if len(normalized) < len(alerts):
            _state_logger.info("validate_state[%s]: clinical_alerts normalized %d->%d", entry_point, len(alerts), len(normalized))
        state["clinical_alerts"] = normalized
    return state
