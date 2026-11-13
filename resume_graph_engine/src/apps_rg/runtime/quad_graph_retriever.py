"""DIE-aligned 4-channel graph hybrid retriever, generational caches, and C0.1->C0.3 traversal."""

from __future__ import annotations

import json
import math
import sqlite3
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.runtime.bge_multi_head import (
    BGE_DENSE_DIM,
    decode_colbert_int8,
    project_text_multi_head,
)
from apps_rg.runtime.graph_skill_hybrid_retrieval import (
    CALIBRATED_HYBRID_RRF_WEIGHTS,
    DEFAULT_GRAPH_SIGNAL_WEIGHT,
    bm25_rank,
    compute_candidate_union,
    compute_graph_expand_signals,
    renormalize_active_rrf_weights,
    sqlite_fts5_bm25_rank,
)
from apps_rg.runtime.graph_traversal import TraversalPath, traverse

DEFAULT_RRF_K = 60


def _mtime_ns(db_path: str) -> int:
    if not db_path or db_path == ":memory:":
        return 0
    try:
        return Path(db_path).stat().st_mtime_ns
    except OSError:
        return 0


class VectorCache:
    """Generational in-memory cache of float32 dense vectors keyed by DB path and digest."""

    def __init__(self) -> None:
        self._key: tuple[str, int, str] | None = None
        self.record_ids: list[str] = []
        self.id_to_idx: dict[str, int] = {}
        self.vectors: list[tuple[float, ...]] = []

    def ensure_loaded(
        self, conn: sqlite3.Connection, *, db_path: str = ":memory:", digest: str = ""
    ) -> None:
        """Load or refresh dense vectors from unit_vectors when generation changes."""
        cache_key = (str(db_path), _mtime_ns(db_path), str(digest))
        if self._key == cache_key and self.record_ids:
            return
        rows = conn.execute(
            "SELECT unit_id, vector FROM unit_vectors ORDER BY unit_id"
        ).fetchall()
        r_ids: list[str] = []
        vecs: list[tuple[float, ...]] = []
        for uid, blob in rows:
            raw = bytes(blob)
            if len(raw) == BGE_DENSE_DIM * 4:
                vec = struct.unpack(f"<{BGE_DENSE_DIM}f", raw)
                r_ids.append(str(uid))
                vecs.append(tuple(float(v) for v in vec))
        self.record_ids = r_ids
        self.id_to_idx = {rid: idx for idx, rid in enumerate(r_ids)}
        self.vectors = vecs
        self._key = cache_key

    def score_query(
        self,
        query_vec: Sequence[float],
        *,
        allowed_ids: set[str] | None = None,
        top_k: int = 100,
    ) -> list[tuple[str, float]]:
        """Score dense cosine similarity via dot product on L2-normalized vectors."""
        if not self.record_ids or not query_vec:
            return []
        q = tuple(float(v) for v in query_vec)
        scored: list[tuple[float, str]] = []
        for idx, rid in enumerate(self.record_ids):
            if allowed_ids is not None and rid not in allowed_ids:
                continue
            vec = self.vectors[idx]
            if len(vec) == len(q):
                scored.append((round(math.fsum(a * b for a, b in zip(q, vec)), 6), rid))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(rid, sim) for sim, rid in scored[: max(1, int(top_k))]]


