"""W4 precision selection for the governed resident BGE-M3 GPU runtime.

This benchmark compares matched FP32, FP16, and BF16 embedding execution.  Its
rank comparison is a technical proxy over tracked W0 inputs; it is not a QREL
evaluation and cannot qualify retrieval or authorize promotion.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from apps_rg.evals.gpu_embedding_baseline_w0 import (
    EmbeddingWorkload,
    build_workloads,
    canonical_sha256,
    percentile,
)
from apps_rg.runtime.bge_embedding import (
    get_bge_runtime,
    load_bge_precision_profile,
    receipt_sha256,
    reset_bge_runtime_for_testing,
    resolve_bge_batch_size,
    unload_bge_runtime,
)
from apps_rg.runtime.embedding_settings import resolve_apps_rg_embedding_settings

RECEIPT_SCHEMA = "apps_rg.gpu_embedding_precision_w4.v1"
DEFAULT_OUTPUT = Path(".runtime/apps_rg/gpu-embedding-precision-w4/current/receipt.json")
PROFILE_ORDER = ("fp32_control", "fp16_candidate", "bf16_candidate")
WORKLOAD_BATCH_PROFILES = {
    "frozen_six_query": "c03_projection",
    "whole_resume_eleven_section": "c03_projection",
    "c02_section_retrieval_representative": "c02_section_queries",
    "r1b_projection_representative": "r1b_projection",
}
SOURCE_PATHS = (
    Path("src/apps_rg/config/domain_contract/bge_precision_profile.v1.json"),
    Path("src/apps_rg/config/domain_contract/bge_batch_profile.v1.json"),
    Path("src/apps_rg/runtime/bge_embedding.py"),
    Path("src/apps_rg/evals/gpu_embedding_baseline_w0.py"),
    Path("src/apps_rg/evals/gpu_embedding_precision_w4.py"),
)


class GpuEmbeddingPrecisionError(RuntimeError):
    """The W4 precision benchmark or selection contract failed."""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_output_path(root: Path, output: Path | str | None) -> Path:
    runtime_root = (root / ".runtime").resolve()
    candidate = root / (Path(output) if output is not None else DEFAULT_OUTPUT)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise GpuEmbeddingPrecisionError(
            f"W4 receipt must remain beneath {runtime_root}: {resolved}"
        ) from exc
    return resolved


def _synchronize(torch: Any, device: str) -> None:
    if device.startswith("cuda"):
        torch.cuda.synchronize()


def _memory_mib(value: int | float) -> float:
    return round(float(value) / (1024.0 * 1024.0), 3)


def _vector_proof(vectors: Sequence[Sequence[float]]) -> dict[str, Any]:
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim != 2 or array.shape[1] != 1024 or not np.isfinite(array).all():
        raise GpuEmbeddingPrecisionError(
            f"W4 vector contract failed: shape={array.shape}"
        )
    norm_errors = np.abs(np.linalg.norm(array, axis=1) - 1.0)
    maximum = float(np.max(norm_errors))
    if maximum > 1e-6:
        raise GpuEmbeddingPrecisionError(
            f"W4 vector post-normalization drifted: {maximum}"
        )
    return {
        "vector_count": int(array.shape[0]),
        "dimension": int(array.shape[1]),
        "finite": True,
        "l2_normalized": True,
        "maximum_l2_norm_error": round(maximum, 8),
    }


def _timed_encode(
    runtime: Any,
    workload: EmbeddingWorkload,
    *,
    batch_size: int,
    torch: Any,
) -> tuple[float, list[list[float]]]:
    _synchronize(torch, runtime.key.device)
    started = time.perf_counter()
    vectors = runtime.encode(workload.texts, batch_size=batch_size)
    _synchronize(torch, runtime.key.device)
    return (time.perf_counter() - started) * 1000.0, vectors


def _run_profile(
    *,
    profile_id: str,
    dtype: str,
    model_path: str,
    workloads: Sequence[EmbeddingWorkload],
    repetitions: int,
    torch: Any,
) -> tuple[dict[str, Any], np.ndarray]:
    reset_bge_runtime_for_testing()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    runtime = get_bge_runtime(
        model_path=model_path,
        device="cuda:0",
        dtype=dtype,
    )
    _synchronize(torch, runtime.key.device)
    load_and_warm_ms = (time.perf_counter() - load_started) * 1000.0

    rows: list[dict[str, Any]] = []
    ordered_vectors: list[list[float]] = []
    for workload in workloads:
        batch_profile = WORKLOAD_BATCH_PROFILES[workload.workload_id]
        batch_size = resolve_bge_batch_size(batch_profile, len(workload.texts))
        _timed_encode(
            runtime,
            workload,
            batch_size=batch_size,
            torch=torch,
        )
        samples: list[float] = []
        vectors: list[list[float]] = []
        for _ in range(repetitions):
            elapsed, vectors = _timed_encode(
                runtime,
                workload,
                batch_size=batch_size,
                torch=torch,
            )
            samples.append(elapsed)
        proof = _vector_proof(vectors)
        ordered_vectors.extend(vectors)
        p50 = percentile(samples, 0.50)
        rows.append(
            {
                "workload_id": workload.workload_id,
                "input_sha256": canonical_sha256(list(workload.texts)),
                "text_count": len(workload.texts),
                "batch_size": batch_size,
                "samples_ms": [round(value, 3) for value in samples],
                "p50_ms": round(p50, 3),
                "p95_ms": round(percentile(samples, 0.95), 3),
                "p50_texts_per_second": round(
                    len(workload.texts) * 1000.0 / p50, 3
                ),
                "vector_proof": proof,
            }
        )

    total_texts = sum(row["text_count"] for row in rows)
    total_p50_ms = sum(row["p50_ms"] for row in rows)
    observation = runtime.observation()
    peak_allocated = _memory_mib(torch.cuda.max_memory_allocated())
    peak_reserved = _memory_mib(torch.cuda.max_memory_reserved())
    unloaded = unload_bge_runtime(runtime.key)
    return (
        {
            "profile_id": profile_id,
            "dtype": dtype,
            "backend": runtime.key.backend,
            "model_load_and_warm_ms": round(load_and_warm_ms, 3),
            "aggregate": {
                "text_count": total_texts,
                "sum_workload_p50_ms": round(total_p50_ms, 3),
                "p50_texts_per_second": round(
                    total_texts * 1000.0 / total_p50_ms, 3
                ),
            },
            "cuda_peak": {
                "allocated_mib": peak_allocated,
                "reserved_mib": peak_reserved,
            },
            "runtime_observation": observation,
            "workloads": rows,
            "fallback_used": False,
            "network_used": False,
            "lifecycle_after_unload": {
                "unloaded_count": unloaded,
                "registry_size": 0,
            },
        },
        np.asarray(ordered_vectors, dtype=np.float32),
    )


def _rankings(
    vectors: np.ndarray, *, query_count: int
) -> tuple[list[list[int]], np.ndarray]:
    queries = vectors[:query_count]
    documents = vectors[query_count:]
    scores = queries @ documents.T
    document_ids = np.arange(documents.shape[0])
    rankings = [
        np.lexsort((document_ids, -row)).astype(int).tolist() for row in scores
    ]
    return rankings, scores


def _precision_comparison(
    control: np.ndarray,
    candidate: np.ndarray,
    *,
    query_count: int,
    throughput_speedup_ratio: float,
    peak_allocated_mib: float,
    controls: Mapping[str, Any],
) -> dict[str, Any]:
    if control.shape != candidate.shape or control.shape[1] != 1024:
        raise GpuEmbeddingPrecisionError(
            f"W4 precision shape mismatch: {control.shape} != {candidate.shape}"
        )
    cosine = np.sum(control * candidate, axis=1) / (
        np.linalg.norm(control, axis=1) * np.linalg.norm(candidate, axis=1)
    )
    control_ranks, _control_scores = _rankings(control, query_count=query_count)
    candidate_ranks, _candidate_scores = _rankings(
        candidate, query_count=query_count
    )
    exact_full = 0
    exact_top10_order = 0
    equal_top10_sets = 0
    top10_overlaps: list[float] = []
    maximum_displacement = 0
    per_query: list[dict[str, Any]] = []
    for index, (expected, observed) in enumerate(
        zip(control_ranks, candidate_ranks, strict=True)
    ):
        exact_full += expected == observed
        exact_top10_order += expected[:10] == observed[:10]
        expected_set = set(expected[:10])
        observed_set = set(observed[:10])
        set_equal = expected_set == observed_set
        equal_top10_sets += set_equal
        overlap = len(expected_set & observed_set) / len(expected_set)
        top10_overlaps.append(overlap)
        positions = {doc_id: rank for rank, doc_id in enumerate(observed)}
        displacement = max(
            abs(rank - positions[doc_id]) for rank, doc_id in enumerate(expected)
        )
        maximum_displacement = max(maximum_displacement, displacement)
        per_query.append(
            {
                "query_ordinal": index,
                "full_rank_exact": expected == observed,
                "top10_order_exact": expected[:10] == observed[:10],
                "top10_set_equal": set_equal,
                "top10_overlap": round(overlap, 6),
                "maximum_rank_displacement": displacement,
            }
        )
    minimum_cosine = float(np.min(cosine))
    all_top10_sets_equal = equal_top10_sets == query_count
    reasons: list[str] = []
    if throughput_speedup_ratio < float(
        controls["minimum_throughput_speedup_ratio"]
    ):
        reasons.append("THROUGHPUT_GATE")
    if minimum_cosine < float(controls["minimum_same_index_cosine"]):
        reasons.append("COSINE_GATE")
    if controls["require_all_top10_sets_equal"] and not all_top10_sets_equal:
        reasons.append("TOP10_SET_GATE")
    if peak_allocated_mib > float(controls["measured_vram_ceiling_mib"]):
        reasons.append("VRAM_GATE")
    return {
        "throughput_speedup_ratio": round(throughput_speedup_ratio, 3),
        "same_index_cosine": {
            "minimum": round(minimum_cosine, 8),
            "p50": round(float(np.median(cosine)), 8),
            "maximum_absolute_delta": round(
                float(np.max(np.abs(control - candidate))), 8
            ),
        },
        "rank_proxy": {
            "query_count": query_count,
            "document_count": int(control.shape[0] - query_count),
            "exact_full_rank_query_count": exact_full,
            "exact_top10_order_query_count": exact_top10_order,
            "equal_top10_set_query_count": equal_top10_sets,
            "all_top10_sets_equal": all_top10_sets_equal,
            "mean_top10_overlap": round(float(np.mean(top10_overlaps)), 6),
            "maximum_rank_displacement": maximum_displacement,
            "per_query": per_query,
        },
        "eligible": not reasons,
        "ineligible_reasons": reasons,
    }


def validate_precision_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("status") != "PASS":
        raise GpuEmbeddingPrecisionError("W4 receipt status or schema mismatch")
    profiles = receipt.get("profiles") or {}
    comparisons = receipt.get("comparisons_to_fp32") or {}
    if tuple(profiles) != PROFILE_ORDER or tuple(comparisons) != PROFILE_ORDER:
        raise GpuEmbeddingPrecisionError("W4 precision profile inventory mismatch")
    fp32_rank = (comparisons["fp32_control"].get("rank_proxy") or {})
    if fp32_rank.get("exact_full_rank_query_count") != fp32_rank.get("query_count"):
        raise GpuEmbeddingPrecisionError("W4 FP32 control ranks are not exact")
    for profile_id, row in profiles.items():
        if row.get("fallback_used") is not False or row.get("network_used") is not False:
            raise GpuEmbeddingPrecisionError(
                f"W4 fallback/network boundary changed: {profile_id}"
            )
        if row.get("lifecycle_after_unload") != {
            "unloaded_count": 1,
            "registry_size": 0,
        }:
            raise GpuEmbeddingPrecisionError(
                f"W4 lifecycle proof failed: {profile_id}"
            )
    selection = receipt.get("selection") or {}
    selected = selection.get("recommended_profile_id")
    if selected not in profiles or selection.get("rollback_profile_id") != "fp32_control":
        raise GpuEmbeddingPrecisionError("W4 selection or rollback profile is invalid")
    if selected != "fp32_control" and comparisons[selected].get("eligible") is not True:
        raise GpuEmbeddingPrecisionError("W4 selected an ineligible candidate")
    if receipt.get("scope") != {
        "embedding_precision_measured": True,
        "rank_proxy_measured": True,
        "retrieval_quality_measured": False,
        "production_promotion_authorized": False,
        "release_authorizing": False,
    }:
        raise GpuEmbeddingPrecisionError("W4 scope boundary mismatch")
    if receipt_sha256(receipt) != receipt.get("receipt_sha256"):
        raise GpuEmbeddingPrecisionError("W4 receipt digest mismatch")


def recommend_precision_profile(
    *,
    profile_results: Mapping[str, Any],
    comparisons: Mapping[str, Any],
    controls: Mapping[str, Any],
) -> str:
    eligible = [
        profile_id
        for profile_id in PROFILE_ORDER[1:]
        if comparisons[profile_id]["eligible"]
    ]
    if not eligible:
        return "fp32_control"
    throughput = {
        profile_id: float(
            profile_results[profile_id]["aggregate"]["p50_texts_per_second"]
        )
        for profile_id in eligible
    }
    fastest = max(throughput.values())
    tie_gap = float(controls["maximum_throughput_tie_gap_ratio"])
    competitive = [
        profile_id
        for profile_id in eligible
        if throughput[profile_id] >= fastest * (1.0 - tie_gap)
    ]
    return max(
        competitive,
        key=lambda profile_id: (
            float(comparisons[profile_id]["same_index_cosine"]["minimum"]),
            int(
                comparisons[profile_id]["rank_proxy"][
                    "exact_top10_order_query_count"
                ]
            ),
            throughput[profile_id],
        ),
    )


def run_precision_benchmark(
    *,
    repository_root: Path | str,
    output: Path | str | None = None,
    repetitions: int = 3,
    require_config_match: bool = True,
) -> tuple[dict[str, Any], Path]:
    if repetitions < 3:
        raise GpuEmbeddingPrecisionError("W4 requires at least three repetitions")
    root = Path(repository_root).resolve()
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[name] = "1"
    try:
        import torch
    except ImportError as exc:
        raise GpuEmbeddingPrecisionError("Torch is unavailable") from exc
    if not torch.cuda.is_available():
        raise GpuEmbeddingPrecisionError("W4 requires an available CUDA device")
    torch.cuda.set_device(0)
    settings = resolve_apps_rg_embedding_settings()
    if not settings.embedding_model_resolved or not settings.embedding_model_path:
        raise GpuEmbeddingPrecisionError(settings.decisive_reason)

    precision_profile = load_bge_precision_profile()
    controls = dict(precision_profile["selection_controls"])
    workloads = build_workloads(root)
    query_count = len(workloads[0].texts)
    profile_results: dict[str, Any] = {}
    profile_vectors: dict[str, np.ndarray] = {}
    for profile_id in PROFILE_ORDER:
        dtype = str(precision_profile["profiles"][profile_id]["dtype"])
        result, vectors = _run_profile(
            profile_id=profile_id,
            dtype=dtype,
            model_path=str(settings.embedding_model_path),
            workloads=workloads,
            repetitions=repetitions,
            torch=torch,
        )
        profile_results[profile_id] = result
        profile_vectors[profile_id] = vectors

    fp32_throughput = float(
        profile_results["fp32_control"]["aggregate"]["p50_texts_per_second"]
    )
    comparisons: dict[str, Any] = {}
    for profile_id in PROFILE_ORDER:
        row = profile_results[profile_id]
        speedup = float(row["aggregate"]["p50_texts_per_second"]) / fp32_throughput
        comparisons[profile_id] = _precision_comparison(
            profile_vectors["fp32_control"],
            profile_vectors[profile_id],
            query_count=query_count,
            throughput_speedup_ratio=speedup,
            peak_allocated_mib=float(row["cuda_peak"]["allocated_mib"]),
            controls=controls,
        )
    comparisons["fp32_control"]["eligible"] = True
    comparisons["fp32_control"]["ineligible_reasons"] = []

    eligible_candidates = [
        profile_id
        for profile_id in PROFILE_ORDER[1:]
        if comparisons[profile_id]["eligible"]
    ]
    recommended = recommend_precision_profile(
        profile_results=profile_results,
        comparisons=comparisons,
        controls=controls,
    )
    configured = str(precision_profile["selected_profile_id"])
    matches = configured == recommended
    if require_config_match and not matches:
        raise GpuEmbeddingPrecisionError(
            f"W4 configured profile {configured} != measured recommendation {recommended}"
        )

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {path.as_posix(): _file_sha256(root / path) for path in SOURCE_PATHS},
        "runtime": {
            "device": "cuda:0",
            "gpu_name": torch.cuda.get_device_name(0),
            "offline": True,
            "fallback_allowed": False,
            "network_allowed": False,
        },
        "controls": controls,
        "comparison_corpus": {
            "ordered_workload_ids": [row.workload_id for row in workloads],
            "input_sha256": canonical_sha256(
                [text for row in workloads for text in row.texts]
            ),
            "query_source_workload_id": workloads[0].workload_id,
            "query_count": query_count,
            "document_count": sum(len(row.texts) for row in workloads[1:]),
            "technical_proxy_only": True,
        },
        "profiles": profile_results,
        "comparisons_to_fp32": comparisons,
        "selection": {
            "recommended_profile_id": recommended,
            "configured_profile_id": configured,
            "configuration_matches_recommendation": matches,
            "rollback_profile_id": str(precision_profile["rollback_profile_id"]),
            "eligible_candidate_profile_ids": eligible_candidates,
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
    validate_precision_receipt(receipt)
    destination = resolve_output_path(root, output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt, destination


__all__ = [
    "GpuEmbeddingPrecisionError",
    "recommend_precision_profile",
    "run_precision_benchmark",
    "validate_precision_receipt",
]
