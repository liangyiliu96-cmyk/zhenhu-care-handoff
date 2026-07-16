"""内存状态存储 —— 阶段D: 跨请求共享患者Agent状态(生产应换Redis)。合并迁入。

阶段H审计修复: 添加 update_state 原子操作,避免 read-modify-write 竞态。
"""
from typing import Any

_store: dict[str, Any] = {}

def get_state(patient_id: str) -> dict[str, Any]:
    """获取患者状态。阶段D: 内存存储(生产应换Redis)。"""
    return _store.get(patient_id, {})

def set_state(patient_id: str, state: dict[str, Any]) -> None:
    """写入患者状态。阶段D: 内存存储(生产应换Redis)。"""
    _store[patient_id] = state

def update_state(patient_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """原子更新患者状态(阶段H: 修复 read-modify-write 竞态)。"""
    current = _store.get(patient_id, {})
    current.update(updates)
    _store[patient_id] = current
    return current
