from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import torch

from apps_rg.cache.r1b_bge_embedding import embed_texts_bge
from apps_rg.fact_inventory.c03_skill_embedding_builder import encode_bge_m3
from apps_rg.runtime import bge_embedding
from apps_rg.runtime.bindings import c0_binding


class _ResidentModel:
    device = "cpu"

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], bool]] = []

    def encode(self, texts: list[str], **_kwargs) -> np.ndarray:
        self.calls.append((list(texts), torch.is_inference_mode_enabled()))
        value = 1.0 / math.sqrt(1024)
        return np.full((len(texts), 1024), value, dtype=np.float32)

    def to(self, _device: str) -> None:
        return None


def test_c0_c03_and_r1b_share_one_process_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bge_embedding.reset_bge_runtime_for_testing()
    model_path = tmp_path / "bge-m3"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("APPS_RG_EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("APPS_RG_EMBEDDING_MODEL_PATH", str(model_path))
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))

    model = _ResidentModel()
    loads: list[object] = []

    def _load(key):
        loads.append(key)
        return model

    monkeypatch.setattr(bge_embedding, "load_local_bge_model", _load)

    c0_runtime = c0_binding._get_embedding_runtime()
    c03_runtime, c03_vectors = encode_bge_m3(
        ["c03 assertion"], model_path=model_path, device="cpu", batch_size=1
    )
    r1b_vectors = embed_texts_bge(["r1b intent"], batch_size=1)

    assert len(loads) == 1
    assert c0_runtime is bge_embedding.get_bge_runtime(
        model_path=model_path, device="cpu"
    )
    assert c03_runtime["resident_runtime"]["load_ordinal"] == 1
    assert len(c03_vectors[0]) == 1024
    assert r1b_vectors[0] is not None and len(r1b_vectors[0]) == 1024
    observation = bge_embedding.resident_runtime_observation()
    assert observation["registry_size"] == 1
    assert observation["model_load_count"] == 1
    assert observation["runtimes"][0]["encode_call_count"] == 2
    assert all(inference_mode for _texts, inference_mode in model.calls)

    assert bge_embedding.unload_bge_runtime() == 1
    assert bge_embedding.resident_runtime_observation()["registry_size"] == 0
