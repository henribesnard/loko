"""Tests for V-lot corrections (Vigilance items).

V1: Streaming-level leak check (not just post-stream)
V2: SSRF DNS rebinding per-request resolution
V4: Budget check on button_click
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator
from unittest.mock import patch

import httpx
import pytest

from loko.api.api_keys import generate_api_key
from loko.bot.config_store import save_bot_config
from loko.bot.generation import BotGenerator
from loko.bot.guardrails import (
    check_response_leaks_streaming,
)
from loko.bot.models import BotConfig, Chunk, Intent, RetrievalResult
from loko.bot.orchestrator import BotOrchestrator
from loko.testing.mocks import MockEscalationProvider


# ---------------------------------------------------------------------------
# Mock LLM providers
# ---------------------------------------------------------------------------


class LeakyMockLLMProvider:
    """LLM provider that emits tokens containing a leaked API key (V1 test)."""

    # Build fake leaked key dynamically to avoid pre-commit secret detection
    _FAKE_KEY_PREFIX = "sk-"
    _FAKE_KEY_BODY = "a" * 26  # 26 chars → matches sk-[a-zA-Z0-9]{20,}

    def __init__(self):
        # Tokens that together form a leaked OpenAI-style key
        self.tokens = [
            "Here is ",
            "the key: ",
            self._FAKE_KEY_PREFIX,
            self._FAKE_KEY_BODY,
            " please use it.",
        ]
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
        emitted = 0
        for token in self.tokens:
            await asyncio.sleep(0.01)
            yield token
            emitted += 1
        self._last_usage = {"completion_tokens": emitted}

    def get_last_usage(self) -> dict[str, int] | None:
        return self._last_usage


class SafeMockLLMProvider:
    """LLM provider that emits clean tokens (no leaks)."""

    def __init__(self, tokens=None):
        self.tokens = tokens or ["Bonjour, ", "votre livraison ", "arrive bientôt."]
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
        emitted = 0
        for token in self.tokens:
            await asyncio.sleep(0.01)
            yield token
            emitted += 1
        self._last_usage = {"completion_tokens": emitted}

    def get_last_usage(self) -> dict[str, int] | None:
        return self._last_usage


class RoutingMockClassifier:
    """Classifier that routes to a specific intent."""

    def __init__(self, intent_id: str = "livraison", score: float = 0.95):
        self._intent_id = intent_id
        self._score = score

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        return [(self._intent_id, self._score)]

    def classify_l2(self, intent_id: str, text: str) -> list[tuple[str, float]]:
        return []


class MockRetriever:
    """Retriever that always returns successful results."""

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


def _make_app(tmp_data, monkeypatch, provider, classifier=None):
    """Create test app with specific LLM provider."""
    from loko.api.bot_public import clear_orchestrators, register_orchestrator
    from loko.main import create_app

    clear_orchestrators()

    config = BotConfig(
        name="VTestBot",
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
    return events


# ===========================================================================
# V1 Tests: Streaming-level leak detection
# ===========================================================================


class TestV1StreamingLeakCheck:
    """V1: Leak check must happen during streaming, not only post-stream."""

    def test_check_response_leaks_streaming_detects_key(self):
        """Unit test: streaming check detects API key in accumulated text."""
        text = "Here is the key: sk-" + "a" * 26 + " please use it."
        result = check_response_leaks_streaming(text)
        assert result is not None
        assert "sk-" in result

    def test_check_response_leaks_streaming_clean(self):
        """Unit test: streaming check passes clean text."""
        result = check_response_leaks_streaming("Bonjour, votre livraison arrive bientôt.")
        assert result is None

    def test_check_response_leaks_streaming_sliding_window(self):
        """Unit test: only checks tail portion for efficiency."""
        # A very long clean prefix + a leak at the end
        long_prefix = "A" * 1000
        text = long_prefix + " sk-" + "a" * 26
        result = check_response_leaks_streaming(text)
        # Should still detect (leak is within last 200 chars)
        assert result is not None

    @pytest.mark.asyncio
    async def test_leak_halts_streaming_no_token_emitted(self, tmp_data, monkeypatch):
        """V1 integration: leaky token is NOT emitted to client; replacement sent."""
        app, config, api_key = _make_app(
            tmp_data, monkeypatch, LeakyMockLLMProvider()
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

            # Send message that triggers leaky generation
            msg_res = await client.post(
                f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
                json={"text": "livraison", "type": "text"},
                headers=headers,
            )
            assert msg_res.status_code == 200

            events = _parse_sse_events(msg_res.content)
            # The leaked key should NOT appear in generation_delta events
            delta_events = [e for e in events if e["event"] == "generation_delta"]
            all_tokens = "".join(
                e["data"].get("token", "") for e in delta_events
            )
            assert "sk-" + "a" * 26 not in all_tokens

            # A generation_replace event should be present (V1 correction)
            replace_events = [e for e in events if e["event"] == "generation_replace"]
            assert len(replace_events) == 1
            assert replace_events[0]["data"]["reason"] == "leak_detected"


# ===========================================================================
# V2 Tests: SSRF DNS rebinding per-request resolution
# ===========================================================================


class TestV2SSRFPerRequest:
    """V2: resolve_and_pin must be called per-request, not just at init."""

    def test_provider_stores_original_url(self):
        """V2: OpenAICompatProvider stores original_url for per-request resolution."""
        from loko.bot.llm.openai_compat import OpenAICompatProvider

        provider = OpenAICompatProvider(
            base_url="https://1.2.3.4/v1",
            api_key="test-key",
            model="test-model",
            host_header="api.example.com",
            original_url="https://api.example.com/v1",
        )
        assert provider._original_url == "https://api.example.com/v1"

    def test_resolve_request_url_desktop_mode(self, monkeypatch):
        """V2: In desktop mode, _resolve_request_url returns base_url as-is."""
        from loko.bot.llm.openai_compat import OpenAICompatProvider

        monkeypatch.setenv("LOKO_MODE", "desktop")
        provider = OpenAICompatProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            original_url="https://api.example.com/v1",
        )
        url, host = provider._resolve_request_url()
        assert url == "https://api.example.com/v1"
        assert host is None

    def test_resolve_request_url_server_mode_calls_resolve_and_pin(self, monkeypatch):
        """V2: In server mode, _resolve_request_url calls resolve_and_pin per-request."""
        from loko.bot.llm.openai_compat import OpenAICompatProvider

        monkeypatch.setenv("LOKO_MODE", "server")

        provider = OpenAICompatProvider(
            base_url="https://93.184.216.34/v1",
            api_key="test-key",
            model="test-model",
            host_header="example.com",
            original_url="https://example.com/v1",
        )

        # Mock resolve_and_pin to track calls
        call_count = {"n": 0}

        def mock_resolve_and_pin(url):
            call_count["n"] += 1
            return "https://93.184.216.34/v1", "example.com"

        with patch("loko.security.ssrf.resolve_and_pin", mock_resolve_and_pin):
            url1, host1 = provider._resolve_request_url()
            url2, host2 = provider._resolve_request_url()

        # Called TWICE (per-request, not cached)
        assert call_count["n"] == 2
        assert host1 == "example.com"
        assert host2 == "example.com"

    def test_resolve_request_url_blocks_rebinding(self, monkeypatch):
        """V2: If DNS rebinds to private IP, request is blocked."""
        from loko.bot.llm.openai_compat import LLMProviderError, OpenAICompatProvider
        from loko.security.ssrf import SSRFError

        monkeypatch.setenv("LOKO_MODE", "server")

        provider = OpenAICompatProvider(
            base_url="https://93.184.216.34/v1",
            api_key="test-key",
            model="test-model",
            host_header="evil.example.com",
            original_url="https://evil.example.com/v1",
        )

        # Mock resolve_and_pin to simulate rebinding to private IP
        def mock_resolve_rebind(url):
            raise SSRFError(url, "Resolved to private IP 192.168.1.1")

        with patch("loko.security.ssrf.resolve_and_pin", mock_resolve_rebind):
            with pytest.raises(LLMProviderError, match="DNS rebinding detected"):
                provider._resolve_request_url()


# ===========================================================================
# V4 Tests: Budget check on button_click
# ===========================================================================


class TestV4BudgetOnButtonClick:
    """V4: Budget must be checked before processing button clicks."""

    @pytest.mark.asyncio
    async def test_button_click_respects_token_budget(self, tmp_data, monkeypatch):
        """V4: process_button_click rejects when token budget exceeded."""
        provider = SafeMockLLMProvider()
        clf = RoutingMockClassifier()
        orchestrator = BotOrchestrator(
            classifier=clf,
            retriever=MockRetriever(),
            generator=BotGenerator(provider),
            escalation=MockEscalationProvider(),
        )

        config = BotConfig(
            name="VTestBot",
            intents=[
                Intent(
                    id="livraison",
                    label="Livraison",
                    definition="Questions de livraison",
                    examples=[f"livraison ex {i}" for i in range(10)],
                ),
                Intent(
                    id="hors_perimetre", label="HP", definition="HP",
                    examples=["hp"], is_system=True,
                ),
                Intent(
                    id="demande_conseiller", label="DC", definition="DC",
                    examples=["dc"], is_system=True,
                ),
            ],
            status="published",
        )

        from loko.bot.models import BotSession, BotState

        # Create a session with tokens_llm_cumul exceeding budget
        session = BotSession(
            bot_id=config.bot_id,
            tokens_llm_cumul=config.journey.max_tokens_llm_session + 100,
            state=BotState.ATTENTE_DEMANDE,
        )

        # Call process_button_click — should hit budget check
        events_collected = []
        async for updated_session, sse_event in orchestrator.process_button_click(
            session, "livraison", config
        ):
            events_collected.append(sse_event)
            session = updated_session

        # Should emit end_of_turn with reason "budget_tokens"
        end_events = [e for e in events_collected if e.event == "end_of_turn"]
        assert len(end_events) == 1
        assert end_events[0].data["reason"] == "budget_tokens"
        # Session should be in CLOTURE_DOUCE state
        assert session.state == BotState.CLOTURE_DOUCE

    @pytest.mark.asyncio
    async def test_button_click_within_budget_works(self, tmp_data, monkeypatch):
        """V4: process_button_click proceeds normally within budget."""
        provider = SafeMockLLMProvider()
        clf = RoutingMockClassifier()
        orchestrator = BotOrchestrator(
            classifier=clf,
            retriever=MockRetriever(),
            generator=BotGenerator(provider),
            escalation=MockEscalationProvider(),
        )

        config = BotConfig(
            name="VTestBot",
            intents=[
                Intent(
                    id="livraison",
                    label="Livraison",
                    definition="Questions de livraison",
                    examples=[f"livraison ex {i}" for i in range(10)],
                ),
                Intent(
                    id="hors_perimetre", label="HP", definition="HP",
                    examples=["hp"], is_system=True,
                ),
                Intent(
                    id="demande_conseiller", label="DC", definition="DC",
                    examples=["dc"], is_system=True,
                ),
            ],
            status="published",
        )

        from loko.bot.models import BotSession, BotState

        # Session within budget (tokens_llm_cumul = 0)
        session = BotSession(
            bot_id=config.bot_id,
            tokens_llm_cumul=0,
            state=BotState.ATTENTE_DEMANDE,
        )

        # Call process_button_click — should NOT hit budget
        events_collected = []
        async for updated_session, sse_event in orchestrator.process_button_click(
            session, "livraison", config
        ):
            events_collected.append(sse_event)
            session = updated_session

        # Should NOT get budget_tokens end event
        end_events = [e for e in events_collected if e.event == "end_of_turn"]
        for e in end_events:
            assert e.data.get("reason") != "budget_tokens"
