"""LOKO Bot — Declarative FSM states and transition table.

The transition table maps (current_state, event_type) pairs to handler
functions.  Each handler receives the session, event data and bot config,
and returns (new_session, list[Action]).

The engine (engine.py) simply looks up the transition and calls it.
No scattered if/else — every path is explicit and testable.
"""

from __future__ import annotations

import enum
from typing import Any

from loko.bot.models import (
    Action,
    BotConfig,
    BotSession,
    BotState,
    CallEscalation,
    CloseSession,
    EmitGeneration,
    EmitTemplate,
    EscalationMotif,
    TemplateKey,
)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventType(str, enum.Enum):
    """Events that can trigger state transitions."""
    # External (from user / system)
    START = "start"                          # session created
    USER_MESSAGE = "user_message"            # free text input
    BUTTON_CLICK = "button_click"            # user clicked a choice button
    TIMEOUT_EXPIRED = "timeout_expired"      # inactivity timer

    # Internal (from engine sub-steps)
    CLASSIFICATION_L1_DONE = "classification_l1_done"
    CLASSIFICATION_L2_DONE = "classification_l2_done"
    RETRIEVAL_GENERATION_DONE = "retrieval_generation_done"


class Event:
    """Wrapper for an event with optional data payload."""
    __slots__ = ("type", "data")

    def __init__(self, event_type: EventType, data: dict[str, Any] | None = None):
        self.type = event_type
        self.data = data or {}


# ---------------------------------------------------------------------------
# Transition result helper
# ---------------------------------------------------------------------------

TransitionResult = tuple[BotSession, list[Action]]


def _update(session: BotSession, **kwargs: Any) -> BotSession:
    """Return a copy of *session* with updated fields."""
    return session.model_copy(update=kwargs)


# ---------------------------------------------------------------------------
# Transition handlers
# ---------------------------------------------------------------------------

