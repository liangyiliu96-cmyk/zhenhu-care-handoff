"""存储后端抽象 — 支持 SQLite(现在) / MySQL + Milvus(将来)。

架构约定:
  - 内存 _store dict = 热路径(读写), 后端 = 持久化(write-through + 恢复)
  - 换后端: 改环境变量 STORAGE_BACKEND=sqlite|mysql → 零业务代码改动
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import os
import secrets
import sqlite3
import threading
import time as _time
from copy import deepcopy
from abc import ABC, abstractmethod
from typing import Any

_logger = logging.getLogger("zhenhu.storage")


class StateVersionConflictError(Exception):
    """Raised when a persisted patient state has advanced since it was read."""


# ═══════════════════════════════════════════════════════════
# 抽象存储后端
# ═══════════════════════════════════════════════════════════

class StorageBackend(ABC):
    """存储后端接口。实现此接口可替换底层数据库。"""

    @abstractmethod
    def save(
        self,
        patient_id: str,
        state: dict,
        timestamp: float,
        *,
        expected_version: int | None = None,
    ) -> None:
        """持久化一条患者状态。"""

    @abstractmethod
    def load_all(self, ttl: int) -> dict[str, tuple[float, dict]]:
        """加载所有未过期患者状态 → {patient_id: (timestamp, state)}。"""

    @abstractmethod
    def delete(self, patient_ids: list[str]) -> None:
        """批量删除患者记录。"""

    @abstractmethod
    def stats(self) -> dict:
        """返回存储统计: {rows, file_size_bytes, db_path}。"""

    # ── org/template/checklist 操作（子类可实现以绕过 SQLite 直接访问）──

    def execute_sql(self, sql: str, params: dict | None = None) -> Any:
        """执行原生 SQL 查询。子类覆盖以使用各自的数据库连接。"""
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════
# SQLite 实现(当前生产)
# ═══════════════════════════════════════════════════════════

class SQLiteBackend(StorageBackend):
    """SQLite 持久化后端。文件存储，写时创建。"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_table()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_table(self) -> None:
        conn = self._conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patient_states (
                    patient_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    state_version INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(patient_states)")}
            if "state_version" not in columns:
                conn.execute("ALTER TABLE patient_states ADD COLUMN state_version INTEGER NOT NULL DEFAULT 0")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_updated ON patient_states(updated_at)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS org_staff (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    title TEXT NOT NULL,
                    department TEXT NOT NULL,
                    role TEXT NOT NULL,
                    job_number TEXT UNIQUE,
                    license_number TEXT,
                    specialty TEXT,
                    phone TEXT,
                    shift TEXT DEFAULT '白班',
                    is_manager INTEGER DEFAULT 0,
                    password_hash TEXT DEFAULT ''
                )
            """)
            # 迁移: 已有 org_staff 表但无 password_hash 列 → ALTER
            org_cols = {row[1] for row in conn.execute("PRAGMA table_info(org_staff)")}
            if "password_hash" not in org_cols:
                conn.execute("ALTER TABLE org_staff ADD COLUMN password_hash TEXT DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_org_dept ON org_staff(department)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_org_role ON org_staff(role)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS disease_templates (
                    disease_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    template_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dept_checklists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    department TEXT NOT NULL,
                    item TEXT NOT NULL,
                    sort_order INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_checklist_dept ON dept_checklists(department)")
            conn.commit()
        finally:
            conn.close()

    def save(
        self,
        patient_id: str,
        state: dict,
        timestamp: float,
        *,
        expected_version: int | None = None,
    ) -> None:
        safe = _safe_dict(state)
        state_version = _state_version(safe)
        conn = self._conn()
        try:
            payload = _json.dumps(safe, ensure_ascii=False, default=str)
            if expected_version is None:
                try:
                    conn.execute(
                        "INSERT INTO patient_states (patient_id, state_json, state_version, updated_at) VALUES (?, ?, ?, ?)",
                        (patient_id, payload, state_version, timestamp),
                    )
                except sqlite3.IntegrityError as exc:
                    raise StateVersionConflictError(patient_id) from exc
            else:
                cursor = conn.execute(
                    "UPDATE patient_states SET state_json = ?, state_version = ?, updated_at = ? "
                    "WHERE patient_id = ? AND state_version = ?",
                    (payload, state_version, timestamp, patient_id, expected_version),
                )
                if cursor.rowcount != 1:
                    raise StateVersionConflictError(patient_id)
            conn.commit()
        finally:
            conn.close()

    def load_all(self, ttl: int) -> dict[str, tuple[float, dict]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT patient_id, state_json, state_version, updated_at FROM patient_states"
            ).fetchall()
        finally:
            conn.close()
        result = {}
        now = _time.time()
        for pid, json_str, state_version, ts in rows:
            try:
                state = _json.loads(json_str)
                if _should_retain_state(state, now - ts, ttl):
                    state["state_version"] = state_version
                    result[pid] = (ts, state)
            except (_json.JSONDecodeError, TypeError):
                pass
        return result

    def delete(self, patient_ids: list[str]) -> None:
        if not patient_ids:
            return
        conn = self._conn()
        try:
            conn.executemany(
                "DELETE FROM patient_states WHERE patient_id = ?",
                [(pid,) for pid in patient_ids]
            )
            conn.commit()
        finally:
            conn.close()

    def stats(self) -> dict:
        conn = self._conn()
        try:
            row_count = conn.execute("SELECT COUNT(*) FROM patient_states").fetchone()[0]
        finally:
            conn.close()
        file_size = os.path.getsize(self._db_path) if os.path.exists(self._db_path) else 0
        return {"rows": row_count, "file_size_bytes": file_size, "db_path": self._db_path}

    def execute_sql(self, sql: str, params: dict | None = None) -> Any:
        conn = self._conn()
        try:
            if params:
                return conn.execute(sql, params).fetchall()
            return conn.execute(sql).fetchall()
        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════
# MySQL 实现(将来 — 当 connection pool 就绪后替换)
# ═══════════════════════════════════════════════════════════

class MySQLBackend(StorageBackend):
    """MySQL 持久化后端 — SQLAlchemy + PyMySQL。

    对应数据库: zhenhu_workflow
    环境变量: MYSQL_HOST/PORT/USER/PASSWORD/DATABASE
    迁移时启用: STORAGE_BACKEND=mysql
    """

    def __init__(self):
        import sqlalchemy as sa
        self._sa_text = sa.text  # 类级保存, 所有方法可用

        host = os.environ.get("MYSQL_HOST", "localhost")
        port = os.environ.get("MYSQL_PORT", "3306")
        user = os.environ.get("MYSQL_USER", "zhenhu")
        password = os.environ.get("MYSQL_PASSWORD", "zhenhu123")
        database = os.environ.get("MYSQL_DATABASE", "zhenhu_workflow")

        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
        self._engine = sa.create_engine(
            url, pool_size=10, max_overflow=20, pool_recycle=3600,
            pool_pre_ping=True, echo=False
        )
        self._init_tables()

    def _init_tables(self):
        with self._engine.begin() as conn:
            conn.execute(self._sa_text("""
                CREATE TABLE IF NOT EXISTS patient_states (
                    patient_id VARCHAR(64) PRIMARY KEY,
                    state_json LONGTEXT NOT NULL,
                    state_version BIGINT NOT NULL DEFAULT 0,
                    updated_at DOUBLE NOT NULL,
                    INDEX idx_updated (updated_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            existing_columns = {
                row[0] for row in conn.execute(self._sa_text("SHOW COLUMNS FROM patient_states")).fetchall()
            }
            if "state_version" not in existing_columns:
                conn.execute(self._sa_text(
                    "ALTER TABLE patient_states ADD COLUMN state_version BIGINT NOT NULL DEFAULT 0 AFTER state_json"
                ))
            conn.execute(self._sa_text("""
                CREATE TABLE IF NOT EXISTS org_staff (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(32) NOT NULL,
                    gender VARCHAR(4) NOT NULL,
                    title VARCHAR(32) NOT NULL,
                    department VARCHAR(32) NOT NULL,
                    role VARCHAR(16) NOT NULL,
                    job_number VARCHAR(32) UNIQUE,
                    license_number VARCHAR(32),
                    specialty VARCHAR(64),
                    phone VARCHAR(16),
                    shift VARCHAR(8) DEFAULT '白班',
                    is_manager TINYINT DEFAULT 0,
                    password_hash VARCHAR(128) DEFAULT '',
                    INDEX idx_org_dept (department),
                    INDEX idx_org_role (role)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            # 迁移: 已有 org_staff 但无 password_hash → ALTER
            org_cols = {row[0] for row in conn.execute(self._sa_text("SHOW COLUMNS FROM org_staff")).fetchall()}
            if "password_hash" not in org_cols:
                conn.execute(self._sa_text(
                    "ALTER TABLE org_staff ADD COLUMN password_hash VARCHAR(128) DEFAULT '' AFTER is_manager"
                ))
            conn.execute(self._sa_text("""
                CREATE TABLE IF NOT EXISTS disease_templates (
                    disease_id VARCHAR(64) PRIMARY KEY,
                    name VARCHAR(64) NOT NULL,
                    department VARCHAR(32) NOT NULL,
                    template_json LONGTEXT NOT NULL,
                    updated_at DOUBLE NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.execute(self._sa_text("""
                CREATE TABLE IF NOT EXISTS dept_checklists (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    department VARCHAR(32) NOT NULL,
                    item VARCHAR(256) NOT NULL,
                    sort_order INT DEFAULT 0,
                    INDEX idx_checklist_dept (department)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

    def save(
        self,
        patient_id: str,
        state: dict,
        timestamp: float,
        *,
        expected_version: int | None = None,
    ) -> None:
        safe = _safe_dict(state)
        state_version = _state_version(safe)
        with self._engine.begin() as conn:
            params = {
                "pid": patient_id,
                "json": _json.dumps(safe, ensure_ascii=False, default=str),
                "version": state_version,
                "ts": timestamp,
            }
            if expected_version is None:
                try:
                    conn.execute(
                        self._sa_text(
                            "INSERT INTO patient_states (patient_id, state_json, state_version, updated_at) "
                            "VALUES (:pid, :json, :version, :ts)"
                        ),
                        params,
                    )
                except Exception as exc:
                    if exc.__class__.__name__ == "IntegrityError":
                        raise StateVersionConflictError(patient_id) from exc
                    raise
            else:
                params["expected_version"] = expected_version
                result = conn.execute(
                    self._sa_text(
                        "UPDATE patient_states SET state_json = :json, state_version = :version, updated_at = :ts "
                        "WHERE patient_id = :pid AND state_version = :expected_version"
                    ),
                    params,
                )
                if result.rowcount != 1:
                    raise StateVersionConflictError(patient_id)

    def load_all(self, ttl: int) -> dict[str, tuple[float, dict]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                self._sa_text("SELECT patient_id, state_json, state_version, updated_at FROM patient_states")
            ).fetchall()
        result, now = {}, _time.time()
        for row in rows:
            try:
                state = _json.loads(row[1])
                if _should_retain_state(state, now - row[3], ttl):
                    state["state_version"] = row[2]
                    result[row[0]] = (row[3], state)
            except (_json.JSONDecodeError, TypeError):
                pass
        return result

    def delete(self, patient_ids: list[str]) -> None:
        if not patient_ids:
            return
        from sqlalchemy import bindparam
        statement = self._sa_text(
            "DELETE FROM patient_states WHERE patient_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        with self._engine.begin() as conn:
            conn.execute(statement, {"ids": patient_ids})

    def stats(self) -> dict:
        with self._engine.connect() as conn:
            count = conn.execute(self._sa_text("SELECT COUNT(*) FROM patient_states")).scalar()
        return {"rows": count, "file_size_bytes": 0, "db_path": f"mysql://{self._engine.url.host}/{self._engine.url.database}"}


# ═══════════════════════════════════════════════════════════
# 后端工厂
# ═══════════════════════════════════════════════════════════

def _default_db_path() -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "zhenhu_state.db")
    )


def create_backend() -> StorageBackend:
    """Create the configured backend without an implicit production downgrade."""
    backend = os.environ.get("STORAGE_BACKEND", "sqlite").lower()
    production = os.environ.get("APP_ENV", "dev").lower() == "production"
    allow_sqlite_state_store = os.environ.get("ALLOW_SQLITE_STATE_STORE", "").lower() in {"1", "true", "yes"}
    if production and backend != "mysql" and not allow_sqlite_state_store:
        raise RuntimeError(
            "Production requires STORAGE_BACKEND=mysql unless ALLOW_SQLITE_STATE_STORE=true "
            "is set for a single-instance phased deployment."
        )
    if production and backend == "mysql":
        required_mysql_settings = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
        missing = [name for name in required_mysql_settings if not os.environ.get(name, "").strip()]
        if missing:
            raise RuntimeError(f"Production MySQL storage requires: {', '.join(missing)}")
    if backend == "mysql":
        try:
            return MySQLBackend()
        except Exception as e:
            if production:
                raise
            _logger.warning("MySQL 不可用 (%s)，fallback 到 SQLite", e)
    elif backend != "sqlite":
        raise RuntimeError(f"Unsupported STORAGE_BACKEND: {backend}")
    return SQLiteBackend(os.environ.get("STATE_DB_PATH", _default_db_path()))


def _safe_dict(obj: dict) -> dict:
    """确保 state 值可 JSON 序列化。"""
    clean = {}
    for k, v in obj.items():
        try:
            _json.dumps({k: v}, default=str)
            clean[k] = v
        except (TypeError, ValueError):
            clean[k] = str(v)
    return clean


def _state_version(state: dict[str, Any]) -> int:
    try:
        return int(state.get("state_version", 0))
    except (TypeError, ValueError):
        return 0


def _is_pending_review_state(state: dict[str, Any]) -> bool:
    return isinstance(state.get("pending_review"), dict) and bool(state["pending_review"])


def is_post_discharge_state(state: dict[str, Any]) -> bool:
    phase = str(state.get("phase") or "").lower()
    discharge_status = str(
        state.get("discharge_sign_status") or state.get("discharge_decision") or ""
    ).lower()
    return (
        phase in {"discharge", "confirm", "completed", "closed", "archived"}
        or discharge_status in {"signed", "approved", "completed", "discharged"}
    )


def _get_post_discharge_ttl() -> int:
    """Retain post-discharge coordination state longer than active ward state."""
    try:
        return max(_get_ttl(), int(os.environ.get("POST_DISCHARGE_STATE_TTL_SECONDS", "7776000")))
    except (TypeError, ValueError):
        return max(_get_ttl(), 7776000)


def _should_retain_state(state: dict[str, Any], age_seconds: float, active_ttl: int) -> bool:
    # Demo packs must survive development-server restarts until an explicit reset.
    if state.get("demo_seed") and os.environ.get("APP_ENV", "dev").lower() != "production":
        return True
    if age_seconds <= active_ttl or _is_pending_review_state(state):
        return True
    return is_post_discharge_state(state) and age_seconds <= _get_post_discharge_ttl()


# ═══════════════════════════════════════════════════════════
# 全局后端实例
# ═══════════════════════════════════════════════════════════

_backend: StorageBackend = create_backend()

# ═══════════════════════════════════════════════════════════
# 状态存储公开 API (向后兼容)
# ═══════════════════════════════════════════════════════════

_lock = threading.RLock()
_store: dict[str, tuple[float, dict[str, Any]]] = {}

_cleanup_interval = 300
_stop_cleanup = threading.Event()


def _get_ttl() -> int:
    try:
        from ..agent.config import get_state_ttl
        return get_state_ttl()
    except ImportError:
        return 1800


def _cleanup_expired() -> int:
    with _lock:
        now = _time.time()
        ttl = _get_ttl()
        expired = [
            patient_id
            for patient_id, (ts, state) in _store.items()
            if not _should_retain_state(state, now - ts, ttl)
        ]
        for k in expired:
            del _store[k]
        if expired:
            _logger.info("state_store 清理: 移除 %d 条过期 (TTL=%ds)", len(expired), ttl)
            try:
                _backend.delete(expired)
            except Exception:
                _logger.exception("state_store 后端删除失败")
        return len(expired)


def _cleanup_worker() -> None:
    _logger.info("state_store 清理线程启动 (间隔 %ds)", _cleanup_interval)
    while not _stop_cleanup.wait(_cleanup_interval):
        try:
            _cleanup_expired()
        except Exception:
            _logger.exception("state_store 清理异常")


# 模块加载: 从后端恢复 + 启动清理线程
loaded = _backend.load_all(_get_ttl())
_store.update(loaded)
if loaded:
    _logger.info("state_store: 从后端加载 %d 条状态 (%s)", len(loaded), type(_backend).__name__)
_cleanup_thread = threading.Thread(target=_cleanup_worker, daemon=True, name="state-store-cleanup")
_cleanup_thread.start()


def stop_cleanup_thread() -> None:
    _stop_cleanup.set()


def get_store_size() -> int:
    with _lock:
        return len(_store)


def get_state(patient_id: str) -> dict[str, Any] | None:
    with _lock:
        _cleanup_expired()
        entry = _store.get(patient_id)
        if entry:
            ts, state = entry
            if _should_retain_state(state, _time.time() - ts, _get_ttl()):
                return deepcopy(state)
            del _store[patient_id]
    return None


def list_states() -> dict[str, dict[str, Any]]:
    """Return exactly the states that canonical patient-detail reads can open."""
    with _lock:
        _cleanup_expired()
        return {patient_id: deepcopy(state) for patient_id, (_, state) in _store.items()}


def list_persisted_state_ids() -> list[str]:
    """List every durable patient-state ID, including inactive historical rows."""
    rows = _backend.execute_sql("SELECT patient_id FROM patient_states")
    return [str(row[0]) for row in rows]


def delete_states(patient_ids: list[str]) -> None:
    """Delete explicitly selected state records from hot and durable stores."""
    if not patient_ids:
        return
    with _lock:
        _backend.delete(patient_ids)
        for patient_id in patient_ids:
            _store.pop(patient_id, None)


def _next_state_version(previous: dict[str, Any] | None, incoming: dict[str, Any]) -> int:
    try:
        current_version = int((previous or {}).get("state_version", 0))
    except (TypeError, ValueError):
        current_version = 0
    try:
        requested_version = int(incoming.get("state_version", 0))
    except (TypeError, ValueError):
        requested_version = 0
    return requested_version if requested_version == current_version + 1 else current_version + 1


def set_state(patient_id: str, state: dict[str, Any]) -> None:
    now = _time.time()
    with _lock:
        safe_state = deepcopy(state)
        previous = _store.get(patient_id, (0.0, None))[1]
        safe_state["state_version"] = _next_state_version(previous, safe_state)
        expected_version = _state_version(previous) if previous is not None else None
        try:
            _backend.save(patient_id, safe_state, now, expected_version=expected_version)
        except StateVersionConflictError:
            raise
        except Exception:
            _logger.exception("state_store 持久化失败 patient_id=%s", patient_id)
            if os.environ.get("APP_ENV", "dev").lower() == "production":
                raise
        _store[patient_id] = (now, safe_state)


def update_state(patient_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        _cleanup_expired()
        _, previous = _store.get(patient_id, (_time.time(), {}))
        current = {**deepcopy(previous), **deepcopy(updates)}
        current["state_version"] = _next_state_version(previous, current)
        now = _time.time()
        expected_version = _state_version(previous) if previous else None
        try:
            _backend.save(patient_id, current, now, expected_version=expected_version)
        except StateVersionConflictError:
            raise
        except Exception:
            _logger.exception("state_store 更新持久化失败 patient_id=%s", patient_id)
            if os.environ.get("APP_ENV", "dev").lower() == "production":
                raise
        _store[patient_id] = (now, current)
        return deepcopy(current)


def get_db_stats() -> dict:
    return _backend.stats()


def get_backend_health() -> dict[str, Any]:
    """Probe the configured durable state backend without exposing credentials."""
    stats = _backend.stats()
    backend = "mysql" if isinstance(_backend, MySQLBackend) else "sqlite"
    return {
        "backend": backend,
        "rows": int(stats.get("rows", 0)),
        "file_size_bytes": int(stats.get("file_size_bytes", 0)),
    }


def force_cleanup() -> int:
    return _cleanup_expired()


# ═══════════════════════════════════════════════════════════
# 组织人员 CRUD
# ═══════════════════════════════════════════════════════════

def _get_backend_conn():
    """获取后端连接上下文管理器 (SQLite 或 MySQL)。"""
    if isinstance(_backend, SQLiteBackend):
        return _backend._conn()
    elif isinstance(_backend, MySQLBackend):
        return _backend._engine.begin()
    return None


def _exec_sql(sql: str, params=None, fetch: bool = False):
    """执行 SQL，自动适配后端。"""
    if isinstance(_backend, SQLiteBackend):
        conn = _backend._conn()
        try:
            cursor = conn.execute(sql, params) if params else conn.execute(sql)
            if fetch:
                return cursor.fetchall()
            conn.commit()
        finally:
            conn.close()
    elif isinstance(_backend, MySQLBackend):
        from sqlalchemy import text as sa_text
        with _backend._engine.begin() as conn:
            result = conn.execute(sa_text(sql), params or {})
            if fetch:
                return result.fetchall()
    else:
        return [] if fetch else None

def _hash_password(password: str) -> str:
    """PBKDF2-SHA256 with random salt — no extra dependencies."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its PBKDF2 hash."""
    if not hashed or not hashed.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, salt, expected = hashed.split("$", 2)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return secrets.compare_digest(dk.hex(), expected)
    except (ValueError, IndexError):
        return False


def verify_staff_credentials(job_number: str, password: str) -> dict | None:
    """查询 org_staff 表验证工号和密码。返回身份 dict 或 None。"""
    row = _exec_sql(
        "SELECT name, gender, title, department, role, job_number, license_number, "
        "specialty, phone, shift, is_manager, password_hash "
        "FROM org_staff WHERE job_number = ?",
        (job_number,), fetch=True
    )
    if not row:
        return None
    r = row[0]
    name = r[0] if isinstance(r, tuple) else r.name
    role_val = r[4] if isinstance(r, tuple) else r.role
    title_val = r[2] if isinstance(r, tuple) else r.title
    dept_val = r[3] if isinstance(r, tuple) else r.department
    pwd_hash = r[11] if isinstance(r, tuple) else getattr(r, 'password_hash', '')
    if not _verify_password(password, pwd_hash):
        return None
    return {
        "name": name, "gender": r[1] if isinstance(r, tuple) else r.gender,
        "title": title_val, "department": dept_val, "role": role_val,
        "job_number": job_number,
        "license_number": r[6] if isinstance(r, tuple) else r.license_number,
        "specialty": r[7] if isinstance(r, tuple) else r.specialty,
        "phone": r[8] if isinstance(r, tuple) else r.phone,
        "shift": r[9] if isinstance(r, tuple) else r.shift,
        "is_manager": bool(r[10] if isinstance(r, tuple) else r.is_manager),
    }


def seed_org_from_json(json_path: str | None = None) -> int:
    """从 JSON 配置文件导入人员到 org_staff 表。"""
    import json as _json
    if json_path is None:
        json_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "config", "org_structure.json")
        )
    with open(json_path, "r", encoding="utf-8") as f:
        org = _json.load(f)

    _exec_sql("DELETE FROM org_staff")
    count = 0
    sql = "INSERT INTO org_staff (name,gender,title,department,role,job_number,license_number,specialty,phone,shift,is_manager,password_hash) VALUES (:n,:g,:t,:d,:r,:jn,:ln,:s,:p,:sh,:im,:ph)"
    for dept, staff in org["departments"].items():
        for doc in staff.get("doctors", []):
            jn = doc.get("job_number", "")
            pwd = jn[-4:] if len(jn) >= 4 else jn
            _exec_sql(sql, {"n":doc["name"],"g":doc.get("gender",""),"t":doc["title"],"d":dept,"r":"doctor",
                "jn":jn,"ln":doc.get("license_number",""),"s":doc.get("specialty",""),
                "p":doc.get("phone",""),"sh":doc.get("shift","白班"),"im":1 if "主任" in doc["title"] else 0,
                "ph": _hash_password(pwd)})
            count += 1
        for nur in staff.get("nurses", []):
            jn = nur.get("job_number", "")
            pwd = jn[-4:] if len(jn) >= 4 else jn
            _exec_sql(sql, {"n":nur["name"],"g":nur.get("gender",""),"t":nur["title"],"d":dept,"r":"nurse",
                "jn":jn,"ln":nur.get("license_number",""),"s":nur.get("specialty",""),
                "p":nur.get("phone",""),"sh":nur.get("shift","白班"),"im":1 if "护士长" in nur["title"] else 0,
                "ph": _hash_password(pwd)})
            count += 1
    return count


def get_org_all() -> list[dict]:
    """获取全员列表（含临床相关信息）。"""
    rows = _exec_sql(
        "SELECT name,gender,title,department,role,job_number,license_number,specialty,phone,shift,is_manager "
        "FROM org_staff ORDER BY department, is_manager DESC",
        fetch=True
    ) or []
    # 统一行格式: SQLite返回tuple, MySQL返回Row
    return [{"name": r[0] if isinstance(r, tuple) else r.name, "gender": r[1] if isinstance(r, tuple) else r.gender,
             "title": r[2] if isinstance(r, tuple) else r.title, "department": r[3] if isinstance(r, tuple) else r.department,
             "role": r[4] if isinstance(r, tuple) else r.role, "job_number": r[5] if isinstance(r, tuple) else r.job_number,
             "license_number": r[6] if isinstance(r, tuple) else r.license_number,
             "specialty": r[7] if isinstance(r, tuple) else r.specialty, "phone": r[8] if isinstance(r, tuple) else r.phone,
             "shift": r[9] if isinstance(r, tuple) else r.shift,
             "is_manager": bool(r[10] if isinstance(r, tuple) else r.is_manager)}
            for r in rows]


def get_org_by_department(department: str) -> dict:
    """按科室返回医生/护士分组。"""
    staff = get_org_all()
    doctors = [s for s in staff if s["department"] == department and s["role"] == "doctor"]
    nurses = [s for s in staff if s["department"] == department and s["role"] == "nurse"]
    return {"department": department, "doctors": doctors, "nurses": nurses}


def get_org_summary() -> dict:
    """全院人员统计。"""
    staff = get_org_all()
    depts = set(s["department"] for s in staff)
    return {
        "total_departments": len(depts),
        "total_staff": len(staff),
        "total_doctors": sum(1 for s in staff if s["role"] == "doctor"),
        "total_nurses": sum(1 for s in staff if s["role"] == "nurse"),
    }


# ═══════════════════════════════════════════════════════════
# 病种模板 CRUD
# ═══════════════════════════════════════════════════════════

def seed_templates_from_dir(templates_dir: str | None = None) -> int:
    """从 disease_templates/ 目录导入到 disease_templates 表。"""
    import json as _json, glob as _glob
    if templates_dir is None:
        templates_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "disease_templates")
        )
    count = 0
    for fpath in _glob.glob(os.path.join(templates_dir, "*.json")):
        with open(fpath, "r", encoding="utf-8") as f:
            tpl = _json.load(f)
        did = tpl.get("disease_id", os.path.basename(fpath).replace(".json", ""))
        _exec_sql(
            "REPLACE INTO disease_templates (disease_id,name,department,template_json,updated_at) VALUES (:did,:nm,:dept,:json,:ts)",
            {"did": did, "nm": tpl.get("name", did), "dept": tpl.get("department", ""),
             "json": _json.dumps(tpl, ensure_ascii=False), "ts": _time.time()}
        )
        count += 1
    return count


def get_template(disease_id: str) -> dict | None:
    """从数据库读取病种模板。优先走 DB，fallback 走文件。"""
    rows = _exec_sql(
        "SELECT template_json FROM disease_templates WHERE disease_id=:did",
        {"did": disease_id}, fetch=True
    ) or []
    if rows:
        import json as _json
        return _json.loads(rows[0][0] if isinstance(rows[0], tuple) else rows[0].template_json)
    # fallback: JSON 文件
    tpl_dir = os.path.join(os.path.dirname(__file__), "..", "disease_templates")
    fpath = os.path.join(tpl_dir, f"{disease_id}.json")
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return _json.load(f)
    return None


def list_templates() -> list[dict]:
    """列出所有病种模板。"""
    rows = _exec_sql(
        "SELECT disease_id,name,department,updated_at FROM disease_templates ORDER BY department",
        fetch=True
    ) or []
    return [{"disease_id": r[0] if isinstance(r, tuple) else r.disease_id,
             "name": r[1] if isinstance(r, tuple) else r.name,
             "department": r[2] if isinstance(r, tuple) else r.department,
             "updated_at": r[3] if isinstance(r, tuple) else r.updated_at}
            for r in rows]


# ═══════════════════════════════════════════════════════════
# 科室护理清单 CRUD
# ═══════════════════════════════════════════════════════════

def seed_checklists_from_dict() -> int:
    """从 constants.py 导入到 dept_checklists 表。"""
    from ..agent.constants import DEPT_CHECKLIST
    _exec_sql("DELETE FROM dept_checklists")
    count = 0
    for dept, items in DEPT_CHECKLIST.items():
        for i, item in enumerate(items):
            _exec_sql(
                "INSERT INTO dept_checklists (department,item,sort_order) VALUES (:d,:it,:so)",
                {"d": dept, "it": item, "so": i}
            )
            count += 1
    return count


def get_checklist(department: str) -> list[str]:
    """获取科室护理清单。"""
    rows = _exec_sql(
        "SELECT item FROM dept_checklists WHERE department=:d ORDER BY sort_order",
        {"d": department}, fetch=True
    ) or []
    return [r[0] if isinstance(r, tuple) else r.item for r in rows]
