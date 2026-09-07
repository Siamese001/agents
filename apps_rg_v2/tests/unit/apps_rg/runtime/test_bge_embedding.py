from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import torch

from apps_rg.runtime import bge_embedding
from apps_rg.runtime.bge_embedding import (
    BgeEmbeddingContractError,
    BgeRuntimeKey,
    embed_text,
    get_bge_runtime,
    load_local_bge_model,
    resolve_bge_precision_dtype,
    resolve_bge_precision_profile_id,
    resolve_bge_batch_size,
    resident_runtime_observation,
    unload_bge_runtime,
)
from apps_rg.runtime.embedding_settings import BGE_M3_DIMENSION


class _Model:
    def __init__(self, dimension: int = BGE_M3_DIMENSION) -> None:
        self.dimension = dimension
        self.device = "cpu"
        self.calls: list[dict] = []
        self.to_calls: list[str] = []

    def encode(self, texts: list[str], **kwargs) -> np.ndarray:
        self.calls.append(
            {
                "texts": list(texts),
                "kwargs": kwargs,
                "inference_mode": torch.is_inference_mode_enabled(),
            }
        )
        value = 1.0 / math.sqrt(self.dimension)
        return np.full((len(texts), self.dimension), value, dtype=np.float32)

    def to(self, device: str) -> None:
        self.to_calls.append(device)


class _Tokenizer:
    model_max_length = 8

    def __call__(self, texts: list[str], **_kwargs) -> dict[str, list[list[int]]]:
        return {"input_ids": [list(range(len(text.split()) + 2)) for text in texts]}


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    bge_embedding.reset_bge_runtime_for_testing()
    yield
    bge_embedding.reset_bge_runtime_for_testing()


def test_embed_text_preserves_shape_normalization_and_inference_mode() -> None:
    model = _Model()

    vector = embed_text(model, "partner-led AI deployment")

    assert len(vector) == BGE_M3_DIMENSION
    assert model.calls == [
        {
            "texts": ["partner-led AI deployment"],
            "kwargs": {
                "batch_size": 1,
                "convert_to_numpy": True,
                "normalize_embeddings": True,
                "show_progress_bar": False,
            },
            "inference_mode": True,
        }
    ]
    assert math.isclose(math.sqrt(sum(item * item for item in vector)), 1.0)


def test_embed_text_rejects_wrong_dimension() -> None:
    with pytest.raises(BgeEmbeddingContractError, match="dimension mismatch"):
        embed_text(_Model(dimension=1), "text")


def test_embed_text_post_normalizes_low_precision_rounding() -> None:
    model = _Model()
    model.encode = lambda texts, **kwargs: np.full(  # type: ignore[method-assign]
        (len(texts), BGE_M3_DIMENSION),
        np.float16(1.0 / math.sqrt(BGE_M3_DIMENSION)),
        dtype=np.float16,
    )

    vector = embed_text(model, "low precision candidate")

    assert math.isclose(
        math.sqrt(sum(item * item for item in vector)),
        1.0,
        rel_tol=1e-7,
        abs_tol=1e-7,
    )


def test_embed_text_rejects_materially_unnormalized_output() -> None:
    model = _Model()
    model.encode = lambda texts, **kwargs: np.ones(  # type: ignore[method-assign]
        (len(texts), BGE_M3_DIMENSION), dtype=np.float32
    )

    with pytest.raises(BgeEmbeddingContractError, match="not L2 normalized"):
        embed_text(model, "invalid output")


def test_resident_runtime_loads_and_warms_once_per_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = _Model()
    loads: list[object] = []

    def _load(key):
        loads.append(key)
        return model

    monkeypatch.setattr(bge_embedding, "load_local_bge_model", _load)

    first = get_bge_runtime(model_path=tmp_path, device="cpu")
    second = get_bge_runtime(model_path=tmp_path, device="cpu")
    vectors = second.encode(["one", "two"], batch_size=2)

    assert first is second
    assert len(loads) == 1
    assert len(model.calls) == 2  # one fixed warm-up plus one caller batch
    assert all(call["inference_mode"] for call in model.calls)
    assert len(vectors) == 2
    observation = resident_runtime_observation()
    assert observation["registry_size"] == 1
    assert observation["model_load_count"] == 1
    assert observation["runtimes"][0]["warmup_completed"] is True
    assert observation["runtimes"][0]["encode_call_count"] == 1
    assert observation["runtimes"][0]["encoded_text_count"] == 2


