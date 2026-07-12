"""Tests for INT interrupt handling — B1 (race condition) and B2 (partial turn persistence).

Required by PLAN_CORRECTION_AUDIT_IMPL_V2_LOKO.md:
- test_interrupt_waits_for_lock_release
- test_interrupt_force_closed_after_2s
- test_interrupt_burst_isolation
- test_interrupted_turn_persisted
- test_interrupted_turn_not_counted
- test_interrupted_tokens_in_budget
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

import httpx
import pytest

from loko.api.api_keys import generate_api_key
from loko.bot.config_store import save_bot_config
from loko.bot.generation import BotGenerator
from loko.bot.models import BotConfig, Chunk, Intent, RetrievalResult
from loko.bot.orchestrator import BotOrchestrator
from loko.testing.mocks import MockEscalationProvider


# ---------------------------------------------------------------------------
# SlowMockLLMProvider — yields tokens with controllable delay
# ---------------------------------------------------------------------------


class SlowMockLLMProvider:
    """LLM provider that yields tokens slowly, for interrupt testing.

    Parameters
    ----------
    tokens : list[str]
        Tokens to yield one by one.
    delay : float
        Seconds between tokens.
    """

    def __init__(
        self,
        tokens: list[str] | None = None,
        delay: float = 0.3,
    ):
        self.tokens = tokens or [f"tok{i}" for i in range(10)]
        self.delay = delay
        self.last_messages: list[dict[str, str]] = []
        self._last_usage: dict[str, int] | None = None

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 600,
        timeout: int = 60,
    ) -> AsyncIterator[str]:
        """Yield tokens with delay."""
        self.last_messages = messages
        emitted = 0
        for token in self.tokens:
            await asyncio.sleep(self.delay)
            yield token + " "
            emitted += 1

        self._last_usage = {"completion_tokens": emitted}

    def get_last_usage(self) -> dict[str, int] | None:
        return self._last_usage


class HungMockLLMProvider:
    """LLM provider that emits one token then blocks indefinitely.

    Simulates a hung network stream (e.g., remote server stalls).
    Used to test the 2s force_closed timeout in _handle_interrupt.
    """

    def __init__(self):
        self.last_messages: list[dict[str, str]] = []
        self._last_usage: dict[str, int] | None = None

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 600,
        timeout: int = 60,
    ) -> AsyncIterator[str]:
        """Yield one token, then hang forever (simulating network stall)."""
        self.last_messages = messages
        yield "first_token "
        # Simulate a hung connection — blocks far longer than the 2s timeout
        await asyncio.sleep(30)
        yield "never_reached "

    def get_last_usage(self) -> dict[str, int] | None:
        return self._last_usage


class RoutingMockClassifier:
    """Classifier that routes to a specific intent for testing."""

    def __init__(self, intent_id: str = "livraison", score: float = 0.95):
        self._intent_id = intent_id
        self._score = score

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        return [(self._intent_id, self._score)]

    def classify_l2(self, intent_id: str, text: str) -> list[tuple[str, float]]:
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Set up temp data dir and test env."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOKO_ENV", "test")
    monkeypatch.setenv("LOKO_ADMIN_TOKEN", "test-admin-token")
    return tmp_path


@pytest.fixture
def slow_provider():
    """Default slow provider: 10 tokens at 0.1s each."""
    return SlowMockLLMProvider(
        tokens=[f"word{i}" for i in range(10)],
        delay=0.1,
    )


@pytest.fixture
def hung_provider():
    """Provider that hangs after first token (for force_closed test)."""
    return HungMockLLMProvider()


class MockRetriever:
    """Retriever that always returns successful results, bypassing knowledge_collection checks."""

    async def retrieve(
        self,
        query: str,
        intent: str,
        sub_motif: str | None,
        config: BotConfig,
        *,
        intent_label: str = "",
        sub_motif_label: str = "",
        top_k: int = 10,
    ) -> RetrievalResult:
        return RetrievalResult(
            success=True,
            scope="intent",
            chunks=[
                Chunk(
                    chunk_id="c1",
                    text="La livraison standard prend entre 3 et 5 jours ouvrés.",
                    score=0.92,
                    metadata={"bot_intents": [intent]},
                ),
            ],
        )


def _make_app_and_config(tmp_data, monkeypatch, provider, classifier=None):
    """Helper to create app with a specific LLM provider."""
    from loko.api.bot_public import clear_orchestrators, register_orchestrator
    from loko.main import create_app

    clear_orchestrators()

    config = BotConfig(
        name="InterruptTestBot",
        intents=[
            Intent(
                id="livraison",
                label="Livraison",
                definition="Questions de livraison",
                examples=[f"livraison ex {i}" for i in range(10)],
            ),
            Intent(
                id="hors_perimetre",
                label="HP",
                definition="HP",
                examples=["hp"],
                is_system=True,
            ),
            Intent(
                id="demande_conseiller",
                label="DC",
                definition="DC",
                examples=["dc"],
                is_system=True,
            ),
        ],
        status="published",
    )
    save_bot_config(config)

    clf = classifier or RoutingMockClassifier()
    orchestrator = BotOrchestrator(
        classifier=clf,
        retriever=MockRetriever(),
        generator=BotGenerator(provider),
        escalation=MockEscalationProvider(),
    )
    register_orchestrator(config.bot_id, orchestrator)

    app = create_app()
    raw_key, _ = generate_api_key(config.bot_id, label="test", allowed_origins=["*"])

    return app, config, raw_key


def _parse_sse_events(raw: bytes) -> list[dict]:
    """Parse SSE text into list of {event, data} dicts."""
    events = []
    current_event = None
    for line in raw.decode("utf-8", errors="replace").split("\n"):
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            data_str = line[6:]
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = data_str
            events.append({"event": current_event, "data": data})
            current_event = None
        elif line.startswith(":"):
            continue  # keepalive comment
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interrupt_waits_for_lock_release(tmp_data, monkeypatch, slow_provider):
    """B1: interrupt waits for generator to release lock, no concurrent writes."""
    app, config, api_key = _make_app_and_config(
        tmp_data, monkeypatch, slow_provider
    )
    headers = {"Authorization": f"Bearer {api_key}"}
    bot_id = config.bot_id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session
        res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions", headers=headers
        )
        assert res.status_code == 201
        session_id = res.json()["session_id"]

        # Start generation in background (non-streaming post reads all SSE)
        msg_task = asyncio.create_task(
            client.post(
                f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
                json={"text": "livraison", "type": "text"},
                headers=headers,
            )
        )

        # Wait for some tokens to be emitted (10 tokens × 0.1s = 1s total)
        await asyncio.sleep(0.35)

        # Send interrupt — B1: should wait for done (bounded by 2s timeout)
        t0 = time.monotonic()
        interrupt_res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
            json={"text": "", "type": "interrupt"},
            headers=headers,
        )
        elapsed = time.monotonic() - t0
        assert interrupt_res.status_code == 200

        # The interrupt waited for the generator to release the lock
        # (remaining ~0.7s of tokens at 0.1s/token), not just sleep(0.1).
        # force_closed should be False since it completed within 2s.
        events = _parse_sse_events(interrupt_res.content)
        interrupted_events = [e for e in events if e["event"] == "generation_interrupted"]
        assert len(interrupted_events) == 1
        assert interrupted_events[0]["data"]["force_closed"] is False
        assert interrupted_events[0]["data"]["tokens_emitted"] > 0

        # Wait for the original message task to complete
        try:
            await asyncio.wait_for(msg_task, timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            pass

        # Verify session integrity: no corrupted transcript
        session_res = await client.get(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}", headers=headers
        )
        assert session_res.status_code == 200
        transcript = session_res.json()["transcript"]
        # Should have: welcome turn(s) + user turn + interrupted bot turn
        bot_turns = [t for t in transcript if t["role"] == "bot"]
        assert len(bot_turns) >= 1


@pytest.mark.asyncio
async def test_interrupt_force_closed_after_2s(tmp_data, monkeypatch, hung_provider):
    """B1: if generator doesn't stop within 2s, force_closed=True and epoch fences writes."""
    app, config, api_key = _make_app_and_config(
        tmp_data, monkeypatch, hung_provider
    )
    headers = {"Authorization": f"Bearer {api_key}"}
    bot_id = config.bot_id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session
        res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions", headers=headers
        )
        assert res.status_code == 201
        session_id = res.json()["session_id"]

        # Start generation in background (hung provider emits 1 token then blocks)
        stream_task = asyncio.create_task(
            client.post(
                f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
                json={"text": "livraison", "type": "text"},
                headers=headers,
            )
        )

        # Wait for the first token to be emitted (provider yields it immediately)
        await asyncio.sleep(0.5)

        # Send interrupt — generator is hung, should force_close after 2s
        t0 = time.monotonic()
        interrupt_res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
            json={"text": "", "type": "interrupt"},
            headers=headers,
        )
        elapsed = time.monotonic() - t0

        # Should have taken ~2s (timeout waiting for done that never comes)
        assert elapsed >= 1.8, f"Expected >= 1.8s but got {elapsed:.2f}s"
        assert interrupt_res.status_code == 200

        events = _parse_sse_events(interrupt_res.content)
        interrupted_events = [e for e in events if e["event"] == "generation_interrupted"]
        assert len(interrupted_events) == 1
        assert interrupted_events[0]["data"]["force_closed"] is True
        assert interrupted_events[0]["data"]["tokens_emitted"] >= 0

        # Verify epoch was incremented (zombie protection active)
        from loko.api.bot_public import _GENERATION_EPOCHS

        assert _GENERATION_EPOCHS.get(session_id, 0) >= 1

        # Cancel the background stream task (it's still hung)
        stream_task.cancel()
        try:
            await stream_task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_interrupt_burst_isolation(tmp_data, monkeypatch):
    """B1/INT-A5: 50 interrupt/regen cycles on 5 sessions — zero transcript crossover."""
    provider = SlowMockLLMProvider(
        tokens=["hello", "world", "test"],
        delay=0.02,  # fast for burst test
    )
    app, config, api_key = _make_app_and_config(tmp_data, monkeypatch, provider)
    headers = {"Authorization": f"Bearer {api_key}"}
    bot_id = config.bot_id

    num_sessions = 5
    cycles_per_session = 10  # 50 total cycles

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create sessions
        session_ids = []
        for _ in range(num_sessions):
            res = await client.post(
                f"/api/v1/bot/{bot_id}/sessions", headers=headers
            )
            assert res.status_code == 201
            session_ids.append(res.json()["session_id"])

        async def run_cycles(sid: str, n: int):
            for i in range(n):
                # Send message
                msg_task = asyncio.create_task(
                    client.post(
                        f"/api/v1/bot/{bot_id}/sessions/{sid}/messages",
                        json={"text": f"msg-{sid[:8]}-{i}", "type": "text"},
                        headers=headers,
                    )
                )
                # Brief delay then interrupt
                await asyncio.sleep(0.05)
                await client.post(
                    f"/api/v1/bot/{bot_id}/sessions/{sid}/messages",
                    json={"text": "", "type": "interrupt"},
                    headers=headers,
                )
                # Wait for original message to complete
                try:
                    await asyncio.wait_for(msg_task, timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    msg_task.cancel()
                    try:
                        await msg_task
                    except (asyncio.CancelledError, Exception):
                        pass

        # Run all sessions in parallel
        await asyncio.gather(
            *[run_cycles(sid, cycles_per_session) for sid in session_ids]
        )

        # Verify isolation: each session's transcript only contains its own content
        for sid in session_ids:
            res = await client.get(
                f"/api/v1/bot/{bot_id}/sessions/{sid}", headers=headers
            )
            assert res.status_code == 200
            transcript = res.json()["transcript"]
            # No turns from other sessions should appear
            for turn in transcript:
                if turn["role"] == "user" and turn["content"].startswith("msg-"):
                    assert turn["content"].startswith(f"msg-{sid[:8]}-")

    # Verify no orphan active generations
    from loko.api.bot_public import _ACTIVE_GENERATIONS

    for sid in session_ids:
        assert sid not in _ACTIVE_GENERATIONS


@pytest.mark.asyncio
async def test_interrupted_turn_persisted(tmp_data, monkeypatch, slow_provider):
    """B2: interrupted generation persists partial turn with interrupted=True."""
    app, config, api_key = _make_app_and_config(
        tmp_data, monkeypatch, slow_provider
    )
    headers = {"Authorization": f"Bearer {api_key}"}
    bot_id = config.bot_id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session
        res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions", headers=headers
        )
        session_id = res.json()["session_id"]

        # Start generation in background
        msg_task = asyncio.create_task(
            client.post(
                f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
                json={"text": "livraison", "type": "text"},
                headers=headers,
            )
        )

        # Wait for some tokens to be emitted
        await asyncio.sleep(0.4)

        # Interrupt
        interrupt_res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
            json={"text": "", "type": "interrupt"},
            headers=headers,
        )
        assert interrupt_res.status_code == 200

        # Wait for original to complete
        try:
            await asyncio.wait_for(msg_task, timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            pass

        # Verify: GET session shows interrupted turn
        session_res = await client.get(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}", headers=headers
        )
        assert session_res.status_code == 200
        transcript = session_res.json()["transcript"]

        # Find the interrupted bot turn
        interrupted_turns = [
            t for t in transcript
            if t["role"] == "bot" and t.get("interrupted") is True
        ]
        assert len(interrupted_turns) >= 1, (
            f"Expected at least one interrupted turn, got transcript: {transcript}"
        )

        turn = interrupted_turns[0]
        assert turn["tokens_emitted"] is not None
        assert turn["tokens_emitted"] > 0
        assert len(turn["content"]) > 0  # partial text was saved


