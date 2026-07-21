"""Deterministic, read-only clinician workload reduction summaries."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .clinical_alerts import alert_message


def build_clinical_brief(state: dict[str, Any]) -> dict[str, Any]:
    """Build a common doctor/nurse briefing without mutating clinical state."""
    alerts = _alert_groups(state)
    lab_changes = _lab_changes(state)
    blockers = _discharge_blockers(state)
    return {
        "generated_by": "rule_based_clinical_brief",
        "round_preview": _round_preview(state, alerts, lab_changes),
        "alert_groups": alerts,
        "lab_changes": lab_changes,
        "handoff_brief": _handoff_brief(state, alerts),
        "discharge_blockers": blockers,
        "education_brief": _education_brief(state),
    }


def _round_preview(state: dict[str, Any], alerts: list[dict[str, Any]], lab_changes: list[dict[str, Any]]) -> dict[str, Any]:
    vital_signs = [item for item in state.get("vital_signs", []) if isinstance(item, dict)]
    latest = vital_signs[-1] if vital_signs else {}
    previous = vital_signs[-2] if len(vital_signs) > 1 else {}
    changes: list[str] = []
    for field, label, unit in (
        ("heart_rate", "心率", "bpm"), ("spo2", "SpO2", "%"),
        ("temperature", "体温", "C"), ("respiratory_rate", "呼吸频率", "/min"),
        ("systolic_mmhg", "收缩压", "mmHg"),
    ):
        current, prior = latest.get(field), previous.get(field)
        if isinstance(current, (int, float)) and isinstance(prior, (int, float)) and current != prior:
            direction = "上升" if current > prior else "下降"
            changes.append(f"{label}{direction}{abs(current - prior):g}{unit}")
    questions = [f"核对：{group['title']}" for group in alerts[:2]]
    questions.extend(f"复核：{change['name']}变化" for change in lab_changes[:2])
    if not questions:
        questions.append("核对主诉变化、治疗反应和今日检查计划")
    return {
        "summary": "；".join(changes) if changes else "尚无可比较的新增体征变化",
        "latest_vitals": _display_vitals(latest),
        "focus_questions": questions[:4],
        "pending_reviews": _pending_review_labels(state),
        "next_action": "优先完成待审核临床草案，再记录本次查房判断",
    }


def _display_vitals(vitals: dict[str, Any]) -> list[dict[str, Any]]:
    fields = (("heart_rate", "心率", "bpm"), ("spo2", "SpO2", "%"), ("temperature", "体温", "C"), ("respiratory_rate", "呼吸频率", "/min"))
    return [{"label": label, "value": value, "unit": unit} for key, label, unit in fields if (value := vitals.get(key)) is not None]


def _alert_groups(state: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for alert in [*(state.get("clinical_alerts", []) or []), *(state.get("nursing_alerts", []) or [])]:
        text = alert_message(alert).strip()
        if not text:
            continue
        key, title, urgency = _alert_bucket(text)
        if text not in groups[key]:
            groups[key].append(text)
    rank = {"high": 0, "medium": 1, "low": 2}
    result = []
    for key, items in groups.items():
        _, title, urgency = _alert_bucket(items[0])
        result.append({"key": key, "title": title, "urgency": urgency, "items": items, "count": len(items)})
    return sorted(result, key=lambda item: (rank[item["urgency"]], item["title"]))


def _alert_bucket(text: str) -> tuple[str, str, str]:
    value = text.lower()
    if any(token in value for token in ("spo2", "低氧", "呼吸", "氧")):
        return "respiratory", "呼吸与氧合风险", "high"
    if any(token in value for token in ("血压", "心率", "news2", "休克", "循环")):
        return "hemodynamic", "循环与生命体征风险", "high"
    if any(token in value for token in ("检验", "肌酐", "钾", "钠", "血糖", "lab")):
        return "laboratory", "检验异常", "medium"
    if any(token in value for token in ("药", "过敏", "相互作用")):
        return "medication", "用药安全", "medium"
    return "other", "其他待核对风险", "low"


def _lab_changes(state: dict[str, Any]) -> list[dict[str, Any]]:
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lab in state.get("lab_results", []) or []:
        if isinstance(lab, dict) and lab.get("name"):
            history[str(lab["name"])].append(lab)
    changes = []
    for name, values in history.items():
        if len(values) < 2:
            continue
        current, previous = values[-1], values[-2]
        try:
            delta = float(current.get("value")) - float(previous.get("value"))
        except (TypeError, ValueError):
            continue
        if delta:
            changes.append({
                "name": name, "current": current.get("value"), "previous": previous.get("value"),
                "unit": current.get("unit") or "", "delta": round(delta, 3),
                "direction": "up" if delta > 0 else "down",
                "recommendation": "结合症状、用药和参考范围复核，必要时按医嘱复查。",
            })
    return sorted(changes, key=lambda item: abs(float(item["delta"])), reverse=True)[:6]


def _handoff_brief(state: dict[str, Any], alerts: list[dict[str, Any]]) -> dict[str, Any]:
    latest_round = state.get("latest_round") or {}
    latest_summary = (state.get("shift_summaries") or state.get("shift_summary_history") or [])
    summary = latest_summary[-1] if isinstance(latest_summary, list) and latest_summary else {}
    return {
        "current_assessment": latest_round.get("assessment") or summary.get("summary") or "待本次查房补充评估",
        "unresolved_problems": [group["title"] for group in alerts[:3]],
        "pending_actions": _pending_review_labels(state),
        "next_shift_focus": list((state.get("decision_checklist") or []))[:3],
    }


def _discharge_blockers(state: dict[str, Any]) -> list[dict[str, str]]:
    """Return only actionable blockers for the *current* discharge stage.

    A patient in routine monitoring can have an unfinished discharge pre-check,
    but has not entered the discharge workflow.  Showing handoff and contact
    tasks there falsely implies that the patient is ready to leave.  The
    workflow panel uses the stable ``key`` and ``target`` fields to take the
    clinician directly to the owning surface.
    """
    if not _discharge_workflow_started(state):
        return []

    blockers = _criteria_blockers(state.get("discharge_criteria_check") or {})
    if not _post_signature_handoff_stage(state):
        return blockers[:6]

    if not state.get("handoff_acknowledged"):
        blockers.append({
            "key": "handoff_acknowledgement",
            "reason": "交接事项尚未签收",
            "action": "在交接闭环状态中确认接收方签收",
            "target": "handoff",
            "status": "blocking",
        })
    # The encrypted phone number stays in the contact service.  The hot
    # patient state carries only this completion bit for workflow projection.
    contact = state.get("follow_up_contact") or {}
    contact_registered = bool(state.get("follow_up_contact_registered")) or bool(contact.get("mobile_phone"))
    if not contact_registered:
        blockers.append({
            "key": "follow_up_contact",
            "reason": "未登记随访联系电话",
            "action": "取得患者授权后补录随访联系电话",
            "target": "contact",
            "status": "blocking",
        })
    return blockers[:6]


def _discharge_workflow_started(state: dict[str, Any]) -> bool:
    phase = str(state.get("phase") or "").lower()
    pending_review = state.get("pending_review") or {}
    pending_type = pending_review.get("type") if isinstance(pending_review, dict) else ""
    signature = str(state.get("discharge_sign_status") or "").lower()
    return bool(
        pending_type == "discharge_sign"
        or signature in {"signed", "approved", "completed"}
        or state.get("bridge_result")
        or state.get("bridge_error")
        or phase in {"discharge", "handoff", "confirm", "completed", "closed", "archived", "follow_up"}
    )


def _post_signature_handoff_stage(state: dict[str, Any]) -> bool:
    phase = str(state.get("phase") or "").lower()
    signature = str(state.get("discharge_sign_status") or "").lower()
    return bool(
        signature in {"signed", "approved", "completed"}
        or state.get("bridge_result")
        or state.get("bridge_error")
        or phase in {"handoff", "confirm", "completed", "closed", "archived", "follow_up"}
    )


def _criteria_blockers(criteria: dict[str, Any]) -> list[dict[str, str]]:
    if criteria.get("all_met"):
        return []

    blockers: list[dict[str, str]] = []
    detail_by_key = {
        str(item.get("key")): item
        for item in criteria.get("details", []) or []
        if isinstance(item, dict) and item.get("key")
    }
    for key, detail in detail_by_key.items():
        if detail.get("met") is True:
            continue
        blockers.append({
            "key": key,
            "reason": str(detail.get("label") or key),
            "action": str(detail.get("action") or "完成复评估或补齐对应临床记录"),
            "target": _normalize_blocker_target(detail.get("category")),
            "status": "blocking",
        })

    existing_keys = {item["key"] for item in blockers}
    for item in criteria.get("unmet", []) or []:
        key = str(item)
        if not key or key in existing_keys:
            continue
        blockers.append({
            "key": key,
            "reason": key,
            "action": "完成复评估或补齐对应临床记录",
            "target": "monitoring",
            "status": "blocking",
        })
    return blockers


def _normalize_blocker_target(value: Any) -> str:
    target = str(value or "").lower()
    return target if target in {"monitoring", "orders", "records", "discharge", "handoff", "contact"} else "monitoring"


def _education_brief(state: dict[str, Any]) -> dict[str, Any]:
    completed = [record for record in state.get("education_records", []) if isinstance(record, dict) and record.get("acknowledged")]
    handoff_items = [item for item in state.get("handoff_items", []) if isinstance(item, dict)]
    topics = [str(item.get("content") or item.get("type") or "出院注意事项") for item in handoff_items[:4]]
    if not topics:
        template = state.get("disease_template") or {}
        topics = [f"{template.get('name') or '当前疾病'}的用药、复诊与危险信号"]
    return {
        "topics": topics,
        "teach_back_questions": [f"请患者或照护者复述：{topic}" for topic in topics[:3]],
        "completed_count": len(completed),
        "requires_human_record": True,
    }


def _pending_review_labels(state: dict[str, Any]) -> list[str]:
    pending = state.get("pending_review") or {}
    labels = []
    if isinstance(pending, dict) and pending.get("type"):
        labels.append(f"等待医生审核：{pending['type']}")
    labels.extend(
        f"AI 草稿待审核：{item.get('draft_type', '未命名草稿')}"
        for item in state.get("assistant_action_drafts", [])
        if isinstance(item, dict) and item.get("status") == "pending"
    )
    return labels[:4]
