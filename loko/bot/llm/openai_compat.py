"""LOKO Bot — OpenAI-compatible LLM provider (K2).

Async HTTP client for any endpoint implementing the OpenAI
``/v1/chat/completions`` streaming protocol.  Covers OpenAI, DeepSeek,
Mistral, vLLM, Ollama, and any compatible server in a single
implementation.

Temperature is hardcoded to 0 (protocol determinism requirement).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# Timeout defaults (seconds)
_DEFAULT_CONNECT_TIMEOUT = 10
_DEFAULT_READ_TIMEOUT = 60


class OpenAICompatProvider:
    """LLM provider using the OpenAI chat completions API.

    Satisfies the ``LLMProvider`` protocol from ``loko.bot.generation``.

    Parameters
    ----------
    base_url : str
        API base URL (e.g. ``https://api.openai.com/v1``).
        The ``/chat/completions`` path is appended automatically.
    api_key : str
        Bearer token for ``Authorization`` header.
    model : str
        Default model identifier.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        host_header: str | None = None,
        *,
        original_url: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = model
        # DNS rebinding protection: override Host header when URL is IP-pinned
        self._host_header = host_header
        # V2: store original URL for per-request DNS re-resolution
        self._original_url = original_url

    def _resolve_request_url(self) -> tuple[str, str | None]:
        """Resolve the request URL with per-request DNS pinning (V2).

        In server mode with an original URL stored, re-resolves DNS on each
        call to prevent DNS rebinding attacks. Returns (url, host_header).
        """
        import os

        if self._original_url and os.environ.get("LOKO_MODE", "desktop").lower() == "server":
            from loko.security.ssrf import resolve_and_pin, SSRFError

            try:
                pinned_url, original_host = resolve_and_pin(self._original_url)
                return pinned_url.rstrip("/"), original_host
            except SSRFError:
                # DNS rebinding detected (e.g., now resolves to private IP)
                logger.error(
                    "DNS rebinding detected for %s — blocking request",
                    self._original_url,
                )
                raise LLMProviderError(
                    "DNS rebinding detected: URL now resolves to a blocked address.",
                    status_code=0,
                )

        # Desktop mode or no original URL: use stored base_url as-is
        return self.base_url, self._host_header

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 800,
        timeout: int = 60,
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens from an OpenAI-compatible API.

        Parameters match the ``LLMProvider`` protocol.  ``temperature``
        is **always forced to 0** regardless of the caller value
        (determinism requirement).
        """
        effective_model = model or self.default_model

        # V2: per-request DNS re-resolution to prevent DNS rebinding attacks
        request_url, host_header = self._resolve_request_url()
        url = f"{request_url}/chat/completions"

        payload = {
            "model": effective_model,
            "messages": messages,
            "temperature": 0,  # hardcoded — determinism
            "max_tokens": max_tokens,
            "stream": True,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        # DNS rebinding protection: set original Host header when IP-pinned
        if host_header:
            headers["Host"] = host_header

        # Request usage info from providers that support it (OpenAI, etc.)
        payload["stream_options"] = {"include_usage": True}

        t0 = time.perf_counter()
        first_token_time: float | None = None
        token_count = 0
        # Track provider-reported usage (populated from final chunk if available)
        self._last_usage: dict[str, int] | None = None

        transport_timeout = httpx.Timeout(
            connect=_DEFAULT_CONNECT_TIMEOUT,
            read=float(timeout),
            write=30.0,
            pool=10.0,
        )

        async with httpx.AsyncClient(timeout=transport_timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code == 401:
                        logger.error("LLM provider returned 401 Unauthorized")
                        raise LLMProviderError(
                            "LLM provider authentication failed (401). "
                            "Check LOKO_LLM_API_KEY.",
                            status_code=401,
                        )
                    if response.status_code == 429:
                        logger.error("LLM provider returned 429 Too Many Requests")
                        raise LLMProviderError(
                            "LLM provider rate-limited (429). Retry later.",
                            status_code=429,
                        )
                    if response.status_code >= 400:
                        body = await response.aread()
                        logger.error(
                            "LLM provider error %d: %s",
                            response.status_code,
                            body[:500],
                        )
                        raise LLMProviderError(
                            f"LLM provider error ({response.status_code})",
                            status_code=response.status_code,
                        )

                    # Parse SSE stream
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data: "):
                            continue
                        data_str = line[len("data: ") :]
                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            logger.debug(
                                "Skipping non-JSON SSE line: %s", data_str[:100]
                            )
                            continue

                        # Capture usage from final chunk if provider includes it
                        usage = chunk.get("usage")
                        if usage and isinstance(usage, dict):
                            self._last_usage = usage

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            if first_token_time is None:
                                first_token_time = time.perf_counter()
                            token_count += 1
                            yield content

            except asyncio.CancelledError:
                # INT: cooperative cancellation — log and propagate cleanly
                elapsed = time.perf_counter() - t0
                logger.info(
                    "LLM generation interrupted: model=%s tokens=%d elapsed=%.2fs",
                    effective_model,
                    token_count,
                    elapsed,
                )
                raise
            except httpx.TimeoutException:
                elapsed = time.perf_counter() - t0
                logger.error(
                    "LLM provider timeout after %.1fs (limit=%ds)",
                    elapsed,
                    timeout,
                )
                raise LLMProviderError(
                    f"LLM provider timeout after {elapsed:.0f}s",
                    status_code=0,
                )
            except LLMProviderError:
                raise
            except httpx.HTTPError as exc:
                logger.error("LLM HTTP error: %s", exc)
                raise LLMProviderError(
                    f"LLM provider connection error: {exc}",
                    status_code=0,
                ) from exc

        elapsed = time.perf_counter() - t0
        ttft = (first_token_time - t0) if first_token_time else elapsed
        logger.info(
            "LLM generation done: model=%s tokens=%d ttft=%.2fs total=%.2fs",
            effective_model,
            token_count,
            ttft,
            elapsed,
        )

    def get_last_usage(self) -> dict[str, int] | None:
        """Return provider-reported usage from the last generation, if available.

        Returns a dict with keys like ``completion_tokens``, ``prompt_tokens``,
        ``total_tokens``, or None if the provider didn't report usage.
        """
        return getattr(self, "_last_usage", None)


class LLMProviderError(Exception):
    """Raised when the LLM provider returns an error or times out."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        self.status_code = status_code
        super().__init__(message)
