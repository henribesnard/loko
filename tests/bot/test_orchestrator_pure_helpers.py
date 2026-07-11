"""Unit tests for pure helper functions extracted in O6 refactor.

These tests verify the behavior of the pure functions extracted from
BotOrchestrator._handle_generation() and BotOrchestrator._handle_escalation().
"""

from loko.bot.orchestrator import BotOrchestrator
from loko.bot.models import (
    BotConfig,
    BotSession,
    BotState,
    CallEscalation,
    EscalationMotif,
    Intent,
    SubMotif,
    Turn,
)


class TestFindIntentLabels:
    """Test BotOrchestrator._find_intent_labels()"""

    def test_find_intent_label_only(self):
        """Should find intent label when no sub-motif requested."""
        config = BotConfig(
            bot_id="test",
            name="Test Bot",
            intents=[
                Intent(
                    id="help",
                    label="Aide générale",
                    definition="Questions d'aide",
                    is_system=True,
                ),
                Intent(
                    id="billing",
                    label="Facturation",
                    definition="Questions de facturation",
                    is_system=True,
                ),
            ],
        )

        intent_label, sub_motif_label = BotOrchestrator._find_intent_labels(
            config, "billing", None
        )

        assert intent_label == "Facturation"
        assert sub_motif_label == ""

    def test_find_intent_and_sub_motif_labels(self):
        """Should find both intent and sub-motif labels."""
        config = BotConfig(
            bot_id="test",
            name="Test Bot",
            intents=[
                Intent(
                    id="billing",
                    label="Facturation",
                    definition="Questions de facturation",
                    is_system=True,
                    sub_motifs=[
                        SubMotif(
                            id="invoice",
                            label="Facture",
                            definition="Questions sur les factures",
                            examples=["facture", "invoice", "billing"],
                        ),
                        SubMotif(
                            id="payment",
                            label="Paiement",
                            definition="Questions sur les paiements",
                            examples=["paiement", "payment", "pay"],
                        ),
                    ],
                ),
            ],
        )

        intent_label, sub_motif_label = BotOrchestrator._find_intent_labels(
            config, "billing", "payment"
        )

        assert intent_label == "Facturation"
        assert sub_motif_label == "Paiement"

    def test_intent_not_found(self):
        """Should return empty strings when intent not found."""
        config = BotConfig(
            bot_id="test",
            name="Test Bot",
            intents=[
                Intent(
                    id="help",
                    label="Aide",
                    definition="Questions d'aide",
                    is_system=True,
                )
            ],
        )

        intent_label, sub_motif_label = BotOrchestrator._find_intent_labels(
            config, "unknown", None
        )

        assert intent_label == ""
        assert sub_motif_label == ""

    def test_sub_motif_not_found(self):
        """Should return empty sub-motif label when not found."""
        config = BotConfig(
            bot_id="test",
            name="Test Bot",
            intents=[
                Intent(
                    id="billing",
                    label="Facturation",
                    definition="Questions de facturation",
                    is_system=True,
                    sub_motifs=[
                        SubMotif(
                            id="invoice",
                            label="Facture",
                            definition="Questions sur les factures",
                            examples=["facture", "invoice", "billing"],
                        )
                    ],
                ),
            ],
        )

        intent_label, sub_motif_label = BotOrchestrator._find_intent_labels(
            config, "billing", "unknown"
        )

        assert intent_label == "Facturation"
        assert sub_motif_label == ""

    def test_empty_config(self):
        """Should handle empty intent list."""
        config = BotConfig(
            bot_id="test",
            name="Test Bot",
            intents=[],
        )

        intent_label, sub_motif_label = BotOrchestrator._find_intent_labels(
            config, "any", None
        )

        assert intent_label == ""
        assert sub_motif_label == ""


