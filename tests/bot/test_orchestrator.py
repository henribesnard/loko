"""Tests for the bot orchestrator (integration of FSM + services)."""

from __future__ import annotations

import pytest
from typing import Any

from loko.bot.generation import BotGenerator, MockLLMProvider
from loko.bot.models import (
    BotConfig,
    Chunk,
    EscalationMotif,
    EscalationPayload,
    Intent,
    JourneyParams,
    SubMotif,
)
from loko.bot.orchestrator import BotOrchestrator, SSEEvent
from loko.bot.retrieval_filter import FilteredRetriever, InMemorySearchBackend


# ---------------------------------------------------------------------------
# Mock classifier
# ---------------------------------------------------------------------------

class MockClassifier:
    """Mock classifier with configurable L1/L2 results."""

    def __init__(
        self,
        l1_scores: list[tuple[str, float]] | None = None,
        l2_scores: dict[str, list[tuple[str, float]]] | None = None,
    ):
        self.l1_scores = l1_scores or [("livraison", 0.90)]
        self.l2_scores = l2_scores or {}

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        return self.l1_scores

    def classify_l2(self, intent_id: str, text: str) -> list[tuple[str, float]]:
        return self.l2_scores.get(intent_id, [("suivi", 0.80)])


# ---------------------------------------------------------------------------
# Mock escalation
# ---------------------------------------------------------------------------

class MockEscalation:
    def __init__(self, wait_minutes: int = 5):
        self.wait_minutes = wait_minutes
        self.last_payload: EscalationPayload | None = None

    async def escalate(self, payload: EscalationPayload) -> dict[str, Any]:
        self.last_payload = payload
        return {"temps_attente_estime_min": self.wait_minutes}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> BotConfig:
    return BotConfig(
        name="TestBot",
        knowledge_collection="test-kb",
        intents=[
            Intent(
                id="livraison", label="Livraison", definition="Livraison",
                examples=[f"ex {i}" for i in range(10)],
                sub_motifs=[
                    SubMotif(id="suivi", label="Suivi de colis", definition="Suivi",
                             examples=["a", "b", "c"]),
                    SubMotif(id="retard", label="Retard", definition="Retard",
                             examples=["d", "e", "f"]),
                ],
            ),
            Intent(
                id="facturation", label="Facturation", definition="Facturation",
                examples=[f"fact {i}" for i in range(10)],
            ),
            Intent(
                id="hors_perimetre", label="Hors périmètre", definition="HP",
                examples=["hp"], is_system=True,
            ),
            Intent(
                id="demande_conseiller", label="Conseiller", definition="Conseiller",
                examples=["humain"], is_system=True,
            ),
        ],
        journey=JourneyParams(
            retrieval_min_score=0.0,  # accept all for testing
            retrieval_min_chunks=1,
        ),
    )


@pytest.fixture
def backend() -> InMemorySearchBackend:
    b = InMemorySearchBackend()
    b.add_chunk(Chunk(
        chunk_id="c1",
        text="suivre votre colis livraison en cours",
        source_url="https://faq.example.com/suivi",
        source_title="FAQ Suivi",
        metadata={
            "bot_intents": ["livraison"],
            "bot_sub_motifs": ["suivi"],
            "confidentiality": "public",
        },
    ))
    b.add_chunk(Chunk(
        chunk_id="c2",
        text="numero de suivi colis expedition livraison",
        metadata={
            "bot_intents": ["livraison"],
            "bot_sub_motifs": ["suivi"],
            "confidentiality": "public",
        },
    ))
    b.add_chunk(Chunk(
        chunk_id="c3",
        text="facture paiement total montant",
        metadata={
            "bot_intents": ["facturation"],
            "bot_sub_motifs": [],
            "confidentiality": "public",
        },
    ))
    return b


@pytest.fixture
def orchestrator(backend) -> BotOrchestrator:
    classifier = MockClassifier(
        l1_scores=[("livraison", 0.90), ("facturation", 0.05)],
        l2_scores={"livraison": [("suivi", 0.85), ("retard", 0.10)]},
    )
    retriever = FilteredRetriever(backend)
    generator = BotGenerator(MockLLMProvider(
        response="Vous pouvez suivre votre colis via le lien de suivi."
    ))
    escalation = MockEscalation(wait_minutes=5)
    return BotOrchestrator(
        classifier=classifier,
        retriever=retriever,
        generator=generator,
        escalation=escalation,
    )


# ---------------------------------------------------------------------------
# Tests: Session creation
# ---------------------------------------------------------------------------

class TestSessionCreation:
    @pytest.mark.asyncio
    async def test_create_and_start(self, orchestrator, config):
        session, events = await orchestrator.create_and_start_session(config)
        assert session.state.value == "attente_demande"

        event_types = [e.event for e in events]
        assert "state" in event_types
        assert "template" in event_types

        # Presentation template should be emitted
        template_events = [e for e in events if e.event == "template"]
        assert len(template_events) >= 1
        assert "TestBot" in template_events[0].data["content"]


# ---------------------------------------------------------------------------
# Tests: Full pipeline (message → classify → retrieve → generate)
# ---------------------------------------------------------------------------