class SparseIndexCache:
    """Generational in-memory inverted index for BGE-M3 learned sparse lexical weights."""

    def __init__(self) -> None:
        self._key: tuple[str, int, str] | None = None
        self.record_ids: list[str] = []
        self.postings: dict[str, list[tuple[int, float]]] = {}

    def ensure_loaded(
        self, conn: sqlite3.Connection, *, db_path: str = ":memory:", digest: str = ""
    ) -> None:
        """Compile inverted posting lists from assertion_learned_sparse."""
        cache_key = (str(db_path), _mtime_ns(db_path), str(digest))
        if self._key == cache_key and self.record_ids:
            return
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'assertion_learned_sparse' LIMIT 1"
        ).fetchone()
        if not has_table:
            self.record_ids, self.postings, self._key = [], {}, cache_key
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
        self.record_ids, self.postings, self._key = r_ids, inv, cache_key

    def score_query(
        self,
        query_weights: Mapping[str, float],
        *,
        allowed_ids: set[str] | None = None,
        top_k: int = 100,
    ) -> list[tuple[str, float]]:
        """Accumulate inner-product scores across inverted posting lists."""
        if not self.record_ids:
            return []
        acc: dict[int, float] = {}
        for tok, qw_raw in query_weights.items():
            qw = float(qw_raw or 0.0)
            if qw > 0.0 and math.isfinite(qw):
                for doc_idx, dw in self.postings.get(str(tok), ()):
                    acc[doc_idx] = acc.get(doc_idx, 0.0) + qw * dw
        scored = [
            (round(acc.get(idx, 0.0), 6), rid)
            for idx, rid in enumerate(self.record_ids)
            if allowed_ids is None or rid in allowed_ids
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(rid, sc) for sc, rid in scored[: max(1, int(top_k))]]


class PrePaddedColbertCache:
    """Generational in-memory cache of decoded ColBERT multi-vector token matrices."""

    def __init__(self) -> None:
        self._key: tuple[str, int, str] | None = None
        self.tensors: dict[str, tuple[tuple[float, ...], ...]] = {}

    def ensure_loaded(
        self, conn: sqlite3.Connection, *, db_path: str = ":memory:", digest: str = ""
    ) -> None:
        """Decode int8 quantized ColBERT token vectors from assertion_colbert_vectors."""
        cache_key = (str(db_path), _mtime_ns(db_path), str(digest))
        if self._key == cache_key and self.tensors:
            return
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'assertion_colbert_vectors' LIMIT 1"
        ).fetchone()
        if not has_table:
            self.tensors, self._key = {}, cache_key
            return
        rows = conn.execute(
            "SELECT assertion_id, token_count, dim, scales_json, vectors_int8 "
            "FROM assertion_colbert_vectors ORDER BY assertion_id"
        ).fetchall()
        decoded: dict[str, tuple[tuple[float, ...], ...]] = {}
        for aid, t_count, c_dim, scales_json, blob in rows:
            try:
                decoded[str(aid)] = decode_colbert_int8(
                    bytes(blob),
                    json.loads(str(scales_json or "[]")),
                    token_count=int(t_count),
                    dim=int(c_dim),
                )
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        self.tensors, self._key = decoded, cache_key

    def score_admitted(
        self,
        query_tokens: Sequence[Sequence[float]],
        admitted_ids: Sequence[str],
        *,
        tile_size: int = 32,
    ) -> list[tuple[str, float]]:
        """Score ColBERT MaxSim over admitted Stage-1 candidate IDs in bounded tiles."""
        if not query_tokens or not admitted_ids:
            return []
        q_vecs = [tuple(float(v) for v in qv) for qv in query_tokens]
        q_len = len(q_vecs)
        scored: list[tuple[float, str]] = []
        step = max(1, int(tile_size))
        for start in range(0, len(admitted_ids), step):
            for rid in admitted_ids[start : start + step]:
                d_vecs = self.tensors.get(str(rid))
                if not d_vecs:
                    scored.append((0.0, str(rid)))
                    continue
                total = 0.0
                for qv in q_vecs:
                    best = max(
                        (math.fsum(a * b for a, b in zip(qv, dv)) for dv in d_vecs if len(dv) == len(qv)),
                        default=0.0,
                    )
                    total += max(0.0, best)
                scored.append((round(total / q_len, 6), str(rid)))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(rid, sc) for sc, rid in scored]


_GLOBAL_VECTOR_CACHE = VectorCache()
_GLOBAL_SPARSE_CACHE = SparseIndexCache()
_GLOBAL_COLBERT_CACHE = PrePaddedColbertCache()


