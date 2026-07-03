"""Tests for the tracing system."""

from __future__ import annotations

import time

from loko.bot.tracing import TraceCollector


class TestTraceCollector:
    def test_add_event(self):
        tc = TraceCollector(turn_id="t1")
        tc.add("classification_l1", {"scores": [("a", 0.9)]}, latency_ms=42.0)
        assert len(tc.events) == 1
        assert tc.events[0].step == "classification_l1"
        assert tc.events[0].latency_ms == 42.0

    def test_measure_context_manager(self):
        tc = TraceCollector(turn_id="t2")
        with tc.measure("retrieval") as ctx:
            ctx["chunks_found"] = 5
            time.sleep(0.01)  # at least 10ms
        assert len(tc.events) == 1
        assert tc.events[0].step == "retrieval"
        assert tc.events[0].latency_ms >= 5  # should be at least a few ms
        assert tc.events[0].detail["chunks_found"] == 5

    def test_total_latency(self):
        tc = TraceCollector(turn_id="t3")
        tc.add("step1", latency_ms=10.0)
        tc.add("step2", latency_ms=20.0)
        tc.add("step3", latency_ms=30.0)
        assert tc.total_latency_ms == 60.0

    def test_to_list(self):
        tc = TraceCollector(turn_id="t4")
        tc.add("template", {"key": "presentation"}, latency_ms=0.1)
        data = tc.to_list()
        assert len(data) == 1
        assert data[0]["step"] == "template"
        assert data[0]["turn_id"] == "t4"

    def test_empty_collector(self):
        tc = TraceCollector(turn_id="t5")
        assert tc.events == []
        assert tc.total_latency_ms == 0.0
        assert tc.to_list() == []
