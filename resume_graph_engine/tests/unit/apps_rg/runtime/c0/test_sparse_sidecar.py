"""Contract tests for the standalone Apps RG C0.2 sparse sidecar."""

from __future__ import annotations

import pytest

from apps_rg.runtime.local_retrieval import SparseLexicalLaneStatus, SparseLexicalQuerySpec
from apps_rg.runtime.c0 import sparse_sidecar


def test_upsert_builds_readable_fts_sidecar_and_replaces_stale_terms(tmp_path) -> None:
    sparse_dir = tmp_path / "sparse"
    first = sparse_sidecar.upsert_documents(
        "fact_vectors",
        [
            {
                "id": "fact-a",
                "document": "Agentic AI platform strategy and executive leadership.",
                "metadata": {"source_class": "candidate_profile", "section_targets": "competencies"},
            },
            {
                "id": "fact-b",
                "document": "Insurance operating-model modernization with measurable outcomes.",
                "metadata": {"source_class": "project_evidence", "section_targets": "competencies"},
            },
        ],
        sparse_dir=sparse_dir,
    )

    assert first == {"upserted_count": 2, "doc_count": 2, "term_count": first["term_count"]}
    assert first["term_count"] > 0
    assert sparse_sidecar.sidecar_summary("fact_vectors", sparse_dir=sparse_dir)["available"] is True

    index = sparse_sidecar.AppsRgSparseIndex("fact_vectors", sparse_dir=sparse_dir)
    assert index.is_available is True
    assert [row["id"] for row in index.search("agentic AI strategy")] == ["fact-a"]

    sparse_sidecar.upsert_documents(
        "fact_vectors",
        [
            {
                "id": "fact-a",
                "document": "Cloud partnership operating model and executive leadership.",
                "metadata": {"source_class": "candidate_profile", "section_targets": "competencies"},
            }
        ],
        sparse_dir=sparse_dir,
    )

    assert index.search("agentic AI") == []
    assert [row["id"] for row in index.search("cloud partnership")] == ["fact-a"]


def test_query_lane_applies_metadata_filter_and_preserves_generic_outcome_shape(tmp_path) -> None:
    sparse_dir = tmp_path / "sparse"
    sparse_sidecar.upsert_documents(
        "fact_vectors",
        [
            {
                "id": "fact-a",
                "document": "AI platform strategy with partner enablement.",
                "metadata": {"source_class": "candidate_profile"},
            },
            {
                "id": "fact-b",
                "document": "AI platform strategy with partner enablement.",
                "metadata": {"source_class": "project_evidence"},
            },
        ],
        sparse_dir=sparse_dir,
    )
    spec = SparseLexicalQuerySpec(
        lane_id="c0.sparse.competencies",
        query_text="AI platform strategy",
        top_k=5,
        sparse_index_collection_name="fact_vectors",
        metadata_filter={"source_class": "candidate_profile"},
    )

    outcome = sparse_sidecar.query_apps_rg_sparse_lexical_lane(spec, sparse_dir=sparse_dir)

    assert outcome.status is SparseLexicalLaneStatus.OK
    assert outcome.receipt_ref.endswith("status=OK:hits=1")
    assert [row.chunk_id for row in outcome.hybrid_rows] == ["fact-a"]
    assert [hit.source_id for hit in outcome.hits] == ["fact-a"]


def test_build_for_collection_rebuilds_from_controlled_chroma_rows(tmp_path, monkeypatch) -> None:
    class _Collection:
        def count(self) -> int:
            return 2

        def get(self, *, limit, offset, include):
            assert include == ["documents", "metadatas"]
            if offset:
                return {"ids": [], "documents": [], "metadatas": []}
            return {
                "ids": ["fact-a", "fact-b"],
                "documents": ["AI strategy", "Insurance platform"],
                "metadatas": [{"source_class": "candidate_profile"}, {"source_class": "project_evidence"}],
            }

    class _Client:
        def get_collection(self, name):
            assert name == "fact_vectors"
            return _Collection()

    monkeypatch.setattr(
        "apps_rg.runtime.c0.chroma_persistent_client.ensure_apps_rg_chroma_client",
        lambda _path: _Client(),
    )

    stats = sparse_sidecar.build_for_collection(
        "fact_vectors",
        chroma_path=tmp_path / "chroma",
        sparse_dir=tmp_path / "sparse",
    )

    assert stats["doc_count"] == 2
    assert stats["term_count"] > 0
    assert sparse_sidecar.sparse_sidecar_exists("fact_vectors", sparse_dir=tmp_path / "sparse")


def test_invalid_collection_name_fails_closed(tmp_path) -> None:
    with pytest.raises(ValueError, match="invalid sparse collection name"):
        sparse_sidecar.upsert_documents("../not-a-collection", [], sparse_dir=tmp_path)
