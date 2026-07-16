"""AgentLoop[T] — 住院域扩展（阶段M: 基类已提取到 contracts）。

阶段M Agent升级: AgentEvent/LoopTrace/AgentLoop 从 contracts 导入，
住院特定方法(gen_input/plan_turn/get_patient_loop)保留在此。
"""

from datetime import datetime
from typing import Generic, TypeVar

from zhenhu.contracts.agent import AgentLoop as _BaseAgentLoop, AgentEvent, LoopTrace  # noqa: F401

T = TypeVar("T")


class PatientAgentLoop(_BaseAgentLoop[T]):
    """住院域 AgentLoop 扩展——新增 gen_input 策略路由和 planTurn 双分支。"""

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
                current_state = self._current_state or {}
                disease_id = current_state.get("disease_template", {}).get("disease_id", "hypertension")
                template = current_state.get("disease_template") or load_template(disease_id)
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
                "latest_round": None,
                "allergies": [],
                "patient_history": {},
                "triage_matched_factors": [],
                "consecutive_abnormal_count": 0,
                "allergy_status": None,
                "discharge_criteria_check": None,
                "clinical_assessments": None,
                "clinical_alerts": [],
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
            result = await inpatient_graph.ainvoke(state, {"configurable": {"thread_id": self._patient_id or "default"}})
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


# 向后兼容别名（阶段M: routes 仍通过..agent.loop 导入 AgentLoop）
AgentLoop = PatientAgentLoop


# 患者级 AgentLoop 实例工厂(并发安全,避免全局单例互相覆盖)
_patient_loops: dict[str, PatientAgentLoop] = {}

def get_patient_loop(patient_id: str) -> PatientAgentLoop:
    """为每个患者创建独立的 AgentLoop 实例(并发安全)。"""
    if patient_id not in _patient_loops:
        _patient_loops[patient_id] = PatientAgentLoop()
    return _patient_loops[patient_id]


def cleanup_patient_loop(patient_id: str) -> None:
    """移除患者AgentLoop实例（出院后调用）。"""
    _patient_loops.pop(patient_id, None)
