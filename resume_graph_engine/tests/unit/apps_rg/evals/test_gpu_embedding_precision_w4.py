from __future__ import annotations

import copy

import pytest

from apps_rg.evals.gpu_embedding_precision_w4 import (
    GpuEmbeddingPrecisionError,
    PROFILE_ORDER,
    RECEIPT_SCHEMA,
    recommend_precision_profile,
    validate_precision_receipt,
)
from apps_rg.runtime.bge_embedding import receipt_sha256


def _receipt() -> dict:
    rank = {
        "query_count": 6,
        "exact_full_rank_query_count": 6,
    }
    profiles = {
        profile_id: {
            "fallback_used": False,
            "network_used": False,
            "lifecycle_after_unload": {"unloaded_count": 1, "registry_size": 0},
        }
        for profile_id in PROFILE_ORDER
    }
    comparisons = {
        profile_id: {"rank_proxy": copy.deepcopy(rank), "eligible": True}
        for profile_id in PROFILE_ORDER
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS",
        "profiles": profiles,
        "comparisons_to_fp32": comparisons,
        "selection": {
            "recommended_profile_id": "fp16_candidate",
            "rollback_profile_id": "fp32_control",
        },
        "scope": {
            "embedding_precision_measured": True,
            "rank_proxy_measured": True,
            "retrieval_quality_measured": False,
            "production_promotion_authorized": False,
            "release_authorizing": False,
        },
    }
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    return receipt


def test_validate_precision_receipt_accepts_technical_selection() -> None:
    validate_precision_receipt(_receipt())


def test_validate_precision_receipt_rejects_ineligible_selection() -> None:
    receipt = _receipt()
    receipt["comparisons_to_fp32"]["fp16_candidate"]["eligible"] = False
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    with pytest.raises(GpuEmbeddingPrecisionError, match="ineligible"):
        validate_precision_receipt(receipt)


def test_validate_precision_receipt_rejects_non_exact_fp32_control() -> None:
    receipt = _receipt()
    receipt["comparisons_to_fp32"]["fp32_control"]["rank_proxy"][
        "exact_full_rank_query_count"
    ] = 5
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    with pytest.raises(GpuEmbeddingPrecisionError, match="FP32 control ranks"):
        validate_precision_receipt(receipt)


def test_recommendation_uses_fidelity_inside_throughput_tie_band() -> None:
    results = {
        "fp16_candidate": {"aggregate": {"p50_texts_per_second": 110.0}},
        "bf16_candidate": {"aggregate": {"p50_texts_per_second": 111.0}},
    }
    comparisons = {
        "fp16_candidate": {
            "eligible": True,
            "same_index_cosine": {"minimum": 0.9999},
            "rank_proxy": {"exact_top10_order_query_count": 3},
        },
        "bf16_candidate": {
            "eligible": True,
            "same_index_cosine": {"minimum": 0.9991},
            "rank_proxy": {"exact_top10_order_query_count": 1},
        },
    }

    assert (
        recommend_precision_profile(
            profile_results=results,
            comparisons=comparisons,
            controls={"maximum_throughput_tie_gap_ratio": 0.02},
        )
        == "fp16_candidate"
    )
