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
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from loko.api.api_keys import APIKeyRecord
from loko.api.auth import require_bot_api_key, validate_bot_id
from loko.api.rate_limit import (
    RATE_FEEDBACK,
    RATE_MESSAGES,
    RATE_READ,
    RATE_SESSIONS,
    get_limiter,
)
import os
import time
from collections import defaultdict
from pathlib import Path
from loko.bot.classifier.loader import load_classifier, load_search_backend
from loko.bot.config_store import load_bot_config
from loko.bot.errors import ComponentUnavailableError
from loko.bot.timeout import check_and_apply_timeout
from loko.bot.generation import BotGenerator
from loko.bot.maintenance import is_maintenance, get_maintenance_message
from loko.bot.models import BotConfig, BotState
from loko.bot.orchestrator import BotOrchestrator, SSEEvent
from loko.bot.retrieval_filter import FilteredRetriever
from loko.bot.session_store import SessionStore, get_bot_dir, get_session_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bot", tags=["bot-runtime"])

# Rate limiter (None if slowapi not installed — desktop mode)
_limiter = get_limiter()


def _apply_limit(rate: str):
    """Decorator that applies slowapi rate limiting if available, no-op otherwise."""
    if _limiter is not None:
        return _limiter.limit(rate)

    def _noop(func):
        return func
    return _noop


# ---------------------------------------------------------------------------
# Q5: Demo bot rate limiter (in-memory, per IP, separate from regular limits)
# ---------------------------------------------------------------------------

_DEMO_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_DEMO_WINDOW_SECONDS = 3600  # 1 hour
_DEMO_MAX_MESSAGES = int(os.environ.get("LOKO_RATE_DEMO_MAX", "20"))


def _check_demo_rate(request: Request) -> None:
    """Q5: enforce tighter rate limit on demo bot messages."""
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    attempts = _DEMO_ATTEMPTS[ip]
    _DEMO_ATTEMPTS[ip] = [t for t in attempts if now - t < _DEMO_WINDOW_SECONDS]
    if len(_DEMO_ATTEMPTS[ip]) >= _DEMO_MAX_MESSAGES:
        raise HTTPException(429, "Rate limit exceeded for demo bot.")
    _DEMO_ATTEMPTS[ip].append(now)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class MessageRequest(BaseModel):
    """User message sent to the bot.

    INT: type="interrupt" cancels any active generation.
    If text is non-empty with interrupt, the text is processed
    as a new message immediately after cancellation.
    """
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=2000)
    type: Literal["text", "button_click", "interrupt"] = "text"


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
_SESSION_LOCKS_MAX = 10_000  # R4: bounded size to prevent unbounded memory growth

# INT: active generation tracking per session for interrupt support

@dataclass
class _ActiveGeneration:
    """Tracks an in-flight generation for interrupt support (INT)."""
    cancel: asyncio.Event
    turn_id: str = ""
    tokens_emitted: int = 0

_ACTIVE_GENERATIONS: dict[str, _ActiveGeneration] = {}  # session_id → generation state


