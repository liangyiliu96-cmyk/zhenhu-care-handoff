"""Agent 节点 metrics 记录——零依赖 Prometheus 风格。"""
import time as _time
from collections import defaultdict

_node_calls = defaultdict(int)
_node_errors = defaultdict(int)
_app_start_time = _time.time()


def record(name: str, error: bool = False):
    _node_calls[name] += 1
    if error:
        _node_errors[name] += 1


def get_metrics() -> str:
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
    lines += [
        "# HELP zhenhu_uptime_seconds 服务运行时间",
        "# TYPE zhenhu_uptime_seconds gauge",
        f"zhenhu_uptime_seconds {_time.time() - _app_start_time:.1f}",
    ]
    return "\n".join(lines) + "\n"
