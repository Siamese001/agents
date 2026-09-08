from __future__ import annotations

import copy

import pytest

from apps_rg.evals import gpu_embedding_observability_w5 as w5
from apps_rg.evals.gpu_embedding_observability_w5 import (
    GpuEmbeddingObservabilityError,
    RECEIPT_SCHEMA,
    validate_observability_receipt,
)
from apps_rg.runtime.bge_embedding import receipt_sha256


def _receipt() -> dict:
    resident = {
        "local_files_only": True,
        "fallback_used": False,
        "caller_timing": {
            "cold_elapsed_ms": 10.0,
            "warm": {"sample_count": 3, "p50_ms": 4.0, "p95_ms": 5.0},
        },
        "last_encode": {
            "token_lengths_available": True,
            "cuda_memory": {"peak_allocated_mib": 100.0},
        },
    }
    workload = {
        "workload_id": "workload",
        "token_lengths": {"max": 4},
        "vector_proof": {"l2_normalized": True},
    }
    regression = {"workload_id": "workload", "passed": True}
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS",
        "runtime": {
            "device": "cuda:0",
            "local_files_only": True,
            "network_allowed": False,
            "fallback_used": False,
            "model_load_count": 1,
            "resident_runtime_observation": {
                "registry_size": 1,
                "model_load_count": 1,
                "runtimes": [resident],
            },
        },
        "workloads": [copy.deepcopy(workload) for _ in range(4)],
        "regressions_against_w0": [copy.deepcopy(regression) for _ in range(4)],
        "lifecycle_after_unload": {"unloaded_count": 1, "registry_size": 0},
        "scope": {
            "embedding_observability_measured": True,
            "w0_regression_measured": True,
            "retrieval_quality_measured": False,
            "qrels_read": False,
            "production_promotion_authorized": False,
            "release_authorizing": False,
        },
    }
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    return receipt


def test_validate_observability_receipt_accepts_complete_runtime_proof() -> None:
    validate_observability_receipt(_receipt())


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda receipt: receipt["runtime"].update(model_load_count=2), "model_load_count"),
        (lambda receipt: receipt["runtime"].update(device="cpu"), "runtime.device"),
        (lambda receipt: receipt["runtime"].update(fallback_used=True), "fallback_used"),
        (
            lambda receipt: receipt["regressions_against_w0"][0].update(passed=False),
            "regressions_against_w0",
        ),
    ],
)
def test_validate_observability_receipt_rejects_runtime_regression(
    mutation, match: str
) -> None:
    receipt = _receipt()
    mutation(receipt)
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    with pytest.raises(GpuEmbeddingObservabilityError, match=match):
        validate_observability_receipt(receipt)


def test_non_gpu_readiness_is_an_explicit_hardware_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setenv(w5.GPU_INTEGRATION_OPT_IN, "1")

    assert w5.gpu_integration_readiness() == (
        False,
        "W5_HARDWARE_SKIP_CUDA_UNAVAILABLE",
    )