def test_runtime_observation_records_bounded_timing_lengths_and_memory_safe_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = _Model()
    model.tokenizer = _Tokenizer()  # type: ignore[attr-defined]
    monkeypatch.setattr(bge_embedding, "load_local_bge_model", lambda _key: model)
    runtime = get_bge_runtime(
        model_path=tmp_path, device="cpu", dtype="float16", warmup=False
    )

    runtime.encode(["one two", "three four five"], batch_size=2)
    runtime.encode(["six seven"], batch_size=1)

    observation = runtime.observation()
    assert observation["caller_timing"]["cold_elapsed_ms"] is not None
    assert observation["caller_timing"]["warm"]["sample_count"] == 1
    assert observation["caller_timing"]["history_limit"] == 128
    assert observation["last_encode"]["input_count"] == 1
    assert observation["last_encode"]["batch_size"] == 1
    assert observation["last_encode"]["token_lengths_available"] is True
    assert observation["last_encode"]["token_lengths"]["max"] == 4
    assert observation["last_encode"]["cuda_memory"] is None
    assert "six seven" not in str(observation)


def test_local_loader_forces_local_files_and_selected_dtype(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sentence_transformers

    calls: list[tuple[str, dict]] = []

    def _construct(path: str, **kwargs):
        calls.append((path, kwargs))
        return _Model()

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", _construct)
    key = BgeRuntimeKey(
        model_path=str(tmp_path),
        device="cpu",
        dtype="float16",
        backend="sentence_transformers",
    )

    load_local_bge_model(key)

    assert calls == [
        (
            str(tmp_path),
            {
                "device": "cpu",
                "local_files_only": True,
                "model_kwargs": {"torch_dtype": torch.float16},
            },
        )
    ]


def test_runtime_key_includes_dtype_and_explicit_unload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    models: list[_Model] = []

    def _load(_key):
        model = _Model()
        models.append(model)
        return model

    monkeypatch.setattr(bge_embedding, "load_local_bge_model", _load)
    fp32 = get_bge_runtime(
        model_path=tmp_path, device="cpu", dtype="float32", warmup=False
    )
    fp16 = get_bge_runtime(
        model_path=tmp_path, device="cpu", dtype="float16", warmup=False
    )

    assert fp32 is not fp16
    assert resident_runtime_observation()["model_load_count"] == 2
    assert unload_bge_runtime(fp32.key) == 1
    assert models[0].to_calls == ["cpu"]
    with pytest.raises(BgeEmbeddingContractError, match="unloaded"):
        _ = fp32.model
    assert resident_runtime_observation()["registry_size"] == 1


def test_runtime_rejects_unsupported_backend(tmp_path: Path) -> None:
    with pytest.raises(BgeEmbeddingContractError, match="unsupported BGE backend"):
        get_bge_runtime(model_path=tmp_path, device="cpu", backend="remote")


def test_precision_profile_defaults_to_selected_and_supports_fp32_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPS_RG_BGE_PRECISION_PROFILE", raising=False)
    assert resolve_bge_precision_profile_id() == "fp16_candidate"
    assert resolve_bge_precision_dtype() == "float16"

    monkeypatch.setenv("APPS_RG_BGE_PRECISION_PROFILE", "fp32_control")
    assert resolve_bge_precision_dtype() == "float32"


def test_precision_profile_rejects_unknown_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPS_RG_BGE_PRECISION_PROFILE", "unknown")
    with pytest.raises(BgeEmbeddingContractError, match="unconfigured"):
        resolve_bge_precision_dtype()


def test_runtime_rejects_legacy_dtype_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APPS_RG_BGE_DTYPE", "bfloat16")
    with pytest.raises(BgeEmbeddingContractError, match="governed precision profile"):
        get_bge_runtime(model_path=tmp_path, device="cpu", warmup=False)


def test_batch_profile_caps_workloads_without_reordering() -> None:
    assert resolve_bge_batch_size("c02_section_queries", 7) == 7
    assert resolve_bge_batch_size("c02_fact_vector_ingest", 100) == 16
    assert resolve_bge_batch_size("c03_projection", 6) == 6
    assert resolve_bge_batch_size("r1b_projection", 3) == 3


def test_batch_profile_rejects_requested_size_above_workload_maximum() -> None:
    with pytest.raises(BgeEmbeddingContractError, match="outside profile"):
        resolve_bge_batch_size("r1b_projection", 100, requested=65)


def test_batch_profile_rejects_weakened_controls(tmp_path: Path) -> None:
    profile = tmp_path / "batch-profile.json"
    profile.write_text(
        """{
  "schema_version": "apps_rg.bge_batch_profile.v1",
  "adaptive_growth_allowed": true,
  "fallback_allowed": false,
  "workloads": {}
}
""",
        encoding="utf-8",
    )

    with pytest.raises(BgeEmbeddingContractError, match="control flags"):
        resolve_bge_batch_size("c02_section_queries", 1, profile_path=profile)
