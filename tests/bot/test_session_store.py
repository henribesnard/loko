"""Tests for session store (SQLite persistence)."""

from __future__ import annotations

import pytest
from pathlib import Path

from loko.bot.models import BotSession, BotState, TemplateKey, TraceEvent, Turn
from loko.bot.session_store import SessionStore


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "test_sessions.db")


@pytest.fixture
def sample_session() -> BotSession:
    return BotSession(bot_id="test-bot-123")


class TestSessionCRUD:
    def test_create_and_get(self, store, sample_session):
        store.create_session(sample_session)
        loaded = store.get_session(sample_session.session_id)
        assert loaded is not None
        assert loaded.session_id == sample_session.session_id
        assert loaded.bot_id == "test-bot-123"
        assert loaded.state == BotState.ACCUEIL

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_session("nonexistent") is None

    def test_update_session(self, store, sample_session):
        store.create_session(sample_session)
        updated = sample_session.model_copy(
            update={
                "state": BotState.ATTENTE_DEMANDE,
                "demandes_count": 2,
                "current_intent": "livraison",
            }
        )
        store.update_session(updated)
        loaded = store.get_session(sample_session.session_id)
        assert loaded.state == BotState.ATTENTE_DEMANDE
        assert loaded.demandes_count == 2
        assert loaded.current_intent == "livraison"

    def test_delete_session(self, store, sample_session):
        store.create_session(sample_session)
        store.delete_session(sample_session.session_id)
        assert store.get_session(sample_session.session_id) is None

    def test_list_sessions(self, store):
        for i in range(3):
            s = BotSession(bot_id="bot-A")
            store.create_session(s)
        s_other = BotSession(bot_id="bot-B")
        store.create_session(s_other)

        results = store.list_sessions("bot-A")
        assert len(results) == 3

    def test_purge_expired(self, store):
        old = BotSession(bot_id="bot-X", last_activity_at="2020-01-01T00:00:00+00:00")
        recent = BotSession(
            bot_id="bot-X", last_activity_at="2099-01-01T00:00:00+00:00"
        )
        store.create_session(old)
        store.create_session(recent)

        deleted = store.purge_expired("bot-X", "2025-01-01T00:00:00+00:00")
        assert deleted == 1
        assert store.get_session(old.session_id) is None
        assert store.get_session(recent.session_id) is not None


class TestTurns:
    def test_add_and_retrieve_turns(self, store, sample_session):
        store.create_session(sample_session)
        turn = Turn(role="user", content="Hello")
        store.add_turn(sample_session.session_id, turn)

        turn2 = Turn(role="bot", content="Hi!", template_key=TemplateKey.PRESENTATION)
        store.add_turn(sample_session.session_id, turn2)

        loaded = store.get_session(sample_session.session_id)
        assert len(loaded.transcript) == 2
        assert loaded.transcript[0].role == "user"
        assert loaded.transcript[0].content == "Hello"
        assert loaded.transcript[1].template_key == TemplateKey.PRESENTATION

    def test_turn_with_buttons(self, store, sample_session):
        store.create_session(sample_session)
        turn = Turn(
            role="bot",
            content="Choose:",
            buttons=["A", "B", "C"],
            button_selected="B",
        )
        store.add_turn(sample_session.session_id, turn)
        loaded = store.get_session(sample_session.session_id)
        assert loaded.transcript[0].buttons == ["A", "B", "C"]
        assert loaded.transcript[0].button_selected == "B"


class TestTraces:
    def test_add_and_retrieve_traces(self, store, sample_session):
        store.create_session(sample_session)
        trace = TraceEvent(
            turn_id="turn-1",
            step="classification_l1",
            detail={"scores": [["livraison", 0.9]]},
            latency_ms=42.5,
        )
        store.add_trace(sample_session.session_id, trace)

        traces = store.get_traces(sample_session.session_id)
        assert len(traces) == 1
        assert traces[0].step == "classification_l1"
        assert traces[0].latency_ms == 42.5
        assert traces[0].detail["scores"] == [["livraison", 0.9]]


class TestFeedback:
    def test_add_and_retrieve_feedback(self, store, sample_session):
        store.create_session(sample_session)
        store.add_feedback(
            sample_session.session_id, "turn-1", "positive", "good answer"
        )

        feedbacks = store.get_feedback(sample_session.session_id)
        assert len(feedbacks) == 1
        assert feedbacks[0]["rating"] == "positive"
        assert feedbacks[0]["comment"] == "good answer"