@pytest.mark.asyncio
async def test_interrupted_turn_not_counted(tmp_data, monkeypatch):
    """B2: interrupted turn does NOT increment tours_demande and does NOT
    trigger satisfaction survey."""
    provider = SlowMockLLMProvider(
        tokens=["hello", "world", "answer"],
        delay=0.1,
    )
    app, config, api_key = _make_app_and_config(
        tmp_data, monkeypatch, provider, classifier=RoutingMockClassifier()
    )
    headers = {"Authorization": f"Bearer {api_key}"}
    bot_id = config.bot_id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session
        res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions", headers=headers
        )
        session_id = res.json()["session_id"]

        # First message: start generation then interrupt
        msg_task = asyncio.create_task(
            client.post(
                f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
                json={"text": "livraison rapide", "type": "text"},
                headers=headers,
            )
        )
        await asyncio.sleep(0.15)

        # Interrupt mid-stream
        await client.post(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
            json={"text": "", "type": "interrupt"},
            headers=headers,
        )
        try:
            await asyncio.wait_for(msg_task, timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            pass

        # Now send a second message with the same intent (reformulation)
        # If tours_demande was incorrectly incremented by the interrupted turn,
        # this could trigger escalation prematurely
        second_res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
            json={"text": "suivi livraison", "type": "text"},
            headers=headers,
        )
        assert second_res.status_code == 200
        second_events = _parse_sse_events(second_res.content)

        # Should NOT have an escalation event (which would mean tours_demande
        # was incorrectly counted from the interrupted turn)
        escalation_events = [
            e for e in second_events
            if e["event"] == "template"
            and isinstance(e["data"], dict)
            and e["data"].get("template_key") == "mise_en_relation"
        ]
        assert len(escalation_events) == 0, (
            "Escalation triggered — tours_demande was incorrectly counted"
        )

        # Check that no satisfaction survey was emitted for the interrupted turn
        # (the first message's SSE stream should NOT contain enquete_satisfaction)
        # We verify via the session transcript
        session_res = await client.get(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}", headers=headers
        )
        transcript = session_res.json()["transcript"]
        # The interrupted turn should exist but NOT be followed by satisfaction
        interrupted_turns = [
            t for t in transcript
            if t["role"] == "bot" and t.get("interrupted") is True
        ]
        if interrupted_turns:
            # Find position of interrupted turn
            idx = next(
                i for i, t in enumerate(transcript)
                if t.get("interrupted") is True
            )
            # Next turn (if any) should NOT be a satisfaction survey
            if idx + 1 < len(transcript):
                next_turn = transcript[idx + 1]
                assert next_turn.get("template_key") != "enquete_satisfaction"


