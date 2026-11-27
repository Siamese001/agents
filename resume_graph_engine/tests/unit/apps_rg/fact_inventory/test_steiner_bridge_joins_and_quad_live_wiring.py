"""Wave 4 verification tests for Steiner Bridge Joins, FTS5 Aliases, and Live Quad Retrieval."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from apps_rg.runtime.graph_skill_hybrid_retrieval import bm25_rank, sqlite_fts5_bm25_rank
from apps_rg.runtime.graph_traversal import traverse_steiner_bridges
from apps_rg.runtime.quad_graph_retriever import QuadGraphHybridRetriever

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    assert DB_PATH.is_file(), f"Augmented skills graph DB missing at {DB_PATH}"
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    yield conn
    conn.close()


def test_w4_path_section_ids_rarity_novelty_and_views(db_conn: sqlite3.Connection) -> None:
    """graph_paths populates section_ids_json, fixes inverted novelty_score, and exposes multi-arc views."""
    non_empty_sections = db_conn.execute(
        "SELECT COUNT(*) FROM graph_paths WHERE json_array_length(section_ids_json) > 0"
    ).fetchone()[0]
    total_paths = db_conn.execute("SELECT COUNT(*) FROM graph_paths").fetchone()[0]
    assert total_paths > 10000
    assert non_empty_sections >= 5000, f"Expected >=5000 paths with section_ids_json, got {non_empty_sections}"

    # Verify high-proof paths do not suffer from inverted 1/(metrics+facts) novelty collapse
    avg_rich = db_conn.execute(
        "SELECT AVG(path_score) FROM graph_paths WHERE json_array_length(proof_fact_ids_json) >= 1 AND json_array_length(metric_ids_json) >= 1"
    ).fetchone()[0]
    avg_empty = db_conn.execute(
        "SELECT AVG(path_score) FROM graph_paths WHERE json_array_length(proof_fact_ids_json) = 0 AND json_array_length(metric_ids_json) = 0"
    ).fetchone()[0]
    assert avg_rich is not None and avg_empty is not None
    assert float(avg_rich) > float(avg_empty), f"Rich proof paths ({avg_rich}) must outscore empty paths ({avg_empty})"

    role_sec_rows = db_conn.execute("SELECT COUNT(*) FROM v_role_section_skill_candidates").fetchone()[0]
    multi_arc_rows = db_conn.execute("SELECT COUNT(*) FROM v_multi_arc_skill_continuity").fetchone()[0]
    assert role_sec_rows >= 1000
    assert multi_arc_rows >= 50

    su_fts_cnt = db_conn.execute("SELECT COUNT(*) FROM semantic_unit_fts").fetchone()[0]
    assert su_fts_cnt >= 200


def test_w4_fts5_aliases_and_steiner_cross_arc_bridges(db_conn: sqlite3.Connection) -> None:
    """FTS5 recalls FSA/ERM aliases and Steiner traversal bridges actuarial and agentic AI seeds."""
    fsa_hits = sqlite_fts5_bm25_rank(db_conn, "Fellow Society Actuaries FSA Solvency", node_type="skill")
    assert len(fsa_hits) > 0 and float(fsa_hits[0]["bm25_score"]) > 0.0

    # Domain token preservation in BM25
    docs = {
        "d1": "Modernized P&C Guidewire policy stack and CI/CD pipelines for SOC 2 compliance",
        "d2": "Generic leadership narrative without technical domain terms",
    }
    ranked = bm25_rank("P&C CI/CD SOC 2", docs)
    assert ranked[0]["assertion_id"] == "d1" and float(ranked[0]["bm25_score"]) > 0.0

    bridges = traverse_steiner_bridges(
        db_conn,
        ["skill_actuarial_fsa_fellowship", "skill_governed_agentic_systems_architecture"],
        max_hops=3,
        max_bridges=20,
    )
    assert len(bridges) > 0, "Steiner traversal failed to bridge actuarial FSA and agentic AI architecture"
    assert any(b["cross_epoch"] for b in bridges)


def test_w4_quad_retriever_skill_dense_coverage(db_conn: sqlite3.Connection) -> None:
    """QuadGraphHybridRetriever scores skill_* nodes with non-zero dense similarity via root_node_id mapping."""
    retriever = QuadGraphHybridRetriever(db_conn, db_path=str(DB_PATH))
    res = retriever.retrieve(
        "Chief AI Officer insurance underwriting GraphRAG FSA Solvency II actuarial risk governance",
        top_k=25,
        union_limit=80,
        include_graph_signals=True,
    )
    rows = res.get("results") or []
    assert len(rows) > 0
    assert res["dense_executed"] is True
    assert res["bm25_executed"] is True
    # Verify skill IDs in VectorCache have dense coverage
    skill_cached = [rid for rid in retriever.vector_cache.record_ids if rid.startswith("skill_")]
    assert len(skill_cached) >= 150, f"Expected >=150 skill_* vectors in VectorCache, got {len(skill_cached)}"
