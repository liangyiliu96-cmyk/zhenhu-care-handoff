"""LLM 工具层 —— P1-4 从 nodes_clinical.py 独立出来的共享 LLM 基础设施。

包含: safe_llm_invoke（统一超时+重试入口）、LLM 结果缓存、DDxItem schema。
P2-1: 新增 LLM 成本追踪（调用次数/延迟/token 估算/缓存命中率）。
v0.3: DeepAgent 管线 — deep_invoke() 内置 Collect(RAG)→Execute(LLM)→Refine(验证)。
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
import time as _time
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("zhenhu.inpatient")

# ── P2-1: LLM 成本追踪计数器 ──
_metrics_lock = threading.Lock()
_llm_metrics = {
    "total_calls": 0,        # 总调用次数（含重试）
    "success": 0,            # 成功次数
    "cache_hits": 0,         # 缓存命中次数
    "timeouts": 0,           # 超时次数
    "errors": 0,             # 异常次数
    "total_latency_ms": 0.0,  # 总延迟（ms）
    "total_prompt_chars": 0,  # 总 prompt 字符数
    "total_response_chars": 0, # 总 response 字符数
    "fallback_success": 0,     # Successful calls served by Ollama fallback
}


def get_llm_metrics() -> dict:
    """返回 LLM 成本追踪指标快照。"""
    with _metrics_lock:
        return dict(_llm_metrics)


def _record_llm_call(success: bool, latency_s: float, prompt_len: int, response_len: int = 0,
                     cache_hit: bool = False, timeout: bool = False, error: bool = False,
                     fallback: bool = False):
    """线程安全地记录一次 LLM 调用指标。"""
    with _metrics_lock:
        _llm_metrics["total_calls"] += 1
        _llm_metrics["total_latency_ms"] += latency_s * 1000
        _llm_metrics["total_prompt_chars"] += prompt_len
        _llm_metrics["total_response_chars"] += response_len
        if success:
            _llm_metrics["success"] += 1
        if cache_hit:
            _llm_metrics["cache_hits"] += 1
        if timeout:
            _llm_metrics["timeouts"] += 1
        if error:
            _llm_metrics["errors"] += 1
        if fallback:
            _llm_metrics["fallback_success"] += 1

# ── LLM 缓存：防 resume 重算，带 TTL + 上限 ──
_llm_cache: dict[str, tuple[float, dict]] = {}  # key → (timestamp, value)
_MAX_CACHE_SIZE = 200
_CACHE_TTL = 1800  # 30 分钟


def cache_get(key: str) -> dict | None:
    """从 LLM 缓存中读取（TTL 内有效）。P2-1: 记录命中。"""
    entry = _llm_cache.get(key)
    if entry:
        ts, val = entry
        if _time.time() - ts < _CACHE_TTL:
            _record_llm_call(success=True, latency_s=0.0, prompt_len=0, cache_hit=True)
            return val
        del _llm_cache[key]
    return None


def cache_set(key: str, value: dict) -> None:
    """写入 LLM 缓存（超出上限时淘汰最旧 20%）。"""
    if len(_llm_cache) >= _MAX_CACHE_SIZE:
        old_keys = sorted(_llm_cache.keys(), key=lambda k: _llm_cache[k][0])[:40]
        for k in old_keys:
            del _llm_cache[k]
    _llm_cache[key] = (_time.time(), value)


def cache_key(patient_id: str, phase: str, inputs: dict) -> str:
    """生成 SHA256 前 16 位的短缓存键，用于幂等检测。"""
    raw = f"{patient_id}:{phase}:{json.dumps(inputs, sort_keys=True, ensure_ascii=False)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ── LLM 超时保护：统一包装 invoke ──
async def safe_llm_invoke(provider: Any, prompt: str, context: dict | None = None,
                          timeout: float | None = None, retries: int | None = None,
                          caller: str = "") -> dict | None:
    """统一 LLM 调用入口，带超时保护 + 指数退避重试 + 异常日志 + P2-1 成本追踪。

    Args:
        provider: AI provider 实例
        prompt: LLM prompt 文本
        context: 可选的上下文 dict
        timeout: 超时秒数（默认从 LLM_TIMEOUT 环境变量读取，默认 10s）
        retries: 失败后重试次数（默认从 LLM_RETRIES 环境变量读取，默认 1 次）
        caller: 调用者标识（用于追踪，如 "hpi"/"ddx"/"daily_round"）

    Returns:
        LLM 返回的 dict，超时/异常时返回 None（不抛异常，不阻断临床流程）
    """
    prompt_len = len(prompt)
    t_start = _time.monotonic()

    # 环境变量覆盖默认值
    if timeout is None:
        timeout = float(os.environ.get("LLM_TIMEOUT", "10"))
    if retries is None:
        retries = int(os.environ.get("LLM_RETRIES", "1"))

    for attempt in range(retries + 1):
        try:
            if isinstance(provider, FailoverProvider):
                invoke = provider.invoke_with_timeouts(
                    prompt,
                    context=context or {},
                    primary_timeout=timeout,
                )
                total_timeout = timeout + provider.fallback_timeout + 1
            else:
                invoke = provider.invoke(prompt, context=context or {})
                total_timeout = timeout
            result = await asyncio.wait_for(
                invoke,
                timeout=total_timeout,
            )
            if _provider_failed(result):
                raise RuntimeError(str(result.get("error", "LLM returned no usable result"))[:200])
            latency = _time.monotonic() - t_start
            backend = result.pop("_llm_backend", "configured") if isinstance(result, dict) else "configured"
            used_fallback = backend == "ollama"
            if used_fallback:
                logger.warning("safe_llm_invoke[%s]: DeepSeek unavailable, served by Ollama fallback", caller)
            resp_len = len(json.dumps(result, ensure_ascii=False)) if result else 0
            _record_llm_call(success=True, latency_s=latency, prompt_len=prompt_len, response_len=resp_len, fallback=used_fallback)
            from .metrics import record_llm_call
            record_llm_call(success=True)
            return result
        except asyncio.TimeoutError:
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s...
                continue
            logger.warning("safe_llm_invoke[%s]: timeout after %.1fs, retries exhausted", caller, timeout)
            latency = _time.monotonic() - t_start
            _record_llm_call(success=False, latency_s=latency, prompt_len=prompt_len, timeout=True)
            from .metrics import record_llm_call
            record_llm_call(success=False)
            return None
        except Exception as e:
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)
                continue
            logger.warning("safe_llm_invoke[%s]: invoke failed: %s", caller, str(e)[:120])
            latency = _time.monotonic() - t_start
            _record_llm_call(success=False, latency_s=latency, prompt_len=prompt_len, error=True)
            from .metrics import record_llm_call
            record_llm_call(success=False)
            return None


# ── DDx Pydantic schema ──
class DDxItem(BaseModel):
    diagnosis: str
    icd10: str = ""
    likelihood: str  # high|moderate|low


# ═══════════════════════════════════════════════════════════
# v0.3: DeepAgent 管线 — Collect(RAG)→Execute(LLM)→Refine(验证)
# ═══════════════════════════════════════════════════════════

# RAG 路由表: 节点名 → 搜索层
NODE_RAG_MAP: dict[str, list[str]] = {
    "admission": ["L2"],           # 入院→疾病要点
    "triage": ["L1", "L7"],        # 分诊→评分+急症流程
    "history_taking": ["L2"],      # 病史→疾病要点
    "ddx": ["L2", "L6"],           # 鉴别→疾病+检验
    "medication_reconciliation": ["L5"],  # 用药→药物安全
    "medication_adjust": ["L5"],    # 调药草案→药物安全
    "nursing": ["L4", "L8"],       # 护理→科室清单+操作规程
    "daily_round": ["L1", "L2", "L6"],  # 查房→评分+要点+检验
    "monitoring": ["L1"],          # 监测→评分
    "discharge": ["L3", "L9"],     # 出院→模板+患教
    "shift_summary": ["L1", "L2"], # 交班→评分+要点
    "lab_review": ["L6"],          # 检验→参考值
}

# v0.3: LLM 模型智能路由 — flash(快) vs pro(强推理)
# 收益: 简单任务用时 -60%, API费用 -70%, 复杂任务精度不降
NODE_MODEL_MAP: dict[str, str] = {
    # ── pro: 需要深度医学推理 ──
    "ddx": os.environ.get("DEEPSEEK_MODEL_PRO", "deepseek-chat"),                    # 鉴别诊断: 多病种推理
    "medication_reconciliation": os.environ.get("DEEPSEEK_MODEL_PRO", "deepseek-chat"), # 用药核对: 相互作用分析
    "medication_adjust": os.environ.get("DEEPSEEK_MODEL_PRO", "deepseek-chat"),      # 调药草案: 保持与用药核对同级
    "discharge": os.environ.get("DEEPSEEK_MODEL_PRO", "deepseek-chat"),               # 出院判断: 多因素权衡
    "history_taking": os.environ.get("DEEPSEEK_MODEL_PRO", "deepseek-chat"),          # 病史采集: 复杂语义理解
    # ── flash: 结构化/简短/高频 ──
    "daily_round": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),           # 查房: 一句建议
    "nursing": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),               # 护理: 清单生成
    "triage": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),                # 分诊: 规则为主
    "admission": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),             # 入院: 模板匹配
    "monitoring": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),            # 监测: 阈值检查
    "shift_summary": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),         # 交班: 摘要合成
    "lab_review": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),            # 检验: 参考值对比
    "db_agent": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),              # DB: SQL 生成
    # 默认必须服从部署配置，避免治理收敛时把原先的显式 Pro 部署静默降级。
    "default": os.environ.get("DEEPSEEK_MODEL", os.environ.get("DEEPSEEK_MODEL_PRO", "deepseek-chat")),
}


def get_model_for_node(caller: str) -> str:
    """根据节点类型返回最优模型: pro=强推理, flash=快。"""
    return NODE_MODEL_MAP.get(caller, NODE_MODEL_MAP["default"])


# 模型实例缓存 — 避免每个节点调用都创建新 Provider
_provider_cache: dict[str, Any] = {}
_provider_cache_lock = threading.Lock()

# Local inference is deliberately limited to drafting and summarization nodes.
# Diagnosis, medication changes and discharge decisions continue to use their
# existing rule/human-confirmation paths when DeepSeek is unavailable.
_DEFAULT_OLLAMA_FALLBACK_CALLERS = frozenset({
    "admission", "triage", "nursing", "daily_round", "monitoring",
    "shift_summary", "handoff", "lab_review", "assistant", "patient_query",
    "ward_priority",
})


class _UnavailableProvider:
    async def invoke(self, _prompt: str, context: dict | None = None) -> dict:
        del context
        return {"error": "No LLM provider is available", "source_type": "source_none"}


class FailoverProvider:
    """Run DeepSeek first and use a local Ollama model only after failure."""

    def __init__(self, primary: Any | None, fallback: Any | None, caller: str):
        self.primary = primary
        self.fallback = fallback
        self.caller = caller
        self.fallback_timeout = float(os.environ.get("OLLAMA_FALLBACK_TIMEOUT", "45"))

    async def invoke(self, prompt: str, context: dict | None = None) -> dict:
        return await self.invoke_with_timeouts(prompt, context=context)

    async def invoke_with_timeouts(
        self,
        prompt: str,
        context: dict | None = None,
        primary_timeout: float | None = None,
        fallback_timeout: float | None = None,
    ) -> dict:
        primary_timeout = primary_timeout or float(os.environ.get("LLM_TIMEOUT", "10"))
        fallback_timeout = fallback_timeout or self.fallback_timeout
        if self.primary is not None:
            try:
                result = await asyncio.wait_for(
                    self.primary.invoke(prompt, context=context),
                    timeout=primary_timeout,
                )
                if not _provider_failed(result):
                    return _with_backend(result, "deepseek")
                logger.warning("LLM primary unavailable for %s: %s", self.caller, result.get("error", "unknown error"))
            except Exception as exc:
                logger.warning("LLM primary invocation failed for %s: %s", self.caller, str(exc)[:160])

        if self.fallback is not None:
            try:
                result = await asyncio.wait_for(
                    self.fallback.invoke(prompt, context=context),
                    timeout=fallback_timeout,
                )
                if not _provider_failed(result):
                    return _with_backend(result, "ollama")
                return result
            except Exception as exc:
                return {"error": f"Ollama fallback failed: {str(exc)[:160]}", "source_type": "source_none"}

        return {"error": "No configured LLM provider is available", "source_type": "source_none"}


def _provider_failed(result: Any) -> bool:
    return not isinstance(result, dict) or bool(result.get("error"))


def _with_backend(result: dict, backend: str) -> dict:
    tagged = dict(result)
    tagged["_llm_backend"] = backend
    return tagged


def _ollama_fallback_enabled(caller: str) -> bool:
    if os.environ.get("OLLAMA_FALLBACK_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    configured = os.environ.get("OLLAMA_FALLBACK_CALLERS", "").strip()
    if not configured:
        return caller in _DEFAULT_OLLAMA_FALLBACK_CALLERS
    allowed = {item.strip() for item in configured.split(",") if item.strip()}
    return "*" in allowed or caller in allowed


def clear_provider_cache() -> None:
    with _provider_cache_lock:
        _provider_cache.clear()


async def warm_ollama_fallback() -> bool:
    """Warm the local drafting model in the background without blocking startup."""
    if os.environ.get("OLLAMA_FALLBACK_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    from zhenhu.contracts.agent import OllamaProvider

    provider = OllamaProvider(
        model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        temperature=0.0,
    )
    try:
        result = await provider.invoke('Return JSON only: {"warmup":"ready"}')
        if _provider_failed(result):
            logger.warning("Ollama fallback warmup unavailable: %s", result.get("error", "unknown error"))
            return False
        logger.info("Ollama fallback warmup completed for model %s", provider.model)
        return True
    except Exception as exc:
        logger.warning("Ollama fallback warmup failed: %s", str(exc)[:160])
        return False

# v0.3: RAG 同回合缓存 — 同一查询+层级 在一次 turn 内不重复查 Milvus
_rag_turn_cache: dict[str, list[dict]] = {}
_rag_turn_cache_lock = threading.Lock()


def get_provider_for_node(caller: str = "default"):
    """获取节点最优模型 Provider，自动缓存。

    使用方式: 替代 get_cached_provider()
        provider = get_provider_for_node("ddx")      # → V4-Pro
        provider = get_provider_for_node("nursing")   # → V4-flash
    """
    model = get_model_for_node(caller)
    fallback_enabled = _ollama_fallback_enabled(caller)
    ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    cache_key = f"{caller}:{model}:{fallback_enabled}:{ollama_model}"
    with _provider_cache_lock:
        if cache_key not in _provider_cache:
            from zhenhu.contracts.agent import DeepSeekProvider, OllamaProvider

            key = os.environ.get("DEEPSEEK_API_KEY", "")
            primary = DeepSeekProvider(api_key=key, model=model, temperature=0.3) if key else None
            fallback = OllamaProvider(
                model=ollama_model,
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                temperature=float(os.environ.get("OLLAMA_TEMPERATURE", "0.3")),
            ) if fallback_enabled else None
            _provider_cache[cache_key] = FailoverProvider(primary, fallback, caller) if primary or fallback else _UnavailableProvider()
    return _provider_cache[cache_key]


async def _rag_collect(query: str, caller: str, top_k: int = 3) -> list[dict]:
    """Collect 阶段: 从 Milvus 检索相关知识。同 query+caller 在 turn 内缓存。"""
    cache_key = f"{caller}:{query[:60]}"
    with _rag_turn_cache_lock:
        if cache_key in _rag_turn_cache:
            return _rag_turn_cache[cache_key]

    layers = NODE_RAG_MAP.get(caller, ["L2"])
    try:
        from .rag_engine import search as rag_search
        all_hits = []
        for layer in layers:
            hits = await rag_search(query, layer=layer, top_k=top_k)
            all_hits.extend(hits)
        seen = set()
        unique = []
        for h in sorted(all_hits, key=lambda x: x["score"], reverse=True):
            key = h["text"][:50]
            if key not in seen:
                seen.add(key)
                unique.append(h)
        result = unique[:top_k]

        with _rag_turn_cache_lock:
            _rag_turn_cache[cache_key] = result
        return result
    except Exception as e:
        logger.debug("RAG collect [%s]: %s", caller, e)
        return []


def clear_rag_turn_cache():
    """清空 RAG 同回合缓存 — Loop 每轮开始时调用。"""
    with _rag_turn_cache_lock:
        _rag_turn_cache.clear()
    logger.debug("RAG turn cache cleared")


async def deep_invoke(
    provider: Any,
    prompt: str,
    rag_query: str | None = None,
    context: dict | None = None,
    caller: str = "",
    timeout: float = 30.0,       # v4-pro 需要更长超时
    validate_fields: list[str] | None = None,
    state: dict | None = None,  # v0.3: 传入患者状态以触发 API 数据收集
    allow_db: bool = False,    # v0.3: 允许 LLM 查询数据库（自然语言→SQL）
    db_question: str = "",     # 数据库查询的自然语言问题
) -> dict | None:
    """DeepAgent 推理入口 — Collect→Execute→Refine 三阶段管线。

    Collect: RAG 检索 + API 数据补全，注入 prompt
    Execute: LLM 推理（带超时保护）
    Refine: RAG 反查验证关键字段 + 标记矛盾

    Args:
        provider: AI provider
        prompt: 核心 prompt（不含 RAG 上下文）
        rag_query: RAG 检索 query，None 则用 prompt 前 100 字
        context: 额外上下文
        caller: 调用者标识（用于 RAG 路由映射）
        timeout: 超时秒数（DeepAgent 管线下默认 15s）
        validate_fields: 需要 RAG 反查验证的字段，如 ["diagnosis","medication"]
    """
    # ── 1. Collect: RAG 检索 + OpenAPI 数据 ──
    rag_context = ""
    rag_sources = []
    if rag_query or prompt:
        q = rag_query or prompt[:100]
        try:
            hits = await _rag_collect(q, caller, top_k=3)
            if hits:
                rag_context = "【临床知识参考】\n" + "\n".join(
                    f"[{h.get('layer','?')}|{h.get('topic','')}] {h['text'][:150]}"
                    for h in hits
                )
                rag_sources = [{"layer": h.get("layer"), "topic": h.get("topic"), "id": h.get("disease_id")} for h in hits]
        except Exception:
            pass

    api_context = ""
    if state:
        try:
            from .clinical_external import enrich_prompt_from_api
            api_context = await enrich_prompt_from_api(state)
        except Exception:
            pass

    # 拼接 Collect 数据到 prompt 前
    if api_context:
        prompt = f"{api_context}\n\n{prompt}"

    # ── 1½. DB Agent: LLM 自然语言查询数据库 ──
    if allow_db and db_question and provider:
        db_result = await _db_agent_query(provider, db_question)
        if db_result:
            prompt = f"【数据库查询结果】\n{db_result}\n\n{prompt}"
    if rag_context:
        prompt = f"{rag_context}\n\n---\n基于以上知识参考和以下临床数据：\n{prompt}"

    # ── 2. Execute: LLM 推理 ──
    result = await safe_llm_invoke(provider, prompt, context, timeout=timeout, caller=caller)

    # ── 3. Refine: RAG 反查验证 ──
    verification = None
    if result and validate_fields:
        try:
            verification = await _rag_verify(result, validate_fields)
            if verification.get("conflicts"):
                logger.warning("deep_invoke[%s]: RAG 验证发现 %d 矛盾", caller, len(verification["conflicts"]))
        except Exception:
            pass

    if result and rag_sources:
        result["_rag_sources"] = rag_sources
        from ..services.clinical_evidence import build_rag_citations
        result["_rag_citations"] = build_rag_citations(hits)
    if verification:
        result = result or {}
        result["_rag_verification"] = verification

    return result


async def _rag_verify(output: dict, fields: list[str]) -> dict:
    """Refine 阶段: RAG 反查验证 LLM 输出的关键字段。

    对每个字段取值，在 RAG 中搜索，检查是否存在矛盾。
    """
    conflicts = []
    for field in fields:
        value = output.get(field, "")
        if not value or not isinstance(value, str):
            continue
        if len(value) < 2:
            continue
        try:
            hits = await _rag_collect(value, "verification", top_k=2)
            # 简单矛盾检测: 若 top hit score < 0.3，标记低置信
            if not hits or all(h["score"] < 0.3 for h in hits):
                conflicts.append({
                    "field": field,
                    "value": value,
                    "confidence": "low",
                    "message": f"{field} '{value}' 在知识库中未找到支持证据",
                })
        except Exception:
            pass
    return {"conflicts": conflicts, "fields_checked": fields}


# ═══════════════════════════════════════════════════════════
# v0.3: DB Agent — LLM 自然语言查询数据库
# ═══════════════════════════════════════════════════════════

_SAFE_TABLES = {"org_staff", "disease_templates", "dept_checklists", "patient_states"}
_FORBIDDEN = {"DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE",
              "GRANT", "REVOKE", "EXEC", "EXECUTE", "--", ";--", "UNION"}


async def _db_agent_query(provider: Any, question: str) -> str | None:
    """DB Agent: LLM 将自然语言转为 SQL → 安全执行 → 返回结果。

    仅允许 SELECT 只读查询。SQL 生成失败不阻断主流程。
    """
    schema_hint = """数据库表:
  org_staff(name,gender,title,department,role,job_number,specialty,phone,shift,is_manager)
  disease_templates(disease_id,name,department)
  dept_checklists(department,item,sort_order)
  patient_states(patient_id,state_json,updated_at)"""

    sql_prompt = (
        f"{schema_hint}\n\n"
        f"将以下自然语言转为 MySQL SELECT 语句，必须返回 JSON 格式 {{\"sql\":\"你的SQL\"}}：\n{question}"
    )

    try:
        result = await safe_llm_invoke(provider, sql_prompt, timeout=10.0, caller="db_agent")
        if not result:
            return None

        sql = ""
        # 提取 SQL: 可能在 response 字段(纯文本) 或 sql 字段
        raw = result.get("response", "") if isinstance(result, dict) else str(result)
        if isinstance(raw, str) and raw.strip():
            sql = raw.strip()

        # 如果 response 是 JSON 字符串 {"sql": "SELECT..."}，解析它
        if not sql.upper().strip().startswith("SELECT") and isinstance(result, dict):
            for key in ["sql", "query", "action"]:
                val = result.get(key, "")
                if isinstance(val, str) and val.upper().strip().startswith("SELECT"):
                    sql = val.strip()
                    break

        # 去掉 markdown 代码块
        for prefix in ["```sql\n", "```sql", "```\n", "```"]:
            if sql.startswith(prefix):
                sql = sql[len(prefix):]
        for suffix in ["\n```", "```"]:
            if sql.endswith(suffix):
                sql = sql[:-len(suffix)]

        sql = sql.strip().strip("`")
        if not sql.upper().strip().startswith("SELECT"):
            return None

        # 安全检查
        upper = sql.upper()
        for keyword in _FORBIDDEN:
            if keyword in upper:
                logger.warning("DB Agent: 危险SQL被拦截: %s", sql[:80])
                return None

        # 执行查询
        from ..routes.state_store import _backend
        if hasattr(_backend, '_conn'):  # SQLite
            conn = _backend._conn()
            try:
                rows = conn.execute(sql).fetchall()
                if rows:
                    lines = [",".join(str(c) for c in row) for row in rows[:10]]
                    return f"查询结果 ({len(rows)}行):\n" + "\n".join(lines)
            finally:
                conn.close()
        elif hasattr(_backend, '_engine'):  # MySQL
            from sqlalchemy import text
            with _backend._engine.connect() as conn:
                rows = conn.execute(text(sql)).fetchall()
            if rows:
                lines = [",".join(str(c) for c in row) for row in rows[:10]]
                return f"查询结果 ({len(rows)}行):\n" + "\n".join(lines)
    except Exception as e:
        logger.debug("DB Agent 查询失败: %s", e)
    return None


# ═══════════════════════════════════════════════
# v0.3: 节点级 CircuitBreaker + 助手联动
# ═══════════════════════════════════════════════

_node_failures: dict[str, int] = {}
_node_cb_lock = threading.Lock()


def record_node_failure(node: str) -> int:
    """记录节点失败，返回累计失败数。"""
    with _node_cb_lock:
        _node_failures[node] = _node_failures.get(node, 0) + 1
        return _node_failures[node]


def reset_node_failures(node: str) -> None:
    with _node_cb_lock:
        _node_failures.pop(node, None)


def get_node_health() -> dict[str, int]:
    """获取所有节点的失败计数。"""
    with _node_cb_lock:
        return dict(_node_failures)


async def ask_assistant(role: str, question: str, patient_id: str = "") -> str | None:
    """图节点内嵌调用助手获取第二意见。失败时返回 None 不阻塞主流程。"""
    try:
        from .assistant import chat
        result = await chat(question, role=role, patient_id=patient_id)
        return result.get("answer", "")[:300]
    except Exception as e:
        logger.debug("ask_assistant[%s]: %s", role, e)
        return None
