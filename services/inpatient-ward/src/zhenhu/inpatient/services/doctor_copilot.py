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
        "history_gaps": _history_gaps(state.get("history_data")),
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


def _history_gaps(history: object) -> list[dict[str, str]]:
    recorded = history if isinstance(history, dict) else {}
    gaps: list[dict[str, str]] = []
    for field, label in _HISTORY_FIELDS:
        value = recorded.get(field)
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
