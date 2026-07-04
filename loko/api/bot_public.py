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
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from loko.api.api_keys import APIKeyRecord
from loko.api.auth import require_bot_api_key, validate_bot_id
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
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., max_length=2000)
    type: Literal["text", "button_click"] = "text"


class FeedbackRequest(BaseModel):
    """User feedback for a turn."""
    model_config = ConfigDict(extra="forbid")

    turn_id: str
    rating: Literal["positive", "negative"]
    comment: str = Field(default="", max_length=1000)


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
_SESSION_LOCKS: dict[str, asyncio.Lock] = {}


def _get_orchestrator(bot_id: str, config: BotConfig) -> BotOrchestrator:
    """Get or create the orchestrator for a bot.

    Fail-closed policy (P0-6):
    - Draft bots cannot be served at runtime (409).
    - Published bots use real classifier if available, else fail explicitly.
    - Mocks are only used when RAGKIT_ENV=test.
    """
    import os

    if bot_id not in _ORCHESTRATORS:
        from loko.bot.escalation import MockEscalationProvider

        is_test = os.environ.get("RAGKIT_ENV") == "test"

        classifier = _load_classifier(bot_id, allow_mock=is_test)
        retriever = FilteredRetriever(InMemorySearchBackend())

        # LLM: use mock only in test; otherwise fail with explicit message
        if is_test:
            generator = BotGenerator(MockLLMProvider(
                response="[Mock] Réponse de test."
            ))
        else:
            generator = BotGenerator(MockLLMProvider(
                response="La base de connaissances n'est pas encore configurée. "
                         "Veuillez contacter l'administrateur."
            ))

        escalation = MockEscalationProvider()

        _ORCHESTRATORS[bot_id] = BotOrchestrator(
            classifier=classifier,
            retriever=retriever,
            generator=generator,
            escalation=escalation,
        )

    return _ORCHESTRATORS[bot_id]


def _load_classifier(bot_id: str, *, allow_mock: bool = False) -> Any:
    """Load the SetFit classifier for a bot.

    If allow_mock is False (production), returns a classifier that
    only returns results if a real model is available, otherwise
    falls back to hors_perimetre with low confidence.
    """
    try:
        from loko.bot.classifier.model_store import model_exists
        from loko.bot.classifier.setfit_service import SetFitClassifier

        if model_exists(bot_id, "level1"):
            clf = SetFitClassifier(bot_id, "level1")
            clf.load()
            return _SetFitClassifierAdapter(bot_id, clf)
    except ImportError:
        if not allow_mock:
            logger.warning(
                "SetFit not installed — classifier for bot %s will use fallback",
                bot_id,
            )

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


def invalidate_orchestrator(bot_id: str) -> None:
    """Remove a cached orchestrator (call on publish/retrain/config update)."""
    _ORCHESTRATORS.pop(bot_id, None)


def clear_orchestrators() -> None:
    """Clear all cached orchestrators (for testing)."""
    _ORCHESTRATORS.clear()
    _SESSION_LOCKS.clear()


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

SSE_KEEPALIVE_INTERVAL = 15  # seconds


def _sse_encode(event: SSEEvent) -> str:
    """Encode an SSEEvent as an SSE text frame."""
    data = json.dumps(event.data, ensure_ascii=False)
    return f"event: {event.event}\ndata: {data}\n\n"


def _sse_keepalive() -> str:
    """SSE comment line to keep connection alive (P2-6)."""
    return ": keepalive\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/{bot_id}/sessions", status_code=201)
async def create_session(
    bot_id: str = Depends(validate_bot_id),
    _key: APIKeyRecord = Depends(require_bot_api_key),
) -> dict[str, Any]:
    """Create a new conversation session and return the welcome message."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    # Fail-closed: draft bots cannot serve runtime (P0-6)
    if config.status != "published":
        raise HTTPException(409, "Bot is not published")

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
    session_id: str,
    req: MessageRequest,
    bot_id: str = Depends(validate_bot_id),
    _key: APIKeyRecord = Depends(require_bot_api_key),
) -> StreamingResponse:
    """Process a user message and stream the response as SSE."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    store = get_session_store(bot_id)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Not found")

    if session.state in (BotState.FIN, BotState.TIMEOUT):
        raise HTTPException(400, "Session has ended")

    # Concurrency guard: reject if another message is being processed (P1-5)
    lock = _SESSION_LOCKS.setdefault(session_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "A message is already being processed for this session")

    orchestrator = _get_orchestrator(bot_id, config)

    async def event_stream() -> AsyncIterator[str]:
        current_session = session

        async with lock:
            try:
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
            finally:
                # Persist session state even on client disconnect (P1-5)
                store.update_session(current_session)
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
async def get_session(
    session_id: str,
    bot_id: str = Depends(validate_bot_id),
    _key: APIKeyRecord = Depends(require_bot_api_key),
) -> dict[str, Any]:
    """Get current session state and transcript."""
    store = get_session_store(bot_id)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Not found")

    # Verify session belongs to this bot
    if session.bot_id != bot_id:
        raise HTTPException(404, "Not found")

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
    session_id: str,
    req: FeedbackRequest,
    bot_id: str = Depends(validate_bot_id),
    _key: APIKeyRecord = Depends(require_bot_api_key),
) -> dict[str, str]:
    """Record user feedback for a turn."""
    store = get_session_store(bot_id)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Not found")

    store.add_feedback(session_id, req.turn_id, req.rating, req.comment)
    return {"status": "recorded"}


    # Note: /traces endpoint removed from public API (P1-2).
    # Traces are accessible via the admin dashboard API only.
