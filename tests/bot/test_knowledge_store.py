"""Tests for R2-b — Knowledge store (SQLite FTS5 backend)."""

from __future__ import annotations

from pathlib import Path

import pytest

from loko.bot.knowledge_store import KnowledgeStore, _chunk_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path) -> KnowledgeStore:
    db_path = tmp_path / "knowledge.db"
    return KnowledgeStore(db_path)


SAMPLE_CONTENT = (
    "Pour réinitialiser votre mot de passe, rendez-vous dans les paramètres "
    "de votre compte et cliquez sur 'Mot de passe oublié'. "
    "Un email de vérification vous sera envoyé. "
    "Vous pourrez ensuite choisir un nouveau mot de passe. "
    "La procédure est identique pour tous les types de compte."
)


# ---------------------------------------------------------------------------
# Tests: chunking
# ---------------------------------------------------------------------------

class TestChunking:
    def test_short_text_single_chunk(self):
        chunks = _chunk_text("Hello world.")
        assert len(chunks) == 1

    def test_long_text_multiple_chunks(self):
        long_text = " ".join(["Phrase numéro {i}." for i in range(50)])
        chunks = _chunk_text(long_text, max_chunk_size=100)
        assert len(chunks) > 1

    def test_empty_text(self):
        chunks = _chunk_text("")
        assert len(chunks) == 1
        assert chunks[0] == ""


# ---------------------------------------------------------------------------
# Tests: document ingestion
# ---------------------------------------------------------------------------

class TestIngestion:
    def test_ingest_and_list(self, store):
        doc_id = store.ingest_document(
            SAMPLE_CONTENT,
            source_url="https://example.com/faq",
            source_title="FAQ Mot de passe",
            bot_intents=["compte"],
        )

        docs = store.list_documents()
        assert len(docs) == 1
        assert docs[0]["doc_id"] == doc_id
        assert docs[0]["bot_intents"] == ["compte"]
        assert docs[0]["source_url"] == "https://example.com/faq"

    def test_ingest_creates_chunks(self, store):
        store.ingest_document(SAMPLE_CONTENT)
        assert store.has_documents()

    def test_re_ingest_replaces(self, store):
        doc_id = "my-doc-1"
        store.ingest_document("First version.", doc_id=doc_id)
        store.ingest_document("Second version.", doc_id=doc_id)

        docs = store.list_documents()
        assert len(docs) == 1

    def test_delete_document(self, store):
        doc_id = store.ingest_document("Test content.")
        assert store.has_documents()

        result = store.delete_document(doc_id)
        assert result is True
        assert not store.has_documents()


# ---------------------------------------------------------------------------
# Tests: search
# ---------------------------------------------------------------------------

class TestSearch:
    @pytest.mark.asyncio
    async def test_fts_search_finds_content(self, store):
        store.ingest_document(
            SAMPLE_CONTENT,
            source_url="https://example.com/faq",
            bot_intents=["compte"],
        )

        results = await store.search(
            "mot de passe", "collection",
        )
        assert len(results) > 0
        assert any("mot de passe" in r.text.lower() for r in results)

    @pytest.mark.asyncio
    async def test_search_with_intent_filter(self, store):
        store.ingest_document(
            "Comment suivre votre colis livraison.",
            bot_intents=["livraison"],
        )
        store.ingest_document(
            "Comment réinitialiser votre mot de passe.",
            bot_intents=["compte"],
        )

        results = await store.search(
            "colis", "collection",
            filters={"bot_intents": "livraison"},
        )
        # Should only find the livraison document
        for r in results:
            assert "livraison" in r.metadata["bot_intents"]

    @pytest.mark.asyncio
    async def test_search_empty_query(self, store):
        store.ingest_document("Some content.")
        results = await store.search("", "collection")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_no_results(self, store):
        store.ingest_document("Some content about dogs.")
        results = await store.search("xyznonexistent", "collection")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Tests: tags and coverage
# ---------------------------------------------------------------------------

class TestTags:
    def test_update_tags(self, store):
        doc_id = store.ingest_document(
            "Test content.", bot_intents=["old_intent"],
        )

        updated = store.update_tags(
            [doc_id], bot_intents=["new_intent"],
        )
        assert updated == 1

        docs = store.list_documents()
        assert docs[0]["bot_intents"] == ["new_intent"]

    def test_coverage_report(self, store):
        store.ingest_document("About delivery.", bot_intents=["livraison"])
        store.ingest_document("About billing.", bot_intents=["facturation"])
        store.ingest_document("Also delivery.", bot_intents=["livraison"])

        coverage = store.get_coverage(["livraison", "facturation", "retour"])
        assert coverage["livraison"] == 2
        assert coverage["facturation"] == 1
        assert coverage["retour"] == 0
