from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from apps_rg.runtime.c0.graph_evidence_cluster_embedding_activation import (
    ACTIVE_CLUSTER_MANIFEST,
    GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV,
    GRAPH_EVIDENCE_CLUSTER_QUALIFICATION_SHA256_ENV,
    GraphEvidenceClusterEmbeddingActivationError,
    graph_evidence_cluster_embeddings_required,
    require_graph_evidence_cluster_embedding_activation,
    validate_cluster_release_qualification_receipt,
    validate_graph_evidence_cluster_activation_manifest,
)

_SOURCE_COMMIT = "a" * 40
_ARTIFACT_ROOT = "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings"
_SCHEMA_ROOT = (
    Path(__file__).resolve().parents[5]
    / "src/apps_rg/evals/authoritative/schemas"
)


def _validate_schema(filename: str, value: dict[str, object]) -> None:
    schema = json.loads((_SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _qualification(*, projection_sha256: str = "1" * 64) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": "apps_rg.cluster_release_qualification_receipt.v1",
        "status": "PASS",
        "completion_marker": "GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_QUALIFIED",
        "logical_retrieval_unit": "graph_evidence_cluster",
        "qualification_scope": "EVAL_W4_RELEASE_HOLDOUT",
        "source_commit": _SOURCE_COMMIT,
        "deployment_bindings": {
            "source_commit": _SOURCE_COMMIT,
            "graph_sha256": "2" * 64,
            "cluster_registry_sha256": "3" * 64,
            "corpus_sha256": "4" * 64,
            "model_artifact_sha256": "5" * 64,
            "projection_sha256": projection_sha256,
            "runtime_config_sha256": "6" * 64,
            "hardware_profile_sha256": "7" * 64,
            "candidate_activation_manifest_sha256": "8" * 64,
            "cluster_count": 35,
            "runtime_top_k": 5,
            "dimension": 1024,
            "normalization": "l2",
        },
        "input_receipt_digests": {
            "threshold_freeze": "1" * 64,
            "qrel_review": "2" * 64,
            "holdout_retrieval": "3" * 64,
            "authority_pipeline": "4" * 64,
            "runtime_quality": "5" * 64,
            "grounding": "6" * 64,
            "repeatability": "7" * 64,
            "evaluator_validity": "8" * 64,
            "holdout_controller": "9" * 64,
        },
        "checks": {
            "calibration_thresholds_frozen": True,
            "human_qrels_complete": True,
            "untouched_holdout_retrieval_passed": True,
            "authority_pipeline_zero_violations": True,
            "runtime_quality_passed": True,
            "grounding_passed": True,
            "controller_repeatability_passed": True,
            "evaluator_validity_passed": True,
            "holdout_controller_bound": True,
        },
        "failure_codes": [],
        "unknown_reasons": [],
        "legacy_regression_only_accepted": False,
        "release_authorizing": True,
    }
    receipt["record_digest"] = _canonical_sha256(receipt)
    return receipt


def _valid_manifest(
    *,
    projection_sha256: str = "1" * 64,
    qualification_file_sha256: str = "b" * 64,
    qualification_record_digest: str | None = None,
) -> dict[str, object]:
    qualification = _qualification(projection_sha256=projection_sha256)
    manifest: dict[str, object] = {
        "schema_version": (
            "apps_rg.graph_evidence_cluster_embedding_activation_manifest.v2"
        ),
        "status": "PASS",
        "completion_marker": "GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_QUALIFIED",
        "release_authorizing": True,
        "logical_retrieval_unit": "graph_evidence_cluster",
        "legacy_skill_vector_generation_active": False,
        "source_commit": _SOURCE_COMMIT,
        "qualification": {
            "path": f"{_ARTIFACT_ROOT}/release-qualification.json",
            "file_sha256": qualification_file_sha256,
            "record_digest": (
                qualification_record_digest or qualification["record_digest"]
            ),
        },
        "projection": {
            "path": f"{_ARTIFACT_ROOT}/projection.sqlite",
            "file_sha256": projection_sha256,
            "cluster_registry_sha256": "3" * 64,
            "corpus_sha256": "4" * 64,
            "model_artifact_sha256": "5" * 64,
            "graph_sha256": "2" * 64,
            "runtime_config_sha256": "6" * 64,
            "hardware_profile_sha256": "7" * 64,
            "cluster_count": 35,
            "top_k": 5,
            "dimension": 1024,
            "normalization": "l2",
            "exact_rehydration_required": True,
        },
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def _reseal_manifest(manifest: dict[str, object]) -> None:
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = _canonical_sha256(manifest)


def test_cluster_activation_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV, raising=False)
    assert graph_evidence_cluster_embeddings_required() is False


def test_cluster_activation_rejects_malformed_boolean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV, "maybe")
    with pytest.raises(GraphEvidenceClusterEmbeddingActivationError, match="boolean"):
        graph_evidence_cluster_embeddings_required()


def test_cluster_activation_fails_closed_without_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV, raising=False)
    with pytest.raises(
        GraphEvidenceClusterEmbeddingActivationError,
        match="not explicitly required",
    ):
        require_graph_evidence_cluster_embedding_activation(tmp_path)


