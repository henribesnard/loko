"""Tests for Prometheus monitoring metrics (OBS-3)."""

from __future__ import annotations

import pytest

from prometheus_client import CollectorRegistry


# ---------------------------------------------------------------------------
# Isolated registry fixture — each test gets a fresh registry to avoid
# cross-test pollution from the module-level singletons.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_registry(monkeypatch):
    """Replace the shared registry with a fresh one for each test."""
    import loko.monitoring.metrics as m

    fresh = CollectorRegistry()
    monkeypatch.setattr(m, "registry", fresh)

    # Re-create all metrics on the fresh registry
    from prometheus_client import Counter, Histogram, Gauge

    monkeypatch.setattr(
        m, "messages_total",
        Counter("loko_messages_total", "Total messages processed",
                ["bot_id", "status"], registry=fresh),
    )
    monkeypatch.setattr(
        m, "escalations_total",
        Counter("loko_escalations_total", "Total escalations to human",
                ["bot_id", "reason"], registry=fresh),
    )
    monkeypatch.setattr(
        m, "classifications_total",
        Counter("loko_classifications_total", "Total classifications",
                ["bot_id", "level", "decision"], registry=fresh),
    )
    monkeypatch.setattr(
        m, "classification_confidence",
        Histogram("loko_classification_confidence",
                  "Classification confidence scores",
                  ["bot_id", "level"],
                  buckets=[0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0],
                  registry=fresh),
    )
    monkeypatch.setattr(
        m, "step_latency",
        Histogram("loko_step_latency_seconds",
                  "Latency per conversation step", ["step"],
                  buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
                  registry=fresh),
    )
    monkeypatch.setattr(
        m, "message_latency",
        Histogram("loko_message_latency_seconds",
                  "Total message processing latency", ["bot_id"],
                  buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
                  registry=fresh),
    )
    monkeypatch.setattr(
        m, "models_loaded",
        Gauge("loko_models_loaded",
              "Number of ML models currently loaded in memory",
              ["bot_id", "level"], registry=fresh),
    )
    monkeypatch.setattr(
        m, "sessions_active",
        Gauge("loko_sessions_active",
              "Number of active chat sessions",
              ["bot_id"], registry=fresh),
    )
    monkeypatch.setattr(
        m, "errors_total",
        Counter("loko_errors_total", "Total errors by type",
                ["error_type", "bot_id"], registry=fresh),
    )
    monkeypatch.setattr(
        m, "auth_attempts_total",
        Counter("loko_auth_attempts_total",
                "Total authentication attempts",
                ["result"], registry=fresh),
    )


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


def test_record_message_increments_counter():
    """record_message increments the messages_total counter."""
    from loko.monitoring.metrics import record_message, messages_total

    record_message("bot1", "success")
    record_message("bot1", "success")
    record_message("bot1", "error")

    assert messages_total.labels(bot_id="bot1", status="success")._value.get() == 2
    assert messages_total.labels(bot_id="bot1", status="error")._value.get() == 1


def test_record_classification_with_confidence():
    """record_classification increments counter and observes histogram."""
    from loko.monitoring.metrics import (
        record_classification,
        classifications_total,
        classification_confidence,
    )

    record_classification("bot1", "l1", "route", 0.85)
    record_classification("bot1", "l1", "clarify", 0.55)

    assert (
        classifications_total
        .labels(bot_id="bot1", level="l1", decision="route")
        ._value.get() == 1
    )
    assert (
        classifications_total
        .labels(bot_id="bot1", level="l1", decision="clarify")
        ._value.get() == 1
    )
    # Histogram should have 2 observations
    sample = classification_confidence.labels(bot_id="bot1", level="l1")
    assert sample._sum.get() == pytest.approx(0.85 + 0.55, abs=0.001)


