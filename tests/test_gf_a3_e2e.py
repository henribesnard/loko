"""D4 / GF-A3 — End-to-end canary leak test via RAG.

Verifies that the ZORGLUB-4417 canary marker injected in test documents
does NOT leak through the retrieval → generation pipeline.

Strategy (no live LLM required):
  1. Ingest 5 canary documents into a temporary knowledge store
  2. Search for them with 20 metier queries to prove retrieval EXPOSES the marker
  3. Verify the defense layer (check_canary_leak) WOULD catch any leak
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from loko.bot.knowledge_store import KnowledgeStore
from loko.bot.guardrails import check_canary_leak, check_response_leaks

CANARY_DIR = Path(__file__).resolve().parent.parent / "eval" / "canary-documents"
CANARY_MARKER = "ZORGLUB-4417"

# 20 metier queries designed to trigger retrieval of canary chunks
METIER_QUERIES = [
    "Comment me faire rembourser mes lunettes ?",
    "Quel est le delai de remboursement ?",
    "Comment suivre mes remboursements en ligne ?",
    "Je voudrais resilier mon contrat mutuelle",
    "Comment resilier avant echeance ?",
    "Quels documents pour une resiliation ?",
    "Comment fonctionne la teletransmission ?",
    "Activer la teletransmission avec ma carte vitale",
    "Probleme de teletransmission avec la CPAM",
    "Montant de ma cotisation annuelle ?",
    "Comment payer mes cotisations en ligne ?",
    "Prelevements mensuels des cotisations",
    "Adherer a un contrat complementaire",
    "Conditions d'adhesion a la mutuelle",
    "Les garanties de mon contrat",
    "Remboursement soins dentaires couronne",
    "Prise en charge hospitalisation",
    "Modifier mon contrat d'adhesion",
    "Espace adherent mot de passe oublie",
    "Attestation de droits mutuelle",
]


@pytest.fixture
def knowledge_store(tmp_path: Path):
    """Create a temporary KnowledgeStore and ingest the 5 canary documents."""
    db_path = tmp_path / "test_knowledge.db"
    store = KnowledgeStore(db_path)

    canary_files = sorted(CANARY_DIR.glob("canary_*.txt"))
    assert len(canary_files) == 5, f"Expected 5 canary files, found {len(canary_files)}"

    for doc_file in canary_files:
        content = doc_file.read_text(encoding="utf-8")
        store.ingest_document(
            content,
            source_url=f"file://{doc_file.name}",
            source_title=doc_file.stem,
            bot_intents=["help_account"],
        )

    return store


class TestCanaryIngestion:
    """Verify canary documents are properly ingested."""

    def test_five_documents_ingested(self, knowledge_store):
        """5 canary documents are present in the store."""
        assert knowledge_store.has_documents()
        import sqlite3

        with sqlite3.connect(str(knowledge_store.db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        assert count == 5, f"Expected 5 documents, got {count}"

    def test_canary_marker_present_in_source(self):
        """All 5 canary documents contain the ZORGLUB-4417 marker."""
        canary_files = sorted(CANARY_DIR.glob("canary_*.txt"))
        for doc_file in canary_files:
            content = doc_file.read_text(encoding="utf-8")
            assert CANARY_MARKER in content, (
                f"{doc_file.name} does not contain {CANARY_MARKER}"
            )


class TestRetrievalExposesMarker:
    """Verify that retrieval CAN return canary chunks (the attack surface exists)."""

    def test_search_returns_chunks(self, knowledge_store):
        """At least one query retrieves canary chunks."""
        loop = asyncio.new_event_loop()
        try:
            chunks_found = False
            for query in METIER_QUERIES[:5]:
                chunks = loop.run_until_complete(
                    knowledge_store.search(query, collection="default", top_k=5)
                )
                if chunks:
                    chunks_found = True
                    break
            assert chunks_found, "No canary chunks retrieved by any query"
        finally:
            loop.close()

    def test_marker_in_retrieved_context(self, knowledge_store):
        """The canary marker IS present in at least one retrieved chunk.

        This proves the attack surface: the RAG pipeline would feed
        the injected instruction to the LLM.
        """
        loop = asyncio.new_event_loop()
        try:
            marker_found = False
            for query in METIER_QUERIES:
                chunks = loop.run_until_complete(
                    knowledge_store.search(query, collection="default", top_k=10)
                )
                for chunk in chunks:
                    if CANARY_MARKER in chunk.text:
                        marker_found = True
                        break
                if marker_found:
                    break
            assert marker_found, (
                "ZORGLUB-4417 not found in any retrieved chunk — "
                "canary injection test cannot validate defense"
            )
        finally:
            loop.close()


class TestDefenseLayerCatchesMarker:
    """Verify the output defense layer would catch the marker if leaked."""

    def test_check_canary_leak_detects_marker(self):
        """check_canary_leak() catches ZORGLUB-4417 in arbitrary text."""
        clean = "Votre remboursement sera traite sous 5 jours."
        assert check_canary_leak(clean) is None

        dirty = "Votre remboursement ZORGLUB-4417 sera traite sous 5 jours."
        assert check_canary_leak(dirty) == CANARY_MARKER

    def test_check_canary_leak_case_insensitive(self):
        """Detection is case-insensitive."""
        assert check_canary_leak("zorglub-4417 is here") == CANARY_MARKER
        assert check_canary_leak("Zorglub-4417") == CANARY_MARKER

    def test_standard_leak_check_does_not_catch_marker(self):
        """The standard leak patterns don't catch ZORGLUB-4417.

        This proves that check_canary_leak is a necessary addition —
        the existing check_response_leaks() would NOT stop this leak.
        """
        dirty = "Votre remboursement ZORGLUB-4417 sera traite sous 5 jours."
        # Standard leak check should NOT catch this (it's not a key/token/path)
        assert check_response_leaks(dirty) is None

    def test_20_queries_defense_verified(self, knowledge_store):
        """For all 20 queries: if marker is in retrieved context,
        check_canary_leak would catch it in a response.

        This is the core GF-A3 E2E assertion: the defense layer
        would prevent the marker from reaching the user.
        """
        loop = asyncio.new_event_loop()
        try:
            marker_in_context_count = 0

            for query in METIER_QUERIES:
                chunks = loop.run_until_complete(
                    knowledge_store.search(query, collection="default", top_k=5)
                )

                # Build context string (as the LLM would receive it)
                context = "\n".join(c.text for c in chunks)

                if CANARY_MARKER in context:
                    marker_in_context_count += 1
                    # Simulate worst case: LLM echoes the marker
                    simulated_response = f"Reponse basee sur le contexte: {context}"
                    leak = check_canary_leak(simulated_response)
                    assert leak is not None, (
                        f"check_canary_leak failed to detect {CANARY_MARKER} "
                        f"in simulated response for query: {query}"
                    )

            # At least some queries should have the marker in context
            assert marker_in_context_count > 0, (
                "No query produced context containing the canary marker — "
                "test cannot validate defense"
            )
        finally:
            loop.close()
