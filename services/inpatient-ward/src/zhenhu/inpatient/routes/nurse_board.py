"""Nursing task board, completion audit, and quality metrics.

护士视角：即将到来的护理任务、待测生命体征、待发药提醒。
#2: 科室级护理任务差异化。
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Query, Request
from sqlalchemy import select

from ..schemas import UnifiedResponse
from .route_schemas import NursingTaskCompletionRequest
from ..services.clinical_alerts import alert_message, is_complication_alert

router = APIRouter(prefix="/nurse", tags=["nurse"])


def _complication_alert_messages(alerts: list) -> list[str]:
    return [alert_message(alert) for alert in alerts if is_complication_alert(alert)]

# P0-2 跨层依赖修复: _DEPT_CHECKLIST 从 agent/constants.py 导入
from ..agent.constants import DEPT_CHECKLIST as _DEPT_CHECKLIST, get_dept_checklist


def _calc_vs_trend(vs: list) -> str:
    """计算体征趋势: 稳定/恶化/改善。"""
    if len(vs) < 2:
        return "数据不足"
    recent = vs[-3:]
    first, last = recent[0], recent[-1]
    try:
        spo2_change = float(last.get("spo2", 0) or 0) - float(first.get("spo2", 0) or 0)
        hr_change = float(last.get("heart_rate", 0) or 0) - float(first.get("heart_rate", 0) or 0)
        if spo2_change < -2 or hr_change > 15:
            return "⚠ 恶化"
        if spo2_change > 2 and hr_change < -10:
            return "↑ 改善"
        return "→ 稳定"
    except (ValueError, TypeError):
        return "→ 稳定"


class NursingTaskNotFoundError(Exception):
    """Raised when a client tries to complete a task that is no longer pending."""


class NursingTaskAlreadyCompletedError(Exception):
    """Raised when a task was completed without an HTTP idempotency replay key."""


_TASK_TYPES = ("vital_signs", "nursing_action", "medication", "checklist")


def _stable_task_key(task_type: str, anchor: object) -> str:
    payload = json.dumps(anchor, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"{task_type}:{digest}"


def _checklist_rule_id(department: str, title: str) -> str:
    return _stable_task_key("checklist", {"department": department, "title": title})


def _checklist_task_types(title: str) -> tuple[str, ...]:
    """Map a protocol item to evidence categories without claiming clinical completion."""
    value = title.lower()
    if any(token in value for token in ("药", "注射", "输液", "吸入", "抗凝")):
        return ("medication",)
    if any(token in value for token in ("监测", "观察", "记录", "复查", "评估", "体温", "体重", "尿量", "血糖", "疼痛", "瞳孔", "nihss")):
        return ("vital_signs",)
    return ("nursing_action",)


def _checklist_window() -> str:
    return datetime.now(timezone.utc).date().isoformat()


async def _checklist_confirmations(department: str, window_date: str) -> dict[str, dict[str, Any]]:
    """Read the latest audited confirmation for each protocol item in the current window."""
    from ..main import async_session_factory
    from ..models import AuditLog

    async with async_session_factory() as session:
        entries = list((await session.scalars(
            select(AuditLog)
            .where(AuditLog.action_type == "nursing_checklist_confirmed")
            .order_by(AuditLog.created_at.desc())
            .limit(500)
        )).all())
    results: dict[str, dict[str, Any]] = {}
    for entry in entries:
        detail = entry.action_detail if isinstance(entry.action_detail, dict) else {}
        rule_id = str(detail.get("rule_id") or "")
        if not rule_id or detail.get("department") != department or detail.get("window_date") != window_date or rule_id in results:
            continue
        results[rule_id] = {
            "audit_id": entry.id,
            "actor_id": entry.actor_id or detail.get("actor_id"),
            "actor_name": detail.get("actor_name"),
            "note": detail.get("note", ""),
            "confirmed_at": entry.created_at.isoformat() if entry.created_at else "",
        }
    return results


def _task_completions(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (state.get("nursing_task_completions") or []) if isinstance(item, dict)]


def _derive_task_items(state: dict[str, Any], *, now: float) -> list[dict[str, Any]]:
    """Derive actionable tasks from current clinical facts, then remove completed instances."""
    vital_signs = state.get("vital_signs") or []
    latest_vital = vital_signs[-1] if vital_signs and isinstance(vital_signs[-1], dict) else {}
    template = state.get("disease_template") or {}
    alerts = state.get("clinical_alerts") or []
    completed_keys = {str(item.get("task_key")) for item in _task_completions(state)}
    items: list[dict[str, Any]] = []

    last_vital_time = str(latest_vital.get("timestamp") or "")
    monitoring_hours = template.get("monitoring_interval_hours") or 4
    vital_overdue = True
    if monitoring_hours and last_vital_time:
        try:
            last_dt = datetime.fromisoformat(last_vital_time.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            vital_overdue = (now - last_dt.timestamp()) / 3600 > float(monitoring_hours)
        except (TypeError, ValueError):
            vital_overdue = True
    if vital_overdue:
        items.append({
            "task_key": _stable_task_key("vital_signs", {"last_vital_time": last_vital_time or "initial", "interval": monitoring_hours}),
            "task_type": "vital_signs",
            "title": "测量并记录生命体征",
            "description": "患者体征已到复测时间，请完成测量并录入护理记录。",
            "priority": "high" if alerts else "normal",
        })

    # Agent-generated nursing guidance is a proposed action. Manual records are
    # already completed facts and must never reappear as pending work.
    agent_records = [
        record for record in (state.get("nursing_records") or [])
        if isinstance(record, dict) and record.get("source") == "agent" and record.get("nursing_actions")
    ]
    if agent_records:
        latest_record = agent_records[-1]
        action_text = str(latest_record.get("nursing_actions") or "").strip()
        items.append({
            "task_key": _stable_task_key("nursing_action", {
                "round": latest_record.get("round_number"),
                "timestamp": latest_record.get("timestamp"),
                "actions": action_text,
            }),
            "task_type": "nursing_action",
            "title": "执行护理措施",
            "description": action_text[:300],
            "priority": "high" if latest_record.get("alerts") else "normal",
        })

    # Active medication orders represent a one-time nursing verification task;
    # recurring MAR scheduling needs a separate prescription schedule contract.
    for order in state.get("medication_orders") or []:
        if not isinstance(order, dict) or order.get("status") != "active":
            continue
        medication = str(order.get("medication") or "未命名药物")
        items.append({
            "task_key": _stable_task_key("medication", order.get("id") or order),
            "task_type": "medication",
            "title": f"核对用药医嘱：{medication}",
            "description": " ".join(str(order.get(key) or "") for key in ("dose", "frequency", "route")).strip(),
            "priority": "normal",
        })

    return [item for item in items if item["task_key"] not in completed_keys]


def _patient_task_summary(patient_id: str, state: dict[str, Any], *, now: float) -> dict[str, Any]:
    patient_data = state.get("patient_data") or {}
    template = state.get("disease_template") or {}
    vital_signs = state.get("vital_signs") or []
    latest_vital = vital_signs[-1] if vital_signs and isinstance(vital_signs[-1], dict) else {}
    task_items = _derive_task_items(state, now=now)
    pending_nursing = [item["description"] for item in task_items if item["task_type"] == "nursing_action"]
    pending_medications = [item["title"] for item in task_items if item["task_type"] == "medication"]
    return {
        "patient_id": patient_id,
        "state_version": state.get("state_version", 0),
        "name": patient_data.get("name", patient_id[:10]),
        "disease": template.get("name") or template.get("disease_id", "unknown"),
        "department": template.get("department") or (state.get("patient_access") or {}).get("department") or "未知",
        "phase": state.get("phase"),
        "risk_level": state.get("risk_level"),
        "round_count": state.get("round_count", 0),
        "vital_signs_due": any(item["task_type"] == "vital_signs" for item in task_items),
        "last_vs_time": latest_vital.get("timestamp", ""),
        "latest_vital_values": {
            "systolic": latest_vital.get("systolic_mmhg"),
            "diastolic": latest_vital.get("diastolic_mmhg"),
            "spo2": latest_vital.get("spo2"),
            "temperature": latest_vital.get("temperature"),
        },
        "pending_nursing_actions": pending_nursing,
        "pending_medications": pending_medications,
        "department_checklist": get_dept_checklist(template.get("department", "")),
        "alert_count": len(state.get("clinical_alerts") or []),
        "open_task_count": len(task_items),
        "task_items": task_items,
        "bedside_flags": {
            "vs_trend": _calc_vs_trend(vital_signs),
            "complication_alerts": _complication_alert_messages(state.get("clinical_alerts") or [])[-3:],
            "pain_score": latest_vital.get("pain_score"),
            "pain_location": patient_data.get("pain_location", ""),
            "bmi": state.get("bmi"),
            "fall_risk": "Morse≥45" if state.get("risk_level") == "high" else "常规",
        },
    }


def _require_nurse(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user_info", {}) or {}
    if "nurse" not in set(user.get("roles") or []):
        raise HTTPException(status_code=403, detail="该操作仅限护士角色")
    return user


def _require_nursing_quality_view(request: Request) -> dict[str, Any]:
    """Allow nurses and departmental managers to read, but never mutate, quality data."""
    user = getattr(request.state, "user_info", {}) or {}
    if "nurse" in set(user.get("roles") or []):
        return user
    from ..services.management_access import management_capabilities

    if management_capabilities(request)["is_manager"]:
        return user
    raise HTTPException(status_code=403, detail="护理质控数据仅限护士、科主任或护士长查看")


@router.get("/department-checklist")
async def get_department_checklist(request: Request, department: str | None = Query(None)):
    """返回科室级护理检查清单。

    - 护士无参数: 返回当前科室清单
    - 管理视图无参数: 保持返回可管理范围内的清单
    - ?department=骨科: 返回指定科室清单
    """
    user = getattr(request.state, "user_info", {}) or {}
    requested_department = department or user.get("department")
    if requested_department:
        checklist = get_dept_checklist(str(requested_department))
        if not checklist:
            return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"无 {requested_department} 的护理清单"})
        return UnifiedResponse(data={
            "department": requested_department,
            "checklist": checklist,
        })

    return UnifiedResponse(data={
        "departments": {k: v for k, v in _DEPT_CHECKLIST.items()},
    })


@router.get("/checklist-execution")
async def get_checklist_execution(request: Request):
    """Project each department protocol item onto real patient-task evidence and audit confirmations."""
    user = _require_nursing_quality_view(request)
    department = str(user.get("department") or "").strip()
    if not department:
        return UnifiedResponse(error={"code": "DEPARTMENT_REQUIRED", "message": "当前账号未绑定科室，无法加载制度执行"})
    checklist = get_dept_checklist(department)
    if not checklist:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"无 {department} 的护理清单"})

    from .state_store import _get_ttl, _store
    from ..services.patient_access import iter_accessible_patient_states

    now = time.time()
    summaries: list[dict[str, Any]] = []
    for patient_id, _, state in iter_accessible_patient_states(
        list(_store.items()), user, now=now, ttl=_get_ttl()
    ):
        if state.get("phase") in ("discharge", "confirm", "review"):
            continue
        summary = _patient_task_summary(patient_id, state, now=now)
        if summary.get("department") == department:
            summaries.append(summary)

    window_date = _checklist_window()
    confirmations = await _checklist_confirmations(department, window_date)
    rules: list[dict[str, Any]] = []
    for title in checklist:
        rule_id = _checklist_rule_id(department, title)
        task_types = _checklist_task_types(title)
        patients = []
        task_count = 0
        overdue_count = 0
        for summary in summaries:
            matched_tasks = [
                task for task in summary.get("task_items", [])
                if task.get("task_type") in task_types
            ]
            if not matched_tasks:
                continue
            task_count += len(matched_tasks)
            if any(task.get("task_type") == "vital_signs" for task in matched_tasks):
                overdue_count += 1
            patients.append({**summary, "matched_tasks": matched_tasks})
        confirmation = confirmations.get(rule_id)
        rules.append({
            "rule_id": rule_id,
            "title": title,
            "task_types": list(task_types),
            "status": "action_required" if task_count else "confirmed" if confirmation else "not_triggered",
            "patient_count": len(patients),
            "task_count": task_count,
            "overdue_count": overdue_count,
            "patients": patients,
            "confirmation": confirmation,
        })
    return UnifiedResponse(data={
        "department": department,
        "window_date": window_date,
        "rules": rules,
        "summary": {
            "total": len(rules),
            "confirmed": sum(1 for rule in rules if rule["status"] == "confirmed"),
            "action_required": sum(1 for rule in rules if rule["status"] == "action_required"),
            "not_triggered": sum(1 for rule in rules if rule["status"] == "not_triggered"),
            "overdue": sum(rule["overdue_count"] for rule in rules),
        },
    })


@router.post("/checklist-rules/{rule_id}/confirm")
async def confirm_checklist_rule(rule_id: str, request: Request, body: dict[str, str] | None = Body(default=None)):
    """Create an auditable nurse confirmation for a protocol item without altering clinical facts."""
    user = _require_nurse(request)
    department = str(user.get("department") or "").strip()
    checklist = get_dept_checklist(department)
    matched_title = next((title for title in checklist if _checklist_rule_id(department, title) == rule_id), None)
    if not matched_title:
        raise HTTPException(status_code=404, detail="制度项不存在或不属于当前科室")
    window_date = _checklist_window()
    confirmations = await _checklist_confirmations(department, window_date)
    existing = confirmations.get(rule_id)
    if existing:
        return UnifiedResponse(data={"rule_id": rule_id, "status": "confirmed", "confirmation": existing, "idempotent": True})

    from ..agent.audit import write_management_audit_event

    note = str((body or {}).get("note") or "").strip()[:500]
    audit_id = await write_management_audit_event(
        action_type="nursing_checklist_confirmed",
        detail={
            "department": department,
            "rule_id": rule_id,
            "rule_title": matched_title,
            "window_date": window_date,
            "note": note,
            "actor_id": user.get("actor_id"),
            "actor_name": user.get("name"),
        },
        request=request,
    )
    confirmation = {
        "audit_id": audit_id,
        "actor_id": user.get("actor_id"),
        "actor_name": user.get("name"),
        "note": note,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    return UnifiedResponse(data={"rule_id": rule_id, "status": "confirmed", "confirmation": confirmation, "idempotent": False})


@router.get("/tasks")
async def get_nurse_tasks(request: Request, department: str | None = Query(None)):
    """返回所有患者待执行的护理任务。可选 ?department=骨科 按科室筛选。

    包括：下次测生命体征时间、待执行护理措施、待给药提醒、科室级检查清单。
    按紧急程度排序。
    """
    from .state_store import _store, _get_ttl

    ttl = _get_ttl()
    now = time.time()
    tasks = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        if state.get("phase") in ("discharge", "confirm", "review"):
            continue  # 已出院/已确认患者不计

        tpl = state.get("disease_template", {}) or {}
        dept = tpl.get("department", "未知")

        # 科室筛选
        if department and dept != department:
            continue

        tasks.append(_patient_task_summary(pid, state, now=now))

    # 排序：有问题患者优先（告警数 > 体征缺测 > 姓名）
    tasks.sort(key=lambda t: (-t["alert_count"], not t["vital_signs_due"], t["name"]))

    return UnifiedResponse(data={
        "total": len(tasks),
        "open_task_count": sum(task["open_task_count"] for task in tasks),
        "vital_signs_overdue": sum(1 for t in tasks if t["vital_signs_due"]),
        "with_alerts": sum(1 for t in tasks if t["alert_count"] > 0),
        "tasks": tasks,
    })


@router.post("/tasks/{patient_id}/complete")
async def complete_nursing_task(
    patient_id: str,
    body: NursingTaskCompletionRequest,
    request: Request,
):
    """Persist a nurse task completion through the clinical transaction boundary."""
    user = _require_nurse(request)
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    try:
        require_patient_access(patient_id, user)
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc

    def operation(state: dict[str, Any]) -> dict[str, Any]:
        existing = next(
            (item for item in _task_completions(state) if item.get("task_key") == body.task_key),
            None,
        )
        if existing is not None:
            raise NursingTaskAlreadyCompletedError(body.task_key)
        task = next(
            (
                item for item in _derive_task_items(state, now=time.time())
                if item["task_key"] == body.task_key and item["task_type"] == body.task_type
            ),
            None,
        )
        if task is None:
            raise NursingTaskNotFoundError(body.task_key)
        completion = {
            "id": str(uuid4()),
            "task_key": task["task_key"],
            "task_type": task["task_type"],
            "title": task["title"],
            "note": body.note.strip(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "actor_id": user.get("actor_id"),
            "actor_name": user.get("name"),
        }
        state.setdefault("nursing_task_completions", []).append(completion)
        return completion

    try:
        completion = await patient_state_service.mutate_clinical(
            request,
            patient_id,
            operation,
            action_type="nursing_task_completed",
            detail=lambda item: {
                "completion_id": item["id"],
                "task_key": item["task_key"],
                "task_type": item["task_type"],
            },
            idempotency_scope=f"nursing-task:{body.task_key}",
            expected_version=body.expected_version,
        )
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到患者状态") from exc
    except NursingTaskAlreadyCompletedError as exc:
        raise HTTPException(status_code=409, detail="护理任务已经完成") from exc
    except NursingTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="护理任务已失效或不存在") from exc

    state = await patient_state_service.read(patient_id)
    return UnifiedResponse(data={"completion": completion, "state_version": state.get("state_version", 0)})


@router.get("/kpi")
async def get_nursing_kpi(request: Request):
    """Return a department-scoped rolling quality snapshot for nurse managers."""
    _require_nursing_quality_view(request)
    from .state_store import _get_ttl, _store
    from ..services.patient_access import iter_accessible_patient_states

    now = time.time()
    window_start = datetime.now(timezone.utc) - timedelta(hours=24)
    user = getattr(request.state, "user_info", {}) or {}
    type_stats = {task_type: {"open": 0, "completed": 0} for task_type in _TASK_TYPES}
    recent_completions: list[dict[str, Any]] = []
    departments: set[str] = set()
    patient_count = 0

    for patient_id, _, state in iter_accessible_patient_states(
        list(_store.items()), user, now=now, ttl=_get_ttl()
    ):
        summary = _patient_task_summary(patient_id, state, now=now)
        departments.add(str(summary["department"]))
        if state.get("phase") not in ("discharge", "confirm", "review"):
            patient_count += 1
            for task in summary["task_items"]:
                type_stats[task["task_type"]]["open"] += 1
        for completion in _task_completions(state):
            try:
                completed_at = datetime.fromisoformat(str(completion.get("completed_at") or "").replace("Z", "+00:00"))
                if completed_at.tzinfo is None:
                    completed_at = completed_at.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if completed_at < window_start:
                continue
            task_type = str(completion.get("task_type") or "")
            if task_type in type_stats:
                type_stats[task_type]["completed"] += 1
            recent_completions.append({
                **completion,
                "patient_id": patient_id,
                "patient_name": summary["name"],
                "department": summary["department"],
            })

    open_tasks = sum(item["open"] for item in type_stats.values())
    completed = sum(item["completed"] for item in type_stats.values())
    denominator = open_tasks + completed
    recent_completions.sort(key=lambda item: str(item.get("completed_at") or ""), reverse=True)
    return UnifiedResponse(data={
        "scope": {"departments": sorted(departments), "patient_count": patient_count},
        "window_hours": 24,
        "window_started_at": window_start.isoformat(),
        "open_tasks": open_tasks,
        "completed_tasks": completed,
        "overdue_tasks": type_stats["vital_signs"]["open"],
        "completion_rate": round(completed / denominator, 4) if denominator else 0.0,
        "by_type": type_stats,
        "recent_completions": recent_completions[:10],
    })


@router.get("/ai-priority")
async def get_nurse_ai_priority(request: Request, enhance_ai: bool = Query(False)):
    """AI 护理优先级排序 — 护士先看谁？

    聚合体征超时 + 告警 + 并发症 → LLM 产出优先顺序建议。
    """
    from .state_store import _store, _get_ttl
    import time
    ttl = _get_ttl()
    now = time.time()
    patients = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        if state.get("phase") in ("discharge", "confirm", "review"):
            continue
        vs = state.get("vital_signs", []) or []
        last_vs = vs[-1] if vs else {}
        tpl = state.get("disease_template", {}) or {}
        patients.append({
            "name": (state.get("patient_data") or {}).get("name", pid[:10]),
            "risk": state.get("risk_level"),
            "news2": state.get("news2_score"),
            "alerts": len(state.get("clinical_alerts", []) or []),
            "spo2": last_vs.get("spo2"), "hr": last_vs.get("heart_rate"),
            "temp": last_vs.get("temperature"),
            "pain": last_vs.get("pain_score"),
            "dept": tpl.get("department", ""),
            "complications": _complication_alert_messages(state.get("clinical_alerts") or [])[-2:],
        })

    if not patients:
        return UnifiedResponse(data={"advice": "当前无活跃患者。", "ranked": []})

    # 规则排序: 告警+体征超时+pending为权重
    def _score(p):
        s = 0
        if p["news2"] and p["news2"] >= 5: s += 5
        if p["spo2"] and p["spo2"] < 92: s += 3
        if p["hr"] and (p["hr"] > 110 or p["hr"] < 50): s += 2
        if p["temp"] and p["temp"] > 38: s += 2
        if p["pain"] and p["pain"] >= 7: s += 2
        s += p["alerts"]
        return s

    ranked = sorted(patients, key=_score, reverse=True)
    top = ranked[:min(5, len(ranked))]

    # Rule-based priority is the default fast path. LLM wording is optional and
    # must never delay the operational nursing board.
    advice = f"共{len(patients)}名患者，建议优先巡查{len(top)}人。"
    if enhance_ai:
        try:
            from ..agent.config import get_cached_provider
            from ..agent.llm_utils import safe_llm_invoke
            provider = get_cached_provider()
            top_text = "; ".join(
                f"{p['name']}({p['risk']} NEWS2={p['news2']} alerts={p['alerts']})"
                for p in top
            )
            prompt = (
                f"护士巡查优先级: {top_text}。共{len(patients)}名患者。"
                f"请用一句中文(30字内)建议护士巡查顺序。不要前缀。"
            )
            llm_result = await safe_llm_invoke(provider, prompt, timeout=8.0)
            llm_advice = (llm_result or {}).get("response", "")
            if llm_advice:
                advice = llm_advice
        except Exception:
            pass

    return UnifiedResponse(data={
        "advice": advice,
        "source": "llm" if enhance_ai and advice != f"共{len(patients)}名患者，建议优先巡查{len(top)}人。" else "rules",
        "total_patients": len(patients),
        "ranked": top,
    })