def test_record_step_latency():
    """record_step_latency observes the histogram."""
    from loko.monitoring.metrics import record_step_latency, step_latency

    record_step_latency("classification_l1", 0.05)
    record_step_latency("retrieval", 0.2)

    assert step_latency.labels(step="classification_l1")._sum.get() == pytest.approx(0.05)
    assert step_latency.labels(step="retrieval")._sum.get() == pytest.approx(0.2)


def test_record_message_latency():
    """record_message_latency observes the histogram."""
    from loko.monitoring.metrics import record_message_latency, message_latency

    record_message_latency("bot1", 1.5)

    assert message_latency.labels(bot_id="bot1")._sum.get() == pytest.approx(1.5)


def test_record_escalation():
    """record_escalation increments the counter with reason label."""
    from loko.monitoring.metrics import record_escalation, escalations_total

    record_escalation("bot1", "hors_perimetre")
    record_escalation("bot1", "hors_perimetre")
    record_escalation("bot1", "demande_conseiller")

    assert (
        escalations_total
        .labels(bot_id="bot1", reason="hors_perimetre")
        ._value.get() == 2
    )
    assert (
        escalations_total
        .labels(bot_id="bot1", reason="demande_conseiller")
        ._value.get() == 1
    )


def test_record_error():
    """record_error increments error counter with type."""
    from loko.monitoring.metrics import record_error, errors_total

    record_error("classification_error", "bot1")
    record_error("timeout", "bot1")

    assert (
        errors_total
        .labels(error_type="classification_error", bot_id="bot1")
        ._value.get() == 1
    )
    assert (
        errors_total
        .labels(error_type="timeout", bot_id="bot1")
        ._value.get() == 1
    )


def test_record_auth_attempt():
    """record_auth_attempt increments counter with result label."""
    from loko.monitoring.metrics import record_auth_attempt, auth_attempts_total

    record_auth_attempt("success")
    record_auth_attempt("failed")
    record_auth_attempt("failed")
    record_auth_attempt("rate_limited")

    assert auth_attempts_total.labels(result="success")._value.get() == 1
    assert auth_attempts_total.labels(result="failed")._value.get() == 2
    assert auth_attempts_total.labels(result="rate_limited")._value.get() == 1


def test_set_models_loaded():
    """set_models_loaded sets the gauge value."""
    from loko.monitoring.metrics import set_models_loaded, models_loaded

    set_models_loaded("bot1", "l1", 3)

    assert models_loaded.labels(bot_id="bot1", level="l1")._value.get() == 3

    set_models_loaded("bot1", "l1", 0)
    assert models_loaded.labels(bot_id="bot1", level="l1")._value.get() == 0


def test_set_active_sessions():
    """set_active_sessions sets the gauge value."""
    from loko.monitoring.metrics import set_active_sessions, sessions_active

    set_active_sessions("bot1", 42)

    assert sessions_active.labels(bot_id="bot1")._value.get() == 42


def test_get_metrics_returns_prometheus_format():
    """get_metrics returns parseable Prometheus text format."""
    from loko.monitoring.metrics import get_metrics, record_message

    record_message("bot1", "success")
    data = get_metrics()

    assert isinstance(data, bytes)
    text = data.decode("utf-8")
    assert "loko_messages_total" in text
    assert 'bot_id="bot1"' in text


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a fresh FastAPI app for endpoint tests."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOKO_ADMIN_TOKEN", "test-admin-token-12345")

    from loko.api.bot_public import clear_orchestrators
    clear_orchestrators()

    from loko.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_metrics_endpoint_requires_auth(client):
    """GET /metrics without auth returns 401."""
    resp = client.get("/metrics")
    assert resp.status_code == 401


def test_metrics_endpoint_returns_data(client):
    """GET /metrics with admin token returns Prometheus data."""
    resp = client.get(
        "/metrics",
        headers={"Authorization": "Bearer test-admin-token-12345"},
    )
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "loko_messages_total" in resp.text or "loko_" in resp.text
