from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import math
from pathlib import Path

import numpy as np
import pytest
import torch

from apps_rg.evals import gpu_embedding_stability_w6 as w6
from apps_rg.evals.gpu_embedding_stability_w6 import (
    GpuEmbeddingStabilityError,
    RECEIPT_SCHEMA,
    validate_stability_receipt,
)
from apps_rg.runtime import bge_embedding
from apps_rg.runtime.bge_embedding import (
    get_bge_runtime,
    receipt_sha256,
    resident_runtime_observation,
)
from apps_rg.runtime.embedding_settings import BGE_M3_DIMENSION


class _Model:
    def __init__(self) -> None:
        self.device = "cpu"
        self.calls = 0

    def encode(self, texts: list[str], **_kwargs) -> np.ndarray:
        self.calls += 1
        value = 1.0 / math.sqrt(BGE_M3_DIMENSION)
        return np.full((len(texts), BGE_M3_DIMENSION), value, dtype=np.float32)

    def to(self, _device: str) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    bge_embedding.reset_bge_runtime_for_testing()
    yield
    bge_embedding.reset_bge_runtime_for_testing()


def _receipt() -> dict:
    stability = {"workload_id": "workload", "passed": True}
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS",
        "runtime": {
            "concurrent_acquisition": {
                "unique_runtime_object_count": 1,
                "model_load_count": 1,
                "registry_size": 1,
            },
            "network_allowed": False,
            "fallback_used": False,
        },
        "workload_stability": [copy.deepcopy(stability) for _ in range(4)],
        "memory_stability": {"passed": True},
        "lifecycle_after_unload": {"unloaded_count": 1, "registry_size": 0},
        "scope": {
            "concurrent_singleton_measured": True,
            "mixed_workload_stability_measured": True,
            "retrieval_quality_measured": False,
            "qrels_read": False,
            "production_promotion_authorized": False,
            "release_authorizing": False,
        },
    }
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    return receipt


def test_concurrent_acquisition_constructs_and_warms_one_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = _Model()
    loads: list[object] = []

    def _load(key):
        loads.append(key)
        return model

    monkeypatch.setattr(bge_embedding, "load_local_bge_model", _load)
    with ThreadPoolExecutor(max_workers=8) as executor:
        runtimes = list(
            executor.map(
                lambda _ordinal: get_bge_runtime(model_path=tmp_path, device="cpu"),
                range(8),
            )
        )

    observation = resident_runtime_observation()
    assert len({id(runtime) for runtime in runtimes}) == 1
    assert len(loads) == 1
    assert model.calls == 1
    assert observation["model_load_count"] == 1
    assert observation["registry_size"] == 1


def test_validate_stability_receipt_accepts_complete_proof() -> None:
    validate_stability_receipt(_receipt())


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (
            lambda receipt: receipt["runtime"]["concurrent_acquisition"].update(
                model_load_count=2
            ),
            "model_load_count",
        ),
        (
            lambda receipt: receipt["workload_stability"][0].update(passed=False),
            "workload_stability",
        ),
        (
            lambda receipt: receipt["memory_stability"].update(passed=False),
            "memory_stability",
        ),
    ],
)
def test_validate_stability_receipt_rejects_regressions(mutation, match: str) -> None:
    receipt = _receipt()
    mutation(receipt)
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    with pytest.raises(GpuEmbeddingStabilityError, match=match):
        validate_stability_receipt(receipt)


def test_non_gpu_readiness_is_an_explicit_hardware_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setenv(w6.GPU_STABILITY_OPT_IN, "1")

    assert w6.gpu_stability_integration_readiness() == (
        False,
        "W6_HARDWARE_SKIP_CUDA_UNAVAILABLE",
    )
