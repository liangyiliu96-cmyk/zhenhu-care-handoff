"""臻护 Agent 基础架构 — 共享 AgentLoop、Harness、CircuitBreaker。

阶段M: 从 inpatient-ward 提取，供 4 服务共享。
"""
from typing import Generic, TypeVar, Callable, Protocol, runtime_checkable
from dataclasses import dataclass, field
from datetime import datetime
import time
import json
import os

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

    def is_open(self) -> bool:
        """检查熔断器是否处于 OPEN 状态。"""
        return self._state == "OPEN"

    def remaining_cooldown(self) -> float:
        """返回剩余冷却时间(s), 0 表示已恢复。"""
        if self._state != "OPEN":
            return 0.0
        return max(0.0, self._last_failure + self.recovery_timeout - time.monotonic())

    def reset(self):
        """手动重置熔断器。"""
        self._failure_count = 0
        self._state = "CLOSED"

    def record_failure(self):
        """记录一次失败，达到阈值自动 OPEN。"""
        self._failure_count += 1
        self._last_failure = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = "OPEN"


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

        # 1. 鉴别诊断场景 (P0-3: DDx fallback)
        if "鉴别诊断" in prompt or "ddx" in prompt.lower() or "DDx" in prompt:
            template = ctx.get("disease_template", {})
            disease_id = template.get("disease_id", "")
            disease_name = template.get("name", disease_id)
            # 基于病种模板生成标准鉴别诊断
            ddx_map = {
                "copd": [
                    {"diagnosis": "慢性阻塞性肺病急性加重", "icd10": "J44.1", "likelihood": "high",
                     "key_findings": ["呼吸困难加重", "痰量增加", "低氧血症"],
                     "rationale": "临床表现典型，符合COPD急性加重诊断标准"},
                    {"diagnosis": "社区获得性肺炎", "icd10": "J18.9", "likelihood": "moderate",
                     "key_findings": ["发热", "脓痰", "肺部浸润影"],
                     "rationale": "需排除合并感染可能，影像学有助于鉴别"},
                    {"diagnosis": "充血性心力衰竭", "icd10": "I50.9", "likelihood": "moderate",
                     "key_findings": ["端坐呼吸", "下肢水肿", "肺部啰音"],
                     "rationale": "呼吸困难需与心源性鉴别，NT-proBNP有助于区分"},
                    {"diagnosis": "肺栓塞", "icd10": "I26.9", "likelihood": "low",
                     "key_findings": ["突发胸痛", "低氧", "D-dimer升高"],
                     "rationale": "虽非典型，需排除隐匿性肺栓塞"},
                ],
                "stroke": [
                    {"diagnosis": "急性缺血性脑卒中", "icd10": "I63.9", "likelihood": "high",
                     "key_findings": ["突发言语障碍", "肢体无力", "NIHSS评分异常"],
                     "rationale": "急性起病+局灶性神经功能缺损，符合缺血性卒中特征"},
                    {"diagnosis": "短暂性脑缺血发作", "icd10": "G45.9", "likelihood": "moderate",
                     "key_findings": ["症状<24h缓解", "无影像学新发梗死"],
                     "rationale": "症状已缓解但需排查TIA，ABCD2评分评估风险"},
                    {"diagnosis": "颅内出血", "icd10": "I61.9", "likelihood": "moderate",
                     "key_findings": ["头痛", "意识障碍", "高血压"],
                     "rationale": "需CT排除出血性卒中，尤其合并高血压急症时"},
                    {"diagnosis": "低血糖发作", "icd10": "E16.2", "likelihood": "low",
                     "key_findings": ["血糖<3.9", "出汗", "意识模糊"],
                     "rationale": "代谢性原因需排除，尤其糖尿病患者"},
                ],
                "heart_failure": [
                    {"diagnosis": "急性失代偿性心力衰竭", "icd10": "I50.9", "likelihood": "high",
                     "key_findings": ["呼吸困难", "肺部啰音", "颈静脉怒张", "下肢水肿"],
                     "rationale": "典型心衰表现，BNP升高+超声可确诊"},
                    {"diagnosis": "COPD急性加重", "icd10": "J44.1", "likelihood": "moderate",
                     "key_findings": ["喘息", "咳嗽咳痰", "既往COPD病史"],
                     "rationale": "呼吸系统疾病需鉴别，尤其吸烟史患者"},
                    {"diagnosis": "急性冠脉综合征", "icd10": "I24.9", "likelihood": "moderate",
                     "key_findings": ["胸痛", "心电图异常", "肌钙蛋白升高"],
                     "rationale": "心衰常由ACS诱发，需动态监测心肌标志物"},
                    {"diagnosis": "肺栓塞", "icd10": "I26.9", "likelihood": "low",
                     "key_findings": ["突发呼吸困难", "胸痛", "D-dimer升高"],
                     "rationale": "突发低氧需排查，Wells评分+D-dimer筛查"},
                ],
            }
            ddx_list = ddx_map.get(disease_id, [
                {"diagnosis": f"{disease_name}(确认诊断)", "icd10": "", "likelihood": "high",
                 "key_findings": ["根据入院检查"],
                 "rationale": "根据临床表现和入院检查结果初步确认"},
                {"diagnosis": "相关鉴别诊断(需进一步评估)", "icd10": "", "likelihood": "moderate",
                 "key_findings": ["请结合具体临床表现"],
                 "rationale": "需结合更多临床信息进一步鉴别"},
            ])
            return {"ddx_list": ddx_list, "source_type": "source_knowledge"}

        # 2. 风险分析场景
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
    用法: set_ai_provider(DeepSeekProvider(api_key="sk-xxx", model="deepseek-v4-pro"))
    """

    BASE_URL = "https://api.deepseek.com/chat/completions"

    def __init__(
        self,
        api_key: str = "",
        model: str = "deepseek-v4-pro",
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


# ═══════════════════════════════════════════════════════════
# v0.3: Ollama 本地 LLM Provider
# ═══════════════════════════════════════════════════════════

class OllamaProvider:
    """Ollama 本地 LLM 提供者 — 零成本、零网络依赖。

    适用场景: DeepSeek 限流/断网时的本地备用, 或简单任务直接本地执行。
    推荐模型: qwen2.5:7b (中文)、llama3.1:8b (英文)
    """

    def __init__(self, model: str = "qwen2.5:7b", base_url: str = "http://localhost:11434",
                 temperature: float = 0.3):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature

    async def invoke(self, prompt: str, context: dict | None = None) -> dict:
        """调用 Ollama API。首次调用需加载模型(~10-30s), 后续2-5s。"""
        import httpx
        import json as _json

        context_text = _json.dumps(context or {}, ensure_ascii=False, default=str)[:2000]
        structured_prompt = (
            "You are a clinical drafting assistant. Return one valid JSON object only. "
            "Do not make autonomous clinical decisions and do not omit uncertainty.\n\n"
            f"Context: {context_text}\n\nRequest: {prompt}"
        )
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                resp = await client.post(
                    f"{self.base_url.rstrip('/')}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": structured_prompt,
                        "format": "json",
                        "stream": False,
                        "keep_alive": os.environ.get("OLLAMA_KEEP_ALIVE", "30m"),
                        "options": {"temperature": self.temperature},
                    },
                )
        except Exception as exc:
            return {"error": f"Ollama unavailable: {str(exc)[:160]}", "source_type": "source_none"}

        if resp.status_code != 200:
            return {"error": f"Ollama error {resp.status_code}", "source_type": "source_none"}

        raw_response = resp.json().get("response", "")
        try:
            result = _json.loads(raw_response)
            if not isinstance(result, dict):
                return {"answer": raw_response, "source_type": "source_knowledge"}
            result.setdefault("source_type", "source_knowledge")
            return result
        except (_json.JSONDecodeError, ValueError):
            return {"answer": raw_response, "source_type": "source_knowledge"}

    async def stream(self, prompt: str, context: dict | None = None):
        import httpx
        import json as _json
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": True,
                      "options": {"temperature": self.temperature}},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            chunk = _json.loads(line)
                            if chunk.get("response"):
                                yield {"token": chunk["response"]}
                        except _json.JSONDecodeError:
                            pass
