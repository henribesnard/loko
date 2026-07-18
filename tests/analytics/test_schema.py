"""Tests for analytics schema creation and constraints."""

import sqlite3

import pytest

from loko.analytics.schema import EVENT_TYPES, create_schema


def _in_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    conn.commit()
    return conn


def test_create_schema_tables():
    """Tables events and daily_rollups are created."""
    conn = _in_memory_db()
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "events" in tables
    assert "daily_rollups" in tables
    conn.close()


def test_create_schema_indexes():
    """Expected indexes exist after schema creation."""
    conn = _in_memory_db()
    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_events_account_ts" in indexes
    assert "idx_events_bot_ts" in indexes
    assert "idx_events_session" in indexes
    assert "idx_events_type_ts" in indexes
    assert "idx_rollups_bot_day" in indexes
    conn.close()


def test_create_schema_idempotent():
    """Calling create_schema twice does not fail."""
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    create_schema(conn)  # second call — should not raise
    conn.commit()
    conn.close()


def test_event_types_closed():
    """EVENT_TYPES is a frozenset with the expected members."""
    assert isinstance(EVENT_TYPES, frozenset)
    assert "session_start" in EVENT_TYPES
    assert "classification" in EVENT_TYPES
    assert "session_end" in EVENT_TYPES
    assert "events_dropped" in EVENT_TYPES
    # Verify it cannot be mutated
    with pytest.raises(AttributeError):
        EVENT_TYPES.add("bogus")  # type: ignore[attr-defined]


def test_events_table_columns():
    """The events table has the expected columns."""
    conn = _in_memory_db()
    info = conn.execute("PRAGMA table_info(events)").fetchall()
    columns = {row[1] for row in info}
    expected = {
        "event_id", "ts", "account_id", "bot_id", "session_id", "turn",
        "event_type", "intent_id", "sub_motif_id", "decision",
        "score_top1", "score_margin", "latency_ms", "error_code",
        "channel", "meta",
    }
    assert expected == columns
    conn.close()
