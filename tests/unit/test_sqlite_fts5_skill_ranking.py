"""Unit tests for Wave 1 SQLite FTS5 keyword index and BM25 ranking."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from apps_rg.fact_inventory.skills_graph.materializer import (
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.runtime.graph_skill_hybrid_retrieval import (
    GraphSkillHybridRetrievalError,
    fuse_dense_bm25,
    sqlite_fts5_bm25_rank,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2] / "resume_graph_engine"


def test_materializer_populates_graph_nodes_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "augmented_skills_graph.sqlite"
    summary = materialize_augmented_skills_graph_sqlite(
        repo_root=_repo_root(),
        db_path=db_path,
    )
    assert "graph_nodes_fts" in summary["tables_created"]

    conn = sqlite3.connect(str(db_path))
    try:
        node_count = int(conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0])
        fts_count = int(conn.execute("SELECT COUNT(*) FROM graph_nodes_fts").fetchone()[0])
        assert node_count > 0
        assert fts_count == node_count

        ranked = sqlite_fts5_bm25_rank(
            conn,
            "governed agentic retrieval graph architecture",
            node_type="skill",
        )
        assert len(ranked) > 0
        assert float(ranked[0]["bm25_score"]) > 0.0
    finally:
        conn.close()


def test_sqlite_fts5_bm25_rank_fuses_with_dense_candidates() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            """
            CREATE TABLE graph_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE graph_nodes_fts USING fts5(
                node_id UNINDEXED,
                node_type UNINDEXED,
                label,
                description
            )
            """
        )
        rows = [
            (
                "skill_hybrid_retrieval",
                "skill",
                "Hybrid Graph Retrieval Architecture",
                "Dense BGE-M3 and sparse BM25 reciprocal rank fusion over SQLite FTS5",
            ),
            (
                "skill_governance_gates",
                "skill",
                "Runtime Governance Gate Mesh",
                "Fail-closed runtime verification and pre-commit policy gates",
            ),
            (
                "skill_cloud_finops",
                "skill",
                "Cloud Cost Optimization",
                "Multi-tenant cloud budget allocation and reserved instance planning",
            ),
        ]
        conn.executemany("INSERT INTO graph_nodes VALUES (?, ?, ?, ?)", rows)
        conn.execute(
            """
            INSERT INTO graph_nodes_fts (node_id, node_type, label, description)
            SELECT node_id, node_type, label, description FROM graph_nodes
            """
        )

        authority_ids = {r[0] for r in rows}
        bm25_candidates = sqlite_fts5_bm25_rank(
            conn,
            "hybrid graph retrieval bm25 sqlite",
            node_ids=authority_ids,
        )
        assert len(bm25_candidates) == 3
        assert bm25_candidates[0]["assertion_id"] == "skill_hybrid_retrieval"
        assert float(bm25_candidates[0]["bm25_score"]) > 0.0
        assert float(bm25_candidates[-1]["bm25_score"]) == 0.0

        dense_candidates = [
            {"assertion_id": "skill_hybrid_retrieval", "similarity": 0.91},
            {"assertion_id": "skill_governance_gates", "similarity": 0.74},
            {"assertion_id": "skill_cloud_finops", "similarity": 0.35},
        ]
        fused = fuse_dense_bm25(
            dense_candidates,
            bm25_candidates,
            assertion_ids=authority_ids,
        )
        assert fused[0]["assertion_id"] == "skill_hybrid_retrieval"
        assert fused[0]["bm25_rank"] == 1
        assert fused[0]["dense_rank"] == 1

        with pytest.raises(GraphSkillHybridRetrievalError):
            sqlite_fts5_bm25_rank(
                conn,
                "hybrid retrieval",
                node_ids={"skill_unknown_unauthorized"},
            )
    finally:
        conn.close()
