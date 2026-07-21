"""落库封装 — v1.3 §十二。P1-5: 升级为 SQLite 持久化。

pending_review 状态持久化，解决 state_store TTL 30min 限制。
使用独立 sync sqlite3 连接（与主 async engine 隔离），文件落盘作 fallback。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading

logger = logging.getLogger("zhenhu.inpatient.persistence")


def _raise_retired_side_store() -> None:
    """Prevent reintroducing a second authoritative review-checkpoint store."""
    raise RuntimeError(
        "agent.persistence is retired; pending reviews are stored in the clinical state backend"
    )

# ── P1-5: SQLite 持久化（独立连接，不受 SKIP_BRIDGE 影响）──
_PERSIST_DIR = os.environ.get("PERSIST_DIR", "/tmp/zhenhu_persist")
_DB_PATH = os.path.join(_PERSIST_DIR, "pending_review.db")
_lock = threading.Lock()


def _ensure_db() -> None:
    """确保持久化目录和 SQLite 表存在。"""
    os.makedirs(_PERSIST_DIR, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    """获取持久化 SQLite 连接（线程安全，每次新建避免跨线程冲突）。

    使用 WAL 模式提升并发安全性。
    """
    _ensure_db()
    conn = sqlite3.connect(_DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS pending_review ("
        "  patient_id TEXT PRIMARY KEY,"
        "  content TEXT NOT NULL,"
        "  created_at TEXT NOT NULL"
        ")"
    )
    return conn


# ──────────────────────────────────────────────
# 公开 API（保持 v1.3 签名不变）
# ──────────────────────────────────────────────


def persist_pending_review(patient_id: str, content: dict) -> str:
    """持久化 pending_review 状态 — SQLite 主存储 + 文件 fallback。

    解决 state_store TTL 30min 限制。
    返回持久化路径（文件路径或 DB key）。
    """
    _raise_retired_side_store()
    content_json = json.dumps(content, ensure_ascii=False)
    created_at = _now_iso()

    # 主路径：SQLite
    try:
        with _lock:
            conn = _get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO pending_review (patient_id, content, created_at) VALUES (?, ?, ?)",
                (patient_id, content_json, created_at),
            )
            conn.commit()
            conn.close()
        logger.info("persist_pending_review[db]: patient=%s", patient_id)
        return f"sqlite://{_DB_PATH}#{patient_id}"
    except Exception as e:
        logger.warning("persist_pending_review[db] failed, fallback to file: %s", e)

    # fallback：文件落盘
    path = os.path.join(_PERSIST_DIR, f"{patient_id}_pending_review.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    logger.info("persist_pending_review[file]: patient=%s → %s", patient_id, path)
    return path


def load_pending_review(patient_id: str) -> dict | None:
    """加载持久化的 pending_review — DB 优先，文件 fallback。

    Returns:
        pending_review 内容 dict，不存在则返回 None。
    """
    # 主路径：SQLite
    try:
        _raise_retired_side_store()
        conn = _get_conn()
        row = conn.execute(
            "SELECT content FROM pending_review WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception as e:
        logger.warning("load_pending_review[db] failed, trying file: %s", e)

    # fallback：文件
    path = os.path.join(_PERSIST_DIR, f"{patient_id}_pending_review.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def delete_pending_review(patient_id: str) -> bool:
    """删除持久化的 pending_review（审核完成后清理）— DB 优先，文件同步清理。

    Returns:
        True 表示已删除（或不存在），False 表示删除失败。
    """
    _raise_retired_side_store()
    deleted = False

    # 主路径：SQLite
    try:
        conn = _get_conn()
        conn.execute(
            "DELETE FROM pending_review WHERE patient_id = ?",
            (patient_id,),
        )
        conn.commit()
        deleted = conn.total_changes > 0
        conn.close()
    except Exception as e:
        logger.warning("delete_pending_review[db] failed: %s", e)

    # 同步清理文件 fallback
    path = os.path.join(_PERSIST_DIR, f"{patient_id}_pending_review.json")
    if os.path.exists(path):
        os.remove(path)
        deleted = True

    if deleted:
        logger.debug("delete_pending_review: patient=%s", patient_id)
    return deleted


def _now_iso() -> str:
    """当前 UTC ISO 时间戳。"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
