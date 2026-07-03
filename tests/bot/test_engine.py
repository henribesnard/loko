"""Tests for the FSM engine — exhaustive transition coverage."""

from __future__ import annotations

import pytest

from loko.bot.engine import (
    add_turn_to_session,
    create_session,
    handle_escalation_result,
    start_session,
    step,
)
from loko.bot.models import (
    BotConfig,
    BotSession,
    BotState,
    CallEscalation,
    CloseSession,
    EmitGeneration,
    EmitTemplate,
    EscalationMotif,
    TemplateKey,
)
from loko.bot.states import Event, EventType


class TestStartup:
    def test_start_emits_presentation(self, fresh_session, sample_config):
        new, actions = start_session(fresh_session, sample_config)
        assert new.state == BotState.ATTENTE_DEMANDE
        assert len(actions) == 1
        assert isinstance(actions[0], EmitTemplate)
        assert actions[0].key == TemplateKey.PRESENTATION
        assert "TestBot" in actions[0].variables["nom_bot"]

    def test_presentation_lists_non_system_intents(self, fresh_session, sample_config):
        new, actions = start_session(fresh_session, sample_config)
        template = actions[0]
        # Should list Livraison, Facturation, Retour but NOT hors_perimetre/demande_conseiller
        listed = template.variables["intentions_gerees"]
        assert "Livraison" in listed
        assert "Facturation" in listed
        assert "Hors perimetre" not in listed
        assert "conseiller" not in listed.lower()


class TestClassificationL1:
    def _go_to_classification(self, fresh_session, sample_config):
        """Helper: get session to CLASSIFICATION_L1 state."""
        s, _ = start_session(fresh_session, sample_config)
        event = Event(EventType.USER_MESSAGE, {"text": "probleme livraison"})
        s2, _ = step(s, event, sample_config)
        assert s2.state == BotState.CLASSIFICATION_L1
        return s2

    def test_high_confidence_goes_to_l2(self, fresh_session, sample_config):
        s = self._go_to_classification(fresh_session, sample_config)
        event = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("livraison", 0.90), ("facturation", 0.30)]},
        )
        s3, actions = step(s, event, sample_config)
        # livraison has sub_motifs -> goes to CLASSIFICATION_L2
        assert s3.state == BotState.CLASSIFICATION_L2
        assert s3.current_intent == "livraison"

    def test_high_confidence_no_submotifs_goes_to_retrieval(self, fresh_session, sample_config):
        s = self._go_to_classification(fresh_session, sample_config)
        event = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("facturation", 0.85)]},
        )
        s3, actions = step(s, event, sample_config)
        # facturation has no sub_motifs -> RETRIEVAL_GENERATION
        assert s3.state == BotState.RETRIEVAL_GENERATION
        assert any(isinstance(a, EmitGeneration) for a in actions)

    def test_medium_confidence_triggers_clarification(self, fresh_session, sample_config):
        s = self._go_to_classification(fresh_session, sample_config)
        event = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("livraison", 0.60), ("facturation", 0.50)]},
        )
        s3, actions = step(s, event, sample_config)
        assert s3.state == BotState.CLARIFICATION_INTER
        assert any(isinstance(a, EmitTemplate) for a in actions)
        template = next(a for a in actions if isinstance(a, EmitTemplate))
        assert template.key == TemplateKey.CLARIFICATION_INTER
        assert template.buttons is not None
        assert len(template.buttons) == 2

    def test_low_confidence_triggers_hors_perimetre(self, fresh_session, sample_config):
        s = self._go_to_classification(fresh_session, sample_config)
        event = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("livraison", 0.30)]},
        )
        s3, actions = step(s, event, sample_config)
        # First time: allow reformulation
        assert s3.state == BotState.ATTENTE_DEMANDE
        assert any(isinstance(a, EmitTemplate) and a.key == TemplateKey.HORS_PERIMETRE for a in actions)
        assert s3.reformulation_count_current_demande == 1

    def test_hors_perimetre_class_triggers_out_of_scope(self, fresh_session, sample_config):
        s = self._go_to_classification(fresh_session, sample_config)
        event = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("hors_perimetre", 0.90)]},
        )
        s3, actions = step(s, event, sample_config)
        assert s3.state == BotState.ATTENTE_DEMANDE
        assert s3.reformulation_count_current_demande == 1

    def test_second_hors_perimetre_triggers_escalade(self, fresh_session, sample_config):
        s = self._go_to_classification(fresh_session, sample_config)
        # First out-of-scope
        event1 = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("hors_perimetre", 0.90)]},
        )
        s3, _ = step(s, event1, sample_config)
        assert s3.reformulation_count_current_demande == 1

        # User reformulates
        s4, _ = step(s3, Event(EventType.USER_MESSAGE, {"text": "autre chose"}), sample_config)
        # Second classification still out-of-scope
        s5 = s4.model_copy(update={"reformulation_count_current_demande": 1})
        event2 = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("hors_perimetre", 0.90)]},
        )
        s6, actions = step(s5, event2, sample_config)
        assert s6.state == BotState.ESCALADE
        assert any(isinstance(a, CallEscalation) for a in actions)

    def test_demande_conseiller_triggers_escalade(self, fresh_session, sample_config):
        s = self._go_to_classification(fresh_session, sample_config)
        event = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("demande_conseiller", 0.80)]},
        )
        s3, actions = step(s, event, sample_config)
        assert s3.state == BotState.ESCALADE
        assert any(
            isinstance(a, CallEscalation) and a.motif == EscalationMotif.DEMANDE_EXPLICITE
            for a in actions
        )


