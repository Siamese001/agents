"""Runtime-only proof that C0, C0.3, and R1B share one resident BGE-M3 model."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.bge_embedding import (
    receipt_sha256,
    reset_bge_runtime_for_testing,
    resident_runtime_observation,
    unload_bge_runtime,
)

RECEIPT_SCHEMA = "apps_rg.gpu_embedding_residency_w2.v1"
DEFAULT_OUTPUT = Path(".runtime/apps_rg/gpu-embedding-residency-w2/receipt.json")
SOURCE_PATHS = (
    Path("src/apps_rg/runtime/bge_embedding.py"),
    Path("src/apps_rg/runtime/embedding_settings.py"),
    Path("src/apps_rg/runtime/bindings/c0_binding.py"),
    Path("src/apps_rg/runtime/c0/c02_fact_vector_ingest.py"),
    Path("src/apps_rg/fact_inventory/c03_skill_embedding_builder.py"),
    Path("src/apps_rg/cache/r1b_bge_embedding.py"),
    Path("src/apps_rg/evals/gpu_embedding_residency_w2.py"),
)


class GpuEmbeddingResidencyError(RuntimeError):
    """W2 residency or receipt invariant failed."""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _vector_proof(vector: list[float]) -> dict[str, Any]:
    norm = math.sqrt(sum(value * value for value in vector))
    return {
        "dimension": len(vector),
        "finite": all(math.isfinite(value) for value in vector),
        "l2_norm": norm,
        "l2_normalized": math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4),
    }


def resolve_output_path(root: Path, output: Path | str | None) -> Path:
    runtime_root = (root / ".runtime").resolve()
    candidate = root / (Path(output) if output is not None else DEFAULT_OUTPUT)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise GpuEmbeddingResidencyError(
            f"W2 receipt must remain beneath {runtime_root}: {resolved}"
        ) from exc
    return resolved


def validate_residency_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise GpuEmbeddingResidencyError("W2 receipt schema mismatch")
    if receipt.get("status") != "PASS":
        raise GpuEmbeddingResidencyError("W2 receipt is not PASS")
    before = receipt.get("resident_runtime_before_unload") or {}
    after = receipt.get("lifecycle_after_unload") or {}
    if before.get("registry_size") != 1 or before.get("model_load_count") != 1:
        raise GpuEmbeddingResidencyError(
            "W2 did not prove exactly one resident model load"
        )
    if after != {"unloaded_count": 1, "registry_size": 0}:
        raise GpuEmbeddingResidencyError("W2 explicit unload proof mismatch")
    for name, proof in (receipt.get("entrypoints") or {}).items():
        if (
            proof.get("vector", {}).get("dimension") != 1024
            or proof.get("vector", {}).get("l2_normalized") is not True
        ):
            raise GpuEmbeddingResidencyError(f"W2 vector proof failed: {name}")
    scope = receipt.get("scope") or {}
    if scope != {
        "runtime_residency_verified": True,
        "retrieval_quality_measured": False,
        "production_promotion_authorized": False,
        "release_authorizing": False,
    }:
        raise GpuEmbeddingResidencyError("W2 scope boundary mismatch")
    if receipt_sha256(receipt) != receipt.get("receipt_sha256"):
        raise GpuEmbeddingResidencyError("W2 receipt digest mismatch")


def run_residency_proof(
    *, repository_root: Path | str, output: Path | str | None = None
) -> tuple[dict[str, Any], Path]:
    root = Path(repository_root).resolve()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("EMBEDDING_ENABLED", "true")
    os.environ.setdefault("APPS_RG_EMBEDDING_ENABLED", "true")
    os.environ.setdefault("EMBEDDING_DEVICE", "cuda:0")
    reset_bge_runtime_for_testing()

    from apps_rg.cache.r1b_bge_embedding import embed_texts_bge
    from apps_rg.fact_inventory.c03_skill_embedding_builder import encode_bge_m3
    from apps_rg.runtime.bindings.c0_binding import _get_embedding_runtime
    from apps_rg.runtime.embedding_settings import resolve_apps_rg_embedding_settings

    settings = resolve_apps_rg_embedding_settings()
    if not settings.embedding_model_resolved or not settings.embedding_model_path:
        raise GpuEmbeddingResidencyError(settings.decisive_reason)
    c0_runtime = _get_embedding_runtime()
    c0_vector = c0_runtime.encode(["W2 C0 resident runtime proof"], batch_size=1)[0]
    c03_runtime, c03_vectors = encode_bge_m3(
        ["W2 C0.3 resident runtime proof"],
        model_path=settings.embedding_model_path,
        device=c0_runtime.key.device,
        batch_size=1,
    )
    r1b_vectors = embed_texts_bge(["W2 R1B resident runtime proof"], batch_size=1)
    if r1b_vectors[0] is None:
        raise GpuEmbeddingResidencyError("R1B did not return a BGE-M3 vector")

    before = resident_runtime_observation()
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS",
        "source": {path.as_posix(): _file_sha256(root / path) for path in SOURCE_PATHS},
        "entrypoints": {
            "c0": {
                "runtime_load_ordinal": c0_runtime.load_ordinal,
                "vector": _vector_proof(c0_vector),
            },
            "c03": {
                "runtime_load_ordinal": c03_runtime["resident_runtime"]["load_ordinal"],
                "vector": _vector_proof(c03_vectors[0]),
            },
            "r1b": {
                "runtime_load_ordinal": 1,
                "vector": _vector_proof(r1b_vectors[0]),
            },
        },
        "resident_runtime_before_unload": before,
        "lifecycle_after_unload": {
            "unloaded_count": unload_bge_runtime(),
            "registry_size": resident_runtime_observation()["registry_size"],
        },
        "scope": {
            "runtime_residency_verified": True,
            "retrieval_quality_measured": False,
            "production_promotion_authorized": False,
            "release_authorizing": False,
        },
    }
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    validate_residency_receipt(receipt)
    destination = resolve_output_path(root, output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt, destination


__all__ = [
    "GpuEmbeddingResidencyError",
    "run_residency_proof",
    "validate_residency_receipt",
]
