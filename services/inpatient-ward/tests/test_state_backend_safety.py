"""Production state storage must fail closed instead of silently degrading."""

from __future__ import annotations

import pytest


def test_production_rejects_sqlite_state_backend(monkeypatch):
    from zhenhu.inpatient.routes.state_store import create_backend

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")

    with pytest.raises(RuntimeError, match="STORAGE_BACKEND=mysql"):
        create_backend()


def test_production_allows_explicit_single_instance_sqlite_state_store(monkeypatch):
    from zhenhu.inpatient.routes import state_store

    class SQLiteForPhasedDeployment:
        def __init__(self, path):
            self.path = path

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("ALLOW_SQLITE_STATE_STORE", "true")
    monkeypatch.setenv("STATE_DB_PATH", "/persistent/state.db")
    monkeypatch.setattr(state_store, "SQLiteBackend", SQLiteForPhasedDeployment)

    backend = state_store.create_backend()

    assert backend.path == "/persistent/state.db"


def test_production_requires_explicit_mysql_connection_settings(monkeypatch):
    from zhenhu.inpatient.routes.state_store import create_backend

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STORAGE_BACKEND", "mysql")
    for name in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="MYSQL_HOST"):
        create_backend()


def test_production_does_not_fallback_when_mysql_is_unavailable(monkeypatch):
    from zhenhu.inpatient.routes import state_store

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STORAGE_BACKEND", "mysql")
    monkeypatch.setenv("MYSQL_HOST", "db.example.test")
    monkeypatch.setenv("MYSQL_USER", "zhenhu")
    monkeypatch.setenv("MYSQL_PASSWORD", "not-a-default")
    monkeypatch.setenv("MYSQL_DATABASE", "zhenhu_workflow")

    class UnavailableMySQL:
        def __init__(self):
            raise ConnectionError("database unavailable")

    monkeypatch.setattr(state_store, "MySQLBackend", UnavailableMySQL)

    with pytest.raises(ConnectionError, match="database unavailable"):
        state_store.create_backend()


def test_production_state_write_failure_is_not_silently_ignored(monkeypatch):
    from zhenhu.inpatient.routes import state_store

    class FailingBackend:
        def save(self, patient_id, state, timestamp, *, expected_version=None):
            raise OSError("write failed")

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(state_store, "_backend", FailingBackend())

    with pytest.raises(OSError, match="write failed"):
        state_store.set_state("state-write-failure", {"patient_id": "state-write-failure"})
