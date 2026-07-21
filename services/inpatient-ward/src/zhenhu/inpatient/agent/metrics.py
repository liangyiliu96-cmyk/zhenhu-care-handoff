"""Agent 节点 metrics 记录——零依赖 Prometheus 风格。"""
import threading
import time as _time
from collections import defaultdict

_lock = threading.Lock()

_node_calls = defaultdict(int)
_node_errors = defaultdict(int)
_app_start_time = _time.time()

# Turn 级指标
_turn_total = 0
_turn_success = 0
_turn_failed = 0
_turn_latency_ms = 0.0
_patient_cleanups = 0

# LLM 调用指标
_llm_calls = 0
_llm_errors = 0
_llm_cache_hits = 0


def record(name: str, error: bool = False):
    with _lock:
        _node_calls[name] += 1
        if error:
            _node_errors[name] += 1


def record_llm_call(success: bool, cached: bool = False):
    with _lock:
        global _llm_calls, _llm_errors, _llm_cache_hits
        _llm_calls += 1
        if not success:
            _llm_errors += 1
        if cached:
            _llm_cache_hits += 1


def record_turn(success: bool, latency_s: float):
    with _lock:
        global _turn_total, _turn_success, _turn_failed, _turn_latency_ms
        _turn_total += 1
        if success:
            _turn_success += 1
        else:
            _turn_failed += 1
        _turn_latency_ms += latency_s * 1000


def record_cleanup():
    global _patient_cleanups
    with _lock:
        _patient_cleanups += 1


def get_metrics() -> str:
    with _lock:
        lines = [
            "# HELP zhenhu_node_calls_total Agent节点调用总次数",
            "# TYPE zhenhu_node_calls_total counter",
        ]
        for node, count in sorted(_node_calls.items()):
            lines.append(f'zhenhu_node_calls_total{{node="{node}"}} {count}')
        lines += [
            "# HELP zhenhu_node_errors_total Agent节点错误次数",
            "# TYPE zhenhu_node_errors_total counter",
        ]
        for node, count in sorted(_node_errors.items()):
            lines.append(f'zhenhu_node_errors_total{{node="{node}"}} {count}')

        # Turn 级指标
        if _turn_total > 0:
            avg_lat = _turn_latency_ms / _turn_total
            lines += [
                "# HELP zhenhu_turn_total Agent turn 总次数",
                "# TYPE zhenhu_turn_total counter",
                f"zhenhu_turn_total {_turn_total}",
                "# HELP zhenhu_turn_success_total 成功 turn 次数",
                "# TYPE zhenhu_turn_success_total counter",
                f"zhenhu_turn_success_total {_turn_success}",
                "# HELP zhenhu_turn_failed_total 失败 turn 次数",
                "# TYPE zhenhu_turn_failed_total counter",
                f"zhenhu_turn_failed_total {_turn_failed}",
                "# HELP zhenhu_turn_avg_latency_ms 平均 turn 延迟(ms)",
                "# TYPE zhenhu_turn_avg_latency_ms gauge",
                f"zhenhu_turn_avg_latency_ms {avg_lat:.1f}",
            ]

        lines += [
            f"# HELP zhenhu_patient_cleanups_total 患者出院清理次数",
            f"# TYPE zhenhu_patient_cleanups_total counter",
            f"zhenhu_patient_cleanups_total {_patient_cleanups}",
            f"# HELP zhenhu_llm_calls_total LLM 调用总次数",
            f"# TYPE zhenhu_llm_calls_total counter",
            f"zhenhu_llm_calls_total {_llm_calls}",
            f"# HELP zhenhu_llm_errors_total LLM 调用错误次数",
            f"# TYPE zhenhu_llm_errors_total counter",
            f"zhenhu_llm_errors_total {_llm_errors}",
            f"# HELP zhenhu_llm_cache_hits_total LLM 缓存命中次数",
            f"# TYPE zhenhu_llm_cache_hits_total counter",
            f"zhenhu_llm_cache_hits_total {_llm_cache_hits}",
            "# HELP zhenhu_rag_documents RAG 知识库文档数",
            "# TYPE zhenhu_rag_documents gauge",
        ]
        try:
            from .rag_engine import _c, LAYERS, collection_row_count, rag_runtime_status
            c = _c()
            for layer, cn in LAYERS.items():
                try:
                    if c.has_collection(cn):
                        n = collection_row_count(cn)
                        lines.append(f'zhenhu_rag_documents{{layer="{layer}"}} {n}')
                except: pass
            runtime = rag_runtime_status()
            cache = runtime["cache"]
            lines += [
                "# HELP zhenhu_rag_cache_hits_total RAG distributed and process cache hits.",
                "# TYPE zhenhu_rag_cache_hits_total counter",
                f"zhenhu_rag_cache_hits_total {runtime['process_cache']['search_hits'] + runtime['process_cache']['embedding_hits']}",
                "# HELP zhenhu_runtime_cache_up Redis runtime cache availability; zero means local fallback.",
                "# TYPE zhenhu_runtime_cache_up gauge",
                f"zhenhu_runtime_cache_up {1 if cache['available'] else 0}",
                "# HELP zhenhu_runtime_cache_operations_total Runtime cache operations by outcome.",
                "# TYPE zhenhu_runtime_cache_operations_total counter",
                f'zhenhu_runtime_cache_operations_total{{outcome="hit"}} {cache["hits"]}',
                f'zhenhu_runtime_cache_operations_total{{outcome="miss"}} {cache["misses"]}',
                f'zhenhu_runtime_cache_operations_total{{outcome="write"}} {cache["writes"]}',
                f'zhenhu_runtime_cache_operations_total{{outcome="error"}} {cache["errors"]}',
            ]
        except: pass

        # v0.3: 节点级健康指标
        try:
            from .llm_utils import get_node_health
            for node, count in get_node_health().items():
                lines.append(f'zhenhu_node_failures_total{{node="{node}"}} {count}')
        except: pass

        lines += [
            "# HELP zhenhu_uptime_seconds 服务运行时间",
            "# TYPE zhenhu_uptime_seconds gauge",
            f"zhenhu_uptime_seconds {_time.time() - _app_start_time:.1f}",
        ]
        return "\n".join(lines) + "\n"
