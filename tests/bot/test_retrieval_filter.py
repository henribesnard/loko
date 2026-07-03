"""Tests for the filtered retrieval service."""

from __future__ import annotations

import pytest

from loko.bot.models import BotConfig, Chunk, EscalationMotif, JourneyParams
from loko.bot.retrieval_filter import FilteredRetriever, InMemorySearchBackend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def backend() -> InMemorySearchBackend:
    """Backend pre-loaded with test chunks."""
    b = InMemorySearchBackend()

    # Livraison chunks (sub-motif: suivi)
    b.add_chunk(Chunk(
        chunk_id="c1", text="suivre votre colis livraison en cours",
        metadata={
            "bot_intents": ["livraison"],
            "bot_sub_motifs": ["suivi"],
            "confidentiality": "public",
        },
    ))
    b.add_chunk(Chunk(
        chunk_id="c2", text="numero de suivi colis expedition livraison",
        metadata={
            "bot_intents": ["livraison"],
            "bot_sub_motifs": ["suivi"],
            "confidentiality": "public",
        },
    ))

    # Livraison chunks (sub-motif: retard)
    b.add_chunk(Chunk(
        chunk_id="c3", text="retard livraison délai dépassé",
        metadata={
            "bot_intents": ["livraison"],
            "bot_sub_motifs": ["retard"],
            "confidentiality": "public",
        },
    ))

    # Facturation chunks
    b.add_chunk(Chunk(
        chunk_id="c4", text="facture paiement montant total",
        metadata={
            "bot_intents": ["facturation"],
            "bot_sub_motifs": [],
            "confidentiality": "public",
        },
    ))

    # Employee-only chunk
    b.add_chunk(Chunk(
        chunk_id="c5", text="procédure interne remboursement livraison",
        metadata={
            "bot_intents": ["livraison"],
            "bot_sub_motifs": ["suivi"],
            "confidentiality": "employee",
        },
    ))

    return b


@pytest.fixture
def config() -> BotConfig:
    return BotConfig(
        name="TestBot",
        knowledge_collection="test-collection",
        journey=JourneyParams(
            retrieval_min_score=0.1,
            retrieval_min_chunks=1,
        ),
        confidentiality_filter=["public"],
    )


@pytest.fixture
def retriever(backend: InMemorySearchBackend) -> FilteredRetriever:
    return FilteredRetriever(backend)


# ---------------------------------------------------------------------------
# Tests: Filtering
# ---------------------------------------------------------------------------

class TestFiltering:
    @pytest.mark.asyncio
    async def test_filter_by_intent(self, retriever, config):
        """Only chunks tagged with the right intent are returned."""
        result = await retriever.retrieve(
            query="facture paiement",
            intent="facturation",
            sub_motif=None,
            config=config,
        )
        assert result.success
        for chunk in result.chunks:
            assert "facturation" in chunk.metadata["bot_intents"]

    @pytest.mark.asyncio
    async def test_filter_by_sub_motif(self, retriever, config):
        """Sub-motif filtering narrows results."""
        result = await retriever.retrieve(
            query="suivi colis livraison",
            intent="livraison",
            sub_motif="suivi",
            config=config,
        )
        assert result.success
        assert result.scope == "sub_motif"
        for chunk in result.chunks:
            assert "suivi" in chunk.metadata["bot_sub_motifs"]

    @pytest.mark.asyncio
    async def test_no_cross_intent_leak(self, retriever, config):
        """Facturation query must not return livraison chunks."""
        result = await retriever.retrieve(
            query="suivi colis livraison",
            intent="facturation",
            sub_motif=None,
            config=config,
        )
        for chunk in result.chunks:
            assert "facturation" in chunk.metadata["bot_intents"]

    @pytest.mark.asyncio
    async def test_confidentiality_filter(self, retriever, config):
        """Employee-only chunks are excluded with public filter."""
        result = await retriever.retrieve(
            query="procédure interne remboursement livraison",
            intent="livraison",
            sub_motif="suivi",
            config=config,
        )
        for chunk in result.chunks:
            assert chunk.metadata["confidentiality"] == "public"
            assert chunk.chunk_id != "c5"

    @pytest.mark.asyncio
    async def test_employee_filter_includes_internal(self, retriever):
        """With employee filter, internal chunks are included."""
        config = BotConfig(
            name="TestBot",
            knowledge_collection="test-collection",
            journey=JourneyParams(
                retrieval_min_score=0.0,
                retrieval_min_chunks=1,
            ),
            confidentiality_filter=["public", "employee"],
        )
        result = await retriever.retrieve(
            query="procédure interne remboursement livraison",
            intent="livraison",
            sub_motif="suivi",
            config=config,
        )
        chunk_ids = {c.chunk_id for c in result.chunks}
        assert "c5" in chunk_ids


# ---------------------------------------------------------------------------
# Tests: Fallback
# ---------------------------------------------------------------------------

class TestFallback:
    @pytest.mark.asyncio
    async def test_fallback_to_intent_level(self, retriever, config):
        """When sub-motif has insufficient chunks, widen to intent level."""
        config_strict = config.model_copy(
            update={"journey": JourneyParams(
                retrieval_min_score=0.1,
                retrieval_min_chunks=3,  # suivi only has 2 public chunks
            )}
        )
        result = await retriever.retrieve(
            query="suivi colis livraison",
            intent="livraison",
            sub_motif="suivi",
            config=config_strict,
        )
        # Should widen to intent level (3 public livraison chunks)
        assert result.success
        assert result.scope == "intent"

    @pytest.mark.asyncio
    async def test_escalation_when_insufficient(self, retriever, config):
        """When even intent level has insufficient chunks, escalate."""
        config_strict = config.model_copy(
            update={"journey": JourneyParams(
                retrieval_min_score=0.1,
                retrieval_min_chunks=20,  # more than available chunks
            )}
        )
        result = await retriever.retrieve(
            query="suivi colis",
            intent="livraison",
            sub_motif=None,
            config=config_strict,
        )
        assert not result.success
        assert result.escalate
        assert result.escalation_motif == EscalationMotif.RETRIEVAL_INSUFFISANT


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_no_collection_configured(self, retriever):
        """If no knowledge collection is set, escalate immediately."""
        config = BotConfig(
            name="TestBot",
            knowledge_collection="",
        )
        result = await retriever.retrieve(
            query="test", intent="x", sub_motif=None, config=config,
        )
        assert not result.success
        assert result.escalate

    @pytest.mark.asyncio
    async def test_no_sub_motif_goes_direct_to_intent(self, retriever, config):
        """When sub_motif is None, skip sub-motif search entirely."""
        result = await retriever.retrieve(
            query="livraison colis",
            intent="livraison",
            sub_motif=None,
            config=config,
        )
        # Should go directly to intent-level search
        assert result.scope == "intent"

    @pytest.mark.asyncio
    async def test_empty_backend_escalates(self):
        """Empty backend means no chunks → escalation."""
        backend = InMemorySearchBackend()
        retriever = FilteredRetriever(backend)
        config = BotConfig(
            name="TestBot",
            knowledge_collection="test",
            journey=JourneyParams(retrieval_min_chunks=1, retrieval_min_score=0.1),
        )
        result = await retriever.retrieve(
            query="test", intent="x", sub_motif=None, config=config,
        )
        assert not result.success
        assert result.escalate
