"""AgentLoop[T] — 住院域扩展（阶段M: 基类已提取到 contracts）。

阶段M Agent升级: AgentEvent/LoopTrace/AgentLoop 从 contracts 导入，
住院特定方法(gen_input/plan_turn/get_patient_loop)保留在此。
"""

import asyncio
import hashlib
import json
import logging
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Awaitable, Callable, TypeVar

from zhenhu.contracts.agent import (
    AgentLoop as _BaseAgentLoop,
    AgentEvent,
    LoopTrace,  # noqa: F401
    CircuitBreaker,
    CircuitBreakerOpenError,  # noqa: F401
    AgentAuditHook,
)

T = TypeVar("T")
logger = logging.getLogger("zhenhu.inpatient")


class PatientAgentLoop(_BaseAgentLoop[T]):
    """住院域 AgentLoop 扩展——新增 gen_input 策略路由和 planTurn 双分支。"""

    def __init__(self):
        super().__init__()
        self._circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
        self._audit_hook = AgentAuditHook()

    def pending_state_snapshot(self) -> dict[str, Any] | None:
        """Return the complete graph state associated with the current review gate."""
        state = self._current_state
        if not isinstance(state, dict) or not state.get("pending_review"):
            return None
        return deepcopy(state)

    def gen_input(self, strategy: str) -> dict:
        """策略注入: 根据入口策略生成初始 State。"""
        from .nodes import load_template  # delay-import
        from .graph import validate_state  # P0-3

        if strategy == "new_admission":
            from .graph import default_state
            state = default_state()
            try:
                current_state = self._current_state or {}
                disease_id = current_state.get("disease_template", {}).get("disease_id", "hypertension")
                template = current_state.get("disease_template") or load_template(disease_id)
                state["disease_template"] = template
            except FileNotFoundError:
                pass
            # A1+A2: NEWS2/qSOFA 初始化为 None
            state["news2_score"] = None
            state["news2_risk"] = None
            state["qsofa_score"] = None
            state["qsofa_risk"] = None
            # A6: Padua VTE 风险评分初始化为 None
            state["padua_score"] = None
            state["padua_risk"] = None
            return validate_state(state, "gen_input:new_admission")
        elif strategy == "monitoring_resume":
            return validate_state(self._current_state or {}, "gen_input:monitoring_resume")
        elif strategy == "discharge_initiate":
            state = self._current_state or {}
            state["discharge_decision"] = "approved"
            return validate_state(state, "gen_input:discharge_initiate")
        return validate_state({}, "gen_input:unknown")

    async def plan_turn(self, state: dict) -> dict:
        """planTurn 双分支: New Turn(GEN) vs Resume。"""
        from .config import get_graph_mode
        from .graph import inpatient_graph  # delay-import
        import uuid

        if inpatient_graph is None:
            return state
        guarded = self._guard_turn(state)
        if guarded is not None:
            return guarded

        pid = getattr(self, '_patient_id', 'default')
        graph_mode = get_graph_mode()
        if graph_mode == "stateful":
            thread_id = pid  # Phase-2: 稳定 pid + SqliteSaver
        else:
            thread_id = f"{pid}-{uuid.uuid4().hex[:8]}"  # classic: 随机，避免 checkpoint 合并

        async def execute(validated_state: dict) -> dict:
            return await inpatient_graph.ainvoke(validated_state, {"configurable": {"thread_id": thread_id}})

        result = await self._execute_turn(state, entry_strategy="graph", execute=execute)
        return self._finalize_turn_result(result)

    async def plan_monitoring_turn(self, state: dict, *, event_type: str, collect: bool = True) -> dict:
        """Advance a monitoring event without replaying the admission graph.

        The main graph has an admission entry point. Re-invoking it for every
        bedside observation replays unrelated LLM nodes and can outlive the
        HTTP write timeout. Monitoring writes instead run the relevant nodes
        and preserve the same medication/discharge review checkpoints.
        """
        from .nodes_checkpoints import node_doctor_discharge_sign, node_doctor_med_confirm
        from .nodes_handoff import node_discharge, node_handoff, node_patient_confirm
        from .nodes_monitoring import node_lab_review, node_medication_adjust, node_monitoring
        guarded = self._guard_turn(state)
        if guarded is not None:
            return guarded

        async def execute(validated_state: dict) -> dict:
            working_state = deepcopy(validated_state)
            if event_type == "lab":
                working_state.update(await node_lab_review(working_state))

            working_state.update(await node_monitoring(working_state))
            # Bedside nursing documentation may refresh discharge criteria, but
            # it cannot initiate a new discharge/handoff workflow by itself.
            if event_type == "nursing" and state.get("discharge_decision") != "approved":
                working_state["discharge_decision"] = state.get("discharge_decision")
                return working_state
            if working_state.get("discharge_decision") == "approved":
                working_state.update(await node_handoff(working_state))
                working_state.update(await node_doctor_discharge_sign(working_state))
                if isinstance(working_state.get("pending_review"), dict):
                    working_state["interrupt_pending"] = True
                    return working_state
                if working_state.get("discharge_sign_status") in {"signed", "approved"}:
                    working_state.update(await node_discharge(working_state))
                    working_state.update(await node_patient_confirm(working_state))
                return working_state

            medication_update = await node_medication_adjust(working_state)
            if medication_update:
                working_state.update(medication_update)
                working_state.update(await node_doctor_med_confirm(working_state))
                if isinstance(working_state.get("pending_review"), dict):
                    working_state["interrupt_pending"] = True
            return working_state

        result = await self._execute_turn(
            state,
            entry_strategy=f"monitoring:{event_type}",
            execute=execute,
            collect=collect,
        )
        return self._finalize_turn_result(result)

    def _guard_turn(self, state: dict) -> dict | None:
        if state.get("doctor_command") == "hold":
            return {**state, "status": "held", "phase": state.get("phase", "monitoring"), "message": f"患者已暂停: {state.get('doctor_command_reason', '')}"}
        if self._circuit_breaker.is_open():
            remaining = int(self._circuit_breaker.remaining_cooldown())
            return {**state, "status": "circuit_open", "phase": state.get("phase", "unknown"), "message": f"Agent 熔断器已打开，{remaining}s 后自动恢复"}
        return None

    async def _execute_turn(
        self,
        state: dict,
        *,
        entry_strategy: str,
        execute: Callable[[dict], Awaitable[dict]],
        collect: bool = True,
    ) -> dict:
        """Shared Collect -> Execute -> Refine lifecycle for every clinical turn."""
        from .graph import validate_state
        from .llm_utils import clear_rag_turn_cache, record_node_failure
        from .metrics import record_turn

        trace = LoopTrace(turn_id=f"turn-{uuid.uuid4().hex[:12]}", entry_strategy=entry_strategy)
        validated_state = validate_state(deepcopy(state), f"turn:{entry_strategy}")
        self._audit_hook.on_node_enter(entry_strategy, {"phase": validated_state.get("phase")})
        turn_start = time.monotonic()
        try:
            clear_rag_turn_cache()
            collect_ctx = await _loop_collect(validated_state) if collect else {"rag_hits": {}, "api_data": {}}
            result = await execute(validated_state)
            if not isinstance(result, dict):
                raise TypeError("clinical turn executor must return a state dictionary")
            result = _loop_refine(result, collect_ctx)
            result = _append_turn_journal(
                result,
                turn_id=trace.turn_id,
                entry_strategy=entry_strategy,
                input_state=validated_state,
                latency_ms=round((time.monotonic() - turn_start) * 1000),
                collect_ctx=collect_ctx,
            )
            self._circuit_breaker.reset()
            record_turn(success=True, latency_s=time.monotonic() - turn_start)
            trace.node_path = result.get("document_chain", [])
            trace.completed_at = datetime.now().isoformat()
            self._append_trace(trace)
            for node_name in result.get("document_chain", []):
                self._audit_hook.on_node_exit(node_name, {"phase": result.get("phase", "")})
            self._audit_hook.on_node_exit(entry_strategy, {"phase": result.get("phase")})
            return result
        except Exception as exc:
            self._circuit_breaker.record_failure()
            current_node = validated_state.get("current_step", entry_strategy)
            failure_count = record_node_failure(current_node)
            if failure_count >= 3:
                logger.warning("节点[%s] 连续%d次失败，建议人工介入", current_node, failure_count)
            self._audit_hook.on_error(entry_strategy, str(exc)[:200])
            record_turn(success=False, latency_s=time.monotonic() - turn_start)
            trace.errors.append({"error": str(exc), "phase": validated_state.get("phase")})
            trace.completed_at = datetime.now().isoformat()
            self._append_trace(trace)
            failed_result = {
                **validated_state,
                "agent_turn_status": "failed",
                "agent_turn_error": {"entry_strategy": entry_strategy, "message": str(exc)[:200]},
            }
            return _append_turn_journal(
                failed_result,
                turn_id=trace.turn_id,
                entry_strategy=entry_strategy,
                input_state=validated_state,
                latency_ms=round((time.monotonic() - turn_start) * 1000),
                error=str(exc),
            )

    def _append_trace(self, trace: LoopTrace) -> None:
        self._traces.append(trace)
        if len(self._traces) > 100:
            self._traces = self._traces[-100:]

    def _finalize_turn_result(self, result: dict) -> dict:
        import uuid

        if result.get("pending_review"):
            self._current_state = deepcopy(result)
            review_payload = result["pending_review"]
            return {"status": "pending_review", "review_id": review_payload.get("review_id", f"review-{uuid.uuid4().hex[:8]}"), "payload": review_payload}
        self._current_state = deepcopy(result)
        if "confirm_note" in result.get("document_chain", []):
            from .metrics import record_cleanup
            cleanup_patient_loop(str(getattr(self, "_patient_id", "default")), remove_lock=False)
            record_cleanup()
        return result


