"""Agent Harness 安全护栏 —— 输出校验 + 幻觉检测 + 回退策略。

阶段M Agent升级: CircuitBreaker/AgentAuditHook/CircuitBreakerOpenError 从 contracts 导入，
住院特定校验函数保留在此。
"""

import time
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, Field

# 阶段M: 从 contracts 导入共享基础架构
from zhenhu.contracts.agent import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    AgentAuditHook,
)


class HandoffItemSchema(BaseModel):
    """交接事项必须满足的schema。"""

    type: str = Field(..., description="事项类型: medication|monitoring|followup")
    content: str = Field(..., min_length=5, description="事项内容")
    feedback: str | None = None


def validate_handoff_items(items: list[dict] | None) -> tuple[list[dict], list[str]]:
    """校验交接事项。返回(有效项, 错误列表)。

    阶段H审计修复: 防御 None 输入。
    """
    if not items:
        return [], []
    valid, errors = [], []
    for i, item in enumerate(items):
        try:
            HandoffItemSchema(**item)
            valid.append(item)
        except Exception as e:
            errors.append(f"handoff_item[{i}]: {e}")
    return valid, errors


def check_source_type(knowledge_results: list[dict], threshold: float = 0.6) -> dict:
    """基于检索评分判断溯源类型。

    score >= threshold → source_knowledge
    score < threshold  → source_none(幻觉标记, 不得入草稿)
    无结果            → source_none
    """
    if not knowledge_results:
        return {"source_type": "source_none", "count": 0}
    high_quality = [r for r in knowledge_results if r.get("score", 0) >= threshold]
    if high_quality:
        return {"source_type": "source_knowledge", "count": len(high_quality)}
    return {"source_type": "source_none", "count": 0}


def fallback_to_template(template: dict) -> dict:
    """RAG检索失败→回退到病种模板默认值。"""
    instructions = template.get("handoff_instructions", [])
    return {
        "handoff_items": [
            {
                "type": inst.get("type", "unknown"),
                "content": inst.get("content", ""),
                "source": "disease_template_fallback",
            }
            for inst in instructions
        ],
        "source_type": "source_none",
    }


def normalize_template(template: dict) -> dict:
    """标准化模板字段名，确保兼容性。
    
    将旧命名(key/alert_high/alert_low)统一为(name/alert_above/alert_below)。
    即使模板已用新字段名，该函数也是空操作。
    """
    vs = template.get("vital_signs", [])
    for v in vs:
        if "key" in v and "name" not in v:
            v["name"] = v.pop("key")
        if "alert_high" in v and "alert_above" not in v:
            v["alert_above"] = v.pop("alert_high")
        if "alert_low" in v and "alert_below" not in v:
            v["alert_below"] = v.pop("alert_low")
    return template


# 全局熔断器实例(阶段G) — 阶段M: 类型从 contracts 导入
bridge_circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
