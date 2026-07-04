"""LOKO Bot — Inactivity timeout check (R5, spec §9.3).

Utility function that checks whether a session has exceeded its inactivity
timeout and, if so, plays the TIMEOUT_EXPIRED event through the pure FSM
engine.  No logic is duplicated outside the FSM — determinism is preserved.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loko.bot.engine import step
from loko.bot.models import Action, BotConfig, BotSession, BotState
from loko.bot.states import Event, EventType


def check_and_apply_timeout(
    session: BotSession,
    config: BotConfig,
) -> tuple[BotSession, list[Action], bool]:
    """Check inactivity timeout and apply TIMEOUT_EXPIRED if exceeded.

    Parameters
    ----------
    session : BotSession
        Current session state.
    config : BotConfig
        Bot configuration (contains journey.timeout_inactivite_s).

    Returns
    -------
    tuple[BotSession, list[Action], bool]
        - Updated session (unchanged if not timed out).
        - Actions produced by the timeout transition (empty if not timed out).
        - True if timeout was applied, False otherwise.
    """
    # Terminal states — nothing to do
    if session.state in (BotState.FIN, BotState.TIMEOUT):
        return session, [], False

    timeout_s = config.journey.timeout_inactivite_s
    now = datetime.now(timezone.utc)

    try:
        last_activity = datetime.fromisoformat(session.last_activity_at)
    except (ValueError, TypeError):
        # Can't parse — don't timeout, let the session proceed
        return session, [], False

    elapsed = (now - last_activity).total_seconds()
    if elapsed <= timeout_s:
        return session, [], False

    # Session has timed out — play through the FSM engine
    event = Event(EventType.TIMEOUT_EXPIRED)
    new_session, actions = step(session, event, config)
    return new_session, actions, True
