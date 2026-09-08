"""Read-only W0 baseline for the governed apps_rg BGE-M3 GPU workloads.

This module measures embedding execution only. It never opens Chroma, queries a
graph projection, reads QREL judgments, or writes beneath canonical artifact
directories. Receipts are restricted to the repository's ignored ``.runtime``
tree and are explicitly non-authoritative for retrieval quality or promotion.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Mapping, Sequence

MODEL_ID = "BAAI/bge-m3"
MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
MODEL_DIMENSION = 1024
RECEIPT_SCHEMA = "apps_rg.gpu_embedding_baseline_w0.v1"

RUNTIME_CONTRACT_PATH = Path(
    "tools/apps_rg_standalone/c03_embedding_runtime_contract.json"
)
QUERY_MANIFEST_PATH = Path(
    "src/apps_rg/evals/c03_graph_evidence_cluster_queries.v1.json"
)
PINNED_MODEL_MANIFEST_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "bge_m3_model_manifest.38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263.json"
)
BASE_RESUME_PATH = Path("src/apps_rg/resume/base/amit_ayer_base_resume_v1.json")
C02_SECTION_PROFILE_PATH = Path(
    "src/apps_rg/config/domain_contract/section_retrieval_profile.yaml"
)
HARNESS_PATH = Path("src/apps_rg/evals/gpu_embedding_baseline_w0.py")
DEFAULT_OUTPUT_ROOT = Path(".runtime/apps_rg/gpu-baseline-w0")


class GpuEmbeddingBaselineError(RuntimeError):
    """Raised when W0 cannot prove an offline, no-fallback GPU baseline."""


@dataclass(frozen=True)
class EmbeddingWorkload:
    """A reproducible batch shape and its tracked-source bindings."""

    workload_id: str
    texts: tuple[str, ...]
    batch_size: int
    source_bindings: Mapping[str, Any]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile, matching the existing W7 diagnostic."""

    if not values:
        raise GpuEmbeddingBaselineError("latency observations are empty")
    if not 0.0 < fraction <= 1.0:
        raise GpuEmbeddingBaselineError("percentile fraction must be in (0, 1]")
    ordered = sorted(float(value) for value in values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def resolve_output_path(repository_root: Path | str, output: Path | str | None) -> Path:
    """Resolve a receipt path and reject writes outside ``.runtime``."""

    root = Path(repository_root).resolve()
    runtime_root = (root / ".runtime").resolve()
    if output is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        candidate = root / DEFAULT_OUTPUT_ROOT / stamp / "receipt.json"
    else:
        supplied = Path(output)
        candidate = supplied if supplied.is_absolute() else root / supplied
        if candidate.suffix.lower() != ".json":
            candidate = candidate / "receipt.json"
    resolved = candidate.resolve()
    try:
        resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise GpuEmbeddingBaselineError(
            f"W0 receipt must remain beneath {runtime_root}: {resolved}"
        ) from exc
    return resolved


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GpuEmbeddingBaselineError(f"cannot load JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise GpuEmbeddingBaselineError(f"JSON value is not an object: {path}")
    return value


def _source_binding(root: Path, path: Path) -> dict[str, str]:
    absolute = (root / path).resolve()
    try:
        relative = absolute.relative_to(root).as_posix()
    except ValueError as exc:
        raise GpuEmbeddingBaselineError(f"source escapes repository: {path}") from exc
    if not absolute.is_file():
        raise GpuEmbeddingBaselineError(
            f"tracked workload source is missing: {relative}"
        )
    return {"path": relative, "sha256": file_sha256(absolute)}


def _representative_r1b_texts(
    base_resume: Mapping[str, Any], intent_text: str
) -> list[str]:
    texts = [intent_text]
    employment = (base_resume.get("facts") or {}).get("employment") or []
    for role in employment:
        if not isinstance(role, Mapping):
            continue
        narrative = str(role.get("role_narrative") or "").strip()
        if narrative:
            texts.append(narrative)
        for bullet in role.get("bullets") or []:
            if isinstance(bullet, Mapping):
                text = str(bullet.get("text") or "").strip()
                if text:
                    texts.append(text)
            if len(texts) >= 8:
                return texts
        if len(texts) >= 8:
            return texts
    if len(texts) < 2:
        raise GpuEmbeddingBaselineError("base resume has no representative R1B chunks")
    return texts


def _representative_c02_queries(root: Path, jd_text: str) -> list[tuple[str, str]]:
    """Read the governed C0.2 profile without importing the full runtime spine."""

    import yaml

    profile_path = root / C02_SECTION_PROFILE_PATH
    try:
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GpuEmbeddingBaselineError(
            f"cannot load C0.2 section profile: {profile_path}"
        ) from exc
    if not isinstance(profile, Mapping):
        raise GpuEmbeddingBaselineError("C0.2 section profile is not an object")
    payload = {"jd_payload": {"jd_text": jd_text}}
    rows: list[tuple[str, str]] = []
    for section in profile.get("sections") or []:
        if not isinstance(section, Mapping):
            continue
        section_id = str(section.get("section_id") or "")
        query = ""
        for dotted in section.get("query_fields") or []:
            value: Any = payload
            for part in str(dotted).split("."):
                value = value.get(part) if isinstance(value, Mapping) else None
            if isinstance(value, str) and len(value) >= 10:
                query = value
                break
        if not query and section.get("fallback_queries"):
            query = str(section["fallback_queries"][0])
        if section_id and query:
            rows.append((section_id, query))
    if not rows:
        raise GpuEmbeddingBaselineError(
            "C0.2 profile produced no representative queries"
        )
    return rows


def build_workloads(repository_root: Path | str) -> list[EmbeddingWorkload]:
    """Build four W0 batches from current tracked production inputs."""

    root = Path(repository_root).resolve()
    from apps_rg.cache.r1b_intent_vector import intent_text_from_request
    from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
        build_query_texts,
        validate_query_manifest,
    )
    from apps_rg.runtime.c0.graph_skill_embedding_allocation import (
        ALL_EMBEDDING_LANES,
        _query_text,
    )

    query_manifest = _load_json_object(root / QUERY_MANIFEST_PATH)
    validate_query_manifest(query_manifest, repository_root=root)
    frozen_queries = build_query_texts(query_manifest, repository_root=root)
    ordered_query_ids = sorted(frozen_queries)
    representative = min(
        query_manifest["queries"], key=lambda row: str(row["query_id"])
    )
    query_id = str(representative["query_id"])
    jd_path = Path(str(representative["jd_path"]))
    brief_path = Path(str(representative["brief_path"]))
    jd_text = (root / jd_path).read_text(encoding="utf-8").strip()
    brief_text = (root / brief_path).read_text(encoding="utf-8").strip()
    target_role = str(representative["target_profile_id"])
    target_company = query_id.rsplit("_", 1)[-1].replace("-", " ").title()

    whole_resume_texts = [
        _query_text(
            section_id=section_id,
            target_company=target_company,
            target_role=target_role,
            jd_text=jd_text,
            briefing_text=brief_text,
        )
        for section_id in ALL_EMBEDDING_LANES
    ]

    c02_rows = _representative_c02_queries(root, jd_text)

    base_resume = _load_json_object(root / BASE_RESUME_PATH)
    r1b_request = {
        "target_company": target_company,
        "target_role": target_role,
        "generation_mode": "strategic_tailor",
        "jd_hash": str(representative["jd_sha256"]),
        "brief_hash": str(representative["brief_sha256"]),
        "resume_hash": file_sha256(root / BASE_RESUME_PATH),
    }
    r1b_texts = _representative_r1b_texts(
        base_resume, intent_text_from_request(r1b_request)
    )

    query_source_bindings = {
        "query_manifest": _source_binding(root, QUERY_MANIFEST_PATH),
        "query_manifest_sha256": str(query_manifest["query_manifest_sha256"]),
    }
    representative_bindings = {
        "representative_query_id": query_id,
        "jd": _source_binding(root, jd_path),
        "brief": _source_binding(root, brief_path),
    }
    return [
        EmbeddingWorkload(
            workload_id="frozen_six_query",
            texts=tuple(frozen_queries[query] for query in ordered_query_ids),
            batch_size=6,
            source_bindings={
                **query_source_bindings,
                "ordered_query_ids": ordered_query_ids,
            },
        ),
        EmbeddingWorkload(
            workload_id="whole_resume_eleven_section",
            texts=tuple(whole_resume_texts),
            batch_size=len(ALL_EMBEDDING_LANES),
            source_bindings={
                **representative_bindings,
                "constructor": (
                    "apps_rg.runtime.c0.graph_skill_embedding_allocation._query_text"
                ),
                "ordered_section_ids": list(ALL_EMBEDDING_LANES),
            },
        ),
        EmbeddingWorkload(
            workload_id="c02_section_retrieval_representative",
            texts=tuple(query for _section_id, query in c02_rows),
            batch_size=1,
            source_bindings={
                **representative_bindings,
                "section_profile": _source_binding(
                    root,
                    C02_SECTION_PROFILE_PATH,
                ),
                "ordered_section_ids": [section_id for section_id, _query in c02_rows],
                "production_batch_shape": "one_query_per_section",
            },
        ),
        EmbeddingWorkload(
            workload_id="r1b_projection_representative",
            texts=tuple(r1b_texts),
            batch_size=64,
            source_bindings={
                **representative_bindings,
                "base_resume": _source_binding(root, BASE_RESUME_PATH),
                "intent_constructor": (
                    "apps_rg.cache.r1b_intent_vector.intent_text_from_request"
                ),
                "batch_shape": "intent_plus_seven_resume_chunks",
            },
        ),
    ]


def _token_length_stats(model: Any, texts: Sequence[str]) -> dict[str, Any]:
    encoded = model.tokenizer(
        list(texts),
        add_special_tokens=True,
        padding=False,
        truncation=False,
    )
    lengths = [len(row) for row in encoded["input_ids"]]
    model_max = int(getattr(model.tokenizer, "model_max_length", 0) or 0)
    return {
        "min": min(lengths),
        "p50": int(percentile(lengths, 0.50)),
        "p95": int(percentile(lengths, 0.95)),
        "max": max(lengths),
        "model_max_length": model_max,
        "over_model_max_count": sum(length > model_max for length in lengths)
        if 0 < model_max < 10**9
        else 0,
    }


def _vector_proof(vectors: Any, expected_count: int) -> dict[str, Any]:
    import numpy as np

    array = np.asarray(vectors, dtype=np.float32)
    expected_shape = (expected_count, MODEL_DIMENSION)
    if tuple(array.shape) != expected_shape:
        raise GpuEmbeddingBaselineError(
            f"vector shape mismatch: expected {expected_shape}, observed {tuple(array.shape)}"
        )
    if not bool(np.isfinite(array).all()):
        raise GpuEmbeddingBaselineError("embedding vectors contain non-finite values")
    norms = np.linalg.norm(array, axis=1)
    max_norm_error = float(np.max(np.abs(norms - 1.0)))
    if max_norm_error > 1e-4:
        raise GpuEmbeddingBaselineError(
            f"embedding vectors are not L2 normalized: max error {max_norm_error}"
        )
    return {
        "vector_count": expected_count,
        "dimension": MODEL_DIMENSION,
        "finite": True,
        "l2_normalized": True,
        "max_l2_norm_error": round(max_norm_error, 8),
        "float32_sha256": hashlib.sha256(array.astype("<f4").tobytes()).hexdigest(),
    }


def _cuda_index(device: str) -> int:
    return int(device.split(":", 1)[1]) if ":" in device else 0


def _synchronize(torch: Any, device: str) -> None:
    if device.startswith("cuda"):
        torch.cuda.synchronize(_cuda_index(device))


def _memory_mib(value: int | float) -> float:
    return round(float(value) / (1024.0 * 1024.0), 3)


def _encode_once(
    model: Any,
    texts: Sequence[str],
    *,
    batch_size: int,
    torch: Any,
    device: str,
) -> tuple[float, Any]:
    _synchronize(torch, device)
    started = time.perf_counter()
    vectors = model.encode(
        list(texts),
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    _synchronize(torch, device)
    return (time.perf_counter() - started) * 1000.0, vectors


def _gpu_identity(torch: Any, device: str) -> dict[str, Any]:
    index = _cuda_index(device)
    properties = torch.cuda.get_device_properties(index)
    driver_version: str | None = None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--id={index}",
                "--query-gpu=driver_version",
                "--format=csv,noheader",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        driver_version = result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        driver_version = None
    return {
        "device": device,
        "name": str(properties.name),
        "compute_capability": list(torch.cuda.get_device_capability(index)),
        "total_memory_mib": _memory_mib(properties.total_memory),
        "driver_version": driver_version,
        "cuda_runtime_version": str(torch.version.cuda),
    }


def _git_identity(root: Path) -> dict[str, Any]:
    def value(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    return {
        "commit": value("rev-parse", "HEAD"),
        "branch": value("branch", "--show-current"),
        "dirty": bool(value("status", "--porcelain")),
    }


def _validate_runtime_contract(
    contract: Mapping[str, Any], *, torch: Any, device: str
) -> None:
    unsigned = dict(contract)
    supplied_digest = str(unsigned.pop("contract_sha256", ""))
    if canonical_sha256(unsigned) != supplied_digest:
        raise GpuEmbeddingBaselineError("embedding runtime contract digest mismatch")
    observed = {
        "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "torch": str(torch.__version__),
        "sentence-transformers": version("sentence-transformers"),
    }
    expected = {
        "python_major_minor": str(contract.get("python_major_minor") or ""),
        "torch": str((contract.get("packages") or {}).get("torch") or ""),
        "sentence-transformers": str(
            (contract.get("packages") or {}).get("sentence-transformers") or ""
        ),
    }
    if observed != expected:
        raise GpuEmbeddingBaselineError(
            f"embedding runtime contract mismatch: expected {expected}, observed {observed}"
        )
    if device != contract.get("promoted_device"):
        raise GpuEmbeddingBaselineError(
            f"device must match promoted runtime: {contract.get('promoted_device')}"
        )
    for field, expected_value in (
        ("local_files_only", True),
        ("network_allowed", False),
        ("fallback_allowed", False),
    ):
        if contract.get(field) is not expected_value:
            raise GpuEmbeddingBaselineError(f"runtime contract weakens {field}")


def run_baseline(
    *,
    repository_root: Path | str,
    model_path: Path | str,
    device: str = "cuda:0",
    warm_repetitions: int = 5,
) -> dict[str, Any]:
    """Execute W0 in memory and return a machine-readable PASS receipt."""

    if warm_repetitions < 3:
        raise GpuEmbeddingBaselineError("at least three warm repetitions are required")
    root = Path(repository_root).resolve()
    resolved_model = Path(model_path).resolve()
    if not resolved_model.is_dir():
        raise GpuEmbeddingBaselineError(
            f"local BGE-M3 directory missing: {resolved_model}"
        )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise GpuEmbeddingBaselineError(
            "BGE-M3 runtime dependencies are unavailable"
        ) from exc
    if not device.startswith("cuda") or not torch.cuda.is_available():
        raise GpuEmbeddingBaselineError(
            "W0 requires the pinned CUDA device; CPU is not valid"
        )

    contract = _load_json_object(root / RUNTIME_CONTRACT_PATH)
    _validate_runtime_contract(contract, torch=torch, device=device)
    pinned_manifest = _load_json_object(root / PINNED_MODEL_MANIFEST_PATH)
    from apps_rg.fact_inventory.c03_skill_embedding_builder import (
        build_local_model_manifest,
    )

    observed_manifest = build_local_model_manifest(resolved_model)
    if observed_manifest != pinned_manifest:
        raise GpuEmbeddingBaselineError(
            "local BGE-M3 artifact does not match the pinned manifest"
        )
    model_contract = contract.get("model") or {}
    if any(
        (
            observed_manifest.get("model_id") != model_contract.get("model_id"),
            observed_manifest.get("revision") != model_contract.get("revision"),
            observed_manifest.get("dimension") != model_contract.get("dimension"),
            observed_manifest.get("normalization")
            != model_contract.get("normalization"),
        )
    ):
        raise GpuEmbeddingBaselineError(
            "pinned model manifest/runtime contract mismatch"
        )

    workloads = build_workloads(root)
    cuda_index = _cuda_index(device)
    # This Windows Torch build does not initialize the allocator merely from
    # ``is_available()``; select the device before using peak-memory counters.
    torch.cuda.set_device(cuda_index)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(cuda_index)
    _synchronize(torch, device)
    load_started = time.perf_counter()
    model = SentenceTransformer(
        str(resolved_model), device=device, local_files_only=True
    )
    _synchronize(torch, device)
    model_load_ms = (time.perf_counter() - load_started) * 1000.0
    if str(model.device) != device:
        raise GpuEmbeddingBaselineError(
            f"model device mismatch: expected {device}, observed {model.device}"
        )
    model_load_memory = {
        "peak_allocated_mib": _memory_mib(torch.cuda.max_memory_allocated(cuda_index)),
        "peak_reserved_mib": _memory_mib(torch.cuda.max_memory_reserved(cuda_index)),
    }

    results: list[dict[str, Any]] = []
    for workload in workloads:
        text_count = len(workload.texts)
        torch.cuda.reset_peak_memory_stats(cuda_index)
        before_allocated = torch.cuda.memory_allocated(cuda_index)
        before_reserved = torch.cuda.memory_reserved(cuda_index)
        cold_ms, cold_vectors = _encode_once(
            model,
            workload.texts,
            batch_size=workload.batch_size,
            torch=torch,
            device=device,
        )
        vector_proof = _vector_proof(cold_vectors, text_count)
        warm_samples: list[float] = []
        warm_digests: list[str] = []
        for _ in range(warm_repetitions):
            elapsed_ms, vectors = _encode_once(
                model,
                workload.texts,
                batch_size=workload.batch_size,
                torch=torch,
                device=device,
            )
            warm_samples.append(elapsed_ms)
            warm_digests.append(_vector_proof(vectors, text_count)["float32_sha256"])
        p50_ms = percentile(warm_samples, 0.50)
        p95_ms = percentile(warm_samples, 0.95)
        text_lengths = [len(text) for text in workload.texts]
        results.append(
            {
                "workload_id": workload.workload_id,
                "text_count": text_count,
                "batch_size": workload.batch_size,
                "input_sha256": canonical_sha256(list(workload.texts)),
                "source_bindings": dict(workload.source_bindings),
                "character_lengths": {
                    "min": min(text_lengths),
                    "p50": int(percentile(text_lengths, 0.50)),
                    "p95": int(percentile(text_lengths, 0.95)),
                    "max": max(text_lengths),
                },
                "token_lengths": _token_length_stats(model, workload.texts),
                "cold_first_pass": {
                    "elapsed_ms": round(cold_ms, 3),
                    "texts_per_second": round(text_count * 1000.0 / cold_ms, 3),
                },
                "warm": {
                    "repetitions": warm_repetitions,
                    "samples_ms": [round(value, 3) for value in warm_samples],
                    "p50_ms": round(p50_ms, 3),
                    "p95_ms": round(p95_ms, 3),
                    "max_ms": round(max(warm_samples), 3),
                    "p50_texts_per_second": round(text_count * 1000.0 / p50_ms, 3),
                    "p95_texts_per_second": round(text_count * 1000.0 / p95_ms, 3),
                    "vector_digest_stable": len(set(warm_digests)) == 1,
                },
                "cuda_memory": {
                    "before_allocated_mib": _memory_mib(before_allocated),
                    "before_reserved_mib": _memory_mib(before_reserved),
                    "peak_allocated_mib": _memory_mib(
                        torch.cuda.max_memory_allocated(cuda_index)
                    ),
                    "peak_reserved_mib": _memory_mib(
                        torch.cuda.max_memory_reserved(cuda_index)
                    ),
                },
                "vector_proof": vector_proof,
            }
        )

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "git": _git_identity(root),
            "harness": _source_binding(root, HARNESS_PATH),
            "runtime_contract": _source_binding(root, RUNTIME_CONTRACT_PATH),
            "pinned_model_manifest": _source_binding(root, PINNED_MODEL_MANIFEST_PATH),
        },
        "scope": {
            "embedding_execution_measured": True,
            "retrieval_quality_measured": False,
            "qrels_read": False,
            "graph_projection_opened": False,
            "chroma_opened": False,
            "canonical_artifacts_written": False,
            "production_promotion_authorized": False,
            "release_authorizing": False,
        },
        "runtime": {
            "offline_environment": {
                "HF_HUB_OFFLINE": os.environ["HF_HUB_OFFLINE"],
                "TRANSFORMERS_OFFLINE": os.environ["TRANSFORMERS_OFFLINE"],
                "HF_DATASETS_OFFLINE": os.environ["HF_DATASETS_OFFLINE"],
            },
            "local_files_only": True,
            "network_allowed": False,
            "fallback_allowed": False,
            "fallback_used": False,
            "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
            "torch_version": str(torch.__version__),
            "sentence_transformers_version": version("sentence-transformers"),
            "gpu": _gpu_identity(torch, device),
        },
        "model": {
            "model_id": observed_manifest["model_id"],
            "revision": observed_manifest["revision"],
            "dimension": observed_manifest["dimension"],
            "normalization": observed_manifest["normalization"],
            "artifact_sha256": observed_manifest["artifact_sha256"],
            "file_count": observed_manifest["file_count"],
            "total_bytes": observed_manifest["total_bytes"],
            "load_elapsed_ms": round(model_load_ms, 3),
            "load_cuda_memory": model_load_memory,
        },
        "workload_count": len(results),
        "workloads": results,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    validate_receipt(receipt)
    return receipt


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        issues.append("schema_version")
    if receipt.get("status") != "PASS":
        issues.append("status")
    scope = receipt.get("scope") or {}
    if scope.get("embedding_execution_measured") is not True:
        issues.append("scope.embedding_execution_measured")
    for field in (
        "retrieval_quality_measured",
        "qrels_read",
        "graph_projection_opened",
        "chroma_opened",
        "canonical_artifacts_written",
        "production_promotion_authorized",
        "release_authorizing",
    ):
        if scope.get(field) is not False:
            issues.append(f"scope.{field}")
    runtime = receipt.get("runtime") or {}
    if runtime.get("local_files_only") is not True:
        issues.append("runtime.local_files_only")
    if runtime.get("network_allowed") is not False:
        issues.append("runtime.network_allowed")
    if runtime.get("fallback_allowed") is not False:
        issues.append("runtime.fallback_allowed")
    if runtime.get("fallback_used") is not False:
        issues.append("runtime.fallback_used")
    gpu = runtime.get("gpu") or {}
    if gpu.get("device") != "cuda:0":
        issues.append("runtime.gpu.device")
    workloads = receipt.get("workloads") or []
    if receipt.get("workload_count") != 4 or len(workloads) != 4:
        issues.append("workload_count")
    expected_ids = {
        "frozen_six_query",
        "whole_resume_eleven_section",
        "c02_section_retrieval_representative",
        "r1b_projection_representative",
    }
    if {
        row.get("workload_id") for row in workloads if isinstance(row, Mapping)
    } != expected_ids:
        issues.append("workload_ids")
    source = receipt.get("source") or {}
    harness = source.get("harness") or {}
    if not harness.get("sha256"):
        issues.append("source.harness.sha256")
    model = receipt.get("model") or {}
    if model.get("model_id") != MODEL_ID:
        issues.append("model.model_id")
    if model.get("revision") != MODEL_REVISION:
        issues.append("model.revision")
    if model.get("dimension") != MODEL_DIMENSION:
        issues.append("model.dimension")
    if model.get("normalization") != "l2":
        issues.append("model.normalization")
    for row in workloads:
        if not isinstance(row, Mapping):
            issues.append("workload.row")
            continue
        workload_id = str(row.get("workload_id") or "unknown")
        if int(row.get("text_count") or 0) < 1:
            issues.append(f"workload.{workload_id}.text_count")
        if int(row.get("batch_size") or 0) < 1:
            issues.append(f"workload.{workload_id}.batch_size")
        token_lengths = row.get("token_lengths") or {}
        if int(token_lengths.get("over_model_max_count") or 0) != 0:
            issues.append(f"workload.{workload_id}.token_lengths")
        warm = row.get("warm") or {}
        if int(warm.get("repetitions") or 0) < 3:
            issues.append(f"workload.{workload_id}.warm.repetitions")
        if warm.get("vector_digest_stable") is not True:
            issues.append(f"workload.{workload_id}.warm.vector_digest_stable")
        vector = row.get("vector_proof") or {}
        if vector.get("dimension") != MODEL_DIMENSION:
            issues.append(f"workload.{workload_id}.vector.dimension")
        if vector.get("finite") is not True:
            issues.append(f"workload.{workload_id}.vector.finite")
        if vector.get("l2_normalized") is not True:
            issues.append(f"workload.{workload_id}.vector.l2_normalized")
    unsigned = dict(receipt)
    supplied_digest = unsigned.pop("receipt_sha256", None)
    if canonical_sha256(unsigned) != supplied_digest:
        issues.append("receipt_sha256")
    if issues:
        raise GpuEmbeddingBaselineError(
            f"invalid W0 GPU embedding receipt: {sorted(set(issues))}"
        )


def write_receipt(path: Path | str, receipt: Mapping[str, Any]) -> None:
    destination = Path(path)
    validate_receipt(receipt)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    staging = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    staging.write_bytes(data)
    os.replace(staging, destination)


__all__ = [
    "EmbeddingWorkload",
    "GpuEmbeddingBaselineError",
    "build_workloads",
    "canonical_sha256",
    "percentile",
    "resolve_output_path",
    "run_baseline",
    "validate_receipt",
    "write_receipt",
]
