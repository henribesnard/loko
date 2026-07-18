"""LOKO Analytics — Event emitter (fail-open, async batch writer).

The emitter buffers events in an asyncio.Queue and flushes them
to analytics.db in batches (every 1 s or 100 events).

**Fail-open contract**: if the write fails, the bot response is
never affected.  A ``events_dropped`` counter is incremented and
exposed as both a Prometheus metric (OBS-3) and a self-healing
analytics event.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_QUEUE_MAX = 10_000
_FLUSH_INTERVAL_S = 1.0
_FLUSH_BATCH_SIZE = 100


def _generate_ulid() -> str:
    """Generate a ULID-like sortable ID (timestamp prefix + random suffix).

    Uses a lightweight inline implementation to avoid an external dependency.
    Format: 12-char hex timestamp + 20-char hex random = 32-char hex string.
    Hex preserves lexicographic ordering of the timestamp prefix.
    """
    import struct

    ts_ms = int(time.time() * 1000)
    ts_bytes = struct.pack(">Q", ts_ms)[-6:]  # 48-bit ms timestamp
    rand_bytes = os.urandom(10)
    return (ts_bytes + rand_bytes).hex()


class AnalyticsEmitter:
    """Async event emitter with in-memory queue and batch writer."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._dropped: int = 0
        self._writer_task: asyncio.Task[None] | None = None
        self._running: bool = False

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the background writer task.  Must be called from an async context."""
        if self._running:
            return
        self._running = True
        self._writer_task = asyncio.create_task(self._writer_loop())
        logger.info("Analytics emitter started (queue max=%d)", _QUEUE_MAX)

    async def stop(self) -> None:
        """Flush remaining events and stop the writer."""
        self._running = False
        if self._writer_task is not None:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
        # Final flush
        await self._flush_queue()
        logger.info(
            "Analytics emitter stopped (dropped=%d total)", self._dropped
        )

    def emit(self, event: dict[str, Any]) -> None:
        """Enqueue an event dict.  Never raises — fail-open."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped % 100 == 1:
                logger.warning(
                    "Analytics queue full — %d events dropped so far",
                    self._dropped,
                )

    async def _writer_loop(self) -> None:
        """Background loop: drain queue, flush in batches."""
        while self._running:
            try:
                await asyncio.sleep(_FLUSH_INTERVAL_S)
                await self._flush_queue()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Analytics writer error (will retry)")

    async def _flush_queue(self) -> None:
        """Drain up to FLUSH_BATCH_SIZE events and write them."""
        batch: list[dict[str, Any]] = []
        while len(batch) < _FLUSH_BATCH_SIZE:
            try:
                event = self._queue.get_nowait()
                batch.append(event)
            except asyncio.QueueEmpty:
                break

        if not batch:
            return

        try:
            from loko.analytics.db import insert_events_batch

            inserted = insert_events_batch(batch)
            logger.debug("Analytics: flushed %d events", inserted)
        except Exception:
            self._dropped += len(batch)
            logger.exception(
                "Analytics flush failed — %d events dropped (total %d)",
                len(batch),
                self._dropped,
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_emitter: AnalyticsEmitter | None = None


def get_emitter() -> AnalyticsEmitter:
    """Return the singleton emitter (created on first call)."""
    global _emitter
    if _emitter is None:
        _emitter = AnalyticsEmitter()
    return _emitter


def analytics_enabled() -> bool:
    """Return True if the emitter is running."""
    return _emitter is not None and _emitter.is_running


def emit(
    event_type: str,
    *,
    account_id: str,
    bot_id: str,
    session_id: str,
    turn: int | None = None,
    intent_id: str | None = None,
    sub_motif_id: str | None = None,
    decision: str | None = None,
    score_top1: float | None = None,
    score_margin: float | None = None,
    latency_ms: int | None = None,
    error_code: str | None = None,
    channel: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Emit a single analytics event.  Never raises.

    This is the public API — call it from endpoints and observers.
    """
    if _emitter is None or not _emitter.is_running:
        return

    try:
        event: dict[str, Any] = {
            "event_id": _generate_ulid(),
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "account_id": account_id,
            "bot_id": bot_id,
            "session_id": session_id,
            "turn": turn,
            "event_type": event_type,
            "intent_id": intent_id,
            "sub_motif_id": sub_motif_id,
            "decision": decision,
            "score_top1": score_top1,
            "score_margin": score_margin,
            "latency_ms": latency_ms,
            "error_code": error_code,
            "channel": channel,
            "meta": meta,
        }
        _emitter.emit(event)
    except Exception:
        # Fail-open: never propagate analytics errors
        logger.debug("Analytics emit error (suppressed)", exc_info=True)
