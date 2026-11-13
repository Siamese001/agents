"""Wave 3 unit tests for 4-signal hybrid retrieval (Dense + Learned Sparse + BM25 + ColBERT)."""

from __future__ import annotations

import os
import pytest

from apps_research.engines.research_retrieval_engine import create_retrieval_engine
from apps_rg.runtime.graph_skill_hybrid_retrieval import (
    GraphSkillHybridRetrievalError,
    bm25_rank,
    colbert_maxsim_rank,
    colbert_maxsim_score,
    fuse_quad_hybrid,
    learned_sparse_rank,
)


def test_learned_sparse_and_colbert_maxsim_ranking() -> None:
    query_weights = {"colbert": 1.8, "maxsim": 1.5, "retrieval": 1.1}
    doc_weights = {
        "skill_a": {"colbert": 1.7, "maxsim": 1.6, "retrieval": 1.2},
        "skill_b": {"retrieval": 0.9, "cloud": 1.4},
    }
    sparse_ranked = learned_sparse_rank(query_weights, doc_weights)
    assert sparse_ranked[0]["assertion_id"] == "skill_a"
    assert float(sparse_ranked[0]["learned_sparse_score"]) > float(
        sparse_ranked[1]["learned_sparse_score"]
    )

    q_vecs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    doc_vecs = {
        "skill_a": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        "skill_b": [[0.5, 0.5, 0.0], [0.0, 0.0, 1.0]],
    }
    colbert_ranked = colbert_maxsim_rank(q_vecs, doc_vecs)
    assert colbert_ranked[0]["assertion_id"] == "skill_a"
    assert colbert_maxsim_score(q_vecs, doc_vecs["skill_a"]) == 1.0


def test_fuse_quad_hybrid_combines_all_four_signals_and_metric_boost() -> None:
    aids = {"skill_alpha", "skill_beta", "skill_gamma"}
    dense = [
        {"assertion_id": "skill_alpha", "similarity": 0.90},
        {"assertion_id": "skill_beta", "similarity": 0.89},
        {"assertion_id": "skill_gamma", "similarity": 0.70},
    ]
    learned_sparse = [
        {"assertion_id": "skill_beta", "learned_sparse_score": 4.2},
        {"assertion_id": "skill_alpha", "learned_sparse_score": 3.8},
        {"assertion_id": "skill_gamma", "learned_sparse_score": 1.1},
    ]
    bm25 = bm25_rank(
        "ColBERT MaxSim late interaction hybrid retrieval",
        {
            "skill_alpha": "Hybrid retrieval with dense embeddings",
            "skill_beta": "ColBERT MaxSim late interaction hybrid retrieval",
            "skill_gamma": "Data warehouse governance",
        },
    )
    colbert = [
        {"assertion_id": "skill_beta", "colbert_score": 0.96},
        {"assertion_id": "skill_alpha", "colbert_score": 0.72},
        {"assertion_id": "skill_gamma", "colbert_score": 0.41},
    ]
    fused = fuse_quad_hybrid(
        dense,
        learned_sparse,
        bm25,
        colbert,
        assertion_ids=aids,
        metric_bearing_assertion_ids={"skill_beta"},
        metric_boost=0.05,
    )
    assert fused[0]["assertion_id"] == "skill_beta"
    assert fused[0]["dense_rank"] == 2
    assert fused[0]["learned_sparse_rank"] == 1
    assert fused[0]["bm25_rank"] == 1
    assert fused[0]["colbert_rank"] == 1
    assert float(fused[0]["colbert_stage2_boost"]) > 0.0
    assert float(fused[0]["metric_authority_boost"]) == 0.05


def test_fuse_quad_hybrid_rejects_unauthorized_candidate() -> None:
    with pytest.raises(GraphSkillHybridRetrievalError, match="outside the authority set"):
        fuse_quad_hybrid(
            [{"assertion_id": "skill_rogue", "similarity": 0.9}],
            [{"assertion_id": "skill_alpha", "learned_sparse_score": 1.0}],
            [{"assertion_id": "skill_alpha", "bm25_score": 1.0}],
            [{"assertion_id": "skill_alpha", "colbert_score": 0.9}],
            assertion_ids={"skill_alpha"},
        )


def test_in_memory_research_store_quad_hybrid_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    engine = create_retrieval_engine(chromadb_path=None)
    id_target = engine.index_research(
        content="Quad-engine hybrid retrieval combining BGE-M3 dense, learned sparse, BM25, and ColBERT late interaction.",
        topic="Quad Retrieval Architecture",
        artifact_mode="brief",
        quality_score=0.95,
        source_count=3,
        claim_types={"architecture": 4},
        sources=["adr_056"],
    )
    _id_other = engine.index_research(
        content="Legacy batch ETL job scheduling for mainframe tape archives.",
        topic="Legacy ETL",
        artifact_mode="brief",
        quality_score=0.70,
        source_count=1,
        claim_types={"ops": 1},
        sources=["legacy_doc"],
    )
    quad_hits = engine.store.query_quad_hybrid(
        "ColBERT late interaction and BGE-M3 learned sparse retrieval",
        n_results=2,
    )
    assert len(quad_hits) == 2
    assert quad_hits[0]["assertion_id"] == id_target
    assert float(quad_hits[0]["colbert_score"]) > 0.0
    assert float(quad_hits[0]["learned_sparse_score"]) > 0.0


def test_die_aligned_candidate_union_and_quad_graph_retriever() -> None:
    import sqlite3
    from pathlib import Path
    from apps_rg.runtime.graph_skill_hybrid_retrieval import (
        CALIBRATED_HYBRID_RRF_WEIGHTS,
        compute_candidate_union,
        renormalize_active_rrf_weights,
    )
    from apps_rg.runtime.quad_graph_retriever import expand_connected_quad_graph
    from apps_rg.runtime.semantic_unit_retrieval import retrieve_semantic_units_quad_hybrid

    prelim = {
        "dense": {"u1": 1, "u2": 2},
        "sparse": {"u2": 1, "u3": 2},
        "bm25": {"u3": 1, "u4": 2},
    }
    union_ids = compute_candidate_union(
        prelim, CALIBRATED_HYBRID_RRF_WEIGHTS, union_limit=4, min_per_modality=1
    )
    assert set(union_ids) == {"u1", "u2", "u3", "u4"}
    weights = renormalize_active_rrf_weights(CALIBRATED_HYBRID_RRF_WEIGHTS, {"dense", "sparse"})
    assert abs(sum(weights.values()) - 1.0) < 1e-4

    repo_root = Path(__file__).resolve().parents[4]
    db_path = (
        repo_root
        / "resume_graph_engine"
        / "artifacts"
        / "apps_rg"
        / "fact_inventory"
        / "augmented_skills_graph.sqlite"
    )
    if db_path.is_file():
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            su_res = retrieve_semantic_units_quad_hybrid(
                conn,
                "governed agentic platform architecture hybrid retrieval",
                db_path=str(db_path),
                limit=8,
            )
            assert su_res["unit_count"] > 0
            assert su_res["dense_executed"] is True
            assert su_res["sparse_executed"] is True
            assert su_res["bm25_executed"] is True
            assert su_res["colbert_executed"] is True

            expanded = expand_connected_quad_graph(
                conn,
                "governed agentic platform architecture hybrid retrieval",
                db_path=str(db_path),
                top_k_seeds=6,
                max_depth=2,
            )
            assert expanded["graph_traversal_executed"] is True
            assert expanded["expanded_path_count"] > 0
        finally:
            conn.close()
