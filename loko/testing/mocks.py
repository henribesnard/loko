"""LOKO — Mock providers for testing (C7).

All 4 mock classes are centralized here.  Each class has a LOKO_ENV
guard that raises RuntimeError outside test mode (defense in depth).

Production code (loko/ excluding loko/testing/) MUST NOT import this
module.  Tests import from here; the lint test test_no_mock_import.py
enforces this boundary.
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


def _check_test_env(class_name: str) -> None:
    """Guard: raise RuntimeError if not in test environment."""
    from loko.config.env import get_env
    is_test = get_env("ENV") == "test"
    is_explicit_mock = os.environ.get("LOKO_ESCALATION_PROVIDER") == "mock"
    # MockEscalationProvider is the only one allowed with explicit LOKO_ESCALATION_PROVIDER=mock
    if class_name == "MockEscalationProvider" and (is_test or is_explicit_mock):
        return
    if is_test:
        return
    raise RuntimeError(
        f"{class_name} cannot be used outside test environment. "
        f"Set LOKO_ENV=test or configure a real provider."
    )


class _MockClassifier:
    """Fallback classifier when no model is trained.

    Guard (R2-a): raises RuntimeError outside LOKO_ENV=test.
    """

    def __init__(self) -> None:
        _check_test_env("_MockClassifier")

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        return [("hors_perimetre", 0.5)]

    def classify_l2(self, intent_id: str, text: str) -> list[tuple[str, float]]:
        return []


class MockLLMProvider:
    """Mock LLM provider that returns a fixed response token by token.

    Guard (R2-a): raises RuntimeError outside LOKO_ENV=test.
    """

    def __init__(self, response: str = ""):
        _check_test_env("MockLLMProvider")
        self.response = response
        self.last_messages: list[dict[str, str]] = []

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 600,
        timeout: int = 60,
    ) -> AsyncIterator[str]:
        """Yield response word by word."""
        self.last_messages = messages
        for word in self.response.split():
            yield word + " "


class InMemorySearchBackend:
    """Simple in-memory search backend for testing.

    Guard (R2-a): raises RuntimeError outside LOKO_ENV=test.
    """

    def __init__(self, chunks: list[Any] | None = None):
        _check_test_env("InMemorySearchBackend")
        self._chunks: list[Any] = chunks or []

    def add_chunk(self, chunk: Any) -> None:
        self._chunks.append(chunk)

    async def search(
        self,
        query: str,
        collection: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[Any]:
        """Return filtered chunks with simple keyword scoring."""
        results: list[Any] = []

        for chunk in self._chunks:
            if not self._matches_filters(chunk, filters):
                continue

            # Simple keyword overlap scoring
            query_words = set(query.lower().split())
            chunk_words = set(chunk.text.lower().split())
            overlap = len(query_words & chunk_words)
            total = max(len(query_words), 1)
            score = overlap / total

            scored_chunk = chunk.model_copy(update={"score": score})
            results.append(scored_chunk)

        results.sort(key=lambda c: c.score, reverse=True)
        return results[:top_k]

    @staticmethod
    def _matches_filters(chunk: Any, filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True

        meta = chunk.metadata

        if "bot_intents" in filters:
            required_intent = filters["bot_intents"]
            chunk_intents = meta.get("bot_intents", [])
            if required_intent not in chunk_intents:
                return False

        if "bot_sub_motifs" in filters:
            required_sub = filters["bot_sub_motifs"]
            chunk_subs = meta.get("bot_sub_motifs", [])
            if required_sub not in chunk_subs:
                return False

        if "confidentiality" in filters:
            allowed = filters["confidentiality"]
            chunk_conf = meta.get("confidentiality", "public")
            if chunk_conf not in allowed:
                return False

        return True


class MockEscalationProvider:
    """Mock escalation provider for V1.

    Returns a configurable estimated wait time and logs the payload.

    Guard (A3/GNG-10): raises RuntimeError outside LOKO_ENV=test.
    Exception: allowed when LOKO_ESCALATION_PROVIDER=mock is explicitly set.
    """

    def __init__(self, default_wait_minutes: int = 4) -> None:
        _check_test_env("MockEscalationProvider")
        self.default_wait_minutes = default_wait_minutes
        self.last_payload: Any = None

    async def escalate(self, payload: Any) -> Any:
        from loko.bot.models import EscalationResult

        self.last_payload = payload
        logger.info(
            "Mock escalation: conversation=%s intent=%s motif=%s",
            payload.conversation_id,
            payload.intention,
            payload.motif_escalade.value,
        )
        return EscalationResult(
            temps_attente_estime_min=self.default_wait_minutes,
        )
