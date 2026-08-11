"""Clinical-facing projection of persisted Agent and LLM workflow facts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_agent_flow(state: dict[str, Any], *, audience: str = "clinical") -> dict[str, Any]:
    if audience == "nurse":
        return _build_nursing_agent_flow(state)

    chain = set(state.get("document_chain") or [])
    citations = [item for item in state.get("clinical_evidence", []) or [] if isinstance(item, dict)]
    pending = active_pending_review(state)
    drafts = [item for item in state.get("assistant_action_drafts", []) or [] if isinstance(item, dict)]
    artifacts = _artifacts(state, citations, drafts)
    review_status = "pending" if pending or any(item.get("status") == "pending" for item in drafts) else "completed"
    stages = [
        _stage("collect", "临床数据采集", "rule", "completed" if chain else "idle", "汇集入院资料、体征、检验与护理记录", _collect_outputs(state), _collect_inputs(state)),
        _stage("evidence", "知识检索与证据", "rag", "completed" if citations or state.get("_collect_summary") else "idle", "检索已配置知识库并保留可追溯引用", [f"{len(citations)} 条临床引用"] if citations else [], _evidence_inputs(state)),
        _stage("reason", "规则与 LLM 推理", "llm", "completed" if artifacts else "idle", "生成诊断、查房、检验解读、交班和草案；不直接执行临床动作", [item["title"] for item in artifacts], _reason_inputs(state, citations)),
        _stage("review", "医生审核卡点", "human", review_status, _review_description(pending, drafts), _review_outputs(pending, drafts), _review_inputs(pending, drafts)),
        _stage("commit", "正式记录与协同", "record", "completed" if _has_committed_records(state) else "idle", "仅在人工确认后写入医嘱、检查、MDT、随访或宣教计划", _committed_outputs(state), _commit_inputs(state)),
    ]
    return {
        "flow_status": "waiting_review" if review_status == "pending" else "ready",
        "state_version": _safe_int(state.get("state_version")),
        "pending_review": _pending_review_projection(pending),
        "stages": stages,
        "generated_artifacts": artifacts,
        "citations": [_citation(item) for item in citations[:12]],
        "turn_journal": _turn_journal(state),
        "latest_execution": _latest_execution(state),
        "safety_boundary": "LLM 仅生成辅助内容和待审核草案；临床记录写入需经过既有权限、版本校验与人工确认。",
    }


def active_pending_review(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return only a review that can still block the persisted clinical state."""
    pending = state.get("pending_review") if isinstance(state.get("pending_review"), dict) else None
    if not pending:
        return None

    review_type = str(pending.get("type") or "")
    completed = {
        "doctor_confirm": str(state.get("doctor_confirm_status") or "") == "approved",
        "med_confirm": str(state.get("med_confirm_status") or "") == "approved",
        "discharge_sign": str(state.get("discharge_sign_status") or "") in {"signed", "approved"},
    }
    if completed.get(review_type):
        return None

    # A completed discharge signature supersedes stale admission or medication
    # review metadata left by an interrupted earlier loop.
    if review_type in {"doctor_confirm", "med_confirm"} and completed["discharge_sign"]:
        return None
    return pending


