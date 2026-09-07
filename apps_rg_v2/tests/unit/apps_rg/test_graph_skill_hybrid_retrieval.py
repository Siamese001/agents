from __future__ import annotations

import pytest

from apps_rg.runtime.graph_skill_hybrid_retrieval import (
    GraphSkillHybridRetrievalError,
    bm25_rank,
    fuse_dense_bm25,
)


def test_bm25_ranks_lexical_match_and_breaks_zero_score_ties_by_id() -> None:
    ranking = bm25_rank(
        "azure platform architecture",
        {
            "skill_c": "sales leadership",
            "skill_a": "Azure platform architecture",
            "skill_b": "azure operations",
        },
    )

    assert [row["assertion_id"] for row in ranking] == ["skill_a", "skill_b", "skill_c"]
    assert ranking[0]["bm25_score"] > ranking[1]["bm25_score"] > 0
    assert ranking[2]["bm25_score"] == 0


def test_dense_bm25_rrf_retains_component_scores_and_ranks() -> None:
    fused = fuse_dense_bm25(
        [
            {"assertion_id": "skill_b", "similarity": 0.99},
            {"assertion_id": "skill_a", "similarity": 0.75},
        ],
        [
            {"assertion_id": "skill_a", "bm25_score": 4.5},
            {"assertion_id": "skill_b", "bm25_score": 0.5},
        ],
        assertion_ids={"skill_a", "skill_b", "skill_c"},
    )

    assert [row["assertion_id"] for row in fused] == ["skill_a", "skill_b", "skill_c"]
    assert fused[0] == {
        "assertion_id": "skill_a",
        "rrf_score": pytest.approx(1 / 62 + 1 / 61),
        "ranks": [2, 1],
        "dense_similarity": 0.75,
        "bm25_score": 4.5,
        "dense_rank": 2,
        "bm25_rank": 1,
    }
    assert fused[2]["rrf_score"] == 0
    assert fused[2]["dense_similarity"] is None
    assert fused[2]["bm25_score"] is None


def test_fusion_rejects_non_authority_dense_candidate_shape() -> None:
    with pytest.raises(GraphSkillHybridRetrievalError, match="shape"):
        fuse_dense_bm25(
            [{"assertion_id": "skill_a", "similarity": 1.0, "label": "forbidden"}],
            [{"assertion_id": "skill_a", "bm25_score": 1.0}],
            assertion_ids={"skill_a"},
        )


def test_fusion_rejects_candidate_outside_authority_set() -> None:
    with pytest.raises(GraphSkillHybridRetrievalError, match="authority"):
        fuse_dense_bm25(
            [{"assertion_id": "orphan", "similarity": 1.0}],
            [{"assertion_id": "skill_a", "bm25_score": 1.0}],
            assertion_ids={"skill_a"},
        )
