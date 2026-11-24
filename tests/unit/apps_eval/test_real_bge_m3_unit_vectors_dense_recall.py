"""Non-mock regression tests for live BGE-M3 unit_vectors and runtime QuadGraphHybridRetriever dense recall."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.runtime.bge_multi_head import (
    LIVE_BGE_M3_MANIFEST_PREFIX,
    resolve_local_bge_m3_model_dir,
)
from apps_rg.runtime.quad_graph_retriever import QuadGraphHybridRetriever

REPO_ROOT = Path(__file__).resolve().parents[3]
RGE_ROOT = REPO_ROOT / "resume_graph_engine"


def test_materialized_unit_vectors_persist_live_bge_m3_and_runtime_dense_recall(tmp_path: Path) -> None:
    model_dir = resolve_local_bge_m3_model_dir()
    assert model_dir is not None and model_dir.is_dir()

    # Fast content-addressed cache reuse when rebuilding into an isolated sandbox DB
    db_path = tmp_path / "augmented_skills_graph.sqlite"
    t0 = time.perf_counter()
    summary = materialize_augmented_skills_graph_sqlite(repo_root=RGE_ROOT, db_path=db_path)
    elapsed_s = time.perf_counter() - t0
    assert summary["live_bge_m3_vectors"] == 1
    assert summary["semantic_unit_count"] == 376
    assert elapsed_s < 15.0

    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as conn:
        tags = conn.execute(
            "SELECT DISTINCT model_manifest_sha, COUNT(*) FROM unit_vectors GROUP BY model_manifest_sha"
        ).fetchall()
        assert len(tags) == 1
        assert str(tags[0][0]).startswith(LIVE_BGE_M3_MANIFEST_PREFIX)
        assert int(tags[0][1]) == 376

        # Live runtime QuadGraphHybridRetriever.retrieve() must find the exact semantic unit via dense channel
        retriever = QuadGraphHybridRetriever(conn, db_path=str(db_path))
        probes = (
            (
                "How many software engineers and enterprise AI charters did Slalom leadership direct for the Fortune 200 utility?",
                "engagement_episode:0e182e2ee7e656a4",
            ),
            (
                "How much gross margin expansion did Unify achieve from its commercial platform operating model?",
                "metric_outcome_story:02fce348f96071c9",
            ),
            (
                "EY BCBS 239 risk-data aggregation lineage metadata controls",
                "metric_outcome_story:0523a20059c1a8af",
            ),
        )
        for query_text, expected_uid in probes:
            res = retriever.retrieve(query_text, top_k=10, union_limit=100)
            assert res["dense_executed"] is True
            assert res["sparse_executed"] is True
            assert res["colbert_executed"] is True
            assert res["bm25_executed"] is True
            by_id = {row["record_id"]: row for row in res["results"]}
            assert expected_uid in by_id, f"Expected {expected_uid} in top 10 for {query_text!r}"
            assert int(by_id[expected_uid]["dense_rank"]) <= 5, (
                f"Expected live BGE-M3 dense_rank <= 5 for {expected_uid}, got {by_id[expected_uid]['dense_rank']}"
            )

        # Pure semantic paraphrase probe (zero lexical overlap on 'software engineers' / 'charters'):
        # proves persisted unit_vectors carry real BGE-M3 semantic geometry even when BM25 ranks it low.
        paraphrase_res = retriever.retrieve(
            "How many builders and client engagements did Slalom engineering leadership scale?",
            top_k=30,
            union_limit=100,
        )
        paraphrase_by_id = {row["record_id"]: row for row in paraphrase_res["results"]}
        assert "engagement_episode:0e182e2ee7e656a4" in paraphrase_by_id
        assert int(paraphrase_by_id["engagement_episode:0e182e2ee7e656a4"]["dense_rank"]) <= 3
        assert int(paraphrase_by_id["engagement_episode:0e182e2ee7e656a4"]["bm25_rank"]) > 20
