"""Tests for R4 — session lock purge."""

from __future__ import annotations

import asyncio

import pytest


def test_purge_removes_orphan_locks(monkeypatch):
    """Locks for sessions not in the active set are removed."""
    monkeypatch.setenv("LOKO_ENV", "test")

    from loko.api.bot_public import _SESSION_LOCKS, purge_session_locks

    _SESSION_LOCKS.clear()
    _SESSION_LOCKS["session-a"] = asyncio.Lock()
    _SESSION_LOCKS["session-b"] = asyncio.Lock()
    _SESSION_LOCKS["session-c"] = asyncio.Lock()

    # Only session-a is still active
    removed = purge_session_locks(active_session_ids={"session-a"})

    assert removed == 2
    assert "session-a" in _SESSION_LOCKS
    assert "session-b" not in _SESSION_LOCKS
    assert "session-c" not in _SESSION_LOCKS

    _SESSION_LOCKS.clear()


def test_purge_keeps_locked_entries(monkeypatch):
    """Locks that are currently held must not be removed."""
    monkeypatch.setenv("LOKO_ENV", "test")

    from loko.api.bot_public import _SESSION_LOCKS, purge_session_locks

    _SESSION_LOCKS.clear()
    lock = asyncio.Lock()
    _SESSION_LOCKS["locked-session"] = lock

    # Simulate a locked state (we can't actually acquire in sync context,
    # but we can set the internal state)
    lock._locked = True  # noqa: SLF001

    removed = purge_session_locks(active_session_ids=set())
    assert removed == 0
    assert "locked-session" in _SESSION_LOCKS

    _SESSION_LOCKS.clear()


def test_purge_respects_max_size(monkeypatch):
    """When over the max limit, unlocked entries are evicted."""
    monkeypatch.setenv("LOKO_ENV", "test")

    import loko.api.bot_public as bp

    bp._SESSION_LOCKS.clear()
    original_max = bp._SESSION_LOCKS_MAX
    bp._SESSION_LOCKS_MAX = 3  # temporarily lower the limit

    try:
        for i in range(5):
            bp._SESSION_LOCKS[f"s-{i}"] = asyncio.Lock()

        removed = bp.purge_session_locks(active_session_ids=set(bp._SESSION_LOCKS.keys()))
        # Should have evicted at least 2 to get from 5 to 3
        assert removed >= 2
        assert len(bp._SESSION_LOCKS) <= 3
    finally:
        bp._SESSION_LOCKS_MAX = original_max
        bp._SESSION_LOCKS.clear()
