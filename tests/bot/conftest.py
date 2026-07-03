"""Shared fixtures for bot tests."""

from __future__ import annotations

import pytest

from loko.bot.models import (
    BotConfig,
    BotLLMConfig,
    BotSession,
    Intent,
    JourneyParams,
    SubMotif,
    ToneProfile,
)


@pytest.fixture
def sample_intents() -> list[Intent]:
    """Minimal set of intents for testing."""
    return [
        Intent(
            id="livraison",
            label="Livraison",
            definition="Questions sur la livraison",
            examples=[f"exemple livraison {i}" for i in range(8)],
            sub_motifs=[
                SubMotif(
                    id="suivi_colis",
                    label="Suivi de colis",
                    definition="Suivi de colis",
                    examples=["ou est mon colis", "suivi livraison", "tracking"],
                ),
                SubMotif(
                    id="retard",
                    label="Retard de livraison",
                    definition="Retard de livraison",
                    examples=["colis en retard", "pas recu", "livraison en retard"],
                ),
            ],
        ),
        Intent(
            id="facturation",
            label="Facturation",
            definition="Questions sur la facturation",
            examples=[f"exemple facturation {i}" for i in range(8)],
        ),
        Intent(
            id="retour",
            label="Retour",
            definition="Retour de produit",
            examples=[f"exemple retour {i}" for i in range(8)],
        ),
        Intent(
            id="hors_perimetre",
            label="Hors perimetre",
            definition="Demandes hors perimetre",
            examples=["quel temps fait-il", "raconte une blague"],
            is_system=True,
        ),
        Intent(
            id="demande_conseiller",
            label="Parler a un conseiller",
            definition="Demande explicite de conseiller",
            examples=["je veux un humain", "passez-moi quelqu'un"],
            is_system=True,
        ),
    ]


@pytest.fixture
def sample_config(sample_intents: list[Intent]) -> BotConfig:
    """A valid bot config for testing."""
    return BotConfig(
        name="TestBot",
        intents=sample_intents,
        journey=JourneyParams(),
        tone_profile=ToneProfile.NEUTRE,
        llm=BotLLMConfig(),
    )


@pytest.fixture
def fresh_session(sample_config: BotConfig) -> BotSession:
    """A session in ACCUEIL state."""
    return BotSession(bot_id=sample_config.bot_id)