def _get_orchestrator(bot_id: str, config: BotConfig) -> BotOrchestrator:
    """Get or create the orchestrator for a bot.

    Fail-closed policy (P0-6, A3, A5, C7, K2):
    - Draft bots cannot be served at runtime (409).
    - Published bots use real classifier — no mock fallback.
    - LLM provider built from LOKO_LLM_* env vars (K2).
    - Tests must use register_orchestrator() to inject mocks.
    - ComponentUnavailableError on any missing component.

    R2-b: Uses SQLiteSearchBackend (persistent) when documents exist.
    """
    if bot_id not in _ORCHESTRATORS:
        # A3: classifier — no mock fallback, raises ComponentUnavailableError
        classifier = load_classifier(bot_id)

        # R2-b: knowledge store
        backend = load_search_backend(bot_id)
        retriever = FilteredRetriever(backend)

        # K2/LLM: provider from env vars or per-bot config (BYO key)
        from loko.bot.llm import build_llm_provider

        llm_provider = build_llm_provider(bot_id, config.llm)
        generator = BotGenerator(llm_provider, config.llm)

        # PRO-4: real escalation providers (webhook, email, mock)
        from loko.bot.escalation import EscalationConfig, build_escalation_provider

        escalation_provider_name = os.environ.get("LOKO_ESCALATION_PROVIDER", "mock")
        try:
            esc_config = EscalationConfig(provider=escalation_provider_name)
            # Load per-bot escalation config if available
            esc_config_path = get_bot_dir(bot_id) / "escalation.json" if hasattr(config, 'bot_id') else None
            if esc_config_path and esc_config_path.is_file():
                import json as _esc_json
                esc_data = _esc_json.loads(esc_config_path.read_text(encoding="utf-8"))
                esc_config = EscalationConfig(**esc_data)

            secret_store = None
            try:
                from loko.security.secret_store import get_secret_store
                secret_store = get_secret_store()
            except Exception:
                pass

            escalation = build_escalation_provider(esc_config, secret_store)
        except Exception as exc:
            logger.warning("Could not build escalation provider: %s — using mock", exc)
            from loko.testing.mocks import MockEscalationProvider
            escalation = MockEscalationProvider()

        orchestrator = BotOrchestrator(
            classifier=classifier,
            retriever=retriever,
            generator=generator,
            escalation=escalation,
        )
        _ORCHESTRATORS[bot_id] = orchestrator

    return _ORCHESTRATORS[bot_id]


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