# 向后兼容别名（阶段M: routes 仍通过..agent.loop 导入 AgentLoop）
AgentLoop = PatientAgentLoop


# 患者级 AgentLoop 实例工厂(并发安全,避免全局单例互相覆盖)
_patient_loops: dict[str, PatientAgentLoop] = {}
_patient_loops_lock = threading.Lock()

# per-patient asyncio.Lock，保证同一患者串行 plan_turn
_patient_locks: dict[str, asyncio.Lock] = {}
_patient_locks_lock = threading.Lock()


def _get_patient_lock(patient_id: str) -> asyncio.Lock:
    """获取患者级 asyncio.Lock（线程安全）。"""
    if patient_id not in _patient_locks:
        with _patient_locks_lock:
            if patient_id not in _patient_locks:  # double-check
                _patient_locks[patient_id] = asyncio.Lock()
    return _patient_locks[patient_id]


def get_patient_lock(patient_id: str) -> asyncio.Lock:
    """获取患者级 asyncio.Lock（公开接口，供 review/command/monitoring 端点使用）。

    调用方应在 get_state → 修改 → plan_turn 整个链路外层持锁，
    确保同一患者状态读写的原子性。
    """
    return _get_patient_lock(patient_id)


def resolve_pending_state(
    loop: Any,
    fallback_state: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Resolve a compact pending-review response to its durable state snapshot."""
    snapshot_getter = getattr(loop, "pending_state_snapshot", None)
    snapshot = snapshot_getter() if callable(snapshot_getter) else None
    if isinstance(snapshot, dict) and snapshot.get("pending_review"):
        snapshot["interrupt_pending"] = True
        return snapshot

    pending_review = result.get("payload")
    if not isinstance(pending_review, dict):
        raise ValueError("pending_review result is missing its review payload")
    persisted_state = deepcopy(fallback_state)
    persisted_state["pending_review"] = deepcopy(pending_review)
    persisted_state["interrupt_pending"] = True
    return persisted_state


def get_patient_loop(patient_id: str) -> PatientAgentLoop:
    """为每个患者创建独立的 AgentLoop 实例（线程安全）。"""
    with _patient_loops_lock:
        if patient_id not in _patient_loops:
            loop = PatientAgentLoop()
            loop._patient_id = patient_id
            _patient_loops[patient_id] = loop
        return _patient_loops[patient_id]


def cleanup_patient_loop(patient_id: str, *, remove_lock: bool = True) -> None:
    """移除患者 AgentLoop；仅在未持有患者锁时移除锁对象。"""
    with _patient_loops_lock:
        _patient_loops.pop(patient_id, None)
    if remove_lock:
        with _patient_locks_lock:
            _patient_locks.pop(patient_id, None)


# ═══════════════════════════════════════════════════════════
# P0-5: Loop 三阶段辅助函数
# ═══════════════════════════════════════════════════════════

async def _loop_collect(state: dict) -> dict:
    """Phase 1 — Collect: 预检索 RAG + API 数据并缓存。

    返回 collect_ctx，供各节点和 Refine 阶段复用。
    """
    ctx = {"rag_hits": {}, "api_data": {}}

    try:
        # RAG routing is by node/caller, while a turn state stores phase and
        # event_type. Prefer the event mapping so a laboratory observation is
        # collected from L6 rather than the generic admission layer.
        phase = state.get("phase", "admission")
        event_type = state.get("event_type", "")
        rag_caller = {
            "admission_start": "admission",
            "vital_sign": "monitoring",
            "vitals": "monitoring",
            "lab": "lab_review",
            "medication": "medication_reconciliation",
            "discharge": "discharge",
        }.get(event_type, phase)
        disease_name = ""
        if isinstance(state.get("disease_template"), dict):
            disease_name = state["disease_template"].get("name", "")

        from .llm_utils import _rag_collect
        rag_q = f"{disease_name} {rag_caller}"
        hits = await _rag_collect(rag_q, rag_caller, top_k=3)
        if hits:
            ctx["rag_hits"][rag_caller] = hits
    except Exception:
        pass

    try:
        # API: OpenFDA/ICD-10 数据
        from .clinical_external import collect_api_data
        ctx["api_data"] = await collect_api_data(state)
    except Exception:
        pass

    return ctx


def _loop_refine(result: dict, collect_ctx: dict) -> dict:
    """Phase 3 — Refine: 融合 Collect 数据 + 去重 + 标记缺口。

    在节点输出基础上追加:
      - _collect_summary: RAG+API 收集到的证据概要
      - _knowledge_gaps: 知识库未覆盖的建议人工审核的领域
    """
    summary_parts = []

    # 汇总 Collect 阶段成果
    rag_hits = collect_ctx.get("rag_hits", {})
    if rag_hits:
        for phase, hits in rag_hits.items():
            if hits:
                summary_parts.append(f"[{phase}] RAG: {hits[0].get('topic','?')}")

    api_data = collect_ctx.get("api_data", {})
    # Keep the legacy summary formatter from treating unavailable evidence as retrieved data.
    api_data["fda_labels"] = [
        item for item in api_data.get("drug_evidence", [])
        if isinstance(item, dict) and item.get("status") == "available"
    ]
    if api_data.get("fda_labels"):
        summary_parts.append(f"FDA: {len(api_data['fda_labels'])} 药物标签")
    if api_data.get("icd10_codes"):
        summary_parts.append(f"ICD-10: {len(api_data['icd10_codes'])} 编码")

    if summary_parts:
        result["_collect_summary"] = " | ".join(summary_parts)

    # ── v0.3: DDx vs 用药冲突检测 ──
    conflicts = _detect_conflicts(result)
    if conflicts:
        existing_alerts = result.get("clinical_alerts", []) or []
        result["clinical_alerts"] = existing_alerts + conflicts
        result["_conflicts"] = conflicts

    # 知识缺口检测
    gaps = []
    if not rag_hits:
        gaps.append("RAG 无命中 — 罕见病或非标准表现")
    result["_knowledge_gaps"] = gaps

    return result


def _turn_input_fingerprint(state: dict) -> str:
    """Fingerprint workflow-relevant state without retaining clinical text."""
    pending = state.get("pending_review") if isinstance(state.get("pending_review"), dict) else {}
    payload = {
        "patient_id": str(state.get("patient_id") or ""),
        "state_version": int(state.get("state_version") or 0),
        "phase": str(state.get("phase") or ""),
        "event_type": str(state.get("event_type") or ""),
        "vital_count": len(state.get("vital_signs") or []),
        "lab_count": len(state.get("lab_results") or []),
        "medication_adjustment_count": len(state.get("medication_adjustments") or []),
        "pending_review_type": str(pending.get("type") or ""),
        "chain_tail": list(state.get("document_chain") or [])[-4:],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _append_turn_journal(
    result: dict,
    *,
    turn_id: str,
    entry_strategy: str,
    input_state: dict,
    latency_ms: int,
    collect_ctx: dict | None = None,
    error: str = "",
) -> dict:
    """Persist a bounded, PHI-minimized operational record for one Agent turn."""
    journal = [item for item in (result.get("agent_turn_journal") or []) if isinstance(item, dict)]
    rag_hits = (collect_ctx or {}).get("rag_hits") or {}
    entry = {
        "turn_id": turn_id,
        "occurred_at": datetime.now().isoformat(),
        "entry_strategy": entry_strategy,
        "status": "failed" if error else "completed",
        "latency_ms": max(0, int(latency_ms)),
        "input_fingerprint": _turn_input_fingerprint(input_state),
        "rag_hit_count": sum(len(items or []) for items in rag_hits.values()),
        "knowledge_gap": bool(result.get("_knowledge_gaps")),
        "node_path": [str(item) for item in (result.get("document_chain") or [])[-12:]],
    }
    if error:
        entry["error_code"] = type(error).__name__
        entry["error_message"] = str(error)[:160]
    journal.append(entry)
    return {
        **result,
        "agent_turn_status": entry["status"],
        "agent_turn_journal": journal[-30:],
    }


def _detect_conflicts(result: dict) -> list[str]:
    """检测 DDx 与用药调整之间的潜在矛盾。"""
    conflicts = []
    ddx = [d.get("diagnosis", "") for d in (result.get("ddx_list") or [])]
    meds = [m.get("drug_name", "") for m in (result.get("medication_adjustments") or [])]
    if not ddx or not meds:
        return conflicts

    # 规则: 抗凝药 + 出血性诊断
    bleeding_dx = any("出血" in d or "bleeding" in d.lower() for d in ddx)
    anticoag_meds = [m for m in meds if any(a in m for a in ("华法林","阿司匹林","氯吡格雷","肝素","利伐沙班"))]
    if bleeding_dx and anticoag_meds:
        conflicts.append(f"[冲突] 出血性诊断({','.join([d for d in ddx if '出血' in d or 'bleeding' in d.lower()])})与抗凝药({','.join(anticoag_meds)})并存，需医生确认")

    # 规则: 降糖药 + 低血糖风险
    hypo_risk = any("低血糖" in d or "hypoglycemia" in d.lower() for d in ddx)
    glucose_meds = [m for m in meds if any(g in m for g in ("胰岛素","二甲双胍","格列"))]
    if hypo_risk and glucose_meds:
        conflicts.append(f"[冲突] 低血糖风险与降糖药({','.join(glucose_meds)})并存，需调整方案")

    return conflicts
