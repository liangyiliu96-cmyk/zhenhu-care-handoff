"""Canonical clinical-alert representation shared by API read and write paths."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


_RESOLVED = "resolved"


def canonicalize_alerts(alerts: list[Any] | None) -> list[dict[str, Any]]:
    """Expose legacy string alerts and structured alerts through one contract."""
    return [canonicalize_alert(alert, index) for index, alert in enumerate(alerts or [])]


def canonicalize_alert(alert: Any, index: int = 0) -> dict[str, Any]:
    if isinstance(alert, dict):
        result = deepcopy(alert)
        message = str(result.get("message") or result.get("text") or result.get("alert") or "")
    else:
        result = {}
        message = str(alert)

    result["alert_id"] = str(result.get("alert_id") or _legacy_alert_id(message, index))
    result["message"] = message
    result["status"] = str(result.get("status") or "open")
    result["severity"] = str(result.get("severity") or infer_alert_severity(message))
    result["source"] = str(result.get("source") or infer_alert_source(message))
    return result


def normalize_alerts(alerts: list[Any] | None) -> list[dict[str, Any]]:
    """Canonicalize and deduplicate alerts without losing lifecycle history."""
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for alert in canonicalize_alerts(alerts):
        signature = (alert["source"], alert["message"], alert["status"])
        if signature not in seen:
            normalized.append(alert)
            seen.add(signature)
    return normalized[-50:]


def create_clinical_alert(
    message: str,
    *,
    severity: str | None = None,
    source: str | None = None,
    status: str = "open",
) -> dict[str, Any]:
    """Create a new alert in the API's persisted representation."""
    alert = {
        "message": message,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if severity:
        alert["severity"] = severity
    if source:
        alert["source"] = source
    return canonicalize_alert(alert)


def alert_message(alert: Any) -> str:
    return canonicalize_alert(alert)["message"]


def is_complication_alert(alert: Any) -> bool:
    canonical = canonicalize_alert(alert)
    return canonical["source"] == "complication" or "\u5e76\u53d1\u75c7" in canonical["message"]


def infer_alert_severity(message: str) -> str:
    normalized = message.lower()
    if "critical" in normalized or "\u5371\u6025\u503c" in message:
        return "critical"
    if "warning" in normalized or "\u9884\u8b66" in message:
        return "warning"
    return "info"


def infer_alert_source(message: str) -> str:
    if "\u5e76\u53d1\u75c7" in message:
        return "complication"
    if "critical" in message.lower() or "\u5371\u6025\u503c" in message:
        return "lab"
    if message.startswith("[") and "]" in message:
        return message[1:message.index("]")].lower().replace("=", "_")
    return "clinical"


def is_critical_alert(alert: Any) -> bool:
    return canonicalize_alert(alert)["severity"].lower() == "critical"


def is_active_alert(alert: Any) -> bool:
    return canonicalize_alert(alert)["status"] != _RESOLVED


def _legacy_alert_id(message: str, index: int) -> str:
    digest = sha256(f"{index}:{message}".encode("utf-8")).hexdigest()[:20]
    return f"legacy:{digest}"