def _compute_variance(values: Sequence[float]) -> float:
    finite = [float(v) for v in values if math.isfinite(float(v))]
    if len(finite) < 2:
        return 0.0
    mean = math.fsum(finite) / len(finite)
    return round(math.fsum((v - mean) ** 2 for v in finite) / len(finite), 8)


def _rank_bm25_corpus(
    conn: sqlite3.Connection, query_text: str, authority_ids: set[str]
) -> list[tuple[str, float]]:
    node_ids = {str(r[0]) for r in conn.execute("SELECT node_id FROM graph_nodes").fetchall()} & authority_ids
    bm25_map: dict[str, float] = {}
    if node_ids:
        for row in sqlite_fts5_bm25_rank(conn, query_text, node_ids=node_ids):
            bm25_map[str(row["assertion_id"])] = float(row["bm25_score"])
    unit_ids = authority_ids - node_ids
    if unit_ids:
        has_su = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'semantic_unit' LIMIT 1"
        ).fetchone()
        if has_su:
            docs = {
                str(uid): str(txt or "")
                for uid, txt in conn.execute("SELECT unit_id, text FROM semantic_unit").fetchall()
                if str(uid) in unit_ids
            }
            for row in bm25_rank(query_text, docs):
                bm25_map[str(row["assertion_id"])] = float(row["bm25_score"])
    ordered = sorted(bm25_map.items(), key=lambda item: (-item[1], item[0]))
    return [(rid, sc) for rid, sc in ordered]


