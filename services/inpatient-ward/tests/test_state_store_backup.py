"""SQLite state-store backup regression tests."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


def _load_backup_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "backup_state_store.py"
    spec = importlib.util.spec_from_file_location("backup_state_store", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sqlite_state_store_backup_is_consistent():
    with TemporaryDirectory() as directory:
        source = Path(directory) / "source.db"
        destination = Path(directory) / "backup" / "state.db"
        connection = sqlite3.connect(source)
        try:
            connection.execute("CREATE TABLE patient_states (patient_id TEXT PRIMARY KEY, state_json TEXT)")
            connection.execute("INSERT INTO patient_states VALUES ('patient-1', '{\"phase\": \"monitoring\"}')")
            connection.commit()
        finally:
            connection.close()

        _load_backup_module().backup_sqlite_state_store(source, destination)

        connection = sqlite3.connect(destination)
        try:
            value = connection.execute("SELECT state_json FROM patient_states WHERE patient_id = 'patient-1'").fetchone()[0]
        finally:
            connection.close()
        assert value == '{"phase": "monitoring"}'


def test_sqlite_state_store_restore_requires_explicit_overwrite_and_preserves_versions():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source.db"
        backup = root / "backup" / "state.db"
        restored = root / "restored.db"
        connection = sqlite3.connect(source)
        try:
            connection.execute(
                "CREATE TABLE patient_states (patient_id TEXT PRIMARY KEY, state_json TEXT, state_version INTEGER)"
            )
            connection.execute(
                "INSERT INTO patient_states VALUES ('patient-pending', '{\"pending_review\": {\"review_id\": \"r-1\"}}', 7)"
            )
            connection.commit()
        finally:
            connection.close()

        module = _load_backup_module()
        module.backup_sqlite_state_store(source, backup)
        restored.write_bytes(b"existing-state-store")

        with pytest.raises(FileExistsError):
            module.restore_sqlite_state_store(backup, restored)

        module.restore_sqlite_state_store(backup, restored, replace=True)

        connection = sqlite3.connect(restored)
        try:
            row = connection.execute(
                "SELECT state_json, state_version FROM patient_states WHERE patient_id = 'patient-pending'"
            ).fetchone()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            connection.close()
        assert row == ('{"pending_review": {"review_id": "r-1"}}', 7)
        assert integrity == "ok"
