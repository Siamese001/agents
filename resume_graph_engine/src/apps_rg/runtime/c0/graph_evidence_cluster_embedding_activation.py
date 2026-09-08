"""Fail-closed activation boundary for future graph-evidence cluster embeddings."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV = (
    "APPS_RG_GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED"
)
GRAPH_EVIDENCE_CLUSTER_QUALIFICATION_SHA256_ENV = (
    "APPS_RG_GRAPH_EVIDENCE_CLUSTER_QUALIFICATION_SHA256"
)
ACTIVE_CLUSTER_MANIFEST = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "graph_evidence_cluster_embedding_activation_manifest.json"
)
ACTIVATION_SCHEMA_VERSION = (
    "apps_rg.graph_evidence_cluster_embedding_activation_manifest.v2"
)
ACTIVATION_COMPLETION_MARKER = "GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_QUALIFIED"
QUALIFICATION_SCHEMA_VERSION = "apps_rg.cluster_release_qualification_receipt.v1"
QUALIFICATION_SCOPE = "EVAL_W4_RELEASE_HOLDOUT"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})
_ACTIVE_CLUSTER_ARTIFACT_DIR = ACTIVE_CLUSTER_MANIFEST.parent
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "completion_marker",
        "release_authorizing",
        "logical_retrieval_unit",
        "legacy_skill_vector_generation_active",
        "source_commit",
        "qualification",
        "projection",
        "manifest_sha256",
    }
)
_QUALIFICATION_REF_FIELDS = frozenset({"path", "file_sha256", "record_digest"})
_PROJECTION_FIELDS = frozenset(
    {
        "path",
        "file_sha256",
        "cluster_registry_sha256",
        "corpus_sha256",
        "model_artifact_sha256",
        "graph_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
        "cluster_count",
        "top_k",
        "dimension",
        "normalization",
        "exact_rehydration_required",
    }
)
_QUALIFICATION_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "completion_marker",
        "logical_retrieval_unit",
        "qualification_scope",
        "source_commit",
        "deployment_bindings",
        "input_receipt_digests",
        "checks",
        "failure_codes",
        "unknown_reasons",
        "legacy_regression_only_accepted",
        "release_authorizing",
        "record_digest",
    }
)
_QUALIFICATION_DEPLOYMENT_FIELDS = frozenset(
    {
        "source_commit",
        "graph_sha256",
        "cluster_registry_sha256",
        "corpus_sha256",
        "model_artifact_sha256",
        "projection_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
        "candidate_activation_manifest_sha256",
        "cluster_count",
        "runtime_top_k",
        "dimension",
        "normalization",
    }
)
_QUALIFICATION_INPUTS = frozenset(
    {
        "threshold_freeze",
        "qrel_review",
        "holdout_retrieval",
        "authority_pipeline",
        "runtime_quality",
        "grounding",
        "repeatability",
        "evaluator_validity",
        "holdout_controller",
    }
)
_QUALIFICATION_CHECKS = frozenset(
    {
        "calibration_thresholds_frozen",
        "human_qrels_complete",
        "untouched_holdout_retrieval_passed",
        "authority_pipeline_zero_violations",
        "runtime_quality_passed",
        "grounding_passed",
        "controller_repeatability_passed",
        "evaluator_validity_passed",
        "holdout_controller_bound",
    }
)


class GraphEvidenceClusterEmbeddingActivationError(RuntimeError):
    """Raised when cluster embedding activation cannot prove its authority."""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    normalized = str(value or "")
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _is_source_commit(value: object) -> bool:
    normalized = str(value or "")
    return len(normalized) == 40 and all(
        character in "0123456789abcdef" for character in normalized
    )


def validate_cluster_release_qualification_receipt(
    receipt: Mapping[str, Any],
) -> str:
    """Validate the only receipt schema allowed to grant cluster release authority."""

    if set(receipt) != _QUALIFICATION_FIELDS:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification receipt schema is invalid"
        )
    if receipt.get("schema_version") != QUALIFICATION_SCHEMA_VERSION:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification schema is invalid"
        )
    if receipt.get("status") != "PASS":
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification status is not PASS"
        )
    if receipt.get("completion_marker") != ACTIVATION_COMPLETION_MARKER:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification marker is invalid"
        )
    if receipt.get("qualification_scope") != QUALIFICATION_SCOPE:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification scope is invalid"
        )
    if receipt.get("logical_retrieval_unit") != "graph_evidence_cluster":
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release logical retrieval unit is invalid"
        )
    if receipt.get("release_authorizing") is not True:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification is not release authorizing"
        )
    if receipt.get("legacy_regression_only_accepted") is not False:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "legacy regression qualification cannot authorize cluster activation"
        )
    if receipt.get("failure_codes") != [] or receipt.get("unknown_reasons") != []:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification contains unresolved failures"
        )
    if not _is_source_commit(receipt.get("source_commit")):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification source commit is invalid"
        )
    deployment = receipt.get("deployment_bindings")
    if not isinstance(deployment, Mapping) or set(deployment) != (
        _QUALIFICATION_DEPLOYMENT_FIELDS
    ):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release deployment bindings are invalid"
        )
    for field in _QUALIFICATION_DEPLOYMENT_FIELDS - {
        "source_commit",
        "cluster_count",
        "runtime_top_k",
        "dimension",
        "normalization",
    }:
        if not _is_sha256(deployment.get(field)):
            raise GraphEvidenceClusterEmbeddingActivationError(
                f"cluster release deployment binding is invalid: {field}"
            )
    if deployment.get("source_commit") != receipt.get("source_commit"):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release deployment source commit is inconsistent"
        )
    cluster_count = deployment.get("cluster_count")
    top_k = deployment.get("runtime_top_k")
    if (
        not isinstance(cluster_count, int)
        or isinstance(cluster_count, bool)
        or cluster_count < 2
        or not isinstance(top_k, int)
        or isinstance(top_k, bool)
        or top_k < 1
        or top_k >= cluster_count
    ):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release deployment top_k is not bounded"
        )
    if deployment.get("dimension") != 1024 or deployment.get("normalization") != "l2":
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release deployment vector shape is invalid"
        )
    inputs = receipt.get("input_receipt_digests")
    if not isinstance(inputs, Mapping) or set(inputs) != _QUALIFICATION_INPUTS:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification input chain is incomplete"
        )
    if any(not _is_sha256(value) for value in inputs.values()):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification input digest is invalid"
        )
    checks = receipt.get("checks")
    if (
        not isinstance(checks, Mapping)
        or set(checks) != _QUALIFICATION_CHECKS
        or any(value is not True for value in checks.values())
    ):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification checks are incomplete"
        )
    unsigned = dict(receipt)
    recorded = str(unsigned.pop("record_digest", "") or "")
    if not _is_sha256(recorded) or recorded != _canonical_sha256(unsigned):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification receipt digest is invalid"
        )
    return recorded


def graph_evidence_cluster_embeddings_required() -> bool:
    """Return the explicit opt-in state; reject malformed boolean values."""

    raw = (
        str(os.environ.get(GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV) or "")
        .strip()
        .lower()
    )
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise GraphEvidenceClusterEmbeddingActivationError(
        f"{GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV} must be a boolean value"
    )


def _load_manifest(path: Path, *, label: str = "activation manifest") -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphEvidenceClusterEmbeddingActivationError(
            f"cluster embedding {label} is missing or malformed: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise GraphEvidenceClusterEmbeddingActivationError(
            f"cluster embedding {label} must be an object: {path}"
        )
    return payload


def validate_graph_evidence_cluster_activation_manifest(
    manifest: Mapping[str, Any],
) -> str:
    """Validate release authority and return the manifest's self digest."""

    if set(manifest) != _MANIFEST_FIELDS:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding activation manifest fields are invalid"
        )
    if manifest.get("schema_version") != ACTIVATION_SCHEMA_VERSION:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding activation schema is invalid"
        )
    if manifest.get("status") != "PASS":
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding activation status is not PASS"
        )
    if manifest.get("completion_marker") != ACTIVATION_COMPLETION_MARKER:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding qualification marker is invalid"
        )
    if manifest.get("release_authorizing") is not True:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding qualification is not release authorizing"
        )
    if manifest.get("logical_retrieval_unit") != "graph_evidence_cluster":
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding logical retrieval unit is invalid"
        )
    if manifest.get("legacy_skill_vector_generation_active") is not False:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "legacy skill-vector generation must be retired before cluster activation"
        )
    if not _is_source_commit(manifest.get("source_commit")):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding activation source commit is invalid"
        )
    qualification = manifest.get("qualification")
    if not isinstance(qualification, Mapping) or set(qualification) != (
        _QUALIFICATION_REF_FIELDS
    ):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding release qualification reference is missing"
        )
    if not str(qualification.get("path") or "").strip() or any(
        not _is_sha256(qualification.get(field))
        for field in ("file_sha256", "record_digest")
    ):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding release qualification reference is invalid"
        )
    projection = manifest.get("projection")
    if not isinstance(projection, Mapping) or set(projection) != _PROJECTION_FIELDS:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding projection authority is missing"
        )
    for field in (
        "path",
        "file_sha256",
        "cluster_registry_sha256",
        "corpus_sha256",
        "model_artifact_sha256",
        "graph_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
    ):
        if not str(projection.get(field) or "").strip():
            raise GraphEvidenceClusterEmbeddingActivationError(
                f"cluster embedding projection authority is missing {field}"
            )
    for field in (
        "file_sha256",
        "cluster_registry_sha256",
        "corpus_sha256",
        "model_artifact_sha256",
        "graph_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
    ):
        if not _is_sha256(projection.get(field)):
            raise GraphEvidenceClusterEmbeddingActivationError(
                f"cluster embedding projection authority has invalid {field}"
            )
    cluster_count = projection.get("cluster_count")
    top_k = projection.get("top_k")
    if (
        not isinstance(cluster_count, int)
        or isinstance(cluster_count, bool)
        or cluster_count < 2
    ):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding projection cluster_count must be at least two"
        )
    if (
        not isinstance(top_k, int)
        or isinstance(top_k, bool)
        or top_k < 1
        or top_k >= cluster_count
    ):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding projection top_k must be bounded below cluster_count"
        )
    if projection.get("dimension") != 1024 or projection.get("normalization") != "l2":
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding projection shape is invalid"
        )
    if projection.get("exact_rehydration_required") is not True:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding projection must require exact graph rehydration"
        )
    unsigned = dict(manifest)
    recorded = str(unsigned.pop("manifest_sha256", "") or "")
    observed = _canonical_sha256(unsigned)
    if not recorded or recorded != observed:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding activation manifest digest is invalid"
        )
    return recorded


