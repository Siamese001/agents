"""W3 production paths batch eligible BGE inputs without changing order."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps_rg.runtime.bindings import c0_binding
from apps_rg.runtime.c0 import c02_fact_vector_ingest as ingest


class _BatchProfile:
    enabled = True
    collection_name = "fact_vectors"
    max_total_items = 12
    max_sections = 8

    def get_sections(self) -> list[dict[str, object]]:
        return [
            {
                "section_id": section_id,
                "source_class_allowlist": ["candidate_profile"],
                "dense_top_k": 3,
            }
            for section_id in ("first", "second", "third")
        ]

    def resolve_section_id(self, section_id: str) -> str:
        return section_id

    def build_query_for_section(
        self, section: dict[str, object], _payload: dict[str, object]
    ) -> str:
        return f"query-{section['section_id']}"

    def section_sparse_config(self, _section: dict[str, object]) -> dict[str, object]:
        return {}

    def any_sparse_enabled(self) -> bool:
        return False


class _BatchMetadataProfile:
    def build_chroma_where_clause(
        self,
        _payload: dict[str, object],
        *,
        source_class_allowlist: list[str],
    ) -> dict[str, object]:
        return {
            "$and": [
                {"app": "apps_rg"},
                {"source_class": {"$in": source_class_allowlist}},
            ]
        }


class _RecordingRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], int]] = []

    def encode(self, texts: list[str], *, batch_size: int) -> list[list[float]]:
        self.calls.append((list(texts), batch_size))
        return [[float(index)] * 1024 for index in range(1, len(texts) + 1)]


class _EmptyRecordingCollection:
    def __init__(self) -> None:
        self.query_vectors: list[float] = []

    def query(self, *, query_embeddings, n_results, where):
        del n_results, where
        self.query_vectors.append(float(query_embeddings[0][0]))
        return {"ids": [[]], "metadatas": [[]], "documents": [[]], "distances": [[]]}


def test_section_queries_are_encoded_once_and_consumed_in_stable_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _RecordingRuntime()
    collection = _EmptyRecordingCollection()
    monkeypatch.setattr(c0_binding, "SectionRetrievalProfile", _BatchProfile)
    monkeypatch.setattr(c0_binding, "MetadataFilterProfile", _BatchMetadataProfile)
    monkeypatch.setattr(c0_binding, "_get_embedding_runtime", lambda: runtime)
    monkeypatch.setattr(c0_binding, "_run_section_sparse_lane", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "apps_rg.runtime.embedding_settings.resolve_apps_rg_embedding_settings",
        lambda **kwargs: SimpleNamespace(embedding_model_name="BAAI/bge-m3"),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.embedding_settings.assert_dense_retrieval_allowed",
        lambda settings: None,
    )

    result = c0_binding._perform_bounded_section_retrieval(
        "",
        {"jd_payload": {}},
        "digest",
        "2026-08-07T00:00:00Z",
        chroma_collection=collection,
    )

    assert runtime.calls == [
        (["query-first", "query-second", "query-third"], 3)
    ]
    assert collection.query_vectors == [1.0, 2.0, 3.0]
    assert result[2] == "EMPTY"


class _Chunk:
    def __init__(self, index: int) -> None:
        self.index = index


class _UpsertCollection:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    def upsert(self, **kwargs) -> None:
        self.payload = kwargs


def test_c02_ingest_encodes_one_ordered_batch_before_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _RecordingRuntime()
    collection = _UpsertCollection()
    chunks = [_Chunk(1), _Chunk(2), _Chunk(3)]
    monkeypatch.setattr(
        ingest,
        "chunk_to_chroma_document",
        lambda chunk, atom: {
            "id": f"id-{chunk.index}",
            "text": f"text-{chunk.index}",
            "metadata": {"ordinal": chunk.index},
        },
    )
    monkeypatch.setattr(
        "apps_rg.runtime.bge_embedding.get_bge_runtime_for_settings",
        lambda settings: runtime,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.embedding_settings.resolve_apps_rg_embedding_settings",
        lambda **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.embedding_settings.apply_apps_rg_embedding_env_guards",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.embedding_settings.assert_dense_retrieval_allowed",
        lambda settings: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.c0.chroma_persistent_client.ensure_apps_rg_chroma_client",
        lambda path: object(),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.chroma_precomputed_collection.get_precomputed_embeddings_collection",
        lambda *args, **kwargs: collection,
    )

    count = ingest.upsert_fact_vector_chunks(
        chunks,  # type: ignore[arg-type]
        chroma_path="C:/runtime/chroma",
    )

    assert count == 3
    assert runtime.calls == [(["text-1", "text-2", "text-3"], 3)]
    assert collection.payload is not None
    assert collection.payload["ids"] == ["id-1", "id-2", "id-3"]
    assert [row[0] for row in collection.payload["embeddings"]] == [1.0, 2.0, 3.0]
