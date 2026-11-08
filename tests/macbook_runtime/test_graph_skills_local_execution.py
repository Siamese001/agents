"""Pillar 3: Graph Multi-Hop Traversal, BM25, Dense Hybrid RRF Fusion, and BGE-M3 Embeddings."""
from __future__ import annotations

import math
from pathlib import Path
import pytest
import sqlite3
import tempfile
import torch

from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.runtime.graph_skill_hybrid_retrieval import (
    fuse_dense_bm25,
    reciprocal_rank_fusion,
    sqlite_fts5_bm25_rank,
)
from sentence_transformers import SentenceTransformer
from tools.run_resume_graph_traversal_probe import run_resume_graph_traversal_probe

pytestmark = [pytest.mark.integration]


def test_sqlite_graph_multi_hop_traversal() -> None:
    """Executes live multi-hop graph traversal walk in sandbox clone."""
    receipt = run_resume_graph_traversal_probe(max_paths=50)
    assert receipt["status"] == "PASS"
    assert receipt["direct_graph_traversal"] is True
    assert receipt["integrity_check"] == "ok"
    assert receipt["two_hop_path_count"] > 0
    assert receipt["domain_skill_evidence_path_count"] > 0


def test_sqlite_fts5_bm25_ranking_on_graph_nodes() -> None:
    """Verifies native SQLite FTS5 BM25 virtual ranking on live skill nodes."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_graph.sqlite"
        materialize_augmented_skills_graph_sqlite(db_path=db_path)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            ranked = sqlite_fts5_bm25_rank(
                conn,
                "governed agentic platform architecture",
                node_type="skill",
            )
            assert len(ranked) > 0
            assert float(ranked[0]["bm25_score"]) > 0.0
            # Scores must be sorted descending
            scores = [float(r["bm25_score"]) for r in ranked]
            assert scores == sorted(scores, reverse=True)
        finally:
            conn.close()


def test_dense_hybrid_rrf_fusion_deterministic_properties() -> None:
    """Verifies deterministic properties of reciprocal rank fusion."""
    assertion_ids = {"aid_1", "aid_2", "aid_3", "aid_4"}
    dense_candidates = [
        {"assertion_id": "aid_1", "similarity": 0.95},
        {"assertion_id": "aid_2", "similarity": 0.85},
        {"assertion_id": "aid_3", "similarity": 0.70},
    ]
    bm25_candidates = [
        {"assertion_id": "aid_2", "bm25_score": 5.2},
        {"assertion_id": "aid_1", "bm25_score": 4.1},
        {"assertion_id": "aid_4", "bm25_score": 3.0},
    ]

    fused = fuse_dense_bm25(dense_candidates, bm25_candidates, assertion_ids=assertion_ids)
    assert len(fused) == len(assertion_ids)
    scores = [float(item["rrf_score"]) for item in fused]
    assert scores == sorted(scores, reverse=True), "Fused candidates must be monotonically non-increasing"


def test_bge_m3_embedding_generation_on_mps() -> None:
    """Verifies that local BGE-M3 model loads on MPS and emits 1024-d unit normalized vectors."""
    model_path = Path("artifacts/models/BAAI/bge-m3")
    if not model_path.exists():
        pytest.skip(f"Local BGE-M3 model weights not found at {model_path}")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(str(model_path), device=device)

    phrases = [
        "Distributed Systems Architecture",
        "Kubernetes Orchestration",
        "Agentic Workflow Orchestrator",
    ]
    vectors = model.encode(phrases, normalize_embeddings=True)
    assert vectors.shape == (3, 1024), f"Expected shape (3, 1024), got {vectors.shape}"

    for i in range(3):
        norm = math.sqrt(sum(float(x) ** 2 for x in vectors[i]))
        assert abs(norm - 1.0) < 1e-4, f"Vector {i} not L2 normalized: norm={norm}"
        assert not any(math.isnan(x) or math.isinf(x) for x in vectors[i]), f"Vector {i} contains NaN/Inf"


def test_bge_m3_semantic_cosine_discrimination() -> None:
    """Verifies semantic cosine similarity discrimination between related and unrelated skills."""
    model_path = Path("artifacts/models/BAAI/bge-m3")
    if not model_path.exists():
        pytest.skip("Local BGE-M3 model weights not found")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(str(model_path), device=device)

    anchor = model.encode("Python Systems Engineering", normalize_embeddings=True)
    related = model.encode("Software Architecture in Python", normalize_embeddings=True)
    unrelated = model.encode("French Pastry Baking and Patisserie", normalize_embeddings=True)

    sim_related = float(anchor @ related)
    sim_unrelated = float(anchor @ unrelated)

    assert sim_related > sim_unrelated + 0.20, (
        f"Semantic discrimination failed: related ({sim_related:.3f}) <= unrelated ({sim_unrelated:.3f}) + 0.20"
    )
