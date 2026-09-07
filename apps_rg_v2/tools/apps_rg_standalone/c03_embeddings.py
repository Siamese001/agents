"""Build, qualify, activate, and inspect standalone C0.3 graph embeddings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.c03_graph_embedding_qualification import (  # noqa: E402
    QUALIFICATION_THRESHOLDS,
    QUERY_QREL_SCHEMA_VERSION,
    evaluate_graph_embedding_qualification,
)
from apps_rg.fact_inventory.c03_graph_authority_reconciliation import (  # noqa: E402
    reconcile_graph_authority,
)
from apps_rg.fact_inventory.c03_skill_assertion_corpus import (  # noqa: E402
    canonical_sha256,
)
from apps_rg.fact_inventory.c03_skill_embedding_builder import (  # noqa: E402
    build_assertion_embedding_generation,
    build_local_model_manifest,
    encode_bge_m3,
)
from apps_rg.runtime.c0.graph_skill_embedding_allocation import (  # noqa: E402
    GraphSkillEmbeddingAllocationError,
    assert_legacy_graph_skill_embedding_lane_not_retired,
    load_graph_skill_embedding_authority,
)
from apps_rg.runtime.graph_skill_embedding_projection import (  # noqa: E402
    GraphSkillEmbeddingIndex,
    rehydrate_assertion_candidates,
    validate_embedding_projection,
)
from apps_rg.runtime.graph_skill_hybrid_retrieval import (  # noqa: E402
    bm25_rank,
    fuse_dense_bm25,
)

ACTIVE_ARTIFACT_REL = Path("artifacts/apps_rg/c03/graph_skill_embeddings")
GRAPH_REL = Path("src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json")
CANDIDATE_FACTS_REL = Path(
    "artifacts/apps_rg/fact_inventory/"
    "master_candidate_skills_fact_ledger_20260518T1100Z.json"
)
BASE_RESUME_REL = Path("src/apps_rg/resume/base/amit_ayer_base_resume_v1.json")
GENERATION_MANIFEST_NAME = "graph_skill_embedding_manifest.json"
QUALIFICATION_MANIFEST_NAME = "graph_embedding_qualification_manifest.json"
ACTIVATION_MANIFEST_NAME = "graph_skill_embedding_activation_manifest.json"
RUNTIME_CONTRACT_REL = Path(
    "tools/apps_rg_standalone/c03_embedding_runtime_contract.json"
)
QUALIFICATION_SCOPE = "REGRESSION_ONLY"


class StandaloneEmbeddingError(RuntimeError):
    """Raised when a standalone embedding operation cannot preserve authority."""


def _assert_legacy_lane_open(repository_root: Path | str) -> None:
    try:
        assert_legacy_graph_skill_embedding_lane_not_retired(repository_root)
    except GraphSkillEmbeddingAllocationError as exc:
        raise StandaloneEmbeddingError(str(exc)) from exc


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise StandaloneEmbeddingError(f"JSON artifact is not an object: {path}")
    return value


def _resolve_within(root: Path, value: str, *, label: str) -> Path:
    if not value:
        raise StandaloneEmbeddingError(f"{label} path is missing")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise StandaloneEmbeddingError(
            f"{label} path escapes its authority root"
        ) from exc
    return path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _require_file_digest(path: Path, expected: str, *, label: str) -> None:
    if not path.is_file():
        raise StandaloneEmbeddingError(f"{label} is missing: {path}")
    observed = _file_sha256(path)
    if not expected or observed != expected:
        raise StandaloneEmbeddingError(
            f"{label} digest mismatch: expected {expected}, observed {observed}"
        )


def _require_self_digest(
    payload: Mapping[str, Any],
    field: str,
    *,
    label: str,
    expected: str | None = None,
) -> str:
    unsigned = dict(payload)
    observed = str(unsigned.pop(field, ""))
    computed = canonical_sha256(unsigned)
    if (
        not observed
        or observed != computed
        or (expected is not None and observed != expected)
    ):
        raise StandaloneEmbeddingError(f"{label} digest mismatch")
    return observed


def _render_json(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write_atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.staging-{os.getpid()}")
    staging.write_bytes(data)
    os.replace(staging, path)


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> str:
    data = _render_json(payload)
    if path.exists():
        if path.read_bytes() != data:
            raise StandaloneEmbeddingError(f"immutable artifact collision: {path}")
    else:
        _write_atomic_bytes(path, data)
    return hashlib.sha256(data).hexdigest()


def _copy_immutable(source: Path, destination: Path) -> None:
    if destination.exists():
        if _file_sha256(destination) != _file_sha256(source):
            raise StandaloneEmbeddingError(
                f"immutable artifact collision: {destination}"
            )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.staging-{os.getpid()}")
    shutil.copyfile(source, staging)
    os.replace(staging, destination)


def standalone_source_paths(repository_root: Path | str) -> dict[str, Path]:
    root = Path(repository_root).resolve()
    return {
        "graph": root / GRAPH_REL,
        "candidate_facts": root / CANDIDATE_FACTS_REL,
        "base_resume": root / BASE_RESUME_REL,
    }


def _active_artifact_dir(repository_root: Path) -> Path:
    return (repository_root / ACTIVE_ARTIFACT_REL).resolve()


def _model_path(value: Path | str | None) -> Path:
    raw = str(value or os.environ.get("APPS_RG_EMBEDDING_MODEL_PATH") or "").strip()
    path = Path(raw).resolve() if raw else Path()
    if not raw or not path.is_dir():
        raise StandaloneEmbeddingError(
            "APPS_RG_EMBEDDING_MODEL_PATH or --model-path must name a local BGE-M3 directory"
        )
    return path


def _device(value: str | None) -> str:
    resolved = str(
        value or os.environ.get("APPS_RG_GRAPH_SKILL_EMBEDDING_DEVICE") or ""
    ).strip()
    if not resolved:
        raise StandaloneEmbeddingError(
            "APPS_RG_GRAPH_SKILL_EMBEDDING_DEVICE or --device is required"
        )
    return resolved


def verify_embedding_runtime_contract(repository_root: Path | str) -> dict[str, Any]:
    """Verify the exact local package/runtime contract used for C0.3 embeddings."""

    root = Path(repository_root).resolve()
    contract_path = root / RUNTIME_CONTRACT_REL
    contract = _load_object(contract_path)
    contract_sha256 = _require_self_digest(
        contract,
        "contract_sha256",
        label="embedding runtime contract",
    )
    expected_python = str(contract.get("python_major_minor") or "")
    observed_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if observed_python != expected_python:
        raise StandaloneEmbeddingError(
            f"embedding runtime Python mismatch: expected {expected_python}, "
            f"observed {observed_python}"
        )
    packages = contract.get("packages")
    if not isinstance(packages, Mapping) or not packages:
        raise StandaloneEmbeddingError(
            "embedding runtime contract packages are missing"
        )
    observed_packages: dict[str, str] = {}
    for name, expected in packages.items():
        try:
            observed = package_version(str(name))
        except PackageNotFoundError as exc:
            raise StandaloneEmbeddingError(
                f"embedding runtime package is missing: {name}"
            ) from exc
        if observed != str(expected):
            raise StandaloneEmbeddingError(
                f"embedding runtime package mismatch for {name}: "
                f"expected {expected}, observed {observed}"
            )
        observed_packages[str(name)] = observed
    if (
        contract.get("local_files_only") is not True
        or contract.get("network_allowed") is not False
        or contract.get("fallback_allowed") is not False
    ):
        raise StandaloneEmbeddingError(
            "embedding runtime contract weakens offline execution"
        )
    model = contract.get("model")
    if not isinstance(model, Mapping):
        raise StandaloneEmbeddingError("embedding runtime model contract is missing")
    return {
        "path": RUNTIME_CONTRACT_REL.as_posix(),
        "contract_sha256": contract_sha256,
        "python_major_minor": expected_python,
        "packages": observed_packages,
        "promoted_device": str(contract.get("promoted_device") or ""),
        "_contract": contract,
    }


def _runtime_contract_evidence(runtime_contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in runtime_contract.items()
        if not str(key).startswith("_")
    }


def _validate_model_runtime_contract(
    runtime_contract: Mapping[str, Any],
    model_manifest: Mapping[str, Any],
) -> None:
    model = (runtime_contract.get("_contract") or {}).get("model")
    if not isinstance(model, Mapping):
        raise StandaloneEmbeddingError("embedding runtime model contract is missing")
    for field in ("model_id", "revision", "dimension", "normalization"):
        if model_manifest.get(field) != model.get(field):
            raise StandaloneEmbeddingError(f"embedding runtime model {field} mismatch")


def _validate_runtime_proof(
    runtime_contract: Mapping[str, Any],
    runtime_proof: Mapping[str, Any],
) -> None:
    if runtime_proof.get("python_major_minor") != runtime_contract.get(
        "python_major_minor"
    ):
        raise StandaloneEmbeddingError("embedding runtime Python proof mismatch")
    packages = runtime_contract.get("packages") or {}
    if runtime_proof.get("torch_version") != packages.get("torch"):
        raise StandaloneEmbeddingError("embedding runtime Torch proof mismatch")
    if runtime_proof.get("sentence_transformers_version") != packages.get(
        "sentence-transformers"
    ):
        raise StandaloneEmbeddingError(
            "embedding runtime Sentence Transformers proof mismatch"
        )
    promoted_device = str(runtime_contract.get("promoted_device") or "")
    if runtime_proof.get("device") != promoted_device:
        raise StandaloneEmbeddingError(
            f"embedding runtime device mismatch: expected {promoted_device}, "
            f"observed {runtime_proof.get('device')}"
        )
    if (
        promoted_device.startswith("cuda")
        and runtime_proof.get("cuda_available") is not True
    ):
        raise StandaloneEmbeddingError("embedding runtime CUDA proof is missing")
    if runtime_proof.get("fallback_used") is not False:
        raise StandaloneEmbeddingError("embedding runtime used a fallback")


def build_candidate(
    *,
    repository_root: Path | str,
    output_dir: Path | str,
    model_path: Path | str | None,
    device: str | None,
) -> dict[str, Any]:
    """Build a standalone-path-bound generation outside the active directory."""

    root = Path(repository_root).resolve()
    _assert_legacy_lane_open(root)
    output = Path(output_dir).resolve()
    active = _active_artifact_dir(root)
    if _is_within(output, active):
        raise StandaloneEmbeddingError(
            "build output must not be the active artifact directory or a child of it"
        )
    if output.exists() and any(output.iterdir()):
        raise StandaloneEmbeddingError(f"candidate directory is not empty: {output}")
    paths = standalone_source_paths(root)
    missing = [label for label, path in paths.items() if not path.is_file()]
    if missing:
        raise StandaloneEmbeddingError(
            "standalone embedding sources are missing: " + ", ".join(sorted(missing))
        )
    runtime_contract = verify_embedding_runtime_contract(root)
    generation = build_assertion_embedding_generation(
        repository_root=root,
        graph_path=paths["graph"],
        candidate_fact_path=paths["candidate_facts"],
        base_resume_path=paths["base_resume"],
        model_path=_model_path(model_path),
        output_dir=output,
        device=_device(device),
    )
    model_ref = generation.get("model")
    runtime_proof = generation.get("runtime_proof")
    if not isinstance(model_ref, Mapping) or not isinstance(runtime_proof, Mapping):
        raise StandaloneEmbeddingError(
            "embedding generation runtime bindings are incomplete"
        )
    _validate_model_runtime_contract(runtime_contract, model_ref)
    _validate_runtime_proof(runtime_contract, runtime_proof)
    return generation


def _load_generation(
    repository_root: Path,
    generation_dir: Path,
) -> dict[str, Any]:
    manifest_path = generation_dir / GENERATION_MANIFEST_NAME
    generation = _load_object(manifest_path)
    generation_digest = _require_self_digest(
        generation,
        "manifest_sha256",
        label="embedding generation manifest",
    )

    source_payloads: dict[str, dict[str, Any]] = {}
    expected_source_paths = standalone_source_paths(repository_root)
    expected_by_manifest_key = {
        "graph": expected_source_paths["graph"],
        "candidate_fact_ledger": expected_source_paths["candidate_facts"],
        "base_resume": expected_source_paths["base_resume"],
    }
    for key in ("graph", "candidate_fact_ledger", "base_resume"):
        ref = generation.get(key)
        if not isinstance(ref, Mapping):
            raise StandaloneEmbeddingError(f"embedding manifest lacks {key} binding")
        path = _resolve_within(repository_root, str(ref.get("path") or ""), label=key)
        if path != expected_by_manifest_key[key].resolve():
            raise StandaloneEmbeddingError(
                f"{key} does not bind the canonical standalone source"
            )
        _require_file_digest(path, str(ref.get("file_sha256") or ""), label=key)
        payload = _load_object(path)
        if canonical_sha256(payload) != str(ref.get("canonical_sha256") or ""):
            raise StandaloneEmbeddingError(f"{key} canonical digest mismatch")
        source_payloads[key] = payload

    corpus_ref = generation.get("assertion_corpus")
    model_ref = generation.get("model")
    projection_ref = generation.get("projection")
    if not all(
        isinstance(value, Mapping) for value in (corpus_ref, model_ref, projection_ref)
    ):
        raise StandaloneEmbeddingError(
            "embedding generation artifact bindings are incomplete"
        )

    corpus_path = _resolve_within(
        generation_dir,
        str(corpus_ref.get("path") or ""),
        label="assertion corpus",
    )
    model_manifest_path = _resolve_within(
        generation_dir,
        str(model_ref.get("path") or ""),
        label="model manifest",
    )
    projection_path = _resolve_within(
        generation_dir,
        str(projection_ref.get("path") or ""),
        label="embedding projection",
    )
    _require_file_digest(
        corpus_path,
        str(corpus_ref.get("file_sha256") or ""),
        label="assertion corpus",
    )
    _require_file_digest(
        model_manifest_path,
        str(model_ref.get("manifest_file_sha256") or ""),
        label="model manifest",
    )
    _require_file_digest(
        projection_path,
        str(projection_ref.get("sqlite_sha256") or ""),
        label="embedding projection",
    )
    corpus = _load_object(corpus_path)
    model_manifest = _load_object(model_manifest_path)
    _require_self_digest(
        corpus,
        "corpus_sha256",
        label="assertion corpus",
        expected=str(corpus_ref.get("corpus_sha256") or ""),
    )
    _require_self_digest(
        model_manifest,
        "artifact_sha256",
        label="model manifest",
        expected=str(model_ref.get("artifact_sha256") or ""),
    )
    projection_issues = validate_embedding_projection(projection_path, corpus=corpus)
    if projection_issues:
        raise StandaloneEmbeddingError(
            "embedding projection validation failed: " + ", ".join(projection_issues)
        )
    runtime_contract = verify_embedding_runtime_contract(repository_root)
    _validate_model_runtime_contract(runtime_contract, model_manifest)
    runtime_proof = generation.get("runtime_proof")
    if not isinstance(runtime_proof, Mapping):
        raise StandaloneEmbeddingError("embedding generation runtime proof is missing")
    _validate_runtime_proof(runtime_contract, runtime_proof)
    return {
        "generation": generation,
        "generation_digest": generation_digest,
        "graph": source_payloads["graph"],
        "corpus": corpus,
        "model_manifest": model_manifest,
        "projection_path": projection_path,
        "referenced_paths": [corpus_path, model_manifest_path, projection_path],
        "runtime_contract": runtime_contract,
    }


def _qualification_thresholds(path: Path | str | None) -> dict[str, float | int]:
    if path is None:
        return dict(QUALIFICATION_THRESHOLDS)
    payload = _load_object(Path(path).resolve())
    thresholds = payload.get("thresholds", payload)
    if not isinstance(thresholds, Mapping):
        raise StandaloneEmbeddingError("qualification thresholds are not an object")
    return {str(key): threshold for key, threshold in thresholds.items()}


def qualify_candidate(
    *,
    repository_root: Path | str,
    generation_dir: Path | str,
    query_qrels_path: Path | str,
    model_path: Path | str | None,
    device: str | None,
    thresholds_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run legacy regression qualification for a candidate generation."""

    root = Path(repository_root).resolve()
    _assert_legacy_lane_open(root)
    output = Path(generation_dir).resolve()
    loaded = _load_generation(root, output)
    generation = loaded["generation"]
    corpus = loaded["corpus"]
    model_manifest = loaded["model_manifest"]
    runtime_contract = loaded["runtime_contract"]
    projection_path = loaded["projection_path"]
    local_model = build_local_model_manifest(_model_path(model_path))
    if local_model != model_manifest:
        raise StandaloneEmbeddingError("local BGE-M3 artifact digest mismatch")

    query_qrels = _load_object(Path(query_qrels_path).resolve())
    if query_qrels.get("schema_version") != QUERY_QREL_SCHEMA_VERSION:
        raise StandaloneEmbeddingError("query QREL schema mismatch")
    _require_self_digest(query_qrels, "query_qrel_sha256", label="query QRELs")
    queries = [row for row in query_qrels.get("queries") or [] if isinstance(row, dict)]
    if not queries:
        raise StandaloneEmbeddingError("query QRELs are empty")

    runtime_proof, query_vectors = encode_bge_m3(
        [str(query.get("query_text") or "") for query in queries],
        model_path=_model_path(model_path),
        device=_device(device),
        batch_size=len(queries),
    )
    _validate_runtime_proof(runtime_contract, runtime_proof)
    projection_before = _file_sha256(projection_path)
    dense_rankings: dict[str, list[dict[str, Any]]] = {}
    with GraphSkillEmbeddingIndex(
        projection_path,
        expected_corpus_sha256=str(corpus.get("corpus_sha256") or ""),
        expected_model_artifact_sha256=str(model_manifest.get("artifact_sha256") or ""),
    ) as index:
        for query, vector in zip(queries, query_vectors, strict=True):
            dense_rankings[str(query.get("query_id") or "")] = index.query(
                vector,
                k=len(corpus.get("assertions") or []),
            )
    projection_after = _file_sha256(projection_path)
    projection_issues = validate_embedding_projection(projection_path, corpus=corpus)
    if projection_before != projection_after:
        projection_issues.append("PROJECTION_MUTATED_DURING_QUALIFICATION")

    thresholds = _qualification_thresholds(thresholds_path)
    report = evaluate_graph_embedding_qualification(
        graph_payload=loaded["graph"],
        corpus=corpus,
        query_qrels=query_qrels,
        dense_rankings=dense_rankings,
        thresholds=thresholds,
        projection_issues=projection_issues,
    )
    report.pop("qualification_sha256", None)
    report.update(
        {
            "embedding_generation_manifest_sha256": loaded["generation_digest"],
            "projection": {
                "generation_sha256": generation["projection"]["generation_sha256"],
                "sqlite_sha256_before": projection_before,
                "sqlite_sha256_after": projection_after,
                "read_only": projection_before == projection_after,
                "vector_count": generation["projection"]["vector_count"],
                "dimension": generation["projection"]["dimension"],
            },
            "model": {
                "model_id": model_manifest["model_id"],
                "revision": model_manifest["revision"],
                "artifact_sha256": model_manifest["artifact_sha256"],
            },
            "runtime_proof": runtime_proof,
            "runtime_contract": _runtime_contract_evidence(runtime_contract),
            "network_used": False,
            "fallback_used": False,
            "qualification_scope": QUALIFICATION_SCOPE,
            "release_authorizing": False,
            "completion_marker": (
                "GRAPH_EMBEDDINGS_QUALIFIED"
                if report["status"] == "PASS"
                else "GRAPH_EMBEDDING_QUALIFICATION_FAILED"
            ),
        }
    )
    report["qualification_sha256"] = canonical_sha256(report)

    query_path = output / (
        f"graph_embedding_query_qrels.{query_qrels['query_qrel_sha256']}.json"
    )
    thresholds_payload: dict[str, Any] = {
        "schema_version": "apps_rg.c03_graph_embedding_qualification_thresholds.v1",
        "thresholds": thresholds,
    }
    thresholds_payload["thresholds_sha256"] = canonical_sha256(thresholds_payload)
    thresholds_file = output / (
        "graph_embedding_qualification_thresholds."
        f"{thresholds_payload['thresholds_sha256']}.json"
    )
    report_path = output / (
        f"graph_embedding_qualification.{report['qualification_sha256']}.json"
    )
    query_file_sha256 = _write_immutable_json(query_path, query_qrels)
    thresholds_file_sha256 = _write_immutable_json(thresholds_file, thresholds_payload)
    report_file_sha256 = _write_immutable_json(report_path, report)
    active_manifest: dict[str, Any] = {
        "schema_version": "apps_rg.c03_graph_embedding_qualification_manifest.v1",
        "status": report["status"],
        "completion_marker": report["completion_marker"],
        "qualification_scope": QUALIFICATION_SCOPE,
        "release_authorizing": False,
        "query_qrels": {
            "path": query_path.name,
            "sha256": query_qrels["query_qrel_sha256"],
            "file_sha256": query_file_sha256,
        },
        "thresholds": {
            "path": thresholds_file.name,
            "sha256": thresholds_payload["thresholds_sha256"],
            "file_sha256": thresholds_file_sha256,
        },
        "qualification": {
            "path": report_path.name,
            "sha256": report["qualification_sha256"],
            "file_sha256": report_file_sha256,
        },
        "embedding_generation_manifest_sha256": loaded["generation_digest"],
    }
    active_manifest["manifest_sha256"] = canonical_sha256(active_manifest)
    _write_atomic_bytes(
        output / QUALIFICATION_MANIFEST_NAME, _render_json(active_manifest)
    )
    return report


