"""LOKO Bot — Public runtime API endpoints.

Prefix: /api/v1/bot
Covers: session creation, message handling (SSE), feedback.

These endpoints are used by the embeddable widget and external
API consumers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from loko.bot.config_store import load_bot_config
from loko.bot.generation import BotGenerator, MockLLMProvider
from loko.bot.models import BotConfig, BotState
from loko.bot.orchestrator import BotOrchestrator, SSEEvent
from loko.bot.retrieval_filter import FilteredRetriever, InMemorySearchBackend
from loko.bot.session_store import SessionStore, get_session_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bot", tags=["bot-runtime"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class MessageRequest(BaseModel):
    """User message sent to the bot."""
    text: str
    type: str = "text"  # "text" | "button_click"


class FeedbackRequest(BaseModel):
    """User feedback for a turn."""
    turn_id: str
    rating: str  # "positive" | "negative"
    comment: str = ""


class SessionResponse(BaseModel):
    """Session state returned to the client."""
    session_id: str
    bot_id: str
    state: str
    transcript: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Bot runtime singleton (lazy init per bot)
# ---------------------------------------------------------------------------

_ORCHESTRATORS: dict[str, BotOrchestrator] = {}


def _get_orchestrator(bot_id: str, config: BotConfig) -> BotOrchestrator:
    """Get or create the orchestrator for a bot.

    In production, this would load the real SetFit classifier and
    connect to the vector store.  For now, uses mocks that can be
    replaced via dependency injection.
    """
    if bot_id not in _ORCHESTRATORS:
        from loko.bot.escalation import MockEscalationProvider

        # Default: mock services (replaced when real ones are configured)
        classifier = _load_classifier(bot_id)
        retriever = FilteredRetriever(InMemorySearchBackend())
        generator = BotGenerator(MockLLMProvider(
            response="Je n'ai pas encore de base de connaissances configurée."
        ))
        escalation = MockEscalationProvider()

        _ORCHESTRATORS[bot_id] = BotOrchestrator(
            classifier=classifier,
            retriever=retriever,
            generator=generator,
            escalation=escalation,
        )

    return _ORCHESTRATORS[bot_id]


def _load_classifier(bot_id: str) -> Any:
    """Load the SetFit classifier for a bot, or use a mock."""
    try:
        from loko.bot.classifier.model_store import model_exists
        from loko.bot.classifier.setfit_service import SetFitClassifier

        if model_exists(bot_id, "level1"):
            clf = SetFitClassifier(bot_id, "level1")
            clf.load()
            return _SetFitClassifierAdapter(bot_id, clf)
    except ImportError:
        pass

    return _MockClassifier()


class _SetFitClassifierAdapter:
    """Adapts SetFitClassifier to the ClassifierProtocol."""

    def __init__(self, bot_id: str, l1_classifier: Any):
        self.bot_id = bot_id
        self._l1 = l1_classifier
        self._l2_cache: dict[str, Any] = {}

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        return self._l1.classify(text)

    def classify_l2(self, intent_id: str, text: str) -> list[tuple[str, float]]:
        if intent_id not in self._l2_cache:
            try:
                from loko.bot.classifier.model_store import model_exists
                from loko.bot.classifier.setfit_service import SetFitClassifier

                if model_exists(self.bot_id, "level2", intent_id):
                    clf = SetFitClassifier(self.bot_id, "level2", intent_id)
                    clf.load()
                    self._l2_cache[intent_id] = clf
                else:
                    return []
            except ImportError:
                return []

        return self._l2_cache[intent_id].classify(text)


class _MockClassifier:
    """Fallback classifier when no model is trained."""

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        return [("hors_perimetre", 0.5)]

    def classify_l2(self, intent_id: str, text: str) -> list[tuple[str, float]]:
        return []


def register_orchestrator(bot_id: str, orchestrator: BotOrchestrator) -> None:
    """Register a custom orchestrator (for testing or advanced setup)."""
    _ORCHESTRATORS[bot_id] = orchestrator


def clear_orchestrators() -> None:
    """Clear all cached orchestrators (for testing)."""
    _ORCHESTRATORS.clear()


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse_encode(event: SSEEvent) -> str:
    """Encode an SSEEvent as an SSE text frame."""
    data = json.dumps(event.data, ensure_ascii=False)
    return f"event: {event.event}\ndata: {data}\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/{bot_id}/sessions", status_code=201)
async def create_session(bot_id: str) -> dict[str, Any]:
    """Create a new conversation session and return the welcome message."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    orchestrator = _get_orchestrator(bot_id, config)
    store = get_session_store(bot_id)

    session, events = await orchestrator.create_and_start_session(config)
    store.create_session(session)

    # Record welcome turns
    for turn in session.transcript:
        store.add_turn(session.session_id, turn)

    return {
        "session_id": session.session_id,
        "bot_id": bot_id,
        "state": session.state.value,
        "events": [{"event": e.event, "data": e.data} for e in events],
    }


@router.post("/{bot_id}/sessions/{session_id}/messages")
async def send_message(
    bot_id: str,
    session_id: str,
    req: MessageRequest,
) -> StreamingResponse:
    """Process a user message and stream the response as SSE."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    store = get_session_store(bot_id)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    if session.state in (BotState.FIN, BotState.TIMEOUT):
        raise HTTPException(400, "Session has ended")

    orchestrator = _get_orchestrator(bot_id, config)

    async def event_stream() -> AsyncIterator[str]:
        current_session = session

        if req.type == "button_click":
            event_iter = orchestrator.process_button_click(
                current_session, req.text, config,
            )
        else:
            event_iter = orchestrator.process_message(
                current_session, req.text, config,
            )

        async for current_session, sse_event in event_iter:
            yield _sse_encode(sse_event)

        # Persist updated session
        store.update_session(current_session)

        # Persist new turns
        for turn in current_session.transcript[len(session.transcript):]:
            store.add_turn(current_session.session_id, turn)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{bot_id}/sessions/{session_id}")
async def get_session(bot_id: str, session_id: str) -> dict[str, Any]:
    """Get current session state and transcript."""
    store = get_session_store(bot_id)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    return {
        "session_id": session.session_id,
        "bot_id": session.bot_id,
        "state": session.state.value,
        "transcript": [t.model_dump(mode="json") for t in session.transcript],
        "current_intent": session.current_intent,
        "current_sub_motif": session.current_sub_motif,
    }


@router.post("/{bot_id}/sessions/{session_id}/feedback")
async def add_feedback(
    bot_id: str,
    session_id: str,
    req: FeedbackRequest,
) -> dict[str, str]:
    """Record user feedback for a turn."""
    store = get_session_store(bot_id)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    store.add_feedback(session_id, req.turn_id, req.rating, req.comment)
    return {"status": "recorded"}


@router.get("/{bot_id}/sessions/{session_id}/traces")
async def get_traces(bot_id: str, session_id: str) -> list[dict[str, Any]]:
    """Get all trace events for a session (playground/debug)."""
    store = get_session_store(bot_id)
    traces = store.get_traces(session_id)
    return [t.model_dump(mode="json") for t in traces]
