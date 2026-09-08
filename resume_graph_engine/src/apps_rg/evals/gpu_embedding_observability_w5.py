"""W5 observability and W0 regression gates for the resident BGE GPU runtime.

W5 measures the governed embedding workloads against the immutable W0 receipt.
It writes only beneath ``.runtime`` and does not read QRELs, open retrieval
stores, qualify retrieval, or authorize production promotion.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.evals.gpu_embedding_baseline_w0 import (
    _git_identity,
    _gpu_identity,
    _token_length_stats,
    _vector_proof,
    build_workloads,
    canonical_sha256,
    percentile,
    validate_receipt as validate_w0_receipt,
)
from apps_rg.runtime.bge_embedding import (
    get_bge_runtime_for_settings,
    load_bge_precision_profile,
    receipt_sha256,
    reset_bge_runtime_for_testing,
    resolve_bge_batch_size,
    resolve_bge_precision_profile_id,
    resident_runtime_observation,
    unload_bge_runtime,
)
from apps_rg.runtime.embedding_settings import resolve_apps_rg_embedding_settings

RECEIPT_SCHEMA = "apps_rg.gpu_embedding_observability_w5.v1"
PROFILE_SCHEMA = "apps_rg.bge_observability_profile.v1"
DEFAULT_OUTPUT = Path(
    ".runtime/apps_rg/gpu-embedding-observability-w5/current/receipt.json"
)
PROFILE_PATH = Path(
    "src/apps_rg/config/domain_contract/bge_observability_profile.v1.json"
)
SOURCE_PATHS = (
    PROFILE_PATH,
    Path("src/apps_rg/config/domain_contract/bge_batch_profile.v1.json"),
    Path("src/apps_rg/config/domain_contract/bge_precision_profile.v1.json"),
    Path("src/apps_rg/runtime/bge_embedding.py"),
    Path("src/apps_rg/evals/gpu_embedding_baseline_w0.py"),
    Path("src/apps_rg/evals/gpu_embedding_observability_w5.py"),
)
WORKLOAD_BATCH_PROFILES = {
    "frozen_six_query": "c03_projection",
    "whole_resume_eleven_section": "c03_projection",
    "c02_section_retrieval_representative": "c02_section_queries",
    "r1b_projection_representative": "r1b_projection",
}
GPU_INTEGRATION_OPT_IN = "APPS_RG_RUN_GPU_INTEGRATION"


class GpuEmbeddingObservabilityError(RuntimeError):
    """W5 could not prove the governed runtime or regression contract."""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GpuEmbeddingObservabilityError(f"cannot load JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise GpuEmbeddingObservabilityError(f"JSON value is not an object: {path}")
    return value


def _load_profile(root: Path) -> dict[str, Any]:
    profile = _load_json(root / PROFILE_PATH)
    if profile.get("schema_version") != PROFILE_SCHEMA:
        raise GpuEmbeddingObservabilityError("W5 observability profile schema mismatch")
    controls = profile.get("runtime_controls") or {}
    if controls.get("local_files_only") is not True:
        raise GpuEmbeddingObservabilityError("W5 local-only control is weakened")
    if controls.get("network_allowed") is not False:
        raise GpuEmbeddingObservabilityError("W5 network control is weakened")
    if controls.get("fallback_allowed") is not False:
        raise GpuEmbeddingObservabilityError("W5 fallback control is weakened")
    return profile


def resolve_output_path(root: Path, output: Path | str | None) -> Path:
    runtime_root = (root / ".runtime").resolve()
    candidate = root / (Path(output) if output is not None else DEFAULT_OUTPUT)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise GpuEmbeddingObservabilityError(
            f"W5 receipt must remain beneath {runtime_root}: {resolved}"
        ) from exc
    return resolved


def gpu_integration_readiness() -> tuple[bool, str]:
    """Return an explicit skip reason without ever simulating GPU success."""

    try:
        import torch
    except ImportError:
        return False, "W5_HARDWARE_SKIP_TORCH_UNAVAILABLE"
    if not torch.cuda.is_available():
        return False, "W5_HARDWARE_SKIP_CUDA_UNAVAILABLE"
    try:
        settings = resolve_apps_rg_embedding_settings()
    except (OSError, RuntimeError, ValueError):
        return False, "W5_HARDWARE_SKIP_MODEL_SETTINGS_UNAVAILABLE"
    if not settings.embedding_model_resolved or not settings.embedding_model_path:
        return False, "W5_HARDWARE_SKIP_LOCAL_MODEL_UNAVAILABLE"
    if os.environ.get(GPU_INTEGRATION_OPT_IN) != "1":
        return False, "W5_GPU_OPT_IN_REQUIRED"
    return True, "READY"


def _timed_encode(
    runtime: Any,
    texts: Sequence[str],
    *,
    batch_size: int,
    torch: Any,
) -> tuple[float, list[list[float]]]:
    torch.cuda.synchronize()
    started = time.perf_counter()
    vectors = runtime.encode(texts, batch_size=batch_size)
    torch.cuda.synchronize()
    return (time.perf_counter() - started) * 1000.0, vectors


def _regression_row(
    *,
    current: Mapping[str, Any],
    baseline: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    current_p50 = float((current.get("warm") or {})["p50_ms"])
    baseline_p50 = float((baseline.get("warm") or {})["p50_ms"])
    current_tps = float((current.get("warm") or {})["p50_texts_per_second"])
    baseline_tps = float((baseline.get("warm") or {})["p50_texts_per_second"])
    current_peak = float((current.get("cuda_memory") or {})["peak_allocated_mib"])
    baseline_peak = float((baseline.get("cuda_memory") or {})["peak_allocated_mib"])
    comparisons = {
        "input_sha256_equal": current.get("input_sha256")
        == baseline.get("input_sha256"),
        "warm_p50_ratio_to_w0": round(current_p50 / baseline_p50, 4),
        "warm_throughput_ratio_to_w0": round(current_tps / baseline_tps, 4),
        "peak_allocated_ratio_to_w0": round(current_peak / baseline_peak, 4),
    }
    gates = {
        "input_binding": comparisons["input_sha256_equal"],
        "warm_p50": comparisons["warm_p50_ratio_to_w0"]
        <= float(thresholds["maximum_warm_p50_ratio_to_w0"]),
        "warm_throughput": comparisons["warm_throughput_ratio_to_w0"]
        >= float(thresholds["minimum_warm_throughput_ratio_to_w0"]),
        "peak_allocated": comparisons["peak_allocated_ratio_to_w0"]
        <= float(thresholds["maximum_peak_allocated_ratio_to_w0"]),
    }
    return {
        "workload_id": current.get("workload_id"),
        "comparisons": comparisons,
        "gates": gates,
        "passed": all(gates.values()),
    }


def validate_observability_receipt(
    receipt: Mapping[str, Any], *, repository_root: Path | str | None = None
) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        issues.append("schema_version")
    if receipt.get("status") != "PASS":
        issues.append("status")
    runtime = receipt.get("runtime") or {}
    if runtime.get("device") != "cuda:0":
        issues.append("runtime.device")
    if runtime.get("local_files_only") is not True:
        issues.append("runtime.local_files_only")
    if runtime.get("network_allowed") is not False:
        issues.append("runtime.network_allowed")
    if runtime.get("fallback_used") is not False:
        issues.append("runtime.fallback_used")
    if runtime.get("model_load_count") != 1:
        issues.append("runtime.model_load_count")
    observation = runtime.get("resident_runtime_observation") or {}
    if observation.get("registry_size") != 1 or observation.get("model_load_count") != 1:
        issues.append("runtime.resident_runtime_observation")
    resident_rows = observation.get("runtimes") or []
    if len(resident_rows) != 1:
        issues.append("runtime.resident_runtime_count")
    else:
        resident = resident_rows[0]
        if resident.get("local_files_only") is not True:
            issues.append("runtime.resident.local_files_only")
        if resident.get("fallback_used") is not False:
            issues.append("runtime.resident.fallback_used")
        timing = resident.get("caller_timing") or {}
        if timing.get("cold_elapsed_ms") is None:
            issues.append("runtime.resident.cold_timing")
        if ((timing.get("warm") or {}).get("sample_count") or 0) < 1:
            issues.append("runtime.resident.warm_timing")
        last_encode = resident.get("last_encode") or {}
        if last_encode.get("token_lengths_available") is not True:
            issues.append("runtime.resident.token_lengths")
        if last_encode.get("cuda_memory") is None:
            issues.append("runtime.resident.cuda_memory")
    workloads = receipt.get("workloads") or []
    if len(workloads) != 4:
        issues.append("workload_count")
    for row in workloads:
        if not (row.get("vector_proof") or {}).get("l2_normalized"):
            issues.append(f"workload.{row.get('workload_id')}.normalization")
        if ((row.get("token_lengths") or {}).get("max") or 0) < 1:
            issues.append(f"workload.{row.get('workload_id')}.token_lengths")
    regressions = receipt.get("regressions_against_w0") or []
    if len(regressions) != 4 or not all(row.get("passed") is True for row in regressions):
        issues.append("regressions_against_w0")
    lifecycle = receipt.get("lifecycle_after_unload") or {}
    if lifecycle != {"unloaded_count": 1, "registry_size": 0}:
        issues.append("lifecycle_after_unload")
    if receipt.get("scope") != {
        "embedding_observability_measured": True,
        "w0_regression_measured": True,
        "retrieval_quality_measured": False,
        "qrels_read": False,
        "production_promotion_authorized": False,
        "release_authorizing": False,
    }:
        issues.append("scope")
    if receipt_sha256(receipt) != receipt.get("receipt_sha256"):
        issues.append("receipt_sha256")
    if repository_root is not None:
        root = Path(repository_root).resolve()
        for relative, digest in (receipt.get("source") or {}).items():
            path = root / relative
            if not path.is_file() or _file_sha256(path) != digest:
                issues.append(f"source.{relative}")
    if issues:
        raise GpuEmbeddingObservabilityError(
            "W5 observability receipt invalid: " + ", ".join(issues)
        )


def run_observability_benchmark(
    *,
    repository_root: Path | str,
    output: Path | str | None = None,
    repetitions: int = 3,
) -> tuple[dict[str, Any], Path]:
    root = Path(repository_root).resolve()
    profile = _load_profile(root)
    controls = dict(profile["runtime_controls"])
    thresholds = dict(profile["regression_thresholds"])
    if repetitions < int(controls["minimum_warm_repetitions"]):
        raise GpuEmbeddingObservabilityError(
            "W5 requires at least the configured warm repetitions"
        )
    baseline_contract = profile["baseline"]
    baseline_path = root / str(baseline_contract["receipt_path"])
    baseline = _load_json(baseline_path)
    validate_w0_receipt(baseline)
    if baseline.get("receipt_sha256") != baseline_contract.get("receipt_sha256"):
        raise GpuEmbeddingObservabilityError("W5 W0 baseline digest mismatch")

    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[name] = "1"
    try:
        import torch
    except ImportError as exc:
        raise GpuEmbeddingObservabilityError("W5 Torch is unavailable") from exc
    if not torch.cuda.is_available():
        raise GpuEmbeddingObservabilityError("W5 requires an available CUDA device")
    device = str(controls["required_device"])
    torch.cuda.set_device(0)
    gpu = _gpu_identity(torch, device)
    baseline_runtime = baseline["runtime"]
    baseline_gpu = baseline_runtime["gpu"]
    if gpu["name"] != baseline_gpu["name"]:
        raise GpuEmbeddingObservabilityError("W5 GPU model differs from W0")
    if gpu["compute_capability"] != baseline_gpu["compute_capability"]:
        raise GpuEmbeddingObservabilityError("W5 compute capability differs from W0")
    if str(torch.__version__) != baseline_runtime["torch_version"]:
        raise GpuEmbeddingObservabilityError("W5 Torch version differs from W0")

    settings = resolve_apps_rg_embedding_settings()
    if not settings.embedding_model_resolved or not settings.embedding_model_path:
        raise GpuEmbeddingObservabilityError(settings.decisive_reason)
    precision_profile = load_bge_precision_profile()
    precision_profile_id = resolve_bge_precision_profile_id()
    if precision_profile_id != profile["expected_precision_profile_id"]:
        raise GpuEmbeddingObservabilityError("W5 selected precision profile drifted")
    if precision_profile["rollback_profile_id"] != profile[
        "rollback_precision_profile_id"
    ]:
        raise GpuEmbeddingObservabilityError("W5 rollback precision profile drifted")

    reset_bge_runtime_for_testing()
    torch.cuda.empty_cache()
    runtime = get_bge_runtime_for_settings(settings)
    workloads = build_workloads(root)
    current_rows: list[dict[str, Any]] = []
    for workload in workloads:
        batch_profile = WORKLOAD_BATCH_PROFILES[workload.workload_id]
        batch_size = resolve_bge_batch_size(batch_profile, len(workload.texts))
        torch.cuda.reset_peak_memory_stats(0)
        before_allocated = torch.cuda.memory_allocated(0)
        before_reserved = torch.cuda.memory_reserved(0)
        cold_ms, cold_vectors = _timed_encode(
            runtime,
            workload.texts,
            batch_size=batch_size,
            torch=torch,
        )
        vector_proof = _vector_proof(cold_vectors, len(workload.texts))
        samples: list[float] = []
        digests: list[str] = []
        for _ in range(repetitions):
            elapsed_ms, vectors = _timed_encode(
                runtime,
                workload.texts,
                batch_size=batch_size,
                torch=torch,
            )
            samples.append(elapsed_ms)
            digests.append(_vector_proof(vectors, len(workload.texts))["float32_sha256"])
        p50 = percentile(samples, 0.50)
        p95 = percentile(samples, 0.95)
        text_lengths = [len(text) for text in workload.texts]
        current_rows.append(
            {
                "workload_id": workload.workload_id,
                "input_sha256": canonical_sha256(list(workload.texts)),
                "text_count": len(workload.texts),
                "batch_profile_id": batch_profile,
                "batch_size": batch_size,
                "character_lengths": {
                    "min": min(text_lengths),
                    "p50": int(percentile(text_lengths, 0.50)),
                    "p95": int(percentile(text_lengths, 0.95)),
                    "max": max(text_lengths),
                },
                "token_lengths": _token_length_stats(runtime.model, workload.texts),
                "cold_first_pass": {
                    "elapsed_ms": round(cold_ms, 3),
                    "texts_per_second": round(len(workload.texts) * 1000.0 / cold_ms, 3),
                },
                "warm": {
                    "repetitions": repetitions,
                    "samples_ms": [round(value, 3) for value in samples],
                    "p50_ms": round(p50, 3),
                    "p95_ms": round(p95, 3),
                    "p50_texts_per_second": round(
                        len(workload.texts) * 1000.0 / p50, 3
                    ),
                    "p95_texts_per_second": round(
                        len(workload.texts) * 1000.0 / p95, 3
                    ),
                    "vector_digest_stable": len(set(digests)) == 1,
                },
                "cuda_memory": {
                    "before_allocated_mib": round(before_allocated / 1048576.0, 3),
                    "before_reserved_mib": round(before_reserved / 1048576.0, 3),
                    "peak_allocated_mib": round(
                        torch.cuda.max_memory_allocated(0) / 1048576.0, 3
                    ),
                    "peak_reserved_mib": round(
                        torch.cuda.max_memory_reserved(0) / 1048576.0, 3
                    ),
                },
                "vector_proof": vector_proof,
            }
        )

    runtime_observation = resident_runtime_observation()
    baseline_rows = {row["workload_id"]: row for row in baseline["workloads"]}
    regressions = [
        _regression_row(
            current=row,
            baseline=baseline_rows[row["workload_id"]],
            thresholds=thresholds,
        )
        for row in current_rows
    ]
    unloaded = unload_bge_runtime(runtime.key)
    lifecycle = resident_runtime_observation()
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS" if all(row["passed"] for row in regressions) else "FAIL",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {path.as_posix(): _file_sha256(root / path) for path in SOURCE_PATHS},
        "git": _git_identity(root),
        "baseline": {
            "wave": "W0",
            "receipt_path": str(baseline_contract["receipt_path"]),
            "receipt_sha256": baseline["receipt_sha256"],
            "gpu": baseline_gpu,
        },
        "runtime": {
            "device": device,
            "gpu": gpu,
            "torch_version": str(torch.__version__),
            "dtype": runtime.key.dtype,
            "backend": runtime.key.backend,
            "precision_profile_id": precision_profile_id,
            "rollback_precision_profile_id": profile["rollback_precision_profile_id"],
            "local_files_only": True,
            "network_allowed": False,
            "fallback_allowed": False,
            "fallback_used": False,
            "model_load_count": runtime_observation["model_load_count"],
            "resident_runtime_observation": runtime_observation,
        },
        "model": {
            "model_id": baseline["model"]["model_id"],
            "revision": baseline["model"]["revision"],
            "dimension": baseline["model"]["dimension"],
            "normalization": baseline["model"]["normalization"],
        },
        "thresholds": thresholds,
        "workloads": current_rows,
        "regressions_against_w0": regressions,
        "lifecycle_after_unload": {
            "unloaded_count": unloaded,
            "registry_size": lifecycle["registry_size"],
        },
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
    destination = resolve_output_path(root, output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    validate_observability_receipt(receipt, repository_root=root)
    return receipt, destination


__all__ = [
    "GPU_INTEGRATION_OPT_IN",
    "GpuEmbeddingObservabilityError",
    "gpu_integration_readiness",
    "run_observability_benchmark",
    "validate_observability_receipt",
]
