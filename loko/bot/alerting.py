"""LOKO Bot — Operational alerting (Lot PRO-5 §7.5).

Periodic evaluation of alert rules against metrics aggregates.
Anti-storm: one alert per rule per silence window (default 30 min).

Channels: email, webhook (reuses webhook escalation infrastructure).
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AlertRule(BaseModel):
    """An alert rule definition."""

    id: str
    metric: str  # escalation_rate, ttfb_p95, guardrail_block_rate, llm_error_rate, fin_ferme_count
    window_min: int = Field(default=15, ge=1, le=1440)
    threshold: float
    direction: Literal["above", "below"] = "above"
    channel: Literal["email", "webhook"] = "webhook"
    enabled: bool = False
    silence_min: int = Field(default=30, ge=1, le=1440)


class AlertEvent(BaseModel):
    """A triggered alert event."""

    rule_id: str
    metric: str
    value: float
    threshold: float
    triggered_at: float  # unix timestamp
    resolved: bool = False


class AlertEngine:
    """Evaluates alert rules against current metrics.

    Anti-storm: tracks last alert time per rule, suppresses
    duplicates within the silence window.
    """

    def __init__(self, rules: list[AlertRule] | None = None) -> None:
        self.rules = rules or []
        self._last_alert: dict[str, float] = {}  # rule_id → unix ts

    def evaluate(self, metrics: dict[str, float]) -> list[AlertEvent]:
        """Evaluate all rules against current metrics.

        Returns a list of newly triggered alert events.
        """
        events: list[AlertEvent] = []
        now = time.time()

        for rule in self.rules:
            if not rule.enabled:
                continue

            value = metrics.get(rule.metric)
            if value is None:
                continue

            triggered = False
            if rule.direction == "above" and value > rule.threshold:
                triggered = True
            elif rule.direction == "below" and value < rule.threshold:
                triggered = True

            if not triggered:
                # Check for recovery alert
                last = self._last_alert.get(rule.id)
                if last is not None:
                    self._last_alert.pop(rule.id, None)
                    events.append(
                        AlertEvent(
                            rule_id=rule.id,
                            metric=rule.metric,
                            value=value,
                            threshold=rule.threshold,
                            triggered_at=now,
                            resolved=True,
                        )
                    )
                continue

            # Check silence window
            last = self._last_alert.get(rule.id, 0)
            if now - last < rule.silence_min * 60:
                continue

            self._last_alert[rule.id] = now
            events.append(
                AlertEvent(
                    rule_id=rule.id,
                    metric=rule.metric,
                    value=value,
                    threshold=rule.threshold,
                    triggered_at=now,
                )
            )

        return events
