"""LOKO Bot — Escalation provider interface.

The escalation contract is frozen (spec §8).  Mock provider moved to
loko.testing.mocks (C7).  Real integrations plug in via the same interface.
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