class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_happy_path_with_generation(self, orchestrator, config):
        """Full path: message → L1 → L2 → retrieval → generation → satisfaction."""
        session, _ = await orchestrator.create_and_start_session(config)

        events: list[SSEEvent] = []
        async for session, event in orchestrator.process_message(
            session, "où est mon colis", config,
        ):
            events.append(event)

        event_types = [e.event for e in events]

        # Should include generation tokens
        assert "generation_delta" in event_types
        # Should include satisfaction survey at the end
        template_events = [e for e in events if e.event == "template"]
        assert any("satisfaction" in str(e.data) for e in template_events)
        # Should include traces
        assert "traces" in event_types

    @pytest.mark.asyncio
    async def test_generation_produces_content(self, orchestrator, config):
        """Verify the generated response is non-empty."""
        session, _ = await orchestrator.create_and_start_session(config)

        gen_tokens: list[str] = []
        async for session, event in orchestrator.process_message(
            session, "suivi colis", config,
        ):
            if event.event == "generation_delta":
                gen_tokens.append(event.data["token"])

        full_response = "".join(gen_tokens)
        assert len(full_response) > 0
        assert "suivre" in full_response.lower() or "colis" in full_response.lower()

    @pytest.mark.asyncio
    async def test_sources_emitted(self, orchestrator, config):
        """Sources from chunks should be emitted."""
        session, _ = await orchestrator.create_and_start_session(config)

        source_events = []
        async for session, event in orchestrator.process_message(
            session, "suivi colis", config,
        ):
            if event.event == "sources":
                source_events.append(event)

        assert len(source_events) >= 1
        sources = source_events[0].data["sources"]
        assert any(s["url"] == "https://faq.example.com/suivi" for s in sources)


# ---------------------------------------------------------------------------
# Tests: Escalation paths
# ---------------------------------------------------------------------------

class TestEscalation:
    @pytest.mark.asyncio
    async def test_retrieval_insufficient_triggers_escalation(self, config):
        """When retrieval finds nothing, should escalate."""
        empty_backend = InMemorySearchBackend()
        classifier = MockClassifier(
            l1_scores=[("facturation", 0.90)],
        )
        retriever = FilteredRetriever(empty_backend)
        generator = BotGenerator(MockLLMProvider(response="should not appear"))
        escalation = MockEscalation(wait_minutes=8)

        # facturation has no sub-motifs → goes directly to retrieval
        orch = BotOrchestrator(
            classifier=classifier,
            retriever=retriever,
            generator=generator,
            escalation=escalation,
        )

        session, _ = await orch.create_and_start_session(config)

        events: list[SSEEvent] = []
        async for session, event in orch.process_message(
            session, "je veux ma facture", config,
        ):
            events.append(event)

        # Should NOT have generation tokens (retrieval failed)
        assert not any(e.event == "generation_delta" for e in events)
        # Escalation should have been called
        assert escalation.last_payload is not None
        assert escalation.last_payload.motif_escalade == EscalationMotif.RETRIEVAL_INSUFFISANT

    @pytest.mark.asyncio
    async def test_demande_conseiller_escalation(self, config, backend):
        """demande_conseiller intent triggers direct escalation."""
        classifier = MockClassifier(
            l1_scores=[("demande_conseiller", 0.95)],
        )
        retriever = FilteredRetriever(backend)
        generator = BotGenerator(MockLLMProvider(response="x"))
        escalation = MockEscalation(wait_minutes=3)

        orch = BotOrchestrator(
            classifier=classifier,
            retriever=retriever,
            generator=generator,
            escalation=escalation,
        )

        session, _ = await orch.create_and_start_session(config)

        events: list[SSEEvent] = []
        async for session, event in orch.process_message(
            session, "je veux un humain", config,
        ):
            events.append(event)

        assert escalation.last_payload is not None
        assert escalation.last_payload.motif_escalade == EscalationMotif.DEMANDE_EXPLICITE


# ---------------------------------------------------------------------------
# Tests: Button clicks
# ---------------------------------------------------------------------------

class TestButtonClicks:
    @pytest.mark.asyncio
    async def test_clarification_button_click(self, config, backend):
        """Medium confidence → clarification → button click → resolve."""
        classifier = MockClassifier(
            l1_scores=[("livraison", 0.60), ("facturation", 0.35)],
            l2_scores={"livraison": [("suivi", 0.85)]},
        )
        retriever = FilteredRetriever(backend)
        generator = BotGenerator(MockLLMProvider(response="Voici le suivi."))
        escalation = MockEscalation()

        orch = BotOrchestrator(
            classifier=classifier,
            retriever=retriever,
            generator=generator,
            escalation=escalation,
        )

        session, _ = await orch.create_and_start_session(config)

        # First message → should get clarification (medium confidence)
        events: list[SSEEvent] = []
        async for session, event in orch.process_message(
            session, "question floue", config,
        ):
            events.append(event)

        # Should have a template with buttons
        template_events = [e for e in events if e.event == "template"]
        has_buttons = any(e.data.get("buttons") for e in template_events)
        assert has_buttons, "Should have clarification buttons"

        # Click on "Livraison" button
        events2: list[SSEEvent] = []
        async for session, event in orch.process_button_click(
            session, "Livraison", config,
        ):
            events2.append(event)

        # Should proceed through L2 → retrieval → generation
        event_types = [e.event for e in events2]
        assert "generation_delta" in event_types


# ---------------------------------------------------------------------------
# Tests: Traces
# ---------------------------------------------------------------------------

class TestTraces:
    @pytest.mark.asyncio
    async def test_traces_emitted(self, orchestrator, config):
        """Each message should produce trace events."""
        session, _ = await orchestrator.create_and_start_session(config)

        trace_events = []
        async for session, event in orchestrator.process_message(
            session, "test query", config,
        ):
            if event.event == "traces":
                trace_events.append(event)

        assert len(trace_events) == 1
        traces_data = trace_events[0].data["traces"]
        assert len(traces_data) > 0

        steps = {t["step"] for t in traces_data}
        assert "classification_l1" in steps