def purge_session_locks(active_session_ids: set[str] | None = None) -> int:
    """Remove locks for sessions that no longer exist (R4).

    Called by the background purge task.  Removes entries whose lock is
    not currently held and whose session_id is not in the active set.
    Also enforces the bounded size by evicting unlocked entries when
    the dict exceeds _SESSION_LOCKS_MAX.

    Returns the number of entries removed.
    """
    removed = 0
    to_remove: list[str] = []

    for sid, lock in _SESSION_LOCKS.items():
        if lock.locked():
            continue  # in use — keep
        if active_session_ids is not None and sid not in active_session_ids:
            to_remove.append(sid)

    # Also enforce max size: evict oldest unlocked entries
    if len(_SESSION_LOCKS) > _SESSION_LOCKS_MAX:
        for sid, lock in _SESSION_LOCKS.items():
            if not lock.locked() and sid not in to_remove:
                to_remove.append(sid)
            if len(_SESSION_LOCKS) - len(to_remove) <= _SESSION_LOCKS_MAX:
                break

    for sid in to_remove:
        _SESSION_LOCKS.pop(sid, None)
        removed += 1

    return removed


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
@_apply_limit(RATE_SESSIONS)
async def create_session(
    request: Request,
    bot_id: str = Depends(validate_bot_id),
    _key: APIKeyRecord = Depends(require_bot_api_key),
) -> dict[str, Any]:
    """Create a new conversation session and return the welcome message."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    # Q5: demo bot rate limit
    if config.demo:
        _check_demo_rate(request)

    # PRO-7: maintenance mode — return template, not an error
    if is_maintenance(bot_id):
        return _maintenance_response(bot_id, config)

    # Fail-closed: draft bots cannot serve runtime (P0-6)
    if config.status != "published":
        raise HTTPException(409, "Bot is not published")

    # PRO-6: quota check on session creation
    _check_api_key_quota(_key, "sessions")

    # A5: ComponentUnavailableError → 503 (no session created)
    try:
        orchestrator = _get_orchestrator(bot_id, config)
    except ComponentUnavailableError as exc:
        logger.error("Bot %s unavailable: %s", bot_id, exc)
        raise HTTPException(503, {"error": "bot_unavailable", "detail": exc.reason})

    store = get_session_store(bot_id)

    session, events = await orchestrator.create_and_start_session(config)
    store.create_session(session)

    # Record welcome turns
    for turn in session.transcript:
        store.add_turn(session.session_id, turn)

    # PRO-6: increment session counter
    _increment_api_key_quota(_key, "sessions")

    return {
        "session_id": session.session_id,
        "bot_id": bot_id,
        "state": session.state.value,
        "events": [{"event": e.event, "data": e.data} for e in events],
    }


@router.post("/{bot_id}/sessions/{session_id}/messages")
@_apply_limit(RATE_MESSAGES)
async def send_message(
    request: Request,
    session_id: str,
    req: MessageRequest,
    bot_id: str = Depends(validate_bot_id),
    _key: APIKeyRecord = Depends(require_bot_api_key),
) -> StreamingResponse:
    """Process a user message and stream the response as SSE."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    # Q5: demo bot rate limit
    if config.demo:
        _check_demo_rate(request)

    # PRO-7: maintenance mode — close session gracefully
    if is_maintenance(bot_id):
        return _maintenance_message_response(bot_id, config, session_id)

    # PRO-6: quota check on message send
    _check_api_key_quota(_key, "messages")

    store = get_session_store(bot_id)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Not found")

    # R5: check inactivity timeout before processing
    session, timeout_actions, timed_out = check_and_apply_timeout(session, config)
    if timed_out:
        # Persist the timeout transition and stream it
        store.update_session(session)
        from loko.bot.orchestrator import SSEEvent as _SSE
        from loko.bot.models import EmitTemplate as _ET, CloseSession as _CS
        from loko.bot.templates import render_template, resolve_template

        async def _timeout_stream() -> AsyncIterator[str]:
            yield _sse_encode(_SSE(event="state", data={"state": session.state.value}))
            for action in timeout_actions:
                if isinstance(action, _ET):
                    template = resolve_template(
                        config.templates, action.key, config.tone_profile,
                    )
                    lang = config.language if config.language != "auto" else "fr"
                    text = render_template(template, lang, action.variables)
                    yield _sse_encode(_SSE(
                        event="template",
                        data={
                            "content": text,
                            "template_key": action.key.value,
                            "buttons": action.buttons,
                        },
                    ))
                elif isinstance(action, _CS):
                    yield _sse_encode(_SSE(
                        event="end_of_turn", data={"reason": action.reason},
                    ))
            # R4: clean up lock for timed-out session
            _SESSION_LOCKS.pop(session_id, None)

        return StreamingResponse(
            _timeout_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if session.state in (BotState.FIN, BotState.TIMEOUT, BotState.CLOTURE_DOUCE, BotState.FIN_FERME):
        raise HTTPException(400, "Session has ended")

    # --- INT: handle interrupt type ---
    if req.type == "interrupt":
        return await _handle_interrupt(session_id, session, req, bot_id, config, store)

    # Concurrency guard: reject if another message is being processed (P1-5)
    lock = _SESSION_LOCKS.setdefault(session_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "A message is already being processed for this session")

    # A5: ComponentUnavailableError → 503
    try:
        orchestrator = _get_orchestrator(bot_id, config)
    except ComponentUnavailableError as exc:
        logger.error("Bot %s unavailable: %s", bot_id, exc)
        raise HTTPException(503, {"error": "bot_unavailable", "detail": exc.reason})

    # INT: register active generation for interrupt support
    active_gen = _ActiveGeneration(cancel=asyncio.Event())
    _ACTIVE_GENERATIONS[session_id] = active_gen

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
                    # INT: check cancellation signal
                    if active_gen.cancel.is_set():
                        break
                    # INT: track tokens for interrupt metadata
                    if sse_event.event == "generation_delta":
                        active_gen.tokens_emitted += 1
                    yield _sse_encode(sse_event)
            finally:
                # Persist session state even on client disconnect (P1-5)
                store.update_session(current_session)
                for turn in current_session.transcript[len(session.transcript):]:
                    store.add_turn(current_session.session_id, turn)

                # R4: release session lock when session reaches terminal state
                if current_session.state in (BotState.FIN, BotState.TIMEOUT, BotState.CLOTURE_DOUCE, BotState.FIN_FERME):
                    _SESSION_LOCKS.pop(session_id, None)
                # INT: clean up active generation reference
                _ACTIVE_GENERATIONS.pop(session_id, None)

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
@_apply_limit(RATE_READ)
async def get_session(
    request: Request,
    session_id: str,
    bot_id: str = Depends(validate_bot_id),
    _key: APIKeyRecord = Depends(require_bot_api_key),
) -> dict[str, Any]:
    """Get current session state and transcript."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    store = get_session_store(bot_id)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Not found")

    # Verify session belongs to this bot
    if session.bot_id != bot_id:
        raise HTTPException(404, "Not found")

    # R5: check and apply inactivity timeout on read
    session, timeout_actions, timed_out = check_and_apply_timeout(session, config)
    if timed_out:
        store.update_session(session)
        _SESSION_LOCKS.pop(session_id, None)

    return {
        "session_id": session.session_id,
        "bot_id": session.bot_id,
        "state": session.state.value,
        "transcript": [t.model_dump(mode="json") for t in session.transcript],
        "current_intent": session.current_intent,
        "current_sub_motif": session.current_sub_motif,
    }


@router.post("/{bot_id}/sessions/{session_id}/feedback")
@_apply_limit(RATE_FEEDBACK)
async def add_feedback(
    request: Request,
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

    turn_id = req.turn_id
    known_turn_ids = {turn.turn_id for turn in session.transcript}
    if turn_id not in known_turn_ids:
        latest_bot_turn = next(
            (turn for turn in reversed(session.transcript) if turn.role == "bot"),
            None,
        )
        if latest_bot_turn:
            turn_id = latest_bot_turn.turn_id

    store.add_feedback(session_id, turn_id, req.rating, req.comment)
    return {"status": "recorded"}


# ---------------------------------------------------------------------------
# INT: Interrupt handler (§3.2)
# ---------------------------------------------------------------------------

async def _handle_interrupt(
    session_id: str,
    session: Any,
    req: MessageRequest,
    bot_id: str,
    config: BotConfig,
    store: SessionStore,
) -> StreamingResponse:
    """Handle an interrupt request (INT lot).

    - Cancel any active generation task for this session
    - If text is empty: return to listening state
    - If text is non-empty: cancel then process the new text
    - If no active generation: no-op (idempotent)
    """
    active_gen = _ACTIVE_GENERATIONS.get(session_id)

    if active_gen is None or active_gen.cancel.is_set():
        # No active generation — idempotent no-op (INT-A4)
        async def _noop_stream() -> AsyncIterator[str]:
            yield _sse_encode(SSEEvent(
                event="noop",
                data={"reason": "no_active_generation"},
            ))

        return StreamingResponse(
            _noop_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Signal cancellation to the active generation
    tokens_emitted = active_gen.tokens_emitted
    active_gen.cancel.set()
    # Give the generator a moment to notice and exit
    await asyncio.sleep(0.1)
    _ACTIVE_GENERATIONS.pop(session_id, None)

    async def _interrupt_stream() -> AsyncIterator[str]:
        # Emit generation_interrupted event with actual metadata
        yield _sse_encode(SSEEvent(
            event="generation_interrupted",
            data={"tokens_emitted": tokens_emitted},
        ))

        # If text is provided, process it as a new message
        if req.text.strip():
            try:
                orchestrator = _get_orchestrator(bot_id, config)
            except ComponentUnavailableError:
                return

            # Reload session (may have been updated by the cancelled task)
            current_session = store.get_session(session_id)
            if current_session is None:
                return

            # Reset to listening state for new classification
            current_session = current_session.model_copy(
                update={"state": BotState.ATTENTE_DEMANDE}
            )

            async for current_session, sse_event in orchestrator.process_message(
                current_session, req.text, config,
            ):
                yield _sse_encode(sse_event)

            store.update_session(current_session)

    return StreamingResponse(
        _interrupt_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


    # Note: /traces endpoint removed from public API (P1-2).
    # Traces are accessible via the admin dashboard API only.


# ---------------------------------------------------------------------------
# PRO-6: API key quota helpers
# ---------------------------------------------------------------------------

def _check_api_key_quota(
    key: APIKeyRecord,
    metric: str,
) -> None:
    """Check monthly quota for an API key. Raises 429 if exceeded.

    Test keys (PRO-3) are excluded from quota counting.
    """
    # PRO-3: test keys excluded from quota counting
    if getattr(key, "is_test", False) or getattr(key, "environment", "live") == "test":
        return

    # Check if quota config exists for this key
    from loko.bot.quota_usage import get_quota_usage_store, get_quota_reset_header

    store = get_quota_usage_store()

    # Load quota config for this key's bot
    config = load_bot_config(key.bot_id)
    if not config:
        return

    # Get quota config from bot config (if attached)
    quota_config = _get_quota_config(key.bot_id)
    if not quota_config:
        return  # No quotas configured

    if store.is_exceeded(key.key_id, quota_config, metric):
        raise HTTPException(
            429,
            {
                "error": "quota_exceeded",
                "metric": metric,
                "reset": get_quota_reset_header(),
            },
            headers={"X-Quota-Reset": get_quota_reset_header()},
        )


def _increment_api_key_quota(
    key: APIKeyRecord,
    metric: str,
    amount: int = 1,
) -> None:
    """Increment a quota counter for an API key.

    PRO-3: test keys are excluded from counting.
    """
    if getattr(key, "is_test", False) or getattr(key, "environment", "live") == "test":
        return

    from loko.bot.quota_usage import get_quota_usage_store
    store = get_quota_usage_store()
    store.increment(key.key_id, metric, amount)


def _get_quota_config(bot_id: str) -> Any:
    """Load quota config for a bot (from quota_configs directory)."""
    from loko.bot.quota_usage import QuotaConfig
    try:
        config_path = Path(os.environ.get("LOKO_DATA_DIR", "data")) / "quota_configs" / f"{bot_id}.json"
        if config_path.is_file():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return QuotaConfig(**data)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# PRO-7: Maintenance mode helpers
# ---------------------------------------------------------------------------

def _maintenance_response(bot_id: str, config: BotConfig) -> dict[str, Any]:
    """Return a maintenance response for session creation (200, not error)."""
    from loko.bot.templates import render_template, resolve_template
    from loko.bot.models import TemplateKey

    custom_msg = get_maintenance_message(bot_id)

    if custom_msg:
        text = custom_msg
    else:
        template = resolve_template(
            config.templates, TemplateKey.MAINTENANCE, config.tone_profile,
        )
        lang = config.language if config.language != "auto" else "fr"
        text = render_template(template, lang, {"nom_bot": config.name})

    return {
        "maintenance": True,
        "message": text,
        "bot_id": bot_id,
    }


def _maintenance_message_response(
    bot_id: str,
    config: BotConfig,
    session_id: str,
) -> StreamingResponse:
    """Stream maintenance template + close for existing session message."""
    from loko.bot.templates import render_template, resolve_template
    from loko.bot.models import TemplateKey

    custom_msg = get_maintenance_message(bot_id)

    if custom_msg:
        text = custom_msg
    else:
        template = resolve_template(
            config.templates, TemplateKey.MAINTENANCE, config.tone_profile,
        )
        lang = config.language if config.language != "auto" else "fr"
        text = render_template(template, lang, {"nom_bot": config.name})

    async def _maint_stream() -> AsyncIterator[str]:
        yield _sse_encode(SSEEvent(
            event="template",
            data={
                "content": text,
                "template_key": "maintenance",
                "buttons": None,
            },
        ))
        yield _sse_encode(SSEEvent(
            event="end_of_turn",
            data={"reason": "maintenance"},
        ))

        # Close the session
        store = get_session_store(bot_id)
        session = store.get_session(session_id)
        if session and session.state not in (BotState.FIN, BotState.TIMEOUT, BotState.CLOTURE_DOUCE, BotState.FIN_FERME):
            session = session.model_copy(update={"state": BotState.FIN})
            store.update_session(session)
        _SESSION_LOCKS.pop(session_id, None)

    return StreamingResponse(
        _maint_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
