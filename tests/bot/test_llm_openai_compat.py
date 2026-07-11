"""K2: Tests for OpenAI-compatible LLM provider.

Uses a real HTTP server (not class mocks) that speaks the OpenAI
streaming protocol.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from loko.bot.llm.openai_compat import LLMProviderError, OpenAICompatProvider


# ---------------------------------------------------------------------------
# Fake OpenAI-compatible server
# ---------------------------------------------------------------------------

class FakeOpenAIHandler(BaseHTTPRequestHandler):
    """Minimal handler that streams OpenAI-format SSE responses."""

    # Class-level config (set before each test)
    response_tokens: list[str] = ["Bonjour", " ", "monde"]
    status_code: int = 200
    auth_required: str | None = None
    delay_s: float = 0

    def do_POST(self):
        # Read request body
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}

        # Store for assertions
        FakeOpenAIHandler.last_request_body = body
        FakeOpenAIHandler.last_request_headers = dict(self.headers)

        # Auth check
        if self.auth_required:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {self.auth_required}":
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())
                return

        # Custom status code
        if self.status_code != 200:
            self.send_response(self.status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Error"}).encode())
            return

        # Stream SSE response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        import time
        if self.delay_s > 0:
            time.sleep(self.delay_s)

        for i, token in enumerate(self.response_tokens):
            chunk = {
                "id": f"chatcmpl-{i}",
                "object": "chat.completion.chunk",
                "choices": [{
                    "index": 0,
                    "delta": {"content": token},
                    "finish_reason": None,
                }],
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()

        # Send [DONE]
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, format, *args):
        pass  # Suppress log output during tests


@pytest.fixture
def fake_server():
    """Start a local HTTP server mimicking the OpenAI API."""
    # Reset defaults
    FakeOpenAIHandler.response_tokens = ["Bonjour", " ", "monde"]
    FakeOpenAIHandler.status_code = 200
    FakeOpenAIHandler.auth_required = None
    FakeOpenAIHandler.delay_s = 0
    FakeOpenAIHandler.last_request_body = {}
    FakeOpenAIHandler.last_request_headers = {}

    server = HTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}"

    server.shutdown()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOpenAICompatProvider:
    """K2: OpenAI-compatible provider tests."""

    @pytest.mark.asyncio
    async def test_nominal_streaming(self, fake_server):
        """Nominal: stream tokens from OpenAI-compat endpoint."""
        provider = OpenAICompatProvider(
            base_url=fake_server, api_key="test-key", model="gpt-test",
        )
        messages = [{"role": "user", "content": "Bonjour"}]

        tokens: list[str] = []
        async for token in provider.stream_chat(
            messages, model="gpt-test", temperature=0.0,
            max_tokens=100, timeout=10,
        ):
            tokens.append(token)

        assert tokens == ["Bonjour", " ", "monde"]

    @pytest.mark.asyncio
    async def test_temperature_always_zero(self, fake_server):
        """Temperature must always be 0 regardless of caller value."""
        provider = OpenAICompatProvider(
            base_url=fake_server, api_key="test-key", model="gpt-test",
        )

        async for _ in provider.stream_chat(
            [{"role": "user", "content": "test"}],
            temperature=0.7,  # caller tries non-zero
            max_tokens=100, timeout=10,
        ):
            pass

        # Verify the request sent temperature=0
        assert FakeOpenAIHandler.last_request_body["temperature"] == 0

    @pytest.mark.asyncio
    async def test_auth_401(self, fake_server):
        """401 from provider raises LLMProviderError."""
        FakeOpenAIHandler.auth_required = "correct-key"

        provider = OpenAICompatProvider(
            base_url=fake_server, api_key="wrong-key", model="gpt-test",
        )

        with pytest.raises(LLMProviderError, match="401"):
            async for _ in provider.stream_chat(
                [{"role": "user", "content": "test"}],
                max_tokens=100, timeout=10,
            ):
                pass

    @pytest.mark.asyncio
    async def test_rate_limit_429(self, fake_server):
        """429 from provider raises LLMProviderError."""
        FakeOpenAIHandler.status_code = 429

        provider = OpenAICompatProvider(
            base_url=fake_server, api_key="test-key", model="gpt-test",
        )

        with pytest.raises(LLMProviderError, match="429"):
            async for _ in provider.stream_chat(
                [{"role": "user", "content": "test"}],
                max_tokens=100, timeout=10,
            ):
                pass

    @pytest.mark.asyncio
    async def test_timeout(self, fake_server):
        """Timeout raises LLMProviderError."""
        FakeOpenAIHandler.delay_s = 5  # 5 second delay

        provider = OpenAICompatProvider(
            base_url=fake_server, api_key="test-key", model="gpt-test",
        )

        with pytest.raises(LLMProviderError, match="timeout"):
            async for _ in provider.stream_chat(
                [{"role": "user", "content": "test"}],
                max_tokens=100, timeout=1,  # 1 second timeout
            ):
                pass

    @pytest.mark.asyncio
    async def test_default_model_used(self, fake_server):
        """When model param is empty, default_model from constructor is used."""
        provider = OpenAICompatProvider(
            base_url=fake_server, api_key="test-key", model="default-model",
        )

        async for _ in provider.stream_chat(
            [{"role": "user", "content": "test"}],
            model="",  # empty → use default
            max_tokens=100, timeout=10,
        ):
            pass

        assert FakeOpenAIHandler.last_request_body["model"] == "default-model"

    @pytest.mark.asyncio
    async def test_authorization_header_sent(self, fake_server):
        """API key is sent as Bearer token."""
        FakeOpenAIHandler.auth_required = "my-secret-key"

        provider = OpenAICompatProvider(
            base_url=fake_server, api_key="my-secret-key", model="gpt-test",
        )

        tokens = []
        async for token in provider.stream_chat(
            [{"role": "user", "content": "test"}],
            max_tokens=100, timeout=10,
        ):
            tokens.append(token)

        # Should succeed with correct key
        assert len(tokens) > 0

    @pytest.mark.asyncio
    async def test_stream_true_in_request(self, fake_server):
        """Request payload must include stream=true."""
        provider = OpenAICompatProvider(
            base_url=fake_server, api_key="test-key", model="gpt-test",
        )

        async for _ in provider.stream_chat(
            [{"role": "user", "content": "test"}],
            max_tokens=100, timeout=10,
        ):
            pass

        assert FakeOpenAIHandler.last_request_body["stream"] is True


class TestBuildLLMProvider:
    """K2: Factory function tests."""

    def test_missing_base_url(self, monkeypatch):
        """No LOKO_LLM_BASE_URL → ComponentUnavailableError."""
        monkeypatch.delenv("LOKO_LLM_BASE_URL", raising=False)
        monkeypatch.delenv("LOKO_LLM_PROVIDER", raising=False)

        from loko.bot.errors import ComponentUnavailableError
        from loko.bot.llm import build_llm_provider

        with pytest.raises(ComponentUnavailableError, match="No LLM provider configured"):
            build_llm_provider("test-bot")

    def test_missing_api_key(self, monkeypatch):
        """LOKO_LLM_BASE_URL set but no API key → ComponentUnavailableError."""
        monkeypatch.setenv("LOKO_LLM_BASE_URL", "http://localhost:8080/v1")
        monkeypatch.delenv("LOKO_LLM_API_KEY", raising=False)
        monkeypatch.delenv("LOKO_LLM_MODEL", raising=False)

        from loko.bot.errors import ComponentUnavailableError
        from loko.bot.llm import build_llm_provider

        with pytest.raises(ComponentUnavailableError, match="LOKO_LLM_API_KEY"):
            build_llm_provider("test-bot")

    def test_missing_model(self, monkeypatch):
        """LOKO_LLM_BASE_URL + API key but no model → ComponentUnavailableError."""
        monkeypatch.setenv("LOKO_LLM_BASE_URL", "http://localhost:8080/v1")
        monkeypatch.setenv("LOKO_LLM_API_KEY", "sk-test")
        monkeypatch.delenv("LOKO_LLM_MODEL", raising=False)

        from loko.bot.errors import ComponentUnavailableError
        from loko.bot.llm import build_llm_provider

        with pytest.raises(ComponentUnavailableError, match="LOKO_LLM_MODEL"):
            build_llm_provider("test-bot")

    def test_successful_build(self, monkeypatch):
        """All env vars set → returns OpenAICompatProvider."""
        monkeypatch.setenv("LOKO_LLM_BASE_URL", "http://localhost:8080/v1")
        monkeypatch.setenv("LOKO_LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LOKO_LLM_MODEL", "gpt-4o-mini")

        from loko.bot.llm import build_llm_provider
        from loko.bot.llm.openai_compat import OpenAICompatProvider

        provider = build_llm_provider("test-bot")
        assert isinstance(provider, OpenAICompatProvider)
        assert provider.default_model == "gpt-4o-mini"

    def test_auto_detect_provider(self, monkeypatch):
        """LOKO_LLM_PROVIDER not set but LOKO_LLM_BASE_URL → auto openai_compat."""
        monkeypatch.delenv("LOKO_LLM_PROVIDER", raising=False)
        monkeypatch.setenv("LOKO_LLM_BASE_URL", "http://localhost:8080/v1")
        monkeypatch.setenv("LOKO_LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LOKO_LLM_MODEL", "gpt-4o-mini")

        from loko.bot.llm import build_llm_provider
        from loko.bot.llm.openai_compat import OpenAICompatProvider

        provider = build_llm_provider("test-bot")
        assert isinstance(provider, OpenAICompatProvider)
