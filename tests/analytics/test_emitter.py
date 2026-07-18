"""Tests for the analytics emitter (queue, batching, fail-open)."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile

import pytest

from loko.analytics.schema import create_schema


@pytest.fixture()
def analytics_db(tmp_path, monkeypatch):
    """Create a temporary analytics.db and point the module to it."""
    db_path = tmp_path / "analytics.db"
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

    # Reset module-level singletons
    import loko.analytics.db as db_mod
    db_mod._connection = None
    db_mod._DB_PATH = None

    import loko.analytics.emitter as em_mod
    em_mod._emitter = None

    yield db_path

    # Cleanup
    db_mod._connection = None
    db_mod._DB_PATH = None
    em_mod._emitter = None


def _make_event(event_type: str = "session_start", bot_id: str = "bot1") -> dict:
    from loko.analytics.emitter import _generate_ulid
    from datetime import datetime, timezone

    return {
        "event_id": _generate_ulid(),
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "account_id": "acc1",
        "bot_id": bot_id,
        "session_id": "sess1",
        "turn": None,
        "event_type": event_type,
        "intent_id": None,
        "sub_motif_id": None,
        "decision": None,
        "score_top1": None,
        "score_margin": None,
        "latency_ms": None,
        "error_code": None,
        "channel": None,
        "meta": None,
    }


@pytest.mark.asyncio
async def test_emit_basic(analytics_db):
    """Events emitted are flushed to the database."""
    from loko.analytics.emitter import AnalyticsEmitter
    from loko.analytics.db import get_analytics_db

    emitter = AnalyticsEmitter()
    emitter.start()

    for _ in range(5):
        emitter.emit(_make_event())

    # Wait for flush
    await asyncio.sleep(2)
    await emitter.stop()

    conn = get_analytics_db()
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 5


@pytest.mark.asyncio
async def test_emit_batch_flush(analytics_db):
    """100 events trigger a batch flush."""
    from loko.analytics.emitter import AnalyticsEmitter
    from loko.analytics.db import get_analytics_db

    emitter = AnalyticsEmitter()
    emitter.start()

    for i in range(100):
        emitter.emit(_make_event(bot_id=f"bot_{i}"))

    await asyncio.sleep(2)
    await emitter.stop()

    conn = get_analytics_db()
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 100


@pytest.mark.asyncio
async def test_emit_queue_full(analytics_db):
    """When the queue is full, events are dropped and counted."""
    from loko.analytics.emitter import AnalyticsEmitter

    emitter = AnalyticsEmitter()
    # Don't start the writer — queue will fill up
    # Manually set running to True so emit() doesn't short-circuit
    # Actually emit() in the module-level function checks _emitter.is_running,
    # but the AnalyticsEmitter.emit() itself doesn't — it just enqueues.
    for i in range(10_100):
        emitter.emit(_make_event(bot_id=f"bot_{i}"))

    assert emitter.dropped >= 100  # At least 100 dropped (queue max is 10_000)


@pytest.mark.asyncio
async def test_emit_fail_open_readonly_db(analytics_db):
    """If analytics.db is read-only, events are dropped but no exception escapes."""
    from loko.analytics.emitter import AnalyticsEmitter
    from loko.analytics.db import get_analytics_db

    # Initialize DB first
    get_analytics_db()

    # Make it read-only (platform-dependent, skip on Windows)
    import sys
    if sys.platform == "win32":
        pytest.skip("chmod not available on Windows")

    os.chmod(str(analytics_db), 0o444)

    emitter = AnalyticsEmitter()
    emitter.start()

    for _ in range(5):
        emitter.emit(_make_event())

    await asyncio.sleep(2)
    await emitter.stop()

    # Events should have been dropped, not crashed
    assert emitter.dropped >= 5

    # Restore permissions for cleanup
    os.chmod(str(analytics_db), 0o644)


@pytest.mark.asyncio
async def test_emit_public_api(analytics_db):
    """The module-level emit() function works end-to-end."""
    import loko.analytics.emitter as em_mod

    emitter = em_mod.get_emitter()
    emitter.start()

    em_mod.emit(
        "classification",
        account_id="acc1",
        bot_id="bot1",
        session_id="sess1",
        intent_id="help_account",
        score_top1=0.85,
        score_margin=0.15,
        latency_ms=42,
    )

    await asyncio.sleep(2)
    await emitter.stop()

    from loko.analytics.db import get_analytics_db

    conn = get_analytics_db()
    row = conn.execute("SELECT * FROM events WHERE event_type='classification'").fetchone()
    assert row is not None


def test_emit_not_started():
    """Calling emit() before start() silently does nothing."""
    import loko.analytics.emitter as em_mod

    # Reset singleton
    em_mod._emitter = None

    # Should not raise
    em_mod.emit(
        "session_start",
        account_id="acc1",
        bot_id="bot1",
        session_id="sess1",
    )


def test_generate_ulid_uniqueness():
    """ULIDs are unique across rapid calls."""
    from loko.analytics.emitter import _generate_ulid

    ids = {_generate_ulid() for _ in range(1000)}
    assert len(ids) == 1000


def test_generate_ulid_sortable():
    """ULIDs generated later should sort after earlier ones."""
    import time
    from loko.analytics.emitter import _generate_ulid

    a = _generate_ulid()
    time.sleep(0.01)
    b = _generate_ulid()
    # Since they encode timestamp in the first bytes, a < b in most cases
    # (tiny chance of collision in the same millisecond, but 10ms sleep prevents that)
    assert a < b
