"""LOKO Bot — Escalation provider interface and mock V1.

The escalation contract is frozen (spec §8).  The mock provider is the
default; real integrations plug in via the same interface.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from loko.bot.models import EscalationPayload, EscalationResult

logger = logging.getLogger(__name__)


@runtime_checkable
class EscalationProvider(Protocol):
    """Interface for escalation providers."""

    async def escalate(self, payload: EscalationPayload) -> EscalationResult:
        """Send the escalation payload and return the result."""
        ...


class MockEscalationProvider:
    """Mock escalation provider for V1.

    Returns a configurable estimated wait time and logs the payload.

    Guard (R2-a): raises RuntimeError outside RAGKIT_ENV=test.
    """

    def __init__(self, default_wait_minutes: int = 4) -> None:
        import os

        if os.environ.get("RAGKIT_ENV") != "test":
            raise RuntimeError(
                "MockEscalationProvider cannot be used outside test environment. "
                "Set RAGKIT_ENV=test or configure a real escalation provider."
            )
        self.default_wait_minutes = default_wait_minutes
        self.last_payload: EscalationPayload | None = None

    async def escalate(self, payload: EscalationPayload) -> EscalationResult:
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
