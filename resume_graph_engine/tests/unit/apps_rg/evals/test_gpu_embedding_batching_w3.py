from __future__ import annotations

import copy

import pytest

from apps_rg.evals.gpu_embedding_batching_w3 import (
    GpuEmbeddingBatchingError,
    RECEIPT_SCHEMA,
    validate_batching_receipt,
)
from apps_rg.runtime.bge_embedding import receipt_sha256


def _receipt() -> dict:
    row = {
        "benchmark_id": "path",
        "bounded_batch": {"material_speedup": True},
        "ordered_vector_equivalence": {
            "cardinality_preserved": True,
            "minimum_same_index_cosine": 1.0,
        },
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS",
        "benchmarks": [copy.deepcopy(row) for _ in range(3)],
        "runtime": {"fallback_used": False, "model_load_count": 1},
        "scope": {
            "embedding_throughput_measured": True,
            "retrieval_quality_measured": False,
            "production_promotion_authorized": False,
            "release_authorizing": False,
        },
    }
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    return receipt


def test_validate_batching_receipt_accepts_bounded_non_authoritative_proof() -> None:
    validate_batching_receipt(_receipt())


def test_validate_batching_receipt_rejects_missing_material_speedup() -> None:
    receipt = _receipt()
    receipt["benchmarks"][0]["bounded_batch"]["material_speedup"] = False
    receipt["receipt_sha256"] = receipt_sha256(receipt)

    with pytest.raises(GpuEmbeddingBatchingError, match="throughput improvement"):
        validate_batching_receipt(receipt)


def test_validate_batching_receipt_rejects_order_drift() -> None:
    receipt = _receipt()
    receipt["benchmarks"][0]["ordered_vector_equivalence"][
        "minimum_same_index_cosine"
    ] = 0.5
    receipt["receipt_sha256"] = receipt_sha256(receipt)

    with pytest.raises(GpuEmbeddingBatchingError, match="stable-order proof"):
        validate_batching_receipt(receipt)
