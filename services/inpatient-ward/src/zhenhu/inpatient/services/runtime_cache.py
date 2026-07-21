"""Redis-backed runtime cache with a bounded in-process fallback.

Clinical source-of-truth data must never depend on this cache.  It is used for
derived, read-only work such as embeddings, RAG retrieval and public/general
assistant answers.  A Redis outage therefore degrades latency, not workflow
correctness.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger("zhenhu.runtime_cache")


class RuntimeCache:
    def __init__(self) -> None:
        self._client: Any | None | bool = False
        self._redis_lock = threading.Lock()
        self._next_redis_retry_at = 0.0
        self._redis_retry_seconds = max(1.0, float(os.environ.get("REDIS_RETRY_SECONDS", "5")))
        self._memory: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()
        self._max_memory_entries = max(64, int(os.environ.get("RUNTIME_CACHE_MEMORY_ENTRIES", "512")))
        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._errors = 0

    def get_json(self, key: str) -> Any | None:
        raw = self.get_text(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            self.delete(key)
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.set_text(key, json.dumps(value, ensure_ascii=False, separators=(",", ":")), ttl_seconds)

    def get_text(self, key: str) -> str | None:
        client = self._redis()
        if client is not None:
            try:
                value = client.get(key)
                self._record(hit=value is not None)
                return str(value) if value is not None else None
            except Exception as exc:
                self._mark_redis_error(exc)
        return self._memory_get(key)

    def set_text(self, key: str, value: str, ttl_seconds: int) -> None:
        ttl_seconds = max(1, int(ttl_seconds))
        client = self._redis()
        if client is not None:
            try:
                client.set(key, value, ex=ttl_seconds)
                self._record(write=True)
                return
            except Exception as exc:
                self._mark_redis_error(exc)
        with self._lock:
            self._memory[key] = (time.time() + ttl_seconds, value)
            self._memory.move_to_end(key)
            while len(self._memory) > self._max_memory_entries:
                self._memory.popitem(last=False)
            self._writes += 1

    def delete(self, key: str) -> None:
        client = self._redis()
        if client is not None:
            try:
                client.delete(key)
            except Exception as exc:
                self._mark_redis_error(exc)
        with self._lock:
            self._memory.pop(key, None)

    def increment(self, key: str) -> int:
        client = self._redis()
        if client is not None:
            try:
                return int(client.incr(key))
            except Exception as exc:
                self._mark_redis_error(exc)
        with self._lock:
            current = int(self._memory_get_unlocked(key) or "0") + 1
            self._memory[key] = (time.time() + 31_536_000, str(current))
            return current

    def status(self) -> dict[str, Any]:
        client = self._redis()
        with self._lock:
            return {
                "backend": "redis" if client is not None else "memory",
                "available": client is not None,
                "memory_entries": len(self._memory),
                "hits": self._hits,
                "misses": self._misses,
                "writes": self._writes,
                "errors": self._errors,
            }

    def redis_client(self) -> Any | None:
        """Expose the optional client for TTL/session primitives not suited to JSON caching."""
        return self._redis()

    def _redis(self) -> Any | None:
        if os.environ.get("RUNTIME_CACHE_DISABLE", "").lower() in {"1", "true", "yes"}:
            return None
        if self._client not in {False, None}:
            return self._client
        if self._client is None and time.monotonic() < self._next_redis_retry_at:
            return None

        with self._redis_lock:
            if self._client not in {False, None}:
                return self._client
            if self._client is None and time.monotonic() < self._next_redis_retry_at:
                return None
            try:
                import redis

                url = os.environ.get("REDIS_URL") or (
                    f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:{os.environ.get('REDIS_PORT', '6379')}/0"
                )
                client = redis.Redis.from_url(url, socket_connect_timeout=0.3, socket_timeout=0.5, decode_responses=True)
                client.ping()
                self._client = client
                self._next_redis_retry_at = 0.0
                logger.info("Runtime cache connected to Redis")
                return client
            except Exception as exc:
                self._client = None
                self._next_redis_retry_at = time.monotonic() + self._redis_retry_seconds
                logger.info("Runtime cache using local fallback; retrying Redis in %.1fs: %s", self._redis_retry_seconds, exc.__class__.__name__)
                return None

    def _memory_get(self, key: str) -> str | None:
        with self._lock:
            value = self._memory_get_unlocked(key)
            self._record(hit=value is not None)
            return value

    def _memory_get_unlocked(self, key: str) -> str | None:
        entry = self._memory.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.time():
            self._memory.pop(key, None)
            return None
        self._memory.move_to_end(key)
        return value

    def _record(self, *, hit: bool = False, write: bool = False) -> None:
        if hit:
            self._hits += 1
        elif not write:
            self._misses += 1
        if write:
            self._writes += 1

    def _mark_redis_error(self, exc: Exception) -> None:
        with self._lock:
            self._errors += 1
        with self._redis_lock:
            self._client = None
            self._next_redis_retry_at = time.monotonic() + self._redis_retry_seconds
        logger.warning("Runtime cache Redis request failed, using local fallback: %s", exc.__class__.__name__)


_runtime_cache = RuntimeCache()


def get_runtime_cache() -> RuntimeCache:
    return _runtime_cache
