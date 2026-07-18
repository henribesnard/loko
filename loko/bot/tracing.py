"""LOKO Bot — Structured tracing per turn.

Collects TraceEvent objects for each step of a turn: classification,
retrieval, generation, template rendering.  Used by the playground
to display the full diagnostic trace.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator

from loko.bot.models import TraceEvent


class TraceCollector:
    """Accumulates trace events for a single turn."""

    def __init__(self, turn_id: str, observer: Any | None = None) -> None:
        self.turn_id = turn_id
        self.events: list[TraceEvent] = []
        self._observer = observer  # AnalyticsObserver (OBS-1)

    def add(
        self,
        step: str,
        detail: dict[str, Any] | None = None,
        latency_ms: float = 0.0,
    ) -> TraceEvent:
        event = TraceEvent(
            turn_id=self.turn_id,
            step=step,
            detail=detail or {},
            latency_ms=latency_ms,
        )
        self.events.append(event)
        if self._observer is not None:
            self._observer.on_trace(event)
        return event

    @contextmanager
    def measure(
        self,
        step: str,
        detail: dict[str, Any] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Context manager that measures wall-clock time for a step.

        Usage::

            with trace.measure("classification_l1") as ctx:
                scores = classifier.classify(text)
                ctx["scores"] = scores
        """
        ctx: dict[str, Any] = dict(detail) if detail else {}
        start = time.perf_counter()
        try:
            yield ctx
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.add(step, detail=ctx, latency_ms=elapsed_ms)

    def to_list(self) -> list[dict[str, Any]]:
        """Serialize all events for JSON output."""
        return [e.model_dump(mode="json") for e in self.events]

    @property
    def total_latency_ms(self) -> float:
        return sum(e.latency_ms for e in self.events)
