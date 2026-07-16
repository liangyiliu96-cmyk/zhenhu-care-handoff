"""AgentLoop[T] — 参考 RAGFlow agent_loop.go: push-based 泛型事件循环。合并迁入。

阶段G: 将 StateGraph 包装为类型安全的 AgentLoop, 支持:
- Push 事件注入(外部体征/检验/医嘱)
- GenInput 策略路由(入院/监测/出院不同入口)
- planTurn 双分支(New Turn + Resume)
- 每步事件审计
"""

from typing import Generic, TypeVar
from dataclasses import dataclass, field
from datetime import datetime

T = TypeVar("T")


@dataclass
class AgentEvent:
    """AgentLoop 事件基类。"""

    event_type: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "system"  # his|nurse_station|doctor|system


@dataclass
class LoopTrace:
    """单次 Agent 运行的完整审计追踪。"""

    turn_id: str
    entry_strategy: str  # "new_admission"|"monitoring_resume"|"discharge_initiate"
    node_path: list[str] = field(default_factory=list)
    events_pushed: int = 0
    errors: list[dict] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None


class AgentLoop(Generic[T]):
    """类型化 Agent 事件循环。

    参考 RAGFlow agent_loop.go: push-based event loop with GenInput routing。
    """

    def __init__(self):
        self._queue: list[AgentEvent] = []
        self._traces: list[LoopTrace] = []
        self._current_state: dict | None = None

    def push(self, *events: AgentEvent) -> int:
        """推送外部事件入队。返回队列长度。"""
        self._queue.extend(events)
        return len(self._queue)

    def gen_input(self, strategy: str) -> dict:
        """策略注入: 根据入口策略生成初始 State。

        策略路由:
        - "new_admission": 加载病种模板, 初始化空白 State(phase=admission)
        - "monitoring_resume": 恢复当前患者状态, 继续监测循环
        - "discharge_initiate": 基于当前状态, 强制设置 discharge_decision=approved
        """
        from .nodes import load_template  # delay-import

        if strategy == "new_admission":
            try:
                template = load_template("hypertension")
            except FileNotFoundError:
                template = {}
            return {
                "patient_id": "new",
                "disease_template": template,
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
                "knowledge_context": "",
                "medication_alerts": [],
                "lab_findings": [],
                "transfer_needed": False,
                "transfer_target": None,
                "transfer_reason": None,
            }
        elif strategy == "monitoring_resume":
            return self._current_state or {}
        elif strategy == "discharge_initiate":
            state = self._current_state or {}
            state["discharge_decision"] = "approved"
            return state
        return {}

    async def plan_turn(self, state: dict) -> dict:
        """planTurn 双分支: New Turn(GEN) vs Resume。"""
        from .graph import inpatient_graph  # delay-import

        if inpatient_graph is None:
            return state

        trace = LoopTrace(
            turn_id=f"turn-{len(self._traces)}",
            entry_strategy=state.get("phase", "unknown"),
        )
        try:
            result = await inpatient_graph.ainvoke(state)
            trace.node_path = result.get("document_chain", [])
            trace.completed_at = datetime.now().isoformat()
            self._traces.append(trace)
            if len(self._traces) > 100:
                self._traces = self._traces[-100:]
            self._current_state = result
            return result
        except Exception as e:
            trace.errors.append({"error": str(e), "phase": state.get("phase")})
            trace.completed_at = datetime.now().isoformat()
            self._traces.append(trace)
            if len(self._traces) > 100:
                self._traces = self._traces[-100:]
            return state

    @property
    def traces(self) -> list[LoopTrace]:
        """最近 N 条审计追踪(最多保留 100 条)。"""
        return self._traces[-100:]

    @property
    def current_state(self) -> dict | None:
        return self._current_state


# 患者级 AgentLoop 实例工厂(并发安全,避免全局单例互相覆盖)
_patient_loops: dict[str, AgentLoop] = {}

def get_patient_loop(patient_id: str) -> AgentLoop:
    """为每个患者创建独立的 AgentLoop 实例(并发安全)。"""
    if patient_id not in _patient_loops:
        _patient_loops[patient_id] = AgentLoop()
    return _patient_loops[patient_id]
