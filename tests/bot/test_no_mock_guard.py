"""Tests for R2-a / C7 — Anti-mock guards.

Mock classes must raise RuntimeError when RAGKIT_ENV != 'test'.
All mocks are imported from loko.testing.mocks (C7).
"""

from __future__ import annotations

import pytest


def test_mock_llm_provider_blocked_outside_test(monkeypatch):
    monkeypatch.delenv("RAGKIT_ENV", raising=False)
    from loko.testing.mocks import MockLLMProvider

    with pytest.raises(RuntimeError, match="MockLLMProvider"):
        MockLLMProvider(response="hello")


def test_mock_llm_provider_allowed_in_test(monkeypatch):
    monkeypatch.setenv("RAGKIT_ENV", "test")
    from loko.testing.mocks import MockLLMProvider

    provider = MockLLMProvider(response="ok")
    assert provider.response == "ok"


def test_in_memory_backend_blocked_outside_test(monkeypatch):
    monkeypatch.delenv("RAGKIT_ENV", raising=False)
    from loko.testing.mocks import InMemorySearchBackend

    with pytest.raises(RuntimeError, match="InMemorySearchBackend"):
        InMemorySearchBackend()


def test_in_memory_backend_allowed_in_test(monkeypatch):
    monkeypatch.setenv("RAGKIT_ENV", "test")
    from loko.testing.mocks import InMemorySearchBackend

    backend = InMemorySearchBackend()
    assert backend._chunks == []


def test_mock_escalation_blocked_outside_test(monkeypatch):
    monkeypatch.delenv("RAGKIT_ENV", raising=False)
    monkeypatch.delenv("LOKO_ESCALATION_PROVIDER", raising=False)
    from loko.testing.mocks import MockEscalationProvider

    with pytest.raises(RuntimeError, match="MockEscalationProvider"):
        MockEscalationProvider()


def test_mock_escalation_allowed_in_test(monkeypatch):
    monkeypatch.setenv("RAGKIT_ENV", "test")
    from loko.testing.mocks import MockEscalationProvider

    provider = MockEscalationProvider()
    assert provider.default_wait_minutes == 4


def test_mock_escalation_allowed_with_explicit_provider(monkeypatch):
    monkeypatch.delenv("RAGKIT_ENV", raising=False)
    monkeypatch.setenv("LOKO_ESCALATION_PROVIDER", "mock")
    from loko.testing.mocks import MockEscalationProvider

    provider = MockEscalationProvider()
    assert provider.default_wait_minutes == 4


def test_mock_classifier_blocked_outside_test(monkeypatch):
    monkeypatch.delenv("RAGKIT_ENV", raising=False)
    from loko.testing.mocks import _MockClassifier

    with pytest.raises(RuntimeError, match="_MockClassifier"):
        _MockClassifier()


def test_mock_classifier_allowed_in_test(monkeypatch):
    monkeypatch.setenv("RAGKIT_ENV", "test")
    from loko.testing.mocks import _MockClassifier

    clf = _MockClassifier()
    assert clf.classify_l1("hello") == [("hors_perimetre", 0.5)]