class QuadGraphHybridRetriever:
    """DIE-aligned 2-stage 4-modality + 1-hop graph hybrid retriever."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        db_path: str = ":memory:",
        vector_cache: VectorCache | None = None,
        sparse_cache: SparseIndexCache | None = None,
        colbert_cache: PrePaddedColbertCache | None = None,
    ) -> None:
        self.conn = conn
        self.db_path = db_path
        self.vector_cache = vector_cache or _GLOBAL_VECTOR_CACHE
        self.sparse_cache = sparse_cache or _GLOBAL_SPARSE_CACHE
        self.colbert_cache = colbert_cache or _GLOBAL_COLBERT_CACHE

    def retrieve(
        self,
        query_text: str,
        *,
        allowed_ids: set[str] | None = None,
        top_k: int = 25,
        union_limit: int = 100,
        rrf_k: int = DEFAULT_RRF_K,
        weights: Mapping[str, float] | None = None,
        include_graph_signals: bool = True,
    ) -> dict[str, Any]:
        """Run Stage-1 (Dense + Sparse + BM25) union, Stage-2 ColBERT MaxSim, and 1-hop graph fusion."""
        meta_row = self.conn.execute(
            "SELECT graph_count_summary FROM graph_metadata ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        digest = str(meta_row[0]) if meta_row and meta_row[0] else ""
        self.vector_cache.ensure_loaded(self.conn, db_path=self.db_path, digest=digest)
        self.sparse_cache.ensure_loaded(self.conn, db_path=self.db_path, digest=digest)
        self.colbert_cache.ensure_loaded(self.conn, db_path=self.db_path, digest=digest)

        authority_ids = (
            set(allowed_ids)
            if allowed_ids is not None
            else set(self.vector_cache.record_ids) | set(self.sparse_cache.record_ids)
        )
        if not authority_ids:
            return {
                "results": [],
                "admitted_union_ids": [],
                "active_weights": {},
                "modality_score_variance": {"dense": 0.0, "sparse": 0.0, "bm25": 0.0, "colbert": 0.0},
                "per_modality_nonzero_variance": False,
                "dense_executed": False,
                "sparse_executed": False,
                "bm25_executed": False,
                "colbert_executed": False,
                "graph_traversal_executed": False,
            }

        q_head = project_text_multi_head(query_text)
        cap = max(union_limit, len(authority_ids))
        dense_pairs = self.vector_cache.score_query(q_head.dense_vector, allowed_ids=authority_ids, top_k=cap)
        sparse_pairs = self.sparse_cache.score_query(
            q_head.learned_sparse_weights, allowed_ids=authority_ids, top_k=cap
        )
        bm25_pairs = _rank_bm25_corpus(self.conn, query_text, authority_ids)

        preliminary_ranks: dict[str, dict[str, int]] = {
            "dense": {rid: rank for rank, (rid, _) in enumerate(dense_pairs, start=1)},
            "sparse": {rid: rank for rank, (rid, _) in enumerate(sparse_pairs, start=1)},
            "bm25": {rid: rank for rank, (rid, _) in enumerate(bm25_pairs, start=1)},
        }
        base_weights = dict(weights or CALIBRATED_HYBRID_RRF_WEIGHTS)
        admitted_union_ids = compute_candidate_union(
            preliminary_ranks,
            base_weights,
            rrf_k=rrf_k,
            union_limit=min(union_limit, len(authority_ids)),
        )
        colbert_pairs = self.colbert_cache.score_admitted(q_head.colbert_vectors, admitted_union_ids)
        colbert_ranks = {rid: rank for rank, (rid, _) in enumerate(colbert_pairs, start=1)}

        top_seed_ids = [rid for rid, _ in dense_pairs[:8]] or admitted_union_ids[:8]
        graph_ranks, graph_scores = (
            compute_graph_expand_signals(self.conn, top_seed_ids, admitted_union_ids)
            if (include_graph_signals and top_seed_ids)
            else ({}, {})
        )
        if graph_ranks and "graph" not in base_weights:
            base_weights["graph"] = DEFAULT_GRAPH_SIGNAL_WEIGHT

        all_channel_ranks: dict[str, dict[str, int]] = {
            **preliminary_ranks,
            "colbert": colbert_ranks,
            **({"graph": graph_ranks} if graph_ranks else {}),
        }
        active_weights = renormalize_active_rrf_weights(
            base_weights, {ch for ch, rmap in all_channel_ranks.items() if rmap}
        )
        dense_map, sparse_map, bm25_map, colbert_map = (
            dict(dense_pairs),
            dict(sparse_pairs),
            dict(bm25_pairs),
            dict(colbert_pairs),
        )
        fused_rows: list[dict[str, Any]] = []
        for rid in admitted_union_ids:
            rrf_val = math.fsum(
                float(w) / (rrf_k + all_channel_ranks[ch][rid])
                for ch, w in active_weights.items()
                if rid in all_channel_ranks.get(ch, {})
            )
            c_score = float(colbert_map.get(rid, 0.0))
            g_score = float(graph_scores.get(rid, 0.0))
            fused_rows.append(
                {
                    "record_id": rid,
                    "assertion_id": rid,
                    "rrf_score": round(rrf_val, 6),
                    "final_score": round(rrf_val + 0.15 * c_score + 0.05 * g_score, 6),
                    "dense_similarity": dense_map.get(rid, 0.0),
                    "learned_sparse_score": sparse_map.get(rid, 0.0),
                    "bm25_score": bm25_map.get(rid, 0.0),
                    "colbert_score": c_score,
                    "graph_score": g_score,
                    "dense_rank": preliminary_ranks["dense"].get(rid),
                    "learned_sparse_rank": preliminary_ranks["sparse"].get(rid),
                    "bm25_rank": preliminary_ranks["bm25"].get(rid),
                    "colbert_rank": colbert_ranks.get(rid),
                    "graph_rank": graph_ranks.get(rid),
                }
            )
        fused_rows.sort(key=lambda r: (-float(r["final_score"]), str(r["record_id"])))
        variance_map = {
            "dense": _compute_variance([r["dense_similarity"] for r in fused_rows]),
            "sparse": _compute_variance([r["learned_sparse_score"] for r in fused_rows]),
            "bm25": _compute_variance([r["bm25_score"] for r in fused_rows]),
            "colbert": _compute_variance([r["colbert_score"] for r in fused_rows]),
        }
        return {
            "results": fused_rows[: max(1, int(top_k))],
            "admitted_union_ids": admitted_union_ids,
            "active_weights": active_weights,
            "modality_score_variance": variance_map,
            "per_modality_nonzero_variance": all(
                variance_map[k] > 0.0 for k in ("dense", "sparse", "colbert")
            ),
            "dense_executed": bool(dense_pairs),
            "sparse_executed": bool(sparse_pairs),
            "bm25_executed": bool(bm25_pairs),
            "colbert_executed": bool(colbert_pairs),
            "graph_traversal_executed": bool(graph_ranks),
        }


def expand_connected_quad_graph(
    conn: sqlite3.Connection,
    query_text: str,
    *,
    db_path: str = ":memory:",
    top_k_seeds: int = 8,
    max_depth: int = 2,
) -> dict[str, Any]:
    """Execute DIE-aligned C0.1 -> C0.2 (4-channel + 1-hop) -> C0.3 multi-seed convergent graph expansion."""
    c02_bundle = QuadGraphHybridRetriever(conn, db_path=db_path).retrieve(query_text, top_k=top_k_seeds)
    unit_roots = {
        str(r[0]): str(r[1])
        for r in conn.execute("SELECT unit_id, root_node_id FROM semantic_unit").fetchall()
    }
    seed_node_scores: dict[str, float] = {}
    for srow in c02_bundle["results"]:
        rid = str(srow["record_id"])
        root_nid = unit_roots.get(rid, rid)
        seed_node_scores[root_nid] = max(seed_node_scores.get(root_nid, 0.0), float(srow["final_score"]))

    allowed_steps = (
        "skill_supported_by_fact",
        "fact_has_metric_outcome",
        "metric_outcome_bound_to_employer",
        "engagement_exercises_skill",
        "engagement_evidenced_by_fact",
    )
    paths: list[TraversalPath] = []
    if seed_node_scores:
        try:
            paths = traverse(conn, seeds=sorted(seed_node_scores), allowed_steps=allowed_steps, max_depth=max_depth)
        except (sqlite3.Error, ValueError, LookupError, RuntimeError):
            paths = []

    endpoint_seeds: dict[str, set[str]] = {}
    for p in paths:
        if p.node_path:
            endpoint_seeds.setdefault(p.end_node_id, set()).add(p.start_node_id)

    convergent_paths: list[dict[str, Any]] = []
    for p in paths:
        start_nid = p.start_node_id
        end_nid = p.end_node_id
        distinct_seeds = len(endpoint_seeds.get(end_nid, set()))
        convergence_bonus = min(0.15, 0.05 * max(0, distinct_seeds - 1))
        convergent_paths.append(
            {
                "nodes": list(p.node_path),
                "edges": list(p.edge_path),
                "score": round(float(p.path_confidence) + seed_node_scores.get(start_nid, 0.0) + convergence_bonus, 6),
                "convergence_bonus": round(convergence_bonus, 6),
                "distinct_seed_roots": distinct_seeds,
            }
        )
    convergent_paths.sort(key=lambda item: (-float(item["score"]), tuple(item["nodes"])))
    return {
        **c02_bundle,
        "seed_node_scores": seed_node_scores,
        "expanded_paths": convergent_paths,
        "expanded_path_count": len(convergent_paths),
        "graph_traversal_executed": bool(convergent_paths) or bool(c02_bundle["graph_traversal_executed"]),
    }


__all__ = [
    "DEFAULT_RRF_K",
    "PrePaddedColbertCache",
    "QuadGraphHybridRetriever",
    "SparseIndexCache",
    "VectorCache",
    "expand_connected_quad_graph",
]