def require_graph_evidence_cluster_embedding_activation(
    repo_root: Path | str,
) -> dict[str, Any]:
    """Load and validate cluster authority when the future lane is required.

    The call fails closed if the opt-in is absent, or if any release-authority
    binding is missing.  Wave 0 intentionally ships no active manifest.
    """

    if not graph_evidence_cluster_embeddings_required():
        raise GraphEvidenceClusterEmbeddingActivationError(
            "graph-evidence cluster embeddings are not explicitly required"
        )
    root = Path(repo_root).resolve()
    manifest_path = (root / ACTIVE_CLUSTER_MANIFEST).resolve()
    try:
        manifest_path.relative_to(root)
    except ValueError as exc:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding activation path escapes the repository root"
        ) from exc
    manifest = _load_manifest(manifest_path)
    manifest_sha256 = validate_graph_evidence_cluster_activation_manifest(manifest)
    artifact_root = (root / _ACTIVE_CLUSTER_ARTIFACT_DIR).resolve()
    qualification_ref = manifest["qualification"]
    qualification_path = (root / str(qualification_ref["path"])).resolve()
    try:
        qualification_path.relative_to(artifact_root)
    except ValueError as exc:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification path escapes the active artifact directory"
        ) from exc
    if qualification_path.is_symlink() or not qualification_path.is_file():
        raise GraphEvidenceClusterEmbeddingActivationError(
            f"cluster release qualification is missing: {qualification_path}"
        )
    observed_qualification_sha256 = _file_sha256(qualification_path)
    expected_qualification_sha256 = str(
        os.environ.get(GRAPH_EVIDENCE_CLUSTER_QUALIFICATION_SHA256_ENV) or ""
    ).strip()
    if not _is_sha256(expected_qualification_sha256):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "external cluster qualification file SHA-256 is required"
        )
    if observed_qualification_sha256 != expected_qualification_sha256:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification differs from the external SHA-256 pin"
        )
    if observed_qualification_sha256 != qualification_ref["file_sha256"]:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification file digest is invalid"
        )
    qualification = _load_manifest(
        qualification_path,
        label="release qualification receipt",
    )
    qualification_digest = validate_cluster_release_qualification_receipt(
        qualification
    )
    if qualification_digest != qualification_ref["record_digest"]:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster release qualification reference digest is invalid"
        )
    projection = manifest["projection"]
    projection_path = (root / str(projection["path"])).resolve()
    try:
        projection_path.relative_to(artifact_root)
    except ValueError as exc:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding projection path escapes the active artifact directory"
        ) from exc
    if projection_path.is_symlink() or not projection_path.is_file():
        raise GraphEvidenceClusterEmbeddingActivationError(
            f"cluster embedding projection is missing: {projection_path}"
        )
    observed_projection_sha256 = _file_sha256(projection_path)
    if observed_projection_sha256 != projection["file_sha256"]:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster embedding projection file digest is invalid"
        )
    deployment = qualification["deployment_bindings"]
    if manifest["source_commit"] != qualification["source_commit"]:
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster activation source commit differs from qualification"
        )
    deployment_projection_bindings = {
        "graph_sha256": "graph_sha256",
        "cluster_registry_sha256": "cluster_registry_sha256",
        "corpus_sha256": "corpus_sha256",
        "model_artifact_sha256": "model_artifact_sha256",
        "projection_sha256": "file_sha256",
        "runtime_config_sha256": "runtime_config_sha256",
        "hardware_profile_sha256": "hardware_profile_sha256",
        "cluster_count": "cluster_count",
        "runtime_top_k": "top_k",
        "dimension": "dimension",
        "normalization": "normalization",
    }
    if any(
        deployment[qualification_field] != projection[projection_field]
        for qualification_field, projection_field in deployment_projection_bindings.items()
    ):
        raise GraphEvidenceClusterEmbeddingActivationError(
            "cluster projection differs from release qualification bindings"
        )
    return {
        "manifest_path": ACTIVE_CLUSTER_MANIFEST.as_posix(),
        "manifest_sha256": manifest_sha256,
        "logical_retrieval_unit": "graph_evidence_cluster",
        "qualification": {
            "path": qualification_ref["path"],
            "file_sha256": qualification_ref["file_sha256"],
            "record_digest": qualification_digest,
        },
        "projection": dict(projection),
    }


__all__ = [
    "ACTIVATION_COMPLETION_MARKER",
    "ACTIVATION_SCHEMA_VERSION",
    "ACTIVE_CLUSTER_MANIFEST",
    "GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV",
    "GRAPH_EVIDENCE_CLUSTER_QUALIFICATION_SHA256_ENV",
    "GraphEvidenceClusterEmbeddingActivationError",
    "graph_evidence_cluster_embeddings_required",
    "require_graph_evidence_cluster_embedding_activation",
    "validate_cluster_release_qualification_receipt",
    "validate_graph_evidence_cluster_activation_manifest",
]
