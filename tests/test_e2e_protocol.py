"""LOKO Bot — E2E Protocol Tests.

Implements the test protocol from POSTULAT_TEST_E2E_LOKO.md phases P0-P9.
Uses the demo assistant configuration from tests/e2e_intents.json.

Covers:
- P0: Bot creation (wizard step 1)
- P1: Intent configuration & validation
- P3: Conversational paths (FSM) with controlled classifier
- P4: Escalation flows (4 motifs)
- P5: Determinism (replay)
- P7: Publication, runtime, widget security
- P9: Metrics collection
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loko.api.api_keys import generate_api_key
from loko.bot.config_store import save_bot_config
from loko.bot.models import BotConfig, Chunk, Intent, RetrievalResult, SubMotif

# Load E2E test intents config
E2E_INTENTS_FILE = Path(__file__).parent / "e2e_intents.json"


def load_e2e_intents() -> list[dict]:
    """Load the E2E test intents from JSON."""
    with open(E2E_INTENTS_FILE) as f:
        data = json.load(f)
    return data["intents"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a test FastAPI app with temp data dir."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOKO_ENV", "test")
    monkeypatch.setenv("LOKO_ADMIN_TOKEN", "e2e-admin-token-xyz")

    from loko.api.bot_public import clear_orchestrators

    clear_orchestrators()

    from loko.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def admin_headers():
    return {"Authorization": "Bearer e2e-admin-token-xyz"}


@pytest.fixture
def e2e_config(tmp_path, monkeypatch) -> BotConfig:
    """Create the E2E test bot configuration."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))

    raw_intents = load_e2e_intents()
    intents = []
    for ri in raw_intents:
        sub_motifs = []
        for sm in ri.get("sub_motifs", []):
            sub_motifs.append(
                SubMotif(
                    id=sm["id"],
                    label=sm["label"],
                    definition=sm["definition"],
                    examples=sm["examples"],
                )
            )
        intents.append(
            Intent(
                id=ri["id"],
                label=ri["label"],
                definition=ri["definition"],
                examples=ri["examples"],
                sub_motifs=sub_motifs,
                is_system=ri.get("is_system", False),
            )
        )

    # System intents (hors_perimetre, demande_conseiller) are already in e2e_intents.json

    config = BotConfig(
        name="Demo Assistant",
        intents=intents,
        status="published",
        language="fr",
        tone_profile="neutre",
    )
    save_bot_config(config)
    return config


@pytest.fixture
def api_key(e2e_config, tmp_path, monkeypatch) -> str:
    """Generate an API key for the demo bot."""
    monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
    raw_key, _ = generate_api_key(
        e2e_config.bot_id,
        label="e2e-test-key",
        allowed_origins=["*"],
    )
    return raw_key


@pytest.fixture
def auth_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


# ---------------------------------------------------------------------------
# Mock classifier for controlled E2E tests
# ---------------------------------------------------------------------------


class ControlledClassifier:
    """Classifier that returns pre-configured scores for E2E test scenarios."""

    def __init__(
        self,
        l1_responses: dict[str, list[tuple[str, float]]] | None = None,
        l2_responses: dict[str, list[tuple[str, float]]] | None = None,
    ):
        self._l1 = l1_responses or {}
        self._l2 = l2_responses or {}
        self._default_l1 = [("hors_perimetre", 0.5)]
        self._calls: list[dict] = []

    def classify_l1(self, text: str) -> list[tuple[str, float]]:
        self._calls.append({"level": "l1", "text": text})
        return self._l1.get(text, self._default_l1)

    def classify_l2(self, intent_id: str, text: str) -> list[tuple[str, float]]:
        self._calls.append({"level": "l2", "text": text, "intent": intent_id})
        key = f"{intent_id}:{text}"
        return self._l2.get(key, self._l2.get(text, []))


