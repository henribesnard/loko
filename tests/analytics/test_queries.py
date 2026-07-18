"""Tests for analytics query functions (read-only dashboard queries)."""

from __future__ import annotations

import json

import pytest

from loko.analytics.schema import create_schema


@pytest.fixture()
def analytics_db(tmp_path, monkeypatch):
    """Create a temporary analytics.db with schema."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

    import loko.analytics.db as db_mod
    db_mod._connection = None
    db_mod._DB_PATH = None

    db_mod.get_analytics_db()

    yield tmp_path / "analytics.db"

    db_mod._connection = None
    db_mod._DB_PATH = None


def _make_event(
    event_id: str = "ev1",
    ts: str = "2026-07-18T10:00:00.000+00:00",
    account_id: str = "acc1",
    bot_id: str = "bot1",
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


def _insert(events: list[dict]) -> None:
    from loko.analytics.db import insert_events_batch
    insert_events_batch(events)


# ---------------------------------------------------------------------------
# KPI overview
# ---------------------------------------------------------------------------


def test_query_kpi_overview_basic(analytics_db):
    """KPI counts and rates are correct."""
    from loko.analytics.queries import query_kpi_overview

    events = [
        _make_event(event_id="s1", event_type="session_start", session_id="sess1"),
        _make_event(event_id="s2", event_type="session_start", session_id="sess2"),
        _make_event(event_id="s3", event_type="session_start", session_id="sess3"),
        _make_event(event_id="m1", event_type="message_in"),
        _make_event(event_id="m2", event_type="message_in"),
        _make_event(event_id="m3", event_type="message_in"),
        _make_event(event_id="m4", event_type="message_in"),
        _make_event(event_id="m5", event_type="message_in"),
        _make_event(event_id="e1", event_type="escalade"),
        _make_event(event_id="fu", event_type="feedback_up"),
        _make_event(event_id="fd", event_type="feedback_down"),
        _make_event(event_id="er", event_type="error"),
        _make_event(event_id="gf", event_type="garde_fou_inapproprie"),
    ]
    _insert(events)

    result = query_kpi_overview("bot1", "2026-07-18", "2026-07-19")

    assert result["sessions"] == 3
    assert result["messages"] == 5
    assert result["escalations"] == 1
    assert result["escalation_rate"] == pytest.approx(1 / 3)
    assert result["feedbacks"] == 2
    assert result["feedback_up"] == 1
    assert result["feedback_down"] == 1
    assert result["feedback_rate"] == pytest.approx(0.5)
    assert result["errors"] == 1
    assert result["error_rate"] == pytest.approx(0.2)
    assert result["guardrail_blocks"] == 1


def test_query_kpi_overview_empty(analytics_db):
    """No events → all zeros."""
    from loko.analytics.queries import query_kpi_overview

    result = query_kpi_overview("bot1", "2026-07-18", "2026-07-19")
    assert result["sessions"] == 0
    assert result["escalation_rate"] == 0.0
    assert result["feedback_rate"] == 0.0
    assert result["error_rate"] == 0.0


def test_query_kpi_overview_date_filter(analytics_db):
    """Only events within the date range are counted."""
    from loko.analytics.queries import query_kpi_overview

    events = [
        _make_event(event_id="in", ts="2026-07-18T10:00:00.000+00:00",
                     event_type="session_start"),
        _make_event(event_id="out", ts="2026-07-20T10:00:00.000+00:00",
                     event_type="session_start"),
    ]
    _insert(events)

    result = query_kpi_overview("bot1", "2026-07-18", "2026-07-19")
    assert result["sessions"] == 1


# ---------------------------------------------------------------------------
# Intent distribution
# ---------------------------------------------------------------------------


def test_query_intent_distribution(analytics_db):
    """Intents sorted by count with average scores."""
    from loko.analytics.queries import query_intent_distribution

    events = [
        _make_event(event_id="c1", intent_id="help_account",
                     score_top1=0.85, score_margin=0.7),
        _make_event(event_id="c2", intent_id="help_account",
                     score_top1=0.90, score_margin=0.8),
        _make_event(event_id="c3", intent_id="help_billing",
                     score_top1=0.60, score_margin=0.3),
    ]
    _insert(events)

    result = query_intent_distribution("bot1", "2026-07-18", "2026-07-19")
    assert len(result) == 2
    assert result[0]["intent_id"] == "help_account"
    assert result[0]["count"] == 2
    assert result[0]["avg_score_top1"] == pytest.approx(0.875, abs=0.001)
    assert result[1]["intent_id"] == "help_billing"
    assert result[1]["count"] == 1


def test_query_intent_distribution_limit(analytics_db):
    """Limit parameter caps the number of results."""
    from loko.analytics.queries import query_intent_distribution

    events = [
        _make_event(event_id=f"c{i}", intent_id=f"intent_{i}", score_top1=0.5)
        for i in range(10)
    ]
    _insert(events)

    result = query_intent_distribution("bot1", "2026-07-18", "2026-07-19", limit=3)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Latency trends
# ---------------------------------------------------------------------------


def test_query_latency_trends(analytics_db):
    """p50/p95 computed correctly per day."""
    from loko.analytics.queries import query_latency_trends

    events = []
    # Day 1: 10 events with latency 10..19
    for i in range(10):
        events.append(
            _make_event(
                event_id=f"d1_{i}",
                ts=f"2026-07-18T10:{i:02d}:00.000+00:00",
                latency_ms=10 + i,
            )
        )
    # Day 2: 10 events with latency 50..59
    for i in range(10):
        events.append(
            _make_event(
                event_id=f"d2_{i}",
                ts=f"2026-07-19T10:{i:02d}:00.000+00:00",
                latency_ms=50 + i,
            )
        )
    _insert(events)

    result = query_latency_trends("bot1", "2026-07-18", "2026-07-20")
    assert len(result) == 2
    assert result[0]["day"] == "2026-07-18"
    assert result[0]["event_count"] == 10
    assert result[0]["p50_latency_ms"] == 15  # index 5 of [10..19]
    assert result[1]["day"] == "2026-07-19"
    assert result[1]["p50_latency_ms"] == 55  # index 5 of [50..59]


# ---------------------------------------------------------------------------
# Event type breakdown
# ---------------------------------------------------------------------------


def test_query_event_type_breakdown(analytics_db):
    """Correct event type counts."""
    from loko.analytics.queries import query_event_type_breakdown

    events = [
        _make_event(event_id="e1", event_type="classification"),
        _make_event(event_id="e2", event_type="classification"),
        _make_event(event_id="e3", event_type="escalade"),
        _make_event(event_id="e4", event_type="message_in"),
    ]
    _insert(events)

    result = query_event_type_breakdown("bot1", "2026-07-18", "2026-07-19")
    counts = {r["event_type"]: r["count"] for r in result}
    assert counts["classification"] == 2
    assert counts["escalade"] == 1
    assert counts["message_in"] == 1


# ---------------------------------------------------------------------------
# Event type timeseries
# ---------------------------------------------------------------------------


def test_query_event_type_timeseries(analytics_db):
    """Daily event type breakdowns."""
    from loko.analytics.queries import query_event_type_timeseries

    events = [
        _make_event(event_id="e1", ts="2026-07-18T10:00:00.000+00:00",
                     event_type="classification"),
        _make_event(event_id="e2", ts="2026-07-18T11:00:00.000+00:00",
                     event_type="classification"),
        _make_event(event_id="e3", ts="2026-07-18T12:00:00.000+00:00",
                     event_type="escalade"),
        _make_event(event_id="e4", ts="2026-07-19T10:00:00.000+00:00",
                     event_type="classification"),
    ]
    _insert(events)

    result = query_event_type_timeseries("bot1", "2026-07-18", "2026-07-20")
    assert len(result) >= 3  # 2 types on day 1 + 1 type on day 2

    # Filter by event type
    filtered = query_event_type_timeseries(
        "bot1", "2026-07-18", "2026-07-20", event_types=["escalade"]
    )
    assert all(r["event_type"] == "escalade" for r in filtered)


# ---------------------------------------------------------------------------
# Escalation analysis
# ---------------------------------------------------------------------------


def test_query_escalation_analysis(analytics_db):
    """Motif and intent breakdown."""
    from loko.analytics.queries import query_escalation_analysis

    events = [
        _make_event(event_id="esc1", event_type="escalade",
                     intent_id="help_account",
                     meta={"motif": "INSATISFACTION"}),
        _make_event(event_id="esc2", event_type="escalade",
                     intent_id="help_account",
                     meta={"motif": "INSATISFACTION"}),
        _make_event(event_id="esc3", event_type="escalade",
                     intent_id="help_billing",
                     meta={"motif": "COMPLEXITE"}),
    ]
    _insert(events)

    result = query_escalation_analysis("bot1", "2026-07-18", "2026-07-19")
    assert result["total_escalations"] == 3
    assert result["by_motif"][0]["motif"] == "INSATISFACTION"
    assert result["by_motif"][0]["count"] == 2
    assert result["by_motif"][1]["motif"] == "COMPLEXITE"
    assert result["by_motif"][1]["count"] == 1


# ---------------------------------------------------------------------------
# Guardrail triggers
# ---------------------------------------------------------------------------


def test_query_guardrail_triggers(analytics_db):
    """Rule aggregation from meta field."""
    from loko.analytics.queries import query_guardrail_triggers

    events = [
        _make_event(event_id="g1", event_type="garde_fou_inapproprie",
                     meta={"rule_id": "sys_injection_01", "category": "injection"}),
        _make_event(event_id="g2", event_type="garde_fou_inapproprie",
                     meta={"rule_id": "sys_injection_01", "category": "injection"}),
        _make_event(event_id="g3", event_type="garde_fou_inapproprie",
                     meta={"rule_id": "pii_leak_02", "category": "pii"}),
    ]
    _insert(events)

    result = query_guardrail_triggers("bot1", "2026-07-18", "2026-07-19")
    assert len(result) == 2
    assert result[0]["rule_id"] == "sys_injection_01"
    assert result[0]["count"] == 2
    assert result[1]["rule_id"] == "pii_leak_02"
    assert result[1]["count"] == 1


# ---------------------------------------------------------------------------
# Session events
# ---------------------------------------------------------------------------


def test_query_session_events(analytics_db):
    """Events for a specific session, ordered by ts."""
    from loko.analytics.queries import query_session_events

    events = [
        _make_event(event_id="e1", session_id="sess1",
                     ts="2026-07-18T10:00:00.000+00:00",
                     event_type="session_start"),
        _make_event(event_id="e2", session_id="sess1",
                     ts="2026-07-18T10:01:00.000+00:00",
                     event_type="classification", intent_id="help_account"),
        _make_event(event_id="e3", session_id="sess2",
                     ts="2026-07-18T10:00:00.000+00:00",
                     event_type="session_start"),
    ]
    _insert(events)

    result = query_session_events("bot1", "sess1")
    assert len(result) == 2
    assert result[0]["event_type"] == "session_start"
    assert result[1]["intent_id"] == "help_account"


def test_query_session_events_nonexistent(analytics_db):
    """Unknown session returns empty list (not 404)."""
    from loko.analytics.queries import query_session_events

    result = query_session_events("bot1", "nonexistent")
    assert result == []


# ---------------------------------------------------------------------------
# Fail-open
# ---------------------------------------------------------------------------


def test_fail_open_missing_db(tmp_path, monkeypatch):
    """All query functions return empty results when DB is absent."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path / "nonexistent"))

    import loko.analytics.db as db_mod
    db_mod._connection = None
    db_mod._DB_PATH = None

    from loko.analytics.queries import (
        query_kpi_overview,
        query_intent_distribution,
        query_latency_trends,
        query_event_type_breakdown,
        query_event_type_timeseries,
        query_escalation_analysis,
        query_guardrail_triggers,
        query_session_events,
    )

    assert query_kpi_overview("bot1", "2026-07-18", "2026-07-19")["sessions"] == 0
    assert query_intent_distribution("bot1", "2026-07-18", "2026-07-19") == []
    assert query_latency_trends("bot1", "2026-07-18", "2026-07-19") == []
    assert query_event_type_breakdown("bot1", "2026-07-18", "2026-07-19") == []
    assert query_event_type_timeseries("bot1", "2026-07-18", "2026-07-19") == []
    result = query_escalation_analysis("bot1", "2026-07-18", "2026-07-19")
    assert result["total_escalations"] == 0
    assert query_guardrail_triggers("bot1", "2026-07-18", "2026-07-19") == []
    assert query_session_events("bot1", "sess1") == []

    db_mod._connection = None
    db_mod._DB_PATH = None
