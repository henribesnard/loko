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
    CloseSession,
    EmitGeneration,
    EmitTemplate,
    EscalationMotif,
    EscalationPayload,
    TemplateKey,
)
from loko.bot.guardrails import (
    GuardrailEngine,
    GuardrailsConfig,
    check_grounding,
    check_response_leaks,
    check_response_leaks_streaming,
    default_ruleset,
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
        guardrails_config: GuardrailsConfig | None = None,
    ):
        self.classifier = classifier
        self.retriever = retriever
        self.generator = generator
        self.escalation = escalation
        # GF: guardrail engine (default rules if no config)
        gc = guardrails_config or GuardrailsConfig(rules=default_ruleset())
        self._guardrail_engine = GuardrailEngine(gc)
        self._guardrails_config = gc

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
                    session,
                    role="bot",
                    content=text,
                    template_key=action.key,
                    buttons=action.buttons,
                )
                events.append(
                    SSEEvent(
                        event="template",
                        data={
                            "content": text,
                            "template_key": action.key.value,
                            "buttons": action.buttons,
                        },
                    )
                )

        return session, events

    def _check_session_budgets(
        self,
        session: BotSession,
        config: BotConfig,
    ) -> tuple[BotSession, list[SSEEvent]] | None:
        """ORC: check duration and token budgets before processing.

        Returns (session, events) to emit if budget exceeded, None otherwise.
        Budget is checked BEFORE the LLM call — a stream already started
        is never cut for budget reasons.
        """
        from datetime import datetime, timezone

        journey = config.journey

        # ORC-2: duration budget
        try:
            created = datetime.fromisoformat(session.created_at)
            now = datetime.now(timezone.utc)
            elapsed_s = (now - created).total_seconds()
        except (ValueError, TypeError):
            elapsed_s = 0

        if elapsed_s > journey.max_duree_session_s:
            return self._build_cloture_douce(session, config, "budget_duree")

        # ORC-3: token budget
        if session.tokens_llm_cumul >= journey.max_tokens_llm_session:
            return self._build_cloture_douce(session, config, "budget_tokens")

        return None

    def _build_cloture_douce(
        self,
        session: BotSession,
        config: BotConfig,
        reason: str,
    ) -> tuple[BotSession, list[SSEEvent]]:
        """Build the CLOTURE_DOUCE response."""
        resume = ", ".join(session.resolved_intents) if session.resolved_intents else ""

        new_session = session.model_copy(update={"state": BotState.CLOTURE_DOUCE})

        text = self._render_action_template(
            EmitTemplate(
                key=TemplateKey.CLOTURE_DOUCE,
                variables={
                    "nom_bot": config.name,
                    "resume_demandes": resume,
                    "lien_escalade": "",
                },
            ),
            config,
        )
        new_session = add_turn_to_session(
            new_session,
            role="bot",
            content=text,
            template_key=TemplateKey.CLOTURE_DOUCE,
        )

        events = [
            SSEEvent(event="state", data={"state": new_session.state.value}),
            SSEEvent(
                event="template",
                data={
                    "content": text,
                    "template_key": TemplateKey.CLOTURE_DOUCE.value,
                },
            ),
            SSEEvent(event="end_of_turn", data={"reason": reason}),
        ]
        return new_session, events

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
        0. ORC: check duration/token budgets
        1. Record user turn
        2. FSM step (USER_MESSAGE) → may trigger CLASSIFICATION_L1
        3. Run SetFit L1 → feed result back → may trigger L2
        4. Run SetFit L2 → feed result back → may trigger RETRIEVAL
        5. Retrieval → check sufficiency → generation or escalation
        6. Emit satisfaction survey
        """
        # ORC: check session budgets before processing
        budget_result = self._check_session_budgets(session, config)
        if budget_result is not None:
            session, events = budget_result
            for sse_event in events:
                yield session, sse_event
            return

        turn_id = str(uuid.uuid4())
        traces = TraceCollector(turn_id)

        # --- GF Layer 1: deterministic pre-filter (before classification) ---
        guardrail_result = self._guardrail_engine.check(user_text)
        if guardrail_result.blocked:
            traces.add(
                "guardrail_prefilter",
                detail={
                    "blocked_by": guardrail_result.rule_id,
                    "category": guardrail_result.category,
                },
            )

            # Record user message
            session = add_turn_to_session(session, role="user", content=user_text)

            # Increment infraction counter if action requires it
            if guardrail_result.action in ("refuser_et_compter", "escalader"):
                session = session.model_copy(
                    update={"infractions": session.infractions + 1}
                )

            # Check if max infractions reached
            if session.infractions >= self._guardrails_config.max_infractions:
                if self._guardrails_config.action_apres_max == "escalade":
                    session = session.model_copy(update={"state": BotState.ESCALADE})
                    yield (
                        session,
                        SSEEvent(event="state", data={"state": session.state.value}),
                    )
                    async for session, sse_event in self._handle_escalation(
                        session,
                        CallEscalation(motif=EscalationMotif.INFRACTIONS),
                        config,
                        traces,
                    ):
                        yield session, sse_event
                else:
                    # FIN_FERME
                    intent_labels = ", ".join(
                        i.label for i in config.intents if not i.is_system
                    )
                    session = session.model_copy(update={"state": BotState.FIN_FERME})
                    text = self._render_action_template(
                        EmitTemplate(
                            key=TemplateKey.FIN_FERME,
                            variables={"intentions_gerees": intent_labels},
                        ),
                        config,
                    )
                    session = add_turn_to_session(
                        session,
                        role="bot",
                        content=text,
                        template_key=TemplateKey.FIN_FERME,
                    )
                    yield (
                        session,
                        SSEEvent(event="state", data={"state": session.state.value}),
                    )
                    yield (
                        session,
                        SSEEvent(
                            event="template",
                            data={
                                "content": text,
                                "template_key": TemplateKey.FIN_FERME.value,
                            },
                        ),
                    )
                    yield (
                        session,
                        SSEEvent(event="end_of_turn", data={"reason": "fin_ferme"}),
                    )
            else:
                # Emit refusal template (no LLM, no retrieval)
                intent_labels = ", ".join(
                    i.label for i in config.intents if not i.is_system
                )
                text = self._render_action_template(
                    EmitTemplate(
                        key=TemplateKey.DEMANDE_INAPPROPRIEE,
                        variables={
                            "nom_bot": config.name,
                            "intentions_gerees": intent_labels,
                        },
                    ),
                    config,
                )
                session = add_turn_to_session(
                    session,
                    role="bot",
                    content=text,
                    template_key=TemplateKey.DEMANDE_INAPPROPRIEE,
                )
                yield (
                    session,
                    SSEEvent(
                        event="template",
                        data={
                            "content": text,
                            "template_key": TemplateKey.DEMANDE_INAPPROPRIEE.value,
                        },
                    ),
                )

            # Emit traces
            yield (
                session,
                SSEEvent(
                    event="traces",
                    data={"turn_id": turn_id, "traces": traces.to_list()},
                ),
            )
            return

        # Record user message
        session = add_turn_to_session(session, role="user", content=user_text)

        # --- Step 1: USER_MESSAGE event ---
        event = Event(EventType.USER_MESSAGE, data={"text": user_text})
        session, actions = step(session, event, config)

        yield session, SSEEvent(event="state", data={"state": session.state.value})

        # Process actions iteratively
        async for session, sse_event in self._process_actions(
            session,
            actions,
            config,
            user_text,
            traces,
        ):
            yield session, sse_event

        # Emit traces with ORC counters
        yield (
            session,
            SSEEvent(
                event="traces",
                data={
                    "turn_id": turn_id,
                    "traces": traces.to_list(),
                    "counters": {
                        "demandes": session.demandes_count,
                        "tours_demande": session.tours_demande,
                        "tokens_llm": session.tokens_llm_cumul,
                    },
                },
            ),
        )

    async def process_button_click(
        self,
        session: BotSession,
        button_value: str,
        config: BotConfig,
    ) -> AsyncIterator[tuple[BotSession, SSEEvent]]:
        """Process a button click (clarification choice)."""
        # V4: check session budgets before processing (same as process_message)
        budget_result = self._check_session_budgets(session, config)
        if budget_result is not None:
            session, events = budget_result
            for sse_event in events:
                yield session, sse_event
            return

        turn_id = str(uuid.uuid4())
        traces = TraceCollector(turn_id)

        session = add_turn_to_session(
            session,
            role="user",
            content=button_value,
            button_selected=button_value,
        )

        event = Event(EventType.BUTTON_CLICK, data={"selected": button_value})
        session, actions = step(session, event, config)

        yield session, SSEEvent(event="state", data={"state": session.state.value})

        async for session, sse_event in self._process_actions(
            session,
            actions,
            config,
            button_value,
            traces,
        ):
            yield session, sse_event

        yield (
            session,
            SSEEvent(
                event="traces",
                data={"turn_id": turn_id, "traces": traces.to_list()},
            ),
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
                    session,
                    user_text,
                    config,
                    traces,
                )
                session = new_session
                yield (
                    session,
                    SSEEvent(event="state", data={"state": session.state.value}),
                )
                pending_actions = list(new_actions) + pending_actions
                continue

            if session.state == BotState.CLASSIFICATION_L2:
                query = session.original_query or user_text
                new_session, new_actions = await self._run_classification_l2(
                    session,
                    query,
                    config,
                    traces,
                )
                session = new_session
                yield (
                    session,
                    SSEEvent(event="state", data={"state": session.state.value}),
                )
                pending_actions = list(new_actions) + pending_actions
                continue

            # --- Action-driven ---
            if not pending_actions:
                break

            action = pending_actions.pop(0)

            if isinstance(action, EmitTemplate):
                text = self._render_action_template(action, config)
                session = add_turn_to_session(
                    session,
                    role="bot",
                    content=text,
                    template_key=action.key,
                    buttons=action.buttons,
                )
                yield (
                    session,
                    SSEEvent(
                        event="template",
                        data={
                            "content": text,
                            "template_key": action.key.value,
                            "buttons": action.buttons,
                        },
                    ),
                )

            elif isinstance(action, EmitGeneration):
                async for session, sse_event in self._handle_generation(
                    session,
                    action,
                    config,
                    traces,
                ):
                    yield session, sse_event

            elif isinstance(action, CallEscalation):
                async for session, sse_event in self._handle_escalation(
                    session,
                    action,
                    config,
                    traces,
                ):
                    yield session, sse_event

            elif isinstance(action, CloseSession):
                yield (
                    session,
                    SSEEvent(
                        event="end_of_turn",
                        data={"reason": action.reason},
                    ),
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
            config,
            action.intent,
            action.sub_motif,
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
                session,
                escalation_action,
                config,
                traces,
            ):
                yield session, sse_event
            return

        # ORC-3: check token budget before starting generation
        if session.tokens_llm_cumul >= config.journey.max_tokens_llm_session:
            session = session.model_copy(update={"state": BotState.CLOTURE_DOUCE})
            yield session, SSEEvent(event="state", data={"state": session.state.value})

            resume = (
                ", ".join(session.resolved_intents) if session.resolved_intents else ""
            )
            cloture_action = EmitTemplate(
                key=TemplateKey.CLOTURE_DOUCE,
                variables={
                    "nom_bot": config.name,
                    "resume_demandes": resume,
                    "lien_escalade": "",
                },
            )
            text = self._render_action_template(cloture_action, config)
            session = add_turn_to_session(
                session,
                role="bot",
                content=text,
                template_key=TemplateKey.CLOTURE_DOUCE,
            )
            yield (
                session,
                SSEEvent(
                    event="template",
                    data={
                        "content": text,
                        "template_key": TemplateKey.CLOTURE_DOUCE.value,
                    },
                ),
            )
            yield (
                session,
                SSEEvent(event="end_of_turn", data={"reason": "budget_tokens"}),
            )
            return

        # --- Generation (streaming) ---
        tokens: list[str] = []
        accumulated = ""
        leak_detected_mid_stream: str | None = None
        with traces.measure("generation") as ctx:
            async for token in self.generator.generate(
                query=action.query,
                chunks=result.chunks,
                intent=action.intent,
                sub_motif=action.sub_motif,
                config=config,
            ):
                tokens.append(token)
                # V1: streaming-level leak check
                accumulated += token
                leak_detected_mid_stream = check_response_leaks_streaming(accumulated)
                if leak_detected_mid_stream:
                    logger.critical(
                        "Leak detected mid-stream (V1): %s — halting generation",
                        leak_detected_mid_stream,
                    )
                    traces.add("guardrail_leak_streaming", detail={
                        "leak_pattern": leak_detected_mid_stream,
                        "tokens_before_halt": len(tokens),
                    })
                    break
                yield (
                    session,
                    SSEEvent(
                        event="generation_delta",
                        data={"token": token},
                    ),
                )

            full_response = "".join(tokens)
            ctx["response_length"] = len(full_response)
            ctx["token_count"] = len(tokens)

        # ORC-3: update cumulative token count (prefer provider-reported usage)
        provider_usage = (
            self.generator.provider.get_last_usage()
            if hasattr(self.generator.provider, "get_last_usage")
            else None
        )
        token_increment = (
            provider_usage.get("completion_tokens", len(tokens))
            if provider_usage
            else len(tokens)
        )
        session = session.model_copy(
            update={"tokens_llm_cumul": session.tokens_llm_cumul + token_increment}
        )

        # --- GF Layer 3b: output validation (leak detection, always blocking) ---
        # V1: if leak was caught mid-stream, skip full re-scan (already detected)
        leak = leak_detected_mid_stream or check_response_leaks(full_response)
        if leak:
            logger.critical("Leak detected in LLM response: %s", leak)
            traces.add("guardrail_leak", detail={"leak_pattern": leak})
            # Replace response with apology template
            full_response = self._render_action_template(
                EmitTemplate(key=TemplateKey.HORS_PERIMETRE),
                config,
            )
            # V1: emit correction event so client replaces partial streamed content
            yield (
                session,
                SSEEvent(
                    event="generation_replace",
                    data={"content": full_response, "reason": "leak_detected"},
                ),
            )

        # GF Layer 3b: grounding check (V1 = marking only)
        is_grounded = check_grounding(full_response, result.chunks)
        if not is_grounded:
            traces.add("guardrail_grounding", detail={"low_grounding": True})

        # Extract sources
        sources = self.generator.extract_sources(result.chunks)
        if sources:
            yield session, SSEEvent(event="sources", data={"sources": sources})

        # Record bot turn
        session = add_turn_to_session(
            session,
            role="bot",
            content=full_response,
            intent=action.intent,
            sub_motif=action.sub_motif,
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
                    session,
                    role="bot",
                    content=text,
                    template_key=a.key,
                    buttons=a.buttons,
                )
                yield (
                    session,
                    SSEEvent(
                        event="template",
                        data={
                            "content": text,
                            "template_key": a.key.value,
                            "buttons": a.buttons,
                        },
                    ),
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
        # PRO-4: build deterministic structured summary (never LLM-generated)
        resume: dict[str, Any] = {
            "demandes_count": session.demandes_count,
            "resolved_intents": list(session.resolved_intents)
            if session.resolved_intents
            else [],
            "infractions": session.infractions,
            "motif": action.motif.value
            if hasattr(action.motif, "value")
            else str(action.motif),
        }

        return EscalationPayload(
            conversation_id=session.session_id,
            transcript=[
                {"role": t.role, "content": t.content}
                for t in session.transcript[-max_turns:]
            ],
            intention=session.current_intent,
            sous_motif=session.current_sub_motif,
            motif_escalade=action.motif,
            resume=resume,
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
            ctx["result"] = (
                result.model_dump() if hasattr(result, "model_dump") else result
            )

        temps_attente = self._extract_temps_attente(result)
        session, esc_actions = handle_escalation_result(session, config, temps_attente)

        yield session, SSEEvent(event="state", data={"state": session.state.value})

        for a in esc_actions:
            if isinstance(a, EmitTemplate):
                text = self._render_action_template(a, config)
                session = add_turn_to_session(
                    session,
                    role="bot",
                    content=text,
                    template_key=a.key,
                )
                yield (
                    session,
                    SSEEvent(
                        event="template",
                        data={
                            "content": text,
                            "template_key": a.key.value,
                        },
                    ),
                )
            elif isinstance(a, CloseSession):
                yield (
                    session,
                    SSEEvent(
                        event="end_of_turn",
                        data={"reason": a.reason},
                    ),
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
            config.templates,
            action.key,
            config.tone_profile,
        )
        lang = config.language if config.language != "auto" else "fr"
        return render_template(template, lang, action.variables)
