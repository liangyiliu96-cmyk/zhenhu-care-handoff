"""Agent Harness 安全护栏 —— 输出校验 + 幻觉检测 + 回退策略。合并迁入。

参考臻护需求§5.1: Agent输出必须标注溯源类型, source_none不得入草稿。
"""

import time
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, Field


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


# ============================================================================
# 阶段G: Harness 增强 —— 熔断器 + 结构化审计钩子
# ============================================================================


@dataclass
class CircuitBreaker:
    """熔断器 — 外部服务调用保护(阶段G)。

    3 次连续失败 → OPEN(拒绝调用 30s) → HALF_OPEN(试探 1 次) → CLOSED。
    """

    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    _failure_count: int = 0
    _last_failure: float = 0.0
    _state: str = "CLOSED"  # CLOSED|OPEN|HALF_OPEN

    def call(self, fn: Callable, *args, **kwargs):
        """包装外部调用, 自动熔断(阶段G)。"""
        if self._state == "OPEN":
            if time.monotonic() - self._last_failure > self.recovery_timeout:
                self._state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenError(
                    f"熔断器 OPEN, {self.recovery_timeout}s 后重试"
                )

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self):
        self._failure_count = 0
        self._state = "CLOSED"

    def _on_failure(self):
        self._failure_count += 1
        self._last_failure = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = "OPEN"


class CircuitBreakerOpenError(Exception):
    """熔断器打开时抛出的异常(阶段G)。"""
    pass


# 全局熔断器实例(阶段G)
bridge_circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)


@dataclass
class AgentAuditHook:
    """Agent 节点审计钩子 — 每个节点执行前后写入结构化事件(阶段G)。

    阶段H审计修复: 限制 events 上限防止内存泄漏。
    """

    MAX_EVENTS = 500

    events: list[dict] = field(default_factory=list)

    def _trim_events(self) -> None:
        if len(self.events) >= self.MAX_EVENTS:
            self.events = self.events[-self.MAX_EVENTS // 2:]

    def on_node_enter(self, node_name: str, state: dict) -> None:
        self._trim_events()
        self.events.append({
            "type": "node_enter",
            "node": node_name,
            "phase_before": state.get("phase"),
            "timestamp": time.time(),
        })

    def on_node_exit(self, node_name: str, result: dict) -> None:
        self._trim_events()
        self.events.append({
            "type": "node_exit",
            "node": node_name,
            "phase_after": result.get("phase"),
            "timestamp": time.time(),
        })

    def on_error(self, node_name: str, error: str) -> None:
        self._trim_events()
        self.events.append({
            "type": "node_error",
            "node": node_name,
            "error": error,
            "timestamp": time.time(),
        })

    def to_dict(self) -> dict:
        return {"total_events": len(self.events), "events": self.events}
