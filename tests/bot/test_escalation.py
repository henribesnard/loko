"""Tests for the escalation provider."""

from __future__ import annotations

import pytest

from loko.bot.escalation import MockEscalationProvider
from loko.bot.models import EscalationMotif, EscalationPayload


@pytest.mark.asyncio
async def test_mock_returns_configured_wait_time():
    provider = MockEscalationProvider(default_wait_minutes=7)
    payload = EscalationPayload(
        conversation_id="conv-1",
        transcript=[{"role": "user", "content": "help"}],
        intention="livraison",
        sous_motif="suivi_colis",
        motif_escalade=EscalationMotif.INSATISFACTION,
    )
    result = await provider.escalate(payload)
    assert result.temps_attente_estime_min == 7


@pytest.mark.asyncio
async def test_mock_stores_last_payload():
    provider = MockEscalationProvider()
    payload = EscalationPayload(
        conversation_id="conv-2",
        transcript=[],
        motif_escalade=EscalationMotif.HORS_PERIMETRE,
    )
    await provider.escalate(payload)
    assert provider.last_payload is not None
    assert provider.last_payload.conversation_id == "conv-2"
    assert provider.last_payload.motif_escalade == EscalationMotif.HORS_PERIMETRE


@pytest.mark.asyncio
async def test_mock_default_wait_time():
    provider = MockEscalationProvider()
    payload = EscalationPayload(
        conversation_id="conv-3",
        transcript=[],
        motif_escalade=EscalationMotif.DEMANDE_EXPLICITE,
    )
    result = await provider.escalate(payload)
    assert result.temps_attente_estime_min == 4  # default