def validate_candidate_bundle(
    *,
    repository_root: Path | str,
    candidate_dir: Path | str,
) -> dict[str, Any]:
    """Validate a self-contained candidate before it can replace active manifests."""

    root = Path(repository_root).resolve()
    candidate = Path(candidate_dir).resolve()
    loaded = _load_generation(root, candidate)
    qualification_manifest = _load_object(candidate / QUALIFICATION_MANIFEST_NAME)
    qualification_manifest_sha256 = _require_self_digest(
        qualification_manifest,
        "manifest_sha256",
        label="embedding qualification manifest",
    )
    if qualification_manifest.get("status") != "PASS":
        raise StandaloneEmbeddingError("embedding qualification is not PASS")
    if qualification_manifest.get("completion_marker") != "GRAPH_EMBEDDINGS_QUALIFIED":
        raise StandaloneEmbeddingError("embedding qualification marker is missing")
    if qualification_manifest.get("qualification_scope") != QUALIFICATION_SCOPE:
        raise StandaloneEmbeddingError(
            "embedding qualification scope is not regression-only"
        )
    if qualification_manifest.get("release_authorizing") is not False:
        raise StandaloneEmbeddingError(
            "embedding qualification must be non-release-authorizing"
        )
    if (
        qualification_manifest.get("embedding_generation_manifest_sha256")
        != loaded["generation_digest"]
    ):
        raise StandaloneEmbeddingError("qualification/generation digest mismatch")

    referenced_paths = list(loaded["referenced_paths"])
    qualification_payloads: dict[str, dict[str, Any]] = {}
    digest_fields = {
        "query_qrels": "query_qrel_sha256",
        "thresholds": "thresholds_sha256",
        "qualification": "qualification_sha256",
    }
    for key, digest_field in digest_fields.items():
        ref = qualification_manifest.get(key)
        if not isinstance(ref, Mapping):
            raise StandaloneEmbeddingError(
                f"qualification manifest lacks {key} binding"
            )
        path = _resolve_within(candidate, str(ref.get("path") or ""), label=key)
        _require_file_digest(path, str(ref.get("file_sha256") or ""), label=key)
        payload = _load_object(path)
        _require_self_digest(
            payload,
            digest_field,
            label=key,
            expected=str(ref.get("sha256") or ""),
        )
        qualification_payloads[key] = payload
        referenced_paths.append(path)

    report = qualification_payloads["qualification"]
    query_qrels = qualification_payloads["query_qrels"]
    thresholds_payload = qualification_payloads["thresholds"]
    thresholds = thresholds_payload.get("thresholds")
    if not isinstance(thresholds, Mapping):
        raise StandaloneEmbeddingError("qualification thresholds payload is malformed")
    graph_sha256 = str(
        (loaded["corpus"].get("source_digests") or {}).get("graph_sha256") or ""
    )
    if report.get("status") != "PASS" or report.get("failures") not in ([], None):
        raise StandaloneEmbeddingError("qualification report failed")
    if report.get("projection_issues") not in ([], None):
        raise StandaloneEmbeddingError("qualification report has projection issues")
    if (
        report.get("embedding_generation_manifest_sha256")
        != loaded["generation_digest"]
    ):
        raise StandaloneEmbeddingError(
            "qualification report generation digest mismatch"
        )
    if report.get("corpus_sha256") != loaded["corpus"].get("corpus_sha256"):
        raise StandaloneEmbeddingError("qualification report corpus digest mismatch")
    if report.get("graph_sha256") != graph_sha256:
        raise StandaloneEmbeddingError("qualification report graph digest mismatch")
    if (
        report.get("network_used") is not False
        or report.get("fallback_used") is not False
    ):
        raise StandaloneEmbeddingError("qualification permits network or fallback")
    if report.get("qualification_scope") != QUALIFICATION_SCOPE:
        raise StandaloneEmbeddingError(
            "qualification report scope is not regression-only"
        )
    if report.get("release_authorizing") is not False:
        raise StandaloneEmbeddingError(
            "qualification report must be non-release-authorizing"
        )
    if report.get("query_qrel_sha256") != query_qrels.get("query_qrel_sha256"):
        raise StandaloneEmbeddingError(
            "qualification report/query QREL digest mismatch"
        )
    if report.get("thresholds") != dict(thresholds):
        raise StandaloneEmbeddingError(
            "qualification report/threshold payload mismatch"
        )
    if report.get("thresholds_sha256") != canonical_sha256(dict(thresholds)):
        raise StandaloneEmbeddingError("qualification report threshold digest mismatch")
    runtime_contract = loaded["runtime_contract"]
    if report.get("runtime_contract") != _runtime_contract_evidence(runtime_contract):
        raise StandaloneEmbeddingError("qualification report runtime contract mismatch")

    return {
        "status": "PASS",
        "generation_manifest_sha256": loaded["generation_digest"],
        "qualification_manifest_sha256": qualification_manifest_sha256,
        "qualification_sha256": report["qualification_sha256"],
        "qualification_scope": qualification_manifest.get("qualification_scope"),
        "release_authorizing": qualification_manifest.get("release_authorizing")
        is True,
        "graph_sha256": graph_sha256,
        "corpus_sha256": loaded["corpus"].get("corpus_sha256"),
        "vector_count": loaded["generation"]["projection"]["vector_count"],
        "dimension": loaded["generation"]["projection"]["dimension"],
        "referenced_paths": referenced_paths,
    }