class TestBuildEscalationPayload:
    """Test BotOrchestrator._build_escalation_payload()"""

    def test_basic_payload(self):
        """Should build payload with session data."""
        session = BotSession(
            session_id="session-123",
            bot_id="test",
            state=BotState.ESCALADE,
            transcript=[
                Turn(role="user", content="Hello"),
                Turn(role="bot", content="Hi there"),
            ],
            current_intent="help",
            current_sub_motif="general",
        )

        action = CallEscalation(motif=EscalationMotif.DEMANDE_EXPLICITE)

        payload = BotOrchestrator._build_escalation_payload(session, action)

        assert payload.conversation_id == "session-123"
        assert payload.intention == "help"
        assert payload.sous_motif == "general"
        assert payload.motif_escalade == EscalationMotif.DEMANDE_EXPLICITE
        assert len(payload.transcript) == 2
        assert payload.transcript[0]["role"] == "user"
        assert payload.transcript[0]["content"] == "Hello"

    def test_transcript_truncation(self):
        """Should limit transcript to max_turns (default 10)."""
        # Create 15 turns
        transcript = [
            Turn(role="user" if i % 2 == 0 else "bot", content=f"Turn {i}")
            for i in range(15)
        ]

        session = BotSession(
            session_id="session-123",
            bot_id="test",
            state=BotState.ESCALADE,
            transcript=transcript,
        )

        action = CallEscalation(motif=EscalationMotif.RETRIEVAL_INSUFFISANT)

        payload = BotOrchestrator._build_escalation_payload(session, action)

        # Should only include last 10 turns
        assert len(payload.transcript) == 10
        assert payload.transcript[0]["content"] == "Turn 5"  # turns 5-14
        assert payload.transcript[-1]["content"] == "Turn 14"

    def test_custom_max_turns(self):
        """Should respect custom max_turns parameter."""
        transcript = [
            Turn(role="user" if i % 2 == 0 else "bot", content=f"Turn {i}")
            for i in range(10)
        ]

        session = BotSession(
            session_id="session-123",
            bot_id="test",
            state=BotState.ESCALADE,
            transcript=transcript,
        )

        action = CallEscalation(motif=EscalationMotif.HORS_PERIMETRE)

        payload = BotOrchestrator._build_escalation_payload(
            session, action, max_turns=5
        )

        # Should only include last 5 turns
        assert len(payload.transcript) == 5
        assert payload.transcript[0]["content"] == "Turn 5"
        assert payload.transcript[-1]["content"] == "Turn 9"

    def test_short_transcript(self):
        """Should include all turns if transcript shorter than max_turns."""
        session = BotSession(
            session_id="session-123",
            bot_id="test",
            state=BotState.ESCALADE,
            transcript=[
                Turn(role="user", content="Hello"),
                Turn(role="bot", content="Hi"),
            ],
        )

        action = CallEscalation(motif=EscalationMotif.DEMANDE_EXPLICITE)

        payload = BotOrchestrator._build_escalation_payload(session, action)

        assert len(payload.transcript) == 2


class TestExtractTempsAttente:
    """Test BotOrchestrator._extract_temps_attente()"""

    def test_extract_from_dict(self):
        """Should extract wait time from dict result."""
        result = {"temps_attente_estime_min": 15, "other_field": "value"}

        temps = BotOrchestrator._extract_temps_attente(result)

        assert temps == 15

    def test_extract_from_object(self):
        """Should extract wait time from object with attribute."""

        class EscalationResult:
            temps_attente_estime_min = 20

        result = EscalationResult()

        temps = BotOrchestrator._extract_temps_attente(result)

        assert temps == 20

    def test_dict_missing_field_uses_default(self):
        """Should use default when field missing from dict."""
        result = {"other_field": "value"}

        temps = BotOrchestrator._extract_temps_attente(result)

        assert temps == 4  # default

    def test_object_missing_attribute_uses_default(self):
        """Should use default when attribute missing from object."""

        class EscalationResult:
            other_field = "value"

        result = EscalationResult()

        temps = BotOrchestrator._extract_temps_attente(result)

        assert temps == 4  # default

    def test_custom_default(self):
        """Should use custom default value."""
        result = {}

        temps = BotOrchestrator._extract_temps_attente(result, default=10)

        assert temps == 10

    def test_zero_wait_time(self):
        """Should handle zero wait time correctly."""
        result = {"temps_attente_estime_min": 0}

        temps = BotOrchestrator._extract_temps_attente(result)

        # Should return 0, not default (0 is a valid value)
        assert temps == 0