class TestClarificationInter:
    def _go_to_clarification_inter(self, fresh_session, sample_config):
        s, _ = start_session(fresh_session, sample_config)
        s, _ = step(s, Event(EventType.USER_MESSAGE, {"text": "question"}), sample_config)
        event = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("livraison", 0.60), ("facturation", 0.50)]},
        )
        s, _ = step(s, event, sample_config)
        assert s.state == BotState.CLARIFICATION_INTER
        return s

    def test_button_click_routes_to_intent(self, fresh_session, sample_config):
        s = self._go_to_clarification_inter(fresh_session, sample_config)
        event = Event(EventType.BUTTON_CLICK, {"button": "Livraison"})
        s2, actions = step(s, event, sample_config)
        # Livraison has sub_motifs -> CLASSIFICATION_L2
        assert s2.state == BotState.CLASSIFICATION_L2
        assert s2.current_intent == "livraison"

    def test_free_text_reclassifies(self, fresh_session, sample_config):
        s = self._go_to_clarification_inter(fresh_session, sample_config)
        event = Event(EventType.USER_MESSAGE, {"text": "c'est pour une facture"})
        s2, _ = step(s, event, sample_config)
        assert s2.state == BotState.CLASSIFICATION_L1


class TestClassificationL2:
    def _go_to_l2(self, fresh_session, sample_config):
        s, _ = start_session(fresh_session, sample_config)
        s, _ = step(s, Event(EventType.USER_MESSAGE, {"text": "colis"}), sample_config)
        event = Event(
            EventType.CLASSIFICATION_L1_DONE,
            {"scores": [("livraison", 0.90)]},
        )
        s, _ = step(s, event, sample_config)
        assert s.state == BotState.CLASSIFICATION_L2
        return s

    def test_confident_submotif_goes_to_retrieval(self, fresh_session, sample_config):
        s = self._go_to_l2(fresh_session, sample_config)
        event = Event(
            EventType.CLASSIFICATION_L2_DONE,
            {"scores": [("suivi_colis", 0.75)]},
        )
        s2, actions = step(s, event, sample_config)
        assert s2.state == BotState.RETRIEVAL_GENERATION
        assert s2.current_sub_motif == "suivi_colis"
        gen = next(a for a in actions if isinstance(a, EmitGeneration))
        assert gen.sub_motif == "suivi_colis"

    def test_low_confidence_triggers_clarification_intra(self, fresh_session, sample_config):
        s = self._go_to_l2(fresh_session, sample_config)
        event = Event(
            EventType.CLASSIFICATION_L2_DONE,
            {"scores": [("suivi_colis", 0.40), ("retard", 0.35)]},
        )
        s2, actions = step(s, event, sample_config)
        assert s2.state == BotState.CLARIFICATION_INTRA
        template = next(a for a in actions if isinstance(a, EmitTemplate))
        assert template.key == TemplateKey.CLARIFICATION_INTRA
        assert "Autre" in template.buttons


