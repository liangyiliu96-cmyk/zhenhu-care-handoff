"""Production deployment prerequisites regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest


SERVICE_ROOT = Path(__file__).resolve().parent.parent


def test_compose_configures_an_async_mysql_database_url_for_fastapi():
    compose = (SERVICE_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "DATABASE_URL=mysql+asyncmy://" in compose
    assert "STATE_DB_PATH=/var/lib/zhenhu/zhenhu_state.db" in compose
    assert "state_data:/var/lib/zhenhu" in compose
    assert "ALLOW_SQLITE_STATE_STORE=${ALLOW_SQLITE_STATE_STORE:-true}" in compose
    assert "OLLAMA_FALLBACK_ENABLED=${OLLAMA_FALLBACK_ENABLED:-true}" in compose
    assert "OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://host.docker.internal:11434}" in compose
    assert "${REDIS_HOST_PORT:-6379}:6379" in compose


def test_runtime_dependencies_include_the_async_mysql_driver():
    requirements = (SERVICE_ROOT / "requirements.txt").read_text(encoding="utf-8")
    pyproject = (SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "asyncmy" in requirements
    assert "asyncmy" in pyproject


def test_runtime_rejects_the_unimplemented_stateful_graph_mode(monkeypatch):
    from zhenhu.inpatient.agent.config import validate_graph_mode_configuration

    monkeypatch.setenv("GRAPH_MODE", "stateful")

    with pytest.raises(RuntimeError, match="stateful is disabled"):
        validate_graph_mode_configuration()


@pytest.mark.asyncio
async def test_production_disables_the_fixture_workflow_before_state_mutation(monkeypatch):
    from zhenhu.inpatient.routes import admin

    monkeypatch.setenv("APP_ENV", "production")
    patient_key = next(iter(admin.PATIENTS))

    response = await admin.load_fixture_patient(patient_key)

    assert response.error.code == "FIXTURE_ENDPOINT_DISABLED"
