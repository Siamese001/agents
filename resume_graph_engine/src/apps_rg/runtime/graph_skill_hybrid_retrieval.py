"""Deterministic BM25 and RRF fusion for authority-bound C0.3 candidates."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class GraphSkillHybridRetrievalError(ValueError):
    """Raised when ranked candidate inputs cannot be fused safely."""


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def bm25_rank(
    query_text: str,
    documents: Mapping[str, str],
    *,
    k1: float = 1.2,
    b: float = 0.75,
) -> list[dict[str, float | str]]:
    """Rank immutable text documents with deterministic Okapi BM25.

    Zero-score documents remain in the result so callers can fuse complete,
    stable candidate sets.  Ties are resolved by assertion ID.
    """
    if k1 <= 0:
        raise GraphSkillHybridRetrievalError("BM25 k1 must be positive")
    if not 0 <= b <= 1:
        raise GraphSkillHybridRetrievalError("BM25 b must be within [0, 1]")
    assertion_ids = sorted(str(assertion_id) for assertion_id in documents)
    if not assertion_ids:
        return []
    query_terms = Counter(_tokens(query_text))
    term_frequencies = {
        assertion_id: Counter(_tokens(str(documents[assertion_id])))
        for assertion_id in assertion_ids
    }
    document_frequency: Counter[str] = Counter()
    for frequencies in term_frequencies.values():
        document_frequency.update(frequencies.keys())
    average_length = math.fsum(sum(frequencies.values()) for frequencies in term_frequencies.values()) / len(assertion_ids)
    scores: list[tuple[float, str]] = []
    for assertion_id in assertion_ids:
        frequencies = term_frequencies[assertion_id]
        document_length = sum(frequencies.values())
        length_normalizer = k1 * (1.0 - b + b * document_length / average_length) if average_length else k1
        score = math.fsum(
            frequency * math.log(1.0 + (len(assertion_ids) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            * (frequencies.get(term, 0) * (k1 + 1.0))
            / (frequencies.get(term, 0) + length_normalizer)
            for term, frequency in query_terms.items()
            if frequencies.get(term, 0)
        )
        scores.append((score, assertion_id))
    scores.sort(key=lambda row: (-row[0], row[1]))
    return [
        {"assertion_id": assertion_id, "bm25_score": score}
        for score, assertion_id in scores
    ]


def sqlite_fts5_bm25_rank(
    conn: Any,
    query_text: str,
    *,
    node_ids: set[str] | None = None,
    node_type: str | None = None,
) -> list[dict[str, float | str]]:
    """Rank SQLite graph_nodes using the native FTS5 BM25 virtual index.

    Preserves zero-score candidates in the authority set so results can be
    passed directly into ``fuse_dense_bm25``. Falls back to ``bm25_rank`` if
    ``graph_nodes_fts`` is unavailable on a custom connection.
    """
    where_clauses: list[str] = []
    params: list[Any] = []
    if node_type is not None:
        where_clauses.append("node_type = ?")
        params.append(str(node_type))
    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    rows = conn.execute(
        f"SELECT node_id, label, description FROM graph_nodes{where_sql}",
        tuple(params),
    ).fetchall()

    candidate_docs: dict[str, str] = {}
    for row in rows:
        nid = str(row[0])
        if node_ids is not None and nid not in node_ids:
            continue
        candidate_docs[nid] = f"{row[1] or ''} {row[2] or ''}".strip()

    if node_ids is not None:
        missing_ids = set(node_ids) - set(candidate_docs)
        if missing_ids:
            raise GraphSkillHybridRetrievalError(
                f"node_ids contains unknown or filtered graph_nodes IDs: {sorted(missing_ids)}"
            )

    if not candidate_docs:
        return []

    has_fts = bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'graph_nodes_fts' LIMIT 1"
        ).fetchone()
    )
    if not has_fts:
        return bm25_rank(query_text, candidate_docs)

    tokens = list(dict.fromkeys(_tokens(query_text)))
    fts_scores: dict[str, float] = dict.fromkeys(candidate_docs, 0.0)
    if tokens:
        match_expr = " OR ".join(f'"{token}"' for token in tokens)
        fts_rows = conn.execute(
            """
            SELECT node_id, -bm25(graph_nodes_fts, 0.0, 0.0, 1.5, 1.0) AS score
            FROM graph_nodes_fts
            WHERE graph_nodes_fts MATCH ?
            """,
            (match_expr,),
        ).fetchall()
        for nid_raw, raw_score in fts_rows:
            nid = str(nid_raw)
            if nid in fts_scores:
                val = float(raw_score or 0.0)
                fts_scores[nid] = val if val > 0.0 and math.isfinite(val) else 0.0

    ordered = sorted(candidate_docs, key=lambda aid: (-fts_scores[aid], aid))
    return [
        {"assertion_id": assertion_id, "bm25_score": fts_scores[assertion_id]}
        for assertion_id in ordered
    ]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    assertion_ids: set[str],
    rank_constant: int = 60,
    authority_boosts: Mapping[str, float] | None = None,
) -> list[dict[str, float | int | str | None]]:
    """Fuse ranked assertion IDs with optional calibrated authority boosts."""
    if rank_constant <= 0:
        raise GraphSkillHybridRetrievalError("RRF rank constant must be positive")
    if authority_boosts:
        for _aid, boost in authority_boosts.items():
            if not math.isfinite(float(boost)) or float(boost) < 0:
                raise GraphSkillHybridRetrievalError(
                    "authority boosts must be non-negative and finite"
                )
    scores = dict.fromkeys(assertion_ids, 0.0)
    ranks: dict[str, list[int | None]] = {
        assertion_id: [None] * len(rankings) for assertion_id in assertion_ids
    }
    for source_index, ranking in enumerate(rankings):
        seen: set[str] = set()
        for rank, assertion_id in enumerate(ranking, start=1):
            if assertion_id in assertion_ids and assertion_id not in seen:
                scores[assertion_id] += 1.0 / (rank_constant + rank)
                ranks[assertion_id][source_index] = rank
                seen.add(assertion_id)
    if authority_boosts:
        for assertion_id, boost in authority_boosts.items():
            if assertion_id in scores and boost > 0:
                scores[assertion_id] += float(boost)
    ordered = sorted(assertion_ids, key=lambda assertion_id: (-scores[assertion_id], assertion_id))
    return [
        {
            "assertion_id": assertion_id,
            "rrf_score": scores[assertion_id],
            "ranks": ranks[assertion_id],
        }
        for assertion_id in ordered
    ]


def fuse_dense_bm25(
    dense_candidates: Sequence[Mapping[str, Any]],
    bm25_candidates: Sequence[Mapping[str, Any]],
    *,
    assertion_ids: set[str],
    rank_constant: int = 60,
    authority_boosts: Mapping[str, float] | None = None,
    metric_bearing_assertion_ids: set[str] | None = None,
    metric_boost: float = 0.05,
) -> list[dict[str, float | int | str | None]]:
    """Fuse dense and BM25 rankings with component scores retained for audit."""
    dense_scores: dict[str, float] = {}
    for candidate in dense_candidates:
        if set(candidate) != {"assertion_id", "similarity"}:
            raise GraphSkillHybridRetrievalError("dense candidate shape is invalid")
        assertion_id = str(candidate["assertion_id"])
        similarity = float(candidate["similarity"])
        if assertion_id not in assertion_ids:
            raise GraphSkillHybridRetrievalError("dense candidate is outside the authority set")
        if assertion_id in dense_scores or not math.isfinite(similarity):
            raise GraphSkillHybridRetrievalError("dense candidates must be unique and finite")
        dense_scores[assertion_id] = similarity
    bm25_scores: dict[str, float] = {}
    for candidate in bm25_candidates:
        if set(candidate) != {"assertion_id", "bm25_score"}:
            raise GraphSkillHybridRetrievalError("BM25 candidate shape is invalid")
        assertion_id = str(candidate["assertion_id"])
        score = float(candidate["bm25_score"])
        if assertion_id not in assertion_ids:
            raise GraphSkillHybridRetrievalError("BM25 candidate is outside the authority set")
        if assertion_id in bm25_scores or not math.isfinite(score):
            raise GraphSkillHybridRetrievalError("BM25 candidates must be unique and finite")
        bm25_scores[assertion_id] = score
    fused = reciprocal_rank_fusion(
        [list(dense_scores), list(bm25_scores)],
        assertion_ids=assertion_ids,
        rank_constant=rank_constant,
        authority_boosts=authority_boosts,
    )
    result = [
        row
        | {
            "dense_similarity": dense_scores.get(str(row["assertion_id"])),
            "bm25_score": bm25_scores.get(str(row["assertion_id"])),
            "dense_rank": row["ranks"][0],
            "bm25_rank": row["ranks"][1],
        }
        for row in fused
    ]
    if metric_bearing_assertion_ids is not None:
        if not math.isfinite(float(metric_boost)) or float(metric_boost) < 0.0 or float(metric_boost) > 0.20:
            raise GraphSkillHybridRetrievalError(
                "metric_boost must be non-negative, finite, and <= 0.20"
            )
        invalid_metric_aids = set(metric_bearing_assertion_ids) - assertion_ids
        if invalid_metric_aids:
            raise GraphSkillHybridRetrievalError(
                f"metric_bearing_assertion_ids contains unauthorized IDs: {sorted(invalid_metric_aids)}"
            )
        boosted = []
        for r in result:
            aid = str(r["assertion_id"])
            boost = metric_boost if aid in metric_bearing_assertion_ids else 0.0
            boosted.append(
                r
                | {
                    "metric_authority_boost": boost,
                    "final_score": round(float(r["rrf_score"]) + boost, 6),
                }
            )
        boosted.sort(key=lambda r: (-float(r["final_score"]), str(r["assertion_id"])))
        return boosted
    return result


def learned_sparse_rank(
    query_weights: Mapping[str, float],
    document_weights: Mapping[str, Mapping[str, float]],
) -> list[dict[str, float | str]]:
    """Rank immutable candidate documents using BGE-M3 learned sparse lexical weights."""
    assertion_ids = sorted(str(assertion_id) for assertion_id in document_weights)
    if not assertion_ids:
        return []
    for tok, qw in query_weights.items():
        if not str(tok).strip() or not math.isfinite(float(qw)) or float(qw) < 0.0:
            raise GraphSkillHybridRetrievalError("query learned sparse weights must be finite and non-negative")
    scores: list[tuple[float, str]] = []
    for aid in assertion_ids:
        doc_w = document_weights[aid]
        overlap = 0.0
        for tok, qw in query_weights.items():
            if tok in doc_w:
                dw = float(doc_w[tok])
                if not math.isfinite(dw) or dw < 0.0:
                    raise GraphSkillHybridRetrievalError("document learned sparse weights must be finite and non-negative")
                overlap += float(qw) * dw
        scores.append((round(overlap, 6), aid))
    scores.sort(key=lambda row: (-row[0], row[1]))
    return [
        {"assertion_id": assertion_id, "learned_sparse_score": score}
        for score, assertion_id in scores
    ]


def colbert_maxsim_score(
    query_vectors: Sequence[Sequence[float]],
    doc_vectors: Sequence[Sequence[float]],
) -> float:
    """Compute ColBERT MaxSim late-interaction score between query and document token vectors."""
    if not query_vectors or not doc_vectors:
        return 0.0
    total = 0.0
    for q_vec in query_vectors:
        q_floats = [float(v) for v in q_vec]
        best_token_sim = -1.0
        for d_vec in doc_vectors:
            if len(d_vec) != len(q_floats):
                raise GraphSkillHybridRetrievalError("ColBERT token vector dimension mismatch")
            dot = math.fsum(a * float(b) for a, b in zip(q_floats, d_vec))
            if not math.isfinite(dot):
                raise GraphSkillHybridRetrievalError("ColBERT token similarity must be finite")
            if dot > best_token_sim:
                best_token_sim = dot
        total += max(0.0, best_token_sim)
    return round(total / len(query_vectors), 6)


def colbert_maxsim_rank(
    query_vectors: Sequence[Sequence[float]],
    document_vectors: Mapping[str, Sequence[Sequence[float]]],
) -> list[dict[str, float | str]]:
    """Rank candidate documents using ColBERT multi-vector MaxSim late interaction."""
    assertion_ids = sorted(str(assertion_id) for assertion_id in document_vectors)
    if not assertion_ids:
        return []
    scores: list[tuple[float, str]] = []
    for aid in assertion_ids:
        sim = colbert_maxsim_score(query_vectors, document_vectors[aid])
        scores.append((sim, aid))
    scores.sort(key=lambda row: (-row[0], row[1]))
    return [
        {"assertion_id": assertion_id, "colbert_score": score}
        for score, assertion_id in scores
    ]


def fuse_quad_hybrid(
    dense_candidates: Sequence[Mapping[str, Any]],
    learned_sparse_candidates: Sequence[Mapping[str, Any]],
    bm25_candidates: Sequence[Mapping[str, Any]],
    colbert_candidates: Sequence[Mapping[str, Any]],
    *,
    assertion_ids: set[str],
    rank_constant: int = 60,
    colbert_stage2_weight: float = 0.15,
    authority_boosts: Mapping[str, float] | None = None,
    metric_bearing_assertion_ids: set[str] | None = None,
    metric_boost: float = 0.05,
) -> list[dict[str, float | int | str | None]]:
    """Fuse all 4 retrieval signals (Dense + Learned Sparse + BM25 + Stage-2 ColBERT MaxSim)."""
    if not math.isfinite(float(colbert_stage2_weight)) or float(colbert_stage2_weight) < 0.0 or float(colbert_stage2_weight) > 0.50:
        raise GraphSkillHybridRetrievalError("colbert_stage2_weight must be within [0.0, 0.50]")

    def _extract_lane(
        candidates: Sequence[Mapping[str, Any]], score_key: str, label: str
    ) -> dict[str, float]:
        lane_scores: dict[str, float] = {}
        for candidate in candidates:
            if set(candidate) != {"assertion_id", score_key}:
                raise GraphSkillHybridRetrievalError(f"{label} candidate shape is invalid")
            aid = str(candidate["assertion_id"])
            val = float(candidate[score_key])
            if aid not in assertion_ids:
                raise GraphSkillHybridRetrievalError(f"{label} candidate is outside the authority set")
            if aid in lane_scores or not math.isfinite(val):
                raise GraphSkillHybridRetrievalError(f"{label} candidates must be unique and finite")
            lane_scores[aid] = val
        return lane_scores

    dense_scores = _extract_lane(dense_candidates, "similarity", "dense")
    learned_sparse_scores = _extract_lane(learned_sparse_candidates, "learned_sparse_score", "learned_sparse")
    bm25_scores = _extract_lane(bm25_candidates, "bm25_score", "BM25")
    colbert_scores = _extract_lane(colbert_candidates, "colbert_score", "ColBERT")

    dense_ordered = [aid for aid, _ in sorted(dense_scores.items(), key=lambda x: (-x[1], x[0]))]
    sparse_ordered = [aid for aid, _ in sorted(learned_sparse_scores.items(), key=lambda x: (-x[1], x[0]))]
    bm25_ordered = [aid for aid, _ in sorted(bm25_scores.items(), key=lambda x: (-x[1], x[0]))]
    colbert_ordered = [aid for aid, _ in sorted(colbert_scores.items(), key=lambda x: (-x[1], x[0]))]

    fused = reciprocal_rank_fusion(
        [dense_ordered, sparse_ordered, bm25_ordered, colbert_ordered],
        assertion_ids=assertion_ids,
        rank_constant=rank_constant,
        authority_boosts=authority_boosts,
    )

    if metric_bearing_assertion_ids is not None:
        if not math.isfinite(float(metric_boost)) or float(metric_boost) < 0.0 or float(metric_boost) > 0.20:
            raise GraphSkillHybridRetrievalError(
                "metric_boost must be non-negative, finite, and <= 0.20"
            )
        invalid_metric_aids = set(metric_bearing_assertion_ids) - assertion_ids
        if invalid_metric_aids:
            raise GraphSkillHybridRetrievalError(
                f"metric_bearing_assertion_ids contains unauthorized IDs: {sorted(invalid_metric_aids)}"
            )

    out: list[dict[str, float | int | str | None]] = []
    for row in fused:
        aid = str(row["assertion_id"])
        colbert_val = float(colbert_scores.get(aid, 0.0))
        stage2_colbert_boost = round(colbert_val * float(colbert_stage2_weight), 6)
        m_boost = (
            float(metric_boost)
            if (metric_bearing_assertion_ids is not None and aid in metric_bearing_assertion_ids)
            else 0.0
        )
        final_val = round(float(row["rrf_score"]) + stage2_colbert_boost + m_boost, 6)
        out.append(
            row
            | {
                "dense_similarity": dense_scores.get(aid),
                "learned_sparse_score": learned_sparse_scores.get(aid),
                "bm25_score": bm25_scores.get(aid),
                "colbert_score": colbert_scores.get(aid),
                "dense_rank": row["ranks"][0],
                "learned_sparse_rank": row["ranks"][1],
                "bm25_rank": row["ranks"][2],
                "colbert_rank": row["ranks"][3],
                "colbert_stage2_boost": stage2_colbert_boost,
                "metric_authority_boost": m_boost,
                "final_score": final_val,
            }
        )
    out.sort(key=lambda r: (-float(r["final_score"]), str(r["assertion_id"])))
    return out


__all__ = [
    "GraphSkillHybridRetrievalError",
    "bm25_rank",
    "colbert_maxsim_rank",
    "colbert_maxsim_score",
    "fuse_dense_bm25",
    "fuse_quad_hybrid",
    "learned_sparse_rank",
    "reciprocal_rank_fusion",
    "sqlite_fts5_bm25_rank",
]
