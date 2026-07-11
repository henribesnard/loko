"""LOKO Bot — Orchestrator.

Connects the pure FSM engine with I/O services:
  - SetFit classifier (L1/L2)
  - Filtered retriever
  - LLM generator (streaming)
  - Escalation provider
  - Trace collector

Main entry point: BotOrchestrator.process_message()
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from loko.bot.engine import (
    add_turn_to_session,
    create_session,
    handle_escalation_result,
    start_session,
    step,
)
from loko.bot.generation import BotGenerator
from loko.bot.models import (
    Action,
    BotConfig,
    BotSession,
    BotState,
    CallEscalation,
    Chunk,
    CloseSession,
    EmitGeneration,
    EmitTemplate,
    EscalationMotif,
    EscalationPayload,
    RetrievalResult,
    TraceEvent,
)
from loko.bot.retrieval_filter import FilteredRetriever
from loko.bot.states import Event, EventType
from loko.bot.templates import render_template, resolve_template
from loko.bot.tracing import TraceCollector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Classifier protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ClassifierProtocol(Protocol):
    """Interface for intent/sub-motif classification."""

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        """Classify text at level 1 (intents). Returns sorted (id, score)."""
        ...

    def classify_l2(self, intent_id: str, text: str) -> list[tuple[str, float]]:
        """Classify text at level 2 (sub-motifs). Returns sorted (id, score)."""
        ...


# ---------------------------------------------------------------------------
# Escalation protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class EscalationProtocol(Protocol):
    """Interface for escalation to human agent."""

    async def escalate(self, payload: EscalationPayload) -> Any:
        """Send escalation request. Returns at least temps_attente_estime_min."""
        ...


# ---------------------------------------------------------------------------
# SSE event types
# ---------------------------------------------------------------------------

@dataclass
class SSEEvent:
    """A Server-Sent Event for the runtime API."""
    event: str
    data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class BotOrchestrator:
    """Connects FSM engine to I/O services.

    Stateless — the session state is passed in and returned.
    """

    def __init__(
        self,
        classifier: ClassifierProtocol,
        retriever: FilteredRetriever,
        generator: BotGenerator,
        escalation: EscalationProtocol,
    ):
        self.classifier = classifier
        self.retriever = retriever
        self.generator = generator
        self.escalation = escalation

    async def create_and_start_session(
        self,
        config: BotConfig,
    ) -> tuple[BotSession, list[SSEEvent]]:
        """Create a new session and emit the welcome message.

        Returns
        -------
        tuple[BotSession, list[SSEEvent]]
            Updated session and SSE events to send to the client.
        """
        session = create_session(config.bot_id)
        session, actions = start_session(session, config)

        events: list[SSEEvent] = []
        events.append(SSEEvent(event="state", data={"state": session.state.value}))

        for action in actions:
            if isinstance(action, EmitTemplate):
                text = self._render_action_template(action, config)
                session = add_turn_to_session(
                    session, role="bot", content=text,
                    template_key=action.key, buttons=action.buttons,
                )
                events.append(SSEEvent(
                    event="template",
                    data={
                        "content": text,
                        "template_key": action.key.value,
                        "buttons": action.buttons,
                    },
                ))

        return session, events

    async def process_message(
        self,
        session: BotSession,
        user_text: str,
        config: BotConfig,
    ) -> AsyncIterator[tuple[BotSession, SSEEvent]]:
        """Process a user message through the full pipeline.

        Yields (updated_session, event) tuples as processing progresses.
        The caller must always use the latest session from the last yield.

        The pipeline:
        1. Record user turn
        2. FSM step (USER_MESSAGE) → may trigger CLASSIFICATION_L1
        3. Run SetFit L1 → feed result back → may trigger L2
        4. Run SetFit L2 → feed result back → may trigger RETRIEVAL
        5. Retrieval → check sufficiency → generation or escalation
        6. Emit satisfaction survey
        """
        turn_id = str(uuid.uuid4())
        traces = TraceCollector(turn_id)

        # Record user message
        session = add_turn_to_session(session, role="user", content=user_text)

        # --- Step 1: USER_MESSAGE event ---
        event = Event(EventType.USER_MESSAGE, data={"text": user_text})
        session, actions = step(session, event, config)

        yield session, SSEEvent(event="state", data={"state": session.state.value})

        # Process actions iteratively
        async for session, sse_event in self._process_actions(
            session, actions, config, user_text, traces,
        ):
            yield session, sse_event

        # Emit traces
        yield session, SSEEvent(
            event="traces",
            data={"turn_id": turn_id, "traces": traces.to_list()},
        )

    async def process_button_click(
        self,
        session: BotSession,
        button_value: str,
        config: BotConfig,
    ) -> AsyncIterator[tuple[BotSession, SSEEvent]]:
        """Process a button click (clarification choice)."""
        turn_id = str(uuid.uuid4())
        traces = TraceCollector(turn_id)

        session = add_turn_to_session(
            session, role="user", content=button_value,
            button_selected=button_value,
        )

        event = Event(EventType.BUTTON_CLICK, data={"selected": button_value})
        session, actions = step(session, event, config)

        yield session, SSEEvent(event="state", data={"state": session.state.value})

        async for session, sse_event in self._process_actions(
            session, actions, config, button_value, traces,
        ):
            yield session, sse_event

        yield session, SSEEvent(
            event="traces",
            data={"turn_id": turn_id, "traces": traces.to_list()},
        )

    # ------------------------------------------------------------------
    # Internal: action processing loop
    # ------------------------------------------------------------------

    async def _process_actions(
        self,
        session: BotSession,
        actions: list[Action],
        config: BotConfig,
        user_text: str,
        traces: TraceCollector,
    ) -> AsyncIterator[tuple[BotSession, SSEEvent]]:
        """Process a list of FSM actions, potentially triggering more steps.

        The loop handles two kinds of progression:
        1. Action-driven: process each action (template, generation, etc.)
        2. State-driven: when session lands in a classification state,
           run the classifier and feed results back to the FSM.
        """
        pending_actions = list(actions)

        # Guard against infinite loops
        max_iterations = 50
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # --- State-driven: classification auto-steps ---
            if session.state == BotState.CLASSIFICATION_L1:
                new_session, new_actions = await self._run_classification_l1(
                    session, user_text, config, traces,
                )
                session = new_session
                yield session, SSEEvent(event="state", data={"state": session.state.value})
                pending_actions = list(new_actions) + pending_actions
                continue

            if session.state == BotState.CLASSIFICATION_L2:
                query = session.original_query or user_text
                new_session, new_actions = await self._run_classification_l2(
                    session, query, config, traces,
                )
                session = new_session
                yield session, SSEEvent(event="state", data={"state": session.state.value})
                pending_actions = list(new_actions) + pending_actions
                continue

            # --- Action-driven ---
            if not pending_actions:
                break

            action = pending_actions.pop(0)

            if isinstance(action, EmitTemplate):
                text = self._render_action_template(action, config)
                session = add_turn_to_session(
                    session, role="bot", content=text,
                    template_key=action.key, buttons=action.buttons,
                )
                yield session, SSEEvent(
                    event="template",
                    data={
                        "content": text,
                        "template_key": action.key.value,
                        "buttons": action.buttons,
                    },
                )

            elif isinstance(action, EmitGeneration):
                async for session, sse_event in self._handle_generation(
                    session, action, config, traces,
                ):
                    yield session, sse_event

            elif isinstance(action, CallEscalation):
                async for session, sse_event in self._handle_escalation(
                    session, action, config, traces,
                ):
                    yield session, sse_event

            elif isinstance(action, CloseSession):
                yield session, SSEEvent(
                    event="end_of_turn",
                    data={"reason": action.reason},
                )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    async def _run_classification_l1(
        self,
        session: BotSession,
        text: str,
        config: BotConfig,
        traces: TraceCollector,
    ) -> tuple[BotSession, list[Action]]:
        """Run L1 classification and feed result to FSM."""
        with traces.measure("classification_l1") as ctx:
            scores = self.classifier.classify_l1(text)
            ctx["scores"] = scores

        event = Event(
            EventType.CLASSIFICATION_L1_DONE,
            data={"scores": scores},
        )
        return step(session, event, config)

    async def _run_classification_l2(
        self,
        session: BotSession,
        text: str,
        config: BotConfig,
        traces: TraceCollector,
    ) -> tuple[BotSession, list[Action]]:
        """Run L2 classification and feed result to FSM."""
        intent_id = session.current_intent or ""

        with traces.measure("classification_l2") as ctx:
            scores = self.classifier.classify_l2(intent_id, text)
            ctx["scores"] = scores

        event = Event(
            EventType.CLASSIFICATION_L2_DONE,
            data={"scores": scores},
        )
        return step(session, event, config)

    # ------------------------------------------------------------------
    # Retrieval + Generation (O6: extracted pure helpers)
    # ------------------------------------------------------------------

    @staticmethod
    def _find_intent_labels(
        config: BotConfig,
        intent_id: str,
        sub_motif_id: str | None,
    ) -> tuple[str, str]:
        """Pure helper: find intent and sub-motif labels from config.

        Returns
        -------
        tuple[str, str]
            (intent_label, sub_motif_label)
        """
        intent_label = ""
        sub_motif_label = ""
        for intent in config.intents:
            if intent.id == intent_id:
                intent_label = intent.label
                if sub_motif_id:
                    for sm in intent.sub_motifs:
                        if sm.id == sub_motif_id:
                            sub_motif_label = sm.label
                            break
                break
        return intent_label, sub_motif_label

    async def _handle_generation(
        self,
        session: BotSession,
        action: EmitGeneration,
        config: BotConfig,
        traces: TraceCollector,
    ) -> AsyncIterator[tuple[BotSession, SSEEvent]]:
        """Handle EmitGeneration: retrieval → check → generate → satisfaction."""
        # Find intent/sub-motif labels for query augmentation
        intent_label, sub_motif_label = self._find_intent_labels(
            config, action.intent, action.sub_motif,
        )

        # --- Retrieval ---
        with traces.measure("retrieval") as ctx:
            result = await self.retriever.retrieve(
                query=action.query,
                intent=action.intent,
                sub_motif=action.sub_motif,
                config=config,
                intent_label=intent_label,
                sub_motif_label=sub_motif_label,
            )
            ctx["scope"] = result.scope
            ctx["num_chunks"] = len(result.chunks)
            ctx["scores"] = [(c.chunk_id, c.score) for c in result.chunks]
            ctx["success"] = result.success

        # If retrieval fails → escalate directly (bypass FSM's RETRIEVAL_GENERATION_DONE
        # which always transitions to satisfaction)
        if not result.success:
            session = session.model_copy(update={"state": BotState.ESCALADE})
            yield session, SSEEvent(event="state", data={"state": session.state.value})

            escalation_action = CallEscalation(
                motif=result.escalation_motif or EscalationMotif.RETRIEVAL_INSUFFISANT,
            )
            async for session, sse_event in self._handle_escalation(
                session, escalation_action, config, traces,
            ):
                yield session, sse_event
            return

        # --- Generation (streaming) ---
        tokens: list[str] = []
        with traces.measure("generation") as ctx:
            async for token in self.generator.generate(
                query=action.query,
                chunks=result.chunks,
                intent=action.intent,
                sub_motif=action.sub_motif,
                config=config,
            ):
                tokens.append(token)
                yield session, SSEEvent(
                    event="generation_delta",
                    data={"token": token},
                )

            full_response = "".join(tokens)
            ctx["response_length"] = len(full_response)

        # Extract sources
        sources = self.generator.extract_sources(result.chunks)
        if sources:
            yield session, SSEEvent(event="sources", data={"sources": sources})

        # Record bot turn
        session = add_turn_to_session(
            session, role="bot", content=full_response,
            intent=action.intent, sub_motif=action.sub_motif,
            sources=sources,
        )

        # --- Transition to satisfaction survey ---
        done_event = Event(EventType.RETRIEVAL_GENERATION_DONE)
        session, next_actions = step(session, done_event, config)
        yield session, SSEEvent(event="state", data={"state": session.state.value})

        # Process next actions (typically satisfaction template)
        for a in next_actions:
            if isinstance(a, EmitTemplate):
                text = self._render_action_template(a, config)
                session = add_turn_to_session(
                    session, role="bot", content=text,
                    template_key=a.key, buttons=a.buttons,
                )
                yield session, SSEEvent(
                    event="template",
                    data={
                        "content": text,
                        "template_key": a.key.value,
                        "buttons": a.buttons,
                    },
                )

    # ------------------------------------------------------------------
    # Escalation (O6: extracted pure helpers)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_escalation_payload(
        session: BotSession,
        action: CallEscalation,
        max_turns: int = 10,
    ) -> EscalationPayload:
        """Pure helper: build escalation payload from session.

        Parameters
        ----------
        session : BotSession
            Current session state
        action : CallEscalation
            Escalation action with motif
        max_turns : int, optional
            Maximum number of transcript turns to include (default: 10)

        Returns
        -------
        EscalationPayload
            Payload ready to send to escalation provider
        """
        return EscalationPayload(
            conversation_id=session.session_id,
            transcript=[
                {"role": t.role, "content": t.content}
                for t in session.transcript[-max_turns:]
            ],
            intention=session.current_intent,
            sous_motif=session.current_sub_motif,
            motif_escalade=action.motif,
        )

    @staticmethod
    def _extract_temps_attente(result: Any, default: int = 4) -> int:
        """Pure helper: extract wait time from escalation result.

        Parameters
        ----------
        result : Any
            Escalation provider result (dict or object)
        default : int, optional
            Default wait time if not found (default: 4)

        Returns
        -------
        int
            Estimated wait time in minutes
        """
        if isinstance(result, dict):
            return result.get("temps_attente_estime_min", default)
        return getattr(result, "temps_attente_estime_min", default)

    async def _handle_escalation(
        self,
        session: BotSession,
        action: CallEscalation,
        config: BotConfig,
        traces: TraceCollector,
    ) -> AsyncIterator[tuple[BotSession, SSEEvent]]:
        """Handle CallEscalation: call provider, then emit template."""
        payload = self._build_escalation_payload(session, action)

        with traces.measure("escalation") as ctx:
            result = await self.escalation.escalate(payload)
            ctx["motif"] = action.motif.value
            ctx["result"] = result.model_dump() if hasattr(result, "model_dump") else result

        temps_attente = self._extract_temps_attente(result)
        session, esc_actions = handle_escalation_result(session, config, temps_attente)

        yield session, SSEEvent(event="state", data={"state": session.state.value})

        for a in esc_actions:
            if isinstance(a, EmitTemplate):
                text = self._render_action_template(a, config)
                session = add_turn_to_session(
                    session, role="bot", content=text,
                    template_key=a.key,
                )
                yield session, SSEEvent(
                    event="template",
                    data={
                        "content": text,
                        "template_key": a.key.value,
                    },
                )
            elif isinstance(a, CloseSession):
                yield session, SSEEvent(
                    event="end_of_turn",
                    data={"reason": a.reason},
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _render_action_template(
        self,
        action: EmitTemplate,
        config: BotConfig,
    ) -> str:
        """Resolve and render a template action."""
        template = resolve_template(
            config.templates, action.key, config.tone_profile,
        )
        lang = config.language if config.language != "auto" else "fr"
        return render_template(template, lang, action.variables)