def _restore_manifest(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        _write_atomic_bytes(path, previous)


def activate_candidate(
    *,
    repository_root: Path | str,
    candidate_dir: Path | str,
) -> dict[str, Any]:
    """Promote a validated candidate while retaining immutable prior generations."""

    root = Path(repository_root).resolve()
    _assert_legacy_lane_open(root)
    candidate = Path(candidate_dir).resolve()
    active = _active_artifact_dir(root)
    if _is_within(candidate, active):
        raise StandaloneEmbeddingError(
            "candidate directory must differ from active directory and must not be inside it"
        )
    validated = validate_candidate_bundle(repository_root=root, candidate_dir=candidate)
    active.mkdir(parents=True, exist_ok=True)
    for source in validated["referenced_paths"]:
        _copy_immutable(source, active / source.name)

    candidate_generation_path = candidate / GENERATION_MANIFEST_NAME
    candidate_qualification_path = candidate / QUALIFICATION_MANIFEST_NAME
    immutable_generation_path = active / (
        "graph_skill_embedding_manifest."
        f"{validated['generation_manifest_sha256']}.json"
    )
    immutable_qualification_path = active / (
        "graph_embedding_qualification_manifest."
        f"{validated['qualification_manifest_sha256']}.json"
    )
    _copy_immutable(candidate_generation_path, immutable_generation_path)
    _copy_immutable(candidate_qualification_path, immutable_qualification_path)
    immutable_generation_file_sha256 = _file_sha256(immutable_generation_path)
    immutable_qualification_file_sha256 = _file_sha256(immutable_qualification_path)

    generation_path = active / GENERATION_MANIFEST_NAME
    qualification_path = active / QUALIFICATION_MANIFEST_NAME
    previous_generation = (
        generation_path.read_bytes() if generation_path.exists() else None
    )
    previous_qualification = (
        qualification_path.read_bytes() if qualification_path.exists() else None
    )
    activation_path = active / ACTIVATION_MANIFEST_NAME
    previous_activation = (
        activation_path.read_bytes() if activation_path.exists() else None
    )
    receipt_path: Path | None = None
    receipt_existed = False
    try:
        _write_atomic_bytes(
            qualification_path,
            (candidate / QUALIFICATION_MANIFEST_NAME).read_bytes(),
        )
        _write_atomic_bytes(
            generation_path,
            (candidate / GENERATION_MANIFEST_NAME).read_bytes(),
        )
        authority = load_graph_skill_embedding_authority(root)
        if authority["manifest_sha256"] != validated["generation_manifest_sha256"]:
            raise StandaloneEmbeddingError("activated generation digest mismatch")
        if (
            authority["qualification"]["qualification_sha256"]
            != validated["qualification_sha256"]
        ):
            raise StandaloneEmbeddingError("activated qualification digest mismatch")

        previous_digest = ""
        if previous_generation is not None:
            previous_payload = json.loads(previous_generation)
            if isinstance(previous_payload, dict):
                previous_digest = str(previous_payload.get("manifest_sha256") or "")
        receipt: dict[str, Any] = {
            "schema_version": "apps_rg.graph_skill_embedding_activation_receipt.v1",
            "status": "PASS",
            "previous_generation_manifest_sha256": previous_digest,
            "active_generation_manifest_sha256": authority["manifest_sha256"],
            "active_qualification_sha256": authority["qualification"][
                "qualification_sha256"
            ],
            "generation_manifest": {
                "path": immutable_generation_path.name,
                "sha256": validated["generation_manifest_sha256"],
                "file_sha256": immutable_generation_file_sha256,
            },
            "qualification_manifest": {
                "path": immutable_qualification_path.name,
                "sha256": validated["qualification_manifest_sha256"],
                "file_sha256": immutable_qualification_file_sha256,
            },
            "graph_sha256": authority["graph_sha256"],
            "corpus_sha256": authority["corpus_sha256"],
            "embedding_generation_sha256": authority["embedding_generation_sha256"],
            "model_artifact_sha256": authority["model_artifact_sha256"],
            "vector_count": authority["assertion_count"],
            "dimension": authority["model_dimension"],
            "qualification_scope": validated["qualification_scope"],
            "release_authorizing": validated["release_authorizing"],
            "graph_mutated": False,
        }
        receipt["activation_receipt_sha256"] = canonical_sha256(receipt)
        receipt_path = active / (
            "graph_skill_embedding_activation."
            f"{receipt['activation_receipt_sha256']}.json"
        )
        receipt_existed = receipt_path.exists()
        receipt_file_sha256 = _write_immutable_json(receipt_path, receipt)
        activation_manifest: dict[str, Any] = {
            "schema_version": "apps_rg.graph_skill_embedding_activation_manifest.v1",
            "status": "PASS",
            "activation_receipt": {
                "path": receipt_path.name,
                "sha256": receipt["activation_receipt_sha256"],
                "file_sha256": receipt_file_sha256,
            },
            "active_generation_manifest_sha256": authority["manifest_sha256"],
            "active_qualification_sha256": authority["qualification"][
                "qualification_sha256"
            ],
            "generation_manifest": receipt["generation_manifest"],
            "qualification_manifest": receipt["qualification_manifest"],
        }
        activation_manifest["manifest_sha256"] = canonical_sha256(activation_manifest)
        _write_atomic_bytes(activation_path, _render_json(activation_manifest))
    except Exception:
        _restore_manifest(generation_path, previous_generation)
        _restore_manifest(qualification_path, previous_qualification)
        _restore_manifest(activation_path, previous_activation)
        if receipt_path is not None and not receipt_existed:
            receipt_path.unlink(missing_ok=True)
        raise
    return receipt


def preflight(
    *,
    repository_root: Path | str,
    artifact_dir: Path | str | None = None,
    model_path: Path | str | None = None,
    device: str | None = None,
    verify_runtime: bool = False,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    _assert_legacy_lane_open(root)
    paths = standalone_source_paths(root)
    missing = [label for label, path in paths.items() if not path.is_file()]
    if missing:
        raise StandaloneEmbeddingError(
            "standalone embedding sources are missing: " + ", ".join(sorted(missing))
        )
    graph = _load_object(paths["graph"])
    if reconcile_graph_authority(graph) != graph:
        raise StandaloneEmbeddingError("canonical graph requires reconciliation")
    selected = (
        Path(artifact_dir).resolve() if artifact_dir else _active_artifact_dir(root)
    )
    if selected == _active_artifact_dir(root):
        authority = load_graph_skill_embedding_authority(root)
        result = {
            "status": "PASS",
            "artifact_dir": str(selected),
            "graph_path": str(paths["graph"]),
            "graph_sha256": authority["graph_sha256"],
            "corpus_sha256": authority["corpus_sha256"],
            "vector_count": authority["assertion_count"],
            "dimension": authority["model_dimension"],
            "qualification_status": authority["qualification_status"],
            "qualification_scope": authority["qualification_scope"],
            "release_authorizing": authority["release_authorizing"],
        }
        if verify_runtime:
            runtime_contract = verify_embedding_runtime_contract(root)
            local_model = build_local_model_manifest(_model_path(model_path))
            _validate_model_runtime_contract(runtime_contract, local_model)
            if local_model != authority["_model_manifest"]:
                raise StandaloneEmbeddingError("local BGE-M3 artifact digest mismatch")
            requested_device = _device(device)
            if requested_device != runtime_contract["promoted_device"]:
                raise StandaloneEmbeddingError(
                    "preflight device does not match the promoted runtime contract"
                )
            if requested_device.startswith("cuda"):
                import torch

                if not torch.cuda.is_available():
                    raise StandaloneEmbeddingError("CUDA requested but unavailable")
            result["runtime_contract"] = _runtime_contract_evidence(runtime_contract)
            result["device"] = requested_device
        return result
    validated = validate_candidate_bundle(repository_root=root, candidate_dir=selected)
    return {
        key: value for key, value in validated.items() if key != "referenced_paths"
    } | {"artifact_dir": str(selected)}


def smoke_query(
    *,
    repository_root: Path | str,
    query_text: str,
    section_id: str,
    model_path: Path | str | None,
    device: str | None,
    k: int,
) -> dict[str, Any]:
    _assert_legacy_lane_open(repository_root)
    if not query_text.strip():
        raise StandaloneEmbeddingError("smoke query text is empty")
    if k <= 0:
        raise StandaloneEmbeddingError("smoke query k must be positive")
    root = Path(repository_root).resolve()
    authority = load_graph_skill_embedding_authority(root)
    runtime_contract = verify_embedding_runtime_contract(root)
    _validate_model_runtime_contract(runtime_contract, authority["_model_manifest"])
    local_model = build_local_model_manifest(_model_path(model_path))
    if local_model != authority["_model_manifest"]:
        raise StandaloneEmbeddingError("local BGE-M3 artifact digest mismatch")
    runtime_proof, vectors = encode_bge_m3(
        [query_text],
        model_path=_model_path(model_path),
        device=_device(device),
        batch_size=1,
    )
    _validate_runtime_proof(runtime_contract, runtime_proof)
    with GraphSkillEmbeddingIndex(
        Path(authority["projection_path"]),
        expected_corpus_sha256=authority["corpus_sha256"],
        expected_model_artifact_sha256=authority["model_artifact_sha256"],
    ) as index:
        dense_candidates = index.query(
            vectors[0],
            k=len(authority["_corpus_payload"].get("assertions") or []),
            section_id=section_id,
        )
    bm25_documents = {
        str(assertion.get("assertion_id") or ""): str(assertion.get("embedding_text") or "")
        for assertion in authority["_corpus_payload"].get("assertions") or []
        if isinstance(assertion, Mapping)
        and section_id in (assertion.get("allowed_sections") or [])
    }
    fused_candidates = fuse_dense_bm25(
        dense_candidates,
        bm25_rank(query_text, bm25_documents),
        assertion_ids=set(bm25_documents),
        rank_constant=int(QUALIFICATION_THRESHOLDS["rrf_rank_constant"]),
    )[:k]
    hydrated = rehydrate_assertion_candidates(
        [
            {"assertion_id": str(row["assertion_id"]), "similarity": float(row["rrf_score"])}
            for row in fused_candidates
        ],
        corpus=authority["_corpus_payload"],
        graph_payload=authority["_graph_payload"],
        section_id=section_id,
    )
    return {
        "status": "PASS",
        "retrieval_mode": "dense_bm25_rrf",
        "section_id": section_id,
        "query_sha256": hashlib.sha256(query_text.encode("utf-8")).hexdigest(),
        "candidate_count": len(hydrated),
        "candidates": [
            {
                "assertion_id": row["assertion_id"],
                "rrf_score": row["similarity"],
                "dense_similarity": fused_candidates[position]["dense_similarity"],
                "bm25_score": fused_candidates[position]["bm25_score"],
                "dense_rank": fused_candidates[position]["dense_rank"],
                "bm25_rank": fused_candidates[position]["bm25_rank"],
                "label": row["semantic_card"]["label"],
            }
            for position, row in enumerate(hydrated)
        ],
        "runtime_proof": runtime_proof,
        "exact_rehydration_pass": True,
        "qualification_scope": authority["qualification_scope"],
        "release_authorizing": authority["release_authorizing"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--artifact-dir", type=Path)
    preflight_parser.add_argument("--model-path", type=Path)
    preflight_parser.add_argument("--device")

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--model-path", type=Path)
    build_parser.add_argument("--device")

    qualify_parser = subparsers.add_parser("qualify")
    qualify_parser.add_argument("--generation-dir", type=Path, required=True)
    qualify_parser.add_argument("--query-qrels", type=Path, required=True)
    qualify_parser.add_argument("--thresholds", type=Path)
    qualify_parser.add_argument("--model-path", type=Path)
    qualify_parser.add_argument("--device")

    activate_parser = subparsers.add_parser("activate")
    activate_parser.add_argument("--candidate-dir", type=Path, required=True)

    rebuild_parser = subparsers.add_parser("rebuild")
    rebuild_parser.add_argument("--candidate-dir", type=Path, required=True)
    rebuild_parser.add_argument("--query-qrels", type=Path, required=True)
    rebuild_parser.add_argument("--thresholds", type=Path)
    rebuild_parser.add_argument("--model-path", type=Path)
    rebuild_parser.add_argument("--device")
    rebuild_parser.add_argument("--activate", action="store_true")

    smoke_parser = subparsers.add_parser("smoke")
    smoke_parser.add_argument("--query", required=True)
    smoke_parser.add_argument("--section", default="competencies")
    smoke_parser.add_argument("--model-path", type=Path)
    smoke_parser.add_argument("--device")
    smoke_parser.add_argument("--k", type=int, default=10)
    return parser


def _summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if not key.startswith("_") and key not in {"per_query"}
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.repo_root.resolve()
    try:
        if args.command == "preflight":
            result = preflight(
                repository_root=root,
                artifact_dir=args.artifact_dir,
                model_path=args.model_path,
                device=args.device,
                verify_runtime=True,
            )
        elif args.command == "build":
            generation = build_candidate(
                repository_root=root,
                output_dir=args.output_dir,
                model_path=args.model_path,
                device=args.device,
            )
            result = {
                "status": "PASS",
                "generation_manifest_sha256": generation["manifest_sha256"],
                "assertion_count": generation["assertion_corpus"]["assertion_count"],
                "projection": generation["projection"],
                "runtime_proof": generation["runtime_proof"],
            }
        elif args.command == "qualify":
            result = qualify_candidate(
                repository_root=root,
                generation_dir=args.generation_dir,
                query_qrels_path=args.query_qrels,
                model_path=args.model_path,
                device=args.device,
                thresholds_path=args.thresholds,
            )
        elif args.command == "activate":
            result = activate_candidate(
                repository_root=root,
                candidate_dir=args.candidate_dir,
            )
        elif args.command == "rebuild":
            generation = build_candidate(
                repository_root=root,
                output_dir=args.candidate_dir,
                model_path=args.model_path,
                device=args.device,
            )
            qualification = qualify_candidate(
                repository_root=root,
                generation_dir=args.candidate_dir,
                query_qrels_path=args.query_qrels,
                model_path=args.model_path,
                device=args.device,
                thresholds_path=args.thresholds,
            )
            result = {
                "status": qualification["status"],
                "generation_manifest_sha256": generation["manifest_sha256"],
                "qualification_sha256": qualification["qualification_sha256"],
                "retrieval_metrics": qualification["retrieval_metrics"],
                "retrieval_diagnostics": qualification["retrieval_diagnostics"],
                "structural_metrics": qualification["structural_metrics"],
                "runtime_proof": qualification["runtime_proof"],
                "qualification_scope": qualification["qualification_scope"],
                "release_authorizing": qualification["release_authorizing"],
            }
            if qualification["status"] == "PASS" and args.activate:
                result["activation"] = activate_candidate(
                    repository_root=root,
                    candidate_dir=args.candidate_dir,
                )
        elif args.command == "smoke":
            result = smoke_query(
                repository_root=root,
                query_text=args.query,
                section_id=args.section,
                model_path=args.model_path,
                device=args.device,
                k=args.k,
            )
        else:  # pragma: no cover - argparse enforces the command set
            raise StandaloneEmbeddingError(f"unsupported command: {args.command}")
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(_summary(result), indent=2))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
