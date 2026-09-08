"""W6 concurrent-acquisition and mixed-workload stability proof.

W6 consumes the exact W5 receipt, exercises one resident local GPU runtime
across repeated tracked workloads, and writes only beneath ``.runtime``. It
does not open retrieval stores, read QRELs, or authorize production/release.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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
    _vector_proof,
    build_workloads,
    canonical_sha256,
    percentile,
)
from apps_rg.evals.gpu_embedding_observability_w5 import (
    WORKLOAD_BATCH_PROFILES,
    validate_observability_receipt,
)
from apps_rg.runtime.bge_embedding import (
    get_bge_runtime_for_settings,
    receipt_sha256,
    reset_bge_runtime_for_testing,
    resident_runtime_observation,
    resolve_bge_batch_size,
    unload_bge_runtime,
)
from apps_rg.runtime.embedding_settings import resolve_apps_rg_embedding_settings

RECEIPT_SCHEMA = "apps_rg.gpu_embedding_stability_w6.v1"
PROFILE_SCHEMA = "apps_rg.bge_stability_profile.v1"
PROFILE_PATH = Path(
    "src/apps_rg/config/domain_contract/bge_stability_profile.v1.json"
)
DEFAULT_OUTPUT = Path(
    ".runtime/apps_rg/gpu-embedding-stability-w6/current/receipt.json"
)
SOURCE_PATHS = (
    PROFILE_PATH,
    Path("src/apps_rg/config/domain_contract/bge_batch_profile.v1.json"),
    Path("src/apps_rg/config/domain_contract/bge_precision_profile.v1.json"),
    Path("src/apps_rg/runtime/bge_embedding.py"),
    Path("src/apps_rg/evals/gpu_embedding_observability_w5.py"),
    Path("src/apps_rg/evals/gpu_embedding_stability_w6.py"),
)
GPU_STABILITY_OPT_IN = "APPS_RG_RUN_GPU_STABILITY_INTEGRATION"


class GpuEmbeddingStabilityError(RuntimeError):
    """W6 could not prove concurrent or sustained runtime stability."""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GpuEmbeddingStabilityError(f"cannot load JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise GpuEmbeddingStabilityError(f"JSON value is not an object: {path}")
    return value


def _load_profile(root: Path) -> dict[str, Any]:
    profile = _load_json(root / PROFILE_PATH)
    if profile.get("schema_version") != PROFILE_SCHEMA:
        raise GpuEmbeddingStabilityError("W6 stability profile schema mismatch")
    controls = profile.get("stability_controls") or {}
    if controls.get("fallback_allowed") is not False:
        raise GpuEmbeddingStabilityError("W6 fallback control is weakened")
    if controls.get("network_allowed") is not False:
        raise GpuEmbeddingStabilityError("W6 network control is weakened")
    return profile


def resolve_output_path(root: Path, output: Path | str | None) -> Path:
    runtime_root = (root / ".runtime").resolve()
    candidate = root / (Path(output) if output is not None else DEFAULT_OUTPUT)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise GpuEmbeddingStabilityError(
            f"W6 receipt must remain beneath {runtime_root}: {resolved}"
        ) from exc
    return resolved


def gpu_stability_integration_readiness() -> tuple[bool, str]:
    """Return an explicit hardware/opt-in skip without simulating CUDA."""

    try:
        import torch
    except ImportError:
        return False, "W6_HARDWARE_SKIP_TORCH_UNAVAILABLE"
    if not torch.cuda.is_available():
        return False, "W6_HARDWARE_SKIP_CUDA_UNAVAILABLE"
    try:
        settings = resolve_apps_rg_embedding_settings()
    except (OSError, RuntimeError, ValueError):
        return False, "W6_HARDWARE_SKIP_MODEL_SETTINGS_UNAVAILABLE"
    if not settings.embedding_model_resolved or not settings.embedding_model_path:
        return False, "W6_HARDWARE_SKIP_LOCAL_MODEL_UNAVAILABLE"
    if os.environ.get(GPU_STABILITY_OPT_IN) != "1":
        return False, "W6_GPU_STABILITY_OPT_IN_REQUIRED"
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


def _workload_stability(
    *,
    workload_id: str,
    samples: Sequence[Mapping[str, Any]],
    w5_row: Mapping[str, Any],
    controls: Mapping[str, Any],
) -> dict[str, Any]:
    split = len(samples) // 2
    latencies = [float(row["elapsed_ms"]) for row in samples]
    first_p50 = percentile(latencies[:split], 0.50)
    last_p50 = percentile(latencies[split:], 0.50)
    overall_p50 = percentile(latencies, 0.50)
    w5_p50 = float((w5_row.get("warm") or {})["p50_ms"])
    w5_peak = float((w5_row.get("cuda_memory") or {})["peak_allocated_mib"])
    maximum_peak = max(float(row["peak_allocated_mib"]) for row in samples)
    digests = {str(row["vector_sha256"]) for row in samples}
    measurements = {
        "sample_count": len(samples),
        "first_half_p50_ms": round(first_p50, 3),
        "last_half_p50_ms": round(last_p50, 3),
        "overall_p50_ms": round(overall_p50, 3),
        "last_half_to_first_half_p50_ratio": round(last_p50 / first_p50, 4),
        "p50_ratio_to_w5": round(overall_p50 / w5_p50, 4),
        "maximum_peak_allocated_mib": round(maximum_peak, 3),
        "maximum_peak_allocated_ratio_to_w5": round(maximum_peak / w5_peak, 4),
        "unique_vector_digest_count": len(digests),
    }
    gates = {
        "latency_drift": measurements["last_half_to_first_half_p50_ratio"]
        <= float(controls["maximum_last_half_to_first_half_p50_ratio"]),
        "w5_latency": measurements["p50_ratio_to_w5"]
        <= float(controls["maximum_p50_ratio_to_w5"]),
        "w5_peak_allocated": measurements["maximum_peak_allocated_ratio_to_w5"]
        <= float(controls["maximum_peak_allocated_ratio_to_w5"]),
        "vector_digest_stable": len(digests) == 1,
    }
    return {
        "workload_id": workload_id,
        "measurements": measurements,
        "gates": gates,
        "passed": all(gates.values()),
    }


def validate_stability_receipt(
    receipt: Mapping[str, Any], *, repository_root: Path | str | None = None
) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        issues.append("schema_version")
    if receipt.get("status") != "PASS":
        issues.append("status")
    runtime = receipt.get("runtime") or {}
    acquisition = runtime.get("concurrent_acquisition") or {}
    if acquisition.get("unique_runtime_object_count") != 1:
        issues.append("runtime.concurrent_acquisition.unique_runtime_object_count")
    if acquisition.get("model_load_count") != 1:
        issues.append("runtime.concurrent_acquisition.model_load_count")
    if acquisition.get("registry_size") != 1:
        issues.append("runtime.concurrent_acquisition.registry_size")
    if runtime.get("fallback_used") is not False:
        issues.append("runtime.fallback_used")
    if runtime.get("network_allowed") is not False:
        issues.append("runtime.network_allowed")
    stability = receipt.get("workload_stability") or []
    if len(stability) != 4 or not all(row.get("passed") is True for row in stability):
        issues.append("workload_stability")
    memory = receipt.get("memory_stability") or {}
    if memory.get("passed") is not True:
        issues.append("memory_stability")
    if receipt.get("lifecycle_after_unload") != {
        "unloaded_count": 1,
        "registry_size": 0,
    }:
        issues.append("lifecycle_after_unload")
    if receipt.get("scope") != {
        "concurrent_singleton_measured": True,
        "mixed_workload_stability_measured": True,
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
        raise GpuEmbeddingStabilityError(
            "W6 stability receipt invalid: " + ", ".join(issues)
        )


def run_stability_benchmark(
    *,
    repository_root: Path | str,
    output: Path | str | None = None,
    cycles: int | None = None,
) -> tuple[dict[str, Any], Path]:
    root = Path(repository_root).resolve()
    profile = _load_profile(root)
    controls = dict(profile["stability_controls"])
    selected_cycles = cycles or int(controls["minimum_soak_cycles"])
    if selected_cycles < int(controls["minimum_soak_cycles"]):
        raise GpuEmbeddingStabilityError("W6 soak cycles are below the profile minimum")

    baseline_contract = profile["baseline"]
    w5_path = root / str(baseline_contract["receipt_path"])
    w5 = _load_json(w5_path)
    validate_observability_receipt(w5, repository_root=root)
    if w5.get("receipt_sha256") != baseline_contract.get("receipt_sha256"):
        raise GpuEmbeddingStabilityError("W6 W5 baseline digest mismatch")

    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[name] = "1"
    try:
        import torch
    except ImportError as exc:
        raise GpuEmbeddingStabilityError("W6 Torch is unavailable") from exc
    if not torch.cuda.is_available():
        raise GpuEmbeddingStabilityError("W6 requires an available CUDA device")
    torch.cuda.set_device(0)
    settings = resolve_apps_rg_embedding_settings()
    if not settings.embedding_model_resolved or not settings.embedding_model_path:
        raise GpuEmbeddingStabilityError(settings.decisive_reason)

    reset_bge_runtime_for_testing()
    torch.cuda.empty_cache()
    worker_count = int(controls["concurrent_acquisition_workers"])
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        runtimes = list(
            executor.map(
                lambda _ordinal: get_bge_runtime_for_settings(settings),
                range(worker_count),
            )
        )
    runtime_ids = {id(runtime) for runtime in runtimes}
    observation = resident_runtime_observation()
    acquisition = {
        "worker_count": worker_count,
        "unique_runtime_object_count": len(runtime_ids),
        "model_load_count": observation["model_load_count"],
        "registry_size": observation["registry_size"],
        "warmup_completed": all(runtime.warmup_completed for runtime in runtimes),
        "passed": len(runtime_ids) == 1
        and observation["model_load_count"]
        == int(controls["required_model_load_count"])
        and observation["registry_size"]
        == int(controls["required_registry_size"]),
    }
    if not acquisition["passed"]:
        raise GpuEmbeddingStabilityError("W6 concurrent singleton acquisition failed")
    runtime = runtimes[0]

    workloads = build_workloads(root)
    samples: dict[str, list[dict[str, Any]]] = {
        workload.workload_id: [] for workload in workloads
    }
    cycle_end_allocated: list[float] = []
    for cycle in range(selected_cycles):
        for workload in workloads:
            batch_profile = WORKLOAD_BATCH_PROFILES[workload.workload_id]
            batch_size = resolve_bge_batch_size(batch_profile, len(workload.texts))
            torch.cuda.reset_peak_memory_stats(0)
            elapsed_ms, vectors = _timed_encode(
                runtime,
                workload.texts,
                batch_size=batch_size,
                torch=torch,
            )
            proof = _vector_proof(vectors, len(workload.texts))
            samples[workload.workload_id].append(
                {
                    "cycle": cycle + 1,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "texts_per_second": round(
                        len(workload.texts) * 1000.0 / elapsed_ms, 3
                    ),
                    "peak_allocated_mib": round(
                        torch.cuda.max_memory_allocated(0) / 1048576.0, 3
                    ),
                    "allocated_after_mib": round(
                        torch.cuda.memory_allocated(0) / 1048576.0, 3
                    ),
                    "vector_sha256": proof["float32_sha256"],
                    "input_sha256": canonical_sha256(list(workload.texts)),
                    "batch_size": batch_size,
                }
            )
        cycle_end_allocated.append(round(torch.cuda.memory_allocated(0) / 1048576.0, 3))

    w5_rows = {row["workload_id"]: row for row in w5["workloads"]}
    workload_stability = [
        _workload_stability(
            workload_id=workload.workload_id,
            samples=samples[workload.workload_id],
            w5_row=w5_rows[workload.workload_id],
            controls=controls,
        )
        for workload in workloads
    ]
    maximum_growth = max(value - cycle_end_allocated[0] for value in cycle_end_allocated)
    memory_stability = {
        "cycle_end_allocated_mib": cycle_end_allocated,
        "maximum_growth_from_first_cycle_mib": round(maximum_growth, 3),
        "maximum_allowed_growth_mib": float(
            controls["maximum_cycle_end_allocated_growth_mib"]
        ),
        "passed": maximum_growth
        <= float(controls["maximum_cycle_end_allocated_growth_mib"]),
    }
    final_observation = resident_runtime_observation()
    unloaded = unload_bge_runtime(runtime.key)
    lifecycle = resident_runtime_observation()
    all_passed = (
        acquisition["passed"]
        and memory_stability["passed"]
        and all(row["passed"] for row in workload_stability)
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS" if all_passed else "FAIL",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {path.as_posix(): _file_sha256(root / path) for path in SOURCE_PATHS},
        "git": _git_identity(root),
        "baseline": {
            "wave": "W5",
            "receipt_path": str(baseline_contract["receipt_path"]),
            "receipt_sha256": w5["receipt_sha256"],
        },
        "runtime": {
            "device": runtime.key.device,
            "dtype": runtime.key.dtype,
            "backend": runtime.key.backend,
            "gpu": _gpu_identity(torch, runtime.key.device),
            "concurrent_acquisition": acquisition,
            "final_resident_observation": final_observation,
            "network_allowed": False,
            "fallback_allowed": False,
            "fallback_used": False,
        },
        "controls": controls,
        "cycles": selected_cycles,
        "samples": samples,
        "workload_stability": workload_stability,
        "memory_stability": memory_stability,
        "lifecycle_after_unload": {
            "unloaded_count": unloaded,
            "registry_size": lifecycle["registry_size"],
        },
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
    destination = resolve_output_path(root, output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    validate_stability_receipt(receipt, repository_root=root)
    return receipt, destination


__all__ = [
    "GPU_STABILITY_OPT_IN",
    "GpuEmbeddingStabilityError",
    "gpu_stability_integration_readiness",
    "run_stability_benchmark",
    "validate_stability_receipt",
]
