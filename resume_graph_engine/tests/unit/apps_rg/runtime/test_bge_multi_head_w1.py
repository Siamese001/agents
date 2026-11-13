"""Wave 1 unit tests for BGE-M3 multi-head runtime (dense + learned sparse + ColBERT)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import torch

from apps_rg.runtime import bge_embedding
from apps_rg.runtime.bge_embedding import (
    BgeEmbeddingContractError,
    MultiHeadEmbedding,
    embed_multi_head,
    get_bge_runtime,
    load_bge_m3_linear_heads,
    project_multi_head_from_dense_and_text,
)
from apps_rg.runtime.embedding_settings import BGE_M3_DIMENSION


class _MockBgeModel:
    def __init__(self, dimension: int = BGE_M3_DIMENSION) -> None:
        self.dimension = dimension
        self.device = "cpu"

    def encode(self, texts: list[str], **_kwargs) -> np.ndarray:
        rows = []
        for idx, _text in enumerate(texts):
            vec = np.full(self.dimension, 1.0 / math.sqrt(self.dimension), dtype=np.float32)
            vec[idx % self.dimension] += 0.01
            vec = vec / np.linalg.norm(vec)
            rows.append(vec)
        return np.stack(rows, axis=0)


@pytest.fixture(autouse=True)
def _reset_bge_registry() -> None:
    bge_embedding.reset_bge_runtime_for_testing()
    yield
    bge_embedding.reset_bge_runtime_for_testing()


def test_load_bge_m3_linear_heads_resolves_local_weights() -> None:
    heads = load_bge_m3_linear_heads()
    if heads["resolved"]:
        assert tuple(heads["sparse_weight"].shape) == (1, BGE_M3_DIMENSION)
        assert tuple(heads["colbert_weight"].shape) == (BGE_M3_DIMENSION, BGE_M3_DIMENSION)


def test_embed_multi_head_returns_dense_sparse_and_colbert() -> None:
    model = _MockBgeModel()
    outputs = embed_multi_head(
        model,
        [
            "Governed bi-temporal SQLite WAL Knowledge Graph with BGE-M3 retrieval",
            "ColBERT MaxSim late interaction and learned sparse lexical weights",
        ],
    )
    assert len(outputs) == 2
    for item in outputs:
        assert isinstance(item, MultiHeadEmbedding)
        assert len(item.dense) == BGE_M3_DIMENSION
        dense_norm = math.sqrt(sum(v * v for v in item.dense))
        assert math.isclose(dense_norm, 1.0, rel_tol=1e-6, abs_tol=1e-6)
        assert len(item.sparse) >= 4
        assert all(weight > 0.0 and math.isfinite(weight) for weight in item.sparse.values())
        assert len(item.colbert) >= 4
        for token_vec in item.colbert:
            assert len(token_vec) == BGE_M3_DIMENSION
            tok_norm = math.sqrt(sum(v * v for v in token_vec))
            assert math.isclose(tok_norm, 1.0, rel_tol=1e-5, abs_tol=1e-5)


def test_resident_runtime_encode_multi_head_supports_head_subset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(bge_embedding, "load_local_bge_model", lambda _key: _MockBgeModel())
    runtime = get_bge_runtime(model_path=tmp_path, device="cpu", dtype="float32")
    results = runtime.encode_multi_head(
        ["Enterprise AI platform governance and partner co-sell execution"],
        heads=("dense", "colbert"),
    )
    assert len(results) == 1
    assert len(results[0].dense) == BGE_M3_DIMENSION
    assert results[0].sparse == {}
    assert len(results[0].colbert) >= 4


def test_project_multi_head_rejects_unknown_head() -> None:
    unit = [1.0 / math.sqrt(BGE_M3_DIMENSION)] * BGE_M3_DIMENSION
    with pytest.raises(BgeEmbeddingContractError, match="unsupported BGE-M3 heads"):
        project_multi_head_from_dense_and_text("test query", unit, heads=("invalid_head",))
