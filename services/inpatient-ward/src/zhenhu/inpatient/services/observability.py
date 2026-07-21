"""Structured request logging and dependency-free Prometheus HTTP metrics."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

_HTTP_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_LOG_FIELDS = ("request_id", "method", "path", "status_code", "duration_ms")
logger = logging.getLogger("zhenhu.inpatient.http")


class JsonLogFormatter(logging.Formatter):
    """Render log records as one JSON object while retaining normal messages."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in _LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Configure JSON logs by default; LOG_FORMAT=text remains available locally."""
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    if os.environ.get("LOG_FORMAT", "json").lower() == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    else:
        handler.setFormatter(JsonLogFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)


class HTTPMetrics:
    """Keep bounded request counters and latency histograms for /metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str, str]] = Counter()
        self._duration_buckets: Counter[tuple[str, str, str]] = Counter()
        self._duration_count: Counter[tuple[str, str]] = Counter()
        self._duration_sum: defaultdict[tuple[str, str], float] = defaultdict(float)

    def record(self, *, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        request_key = (method, path, str(status_code))
        duration_key = (method, path)
        with self._lock:
            self._requests[request_key] += 1
            self._duration_count[duration_key] += 1
            self._duration_sum[duration_key] += max(0.0, duration_seconds)
            for bucket in _HTTP_DURATION_BUCKETS:
                if duration_seconds <= bucket:
                    self._duration_buckets[(method, path, _bucket_label(bucket))] += 1
            self._duration_buckets[(method, path, "+Inf")] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP zhenhu_http_requests_total HTTP requests by method, route, and response status.",
                "# TYPE zhenhu_http_requests_total counter",
            ]
            for (method, path, status), count in sorted(self._requests.items()):
                lines.append(
                    f'zhenhu_http_requests_total{{method="{_escape(method)}",path="{_escape(path)}",status="{status}"}} {count}'
                )
            lines += [
                "# HELP zhenhu_http_request_duration_seconds HTTP response duration by method and route.",
                "# TYPE zhenhu_http_request_duration_seconds histogram",
            ]
            for method, path in sorted(self._duration_count):
                labels = f'method="{_escape(method)}",path="{_escape(path)}"'
                for bucket in (*(_bucket_label(value) for value in _HTTP_DURATION_BUCKETS), "+Inf"):
                    count = self._duration_buckets[(method, path, bucket)]
                    lines.append(f'zhenhu_http_request_duration_seconds_bucket{{{labels},le="{bucket}"}} {count}')
                lines.append(f'zhenhu_http_request_duration_seconds_count{{{labels}}} {self._duration_count[(method, path)]}')
                lines.append(f'zhenhu_http_request_duration_seconds_sum{{{labels}}} {self._duration_sum[(method, path)]:.6f}')
        return "\n".join(lines) + "\n"


class HTTPObservabilityMiddleware(BaseHTTPMiddleware):
    """Emit one correlated request log and record one low-cardinality metric sample."""

    async def dispatch(self, request: Request, call_next: Callable):
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_seconds = time.perf_counter() - started
            path = _route_label(request)
            http_metrics.record(
                method=request.method,
                path=path,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            logger.info(
                "http_request",
                extra={
                    "request_id": getattr(request.state, "request_id", None),
                    "method": request.method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round(duration_seconds * 1000, 2),
                },
            )


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else "unmatched"


def _bucket_label(value: float) -> str:
    return f"{value:g}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


http_metrics = HTTPMetrics()
