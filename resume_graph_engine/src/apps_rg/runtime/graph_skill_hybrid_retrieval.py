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


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    assertion_ids: set[str],
    rank_constant: int = 60,
) -> list[dict[str, float | int | str | None]]:
    """Fuse ranked assertion IDs without exposing anything beyond IDs/scores."""
    if rank_constant <= 0:
        raise GraphSkillHybridRetrievalError("RRF rank constant must be positive")
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
    )
    return [
        row
        | {
            "dense_similarity": dense_scores.get(str(row["assertion_id"])),
            "bm25_score": bm25_scores.get(str(row["assertion_id"])),
            "dense_rank": row["ranks"][0],
            "bm25_rank": row["ranks"][1],
        }
        for row in fused
    ]


__all__ = [
    "GraphSkillHybridRetrievalError",
    "bm25_rank",
    "fuse_dense_bm25",
    "reciprocal_rank_fusion",
]