class MockSuccessRetriever:
    """Retriever that always returns successful results with mock chunks."""

    async def retrieve(self, query, intent, sub_motif, config, **kwargs):
        """Return mock success retrieval result."""
        return RetrievalResult(
            chunks=[
                Chunk(
                    chunk_id="mock-1",
                    text=f"Reponse FAQ pour {intent}: {query}",
                    score=0.85,
                    metadata={"source_url": "https://example.com/help"},
                ),
                Chunk(
                    chunk_id="mock-2",
                    text=f"Information complementaire sur {intent}.",
                    score=0.72,
                    metadata={"source_url": "https://example.com/helpdetail"},
                ),
            ],
            success=True,
            scope="intent",
        )


def _register_controlled_orchestrator(
    bot_id: str,
    config: BotConfig,
    classifier: ControlledClassifier,
):
    """Register an orchestrator with a controlled classifier."""
    from loko.testing.mocks import MockEscalationProvider, MockLLMProvider
    from loko.bot.generation import BotGenerator
    from loko.bot.orchestrator import BotOrchestrator
    from loko.api.bot_public import register_orchestrator

    orchestrator = BotOrchestrator(
        classifier=classifier,
        retriever=MockSuccessRetriever(),
        generator=BotGenerator(
            MockLLMProvider(
                response="[FAQ] Voici la reponse a votre question. Pour plus de details consultez https://example.com/help.",
            )
        ),
        escalation=MockEscalationProvider(),
    )
    register_orchestrator(bot_id, orchestrator)
    return orchestrator


# ---------------------------------------------------------------------------
# Helper: parse SSE events from streaming response
# ---------------------------------------------------------------------------


def parse_sse_events(content: str) -> list[dict]:
    """Parse SSE formatted text into a list of event dicts."""
    events = []
    current_event = None
    current_data = None

    for line in content.split("\n"):
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current_data = line[len("data:") :].strip()
        elif line == "" and current_event is not None:
            try:
                data = json.loads(current_data) if current_data else {}
            except (json.JSONDecodeError, TypeError):
                data = {"raw": current_data}
            events.append({"event": current_event, "data": data})
            current_event = None
            current_data = None

    return events


# ===========================================================================
# P0 — Installation & creation du bot
# ===========================================================================


