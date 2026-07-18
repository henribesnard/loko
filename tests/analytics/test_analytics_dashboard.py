"""Tests for the analytics dashboard API endpoints (OBS-2)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from loko.bot.config_store import save_bot_config
from loko.bot.models import BotConfig, Intent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOKO_ADMIN_TOKEN", "test-admin-token-12345")

    import loko.analytics.db as db_mod
    db_mod._connection = None
    db_mod._DB_PATH = None

    from loko.api.bot_public import clear_orchestrators
    clear_orchestrators()

    from loko.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    c = TestClient(app)
    c.headers.update({"Authorization": "Bearer test-admin-token-12345"})
    return c


@pytest.fixture
def bot_id(tmp_path, monkeypatch) -> str:
    """Create a bot config in the temp data dir."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    bid = "test-analytics-bot"
    config = BotConfig(
        bot_id=bid,
        name="Analytics Test Bot",
        account_id="acc1",
        intents=[
            Intent(
                id="help_account",
                label="Aide compte",
                definition="Aide sur les comptes",
                examples=[f"aide compte exemple {i}" for i in range(10)],
            ),
        ],
    )
    save_bot_config(config)
    return bid


def _make_event(
    event_id: str = "ev1",
    ts: str = "2026-07-18T10:00:00.000+00:00",
    account_id: str = "acc1",
    bot_id: str = "test-analytics-bot",
    session_id: str = "sess1",
    event_type: str = "classification",
    **kwargs,
) -> dict:
    return {
        "event_id": event_id,
        "ts": ts,
        "account_id": account_id,
        "bot_id": bot_id,
        "session_id": session_id,
        "turn": kwargs.get("turn"),
        "event_type": event_type,
        "intent_id": kwargs.get("intent_id"),
        "sub_motif_id": kwargs.get("sub_motif_id"),
        "decision": kwargs.get("decision"),
        "score_top1": kwargs.get("score_top1"),
        "score_margin": kwargs.get("score_margin"),
        "latency_ms": kwargs.get("latency_ms"),
        "error_code": kwargs.get("error_code"),
        "channel": kwargs.get("channel"),
        "meta": kwargs.get("meta"),
    }


def _populate_analytics(monkeypatch, tmp_path):
    """Insert sample events into analytics.db."""
    import loko.analytics.db as db_mod
    db_mod._connection = None
    db_mod._DB_PATH = None
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

    from loko.analytics.db import get_analytics_db, insert_events_batch

    get_analytics_db()

    events = [
        _make_event(event_id="s1", event_type="session_start", session_id="sess1"),
        _make_event(event_id="s2", event_type="session_start", session_id="sess2"),
        _make_event(event_id="m1", event_type="message_in"),
        _make_event(event_id="m2", event_type="message_in"),
        _make_event(event_id="m3", event_type="message_in"),
        _make_event(event_id="c1", event_type="classification",
                     intent_id="help_account", score_top1=0.85, score_margin=0.7,
                     latency_ms=25),
        _make_event(event_id="c2", event_type="classification",
                     intent_id="help_account", score_top1=0.90, score_margin=0.8,
                     latency_ms=30),
        _make_event(event_id="esc1", event_type="escalade",
                     intent_id="help_account",
                     meta={"motif": "INSATISFACTION"}),
        _make_event(event_id="fu1", event_type="feedback_up"),
        _make_event(event_id="fd1", event_type="feedback_down"),
        _make_event(event_id="gf1", event_type="garde_fou_inapproprie",
                     meta={"rule_id": "sys_injection_01", "category": "injection"}),
    ]
    insert_events_batch(events)


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


def test_kpi_requires_auth(app, bot_id):
    """Request without auth returns 401."""
    c = TestClient(app)
    resp = c.get(f"/api/bot/{bot_id}/analytics/kpi")
    assert resp.status_code == 401


def test_kpi_ops_access(client, bot_id, tmp_path, monkeypatch):
    """Ops admin token grants access."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/kpi?from=2026-07-18&to=2026-07-19"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


def test_get_kpi(client, bot_id, tmp_path, monkeypatch):
    """KPI endpoint returns correct metrics."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/kpi?from=2026-07-18&to=2026-07-19"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"] == 2
    assert data["messages"] == 3
    assert data["escalations"] == 1
    assert data["feedback_up"] == 1
    assert data["feedback_down"] == 1
    assert data["guardrail_blocks"] == 1


def test_get_kpi_empty_bot(client, bot_id):
    """KPI for a bot with no analytics events returns zeros."""
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/kpi?from=2026-07-18&to=2026-07-19"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"] == 0
    assert data["escalation_rate"] == 0.0


def test_get_intents(client, bot_id, tmp_path, monkeypatch):
    """Intents endpoint returns intent distribution."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/intents?from=2026-07-18&to=2026-07-19"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["intent_id"] == "help_account"
    assert data[0]["count"] == 2


def test_get_latency(client, bot_id, tmp_path, monkeypatch):
    """Latency endpoint returns daily trends."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/latency?from=2026-07-18&to=2026-07-19"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "p50_latency_ms" in data[0]


def test_get_event_breakdown(client, bot_id, tmp_path, monkeypatch):
    """Event breakdown endpoint returns event type distribution."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/events?from=2026-07-18&to=2026-07-19"
    )
    assert resp.status_code == 200
    data = resp.json()
    types = {r["event_type"] for r in data}
    assert "classification" in types
    assert "message_in" in types


def test_get_event_timeseries(client, bot_id, tmp_path, monkeypatch):
    """Event timeseries endpoint returns daily breakdowns."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/events/timeseries"
        "?from=2026-07-18&to=2026-07-19"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "day" in data[0]
    assert "event_type" in data[0]


def test_get_event_timeseries_filter(client, bot_id, tmp_path, monkeypatch):
    """Event timeseries with event_types filter."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/events/timeseries"
        "?from=2026-07-18&to=2026-07-19&event_types=escalade"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["event_type"] == "escalade" for r in data)


def test_get_escalations(client, bot_id, tmp_path, monkeypatch):
    """Escalation analysis returns motif breakdown."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/escalations?from=2026-07-18&to=2026-07-19"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_escalations"] == 1
    assert data["by_motif"][0]["motif"] == "INSATISFACTION"


def test_get_guardrails(client, bot_id, tmp_path, monkeypatch):
    """Guardrail triggers returns rule breakdown."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/guardrails?from=2026-07-18&to=2026-07-19"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["rule_id"] == "sys_injection_01"


def test_get_session_events(client, bot_id, tmp_path, monkeypatch):
    """Session events returns events for a specific session."""
    _populate_analytics(monkeypatch, tmp_path)
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/sessions/sess1"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


def test_get_session_events_empty(client, bot_id):
    """Unknown session returns 200 with empty list."""
    resp = client.get(
        f"/api/bot/{bot_id}/analytics/sessions/nonexistent"
    )
    assert resp.status_code == 200
    assert resp.json() == []
