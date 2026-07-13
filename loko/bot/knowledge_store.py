"""LOKO Bot — Persistent knowledge store (SQLite FTS5).

Provides document ingestion, chunk storage, and BM25 search with
hard metadata filtering (intent, sub-motif, confidentiality).

Implements the ChunkSearchBackend protocol from retrieval_filter.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from loko.bot.models import Chunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_KNOWLEDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL DEFAULT '',
    source_title TEXT NOT NULL DEFAULT '',
    raw_content TEXT NOT NULL,
    content_hash TEXT NOT NULL DEFAULT '',
    bot_intents TEXT NOT NULL DEFAULT '[]',
    bot_sub_motifs TEXT NOT NULL DEFAULT '[]',
    confidentiality TEXT NOT NULL DEFAULT 'public',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_docs_intent ON documents(bot_intents);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    source_title TEXT NOT NULL DEFAULT '',
    bot_intents TEXT NOT NULL DEFAULT '[]',
    bot_sub_motifs TEXT NOT NULL DEFAULT '[]',
    confidentiality TEXT NOT NULL DEFAULT 'public',
    chunk_index INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_intent ON chunks(bot_intents);

-- FTS5 virtual table for BM25 search
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    text,
    content='chunks',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, chunk_id, text)
    VALUES (new.rowid, new.chunk_id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, text)
    VALUES ('delete', old.rowid, old.chunk_id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, text)
    VALUES ('delete', old.rowid, old.chunk_id, old.text);
    INSERT INTO chunks_fts(rowid, chunk_id, text)
    VALUES (new.rowid, new.chunk_id, new.text);
END;
"""


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _chunk_text(text: str, max_chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks by sentence boundaries."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        if current_len + len(sentence) > max_chunk_size and current:
            chunks.append(" ".join(current))
            # Keep last few sentences for overlap
            overlap_text = " ".join(current)
            if len(overlap_text) > overlap:
                # Find the split point for overlap
                current = current[-1:]
                current_len = sum(len(s) for s in current)
            else:
                current = []
                current_len = 0

        current.append(sentence)
        current_len += len(sentence)

    if current:
        chunks.append(" ".join(current))

    return chunks if chunks else [text]


# ---------------------------------------------------------------------------
# Knowledge store
# ---------------------------------------------------------------------------


class KnowledgeStore:
    """SQLite-backed knowledge store with FTS5 search for a single bot."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_KNOWLEDGE_SCHEMA)
            # §5.3: idempotent migration — add source_id column
            self._migrate_source_id(conn)

    @staticmethod
    def _migrate_source_id(conn: sqlite3.Connection) -> None:
        """Add source_id column to documents and chunks if missing."""
        # Check if column already exists
        cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
        if "source_id" not in cols:
            conn.execute("ALTER TABLE documents ADD COLUMN source_id TEXT DEFAULT NULL")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_docs_source ON documents(source_id)"
            )
            logger.info("Migrated documents table: added source_id column")
        chunk_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(chunks)").fetchall()
        }
        if "source_id" not in chunk_cols:
            conn.execute("ALTER TABLE chunks ADD COLUMN source_id TEXT DEFAULT NULL")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id)"
            )
            logger.info("Migrated chunks table: added source_id column")

    # ------------------------------------------------------------------
    # Document CRUD
    # ------------------------------------------------------------------

    def ingest_document(
        self,
        content: str,
        *,
        source_url: str = "",
        source_title: str = "",
        bot_intents: list[str] | None = None,
        bot_sub_motifs: list[str] | None = None,
        confidentiality: str = "public",
        doc_id: str | None = None,
        source_id: str | None = None,
    ) -> str:
        """Ingest a document: split into chunks and store.

        Returns the doc_id.
        """
        if not doc_id:
            doc_id = str(uuid.uuid4())

        intents = bot_intents or []
        sub_motifs = bot_sub_motifs or []
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        with self._connect() as conn:
            # Delete existing document with same ID (re-ingestion)
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))

            conn.execute(
                """INSERT INTO documents
                   (doc_id, source_url, source_title, raw_content, content_hash,
                    bot_intents, bot_sub_motifs, confidentiality, source_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc_id,
                    source_url,
                    source_title,
                    content,
                    content_hash,
                    json.dumps(intents),
                    json.dumps(sub_motifs),
                    confidentiality,
                    source_id,
                ),
            )

            # Chunk the content
            chunks = _chunk_text(content)
            for i, chunk_text in enumerate(chunks):
                chunk_id = f"{doc_id}:{i}"
                conn.execute(
                    """INSERT INTO chunks
                       (chunk_id, doc_id, text, source_url, source_title,
                        bot_intents, bot_sub_motifs, confidentiality, chunk_index,
                        source_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chunk_id,
                        doc_id,
                        chunk_text,
                        source_url,
                        source_title,
                        json.dumps(intents),
                        json.dumps(sub_motifs),
                        confidentiality,
                        i,
                        source_id,
                    ),
                )

        logger.info(
            "Ingested document %s (%d chunks, intents=%s)",
            doc_id,
            len(chunks),
            intents,
        )
        return doc_id

    def delete_document(self, doc_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM documents WHERE doc_id = ?",
                (doc_id,),
            )
            return cursor.rowcount > 0

    def delete_by_source(self, source_id: str) -> int:
        """Delete all documents (and their chunks) belonging to a source."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM documents WHERE source_id = ?",
                (source_id,),
            )
            count = cursor.rowcount
            if count:
                logger.info("Deleted %d document(s) for source %s", count, source_id)
            return count

    def count_by_source(self, source_id: str) -> int:
        """Count documents belonging to a source."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM documents WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    def list_documents(
        self,
        *,
        intent: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            where_parts: list[str] = []
            params: list[Any] = []
            if intent:
                where_parts.append("bot_intents LIKE ?")
                params.append(f'%"{intent}"%')
            if source_id:
                where_parts.append("source_id = ?")
                params.append(source_id)

            where_clause = ""
            if where_parts:
                where_clause = "WHERE " + " AND ".join(where_parts)

            rows = conn.execute(
                f"""SELECT doc_id, source_url, source_title, content_hash,
                           bot_intents, bot_sub_motifs, confidentiality,
                           source_id, created_at
                    FROM documents
                    {where_clause}
                    ORDER BY created_at DESC LIMIT ?""",
                params + [limit],
            ).fetchall()

            return [
                {
                    "doc_id": r["doc_id"],
                    "source_url": r["source_url"],
                    "source_title": r["source_title"],
                    "bot_intents": json.loads(r["bot_intents"]),
                    "bot_sub_motifs": json.loads(r["bot_sub_motifs"]),
                    "confidentiality": r["confidentiality"],
                    "source_id": r["source_id"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    def update_tags(
        self,
        doc_ids: list[str],
        *,
        bot_intents: list[str] | None = None,
        bot_sub_motifs: list[str] | None = None,
    ) -> int:
        """Bulk-update intent/sub-motif tags on documents and their chunks."""
        updated = 0
        with self._connect() as conn:
            for doc_id in doc_ids:
                updates: list[str] = []
                params: list[Any] = []

                if bot_intents is not None:
                    updates.append("bot_intents = ?")
                    params.append(json.dumps(bot_intents))
                if bot_sub_motifs is not None:
                    updates.append("bot_sub_motifs = ?")
                    params.append(json.dumps(bot_sub_motifs))

                if not updates:
                    continue

                set_clause = ", ".join(updates)
                params.append(doc_id)

                cursor = conn.execute(
                    f"UPDATE documents SET {set_clause} WHERE doc_id = ?",
                    params,
                )
                if cursor.rowcount:
                    updated += cursor.rowcount
                    # Also update chunks
                    chunk_params = params[:-1] + [doc_id]
                    conn.execute(
                        f"UPDATE chunks SET {set_clause} WHERE doc_id = ?",
                        chunk_params,
                    )

        return updated

    def get_coverage(self, intents: list[str]) -> dict[str, int]:
        """Return document count per intent (for publication checks)."""
        coverage: dict[str, int] = {}
        with self._connect() as conn:
            for intent_id in intents:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM documents WHERE bot_intents LIKE ?",
                    (f'%"{intent_id}"%',),
                ).fetchone()
                coverage[intent_id] = row["cnt"] if row else 0
        return coverage

    def has_documents(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()
            return row["cnt"] > 0 if row else False

    # ------------------------------------------------------------------
    # Search (ChunkSearchBackend protocol)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        collection: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[Chunk]:
        """BM25 search with hard metadata filtering (pre-filtering).

        Filters are applied in the SQL query itself (not post-filtering),
        making confidentiality guarantees verifiable by construction (critère 6).
        """
        if not query.strip():
            return []

        with self._connect() as conn:
            # Build WHERE clauses for hard filtering
            where_parts: list[str] = []
            params: list[Any] = []

            if filters:
                if "bot_intents" in filters:
                    intent = filters["bot_intents"]
                    where_parts.append("c.bot_intents LIKE ?")
                    params.append(f'%"{intent}"%')

                if "bot_sub_motifs" in filters:
                    sub = filters["bot_sub_motifs"]
                    where_parts.append("c.bot_sub_motifs LIKE ?")
                    params.append(f'%"{sub}"%')

                if "confidentiality" in filters:
                    allowed = filters["confidentiality"]
                    if isinstance(allowed, list):
                        placeholders = ",".join("?" for _ in allowed)
                        where_parts.append(f"c.confidentiality IN ({placeholders})")
                        params.extend(allowed)
                    else:
                        where_parts.append("c.confidentiality = ?")
                        params.append(allowed)

            where_clause = ""
            if where_parts:
                where_clause = "AND " + " AND ".join(where_parts)

            # FTS5 BM25 search with pre-filtering
            # Use MATCH on the FTS table, JOIN with chunks for filtering
            import re

            terms = [
                term.replace('"', '""')
                for term in re.findall(r"\w+", query.lower())[:12]
                if len(term) > 2
            ]
            if not terms:
                return []
            fts_query = " OR ".join(f'"{term}"' for term in terms)

            sql = f"""
                SELECT c.chunk_id, c.text, c.source_url, c.source_title,
                       c.bot_intents, c.bot_sub_motifs, c.confidentiality,
                       rank
                FROM chunks_fts fts
                JOIN chunks c ON c.chunk_id = fts.chunk_id
                WHERE chunks_fts MATCH ?
                {where_clause}
                ORDER BY rank
                LIMIT ?
            """
            params_full = [fts_query] + params + [top_k]

            try:
                rows = conn.execute(sql, params_full).fetchall()
            except sqlite3.OperationalError:
                # FTS query syntax error — fallback to LIKE search
                logger.warning("FTS query failed, falling back to LIKE search")
                return await self._fallback_search(
                    conn,
                    query,
                    filters,
                    top_k,
                    where_parts,
                    params,
                )

            return [
                Chunk(
                    chunk_id=r["chunk_id"],
                    text=r["text"],
                    score=self._rank_to_score(r["rank"]),
                    source_url=r["source_url"],
                    source_title=r["source_title"],
                    metadata={
                        "bot_intents": json.loads(r["bot_intents"]),
                        "bot_sub_motifs": json.loads(r["bot_sub_motifs"]),
                        "confidentiality": r["confidentiality"],
                    },
                )
                for r in rows
            ]

    async def _fallback_search(
        self,
        conn: sqlite3.Connection,
        query: str,
        filters: dict[str, Any] | None,
        top_k: int,
        where_parts: list[str],
        params: list[Any],
    ) -> list[Chunk]:
        """Simple LIKE-based search as fallback when FTS fails."""
        where_clause = ""
        if where_parts:
            where_clause = "AND " + " AND ".join(where_parts)

        words = query.lower().split()
        like_parts = []
        like_params = []
        for word in words[:5]:  # limit to first 5 words
            like_parts.append("LOWER(c.text) LIKE ?")
            like_params.append(f"%{word}%")

        if like_parts:
            where_clause += " AND (" + " OR ".join(like_parts) + ")"

        sql = f"""
            SELECT c.chunk_id, c.text, c.source_url, c.source_title,
                   c.bot_intents, c.bot_sub_motifs, c.confidentiality
            FROM chunks c
            WHERE 1=1 {where_clause}
            LIMIT ?
        """
        all_params = params + like_params + [top_k]
        rows = conn.execute(sql, all_params).fetchall()

        return [
            Chunk(
                chunk_id=r["chunk_id"],
                text=r["text"],
                score=0.5,  # flat score for fallback
                source_url=r["source_url"],
                source_title=r["source_title"],
                metadata={
                    "bot_intents": json.loads(r["bot_intents"]),
                    "bot_sub_motifs": json.loads(r["bot_sub_motifs"]),
                    "confidentiality": r["confidentiality"],
                },
            )
            for r in rows
        ]

    @staticmethod
    def _rank_to_score(rank: float) -> float:
        """Convert FTS5 rank (negative BM25) to a 0-1 score."""
        # FTS5 rank is negative; stronger matches have a larger absolute BM25
        # magnitude. Convert that to a bounded score where higher is better.
        if rank >= 0:
            return 0.0
        magnitude = abs(rank)
        return max(0.0, min(1.0, magnitude / (1.0 + magnitude)))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_knowledge_store(bot_id: str) -> KnowledgeStore:
    """Get or create a KnowledgeStore for a bot."""
    from loko.bot.session_store import get_bot_dir

    db_path = get_bot_dir(bot_id) / "knowledge.db"
    return KnowledgeStore(db_path)