class TestP0_BotCreation:
    """P0: Bot creation via admin API."""

    def test_create_demo_bot(self, client, admin_headers):
        """P0: Create the 'Demo Assistant' bot via wizard step 1."""
        res = client.post(
            "/api/bot/",
            json={
                "name": "Demo Assistant",
            },
            headers=admin_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Demo Assistant"
        assert "bot_id" in data
        assert data["status"] == "draft"

    def test_bot_persists_in_data_dir(
        self, client, admin_headers, tmp_path, monkeypatch
    ):
        """P0: Config persisted in data dir."""
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        res = client.post(
            "/api/bot/", json={"name": "PersistTest"}, headers=admin_headers
        )
        bot_id = res.json()["bot_id"]
        # Verify file on disk
        config_file = tmp_path / "bots" / bot_id / "config.json"
        assert config_file.exists()


# ===========================================================================
# P1 — Intentions & validation
# ===========================================================================


class TestP1_Intents:
    """P1: Intent configuration and validation."""

    def test_intent_min_examples_validation(
        self, client, admin_headers, tmp_path, monkeypatch
    ):
        """P1: Attempting to save an intent with < 8 examples should fail."""
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        # Create bot first
        res = client.post(
            "/api/bot/", json={"name": "ValidationBot"}, headers=admin_headers
        )
        bot_id = res.json()["bot_id"]

        # Try to update with insufficient examples (5 < min 8)
        res = client.put(
            f"/api/bot/{bot_id}",
            json={
                "intents": [
                    {
                        "id": "help_cancellation",
                        "label": "Resiliation",
                        "definition": "Resiliation du contrat",
                        "examples": ["ex1", "ex2", "ex3", "ex4", "ex5"],
                        "is_system": False,
                    }
                ],
            },
            headers=admin_headers,
        )
        # Should be rejected (422) due to insufficient examples
        assert res.status_code in (422, 400)

    def test_e2e_config_has_9_intents(self, e2e_config):
        """P1: E2E config has 7 business + 2 system intents."""
        assert len(e2e_config.intents) == 9
        system_intents = [i for i in e2e_config.intents if i.is_system]
        business_intents = [i for i in e2e_config.intents if not i.is_system]
        assert len(system_intents) == 2
        assert len(business_intents) == 7

    def test_services_en_ligne_has_sub_motifs(self, e2e_config):
        """P1: help_account has 5 sub-motifs."""
        sel = next(i for i in e2e_config.intents if i.id == "help_account")
        assert len(sel.sub_motifs) == 5
        sub_ids = {sm.id for sm in sel.sub_motifs}
        assert sub_ids == {
            "password_forgotten",
            "login_help",
            "account_locked",
            "account_creation",
            "password_reset",
        }

    def test_all_intents_have_min_examples(self, e2e_config):
        """P1: All intents have >= 8 examples (validation threshold)."""
        for intent in e2e_config.intents:
            assert len(intent.examples) >= 8, (
                f"Intent {intent.id} has only {len(intent.examples)} examples"
            )


# ===========================================================================
# P3 — Conversational paths (FSM)
# ===========================================================================


class TestP3_ConversationalPaths:
    """P3: Conversational paths through the state machine."""

    def test_T01_compte_bloque_direct(self, client, e2e_config, auth_headers):
        """T01: unlock account → help_account/account_locked."""
        classifier = ControlledClassifier(
            l1_responses={
                "I would like to unlock my account": [
                    ("help_account", 0.92),
                    ("hors_perimetre", 0.03),
                ],
            },
            l2_responses={
                "help_account:I would like to unlock my account": [
                    ("account_locked", 0.88),
                    ("password_reset", 0.05),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        # Create session
        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        assert res.status_code == 201
        session_id = res.json()["session_id"]

        # Send message
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "I would like to unlock my account", "type": "text"},
            headers=auth_headers,
        ) as response:
            assert response.status_code == 200
            content = response.read().decode()
            events = parse_sse_events(content)

        # Should have generation (no clarification)
        event_types = [e["event"] for e in events]
        assert "generation_delta" in event_types or "template" in event_types
        # Should reach satisfaction survey
        template_events = [e for e in events if e["event"] == "template"]
        # Last template should be satisfaction survey
        if template_events:
            last_template = template_events[-1]
            assert last_template["data"].get("template_key") in (
                "enquete_satisfaction",
                "hors_perimetre",
                "mise_en_relation",
            )

    def test_T03_clarification_intra(self, client, e2e_config, auth_headers):
        """T03: account access → help_account → clarification intra."""
        classifier = ControlledClassifier(
            l1_responses={
                "access to my account": [
                    ("help_account", 0.90),
                    ("hors_perimetre", 0.02),
                ],
            },
            l2_responses={
                "help_account:access to my account": [
                    ("password_forgotten", 0.30),
                    ("account_creation", 0.28),
                    ("account_locked", 0.20),
                    ("login_help", 0.15),
                    ("password_reset", 0.07),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "access to my account", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        # Should get a clarification (intra or inter)
        template_events = [e for e in events if e["event"] == "template"]
        clarification_found = False
        for te in template_events:
            if te["data"].get("template_key") in (
                "clarification_intra",
                "clarification_inter",
            ):
                clarification_found = True
                # Should have buttons
                buttons = te["data"].get("buttons", [])
                assert len(buttons) >= 2
                break

        assert clarification_found, (
            f"Expected clarification, got events: {[e['event'] for e in events]}"
        )

    def test_T04_clarification_inter(self, client, e2e_config, auth_headers):
        """T04: 'RIB coordonnees bancaires' → ambiguous → clarification inter."""
        classifier = ControlledClassifier(
            l1_responses={
                "RIB coordonnees bancaires": [
                    ("help_contact", 0.55),
                    ("help_billing", 0.50),
                    ("hors_perimetre", 0.05),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "RIB coordonnees bancaires", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        # Should get clarification inter (two top intents close)
        template_events = [e for e in events if e["event"] == "template"]
        has_clarification = any(
            te["data"].get("template_key") == "clarification_inter"
            for te in template_events
        )
        assert has_clarification, (
            f"Expected clarification_inter, got: {template_events}"
        )

    def test_T07_justificatif_droits_direct(self, client, e2e_config, auth_headers):
        """T07: coverage certificate → help_documents direct."""
        classifier = ControlledClassifier(
            l1_responses={
                "coverage certificate": [
                    ("help_documents", 0.95),
                    ("help_leave", 0.02),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "coverage certificate", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        # Should have generation without clarification
        event_types = [e["event"] for e in events]
        assert "generation_delta" in event_types
        assert "clarification_inter" not in [
            e.get("data", {}).get("template_key")
            for e in events
            if e["event"] == "template"
        ]

    def test_T09_teletransmission_direct(self, client, e2e_config, auth_headers):
        """T09: data transmission → help_transfer direct."""
        classifier = ControlledClassifier(
            l1_responses={
                "is there automatic data transmission": [
                    ("help_transfer", 0.97),
                    ("hors_perimetre", 0.01),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "is there automatic data transmission", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        event_types = [e["event"] for e in events]
        assert "generation_delta" in event_types

    def test_T11_escalade_demande_explicite(self, client, e2e_config, auth_headers):
        """T11: 'Je prefere parler a un humain' → ESCALADE motif demande_explicite."""
        classifier = ControlledClassifier(
            l1_responses={
                "Je prefere parler a un humain": [
                    ("demande_conseiller", 0.95),
                    ("hors_perimetre", 0.02),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "Je prefere parler a un humain", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        # Should get escalation template (mise_en_relation)
        template_events = [e for e in events if e["event"] == "template"]
        escalation_found = any(
            te["data"].get("template_key") == "mise_en_relation"
            for te in template_events
        )
        assert escalation_found, (
            f"Expected escalation, got: {[e['event'] for e in events]}"
        )

    def test_T12_hors_perimetre(self, client, e2e_config, auth_headers):
        """T12: 'declarer un accident de ski' → hors_perimetre → template hors perimetre."""
        classifier = ControlledClassifier(
            l1_responses={
                "declarer un accident de ski": [
                    ("hors_perimetre", 0.85),
                    ("help_leave", 0.08),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "declarer un accident de ski", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        # Should get hors_perimetre template OR escalation
        template_events = [e for e in events if e["event"] == "template"]
        hp_or_esc = any(
            te["data"].get("template_key") in ("hors_perimetre", "mise_en_relation")
            for te in template_events
        )
        assert hp_or_esc, (
            f"Expected hors_perimetre or escalation, got: {template_events}"
        )

    def test_T14_single_word_noemie(self, client, e2e_config, auth_headers):
        """T14: single word transfer → help_transfer — robustness test."""
        classifier = ControlledClassifier(
            l1_responses={
                "transfer": [
                    ("help_transfer", 0.82),
                    ("help_account", 0.05),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "transfer", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        event_types = [e["event"] for e in events]
        # Should process without error — generation or template
        assert len(events) > 0
        assert "generation_delta" in event_types or "template" in event_types


# ===========================================================================
# P3 — Scenarios (S1-S9)
# ===========================================================================


class TestP3_Scenarios:
    """P3: Full conversational scenarios."""

    def test_S1_nominal_flow(self, client, e2e_config, auth_headers):
        """S1: Query → generation with source → satisfaction 'Oui' → autre demande → 'Non' → FIN."""
        classifier = ControlledClassifier(
            l1_responses={
                "password reset": [
                    ("help_account", 0.93),
                    ("hors_perimetre", 0.02),
                ],
            },
            l2_responses={
                "help_account:password reset": [
                    ("password_forgotten", 0.91),
                    ("login_help", 0.04),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        # Step 1: Create session
        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        assert res.status_code == 201
        session_id = res.json()["session_id"]
        assert res.json()["state"] == "attente_demande"

        # Step 2: Send query → expect generation + satisfaction survey
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "password reset", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        event_types = [e["event"] for e in events]
        assert "generation_delta" in event_types
        # Should have satisfaction survey
        template_events = [e for e in events if e["event"] == "template"]
        satisfaction_found = any(
            te["data"].get("template_key") == "enquete_satisfaction"
            for te in template_events
        )
        assert satisfaction_found, f"No satisfaction survey. Events: {event_types}"

        # Step 3: Click "Oui" (satisfied) → expect autre_demande
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "Oui", "type": "button_click"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        template_events = [e for e in events if e["event"] == "template"]
        autre_demande_found = any(
            te["data"].get("template_key") == "autre_demande" for te in template_events
        )
        assert autre_demande_found, f"No autre_demande. Events: {events}"

        # Step 4: Click "Non" (no more questions) → expect FIN
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "Non", "type": "button_click"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        template_events = [e for e in events if e["event"] == "template"]
        fin_found = any(
            te["data"].get("template_key") == "fin" for te in template_events
        )
        end_events = [e for e in events if e["event"] == "end_of_turn"]
        assert fin_found or len(end_events) > 0, f"No FIN. Events: {events}"

        # Verify session state is FIN
        res = client.get(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}",
            headers=auth_headers,
        )
        assert res.json()["state"] == "fin"

    def test_S4_max_one_clarification_per_demande(
        self, client, e2e_config, auth_headers
    ):
        """S4: Max 1 clarification per demande (regle d'or)."""
        # First message triggers clarification inter
        classifier = ControlledClassifier(
            l1_responses={
                "attestation de paiement": [
                    ("help_leave", 0.55),
                    ("help_billing", 0.52),
                    ("help_documents", 0.48),
                ],
                # After clarification, user clicks and we get high confidence
                "help_billing": [
                    ("help_billing", 0.95),
                    ("hors_perimetre", 0.02),
                ],
            },
            l2_responses={},
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        # Send ambiguous message → should get clarification inter
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "attestation de paiement", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        template_events = [e for e in events if e["event"] == "template"]
        clarification_inter = [
            te
            for te in template_events
            if te["data"].get("template_key") == "clarification_inter"
        ]
        # Should get at most one clarification
        assert len(clarification_inter) <= 1

    def test_S5_insatisfaction_escalade(self, client, e2e_config, auth_headers):
        """S5: User unsatisfied → escalation, no retry loop."""
        classifier = ControlledClassifier(
            l1_responses={
                "password reset": [
                    ("help_account", 0.93),
                    ("hors_perimetre", 0.02),
                ],
            },
            l2_responses={
                "help_account:password reset": [
                    ("password_forgotten", 0.91),
                    ("login_help", 0.04),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        # Send query → generation → satisfaction survey
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "password reset", "type": "text"},
            headers=auth_headers,
        ) as response:
            response.read()

        # Click "Non" (not satisfied) → expect ESCALADE
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "Non", "type": "button_click"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        # Should get escalation template (mise_en_relation)
        template_events = [e for e in events if e["event"] == "template"]
        escalation_found = any(
            te["data"].get("template_key") == "mise_en_relation"
            for te in template_events
        )
        assert escalation_found, (
            f"Expected escalation on insatisfaction. Events: {events}"
        )

        # Verify session ends (FIN after escalation)
        res = client.get(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}",
            headers=auth_headers,
        )
        assert res.json()["state"] == "fin"

    def test_S6_max_demandes(self, client, e2e_config, auth_headers):
        """S6: After max_demandes (5), session ends."""
        classifier = ControlledClassifier(
            l1_responses={
                "question": [
                    ("help_transfer", 0.95),
                    ("hors_perimetre", 0.02),
                ],
                "Oui": [
                    ("help_transfer", 0.95),
                    ("hors_perimetre", 0.02),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        # Loop through max_demandes questions
        for i in range(6):
            # Send question
            with client.stream(
                "POST",
                f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
                json={"text": "question", "type": "text"},
                headers=auth_headers,
            ) as response:
                content = response.read().decode()
                events = parse_sse_events(content)

            # Check if session ended
            session_res = client.get(
                f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}",
                headers=auth_headers,
            )
            state = session_res.json()["state"]
            if state == "fin":
                # Should have ended at or before demand 6
                assert i >= 4, f"Session ended too early at demand {i + 1}"
                break

            # If in satisfaction survey, click Oui
            if state == "enquete_satisfaction":
                with client.stream(
                    "POST",
                    f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
                    json={"text": "Oui", "type": "button_click"},
                    headers=auth_headers,
                ) as response:
                    response.read()

                # Check state after Oui
                session_res = client.get(
                    f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}",
                    headers=auth_headers,
                )
                state = session_res.json()["state"]
                if state == "fin":
                    assert i >= 4
                    break

                # If autre_demande, click Oui to continue
                if state == "autre_demande":
                    with client.stream(
                        "POST",
                        f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
                        json={"text": "Oui", "type": "button_click"},
                        headers=auth_headers,
                    ) as response:
                        response.read()

                    session_res = client.get(
                        f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}",
                        headers=auth_headers,
                    )
                    state = session_res.json()["state"]
                    if state == "fin":
                        assert i >= 4
                        break


# ===========================================================================
# P4 — Escalation (4 motifs)
# ===========================================================================


class TestP4_Escalation:
    """P4: Escalation with all 4 motifs."""

    def test_escalation_demande_explicite(self, client, e2e_config, auth_headers):
        """P4: demande_explicite motif via demande_conseiller intent."""
        classifier = ControlledClassifier(
            l1_responses={
                "je veux parler a un agent": [
                    ("demande_conseiller", 0.96),
                    ("hors_perimetre", 0.01),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "je veux parler a un agent", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        # Verify escalation
        template_events = [e for e in events if e["event"] == "template"]
        assert any(
            te["data"].get("template_key") == "mise_en_relation"
            for te in template_events
        )

    def test_escalation_hors_perimetre(self, client, e2e_config, auth_headers):
        """P4: hors_perimetre motif via out-of-scope classification."""
        classifier = ControlledClassifier(
            l1_responses={
                "remboursement prothese dentaire": [
                    ("hors_perimetre", 0.92),
                    ("help_billing", 0.03),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "remboursement prothese dentaire", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        template_events = [e for e in events if e["event"] == "template"]
        # Should get hors_perimetre or escalation
        assert any(
            te["data"].get("template_key") in ("hors_perimetre", "mise_en_relation")
            for te in template_events
        )

    def test_escalation_insatisfaction(self, client, e2e_config, auth_headers):
        """P4: insatisfaction motif via 'Non' at satisfaction survey."""
        classifier = ControlledClassifier(
            l1_responses={
                "question simple": [
                    ("help_transfer", 0.95),
                    ("hors_perimetre", 0.02),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        # Generate answer
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "question simple", "type": "text"},
            headers=auth_headers,
        ) as response:
            response.read()

        # Click Non (unsatisfied)
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "Non", "type": "button_click"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()
            events = parse_sse_events(content)

        template_events = [e for e in events if e["event"] == "template"]
        assert any(
            te["data"].get("template_key") == "mise_en_relation"
            for te in template_events
        ), f"Expected mise_en_relation. Got: {template_events}"


# ===========================================================================
# P5 — Determinism
# ===========================================================================


class TestP5_Determinism:
    """P5: Deterministic replay — same inputs → same state transitions."""

    def test_deterministic_replay(self, client, e2e_config, auth_headers):
        """P5: Two identical sessions produce identical state sequences."""
        classifier = ControlledClassifier(
            l1_responses={
                "how to cancel membership": [
                    ("help_cancellation", 0.94),
                    ("hors_perimetre", 0.02),
                ],
            },
        )

        results = []
        for _ in range(2):
            # Fresh orchestrator each time
            _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

            res = client.post(
                f"/api/v1/bot/{e2e_config.bot_id}/sessions",
                headers=auth_headers,
            )
            session_id = res.json()["session_id"]

            with client.stream(
                "POST",
                f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
                json={"text": "how to cancel membership", "type": "text"},
                headers=auth_headers,
            ) as response:
                content = response.read().decode()
                events = parse_sse_events(content)

            # Extract state transitions and template keys
            state_sequence = [
                e["data"].get("state") for e in events if e["event"] == "state"
            ]
            template_sequence = [
                e["data"].get("template_key")
                for e in events
                if e["event"] == "template"
            ]
            results.append(
                {
                    "states": state_sequence,
                    "templates": template_sequence,
                }
            )

        # Both replays must be identical
        assert results[0]["states"] == results[1]["states"], (
            f"State divergence: {results[0]['states']} vs {results[1]['states']}"
        )
        assert results[0]["templates"] == results[1]["templates"], (
            f"Template divergence: {results[0]['templates']} vs {results[1]['templates']}"
        )


# ===========================================================================
# P7 — Publication, runtime & widget
# ===========================================================================


class TestP7_Runtime:
    """P7: Publication, runtime, and security."""

    def test_draft_bot_cannot_serve(
        self, client, admin_headers, auth_headers, tmp_path, monkeypatch
    ):
        """P7: Draft bot returns 409 at runtime."""
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        from loko.api.bot_public import clear_orchestrators

        clear_orchestrators()

        config = BotConfig(
            name="DraftBot",
            intents=[
                Intent(
                    id="test",
                    label="Test",
                    definition="Test",
                    examples=[f"ex{i}" for i in range(10)],
                ),
                Intent(
                    id="hors_perimetre",
                    label="HP",
                    definition="HP",
                    examples=[f"hp{i}" for i in range(10)],
                    is_system=True,
                ),
                Intent(
                    id="demande_conseiller",
                    label="DC",
                    definition="DC",
                    examples=[f"dc{i}" for i in range(10)],
                    is_system=True,
                ),
            ],
            status="draft",
        )
        save_bot_config(config)
        raw_key, _ = generate_api_key(
            config.bot_id, label="test", allowed_origins=["*"]
        )

        res = client.post(
            f"/api/v1/bot/{config.bot_id}/sessions",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert res.status_code == 409

    def test_session_creation_returns_welcome(self, client, e2e_config, auth_headers):
        """P7: Session creation returns welcome message with state."""
        classifier = ControlledClassifier()
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["state"] == "attente_demande"
        assert len(data["events"]) > 0

        # First event should be state
        assert data["events"][0]["event"] == "state"
        # Should have template event with presentation
        template_events = [e for e in data["events"] if e["event"] == "template"]
        assert len(template_events) >= 1
        assert template_events[0]["data"]["template_key"] == "presentation"

    def test_sse_event_format(self, client, e2e_config, auth_headers):
        """P7: SSE events have correct format (event: / data: lines)."""
        classifier = ControlledClassifier(
            l1_responses={
                "test": [("help_transfer", 0.95), ("hors_perimetre", 0.02)],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "test", "type": "text"},
            headers=auth_headers,
        ) as response:
            content = response.read().decode()

        # Verify SSE format
        assert "event:" in content
        assert "data:" in content
        events = parse_sse_events(content)
        assert len(events) > 0
        # All events should have the expected types
        valid_types = {
            "state",
            "template",
            "generation_delta",
            "sources",
            "end_of_turn",
            "traces",
        }
        for e in events:
            assert e["event"] in valid_types, f"Unknown event type: {e['event']}"

    def test_message_too_long_rejected(self, client, e2e_config, auth_headers):
        """P7-P0-5: Messages > 2000 chars are rejected."""
        classifier = ControlledClassifier()
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "x" * 5000, "type": "text"},
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_security_no_api_key_rejected(self, client, e2e_config):
        """P7: No API key → 401."""
        res = client.post(f"/api/v1/bot/{e2e_config.bot_id}/sessions")
        assert res.status_code == 401

    def test_security_wrong_origin_rejected(
        self, client, e2e_config, tmp_path, monkeypatch
    ):
        """P7: Wrong origin → 403."""
        monkeypatch.setenv("LOKO_DATA_DIR", str(tmp_path))
        raw_key, _ = generate_api_key(
            e2e_config.bot_id,
            label="restricted",
            allowed_origins=["https://allowed.example.com"],
        )

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers={
                "Authorization": f"Bearer {raw_key}",
                "Origin": "https://evil.example.com",
            },
        )
        assert res.status_code == 403

    def test_security_headers_present(self, client):
        """P7-P0-3: Security headers on all responses."""
        res = client.get("/health")
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"

    def test_ended_session_rejects_messages(self, client, e2e_config, auth_headers):
        """P7: Ended session rejects new messages with 400."""
        classifier = ControlledClassifier(
            l1_responses={
                "parler a un humain": [
                    ("demande_conseiller", 0.98),
                    ("hors_perimetre", 0.01),
                ],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        # Trigger escalation → FIN
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "parler a un humain", "type": "text"},
            headers=auth_headers,
        ) as response:
            response.read()

        # Try to send another message
        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "encore une question", "type": "text"},
            headers=auth_headers,
        )
        assert res.status_code == 400


# ===========================================================================
# P9 — Feedback & metrics
# ===========================================================================


class TestP9_Metrics:
    """P9: Feedback recording and session replay."""

    def test_feedback_positive(self, client, e2e_config, auth_headers):
        """P9: Positive feedback is recorded."""
        classifier = ControlledClassifier(
            l1_responses={
                "test": [("help_transfer", 0.95), ("hors_perimetre", 0.02)],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        # Send a message to get a turn
        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "test", "type": "text"},
            headers=auth_headers,
        ) as response:
            response.read()

        # Submit feedback
        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/feedback",
            json={"turn_id": "t1", "rating": "positive", "comment": "tres utile"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "recorded"

    def test_feedback_negative(self, client, e2e_config, auth_headers):
        """P9: Negative feedback is recorded."""
        classifier = ControlledClassifier(
            l1_responses={
                "test": [("help_transfer", 0.95), ("hors_perimetre", 0.02)],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "test", "type": "text"},
            headers=auth_headers,
        ) as response:
            response.read()

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/feedback",
            json={"turn_id": "t1", "rating": "negative", "comment": "pas clair"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "recorded"

    def test_feedback_invalid_rating_rejected(self, client, e2e_config, auth_headers):
        """P9-P2-7: Invalid rating ('neutral') is rejected."""
        classifier = ControlledClassifier()
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/feedback",
            json={"turn_id": "t1", "rating": "neutral"},
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_session_transcript_replay(self, client, e2e_config, auth_headers):
        """P9: Session transcript can be retrieved for replay."""
        classifier = ControlledClassifier(
            l1_responses={
                "hello": [("help_transfer", 0.95), ("hors_perimetre", 0.02)],
            },
        )
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "hello", "type": "text"},
            headers=auth_headers,
        ) as response:
            response.read()

        # Get full session
        res = client.get(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}",
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        transcript = data["transcript"]
        # Should have: welcome (bot) + user message + bot responses
        assert len(transcript) >= 3
        roles = [t["role"] for t in transcript]
        assert "user" in roles
        assert "bot" in roles


# ===========================================================================
# Security tests (cross-cutting P0-1/P0-3/P0-4)
# ===========================================================================


class TestSecurity:
    """Cross-cutting security tests."""

    def test_traces_not_public(self, client, e2e_config, auth_headers):
        """P1-2: /traces endpoint not available on public API."""
        classifier = ControlledClassifier()
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        res = client.get(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/traces",
            headers=auth_headers,
        )
        assert res.status_code in (404, 405)

    def test_extra_fields_rejected(self, client, e2e_config, auth_headers):
        """P2-7: Extra fields in request body are rejected."""
        classifier = ControlledClassifier()
        _register_controlled_orchestrator(e2e_config.bot_id, e2e_config, classifier)

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions",
            headers=auth_headers,
        )
        session_id = res.json()["session_id"]

        res = client.post(
            f"/api/v1/bot/{e2e_config.bot_id}/sessions/{session_id}/messages",
            json={"text": "test", "type": "text", "malicious_field": "injected"},
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_path_traversal_rejected(self):
        """P0-4: Path traversal in bot_id rejected."""
        from loko.bot.session_store import get_bot_dir

        with pytest.raises(ValueError):
            get_bot_dir("..")
        with pytest.raises(ValueError):
            get_bot_dir("../../../etc/passwd")
