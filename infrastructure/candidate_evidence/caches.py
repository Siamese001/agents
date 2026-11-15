"""In-memory dense, sparse, and ColBERT caches for candidate evidence retrieval.

Zero upward imports: never import ``apps_lic``, ``apps_rg``, ``apps_research``, or ``apps_eval``.
"""

from __future__ import annotations

import json
import math
import sqlite3
import struct
from collections.abc import Mapping, Sequence
from typing import Any

BGE_DENSE_DIM = 1024


def dequantize_colbert_vectors_int8(
    blob: bytes,
    scales: Sequence[float] | str,
    *,
    dim: int = BGE_DENSE_DIM,
) -> list[tuple[float, ...]]:
    """Dequantize int8 ColBERT vectors with per-token scale factors."""
    parsed_scales = json.loads(scales) if isinstance(scales, str) else scales
    token_count = len(parsed_scales)
    if token_count < 1 or len(blob) != token_count * dim:
        return []
    out: list[tuple[float, ...]] = []
    for idx, scale in enumerate(parsed_scales):
        s = float(scale) or (1.0 / 127.0)
        start = idx * dim
        raw_slice = blob[start : start + dim]
        floats = [((b - 256) if b >= 128 else b) * s for b in raw_slice]
        norm = math.sqrt(sum(v * v for v in floats)) or 1.0
        out.append(tuple(v / norm for v in floats))
    return out


class CandidateEvidenceVectorCache:
    """In-memory dense float32 vector cache loaded from SQLite unit_vectors."""

    def __init__(self) -> None:
        self.record_ids: list[str] = []
        self.vectors: list[tuple[float, ...]] = []
        self._key: tuple[str, int] | None = None

    def ensure_loaded(self, conn: sqlite3.Connection, db_path: str = "") -> None:
        """Ensure dense float32 vectors are loaded from unit_vectors table."""
        key = (str(db_path), len(self.record_ids))
        if self._key == key and self.record_ids:
            return
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'unit_vectors' LIMIT 1"
        ).fetchone()
        if not has_table:
            return
        rows = conn.execute("SELECT unit_id, vector FROM unit_vectors ORDER BY unit_id").fetchall()
        r_ids: list[str] = []
        vecs: list[tuple[float, ...]] = []
        for uid, blob in rows:
            if isinstance(blob, bytes) and len(blob) == BGE_DENSE_DIM * 4:
                vec = struct.unpack(f"<{BGE_DENSE_DIM}f", blob)
                r_ids.append(str(uid))
                vecs.append(tuple(float(v) for v in vec))
        self.record_ids = r_ids
        self.vectors = vecs
        self._key = (str(db_path), len(r_ids))

    def score_query(
        self,
        query_vec: Sequence[float],
        *,
        allowed_ids: set[str] | None = None,
        top_k: int = 100,
    ) -> list[tuple[str, float]]:
        """Score dense cosine dot-product against cached L2-normalized vectors."""
        if not self.record_ids or not query_vec:
            return []
        q = tuple(float(v) for v in query_vec)
        scored: list[tuple[float, str]] = []
        for idx, rid in enumerate(self.record_ids):
            if allowed_ids is not None and rid not in allowed_ids:
                continue
            vec = self.vectors[idx]
            sim = math.fsum(a * b for a, b in zip(q, vec))
            scored.append((round(sim, 6), rid))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(rid, sim) for sim, rid in scored[: max(1, int(top_k))]]


