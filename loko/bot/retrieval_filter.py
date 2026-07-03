"""LOKO Bot — Filtered retrieval service.

Performs document retrieval with hard filtering by intent/sub-motif
and confidentiality, with fallback escalation when insufficient chunks.

The retriever is injected via protocol to allow testing with mocks.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from loko.bot.models import (
    BotConfig,
    Chunk,
    EscalationMotif,
    RetrievalResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retrieval backend protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ChunkSearchBackend(Protocol):
    """Low-level search backend that the filtered retriever delegates to.

    Implementations must perform the actual vector/BM25 search on a
    corpus, returning scored chunks.  Filtering by intent/sub-motif
    and confidentiality is handled by the FilteredRetriever wrapper.
    """

    async def search(
        self,
        query: str,
        collection: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[Chunk]:
        """Search and return top-k chunks.

        Parameters
        ----------
        query : str
            Search query text.
        collection : str
            Name of the vector collection / knowledge base.
        filters : dict
            Metadata filters to apply (hard).
        top_k : int
            Maximum number of results.
        """
        ...


# ---------------------------------------------------------------------------
# Filtered retriever
# ---------------------------------------------------------------------------

class FilteredRetriever:
    """Retrieves chunks with hard filtering by intent/sub-motif + confidentiality.

    Implements the fallback strategy:
    1. Search at sub-motif level (if applicable)
    2. If insufficient, widen to intent level
    3. If still insufficient, escalate
    """

    def __init__(self, backend: ChunkSearchBackend):
        self.backend = backend

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
        """Perform filtered retrieval with fallback.

        Parameters
        ----------
        query : str
            Original user query text.
        intent : str
            Current intent id.
        sub_motif : str | None
            Current sub-motif id (or None).
        config : BotConfig
            Bot configuration (thresholds, collection, confidentiality).
        intent_label : str
            Human-readable intent label for query augmentation.
        sub_motif_label : str
            Human-readable sub-motif label for query augmentation.
        top_k : int
            Max chunks to retrieve.
        """
        collection = config.knowledge_collection
        if not collection:
            logger.warning("No knowledge collection configured for bot %s", config.bot_id)
            return RetrievalResult(
                success=False,
                escalate=True,
                escalation_motif=EscalationMotif.RETRIEVAL_INSUFFISANT,
                scope="none",
            )

        min_score = config.journey.retrieval_min_score
        min_chunks = config.journey.retrieval_min_chunks

        # --- Step 1: Search at sub-motif level (if applicable) ---
        if sub_motif:
            augmented_query = f"{query} — {sub_motif_label}" if sub_motif_label else query
            filters = self._build_filters(
                intent=intent,
                sub_motif=sub_motif,
                confidentiality=config.confidentiality_filter,
            )
            chunks = await self.backend.search(
                augmented_query, collection, filters=filters, top_k=top_k,
            )
            good_chunks = [c for c in chunks if c.score >= min_score]

            if len(good_chunks) >= min_chunks:
                logger.info(
                    "Retrieval success at sub-motif level: %d chunks (min=%d)",
                    len(good_chunks), min_chunks,
                )
                return RetrievalResult(
                    chunks=good_chunks,
                    success=True,
                    scope="sub_motif",
                )

            logger.info(
                "Insufficient chunks at sub-motif level (%d < %d), widening to intent",
                len(good_chunks), min_chunks,
            )

        # --- Step 2: Search at intent level ---
        augmented_query = f"{query} — {intent_label}" if intent_label else query
        filters = self._build_filters(
            intent=intent,
            sub_motif=None,
            confidentiality=config.confidentiality_filter,
        )
        chunks = await self.backend.search(
            augmented_query, collection, filters=filters, top_k=top_k,
        )
        good_chunks = [c for c in chunks if c.score >= min_score]

        if len(good_chunks) >= min_chunks:
            logger.info(
                "Retrieval success at intent level: %d chunks (min=%d)",
                len(good_chunks), min_chunks,
            )
            return RetrievalResult(
                chunks=good_chunks,
                success=True,
                scope="intent",
            )

        # --- Step 3: Insufficient → escalate ---
        logger.info(
            "Retrieval insufficient at intent level (%d < %d) → escalation",
            len(good_chunks), min_chunks,
        )
        return RetrievalResult(
            chunks=good_chunks,  # still pass what we found
            success=False,
            scope="fallback",
            escalate=True,
            escalation_motif=EscalationMotif.RETRIEVAL_INSUFFISANT,
        )

    @staticmethod
    def _build_filters(
        intent: str,
        sub_motif: str | None,
        confidentiality: list[str],
    ) -> dict[str, Any]:
        """Build metadata filters for the search backend."""
        filters: dict[str, Any] = {
            "bot_intents": intent,
            "confidentiality": confidentiality,
        }
        if sub_motif:
            filters["bot_sub_motifs"] = sub_motif
        return filters


# ---------------------------------------------------------------------------
# In-memory mock backend (for tests and playground)
# ---------------------------------------------------------------------------

class InMemorySearchBackend:
    """Simple in-memory search backend for testing.

    Stores chunks and returns those matching the provided filters,
    scored by simple text overlap.
    """

    def __init__(self, chunks: list[Chunk] | None = None):
        self._chunks: list[Chunk] = chunks or []

    def add_chunk(self, chunk: Chunk) -> None:
        self._chunks.append(chunk)

    async def search(
        self,
        query: str,
        collection: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[Chunk]:
        """Return filtered chunks with simple keyword scoring."""
        results: list[Chunk] = []

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
    def _matches_filters(chunk: Chunk, filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True

        meta = chunk.metadata

        # Check bot_intents filter
        if "bot_intents" in filters:
            required_intent = filters["bot_intents"]
            chunk_intents = meta.get("bot_intents", [])
            if required_intent not in chunk_intents:
                return False

        # Check bot_sub_motifs filter
        if "bot_sub_motifs" in filters:
            required_sub = filters["bot_sub_motifs"]
            chunk_subs = meta.get("bot_sub_motifs", [])
            if required_sub not in chunk_subs:
                return False

        # Check confidentiality filter
        if "confidentiality" in filters:
            allowed = filters["confidentiality"]
            chunk_conf = meta.get("confidentiality", "public")
            if chunk_conf not in allowed:
                return False

        return True
