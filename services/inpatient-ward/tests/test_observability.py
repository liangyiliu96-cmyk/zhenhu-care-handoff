"""Structured logging and HTTP metrics regression tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest


def test_http_metrics_export_request_count_and_latency_histogram():
    from zhenhu.inpatient.services.observability import HTTPMetrics

    metrics = HTTPMetrics()
    metrics.record(method="POST", path="/inpatient/{patient_id}/command", status_code=200, duration_seconds=0.04)

    rendered = metrics.render_prometheus()
    assert 'zhenhu_http_requests_total{method="POST",path="/inpatient/{patient_id}/command",status="200"} 1' in rendered
    assert 'zhenhu_http_request_duration_seconds_count{method="POST",path="/inpatient/{patient_id}/command"} 1' in rendered


def test_json_log_formatter_preserves_request_correlation_fields():
    from zhenhu.inpatient.services.observability import JsonLogFormatter

    record = logging.LogRecord("zhenhu.inpatient", logging.INFO, __file__, 1, "http_request", (), None)
    record.request_id = "request-123"
    record.method = "GET"
    record.path = "/health"
    record.status_code = 200
    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["event"] == "http_request"
    assert payload["request_id"] == "request-123"
    assert payload["status_code"] == 200


def test_prometheus_configuration_loads_alert_rules():
    root = Path(__file__).resolve().parent.parent
    prometheus = (root / "monitoring" / "prometheus.yml").read_text(encoding="utf-8")
    alert_rules = (root / "monitoring" / "alerts.yml").read_text(encoding="utf-8")
    alertmanager = (root / "monitoring" / "alertmanager.yml").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "rule_files:" in prometheus
    assert "alerts.yml" in prometheus
    assert "alertmanagers:" in prometheus
    assert "alertmanager:9093" in prometheus
    assert "ZhenhuHighHttpErrorRate" in alert_rules
    assert "ZhenhuHighHttpLatency" in alert_rules
    assert "ZhenhuRagKnowledgeUnavailable" in alert_rules
    assert "ZhenhuStateStoreUnavailable" in alert_rules
    assert "clinical-critical" in alertmanager
    assert "clinical-warning" in alertmanager
    assert "ALERTMANAGER_CRITICAL_WEBHOOK_URL" in alertmanager
    assert "alertmanager:" in compose


@pytest.mark.asyncio
async def test_readiness_and_metrics_include_state_store_health(isolated_state_store, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from zhenhu.inpatient import main
    from zhenhu.inpatient.models import Base
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(main, "async_engine", engine)
    monkeypatch.setattr(main, "async_session_factory", async_sessionmaker(engine, expire_on_commit=False))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        readiness = await client.get("/ready")
        metrics = await client.get("/metrics")

    assert readiness.status_code == 200
    assert readiness.json()["checks"]["state_store"]["backend"] == "sqlite"
    assert 'zhenhu_state_store_up{backend="sqlite"} 1' in metrics.text
    await engine.dispose()
