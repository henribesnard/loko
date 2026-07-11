"""
Prometheus metrics for LOKO
Implements O1 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

Exports metrics at /metrics endpoint (admin-only, never public).
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
)
from typing import Literal

# Custom registry to avoid conflicts
registry = CollectorRegistry()

# ---------------------------------------------------------------------------
# Message counters
# ---------------------------------------------------------------------------

messages_total = Counter(
    "loko_messages_total",
    "Total messages processed",
    ["bot_id", "status"],  # status: success, error, rate_limited
    registry=registry,
)

escalations_total = Counter(
    "loko_escalations_total",
    "Total escalations to human",
    ["bot_id", "reason"],  # reason: hors_perimetre, demande_conseiller, timeout
    registry=registry,
)

# ---------------------------------------------------------------------------
# Classification metrics
# ---------------------------------------------------------------------------

classifications_total = Counter(
    "loko_classifications_total",
    "Total classifications",
    ["bot_id", "level", "decision"],
    # level: l1, l2
    # decision: route (confident), clarify (uncertain), reject (out of scope), escalate
    registry=registry,
)

classification_confidence = Histogram(
    "loko_classification_confidence",
    "Classification confidence scores",
    ["bot_id", "level"],
    buckets=[0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0],
    registry=registry,
)

# ---------------------------------------------------------------------------
# Latency metrics
# ---------------------------------------------------------------------------

step_latency = Histogram(
    "loko_step_latency_seconds",
    "Latency per conversation step",
    ["step"],
    # step: classification_l1, classification_l2, retrieval, generation, total
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
    registry=registry,
)

message_latency = Histogram(
    "loko_message_latency_seconds",
    "Total message processing latency",
    ["bot_id"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
    registry=registry,
)

# ---------------------------------------------------------------------------
# System metrics
# ---------------------------------------------------------------------------

models_loaded = Gauge(
    "loko_models_loaded",
    "Number of ML models currently loaded in memory",
    ["bot_id", "level"],  # level: l1, l2
    registry=registry,
)

sessions_active = Gauge(
    "loko_sessions_active",
    "Number of active chat sessions",
    ["bot_id"],
    registry=registry,
)

# ---------------------------------------------------------------------------
# Error metrics
# ---------------------------------------------------------------------------

errors_total = Counter(
    "loko_errors_total",
    "Total errors by type",
    ["error_type", "bot_id"],
    # error_type: classification_error, retrieval_error, generation_error, timeout, etc.
    registry=registry,
)

# ---------------------------------------------------------------------------
# Authentication metrics
# ---------------------------------------------------------------------------

auth_attempts_total = Counter(
    "loko_auth_attempts_total",
    "Total authentication attempts",
    ["result"],  # result: success, failed, rate_limited
    registry=registry,
)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

DecisionType = Literal["route", "clarify", "reject", "escalate"]


def record_message(bot_id: str, status: str = "success"):
    """Record a message processed."""
    messages_total.labels(bot_id=bot_id, status=status).inc()


def record_escalation(bot_id: str, reason: str):
    """Record an escalation to human."""
    escalations_total.labels(bot_id=bot_id, reason=reason).inc()


def record_classification(
    bot_id: str, level: Literal["l1", "l2"], decision: DecisionType, confidence: float
):
    """Record a classification result."""
    classifications_total.labels(bot_id=bot_id, level=level, decision=decision).inc()
    classification_confidence.labels(bot_id=bot_id, level=level).observe(confidence)


def record_step_latency(step: str, duration_seconds: float):
    """Record latency for a conversation step."""
    step_latency.labels(step=step).observe(duration_seconds)


def record_message_latency(bot_id: str, duration_seconds: float):
    """Record total message latency."""
    message_latency.labels(bot_id=bot_id).observe(duration_seconds)


def set_models_loaded(bot_id: str, level: Literal["l1", "l2"], count: int):
    """Set number of models loaded for a bot."""
    models_loaded.labels(bot_id=bot_id, level=level).set(count)


def set_active_sessions(bot_id: str, count: int):
    """Set number of active sessions for a bot."""
    sessions_active.labels(bot_id=bot_id).set(count)


def record_error(error_type: str, bot_id: str = "unknown"):
    """Record an error."""
    errors_total.labels(error_type=error_type, bot_id=bot_id).inc()


def record_auth_attempt(result: Literal["success", "failed", "rate_limited"]):
    """Record an authentication attempt."""
    auth_attempts_total.labels(result=result).inc()


def get_metrics() -> bytes:
    """
    Generate Prometheus metrics in text format.

    Returns:
        Metrics as bytes (Content-Type: text/plain; version=0.0.4)
    """
    return generate_latest(registry)