class TestClarificationIntra:
    def _go_to_clarification_intra(self, fresh_session, sample_config):
        s, _ = start_session(fresh_session, sample_config)
        s, _ = step(s, Event(EventType.USER_MESSAGE, {"text": "colis"}), sample_config)
        s, _ = step(
            s,
            Event(EventType.CLASSIFICATION_L1_DONE, {"scores": [("livraison", 0.90)]}),
            sample_config,
        )
        s, _ = step(
            s,
            Event(EventType.CLASSIFICATION_L2_DONE, {"scores": [("suivi_colis", 0.40)]}),
            sample_config,
        )
        assert s.state == BotState.CLARIFICATION_INTRA
        return s

    def test_button_routes_to_submotif(self, fresh_session, sample_config):
        s = self._go_to_clarification_intra(fresh_session, sample_config)
        event = Event(EventType.BUTTON_CLICK, {"button": "Suivi de colis"})
        s2, actions = step(s, event, sample_config)
        assert s2.state == BotState.RETRIEVAL_GENERATION
        assert s2.current_sub_motif == "suivi_colis"

    def test_autre_uses_intent_level_retrieval(self, fresh_session, sample_config):
        s = self._go_to_clarification_intra(fresh_session, sample_config)
        event = Event(EventType.BUTTON_CLICK, {"button": "Autre"})
        s2, actions = step(s, event, sample_config)
        assert s2.state == BotState.RETRIEVAL_GENERATION
        gen = next(a for a in actions if isinstance(a, EmitGeneration))
        assert gen.sub_motif is None  # intent-level

    def test_free_text_reclassifies_l2(self, fresh_session, sample_config):
        s = self._go_to_clarification_intra(fresh_session, sample_config)
        event = Event(EventType.USER_MESSAGE, {"text": "mon colis est en retard"})
        s2, _ = step(s, event, sample_config)
        assert s2.state == BotState.CLASSIFICATION_L2


class TestRetrievalAndSatisfaction:
    def _go_to_enquete(self, fresh_session, sample_config):
        s, _ = start_session(fresh_session, sample_config)
        s, _ = step(s, Event(EventType.USER_MESSAGE, {"text": "facture"}), sample_config)
        s, _ = step(
            s,
            Event(EventType.CLASSIFICATION_L1_DONE, {"scores": [("facturation", 0.90)]}),
            sample_config,
        )
        # facturation has no sub_motifs -> RETRIEVAL_GENERATION
        assert s.state == BotState.RETRIEVAL_GENERATION
        s, _ = step(
            s,
            Event(EventType.RETRIEVAL_GENERATION_DONE, {}),
            sample_config,
        )
        assert s.state == BotState.ENQUETE_SATISFACTION
        return s

    def test_satisfied_goes_to_autre_demande(self, fresh_session, sample_config):
        s = self._go_to_enquete(fresh_session, sample_config)
        s2, actions = step(s, Event(EventType.BUTTON_CLICK, {"button": "Oui"}), sample_config)
        assert s2.state == BotState.AUTRE_DEMANDE

    def test_not_satisfied_escalates_immediately(self, fresh_session, sample_config):
        s = self._go_to_enquete(fresh_session, sample_config)
        s2, actions = step(s, Event(EventType.BUTTON_CLICK, {"button": "Non"}), sample_config)
        assert s2.state == BotState.ESCALADE
        assert any(
            isinstance(a, CallEscalation) and a.motif == EscalationMotif.INSATISFACTION
            for a in actions
        )


