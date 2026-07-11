"""LOKO Bot — Pure FSM engine.

The engine is a pure function: no I/O, no side effects.
Effects (SetFit, retrieval, LLM, escalation) are injected via protocols.

    new_session, actions = engine.step(session, event, config)

The caller is responsible for executing the actions and feeding results
back as new events.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from loko.bot.models import (
    Action,
    BotConfig,
    BotSession,
    BotState,
    CallEscalation,
    EscalationMotif,
    Turn,
)
from loko.bot.states import (
    TRANSITIONS,
    TRANSVERSE_EVENTS,
    Event,
    EventType,
    TransitionResult,
    on_escalade_done,
)

logger = logging.getLogger(__name__)


def step(
    session: BotSession,
    event: Event,
    config: BotConfig,
) -> TransitionResult:
    """Execute one FSM step.

    Parameters
    ----------
    session : BotSession
        Current session state (immutable — a new copy is returned).
    event : Event
        The event to process.
    config : BotConfig
        Bot configuration (intents, journey params, etc.).

    Returns
    -------
    tuple[BotSession, list[Action]]
        The updated session and the list of actions to execute.
    """
    # Update last activity timestamp
    session = session.model_copy(
        update={"last_activity_at": datetime.now(timezone.utc).isoformat()}
    )

    # --- Transverse exits (active from any state) ---

    # 1. Timeout
    if event.type in TRANSVERSE_EVENTS:
        handler = TRANSVERSE_EVENTS[event.type]
        new_session, actions = handler(session, event, config)
        _log_transition(session.state, new_session.state, event.type, actions)
        return new_session, actions

    # 2. Explicit request for advisor (from user text at any state)
    if event.type == EventType.USER_MESSAGE and _is_escalation_request(
        session, event, config
    ):
        new_session = session.model_copy(update={"state": BotState.ESCALADE})
        actions: list[Action] = [
            CallEscalation(motif=EscalationMotif.DEMANDE_EXPLICITE)
        ]
        _log_transition(session.state, BotState.ESCALADE, event.type, actions)
        return new_session, actions

    # --- Terminal states ---
    if session.state in (
        BotState.FIN,
        BotState.TIMEOUT,
        BotState.CLOTURE_DOUCE,
        BotState.FIN_FERME,
    ):
        logger.debug(
            "Session %s already in terminal state %s", session.session_id, session.state
        )
        return session, []

    # --- Look up transition ---
    key = (session.state, event.type)
    handler = TRANSITIONS.get(key)

    if handler is None:
        logger.warning(
            "No transition for (%s, %s) — ignoring event",
            session.state.value,
            event.type.value,
        )
        return session, []

    new_session, actions = handler(session, event, config)
    _log_transition(session.state, new_session.state, event.type, actions)
    return new_session, actions


def create_session(bot_id: str) -> BotSession:
    """Create a fresh session in ACCUEIL state."""
    return BotSession(bot_id=bot_id)


def start_session(
    session: BotSession,
    config: BotConfig,
) -> TransitionResult:
    """Convenience: emit the START event on a fresh session."""
    return step(session, Event(EventType.START), config)


def handle_escalation_result(
    session: BotSession,
    config: BotConfig,
    temps_attente: int = 4,
) -> TransitionResult:
    """After the escalation provider responds, emit the template and close."""
    event = Event(
        EventType.BUTTON_CLICK,  # reuse — doesn't matter, on_escalade_done ignores
        data={"temps_attente_estime_min": temps_attente},
    )
    return on_escalade_done(session, event, config)


def add_turn_to_session(
    session: BotSession,
    role: str,
    content: str,
    **extra: Any,
) -> BotSession:
    """Append a turn to the session transcript and return updated session."""
    turn = Turn(role=role, content=content, **extra)
    new_transcript = list(session.transcript) + [turn]
    return session.model_copy(update={"transcript": new_transcript})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_escalation_request(
    session: BotSession,
    event: Event,
    config: BotConfig,
) -> bool:
    """Check if the user text is an explicit escalation request.

    In the full system, the SetFit classifier handles this via the
    `demande_conseiller` intent.  At the engine level we only detect it
    when the classifier has already tagged it.  This function is a
    placeholder for pre-classifier keyword detection (optional).
    """
    # The classifier will handle this; at engine level we rely on the
    # classification result returning `demande_conseiller`.
    # This hook exists for future keyword-based shortcut.
    return False


def _log_transition(
    from_state: BotState,
    to_state: BotState,
    event_type: EventType,
    actions: list[Action],
) -> None:
    action_names = [type(a).__name__ for a in actions]
    logger.debug(
        "Transition: %s -[%s]-> %s  actions=%s",
        from_state.value,
        event_type.value,
        to_state.value,
        action_names,
    )
