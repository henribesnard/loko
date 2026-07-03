"""Tests for Pydantic models — validation rules."""

from __future__ import annotations

import pytest

from loko.bot.models import (
    BotConfig,
    BotLLMConfig,
    Intent,
    JourneyParams,
    MessageTemplate,
    SubMotif,
    TemplateKey,
    ToneProfile,
)


class TestIntent:
    def test_valid_intent(self):
        intent = Intent(
            id="test",
            label="Test",
            definition="A test intent",
            examples=[f"ex {i}" for i in range(8)],
        )
        assert intent.id == "test"

    def test_too_few_examples_raises(self):
        with pytest.raises(ValueError, match="at least 8 examples"):
            Intent(
                id="test",
                label="Test",
                definition="test",
                examples=["a", "b"],
            )

    def test_system_intent_allows_few_examples(self):
        intent = Intent(
            id="hors_perimetre",
            label="Hors perimetre",
            definition="Out of scope",
            examples=["a", "b"],
            is_system=True,
        )
        assert intent.is_system

    def test_empty_id_raises(self):
        with pytest.raises(ValueError):
            Intent(
                id="  ",
                label="Test",
                definition="test",
                examples=[f"ex {i}" for i in range(8)],
            )


class TestSubMotif:
    def test_valid_submotif(self):
        sm = SubMotif(
            id="suivi", label="Suivi", definition="Suivi colis",
            examples=["a", "b", "c"],
        )
        assert sm.id == "suivi"

    def test_too_few_examples_raises(self):
        with pytest.raises(ValueError, match="at least 3 examples"):
            SubMotif(id="x", label="X", definition="X", examples=["a"])


class TestJourneyParams:
    def test_defaults(self):
        jp = JourneyParams()
        assert jp.seuil_haut == 0.75
        assert jp.seuil_bas == 0.45

    def test_seuil_bas_must_be_less_than_haut(self):
        with pytest.raises(ValueError, match="seuil_bas"):
            JourneyParams(seuil_bas=0.80, seuil_haut=0.75)

    def test_equal_thresholds_raises(self):
        with pytest.raises(ValueError):
            JourneyParams(seuil_bas=0.75, seuil_haut=0.75)


class TestMessageTemplate:
    def test_valid_template(self):
        t = MessageTemplate(
            key=TemplateKey.PRESENTATION,
            text_fr="Bonjour {nom_bot}",
            text_en="Hello {nom_bot}",
            variables=["nom_bot"],
        )
        assert t.key == TemplateKey.PRESENTATION

    def test_unknown_variable_raises(self):
        with pytest.raises(ValueError, match="Unknown template variables"):
            MessageTemplate(
                key=TemplateKey.FIN,
                text_fr="test",
                text_en="test",
                variables=["bogus_var"],
            )


class TestBotConfig:
    def test_draft_allows_no_hors_perimetre(self):
        config = BotConfig(
            name="Test",
            intents=[
                Intent(
                    id="x", label="X", definition="X",
                    examples=[f"e{i}" for i in range(8)],
                )
            ],
        )
        assert config.status == "draft"

    def test_published_requires_hors_perimetre(self):
        with pytest.raises(ValueError, match="hors_perimetre"):
            BotConfig(
                name="Test",
                intents=[
                    Intent(
                        id="x", label="X", definition="X",
                        examples=[f"e{i}" for i in range(8)],
                    )
                ],
                status="published",
            )


class TestBotLLMConfig:
    def test_temperature_fixed_at_zero(self):
        llm = BotLLMConfig()
        assert llm.temperature == 0.0

    def test_temperature_nonzero_raises(self):
        with pytest.raises(ValueError):
            BotLLMConfig(temperature=0.5)