def test_cluster_activation_fails_closed_when_manifest_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV, "1")
    with pytest.raises(
        GraphEvidenceClusterEmbeddingActivationError,
        match="missing or malformed",
    ):
        require_graph_evidence_cluster_embedding_activation(tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("release_authorizing", False, "not release authorizing"),
        (
            "logical_retrieval_unit",
            "skill",
            "logical retrieval unit is invalid",
        ),
        (
            "legacy_skill_vector_generation_active",
            True,
            "legacy skill-vector generation must be retired",
        ),
    ],
)
def test_cluster_activation_rejects_non_promotable_manifests(
    field: str,
    value: object,
    message: str,
) -> None:
    manifest = _valid_manifest()
    manifest[field] = value
    _reseal_manifest(manifest)
    with pytest.raises(GraphEvidenceClusterEmbeddingActivationError, match=message):
        validate_graph_evidence_cluster_activation_manifest(manifest)


def test_cluster_activation_rejects_v1_self_declared_release() -> None:
    manifest = _valid_manifest()
    manifest["schema_version"] = (
        "apps_rg.graph_evidence_cluster_embedding_activation_manifest.v1"
    )
    _reseal_manifest(manifest)

    with pytest.raises(
        GraphEvidenceClusterEmbeddingActivationError,
        match="schema is invalid",
    ):
        validate_graph_evidence_cluster_activation_manifest(manifest)


def test_release_qualification_rejects_legacy_regression_receipt() -> None:
    legacy = {
        "schema_version": "apps_rg.graph_embedding_qualification_report.v1",
        "status": "PASS",
        "qualification_scope": "REGRESSION_ONLY",
        "release_authorizing": False,
    }

    with pytest.raises(
        GraphEvidenceClusterEmbeddingActivationError,
        match="receipt schema is invalid",
    ):
        validate_cluster_release_qualification_receipt(legacy)


def _write_active_chain(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    projection_path = tmp_path / f"{_ARTIFACT_ROOT}/projection.sqlite"
    projection_path.parent.mkdir(parents=True)
    projection_path.write_bytes(b"cluster projection")
    projection_sha256 = hashlib.sha256(projection_path.read_bytes()).hexdigest()
    qualification = _qualification(projection_sha256=projection_sha256)
    qualification_path = tmp_path / f"{_ARTIFACT_ROOT}/release-qualification.json"
    qualification_path.write_text(json.dumps(qualification), encoding="utf-8")
    qualification_file_sha256 = hashlib.sha256(
        qualification_path.read_bytes()
    ).hexdigest()
    manifest = _valid_manifest(
        projection_sha256=projection_sha256,
        qualification_file_sha256=qualification_file_sha256,
        qualification_record_digest=str(qualification["record_digest"]),
    )
    path = tmp_path / ACTIVE_CLUSTER_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest, qualification


def test_cluster_activation_accepts_exact_external_release_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, qualification = _write_active_chain(tmp_path)
    monkeypatch.setenv(GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV, "true")
    qualification_ref = manifest["qualification"]
    assert isinstance(qualification_ref, dict)
    monkeypatch.setenv(
        GRAPH_EVIDENCE_CLUSTER_QUALIFICATION_SHA256_ENV,
        str(qualification_ref["file_sha256"]),
    )

    authority = require_graph_evidence_cluster_embedding_activation(tmp_path)

    assert authority["logical_retrieval_unit"] == "graph_evidence_cluster"
    assert authority["manifest_sha256"] == manifest["manifest_sha256"]
    assert authority["projection"] == manifest["projection"]
    assert authority["qualification"]["record_digest"] == qualification[
        "record_digest"
    ]
    _validate_schema("cluster_activation_manifest.v2.schema.json", manifest)
    _validate_schema(
        "cluster_release_qualification_receipt.v1.schema.json",
        qualification,
    )


def test_cluster_activation_requires_external_qualification_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_active_chain(tmp_path)
    monkeypatch.setenv(GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV, "true")
    monkeypatch.delenv(
        GRAPH_EVIDENCE_CLUSTER_QUALIFICATION_SHA256_ENV,
        raising=False,
    )

    with pytest.raises(
        GraphEvidenceClusterEmbeddingActivationError,
        match="external cluster qualification file SHA-256 is required",
    ):
        require_graph_evidence_cluster_embedding_activation(tmp_path)


def test_cluster_activation_rejects_tampered_qualification_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_active_chain(tmp_path)
    qualification_path = tmp_path / f"{_ARTIFACT_ROOT}/release-qualification.json"
    qualification_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV, "true")
    monkeypatch.setenv(
        GRAPH_EVIDENCE_CLUSTER_QUALIFICATION_SHA256_ENV,
        hashlib.sha256(qualification_path.read_bytes()).hexdigest(),
    )

    with pytest.raises(
        GraphEvidenceClusterEmbeddingActivationError,
        match="qualification file digest is invalid",
    ):
        require_graph_evidence_cluster_embedding_activation(tmp_path)


def test_cluster_activation_rejects_projection_binding_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _qualification_receipt = _write_active_chain(tmp_path)
    projection = manifest["projection"]
    assert isinstance(projection, dict)
    projection["corpus_sha256"] = "f" * 64
    _reseal_manifest(manifest)
    (tmp_path / ACTIVE_CLUSTER_MANIFEST).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    monkeypatch.setenv(GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_REQUIRED_ENV, "true")
    qualification_ref = manifest["qualification"]
    assert isinstance(qualification_ref, dict)
    monkeypatch.setenv(
        GRAPH_EVIDENCE_CLUSTER_QUALIFICATION_SHA256_ENV,
        str(qualification_ref["file_sha256"]),
    )

    with pytest.raises(
        GraphEvidenceClusterEmbeddingActivationError,
        match="differs from release qualification bindings",
    ):
        require_graph_evidence_cluster_embedding_activation(tmp_path)
