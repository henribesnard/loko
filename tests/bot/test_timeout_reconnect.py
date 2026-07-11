"""Tests for R5 — TIMEOUT_EXPIRED at reconnection (spec §9.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from loko.bot.models import BotConfig, BotSession, BotState, JourneyParams


@pytest.fixture
def config_short_timeout(sample_intents):
    """Config with a very short timeout for testing."""
    return BotConfig(
        name="TestBot",
        intents=sample_intents,
        journey=JourneyParams(timeout_inactivite_s=30),
    )


def test_timeout_applied_when_expired(config_short_timeout):
    """Session inactive beyond timeout_inactivite_s triggers TIMEOUT_EXPIRED."""
    from loko.bot.timeout import check_and_apply_timeout

    # Session with last_activity 60s ago (timeout is 30s)
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    session = BotSession(
        bot_id=config_short_timeout.bot_id,
        state=BotState.ATTENTE_DEMANDE,
        last_activity_at=old_time,
    )

    new_session, actions, timed_out = check_and_apply_timeout(
        session, config_short_timeout,
    )

    assert timed_out is True
    assert new_session.state == BotState.TIMEOUT
    assert len(actions) >= 1  # at least EmitTemplate(TIMEOUT) + CloseSession


def test_timeout_not_applied_when_active(config_short_timeout):
    """Session within timeout window is not timed out."""
    from loko.bot.timeout import check_and_apply_timeout

    recent_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    session = BotSession(
        bot_id=config_short_timeout.bot_id,
        state=BotState.ATTENTE_DEMANDE,
        last_activity_at=recent_time,
    )

    new_session, actions, timed_out = check_and_apply_timeout(
        session, config_short_timeout,
    )

    assert timed_out is False
    assert new_session.state == BotState.ATTENTE_DEMANDE
    assert actions == []


def test_timeout_not_applied_on_terminal_state(config_short_timeout):
    """Already-terminal sessions are not timed out again."""
    from loko.bot.timeout import check_and_apply_timeout

    old_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    session = BotSession(
        bot_id=config_short_timeout.bot_id,
        state=BotState.FIN,
        last_activity_at=old_time,
    )

    new_session, actions, timed_out = check_and_apply_timeout(
        session, config_short_timeout,
    )

    assert timed_out is False
    assert new_session.state == BotState.FIN


def test_timeout_determinism(config_short_timeout):
    """Two replays of the same timeout scenario produce the same result."""
    from loko.bot.timeout import check_and_apply_timeout

    old_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    session = BotSession(
        bot_id=config_short_timeout.bot_id,
        state=BotState.ENQUETE_SATISFACTION,
        last_activity_at=old_time,
    )

    s1, a1, t1 = check_and_apply_timeout(session, config_short_timeout)
    s2, a2, t2 = check_and_apply_timeout(session, config_short_timeout)

    assert t1 == t2 == True  # noqa: E712
    assert s1.state == s2.state == BotState.TIMEOUT
    assert len(a1) == len(a2)
    for action1, action2 in zip(a1, a2):
        assert type(action1) == type(action2)