class TestAutreDemande:
    def _go_to_autre_demande(self, fresh_session, sample_config):
        s, _ = start_session(fresh_session, sample_config)
        s, _ = step(s, Event(EventType.USER_MESSAGE, {"text": "facture"}), sample_config)
        s, _ = step(
            s,
            Event(EventType.CLASSIFICATION_L1_DONE, {"scores": [("facturation", 0.90)]}),
            sample_config,
        )
        s, _ = step(s, Event(EventType.RETRIEVAL_GENERATION_DONE, {}), sample_config)
        s, _ = step(s, Event(EventType.BUTTON_CLICK, {"button": "Oui"}), sample_config)
        assert s.state == BotState.AUTRE_DEMANDE
        return s

    def test_oui_loops_back(self, fresh_session, sample_config):
        s = self._go_to_autre_demande(fresh_session, sample_config)
        s2, _ = step(s, Event(EventType.BUTTON_CLICK, {"button": "Oui"}), sample_config)
        assert s2.state == BotState.ATTENTE_DEMANDE
        assert s2.demandes_count == 1
        assert s2.current_intent is None

    def test_non_closes(self, fresh_session, sample_config):
        s = self._go_to_autre_demande(fresh_session, sample_config)
        s2, actions = step(s, Event(EventType.BUTTON_CLICK, {"button": "Non"}), sample_config)
        assert s2.state == BotState.FIN
        assert any(isinstance(a, CloseSession) for a in actions)

    def test_max_demandes_closes(self, fresh_session, sample_config):
        s = self._go_to_autre_demande(fresh_session, sample_config)
        s = s.model_copy(update={"demandes_count": sample_config.journey.max_demandes - 1})
        s2, actions = step(s, Event(EventType.BUTTON_CLICK, {"button": "Oui"}), sample_config)
        assert s2.state == BotState.FIN
        assert any(isinstance(a, CloseSession) for a in actions)


class TestTransverseExits:
    def test_timeout_from_any_state(self, fresh_session, sample_config):
        s, _ = start_session(fresh_session, sample_config)
        s2, actions = step(s, Event(EventType.TIMEOUT_EXPIRED), sample_config)
        assert s2.state == BotState.TIMEOUT
        assert any(isinstance(a, EmitTemplate) and a.key == TemplateKey.TIMEOUT for a in actions)
        assert any(isinstance(a, CloseSession) for a in actions)

    def test_terminal_state_ignores_events(self, fresh_session, sample_config):
        s = fresh_session.model_copy(update={"state": BotState.FIN})
        s2, actions = step(s, Event(EventType.USER_MESSAGE, {"text": "hello"}), sample_config)
        assert s2.state == BotState.FIN
        assert actions == []


class TestEscalationResult:
    def test_escalation_result_emits_mise_en_relation(self, fresh_session, sample_config):
        s = fresh_session.model_copy(update={"state": BotState.ESCALADE})
        s2, actions = handle_escalation_result(s, sample_config, temps_attente=7)
        assert s2.state == BotState.FIN
        template = next(a for a in actions if isinstance(a, EmitTemplate))
        assert template.key == TemplateKey.MISE_EN_RELATION
        assert template.variables["temps_attente"] == "7"
        assert any(isinstance(a, CloseSession) for a in actions)


class TestDeterminism:
    """Two identical runs must produce identical state sequences."""

    def test_deterministic_replay(self, fresh_session, sample_config):
        events = [
            Event(EventType.START),
            Event(EventType.USER_MESSAGE, {"text": "livraison"}),
            Event(EventType.CLASSIFICATION_L1_DONE, {"scores": [("livraison", 0.90)]}),
            Event(EventType.CLASSIFICATION_L2_DONE, {"scores": [("suivi_colis", 0.75)]}),
            Event(EventType.RETRIEVAL_GENERATION_DONE, {}),
            Event(EventType.BUTTON_CLICK, {"button": "Oui"}),
            Event(EventType.BUTTON_CLICK, {"button": "Non"}),
        ]

        def run_scenario():
            s = fresh_session.model_copy()
            states = []
            all_actions = []
            for evt in events:
                s, actions = step(s, evt, sample_config)
                states.append(s.state.value)
                all_actions.append([type(a).__name__ for a in actions])
            return states, all_actions

        states1, actions1 = run_scenario()
        states2, actions2 = run_scenario()

        assert states1 == states2, "State sequences differ between runs"
        assert actions1 == actions2, "Action sequences differ between runs"


class TestAddTurn:
    def test_add_turn_appends(self, fresh_session):
        s = add_turn_to_session(fresh_session, "user", "hello")
        assert len(s.transcript) == 1
        assert s.transcript[0].content == "hello"
        assert s.transcript[0].role == "user"

        s2 = add_turn_to_session(s, "bot", "hi there")
        assert len(s2.transcript) == 2
