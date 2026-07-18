"""Tests for analytics database layer (insert, purge, rollups)."""

from __future__ import annotations

import sqlite3

import pytest

from loko.analytics.schema import create_schema


@pytest.fixture()
def analytics_db(tmp_path, monkeypatch):
    """Create a temporary analytics.db."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

    import loko.analytics.db as db_mod
    db_mod._connection = None
    db_mod._DB_PATH = None

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
        "turn": None,
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


def test_insert_events_batch(analytics_db):
    """Batch insert writes events to DB."""
    from loko.analytics.db import get_analytics_db, insert_events_batch

    get_analytics_db()  # initialize schema

    events = [_make_event(event_id=f"ev{i}") for i in range(10)]
    count = insert_events_batch(events)

    assert count == 10

    conn = get_analytics_db()
    stored = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert stored == 10


def test_insert_events_batch_empty(analytics_db):
    """Empty batch returns 0 and does not fail."""
    from loko.analytics.db import get_analytics_db, insert_events_batch

    get_analytics_db()
    assert insert_events_batch([]) == 0


def test_insert_events_duplicate_ignored(analytics_db):
    """Duplicate event_id is silently ignored (INSERT OR IGNORE)."""
    from loko.analytics.db import get_analytics_db, insert_events_batch

    get_analytics_db()

    event = _make_event(event_id="dup1")
    insert_events_batch([event])
    insert_events_batch([event])  # duplicate

    conn = get_analytics_db()
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 1


def test_purge_events(analytics_db):
    """Purge deletes events before cutoff timestamp."""
    from loko.analytics.db import get_analytics_db, insert_events_batch, purge_events

    get_analytics_db()

    events = [
        _make_event(event_id="old", ts="2026-01-01T00:00:00.000+00:00"),
        _make_event(event_id="new", ts="2026-07-18T10:00:00.000+00:00"),
    ]
    insert_events_batch(events)

    deleted = purge_events("2026-07-01T00:00:00.000+00:00")
    assert deleted == 1

    conn = get_analytics_db()
    remaining = conn.execute("SELECT event_id FROM events").fetchone()
    assert remaining[0] == "new"


def test_compute_daily_rollups(analytics_db):
    """Rollups aggregate correctly for a given day."""
    from loko.analytics.db import (
        get_analytics_db,
        insert_events_batch,
        compute_daily_rollups,
    )

    get_analytics_db()

    day = "2026-07-18"
    events = [
        _make_event(
            event_id=f"ev{i}",
            ts=f"{day}T10:{i:02d}:00.000+00:00",
            event_type="classification",
            intent_id="help_account",
            latency_ms=20 + i,
        )
        for i in range(10)
    ]
    insert_events_batch(events)

    count = compute_daily_rollups(day)
    assert count >= 1

    conn = get_analytics_db()
    row = conn.execute(
        "SELECT count, p50_latency, p95_latency FROM daily_rollups "
        "WHERE day = ? AND event_type = 'classification'",
        (day,),
    ).fetchone()
    assert row is not None
    assert row[0] == 10  # count
    assert row[1] is not None  # p50
    assert row[2] is not None  # p95


def test_compute_daily_rollups_idempotent(analytics_db):
    """Re-computing rollups for the same day replaces, not duplicates."""
    from loko.analytics.db import (
        get_analytics_db,
        insert_events_batch,
        compute_daily_rollups,
    )

    get_analytics_db()

    day = "2026-07-18"
    events = [
        _make_event(event_id="ev1", ts=f"{day}T10:00:00.000+00:00"),
    ]
    insert_events_batch(events)

    compute_daily_rollups(day)
    compute_daily_rollups(day)  # second call — idempotent

    conn = get_analytics_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM daily_rollups WHERE day = ?", (day,)
    ).fetchone()[0]
    assert count == 1
