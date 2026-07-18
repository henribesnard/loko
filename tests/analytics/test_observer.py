"""Tests for the analytics observer (trace → event mapping)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest


@dataclass
class FakeTraceEvent:
    """Minimal TraceEvent for testing."""

    turn_id: str = "turn-1"
    step: str = "classification_l1"
    detail: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 42.0


def test_classification_l1_mapped():
    """classification_l1 trace step → 'classification' event with scores."""
    from loko.analytics.observer import AnalyticsObserver

    emitted: list[dict] = []

    def mock_emit(event_type, **kwargs):
        emitted.append({"event_type": event_type, **kwargs})

    observer = AnalyticsObserver(
        account_id="acc1",
        bot_id="bot1",
        session_id="sess1",
    )

    trace = FakeTraceEvent(
        step="classification_l1",
        detail={
            "scores": [
                ("help_account", 0.85),
                ("help_billing", 0.10),
                ("hors_perimetre", 0.05),
            ]
        },
        latency_ms=25.0,
    )

    with patch("loko.analytics.emitter.emit", side_effect=mock_emit):
        observer.on_trace(trace)

    assert len(emitted) == 1
    evt = emitted[0]
    assert evt["event_type"] == "classification"
    assert evt["intent_id"] == "help_account"
    assert evt["score_top1"] == pytest.approx(0.85)
    assert evt["score_margin"] == pytest.approx(0.75)  # 0.85 - 0.10
    assert evt["latency_ms"] == 25


def test_classification_l2_mapped():
    """classification_l2 trace step → 'classification' event with sub_motif."""
    from loko.analytics.observer import AnalyticsObserver

    emitted: list[dict] = []

    def mock_emit(event_type, **kwargs):
        emitted.append({"event_type": event_type, **kwargs})

    observer = AnalyticsObserver(
        account_id="acc1",
        bot_id="bot1",
        session_id="sess1",
    )

    trace = FakeTraceEvent(
        step="classification_l2",
        detail={
            "scores": [
                ("mot_de_passe_oublie", 0.72),
                ("compte_bloque", 0.28),
            ],
            "intent_id": "help_account",
        },
        latency_ms=18.0,
    )

    with patch("loko.analytics.emitter.emit", side_effect=mock_emit):
        observer.on_trace(trace)

    assert len(emitted) == 1
    evt = emitted[0]
    assert evt["event_type"] == "classification"
    assert evt["sub_motif_id"] == "mot_de_passe_oublie"


def test_guardrail_mapped():
    """guardrail_prefilter trace step → 'garde_fou_inapproprie' event."""
    from loko.analytics.observer import AnalyticsObserver

    emitted: list[dict] = []

    def mock_emit(event_type, **kwargs):
        emitted.append({"event_type": event_type, **kwargs})

    observer = AnalyticsObserver(
        account_id="acc1",
        bot_id="bot1",
        session_id="sess1",
    )

    trace = FakeTraceEvent(
        step="guardrail_prefilter",
        detail={
            "blocked_by": "sys_injection_01",
            "category": "injection",
        },
        latency_ms=0.5,
    )

    with patch("loko.analytics.emitter.emit", side_effect=mock_emit):
        observer.on_trace(trace)

    assert len(emitted) == 1
    evt = emitted[0]
    assert evt["event_type"] == "garde_fou_inapproprie"
    assert evt["meta"]["rule_id"] == "sys_injection_01"
    assert evt["meta"]["category"] == "injection"


def test_escalation_mapped():
    """escalation trace step → 'escalade' event."""
    from loko.analytics.observer import AnalyticsObserver

    emitted: list[dict] = []

    def mock_emit(event_type, **kwargs):
        emitted.append({"event_type": event_type, **kwargs})

    observer = AnalyticsObserver(
        account_id="acc1",
        bot_id="bot1",
        session_id="sess1",
    )

    trace = FakeTraceEvent(
        step="escalation",
        detail={"motif": "INSATISFACTION", "intent_id": "help_account"},
        latency_ms=150.0,
    )

    with patch("loko.analytics.emitter.emit", side_effect=mock_emit):
        observer.on_trace(trace)

    assert len(emitted) == 1
    evt = emitted[0]
    assert evt["event_type"] == "escalade"
    assert evt["meta"]["motif"] == "INSATISFACTION"


def test_unknown_step_ignored():
    """Unknown trace steps (retrieval, generation) are silently ignored."""
    from loko.analytics.observer import AnalyticsObserver

    emitted: list[dict] = []

    def mock_emit(event_type, **kwargs):
        emitted.append({"event_type": event_type, **kwargs})

    observer = AnalyticsObserver(
        account_id="acc1",
        bot_id="bot1",
        session_id="sess1",
    )

    for step in ["retrieval", "generation", "template", "unknown_step"]:
        trace = FakeTraceEvent(step=step)
        with patch("loko.analytics.emitter.emit", side_effect=mock_emit):
            observer.on_trace(trace)

    assert len(emitted) == 0


def test_no_verbatim_in_events():
    """Events must never contain user text (verbatim)."""
    from loko.analytics.observer import AnalyticsObserver

    emitted: list[dict] = []

    def mock_emit(event_type, **kwargs):
        emitted.append({"event_type": event_type, **kwargs})

    observer = AnalyticsObserver(
        account_id="acc1",
        bot_id="bot1",
        session_id="sess1",
    )

    # Classification trace with scores (no text)
    trace = FakeTraceEvent(
        step="classification_l1",
        detail={
            "scores": [("help_account", 0.85)],
            "user_text": "je veux acceder a mon compte",  # should NOT be emitted
        },
        latency_ms=25.0,
    )

    with patch("loko.analytics.emitter.emit", side_effect=mock_emit):
        observer.on_trace(trace)

    assert len(emitted) == 1
    evt = emitted[0]
    # Check that no field contains the user text
    for key, value in evt.items():
        if isinstance(value, str):
            assert "acceder" not in value.lower(), f"Verbatim leaked in {key}"
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, str):
                    assert "acceder" not in v.lower(), f"Verbatim leaked in meta.{k}"


def test_observer_fail_open():
    """Observer errors are suppressed — never crash the bot."""
    from loko.analytics.observer import AnalyticsObserver

    observer = AnalyticsObserver(
        account_id="acc1",
        bot_id="bot1",
        session_id="sess1",
    )

    trace = FakeTraceEvent(
        step="classification_l1",
        detail={"scores": [("help_account", 0.85)]},
    )

    # Make emit() raise an exception
    with patch("loko.analytics.emitter.emit", side_effect=RuntimeError("boom")):
        # Should NOT raise
        observer.on_trace(trace)
