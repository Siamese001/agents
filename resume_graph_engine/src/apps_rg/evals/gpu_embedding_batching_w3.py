"""W3 benchmark for bounded BGE-M3 production batching on the current GPU.

The benchmark reads the tracked W0 workload constructors, uses the canonical
W2 resident runtime, and writes only a non-authoritative receipt beneath
``.runtime``.  It does not open retrieval stores or read human judgments.
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
    get_bge_runtime_for_settings,
    receipt_sha256,
    reset_bge_runtime_for_testing,
    resident_runtime_observation,
    resolve_bge_batch_size,
    unload_bge_runtime,
)
from apps_rg.runtime.embedding_settings import resolve_apps_rg_embedding_settings

RECEIPT_SCHEMA = "apps_rg.gpu_embedding_batching_w3.v1"
DEFAULT_OUTPUT = Path(".runtime/apps_rg/gpu-embedding-batching-w3/current/receipt.json")
MINIMUM_MATERIAL_SPEEDUP = 1.25
MINIMUM_ORDERED_VECTOR_COSINE = 0.99999
SOURCE_PATHS = (
    Path("src/apps_rg/config/domain_contract/bge_batch_profile.v1.json"),
    Path("src/apps_rg/runtime/bge_embedding.py"),
    Path("src/apps_rg/runtime/bindings/c0_binding.py"),
    Path("src/apps_rg/runtime/c0/c02_fact_vector_ingest.py"),
    Path("src/apps_rg/cache/r1b_bge_embedding.py"),
    Path("src/apps_rg/evals/gpu_embedding_batching_w3.py"),
)


class GpuEmbeddingBatchingError(RuntimeError):
    """The W3 throughput, order, or receipt contract was not satisfied."""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_output_path(root: Path, output: Path | str | None) -> Path:
    runtime_root = (root / ".runtime").resolve()
    candidate = root / (Path(output) if output is not None else DEFAULT_OUTPUT)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise GpuEmbeddingBatchingError(
            f"W3 receipt must remain beneath {runtime_root}: {resolved}"
        ) from exc
    return resolved


def _cuda_index(device: str) -> int:
    return int(device.split(":", 1)[1]) if ":" in device else 0


def _synchronize(torch: Any, device: str) -> None:
    if device.startswith("cuda"):
        torch.cuda.synchronize(_cuda_index(device))


def _memory_mib(value: int | float) -> float:
    return round(float(value) / (1024.0 * 1024.0), 3)


def _timed_encode(
    runtime: Any,
    texts: Sequence[str],
    *,
    batch_size: int,
    torch: Any,
    device: str,
) -> tuple[float, list[list[float]]]:
    _synchronize(torch, device)
    started = time.perf_counter()
    vectors = runtime.encode(texts, batch_size=batch_size)
    _synchronize(torch, device)
    return (time.perf_counter() - started) * 1000.0, vectors


def _timed_prior_loop(
    runtime: Any,
    texts: Sequence[str],
    *,
    torch: Any,
    device: str,
) -> tuple[float, list[list[float]]]:
    _synchronize(torch, device)
    started = time.perf_counter()
    vectors = [runtime.encode([text], batch_size=1)[0] for text in texts]
    _synchronize(torch, device)
    return (time.perf_counter() - started) * 1000.0, vectors


def _ordered_vector_equivalence(
    control: Sequence[Sequence[float]], candidate: Sequence[Sequence[float]]
) -> dict[str, Any]:
    left = np.asarray(control, dtype=np.float32)
    right = np.asarray(candidate, dtype=np.float32)
    if left.shape != right.shape or left.ndim != 2 or left.shape[1] != 1024:
        raise GpuEmbeddingBatchingError(
            f"W3 ordered vector shape changed: {left.shape} != {right.shape}"
        )
    cosine = np.sum(left * right, axis=1) / (
        np.linalg.norm(left, axis=1) * np.linalg.norm(right, axis=1)
    )
    proof = {
        "cardinality_preserved": left.shape[0] == right.shape[0],
        "dimension": int(left.shape[1]),
        "minimum_same_index_cosine": round(float(np.min(cosine)), 8),
        "maximum_absolute_delta": round(float(np.max(np.abs(left - right))), 8),
    }
    if proof["minimum_same_index_cosine"] < MINIMUM_ORDERED_VECTOR_COSINE:
        raise GpuEmbeddingBatchingError(
            "W3 batched vectors did not preserve stable same-index output"
        )
    return proof


def _candidate_batch_sizes(item_count: int, selected: int) -> list[int]:
    candidates = {1, selected, item_count}
    value = 2
    while value < item_count:
        candidates.add(value)
        value *= 2
    return sorted(min(item_count, candidate) for candidate in candidates)


def _benchmark_workload(
    *,
    runtime: Any,
    workload: EmbeddingWorkload,
    workload_profile_id: str,
    benchmark_id: str,
    repetitions: int,
    torch: Any,
    device: str,
    source_shape: str,
) -> dict[str, Any]:
    texts = list(workload.texts)
    selected = resolve_bge_batch_size(workload_profile_id, len(texts))
    cuda_index = _cuda_index(device)

    # Warm every measured path before collecting samples.
    _timed_prior_loop(runtime, texts, torch=torch, device=device)
    _timed_encode(
        runtime,
        texts,
        batch_size=selected,
        torch=torch,
        device=device,
    )

    control_samples: list[float] = []
    batch_samples: list[float] = []
    control_vectors: list[list[float]] = []
    batch_vectors: list[list[float]] = []
    torch.cuda.reset_peak_memory_stats(cuda_index)
    for _ in range(repetitions):
        control_elapsed, control_vectors = _timed_prior_loop(
            runtime, texts, torch=torch, device=device
        )
        batch_elapsed, batch_vectors = _timed_encode(
            runtime,
            texts,
            batch_size=selected,
            torch=torch,
            device=device,
        )
        control_samples.append(control_elapsed)
        batch_samples.append(batch_elapsed)

    control_p50 = percentile(control_samples, 0.50)
    batch_p50 = percentile(batch_samples, 0.50)
    speedup = control_p50 / batch_p50

    sweep: list[dict[str, Any]] = []
    for candidate in _candidate_batch_sizes(len(texts), selected):
        samples = [
            _timed_encode(
                runtime,
                texts,
                batch_size=candidate,
                torch=torch,
                device=device,
            )[0]
            for _ in range(repetitions)
        ]
        p50 = percentile(samples, 0.50)
        sweep.append(
            {
                "batch_size": candidate,
                "samples_ms": [round(value, 3) for value in samples],
                "p50_ms": round(p50, 3),
                "p50_texts_per_second": round(len(texts) * 1000.0 / p50, 3),
            }
        )

    return {
        "benchmark_id": benchmark_id,
        "workload_profile_id": workload_profile_id,
        "source_workload_id": workload.workload_id,
        "source_shape": source_shape,
        "text_count": len(texts),
        "selected_batch_size": selected,
        "input_sha256": canonical_sha256(texts),
        "source_bindings": dict(workload.source_bindings),
        "prior_per_item_loop": {
            "encode_calls_per_repetition": len(texts),
            "samples_ms": [round(value, 3) for value in control_samples],
            "p50_ms": round(control_p50, 3),
            "p50_texts_per_second": round(len(texts) * 1000.0 / control_p50, 3),
        },
        "bounded_batch": {
            "encode_calls_per_repetition": 1,
            "samples_ms": [round(value, 3) for value in batch_samples],
            "p50_ms": round(batch_p50, 3),
            "p50_texts_per_second": round(len(texts) * 1000.0 / batch_p50, 3),
            "speedup_ratio": round(speedup, 3),
            "material_speedup": speedup >= MINIMUM_MATERIAL_SPEEDUP,
        },
        "batch_size_sweep": sweep,
        "ordered_vector_equivalence": _ordered_vector_equivalence(
            control_vectors, batch_vectors
        ),
        "cuda_peak": {
            "allocated_mib": _memory_mib(torch.cuda.max_memory_allocated(cuda_index)),
            "reserved_mib": _memory_mib(torch.cuda.max_memory_reserved(cuda_index)),
        },
    }


def validate_batching_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("status") != "PASS":
        raise GpuEmbeddingBatchingError("W3 receipt status or schema mismatch")
    rows = receipt.get("benchmarks") or []
    if len(rows) != 3:
        raise GpuEmbeddingBatchingError("W3 receipt must contain three production paths")
    for row in rows:
        if (row.get("bounded_batch") or {}).get("material_speedup") is not True:
            raise GpuEmbeddingBatchingError(
                f"W3 material throughput improvement missing: {row.get('benchmark_id')}"
            )
        proof = row.get("ordered_vector_equivalence") or {}
        if proof.get("cardinality_preserved") is not True or float(
            proof.get("minimum_same_index_cosine") or 0.0
        ) < MINIMUM_ORDERED_VECTOR_COSINE:
            raise GpuEmbeddingBatchingError(
                f"W3 stable-order proof failed: {row.get('benchmark_id')}"
            )
    runtime = receipt.get("runtime") or {}
    if runtime.get("fallback_used") is not False:
        raise GpuEmbeddingBatchingError("W3 fallback boundary changed")
    if runtime.get("model_load_count") != 1:
        raise GpuEmbeddingBatchingError("W3 did not reuse one resident model")
    if receipt.get("scope") != {
        "embedding_throughput_measured": True,
        "retrieval_quality_measured": False,
        "production_promotion_authorized": False,
        "release_authorizing": False,
    }:
        raise GpuEmbeddingBatchingError("W3 scope boundary mismatch")
    if receipt_sha256(receipt) != receipt.get("receipt_sha256"):
        raise GpuEmbeddingBatchingError("W3 receipt digest mismatch")


def run_batching_benchmark(
    *,
    repository_root: Path | str,
    output: Path | str | None = None,
    repetitions: int = 3,
) -> tuple[dict[str, Any], Path]:
    if repetitions < 3:
        raise GpuEmbeddingBatchingError("W3 requires at least three repetitions")
    root = Path(repository_root).resolve()
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[name] = "1"
    os.environ.setdefault("EMBEDDING_ENABLED", "true")
    os.environ.setdefault("APPS_RG_EMBEDDING_ENABLED", "true")
    os.environ.setdefault("EMBEDDING_DEVICE", "cuda:0")

    try:
        import torch
    except ImportError as exc:
        raise GpuEmbeddingBatchingError("Torch is unavailable") from exc
    settings = resolve_apps_rg_embedding_settings()
    if not settings.embedding_model_resolved or not settings.embedding_model_path:
        raise GpuEmbeddingBatchingError(settings.decisive_reason)
    if not torch.cuda.is_available():
        raise GpuEmbeddingBatchingError("W3 requires an available CUDA device")

    workloads = {row.workload_id: row for row in build_workloads(root)}
    ingest_source = workloads["r1b_projection_representative"]
    ingest_proxy = EmbeddingWorkload(
        workload_id="c02_fact_vector_ingest_32_item_proxy",
        texts=tuple(
            ingest_source.texts[index % len(ingest_source.texts)]
            for index in range(32)
        ),
        batch_size=32,
        source_bindings={
            **dict(ingest_source.source_bindings),
            "proxy_derivation": (
                "repeat the tracked ordered eight-item claim-sized source shape "
                "four times to locate the ingest knee through the tested 32-item cap"
            ),
        },
    )
    cases = (
        (
            "c02_section_query_batch",
            "c02_section_queries",
            workloads["c02_section_retrieval_representative"],
            "tracked production section queries",
        ),
        (
            "c02_fact_vector_ingest_batch",
            "c02_fact_vector_ingest",
            ingest_proxy,
            "32-item deterministic proxy derived from tracked claim-sized resume chunks",
        ),
        (
            "r1b_projection_batch",
            "r1b_projection",
            workloads["r1b_projection_representative"],
            "tracked intent plus seven ordered resume chunks",
        ),
    )

    reset_bge_runtime_for_testing()
    runtime = get_bge_runtime_for_settings(settings)
    device = runtime.key.device
    if not device.startswith("cuda"):
        raise GpuEmbeddingBatchingError(
            f"W3 requires the configured CUDA device; observed {device}"
        )
    cuda_index = _cuda_index(device)
    torch.cuda.set_device(cuda_index)
    benchmarks = [
        _benchmark_workload(
            runtime=runtime,
            workload=workload,
            workload_profile_id=profile_id,
            benchmark_id=benchmark_id,
            repetitions=repetitions,
            torch=torch,
            device=device,
            source_shape=source_shape,
        )
        for benchmark_id, profile_id, workload, source_shape in cases
    ]
    observation = resident_runtime_observation()
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {path.as_posix(): _file_sha256(root / path) for path in SOURCE_PATHS},
        "controls": {
            "minimum_material_speedup": MINIMUM_MATERIAL_SPEEDUP,
            "minimum_ordered_vector_cosine": MINIMUM_ORDERED_VECTOR_COSINE,
            "repetitions": repetitions,
            "batch_profile_sha256": _file_sha256(
                root / "src/apps_rg/config/domain_contract/bge_batch_profile.v1.json"
            ),
        },
        "runtime": {
            "device": device,
            "gpu_name": torch.cuda.get_device_name(cuda_index),
            "model_load_count": observation["model_load_count"],
            "registry_size": observation["registry_size"],
            "fallback_allowed": False,
            "fallback_used": False,
            "offline": True,
        },
        "benchmarks": benchmarks,
        "lifecycle_after_unload": {
            "unloaded_count": unload_bge_runtime(),
            "registry_size": resident_runtime_observation()["registry_size"],
        },
        "scope": {
            "embedding_throughput_measured": True,
            "retrieval_quality_measured": False,
            "production_promotion_authorized": False,
            "release_authorizing": False,
        },
    }
    if not all(row["bounded_batch"]["material_speedup"] for row in benchmarks):
        failed = [
            row["benchmark_id"]
            for row in benchmarks
            if not row["bounded_batch"]["material_speedup"]
        ]
        raise GpuEmbeddingBatchingError(
            f"W3 speedup below {MINIMUM_MATERIAL_SPEEDUP}: {failed}"
        )
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    validate_batching_receipt(receipt)
    destination = resolve_output_path(root, output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt, destination


__all__ = [
    "GpuEmbeddingBatchingError",
    "run_batching_benchmark",
    "validate_batching_receipt",
]
