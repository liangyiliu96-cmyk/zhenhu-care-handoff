"""内存状态存储——阶段D+：带TTL的跨请求共享(30分钟过期)。"""
import time as _time
from typing import Any

_store: dict[str, tuple[float, dict[str, Any]]] = {}
_TTL_SECONDS = 1800  # 30分钟


def _cleanup_expired() -> None:
    now = _time.time()
    expired = [k for k, (ts, _) in _store.items() if now - ts > _TTL_SECONDS]
    for k in expired:
        del _store[k]


def get_state(patient_id: str) -> dict[str, Any]:
    _cleanup_expired()
    entry = _store.get(patient_id)
    if entry:
        ts, state = entry
        if _time.time() - ts <= _TTL_SECONDS:
            return state
        del _store[patient_id]
    return {}


def set_state(patient_id: str, state: dict[str, Any]) -> None:
    _store[patient_id] = (_time.time(), state)


def update_state(patient_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    _cleanup_expired()
    ts, current = _store.get(patient_id, (_time.time(), {}))
    current.update(updates)
    _store[patient_id] = (ts, current)
    return current