class CandidateEvidenceSparseCache:
    """In-memory inverted postings index for learned sparse lexical weights."""

    def __init__(self) -> None:
        self.record_ids: list[str] = []
        self.postings: dict[str, list[tuple[int, float]]] = {}
        self._key: tuple[str, int] | None = None

    def ensure_loaded(self, conn: sqlite3.Connection, db_path: str = "") -> None:
        """Ensure inverted index is compiled from assertion_learned_sparse table."""
        key = (str(db_path), len(self.record_ids))
        if self._key == key and self.record_ids:
            return
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'assertion_learned_sparse' LIMIT 1"
        ).fetchone()
        if not has_table:
            return
        rows = conn.execute(
            "SELECT assertion_id, weights_json FROM assertion_learned_sparse ORDER BY assertion_id"
        ).fetchall()
        r_ids: list[str] = []
        inv: dict[str, list[tuple[int, float]]] = {}
        for idx, (aid, w_json) in enumerate(rows):
            r_ids.append(str(aid))
            try:
                weights = json.loads(str(w_json or "{}"))
            except (json.JSONDecodeError, TypeError):
                weights = {}
            if isinstance(weights, Mapping):
                for tok, w in weights.items():
                    wf = float(w or 0.0)
                    if wf > 0.0 and math.isfinite(wf):
                        inv.setdefault(str(tok), []).append((idx, wf))
        self.record_ids = r_ids
        self.postings = inv
        self._key = (str(db_path), len(r_ids))

    def score_query(
        self,
        query_weights: Mapping[str, float],
        *,
        allowed_ids: set[str] | None = None,
        top_k: int = 100,
    ) -> list[tuple[str, float]]:
        """Score learned sparse lexical inner product across inverted postings."""
        if not self.record_ids or not query_weights:
            return []
        acc: dict[int, float] = {}
        for tok, qw in query_weights.items():
            if qw > 0.0:
                for doc_idx, dw in self.postings.get(str(tok), ()):
                    acc[doc_idx] = acc.get(doc_idx, 0.0) + qw * dw
        scored = [
            (round(acc.get(idx, 0.0), 6), rid)
            for idx, rid in enumerate(self.record_ids)
            if allowed_ids is None or rid in allowed_ids
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(rid, sc) for sc, rid in scored[: max(1, int(top_k))]]


class CandidateEvidenceColbertCache:
    """In-memory cache for int8 ColBERT token multi-vectors."""

    def __init__(self) -> None:
        self.tensors: dict[str, list[tuple[float, ...]]] = {}
        self._key: tuple[str, int] | None = None

    def ensure_loaded(self, conn: sqlite3.Connection, db_path: str = "") -> None:
        """Ensure int8 multi-vectors are decoded from assertion_colbert_vectors."""
        key = (str(db_path), len(self.tensors))
        if self._key == key and self.tensors:
            return
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'assertion_colbert_vectors' LIMIT 1"
        ).fetchone()
        if not has_table:
            return
        rows = conn.execute(
            "SELECT assertion_id, scales_json, vectors_int8 FROM assertion_colbert_vectors ORDER BY assertion_id"
        ).fetchall()
        tensors: dict[str, list[tuple[float, ...]]] = {}
        for aid, scales_json, blob in rows:
            vecs = dequantize_colbert_vectors_int8(bytes(blob), str(scales_json))
            if vecs:
                tensors[str(aid)] = vecs
        self.tensors = tensors
        self._key = (str(db_path), len(tensors))

    def score_candidates(
        self,
        query_tokens: Sequence[Sequence[float]],
        candidate_ids: Sequence[str],
    ) -> list[tuple[str, float]]:
        """Compute ColBERT MaxSim late-interaction scores over candidate IDs."""
        if not query_tokens or not candidate_ids:
            return []
        q_vecs = [tuple(float(v) for v in qv) for qv in query_tokens]
        scored: list[tuple[float, str]] = []
        for cid in candidate_ids:
            doc_vecs = self.tensors.get(str(cid))
            if not doc_vecs:
                scored.append((0.0, str(cid)))
                continue
            total = 0.0
            for qv in q_vecs:
                best = max((math.fsum(a * b for a, b in zip(qv, dv)) for dv in doc_vecs), default=0.0)
                total += max(0.0, best)
            scored.append((round(total / len(q_vecs), 6), str(cid)))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(cid, sc) for sc, cid in scored]


__all__ = [
    "BGE_DENSE_DIM",
    "CandidateEvidenceColbertCache",
    "CandidateEvidenceSparseCache",
    "CandidateEvidenceVectorCache",
    "dequantize_colbert_vectors_int8",
]