def on_start(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """ACCUEIL -> ATTENTE_DEMANDE: emit welcome template."""
    intent_labels = ", ".join(
        i.label for i in config.intents if not i.is_system
    )
    new = _update(session, state=BotState.ATTENTE_DEMANDE)
    actions: list[Action] = [
        EmitTemplate(
            key=TemplateKey.PRESENTATION,
            variables={
                "nom_bot": config.name,
                "intentions_gerees": intent_labels,
            },
        ),
    ]
    return new, actions


def on_user_message_attente(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """ATTENTE_DEMANDE -> CLASSIFICATION_L1: user typed first/next query."""
    text = event.data.get("text", "")
    new = _update(
        session,
        state=BotState.CLASSIFICATION_L1,
        original_query=text,
        current_intent=None,
        current_sub_motif=None,
        clarifications_count_current_demande=0,
        reformulation_count_current_demande=0,
    )
    return new, []  # engine will call classifier next


def on_classification_l1_done(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """Handle L1 classification result — route based on scores & thresholds."""
    scores: list[tuple[str, float]] = event.data.get("scores", [])
    journey = config.journey

    if not scores:
        return _handle_hors_perimetre(session, config)

    best_id, best_score = scores[0]

    # Transverse exit: demande_conseiller (any score)
    if best_id == "demande_conseiller":
        new = _update(session, state=BotState.ESCALADE)
        return new, [CallEscalation(motif=EscalationMotif.DEMANDE_EXPLICITE)]

    # hors_perimetre class → out-of-scope handling (any score)
    if best_id == "hors_perimetre":
        return _handle_hors_perimetre(session, config)

    # Low confidence → out-of-scope
    if best_score < journey.seuil_bas:
        return _handle_hors_perimetre(session, config)

    # High confidence
    if best_score >= journey.seuil_haut:
        return _route_after_l1(session, config, best_id)

    # Medium confidence — clarification between top 2
    if len(scores) >= 2:
        if session.clarifications_count_current_demande >= journey.max_clarifications:
            # Max clarifications reached, take the best
            return _route_after_l1(session, config, best_id)

        second_id, _ = scores[1]
        # Find labels
        intent_map = {i.id: i.label for i in config.intents}
        options = [intent_map.get(best_id, best_id), intent_map.get(second_id, second_id)]
        candidates = [(best_id, best_score), (second_id, scores[1][1])]

        new = _update(
            session,
            state=BotState.CLARIFICATION_INTER,
            pending_candidates=candidates,
            clarifications_count_current_demande=(
                session.clarifications_count_current_demande + 1
            ),
        )
        return new, [
            EmitTemplate(
                key=TemplateKey.CLARIFICATION_INTER,
                variables={"options": ", ".join(options)},
                buttons=options,
            ),
        ]

    # Single score in medium range — take it
    return _route_after_l1(session, config, best_id)


def _handle_hors_perimetre(
    session: BotSession, config: BotConfig,
) -> TransitionResult:
    """Handle out-of-scope: allow 1 reformulation, then escalade."""
    if session.reformulation_count_current_demande == 0:
        new = _update(
            session,
            state=BotState.ATTENTE_DEMANDE,
            reformulation_count_current_demande=1,
        )
        return new, [EmitTemplate(key=TemplateKey.HORS_PERIMETRE)]
    # Second failure
    new = _update(session, state=BotState.ESCALADE)
    return new, [CallEscalation(motif=EscalationMotif.HORS_PERIMETRE)]


def _route_after_l1(
    session: BotSession, config: BotConfig, intent_id: str,
) -> TransitionResult:
    """After L1 is resolved: go to L2 if sub-motifs exist, else retrieval."""
    intent = next((i for i in config.intents if i.id == intent_id), None)
    new = _update(session, current_intent=intent_id)

    if intent and intent.sub_motifs:
        new = _update(new, state=BotState.CLASSIFICATION_L2)
        return new, []  # engine will call classifier L2
    else:
        new = _update(new, state=BotState.RETRIEVAL_GENERATION)
        return new, [
            EmitGeneration(
                query=session.original_query or "",
                intent=intent_id,
            ),
        ]


def on_clarification_inter_button(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """CLARIFICATION_INTER: user clicked a choice button."""
    selected_label = event.data.get("button", "")
    # Find intent id from label
    intent_map = {i.label: i.id for i in config.intents}
    intent_id = intent_map.get(selected_label)

    if not intent_id:
        # If label doesn't match, try re-classification
        new = _update(session, state=BotState.CLASSIFICATION_L1)
        return new, []

    return _route_after_l1(session, config, intent_id)


def on_clarification_inter_text(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """CLARIFICATION_INTER: user typed free text instead of clicking."""
    # Re-classify with L1
    new = _update(session, state=BotState.CLASSIFICATION_L1)
    return new, []


def on_classification_l2_done(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """Handle L2 classification result."""
    scores: list[tuple[str, float]] = event.data.get("scores", [])
    journey = config.journey

    if not scores:
        # No sub-motif detected — use intent-level retrieval
        new = _update(session, state=BotState.RETRIEVAL_GENERATION)
        return new, [
            EmitGeneration(
                query=session.original_query or "",
                intent=session.current_intent or "",
            ),
        ]

    best_id, best_score = scores[0]

    if best_score >= journey.seuil_sous_motif:
        # Confident sub-motif — skip clarification
        new = _update(
            session,
            state=BotState.RETRIEVAL_GENERATION,
            current_sub_motif=best_id,
        )
        return new, [
            EmitGeneration(
                query=session.original_query or "",
                intent=session.current_intent or "",
                sub_motif=best_id,
            ),
        ]

    # Not confident — clarification intra (if allowed)
    if session.clarifications_count_current_demande >= journey.max_clarifications:
        # Already used clarification at L1, go straight with best guess
        new = _update(
            session,
            state=BotState.RETRIEVAL_GENERATION,
            current_sub_motif=best_id,
        )
        return new, [
            EmitGeneration(
                query=session.original_query or "",
                intent=session.current_intent or "",
                sub_motif=best_id,
            ),
        ]

    # Present sub-motif options
    intent = next(
        (i for i in config.intents if i.id == session.current_intent), None
    )
    if not intent:
        new = _update(session, state=BotState.RETRIEVAL_GENERATION)
        return new, [
            EmitGeneration(
                query=session.original_query or "",
                intent=session.current_intent or "",
            ),
        ]

    options = [sm.label for sm in intent.sub_motifs] + ["Autre"]
    new = _update(
        session,
        state=BotState.CLARIFICATION_INTRA,
        clarifications_count_current_demande=(
            session.clarifications_count_current_demande + 1
        ),
    )
    return new, [
        EmitTemplate(
            key=TemplateKey.CLARIFICATION_INTRA,
            variables={"options": ", ".join(options)},
            buttons=options,
        ),
    ]


def on_clarification_intra_button(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """CLARIFICATION_INTRA: user clicked a sub-motif or 'Autre'."""
    selected_label = event.data.get("button", "")

    if selected_label == "Autre":
        # Retrieve on whole intent; if scores too low -> escalade
        new = _update(session, state=BotState.RETRIEVAL_GENERATION)
        return new, [
            EmitGeneration(
                query=session.original_query or "",
                intent=session.current_intent or "",
            ),
        ]

    # Find sub-motif id from label
    intent = next(
        (i for i in config.intents if i.id == session.current_intent), None
    )
    if intent:
        sm = next((s for s in intent.sub_motifs if s.label == selected_label), None)
        if sm:
            new = _update(
                session,
                state=BotState.RETRIEVAL_GENERATION,
                current_sub_motif=sm.id,
            )
            return new, [
                EmitGeneration(
                    query=session.original_query or "",
                    intent=session.current_intent or "",
                    sub_motif=sm.id,
                ),
            ]

    # Fallback — intent-level retrieval
    new = _update(session, state=BotState.RETRIEVAL_GENERATION)
    return new, [
        EmitGeneration(
            query=session.original_query or "",
            intent=session.current_intent or "",
        ),
    ]


def on_clarification_intra_text(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """CLARIFICATION_INTRA: user typed free text — re-classify L2."""
    text = event.data.get("text", "")
    # Concatenate original query + response for re-classification
    combined = f"{session.original_query or ''} {text}".strip()
    new = _update(session, state=BotState.CLASSIFICATION_L2, original_query=combined)
    return new, []


def on_retrieval_generation_done(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """RETRIEVAL_GENERATION -> ENQUETE_SATISFACTION."""
    new = _update(session, state=BotState.ENQUETE_SATISFACTION)
    return new, [
        EmitTemplate(
            key=TemplateKey.ENQUETE_SATISFACTION,
            buttons=["Oui", "Non"],
        ),
    ]


def on_satisfaction_positive(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """User satisfied — ask if they have another question."""
    new = _update(session, state=BotState.AUTRE_DEMANDE)
    return new, [
        EmitTemplate(
            key=TemplateKey.AUTRE_DEMANDE,
            buttons=["Oui", "Non"],
        ),
    ]


def on_satisfaction_negative(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """User NOT satisfied — immediate escalation (no retry, decision acte)."""
    new = _update(session, state=BotState.ESCALADE)
    return new, [CallEscalation(motif=EscalationMotif.INSATISFACTION)]


def on_autre_demande_oui(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """User has another question — loop back if under max_demandes."""
    new_count = session.demandes_count + 1
    if new_count >= config.journey.max_demandes:
        new = _update(session, state=BotState.FIN, demandes_count=new_count)
        return new, [EmitTemplate(key=TemplateKey.FIN), CloseSession(reason="max_demandes")]

    new = _update(
        session,
        state=BotState.ATTENTE_DEMANDE,
        demandes_count=new_count,
        current_intent=None,
        current_sub_motif=None,
        pending_candidates=[],
        original_query=None,
        clarifications_count_current_demande=0,
        reformulation_count_current_demande=0,
    )
    return new, []


def on_autre_demande_non(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """User is done — close."""
    new = _update(session, state=BotState.FIN)
    return new, [EmitTemplate(key=TemplateKey.FIN), CloseSession()]


def on_escalade_done(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """After escalation result received — emit template and close."""
    temps_attente = str(event.data.get("temps_attente_estime_min", 4))
    new = _update(session, state=BotState.FIN)
    return new, [
        EmitTemplate(
            key=TemplateKey.MISE_EN_RELATION,
            variables={"temps_attente": temps_attente},
        ),
        CloseSession(reason="escalade"),
    ]


def on_timeout(
    session: BotSession, event: Event, config: BotConfig,
) -> TransitionResult:
    """Inactivity timeout — close with timeout template."""
    new = _update(session, state=BotState.TIMEOUT)
    return new, [EmitTemplate(key=TemplateKey.TIMEOUT), CloseSession(reason="timeout")]


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

# Key: (current_state, event_type)
# Value: handler function (session, event, config) -> (session, actions)

TransitionHandler = type(on_start)  # callable type hint

TRANSITIONS: dict[tuple[BotState, EventType], TransitionHandler] = {
    # Startup
    (BotState.ACCUEIL, EventType.START): on_start,
    # User submits a query
    (BotState.ATTENTE_DEMANDE, EventType.USER_MESSAGE): on_user_message_attente,
    # L1 classification result
    (BotState.CLASSIFICATION_L1, EventType.CLASSIFICATION_L1_DONE): on_classification_l1_done,
    # Clarification inter-intentions
    (BotState.CLARIFICATION_INTER, EventType.BUTTON_CLICK): on_clarification_inter_button,
    (BotState.CLARIFICATION_INTER, EventType.USER_MESSAGE): on_clarification_inter_text,
    # L2 classification result
    (BotState.CLASSIFICATION_L2, EventType.CLASSIFICATION_L2_DONE): on_classification_l2_done,
    # Clarification intra-intention
    (BotState.CLARIFICATION_INTRA, EventType.BUTTON_CLICK): on_clarification_intra_button,
    (BotState.CLARIFICATION_INTRA, EventType.USER_MESSAGE): on_clarification_intra_text,
    # Retrieval + generation done
    (BotState.RETRIEVAL_GENERATION, EventType.RETRIEVAL_GENERATION_DONE): on_retrieval_generation_done,
    # Satisfaction survey
    (BotState.ENQUETE_SATISFACTION, EventType.BUTTON_CLICK): lambda s, e, c: (
        on_satisfaction_positive(s, e, c) if e.data.get("button") == "Oui"
        else on_satisfaction_negative(s, e, c)
    ),
    # Another question?
    (BotState.AUTRE_DEMANDE, EventType.BUTTON_CLICK): lambda s, e, c: (
        on_autre_demande_oui(s, e, c) if e.data.get("button") == "Oui"
        else on_autre_demande_non(s, e, c)
    ),
}

# Transverse transitions (checked before the table)
TRANSVERSE_EVENTS: dict[EventType, TransitionHandler] = {
    EventType.TIMEOUT_EXPIRED: on_timeout,
}
