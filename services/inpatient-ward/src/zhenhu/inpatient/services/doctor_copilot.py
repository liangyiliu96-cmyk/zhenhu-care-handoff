"""Deterministic, evidence-linked preparation for a doctor's patient review."""

from __future__ import annotations

from typing import Any


_HISTORY_FIELDS = (
    ("chief_complaint", "主诉"),
    ("hpi_narrative", "现病史"),
    ("allergies", "过敏史"),
    ("pmh", "既往史"),
    ("ros_findings", "系统回顾"),
)


def build_pre_round_brief(state: dict[str, Any]) -> dict[str, Any]:
    """Return a read-only pre-round brief derived only from the supplied state.

    This function deliberately does not invoke an LLM. Each attention item
    carries its supporting source facts so a later drafting step cannot turn an
    unsupported inference into a clinical record.
    """

    return {
        "patient_id": str(state.get("patient_id") or ""),
        "state_version": int(state.get("state_version") or 0),
        "attention_items": _attention_items(state),
        "history_gaps": _history_gaps(state),
    }


def build_progress_note_draft(state: dict[str, Any]) -> dict[str, Any]:
    """Build a non-persistent SOAP draft without making clinical inferences.

    Assessment and plan stay explicitly incomplete until a clinician supplies
    them. This keeps the drafting helper useful for documentation while making
    it incapable of silently producing a diagnosis or treatment direction.
    """

    history = state.get("history_data") if isinstance(state.get("history_data"), dict) else {}
    subjective_facts: list[dict[str, Any]] = []
    chief_complaint = str(history.get("chief_complaint") or "").strip()
    if chief_complaint:
        subjective_facts.append(_fact("history", "current", "", "chief_complaint", chief_complaint))

    objective_facts: list[dict[str, Any]] = []
    objective_lines: list[str] = []
    vital = _latest_dict(state.get("vital_signs"))
    if vital:
        observed_at = str(vital.get("timestamp") or "")
        for field, label, unit in (("heart_rate", "心率", "次/分"), ("spo2", "血氧饱和度", "%"), ("temperature", "体温", "摄氏度")):
            if vital.get(field) is None:
                continue
            value = vital[field]
            objective_facts.append(_fact("vital_sign", "latest", observed_at, field, value))
            objective_lines.append(f"{label}{value}{unit}")
    lab = _latest_dict(state.get("lab_results"))
    if lab:
        name = str(lab.get("name") or "检验")
        value = lab.get("value")
        unit = str(lab.get("unit") or "")
        objective_facts.append(_fact("lab_result", str(lab.get("id") or "latest"), str(lab.get("timestamp") or ""), name, value))
        objective_lines.append(f"最近检验：{name} {value if value is not None else ''}{unit}".strip())

    return {
        "patient_id": str(state.get("patient_id") or ""),
        "state_version": int(state.get("state_version") or 0),
        "generation_source": "rule_based_fact_draft",
        "write_back": "requires_doctor_edit_and_existing_round_review",
        "sections": {
            "subjective": _draft_section(
                f"主诉：{chief_complaint}" if chief_complaint else "待医生补充",
                subjective_facts,
            ),
            "objective": _draft_section("；".join(objective_lines) if objective_lines else "待医生补充", objective_facts),
            "assessment": _draft_section("待医生补充", []),
            "plan": _draft_section("待医生补充", []),
        },
    }


def _attention_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, alert in enumerate(_dict_items(state.get("clinical_alerts"))):
        status = str(alert.get("status") or "active").lower()
        if status in {"resolved", "closed", "acknowledged"}:
            continue
        message = str(alert.get("message") or alert.get("content") or "待复核临床告警")
        items.append(
            {
                "kind": "clinical_alert",
                "priority": "high",
                "title": message,
                "action": "请结合当前患者情况复核该告警。",
                "facts": [
                    _fact(
                        "clinical_alert",
                        str(alert.get("id") or f"alert-{index + 1}"),
                        str(alert.get("timestamp") or ""),
                        "message",
                        message,
                    )
                ],
            }
        )

    latest_vital = _latest_dict(state.get("vital_signs"))
    heart_rate = _number(latest_vital.get("heart_rate")) if latest_vital else None
    if heart_rate is not None and heart_rate > 100:
        items.append(
            {
                "kind": "vital_sign_change",
                "priority": "high" if heart_rate >= 120 else "medium",
                "title": f"最新心率 {heart_rate:g} 次/分",
                "action": "请核对症状、节律和近期处置记录。",
                "facts": [
                    _fact(
                        "vital_sign",
                        "latest",
                        str(latest_vital.get("timestamp") or ""),
                        "heart_rate",
                        heart_rate,
                    )
                ],
            }
        )

    latest_lab = _latest_dict(state.get("lab_results"))
    if latest_lab:
        name = str(latest_lab.get("name") or "检验")
        value = latest_lab.get("value")
        items.append(
            {
                "kind": "recent_lab",
                "priority": "medium",
                "title": f"最近检验：{name} {value if value is not None else ''}".strip(),
                "action": "请结合趋势、参考范围和患者症状判断是否需要处置。",
                "facts": [
                    _fact(
                        "lab_result",
                        str(latest_lab.get("id") or "latest"),
                        str(latest_lab.get("timestamp") or ""),
                        name,
                        value,
                    )
                ],
            }
        )
    return items


def _history_gaps(state: dict[str, Any]) -> list[dict[str, str]]:
    recorded = state.get("history_data") if isinstance(state.get("history_data"), dict) else {}
    patient_history = state.get("patient_history") if isinstance(state.get("patient_history"), dict) else {}
    values = {
        "chief_complaint": recorded.get("chief_complaint") or state.get("chief_complaint"),
        "hpi_narrative": state.get("hpi_narrative") or recorded.get("hpi_narrative"),
        "allergies": state.get("allergies") or recorded.get("allergies"),
        "pmh": recorded.get("pmh") or patient_history.get("comorbidities"),
        "ros_findings": state.get("ros_findings") or recorded.get("ros_findings"),
    }
    gaps: list[dict[str, str]] = []
    for field, label in _HISTORY_FIELDS:
        value = values.get(field)
        if value not in (None, "", [], {}):
            continue
        gaps.append(
            {
                "field": field,
                "label": label,
                "status": "needs_input",
                "prompt": f"请补充{label}，系统不会根据其他病历内容自动推断。",
            }
        )
    return gaps


def _fact(source_type: str, source_id: str, observed_at: str, field: str, value: object) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "source_id": source_id,
        "observed_at": observed_at,
        "field": field,
        "value": value,
    }


def _draft_section(text: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "text": text,
        "status": "draft" if facts else "needs_input",
        "facts": facts,
    }


def _dict_items(value: object) -> list[dict[str, Any]]:
    return [item for item in (value or []) if isinstance(item, dict)] if isinstance(value, list) else []


def _latest_dict(value: object) -> dict[str, Any]:
    items = _dict_items(value)
    return items[-1] if items else {}


def _number(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
