"""臻护 Agent 基础架构 — 共享 AgentLoop、Harness、CircuitBreaker。

阶段M: 从 inpatient-ward 提取，供 4 服务共享。
"""
from typing import Generic, TypeVar, Callable, Protocol, runtime_checkable
from dataclasses import dataclass, field
from datetime import datetime
import time
import asyncio
import json

T = TypeVar("T")


# ── AgentLoop ──

@dataclass
class AgentEvent:
    event_type: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "system"


@dataclass
class LoopTrace:
    turn_id: str
    entry_strategy: str
    node_path: list[str] = field(default_factory=list)
    events_pushed: int = 0
    errors: list[dict] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None


class AgentLoop(Generic[T]):
    """类型化 Agent 事件循环 — 服务级单例共享。"""

    def __init__(self, max_traces: int = 100):
        self._queue: list[AgentEvent] = []
        self._traces: list[LoopTrace] = []
        self._max_traces = max_traces
        self._current_state: dict | None = None

    def push(self, *events: AgentEvent) -> int:
        self._queue.extend(events)
        return len(self._queue)

    @property
    def traces(self) -> list[LoopTrace]:
        return self._traces[-self._max_traces:]

    @property
    def current_state(self) -> dict | None:
        return self._current_state


# ── CircuitBreaker ──

@dataclass
class CircuitBreaker:
    """熔断器 — 3次失败→OPEN→30s→HALF_OPEN→CLOSED。"""
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    _failure_count: int = 0
    _last_failure: float = 0.0
    _state: str = "CLOSED"

    def call(self, fn: Callable, *args, **kwargs):
        if self._state == "OPEN":
            if time.monotonic() - self._last_failure > self.recovery_timeout:
                self._state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenError(f"熔断器 OPEN, {self.recovery_timeout}s 后重试")
        try:
            result = fn(*args, **kwargs)
            self._failure_count = 0
            self._state = "CLOSED"
            return result
        except Exception:
            self._failure_count += 1
            self._last_failure = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = "OPEN"
            raise


class CircuitBreakerOpenError(Exception):
    pass


# ── AgentAuditHook ──

@dataclass
class AgentAuditHook:
    """Agent 节点审计钩子。"""
    MAX_EVENTS = 500
    events: list[dict] = field(default_factory=list)

    def on_node_enter(self, node_name: str, state: dict) -> None:
        if len(self.events) >= self.MAX_EVENTS:
            self.events = self.events[-self.MAX_EVENTS // 2:]
        self.events.append({"type": "node_enter", "node": node_name, "timestamp": time.time()})

    def on_node_exit(self, node_name: str, result: dict) -> None:
        self.events.append({"type": "node_exit", "node": node_name, "timestamp": time.time()})

    def on_error(self, node_name: str, error: str) -> None:
        self.events.append({"type": "node_error", "node": node_name, "error": error, "timestamp": time.time()})


# ── AIProvider 协议 ──

@runtime_checkable
class AIProvider(Protocol):
    """LangChain 兼容的 AI 提供者协议。

    阶段M: 4 服务统一的 LLM 调用接口。当前 fixture 占位，阶段 5 接入真实模型。
    """

    async def invoke(self, prompt: str, context: dict | None = None) -> dict:
        """同步调用：输入 prompt + context，返回结构化结果。"""
        ...

    async def stream(self, prompt: str, context: dict | None = None):
        """流式调用：逐步返回 token。"""
        ...


class FixtureAIProvider:
    """Fixture AI 提供者 — 阶段 0 默认实现。"""
    async def invoke(self, prompt: str, context: dict | None = None) -> dict:
        return {"result": "fixture", "source_type": "source_none"}
    async def stream(self, prompt: str, context: dict | None = None):
        yield {"token": "fixture"}


class RuleBasedProvider:
    """规则驱动的 AI 提供者 — 阶段 M：基于病种模板+上下文生成结构化临床输出。

    无外部 API 依赖，使用规则引擎替代 LLM 调用。
    当真实 LLM 接入时，set_ai_provider(OpenAIProvider()) 即可替换。
    """

    async def invoke(self, prompt: str, context: dict | None = None) -> dict:
        ctx = context or {}

        # 1. 风险分析场景
        if "analyse" in prompt.lower() or "风险" in prompt:
            template = ctx.get("disease_template", {})
            risks = []
            for rf in template.get("risk_factors", [])[:3]:
                risks.append({
                    "risk_id": f"risk-{rf[:8]}",
                    "category": "clinical_risk",
                    "severity": "medium",
                    "title": f"风险因子: {rf}",
                    "source_type": "source_knowledge",
                })
            return {"risks": risks, "source_type": "source_knowledge"}

        # 2. 分块后处理场景
        if "分块" in prompt or "chunk" in prompt.lower():
            chunks = ctx.get("chunks", [])
            tags = ctx.get("disease_tags", ["心血管"])
            return {
                "chunks": [
                    {**c, "keywords": ["临床指南"], "tags": tags[:1]}
                    for c in chunks
                ],
                "source_type": "source_knowledge",
            }

        # 3. 出院指导场景
        if "出院" in prompt or "handoff" in prompt.lower():
            template = ctx.get("disease_template", {})
            instructions = template.get("handoff_instructions", [])
            return {
                "handoff_items": instructions,
                "source_type": "source_knowledge",
            }

        # 默认
        return {"result": "rule_based", "source_type": "source_none"}

    async def stream(self, prompt: str, context: dict | None = None):
        result = await self.invoke(prompt, context)
        for k, v in result.items():
            yield {k: v}


# 全局默认 Provider — 阶段 M2 默认规则引擎（接真实 LLM 后自动替换）
_default_provider: AIProvider = RuleBasedProvider()


class DeepSeekProvider:
    """DeepSeek V4 提供者 — 对接 deepseek-v4-flash / v4-pro 模型。

    OpenAI 兼容 API: POST https://api.deepseek.com/chat/completions
    用法: set_ai_provider(DeepSeekProvider(api_key="sk-xxx", model="deepseek-v4-flash"))
    """

    BASE_URL = "https://api.deepseek.com/chat/completions"

    def __init__(
        self,
        api_key: str = "",
        model: str = "deepseek-v4-flash",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def invoke(self, prompt: str, context: dict | None = None) -> dict:
        """调用 DeepSeek API，返回结构化 JSON 结果。

        阶段 M2: 临床场景注入 system prompt 引导模型输出 JSON Schema。
        """
        import httpx

        ctx = context or {}
        template = ctx.get("disease_template", {})

        # 构造系统提示词（引导 JSON 输出）
        system_msg = (
            "你是臻护临床 AI 助手。请根据输入生成结构化 JSON 输出。"
            "输出必须包含 source_type 字段（source_knowledge/source_ehr/source_none）。"
        )

        user_msg = f"提示: {prompt}\n上下文: {json.dumps(ctx, ensure_ascii=False, default=str)[:2000]}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self.BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    result = json.loads(content)
                    if "source_type" not in result:
                        result["source_type"] = "source_knowledge"
                    return result
                return {"error": f"API {resp.status_code}", "source_type": "source_none"}
        except Exception as e:
            return {"error": str(e)[:200], "source_type": "source_none"}

    async def stream(self, prompt: str, context: dict | None = None):
        result = await self.invoke(prompt, context)
        for k, v in result.items():
            yield {k: v}

def get_ai_provider() -> AIProvider:
    return _default_provider

def set_ai_provider(provider: AIProvider) -> None:
    global _default_provider
    _default_provider = provider
