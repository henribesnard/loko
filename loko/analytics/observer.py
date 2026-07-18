"""LOKO Analytics — Trace observer.

Maps TraceEvent steps to analytics event_types and emits them
via the AnalyticsEmitter.  Attached to TraceCollector as an
optional observer — zero ``if`` in the FSM itself.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _TraceEventLike(Protocol):
    """Minimal interface expected from TraceEvent (avoids circular import)."""

    step: str
    detail: dict[str, Any]
    latency_ms: float
    turn_id: str


# Mapping from TraceCollector step names to analytics event_types.
# Steps not in this map are silently ignored (e.g. retrieval, generation
# whose data is folded into answer_served at the session level).
_STEP_TO_EVENT: dict[str, str] = {
    "classification_l1": "classification",
    "classification_l2": "classification",
    "guardrail_prefilter": "garde_fou_inapproprie",
    "escalation": "escalade",
}


class AnalyticsObserver:
    """Observer attached to a TraceCollector for a single turn.

    Created with the session context (account_id, bot_id, session_id,
    channel) so each emitted event carries the right scoping.
    """

    def __init__(
        self,
        *,
        account_id: str,
        bot_id: str,
        session_id: str,
        channel: str | None = None,
        turn: int | None = None,
    ) -> None:
        self.account_id = account_id
        self.bot_id = bot_id
        self.session_id = session_id
        self.channel = channel
        self.turn = turn

    def on_trace(self, trace_event: _TraceEventLike) -> None:
        """Called by TraceCollector.add() — maps and emits."""
        event_type = _STEP_TO_EVENT.get(trace_event.step)
        if event_type is None:
            return

        try:
            from loko.analytics.emitter import emit

            detail = trace_event.detail or {}
            kwargs: dict[str, Any] = {
                "account_id": self.account_id,
                "bot_id": self.bot_id,
                "session_id": self.session_id,
                "turn": self.turn,
                "channel": self.channel,
                "latency_ms": int(trace_event.latency_ms) if trace_event.latency_ms else None,
            }

            if event_type == "classification":
                scores = detail.get("scores", [])
                if scores:
                    top = scores[0] if isinstance(scores[0], (list, tuple)) else None
                    if top:
                        kwargs["intent_id"] = str(top[0])
                        kwargs["score_top1"] = float(top[1])
                        if len(scores) > 1:
                            second = scores[1]
                            if isinstance(second, (list, tuple)):
                                kwargs["score_margin"] = float(top[1]) - float(second[1])
                # L2 classification includes sub_motif
                if trace_event.step == "classification_l2" and scores:
                    top = scores[0] if isinstance(scores[0], (list, tuple)) else None
                    if top:
                        kwargs["sub_motif_id"] = str(top[0])
                        kwargs["intent_id"] = detail.get("intent_id")

            elif event_type == "garde_fou_inapproprie":
                kwargs["meta"] = {
                    "rule_id": detail.get("blocked_by"),
                    "category": detail.get("category"),
                }

            elif event_type == "escalade":
                kwargs["meta"] = {
                    "motif": detail.get("motif"),
                }
                kwargs["intent_id"] = detail.get("intent_id")

            emit(event_type, **kwargs)

        except Exception:
            # Fail-open: never let analytics crash the bot
            logger.debug("Analytics observer error (suppressed)", exc_info=True)