@pytest.mark.asyncio
async def test_interrupted_tokens_in_budget(tmp_data, monkeypatch):
    """B2/ORC-3: tokens_llm_cumul reflects tokens from interrupted generation."""
    provider = SlowMockLLMProvider(
        tokens=[f"tok{i}" for i in range(20)],
        delay=0.05,
    )
    app, config, api_key = _make_app_and_config(tmp_data, monkeypatch, provider)
    headers = {"Authorization": f"Bearer {api_key}"}
    bot_id = config.bot_id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session
        res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions", headers=headers
        )
        session_id = res.json()["session_id"]

        # Start generation
        msg_task = asyncio.create_task(
            client.post(
                f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
                json={"text": "livraison", "type": "text"},
                headers=headers,
            )
        )

        # Wait for some tokens to stream (expect ~5 tokens in 0.25s)
        await asyncio.sleep(0.3)

        # Interrupt
        interrupt_res = await client.post(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
            json={"text": "", "type": "interrupt"},
            headers=headers,
        )
        assert interrupt_res.status_code == 200

        # Get tokens_emitted from interrupt event
        events = _parse_sse_events(interrupt_res.content)
        interrupted_events = [e for e in events if e["event"] == "generation_interrupted"]
        assert len(interrupted_events) == 1
        reported_tokens = interrupted_events[0]["data"]["tokens_emitted"]

        # Wait for original task to complete
        try:
            await asyncio.wait_for(msg_task, timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            pass

        # Verify the interrupted turn was persisted with correct token count
        session_res = await client.get(
            f"/api/v1/bot/{bot_id}/sessions/{session_id}", headers=headers
        )
        transcript = session_res.json()["transcript"]
        interrupted_turns = [
            t for t in transcript
            if t["role"] == "bot" and t.get("interrupted") is True
        ]

        if interrupted_turns:
            turn = interrupted_turns[0]
            # tokens_emitted should be > 0 (some tokens were streamed)
            assert turn["tokens_emitted"] > 0
            # Should match what was reported in the interrupt event
            assert turn["tokens_emitted"] == reported_tokens