def _build_nursing_agent_flow(state: dict[str, Any]) -> dict[str, Any]:
    """Project the same persisted workflow facts in a nurse-operational vocabulary."""
    citations = [item for item in state.get("clinical_evidence", []) or [] if isinstance(item, dict)]
    nursing_records = [item for item in state.get("nursing_records", []) or [] if isinstance(item, dict)]
    agent_records = [item for item in nursing_records if item.get("source") == "agent"]
    completions = [item for item in state.get("nursing_task_completions", []) or [] if isinstance(item, dict)]
    latest_agent_record = agent_records[-1] if agent_records else None
    waiting_confirmation = bool(latest_agent_record) and not _nursing_suggestion_confirmed(latest_agent_record, completions)
    artifacts = _nursing_artifacts(state, citations, agent_records, completions, waiting_confirmation)
    review_status = "pending" if waiting_confirmation else "completed"
    stages = [
        _stage(
            "collect", "床旁护理数据采集", "rule", "completed" if _nursing_has_inputs(state) else "idle",
            "汇集生命体征、护理记录、给药核对和风险提示", _nursing_collect_outputs(state), _nursing_collect_inputs(state),
        ),
        _stage(
            "evidence", "护理规范与证据检索", "rag", "completed" if citations else "idle",
            "按当前患者问题检索护理规范，并保留可追溯引用", [f"{len(citations)} 条护理或临床引用"] if citations else [], ["当前患者护理事实", "护理规范知识库"] if _nursing_has_inputs(state) else ["当前患者病种与护理问题"],
        ),
        _stage(
            "reason", "风险识别与护理建议", "llm", "completed" if agent_records else "idle",
            "规则优先，必要时由 LLM 补充护理观察和措施建议", _nursing_suggestion_outputs(latest_agent_record), ["生命体征与风险提示", f"{len(citations)} 条证据引用"] if citations else ["生命体征与风险提示"],
        ),
        _stage(
            "review", "护士复核与任务执行", "human", review_status,
            "智能建议仅供复核；护士确认后选择记录护理事实或完成对应任务", _nursing_review_outputs(latest_agent_record, completions, waiting_confirmation), ["智能护理建议", "护理任务与版本校验"],
        ),
        _stage(
            "commit", "护理记录与交接审计", "record", "completed" if nursing_records or completions else "idle",
            "已确认的护理记录、任务完成和交接信息写入患者正式病程", _nursing_commit_outputs(nursing_records, completions), ["护士复核结果", "审计与版本校验"],
        ),
    ]
    return {
        "flow_status": "waiting_review" if waiting_confirmation else "ready",
        "state_version": _safe_int(state.get("state_version")),
        "pending_review": None,
        "stages": stages,
        "generated_artifacts": artifacts,
        "citations": [_citation(item) for item in citations[:12]],
        "turn_journal": _turn_journal(state),
        "latest_execution": _latest_execution(state),
        "safety_boundary": "护理助手仅生成风险提示和护理建议；生命体征、护理记录及任务完成均须由护士复核并通过既有权限、版本校验和审计链路写入。",
    }


def _nursing_has_inputs(state: dict[str, Any]) -> bool:
    return any(state.get(key) for key in ("vital_signs", "nursing_records", "clinical_alerts", "medication_orders"))


def _nursing_collect_outputs(state: dict[str, Any]) -> list[str]:
    values: list[str] = []
    if state.get("vital_signs"):
        values.append(f"{len(state['vital_signs'])} 次生命体征")
    if state.get("nursing_records"):
        values.append(f"{len(state['nursing_records'])} 条护理记录")
    if state.get("clinical_alerts"):
        values.append(f"{len(state['clinical_alerts'])} 条风险提示")
    if state.get("medication_orders"):
        values.append(f"{len(state['medication_orders'])} 项用药核对")
    return values


def _nursing_suggestion_outputs(record: dict[str, Any] | None) -> list[str]:
    if not record:
        return []
    values = [str(record.get("nursing_actions") or "护理措施建议")[:120]]
    values.extend(str(item)[:120] for item in (record.get("alerts") or []) if str(item).strip())
    return values[:4]


def _nursing_suggestion_confirmed(record: dict[str, Any], completions: list[dict[str, Any]]) -> bool:
    suggestion_time = str(record.get("timestamp") or "")
    if not suggestion_time:
        return bool(completions)
    return any(str(item.get("completed_at") or "") >= suggestion_time for item in completions)


def _nursing_review_outputs(record: dict[str, Any] | None, completions: list[dict[str, Any]], waiting: bool) -> list[str]:
    if waiting and record:
        return ["待复核：智能护理建议", *[str(item)[:100] for item in (record.get("alerts") or [])]][:4]
    if completions:
        return [f"已审计完成 {len(completions)} 项护理任务"]
    return []


def _nursing_commit_outputs(records: list[dict[str, Any]], completions: list[dict[str, Any]]) -> list[str]:
    values = []
    if records:
        values.append(f"护理记录 {len(records)} 条")
    if completions:
        values.append(f"已完成任务 {len(completions)} 项")
    return values


