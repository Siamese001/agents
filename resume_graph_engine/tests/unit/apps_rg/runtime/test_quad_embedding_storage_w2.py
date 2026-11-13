"""Wave 2 unit tests for learned sparse & ColBERT multi-vector storage and int8 quantization."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.runtime.bge_embedding import (
    dequantize_colbert_vectors_int8,
    project_multi_head_from_dense_and_text,
    quantize_colbert_vectors_int8,
)
from apps_rg.runtime.c0.sparse_sidecar import AppsRgSparseIndex, upsert_documents
from apps_rg.runtime.embedding_settings import BGE_M3_DIMENSION


def _maxsim(query_vecs: list[list[float]], doc_vecs: list[list[float]]) -> float:
    total = 0.0
    for qv in query_vecs:
        best = max(sum(a * b for a, b in zip(qv, dv)) for dv in doc_vecs)
        total += best
    return total / len(query_vecs)


def test_colbert_int8_quantization_preserves_maxsim_within_one_percent() -> None:
    unit = [1.0 / math.sqrt(BGE_M3_DIMENSION)] * BGE_M3_DIMENSION
    q_mh = project_multi_head_from_dense_and_text(
        "bi-temporal SQLite WAL Knowledge Graph with BGE-M3 ColBERT retrieval",
        unit,
        heads=("colbert",),
    )
    d_mh = project_multi_head_from_dense_and_text(
        "Designed a bi-temporal SQLite WAL Knowledge Graph fusing BGE-M3 and ColBERT MaxSim",
        unit,
        heads=("colbert",),
    )
    exact_score = _maxsim(q_mh.colbert, d_mh.colbert)
    blob, scales = quantize_colbert_vectors_int8(d_mh.colbert)
    reconstructed = dequantize_colbert_vectors_int8(blob, scales)
    quant_score = _maxsim(q_mh.colbert, reconstructed)
    assert abs(exact_score - quant_score) < 0.01


def test_materialized_sqlite_populates_all_four_index_families(tmp_path: Path) -> None:
    db_path = tmp_path / "augmented_skills_graph.sqlite"
    summary = materialize_augmented_skills_graph_sqlite(db_path=db_path)
    assert summary["learned_sparse_count"] > 300
    assert summary["colbert_vector_count"] == summary["learned_sparse_count"]

    with sqlite3.connect(db_path) as conn:
        unit_count = conn.execute("SELECT COUNT(*) FROM semantic_unit").fetchone()[0]
        dense_unit_count = conn.execute("SELECT COUNT(*) FROM unit_vectors").fetchone()[0]
        elig_skill_count = conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE node_type = 'skill' AND external_eligible = 1"
        ).fetchone()[0]
        sparse_count = conn.execute("SELECT COUNT(*) FROM assertion_learned_sparse").fetchone()[0]
        colbert_count = conn.execute("SELECT COUNT(*) FROM assertion_colbert_vectors").fetchone()[0]
        fts_count = conn.execute("SELECT COUNT(*) FROM graph_nodes_fts").fetchone()[0]
        node_count = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]

        assert unit_count == dense_unit_count
        assert fts_count == node_count
        assert sparse_count == unit_count + elig_skill_count
        assert colbert_count == unit_count + elig_skill_count

        sample_colbert = conn.execute(
            "SELECT token_count, dim, scales_json, vectors_int8 FROM assertion_colbert_vectors LIMIT 1"
        ).fetchone()
        assert sample_colbert is not None
        tok_count, dim, scales_json, blob = sample_colbert
        scales = json.loads(scales_json)
        assert len(scales) == tok_count
        vecs = dequantize_colbert_vectors_int8(blob, scales, dim=dim)
        assert len(vecs) == tok_count
        for v in vecs:
            norm = math.sqrt(sum(x * x for x in v))
            assert math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5)


def test_sparse_sidecar_indexes_and_queries_learned_sparse_weights(tmp_path: Path) -> None:
    stats = upsert_documents(
        "quad_test_collection",
        [
            {
                "id": "doc_1",
                "document": "Quad-engine hybrid retrieval with ColBERT late interaction and BGE-M3 sparse weights",
                "metadata": {"section": "architecture"},
            },
            {
                "id": "doc_2",
                "document": "Enterprise cloud data warehouse governance and cost optimization",
                "metadata": {"section": "cloud"},
            },
        ],
        sparse_dir=tmp_path,
    )
    assert stats["doc_count"] == 2
    idx = AppsRgSparseIndex("quad_test_collection", sparse_dir=tmp_path)
    assert idx.is_available
    hits = idx.search_learned_sparse("ColBERT late interaction hybrid retrieval", top_k=2)
    assert len(hits) >= 1
    assert hits[0]["id"] == "doc_1"
    assert float(hits[0]["score"]) > 0.0
