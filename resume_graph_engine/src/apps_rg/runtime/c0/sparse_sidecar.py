"""Apps RG-owned FTS5 sidecar for the C0.2 sparse retrieval lane.

The standalone Apps RG checkout owns its ``fact_vectors`` Chroma store under
this repository.  The monorepo helper that originally built the matching FTS5
sidecar is not available here, so this module keeps the same durable SQLite
shape while resolving every path from the Apps RG repository root.

It is deliberately narrow: source-grounded fact-vector rows go in, a local
SQLite sidecar is produced, and C0 reads it as a bounded lexical lane.  It
does not create graph claims, change embeddings, or perform any write-back
decision.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.runtime.local_retrieval import (
    HybridSearchResult,
    SparseLexicalHit,
    SparseLexicalLaneOutcome,
    SparseLexicalLaneStatus,
    SparseLexicalQuerySpec,
)

from apps_rg.repository_layout import repository_root

_LOGGER = logging.getLogger(__name__)

BATCH_SIZE = 500
SPARSE_PATH = repository_root(Path(__file__)) / "data" / "cache" / "sparse"

_COLLECTION_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_STOP = frozenset(
    "self cls none true false return if else elif for while try except finally with "
    "as import from def class pass break continue and or not in is lambda yield raise "
    "assert del global nonlocal async await the a an of to".split()
)
_SPLIT_RE = re.compile(r"[^A-Za-z0-9_]+")
_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")


def _collection_name(value: str) -> str:
    name = str(value or "").strip()
    if not _COLLECTION_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid sparse collection name: {value!r}")
    return name


def _target_dir(sparse_dir: str | Path | None = None) -> Path:
    return Path(sparse_dir) if sparse_dir is not None else SPARSE_PATH


def sidecar_path(
    collection_name: str,
    *,
    sparse_dir: str | Path | None = None,
) -> Path:
    """Return the controlled sidecar path for one internal collection name."""
    return _target_dir(sparse_dir) / f"{_collection_name(collection_name)}.db"


def _split_identifier(name: str) -> list[str]:
    tokens: list[str] = []
    for part in name.split("_"):
        for subtoken in _CAMEL_RE.sub(r"\1 \2", part).split():
            if len(subtoken) > 1:
                tokens.append(subtoken.lower())
    return tokens


def tokenize(text: str) -> list[str]:
    """Tokenize lexical content consistently for indexing and querying."""
    tokens: list[str] = []
    seen: set[str] = set()

    def _emit(token: str) -> None:
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)

    for raw in _SPLIT_RE.split(str(text or "")):
        if not raw or len(raw) < 2:
            continue
        lower = raw.lower()
        if lower in _STOP:
            continue
        _emit(lower)
        for part in _split_identifier(raw):
            if part not in _STOP:
                _emit(part)
    return tokens


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS docs (
            id       TEXT PRIMARY KEY,
            document TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts
            USING fts5(
                id UNINDEXED,
                document,
                content=docs,
                content_rowid=rowid,
                tokenize="unicode61 tokenchars '_'"
            );

        CREATE TABLE IF NOT EXISTS term_freq (
            term   TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            freq   INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (term, doc_id)
        );

        CREATE INDEX IF NOT EXISTS idx_term ON term_freq(term);
        CREATE INDEX IF NOT EXISTS idx_doc ON term_freq(doc_id);

        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    connection.commit()


def _rebuild_fts(connection: sqlite3.Connection) -> None:
    connection.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild')")
    connection.commit()


def _refresh_meta(connection: sqlite3.Connection, collection_name: str) -> dict[str, int]:
    doc_count = int(connection.execute("SELECT COUNT(*) FROM docs").fetchone()[0] or 0)
    term_count = int(connection.execute("SELECT COUNT(*) FROM term_freq").fetchone()[0] or 0)
    connection.executemany(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
        (
            ("collection", collection_name),
            ("doc_count", str(doc_count)),
            ("term_count", str(term_count)),
            ("built_at", str(time.time())),
        ),
    )
    connection.commit()
    return {"doc_count": doc_count, "term_count": term_count}


def _rows_for_documents(rows: Sequence[Mapping[str, object]]) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, int]]]:
    document_rows: list[tuple[str, str, str]] = []
    term_rows: list[tuple[str, str, int]] = []
    for row in rows:
        document_id = str(row.get("id") or "").strip()
        if not document_id:
            continue
        document = str(row.get("document") or "")
        metadata = row.get("metadata")
        metadata_json = json.dumps(
            metadata if isinstance(metadata, dict) else {},
            ensure_ascii=False,
            sort_keys=True,
        )
        document_rows.append((document_id, document, metadata_json))
        for term, frequency in Counter(tokenize(document)).items():
            term_rows.append((term, document_id, frequency))
    return document_rows, term_rows


def _upsert_batches(
    connection: sqlite3.Connection,
    document_rows: Sequence[tuple[str, str, str]],
    term_rows: Sequence[tuple[str, str, int]],
) -> None:
    if document_rows:
        document_ids = [(row[0],) for row in document_rows]
        connection.executemany("DELETE FROM term_freq WHERE doc_id = ?", document_ids)
        connection.executemany("DELETE FROM docs WHERE id = ?", document_ids)
        connection.executemany(
            "INSERT OR REPLACE INTO docs(id, document, metadata) VALUES(?, ?, ?)",
            document_rows,
        )
    if term_rows:
        connection.executemany(
            """INSERT INTO term_freq(term, doc_id, freq) VALUES(?, ?, ?)
               ON CONFLICT(term, doc_id) DO UPDATE SET freq = excluded.freq""",
            term_rows,
        )
    connection.commit()


def upsert_documents(
    collection_name: str,
    rows: Sequence[Mapping[str, object]],
    *,
    sparse_dir: str | Path | None = None,
) -> dict[str, int]:
    """Incrementally synchronize source-grounded rows into the FTS5 sidecar."""
    name = _collection_name(collection_name)
    target_dir = _target_dir(sparse_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = sidecar_path(name, sparse_dir=target_dir)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        _create_schema(connection)
        document_rows, term_rows = _rows_for_documents(rows)
        _upsert_batches(connection, document_rows, term_rows)
        if document_rows:
            _rebuild_fts(connection)
        stats = _refresh_meta(connection, name)
        return {"upserted_count": len(document_rows), **stats}
    finally:
        connection.close()


def build_for_collection(
    collection_name: str,
    dry_run: bool = False,
    *,
    chroma_path: str | Path | None = None,
    sparse_dir: str | Path | None = None,
) -> dict[str, int]:
    """Rebuild the local sparse sidecar from the controlled Chroma collection."""
    name = _collection_name(collection_name)
    from apps_rg.runtime.c0.chroma_persistent_client import ensure_apps_rg_chroma_client

    resolved_chroma = str(chroma_path or (repository_root(Path(__file__)) / "data" / "cache" / "chromadb"))
    client = ensure_apps_rg_chroma_client(resolved_chroma)
    try:
        collection = client.get_collection(name)
    except (KeyError, ValueError):
        return {"doc_count": 0, "term_count": 0}

    total = int(collection.count())
    if total <= 0:
        return {"doc_count": 0, "term_count": 0}
    if dry_run:
        return {"doc_count": total, "term_count": 0}

    target_dir = _target_dir(sparse_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = sidecar_path(name, sparse_dir=target_dir)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        _create_schema(connection)
        connection.execute("DELETE FROM term_freq")
        connection.execute("DELETE FROM docs")
        connection.commit()

        offset = 0
        while offset < total:
            batch = collection.get(
                limit=BATCH_SIZE,
                offset=offset,
                include=["documents", "metadatas"],
            )
            ids = list(batch.get("ids") or [])
            if not ids:
                break
            documents = list(batch.get("documents") or [])
            metadata = list(batch.get("metadatas") or [])
            rows: list[dict[str, object]] = []
            for index, document_id in enumerate(ids):
                rows.append(
                    {
                        "id": str(document_id),
                        "document": str(documents[index] or "") if index < len(documents) else "",
                        "metadata": metadata[index] if index < len(metadata) else {},
                    }
                )
            document_rows, term_rows = _rows_for_documents(rows)
            connection.executemany(
                "INSERT OR REPLACE INTO docs(id, document, metadata) VALUES(?, ?, ?)",
                document_rows,
            )
            if term_rows:
                connection.executemany(
                    "INSERT INTO term_freq(term, doc_id, freq) VALUES(?, ?, ?)",
                    term_rows,
                )
            connection.commit()
            offset += len(ids)

        _rebuild_fts(connection)
        return _refresh_meta(connection, name)
    finally:
        connection.close()


def sidecar_summary(
    collection_name: str,
    *,
    sparse_dir: str | Path | None = None,
) -> dict[str, object]:
    """Return an integrity-focused read-only summary of a sparse sidecar."""
    path = sidecar_path(collection_name, sparse_dir=sparse_dir)
    if not path.is_file():
        return {"path": str(path), "available": False, "doc_count": 0, "error": "missing"}
    try:
        connection = sqlite3.connect(str(path))
        try:
            docs = int(connection.execute("SELECT COUNT(*) FROM docs").fetchone()[0] or 0)
            fts_docs = int(connection.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0] or 0)
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return {
            "path": str(path),
            "available": False,
            "doc_count": 0,
            "error": f"unreadable:{type(exc).__name__}",
        }
    if docs <= 0:
        return {"path": str(path), "available": False, "doc_count": 0, "error": "empty"}
    if fts_docs != docs:
        return {
            "path": str(path),
            "available": False,
            "doc_count": docs,
            "error": "fts_docs_count_mismatch",
        }
    return {"path": str(path), "available": True, "doc_count": docs, "error": ""}


def sparse_sidecar_exists(
    collection_name: str,
    *,
    sparse_dir: str | Path | None = None,
) -> bool:
    """True only when a readable, nonempty, synchronized sidecar exists."""
    return bool(sidecar_summary(collection_name, sparse_dir=sparse_dir).get("available"))


class AppsRgSparseIndex:
    """Read-only lexical adapter over an Apps RG-owned SQLite FTS5 sidecar."""

    def __init__(self, collection_name: str, *, sparse_dir: str | Path | None = None) -> None:
        self.collection_name = _collection_name(collection_name)
        self._db_path = sidecar_path(self.collection_name, sparse_dir=sparse_dir)
        self._available = sparse_sidecar_exists(self.collection_name, sparse_dir=sparse_dir)

    @property
    def is_available(self) -> bool:
        return self._available

    def search(self, query: str, top_k: int = 10) -> list[dict[str, object]]:
        if not self._available:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        maximum = max(1, int(top_k))
        try:
            connection = sqlite3.connect(str(self._db_path))
            try:
                connection.execute("PRAGMA query_only=ON")
                rows = connection.execute(
                    "SELECT id, document FROM docs_fts WHERE docs_fts MATCH ? "
                    "ORDER BY rank, id LIMIT ?",
                    (" ".join(tokens), maximum * 2),
                ).fetchall()
                if not rows and len(tokens) > 1:
                    rows = connection.execute(
                        "SELECT id, document FROM docs_fts WHERE docs_fts MATCH ? "
                        "ORDER BY rank, id LIMIT ?",
                        (" OR ".join(tokens), maximum * 2),
                    ).fetchall()

                results: list[dict[str, object]] = []
                for rank, (document_id, document) in enumerate(rows[:maximum]):
                    metadata: dict[str, object] = {}
                    metadata_row = connection.execute(
                        "SELECT metadata FROM docs WHERE id = ?", (document_id,)
                    ).fetchone()
                    if metadata_row and metadata_row[0]:
                        try:
                            decoded = json.loads(metadata_row[0])
                        except (json.JSONDecodeError, TypeError, ValueError):
                            decoded = {}
                        if isinstance(decoded, dict):
                            metadata = decoded
                    results.append(
                        {
                            "id": str(document_id),
                            "content": str(document or ""),
                            "score": 1.0 / (1.0 + rank),
                            "metadata": metadata,
                            "source": "apps_rg_sparse_fts",
                        }
                    )
                return results
            finally:
                connection.close()
        except sqlite3.Error as exc:
            _LOGGER.error("Apps RG sparse lookup failed for %s: %s", self.collection_name, exc)
            return []


def _metadata_matches(row_metadata: Mapping[str, object], expected: Mapping[str, Any] | None) -> bool:
    if not expected:
        return True
    return all(key in row_metadata and row_metadata[key] == value for key, value in expected.items())


def _receipt_ref(lane_id: str, status: SparseLexicalLaneStatus, hit_count: int) -> str:
    return f"ref:sparse:lane:{lane_id.replace(':', '_')}:status={status.value}:hits={hit_count}"


def _hybrid_row_to_hit(row: HybridSearchResult) -> SparseLexicalHit:
    metadata = dict(row.metadata or {})
    return SparseLexicalHit(
        chunk_id=row.chunk_id,
        source_id=str(metadata.get("source_document_id") or metadata.get("source_id") or row.chunk_id),
        text=row.content,
        span_ref=row.content[:120] if row.content else "",
        lexical_score=float(row.lexical_score),
        dense_score=float(row.vector_score),
        metadata=metadata,
        citation_ref=f"urn:chunk:{row.chunk_id}",
    )


def query_apps_rg_sparse_lexical_lane(
    spec: SparseLexicalQuerySpec,
    *,
    sparse_dir: str | Path | None = None,
) -> SparseLexicalLaneOutcome:
    """Run the Apps RG C0 sparse lane without resolving another checkout's paths."""
    name = str(spec.sparse_index_collection_name or "").strip()
    if not name:
        status = SparseLexicalLaneStatus.UNAVAILABLE
        return SparseLexicalLaneOutcome(
            lane_id=spec.lane_id,
            status=status,
            hits=(),
            receipt_ref=_receipt_ref(spec.lane_id, status, 0),
            hybrid_rows=(),
        )
    try:
        index = AppsRgSparseIndex(name, sparse_dir=sparse_dir)
    except ValueError:
        index = None
    if index is None or not index.is_available:
        status = SparseLexicalLaneStatus.UNAVAILABLE
        return SparseLexicalLaneOutcome(
            lane_id=spec.lane_id,
            status=status,
            hits=(),
            receipt_ref=_receipt_ref(spec.lane_id, status, 0),
            hybrid_rows=(),
        )

    rows = index.search(spec.query_text, top_k=max(1, int(spec.top_k)))
    hybrid_rows = tuple(
        HybridSearchResult(
            chunk_id=str(row.get("id") or ""),
            content=str(row.get("content") or ""),
            metadata=dict(row.get("metadata") or {}),
            combined_score=float(row.get("score") or 0.0),
            source="lexical",
            vector_score=0.0,
            lexical_score=float(row.get("score") or 0.0),
        )
        for row in rows
        if str(row.get("id") or "").strip()
    )
    filtered = tuple(
        row for row in hybrid_rows if _metadata_matches(row.metadata or {}, spec.metadata_filter)
    )
    status = SparseLexicalLaneStatus.OK if filtered else SparseLexicalLaneStatus.EMPTY
    return SparseLexicalLaneOutcome(
        lane_id=spec.lane_id,
        status=status,
        hits=tuple(_hybrid_row_to_hit(row) for row in filtered),
        receipt_ref=_receipt_ref(spec.lane_id, status, len(filtered)),
        hybrid_rows=filtered,
    )