def _nursing_artifacts(
    state: dict[str, Any], citations: list[dict[str, Any]], agent_records: list[dict[str, Any]],
    completions: list[dict[str, Any]], waiting_confirmation: bool,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if agent_records:
        records.append(_artifact(
            "nursing-suggestion", "智能护理建议", "llm",
            "待护士复核" if waiting_confirmation else "已复核",
            len(agent_records[-1].get("citations") or citations), "不会自动写入护理记录或关闭任务",
        ))
    if state.get("shift_summaries") or state.get("shift_summary_history"):
        records.append(_artifact("handover", "智能交班摘要", "llm", "已生成", len(citations), "供交接核对，不替代人工交班"))
    if state.get("nursing_records"):
        records.append(_artifact("nursing-records", "护理记录", "rule", "已记录", 0, "人工录入内容作为临床事实保存"))
    if completions:
        records.append(_artifact("nursing-tasks", "护理任务审计", "rule", "已完成", 0, "保留执行人、时间和任务说明"))
    return records


def _stage(identifier: str, title: str, mode: str, status: str, description: str, outputs: list[str], inputs: list[str] | None = None) -> dict[str, Any]:
    return {"id": identifier, "title": title, "mode": mode, "status": status, "description": description, "inputs": (inputs or [])[:6], "outputs": outputs[:4]}


def _turn_journal(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose only operational turn facts needed for clinical transparency."""
    records = _ordered_turns(state)
    projected = []
    for item in records[-6:][::-1]:
        projected.append({
            "turn_id": str(item.get("turn_id") or ""),
            "occurred_at": str(item.get("occurred_at") or ""),
            "entry_strategy": str(item.get("entry_strategy") or ""),
            "status": "failed" if item.get("status") == "failed" else "completed",
            "latency_ms": _safe_int(item.get("latency_ms")),
            "rag_hit_count": _safe_int(item.get("rag_hit_count")),
            "knowledge_gap": bool(item.get("knowledge_gap")),
            "node_count": len(item.get("node_path") or []),
            "error_message": str(item.get("error_message") or "")[:160],
        })
    return projected


def _latest_execution(state: dict[str, Any]) -> dict[str, Any] | None:
    records = _ordered_turns(state)
    if not records:
        return None
    item = records[-1]
    return {
        "turn_id": str(item.get("turn_id") or ""),
        "occurred_at": str(item.get("occurred_at") or ""),
        "entry_strategy": str(item.get("entry_strategy") or ""),
        "status": "failed" if item.get("status") == "failed" else "completed",
        "latency_ms": _safe_int(item.get("latency_ms")),
        "rag_hit_count": _safe_int(item.get("rag_hit_count")),
        "node_path": [str(node) for node in (item.get("node_path") or [])[-12:]],
        "error_message": str(item.get("error_message") or "")[:160],
    }


def _ordered_turns(state: dict[str, Any]) -> list[dict[str, Any]]:
    records = [item for item in (state.get("agent_turn_journal") or []) if isinstance(item, dict)]
    return [item for _, item in sorted(enumerate(records), key=lambda pair: (_turn_time(pair[1].get("occurred_at")), pair[0]))]


def _turn_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _collect_outputs(state: dict[str, Any]) -> list[str]:
    values = []
    if state.get("history_data") or "history_note" in (state.get("document_chain") or []): values.append("病史与主诉")
    if state.get("vital_signs"): values.append(f"{len(state['vital_signs'])} 次生命体征")
    if state.get("lab_results"): values.append(f"{len(state['lab_results'])} 项检验结果")
    if state.get("nursing_records"): values.append(f"{len(state['nursing_records'])} 条护理记录")
    return values


def _collect_inputs(state: dict[str, Any]) -> list[str]:
    values = ["患者入院资料"]
    if state.get("vital_signs"): values.append("生命体征")
    if state.get("lab_results"): values.append("检验结果")
    if state.get("nursing_records"): values.append("护理记录")
    return values


def _evidence_inputs(state: dict[str, Any]) -> list[str]:
    return ["当前病种模板", "患者临床问题", "已配置知识库"]


def _reason_inputs(state: dict[str, Any], citations: list[dict[str, Any]]) -> list[str]:
    values = ["结构化临床事实", f"{len(citations)} 条证据引用"]
    if state.get("pending_review"): values.append("既有审核状态")
    return values


def _review_inputs(pending: dict[str, Any] | None, drafts: list[dict[str, Any]]) -> list[str]:
    values = ["规则与 LLM 生成内容"]
    if pending: values.append("待审核临床 payload")
    if any(item.get("status") == "pending" for item in drafts): values.append("操作草稿")
    return values


def _commit_inputs(state: dict[str, Any]) -> list[str]:
    return ["人工确认结果", "权限与状态版本校验"]


def _nursing_collect_inputs(state: dict[str, Any]) -> list[str]:
    values = ["床旁患者状态"]
    if state.get("vital_signs"): values.append("生命体征")
    if state.get("nursing_records"): values.append("护理记录")
    if state.get("clinical_alerts"): values.append("风险提示")
    return values


def _artifacts(state: dict[str, Any], citations: list[dict[str, Any]], drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_count = len(citations)
    records: list[dict[str, Any]] = []
    if state.get("ddx_list"):
        records.append(_artifact("ddx", "鉴别诊断", "llm", "已生成", evidence_count, "需医生确认诊断与处置方向"))
    if state.get("latest_round"):
        records.append(_artifact("round", "SOAP 查房摘要", "llm", "已生成", evidence_count, "由医生结合原始数据确认"))
    if state.get("lab_findings"):
        records.append(_artifact("lab", "检验变化解读", "llm", "已生成", evidence_count, "不替代检验报告与临床判断"))
    if state.get("nursing_records"):
        source = "llm" if any(isinstance(item, dict) and item.get("source") == "agent" for item in state["nursing_records"][-3:]) else "rule"
        records.append(_artifact("nursing", "护理观察与措施", source, "已生成", evidence_count, "由护理人员记录或复核"))
    if state.get("shift_summaries") or state.get("shift_summary_history"):
        records.append(_artifact("handover", "交班摘要", "llm", "已生成", evidence_count, "供交班核对，不替代交班签署"))
    if state.get("handoff_items"):
        records.append(_artifact("discharge", "出院交接事项", "rule", "已生成", evidence_count, "需完成签字、签收与患者回授"))
    for draft in drafts[:5]:
        status = {"pending": "待医生审核", "approved": "已批准", "rejected": "已驳回"}.get(str(draft.get("status")), "草稿")
        records.append(_artifact(f"draft-{draft.get('id', '')}", _draft_title(draft), "llm", status, len(draft.get("citations") or []), "草稿批准前不会生成正式临床记录"))
    return records[:12]


def _artifact(identifier: str, title: str, generator: str, status: str, citation_count: int, guardrail: str) -> dict[str, Any]:
    return {"id": identifier, "title": title, "generator": generator, "status": status, "citation_count": citation_count, "guardrail": guardrail}


def _draft_title(draft: dict[str, Any]) -> str:
    return {"medication_order": "用药医嘱草稿", "investigation_order": "检查医嘱草稿", "follow_up_task": "随访任务草稿", "mdt_request": "MDT 会诊草稿", "education_plan": "患者宣教计划"}.get(str(draft.get("draft_type")), "临床操作草稿")


def _review_description(pending: dict[str, Any] | None, drafts: list[dict[str, Any]]) -> str:
    if pending:
        return f"当前等待医生审核：{_review_label(str(pending.get('type', '')))}"
    if any(item.get("status") == "pending" for item in drafts):
        return "存在助手生成的待审核操作草稿"
    return "当前没有阻塞性的待审核 Agent 输出"


def _review_outputs(pending: dict[str, Any] | None, drafts: list[dict[str, Any]]) -> list[str]:
    outputs = [f"待审核：{_review_label(str(pending.get('type', '')))}" ] if pending else []
    outputs.extend(f"草稿：{_draft_title(item)}" for item in drafts if item.get("status") == "pending")
    return outputs


def _pending_review_projection(pending: dict[str, Any] | None) -> dict[str, str] | None:
    if not pending:
        return None
    review_type = str(pending.get("type") or "")
    return {
        "review_type": review_type,
        "review_id": str(pending.get("review_id") or ""),
        "label": _review_label(review_type),
    }


def _review_label(review_type: str) -> str:
    return {
        "doctor_confirm": "入院诊断审核",
        "med_confirm": "用药调整审核",
        "discharge_sign": "出院签字审核",
    }.get(review_type, "临床节点审核")


def _has_committed_records(state: dict[str, Any]) -> bool:
    return any(state.get(key) for key in ("medication_orders", "investigation_orders", "mdt_requests", "follow_up_tasks", "education_plans"))


def _committed_outputs(state: dict[str, Any]) -> list[str]:
    labels = {"medication_orders": "正式用药医嘱", "investigation_orders": "正式检查医嘱", "mdt_requests": "MDT 请求", "follow_up_tasks": "随访任务", "education_plans": "待执行宣教计划"}
    return [f"{labels[key]} {len(state.get(key) or [])} 项" for key in labels if state.get(key)]


def _citation(item: dict[str, Any]) -> dict[str, str]:
    return {"title": str(item.get("title") or item.get("topic") or item.get("source") or "临床证据"), "source": str(item.get("source") or item.get("layer") or "RAG"), "excerpt": str(item.get("excerpt") or item.get("text") or item.get("content") or "")[:240]}
