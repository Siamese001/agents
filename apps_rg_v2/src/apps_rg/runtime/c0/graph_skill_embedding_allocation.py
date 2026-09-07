"""Fail-closed graph-skill embedding authority for whole-resume allocation."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_skill_assertion_corpus import (
    build_skill_assertion_corpus,
    canonical_sha256,
    validate_skill_assertion_corpus,
)
from apps_rg.fact_inventory.c03_legacy_embedding_retirement_wave5 import (
    RETIREMENT_MARKER,
    RETIREMENT_MARKER_PATH,
    LegacyEmbeddingRetirementWave5Error,
    validate_retirement_marker,
)
from apps_rg.repository_layout import resolve_apps_rg_path
from apps_rg.runtime.graph_skill_embedding_projection import (
    GraphSkillEmbeddingContractError,
    GraphSkillEmbeddingIndex,
    rehydrate_assertion_candidates,
    validate_embedding_projection,
)

GRAPH_SKILL_EMBEDDINGS_REQUIRED_ENV = "APPS_RG_GRAPH_SKILL_EMBEDDINGS_REQUIRED"
GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV = "APPS_RG_GRAPH_SKILL_EMBEDDING_ALLOWLISTS"
GRAPH_SKILL_EMBEDDING_DEVICE_ENV = "APPS_RG_GRAPH_SKILL_EMBEDDING_DEVICE"
EMBEDDING_MODEL_PATH_ENV = "APPS_RG_EMBEDDING_MODEL_PATH"

ALL_EMBEDDING_LANES: tuple[str, ...] = (
    "competencies",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "ey_bullets",
    "unify_narrative",
    "ibm_narrative",
    "insurtech_narrative",
    "ey_narrative",
    "executive_summary",
    "headline",
)
NARRATIVE_AUTHORITY_SECTIONS: Mapping[str, str] = {
    "unify_narrative": "unify_bullets",
    "ibm_narrative": "ibm_bullets",
    "insurtech_narrative": "insurtech_bullets",
    "ey_narrative": "ey_bullets",
}

_ACTIVE_ARTIFACT_DIR = Path("artifacts/apps_rg/c03/graph_skill_embeddings")
_ACTIVE_MANIFEST = "graph_skill_embedding_manifest.json"
_QUALIFICATION_MANIFEST = "graph_embedding_qualification_manifest.json"
_RUNTIME_CONTRACT = Path("tools/apps_rg_standalone/c03_embedding_runtime_contract.json")
_REGRESSION_QUALIFICATION_SCOPE = "REGRESSION_ONLY"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


class GraphSkillEmbeddingAllocationError(RuntimeError):
    """Raised when embedding authority cannot be bound before generation."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphSkillEmbeddingAllocationError(
            f"embedding authority artifact is missing or malformed: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise GraphSkillEmbeddingAllocationError(
            f"embedding authority artifact must be a JSON object: {path}"
        )
    return payload


def load_legacy_graph_skill_embedding_retirement(
    repo_root: Path | str,
) -> dict[str, Any] | None:
    """Return the valid W5 marker, or ``None`` before the lane is retired."""

    root = Path(repo_root).resolve()
    path = (root / RETIREMENT_MARKER_PATH).resolve()
    if not path.is_file():
        return None
    marker = _load_json_object(path)
    try:
        validate_retirement_marker(marker)
    except LegacyEmbeddingRetirementWave5Error as exc:
        raise GraphSkillEmbeddingAllocationError(
            f"legacy graph-skill embedding retirement marker is invalid: {exc}"
        ) from exc
    return marker


def assert_legacy_graph_skill_embedding_lane_not_retired(
    repo_root: Path | str,
) -> None:
    """Fail before manifest access when W5 has retired the legacy lane."""

    marker = load_legacy_graph_skill_embedding_retirement(repo_root)
    if marker is not None:
        raise GraphSkillEmbeddingAllocationError(
            "legacy one-vector-per-skill embedding lane is retired by "
            f"{RETIREMENT_MARKER}; use the graph-evidence cluster pipeline"
        )


def _resolve_within(root: Path, relative: str, *, label: str) -> Path:
    value = str(relative or "").strip()
    if not value:
        raise GraphSkillEmbeddingAllocationError(f"{label} path is missing")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise GraphSkillEmbeddingAllocationError(
            f"{label} path escapes its authority root"
        ) from exc
    return path


def _assert_file_digest(path: Path, expected: str, *, label: str) -> None:
    if not path.is_file():
        raise GraphSkillEmbeddingAllocationError(f"{label} is missing: {path}")
    observed = _file_sha256(path)
    if observed != str(expected or ""):
        raise GraphSkillEmbeddingAllocationError(
            f"{label} file digest mismatch: expected {expected}, observed {observed}"
        )


def _assert_self_digest(
    payload: Mapping[str, Any],
    field: str,
    *,
    expected: str | None = None,
    label: str,
) -> str:
    unsigned = dict(payload)
    recorded = str(unsigned.pop(field, "") or "")
    observed = canonical_sha256(unsigned)
    if not recorded or recorded != observed:
        raise GraphSkillEmbeddingAllocationError(
            f"{label} {field} mismatch: expected canonical {observed}, observed {recorded or '<missing>'}"
        )
    if expected is not None and recorded != expected:
        raise GraphSkillEmbeddingAllocationError(
            f"{label} digest mismatch: expected {expected}, observed {recorded}"
        )
    return recorded


def graph_skill_embeddings_required() -> bool:
    raw = str(os.environ.get(GRAPH_SKILL_EMBEDDINGS_REQUIRED_ENV) or "").strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise GraphSkillEmbeddingAllocationError(
        f"{GRAPH_SKILL_EMBEDDINGS_REQUIRED_ENV} must be a boolean value"
    )


def _load_runtime_contract(repo_root: Path) -> dict[str, Any]:
    path = (repo_root / _RUNTIME_CONTRACT).resolve()
    contract = _load_json_object(path)
    contract_sha256 = _assert_self_digest(
        contract,
        "contract_sha256",
        label="embedding runtime contract",
    )
    packages = contract.get("packages")
    model = contract.get("model")
    if not isinstance(packages, Mapping) or not isinstance(model, Mapping):
        raise GraphSkillEmbeddingAllocationError(
            "embedding runtime contract package/model bindings are missing"
        )
    if (
        contract.get("local_files_only") is not True
        or contract.get("network_allowed") is not False
        or contract.get("fallback_allowed") is not False
    ):
        raise GraphSkillEmbeddingAllocationError(
            "embedding runtime contract weakens offline execution"
        )
    return {
        "path": _RUNTIME_CONTRACT.as_posix(),
        "contract_sha256": contract_sha256,
        "python_major_minor": str(contract.get("python_major_minor") or ""),
        "packages": dict(packages),
        "promoted_device": str(contract.get("promoted_device") or ""),
        "_model": dict(model),
    }


def _validate_runtime_proof(
    runtime_proof: object,
    *,
    runtime_contract: Mapping[str, Any],
    label: str,
) -> None:
    if not isinstance(runtime_proof, Mapping):
        raise GraphSkillEmbeddingAllocationError(f"{label} runtime proof is missing")
    if runtime_proof.get("python_major_minor") != runtime_contract.get(
        "python_major_minor"
    ):
        raise GraphSkillEmbeddingAllocationError(f"{label} Python proof mismatch")
    packages = runtime_contract.get("packages") or {}
    if runtime_proof.get("torch_version") != packages.get("torch"):
        raise GraphSkillEmbeddingAllocationError(f"{label} Torch proof mismatch")
    if runtime_proof.get("sentence_transformers_version") != packages.get(
        "sentence-transformers"
    ):
        raise GraphSkillEmbeddingAllocationError(
            f"{label} Sentence Transformers proof mismatch"
        )
    promoted_device = str(runtime_contract.get("promoted_device") or "")
    if runtime_proof.get("device") != promoted_device:
        raise GraphSkillEmbeddingAllocationError(f"{label} device proof mismatch")
    if (
        promoted_device.startswith("cuda")
        and runtime_proof.get("cuda_available") is not True
    ):
        raise GraphSkillEmbeddingAllocationError(f"{label} CUDA proof is missing")
    expected_dimension = int(
        (runtime_contract.get("_model") or {}).get("dimension") or 0
    )
    if int(runtime_proof.get("dimension") or 0) != expected_dimension:
        raise GraphSkillEmbeddingAllocationError(f"{label} dimension proof mismatch")
    if runtime_proof.get("fallback_used") is not False:
        raise GraphSkillEmbeddingAllocationError(f"{label} used a fallback")


def _validate_qualification_artifacts(
    artifact_dir: Path,
    *,
    embedding_manifest_sha256: str,
    corpus_sha256: str,
    graph_sha256: str,
    runtime_contract: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path = artifact_dir / _QUALIFICATION_MANIFEST
    manifest = _load_json_object(manifest_path)
    manifest_sha256 = _assert_self_digest(
        manifest,
        "manifest_sha256",
        label="embedding qualification manifest",
    )
    if manifest.get("status") != "PASS":
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification is not PASS"
        )
    if manifest.get("completion_marker") != "GRAPH_EMBEDDINGS_QUALIFIED":
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification marker is missing"
        )
    if manifest.get("qualification_scope") != _REGRESSION_QUALIFICATION_SCOPE:
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification scope is not regression-only"
        )
    if manifest.get("release_authorizing") is not False:
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification must be non-release-authorizing"
        )
    if (
        manifest.get("embedding_generation_manifest_sha256")
        != embedding_manifest_sha256
    ):
        raise GraphSkillEmbeddingAllocationError(
            "qualification/embedding generation manifest digest mismatch"
        )

    loaded: dict[str, dict[str, Any]] = {}
    digest_fields = {
        "query_qrels": "query_qrel_sha256",
        "thresholds": "thresholds_sha256",
        "qualification": "qualification_sha256",
    }
    for key, digest_field in digest_fields.items():
        ref = manifest.get(key)
        if not isinstance(ref, Mapping):
            raise GraphSkillEmbeddingAllocationError(
                f"embedding qualification manifest lacks {key} binding"
            )
        path = _resolve_within(artifact_dir, str(ref.get("path") or ""), label=key)
        _assert_file_digest(path, str(ref.get("file_sha256") or ""), label=key)
        payload = _load_json_object(path)
        _assert_self_digest(
            payload,
            digest_field,
            expected=str(ref.get("sha256") or ""),
            label=key,
        )
        loaded[key] = payload

    report = loaded["qualification"]
    query_qrels = loaded["query_qrels"]
    thresholds_payload = loaded["thresholds"]
    thresholds = thresholds_payload.get("thresholds")
    if not isinstance(thresholds, Mapping):
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification thresholds payload is malformed"
        )
    if report.get("status") != "PASS" or report.get("failures") not in ([], None):
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification report failed"
        )
    if report.get("projection_issues") not in ([], None):
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification reports projection issues"
        )
    if report.get("completion_marker") != "GRAPH_EMBEDDINGS_QUALIFIED":
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification report marker is missing"
        )
    if report.get("corpus_sha256") != corpus_sha256:
        raise GraphSkillEmbeddingAllocationError("qualification corpus digest mismatch")
    if report.get("graph_sha256") != graph_sha256:
        raise GraphSkillEmbeddingAllocationError("qualification graph digest mismatch")
    if report.get("embedding_generation_manifest_sha256") != embedding_manifest_sha256:
        raise GraphSkillEmbeddingAllocationError(
            "qualification report embedding generation digest mismatch"
        )
    if (
        report.get("network_used") is not False
        or report.get("fallback_used") is not False
    ):
        raise GraphSkillEmbeddingAllocationError(
            "qualification report permits network or embedding fallback"
        )
    if report.get("qualification_scope") != _REGRESSION_QUALIFICATION_SCOPE:
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification report scope is not regression-only"
        )
    if report.get("release_authorizing") is not False:
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification report must be non-release-authorizing"
        )
    if report.get("query_qrel_sha256") != query_qrels.get("query_qrel_sha256"):
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification report/query QREL digest mismatch"
        )
    if report.get("thresholds") != dict(thresholds):
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification report/threshold payload mismatch"
        )
    if report.get("thresholds_sha256") != canonical_sha256(dict(thresholds)):
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification report threshold digest mismatch"
        )
    expected_runtime_contract = {
        key: value
        for key, value in runtime_contract.items()
        if not str(key).startswith("_")
    }
    if report.get("runtime_contract") != expected_runtime_contract:
        raise GraphSkillEmbeddingAllocationError(
            "graph embedding qualification report runtime contract mismatch"
        )
    _validate_runtime_proof(
        report.get("runtime_proof"),
        runtime_contract=runtime_contract,
        label="graph embedding qualification",
    )
    return {
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": _file_sha256(manifest_path),
        "manifest_sha256": manifest_sha256,
        "qualification_sha256": str(report.get("qualification_sha256") or ""),
        "status": "PASS",
        "qualification_scope": _REGRESSION_QUALIFICATION_SCOPE,
        "release_authorizing": False,
    }


def load_graph_skill_embedding_authority(repo_root: Path | str) -> dict[str, Any]:
    """Validate the complete immutable graph/assertion/projection authority chain."""
    root = Path(repo_root).resolve()
    assert_legacy_graph_skill_embedding_lane_not_retired(root)
    runtime_contract = _load_runtime_contract(root)
    artifact_dir = (root / _ACTIVE_ARTIFACT_DIR).resolve()
    manifest_path = artifact_dir / _ACTIVE_MANIFEST
    manifest = _load_json_object(manifest_path)
    manifest_sha256 = _assert_self_digest(
        manifest,
        "manifest_sha256",
        label="graph skill embedding manifest",
    )
    if (
        manifest.get("network_used") is not False
        or manifest.get("fallback_used") is not False
    ):
        raise GraphSkillEmbeddingAllocationError(
            "embedding generation manifest permits network or fallback"
        )
    _validate_runtime_proof(
        manifest.get("runtime_proof"),
        runtime_contract=runtime_contract,
        label="embedding generation",
    )

    source_payloads: dict[str, dict[str, Any]] = {}
    source_paths: dict[str, Path] = {}
    canonical_source_paths = {
        "graph": resolve_apps_rg_path(
            root,
            "fact_inventory",
            "master_skills_arsenal_ledger.json",
        ).resolve(),
        "candidate_fact_ledger": (
            root / "artifacts/apps_rg/fact_inventory/"
            "master_candidate_skills_fact_ledger_20260518T1100Z.json"
        ).resolve(),
        "base_resume": resolve_apps_rg_path(
            root,
            "resume",
            "base",
            "amit_ayer_base_resume_v1.json",
        ).resolve(),
    }
    for key in ("graph", "candidate_fact_ledger", "base_resume"):
        ref = manifest.get(key)
        if not isinstance(ref, Mapping):
            raise GraphSkillEmbeddingAllocationError(
                f"embedding manifest lacks {key} binding"
            )
        path = _resolve_within(root, str(ref.get("path") or ""), label=key)
        if path != canonical_source_paths[key]:
            raise GraphSkillEmbeddingAllocationError(
                f"{key} does not bind the canonical repository source"
            )
        _assert_file_digest(path, str(ref.get("file_sha256") or ""), label=key)
        payload = _load_json_object(path)
        if canonical_sha256(payload) != str(ref.get("canonical_sha256") or ""):
            raise GraphSkillEmbeddingAllocationError(f"{key} canonical digest mismatch")
        source_payloads[key] = payload
        source_paths[key] = path

    corpus_ref = manifest.get("assertion_corpus")
    if not isinstance(corpus_ref, Mapping):
        raise GraphSkillEmbeddingAllocationError(
            "embedding manifest lacks assertion corpus binding"
        )
    corpus_path = _resolve_within(
        artifact_dir,
        str(corpus_ref.get("path") or ""),
        label="assertion corpus",
    )
    _assert_file_digest(
        corpus_path,
        str(corpus_ref.get("file_sha256") or ""),
        label="assertion corpus",
    )
    corpus = _load_json_object(corpus_path)
    corpus_sha256 = _assert_self_digest(
        corpus,
        "corpus_sha256",
        expected=str(corpus_ref.get("corpus_sha256") or ""),
        label="assertion corpus",
    )
    rebuilt_corpus = build_skill_assertion_corpus(
        graph_payload=source_payloads["graph"],
        candidate_fact_payload=source_payloads["candidate_fact_ledger"],
        base_resume_payload=source_payloads["base_resume"],
    )
    if rebuilt_corpus != corpus:
        raise GraphSkillEmbeddingAllocationError(
            "assertion corpus does not exactly rehydrate from graph and source facts"
        )
    corpus_issues = validate_skill_assertion_corpus(
        corpus,
        graph_payload=source_payloads["graph"],
    )
    if corpus_issues:
        raise GraphSkillEmbeddingAllocationError(
            "assertion corpus validation failed: " + ", ".join(corpus_issues)
        )

    model_ref = manifest.get("model")
    if not isinstance(model_ref, Mapping):
        raise GraphSkillEmbeddingAllocationError(
            "embedding manifest lacks model binding"
        )
    model_manifest_path = _resolve_within(
        artifact_dir,
        str(model_ref.get("path") or ""),
        label="model manifest",
    )
    _assert_file_digest(
        model_manifest_path,
        str(model_ref.get("manifest_file_sha256") or ""),
        label="model manifest",
    )
    model_manifest = _load_json_object(model_manifest_path)
    model_artifact_sha256 = _assert_self_digest(
        model_manifest,
        "artifact_sha256",
        expected=str(model_ref.get("artifact_sha256") or ""),
        label="model manifest",
    )
    for field in ("model_id", "revision", "dimension", "normalization"):
        if model_manifest.get(field) != model_ref.get(field):
            raise GraphSkillEmbeddingAllocationError(f"model {field} binding mismatch")
        if model_manifest.get(field) != runtime_contract["_model"].get(field):
            raise GraphSkillEmbeddingAllocationError(
                f"model {field} does not match embedding runtime contract"
            )

    projection_ref = manifest.get("projection")
    if not isinstance(projection_ref, Mapping):
        raise GraphSkillEmbeddingAllocationError(
            "embedding manifest lacks projection binding"
        )
    projection_path = _resolve_within(
        artifact_dir,
        str(projection_ref.get("path") or ""),
        label="embedding projection",
    )
    _assert_file_digest(
        projection_path,
        str(projection_ref.get("sqlite_sha256") or ""),
        label="embedding projection",
    )
    projection_issues = validate_embedding_projection(projection_path, corpus=corpus)
    if projection_issues:
        raise GraphSkillEmbeddingAllocationError(
            "embedding projection validation failed: " + ", ".join(projection_issues)
        )
    try:
        with GraphSkillEmbeddingIndex(
            projection_path,
            expected_corpus_sha256=corpus_sha256,
            expected_model_artifact_sha256=model_artifact_sha256,
        ) as index:
            projection_metadata = dict(index.metadata)
    except (OSError, GraphSkillEmbeddingContractError) as exc:
        raise GraphSkillEmbeddingAllocationError(
            f"embedding projection cannot be opened read-only: {exc}"
        ) from exc
    if projection_metadata.get("generation_sha256") != str(
        projection_ref.get("generation_sha256") or ""
    ):
        raise GraphSkillEmbeddingAllocationError("embedding generation digest mismatch")
    if projection_metadata.get("graph_sha256") != str(
        (corpus.get("source_digests") or {}).get("graph_sha256") or ""
    ):
        raise GraphSkillEmbeddingAllocationError("projection graph digest mismatch")
    if int(projection_metadata.get("vector_count") or -1) != int(
        corpus_ref.get("assertion_count") or -2
    ):
        raise GraphSkillEmbeddingAllocationError(
            "projection assertion/vector count mismatch"
        )

    graph_sha256 = str((corpus.get("source_digests") or {}).get("graph_sha256") or "")
    if graph_sha256 != str((manifest.get("graph") or {}).get("canonical_sha256") or ""):
        raise GraphSkillEmbeddingAllocationError("corpus/graph digest mismatch")
    qualification = _validate_qualification_artifacts(
        artifact_dir,
        embedding_manifest_sha256=manifest_sha256,
        corpus_sha256=corpus_sha256,
        graph_sha256=graph_sha256,
        runtime_contract=runtime_contract,
    )

    return {
        "schema_version": "apps_rg.graph_skill_embedding_authority.v1",
        "status": "PASS",
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": _file_sha256(manifest_path),
        "manifest_sha256": manifest_sha256,
        "graph_path": str(source_paths["graph"]),
        "graph_sha256": graph_sha256,
        "candidate_fact_ledger_path": str(source_paths["candidate_fact_ledger"]),
        "candidate_fact_ledger_sha256": str(
            (corpus.get("source_digests") or {}).get("candidate_fact_ledger_sha256")
            or ""
        ),
        "base_resume_path": str(source_paths["base_resume"]),
        "base_resume_sha256": str(
            (corpus.get("source_digests") or {}).get("base_resume_sha256") or ""
        ),
        "corpus_path": str(corpus_path),
        "corpus_sha256": corpus_sha256,
        "assertion_count": len(corpus.get("assertions") or []),
        "exclusion_count": len(corpus.get("exclusions") or []),
        "model_manifest_path": str(model_manifest_path),
        "model_artifact_sha256": model_artifact_sha256,
        "model_id": str(model_manifest.get("model_id") or ""),
        "model_revision": str(model_manifest.get("revision") or ""),
        "model_dimension": int(model_manifest.get("dimension") or 0),
        "projection_path": str(projection_path),
        "projection_sha256": str(projection_ref.get("sqlite_sha256") or ""),
        "embedding_generation_sha256": str(
            projection_ref.get("generation_sha256") or ""
        ),
        "qualification_status": qualification["status"],
        "qualification_scope": qualification["qualification_scope"],
        "release_authorizing": qualification["release_authorizing"],
        "qualification": qualification,
        "runtime_contract": {
            key: value
            for key, value in runtime_contract.items()
            if not str(key).startswith("_")
        },
        "projection_read_only": True,
        "network_used": False,
        "fallback_used": False,
        "_graph_payload": source_payloads["graph"],
        "_corpus_payload": corpus,
        "_model_manifest": model_manifest,
    }


def _authority_pins(authority: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "manifest_sha256": str(authority.get("manifest_sha256") or ""),
        "graph_sha256": str(authority.get("graph_sha256") or ""),
        "candidate_fact_ledger_sha256": str(
            authority.get("candidate_fact_ledger_sha256") or ""
        ),
        "base_resume_sha256": str(authority.get("base_resume_sha256") or ""),
        "corpus_sha256": str(authority.get("corpus_sha256") or ""),
        "embedding_generation_sha256": str(
            authority.get("embedding_generation_sha256") or ""
        ),
        "projection_sha256": str(authority.get("projection_sha256") or ""),
        "model_id": str(authority.get("model_id") or ""),
        "model_revision": str(authority.get("model_revision") or ""),
        "model_artifact_sha256": str(authority.get("model_artifact_sha256") or ""),
        "qualification_sha256": str(
            (authority.get("qualification") or {}).get("qualification_sha256") or ""
        ),
        "qualification_scope": str(authority.get("qualification_scope") or ""),
        "release_authorizing": authority.get("release_authorizing") is True,
        "runtime_contract_sha256": str(
            (authority.get("runtime_contract") or {}).get("contract_sha256") or ""
        ),
        "runtime_contract_packages": dict(
            (authority.get("runtime_contract") or {}).get("packages") or {}
        ),
    }


def _query_text(
    *,
    section_id: str,
    target_company: str,
    target_role: str,
    jd_text: str,
    briefing_text: str,
) -> str:
    return "\n".join(
        (
            f"Resume section: {section_id}",
            f"Target company: {str(target_company or '').strip()}",
            f"Target role: {str(target_role or '').strip()}",
            "Job description:",
            str(jd_text or "").strip(),
            "Research briefing:",
            str(briefing_text or "").strip(),
        )
    ).strip()


def build_whole_resume_graph_embedding_candidates(
    *,
    repo_root: Path,
    target_company: str,
    target_role: str,
    jd_text: str,
    briefing_text: str,
    model_path: Path | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Validate pins, embed eleven queries, and return exact rehydrated candidates."""
    from apps_rg.fact_inventory.c03_skill_embedding_builder import (
        build_local_model_manifest,
        encode_bge_m3,
    )

    authority = load_graph_skill_embedding_authority(repo_root)
    resolved_model_path = Path(
        model_path or str(os.environ.get(EMBEDDING_MODEL_PATH_ENV) or "")
    )
    if not str(resolved_model_path).strip() or not resolved_model_path.is_dir():
        raise GraphSkillEmbeddingAllocationError(
            f"{EMBEDDING_MODEL_PATH_ENV} must name the pinned local BGE-M3 directory"
        )
    observed_model_manifest = build_local_model_manifest(resolved_model_path)
    if observed_model_manifest != authority["_model_manifest"]:
        raise GraphSkillEmbeddingAllocationError(
            "local BGE-M3 artifact digest mismatch"
        )
    resolved_device = str(
        device or os.environ.get(GRAPH_SKILL_EMBEDDING_DEVICE_ENV) or ""
    ).strip()
    if not resolved_device:
        raise GraphSkillEmbeddingAllocationError(
            f"{GRAPH_SKILL_EMBEDDING_DEVICE_ENV} must be set for mandatory graph embeddings"
        )
    runtime_contract = authority["runtime_contract"]
    promoted_device = str(runtime_contract.get("promoted_device") or "")
    if resolved_device != promoted_device:
        raise GraphSkillEmbeddingAllocationError(
            f"mandatory graph embedding device mismatch: expected {promoted_device}, "
            f"observed {resolved_device}"
        )

    query_texts = [
        _query_text(
            section_id=section_id,
            target_company=target_company,
            target_role=target_role,
            jd_text=jd_text,
            briefing_text=briefing_text,
        )
        for section_id in ALL_EMBEDDING_LANES
    ]
    try:
        runtime_proof, query_vectors = encode_bge_m3(
            query_texts,
            model_path=resolved_model_path,
            device=resolved_device,
            batch_size=len(ALL_EMBEDDING_LANES),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise GraphSkillEmbeddingAllocationError(
            f"mandatory BGE-M3 query encoding failed: {exc}"
        ) from exc
    live_runtime_contract = {
        **runtime_contract,
        "_model": {"dimension": authority["model_dimension"]},
    }
    _validate_runtime_proof(
        runtime_proof,
        runtime_contract=live_runtime_contract,
        label="BGE-M3 query",
    )

    projection_path = Path(str(authority["projection_path"]))
    projection_before = _file_sha256(projection_path)
    candidates_by_section: dict[str, list[dict[str, Any]]] = {}
    query_receipts: dict[str, dict[str, Any]] = {}
    try:
        with GraphSkillEmbeddingIndex(
            projection_path,
            expected_corpus_sha256=str(authority["corpus_sha256"]),
            expected_model_artifact_sha256=str(authority["model_artifact_sha256"]),
        ) as index:
            for section_id, query_text, query_vector in zip(
                ALL_EMBEDDING_LANES,
                query_texts,
                query_vectors,
                strict=True,
            ):
                authority_section_id = NARRATIVE_AUTHORITY_SECTIONS.get(
                    section_id,
                    section_id,
                )
                raw_candidates = index.query(
                    query_vector,
                    k=int(authority["assertion_count"]),
                    section_id=authority_section_id,
                )
                if any(
                    set(row) != {"assertion_id", "similarity"} for row in raw_candidates
                ):
                    raise GraphSkillEmbeddingAllocationError(
                        f"{section_id}: embedding index exposed non-candidate fields"
                    )
                hydrated = rehydrate_assertion_candidates(
                    raw_candidates,
                    corpus=authority["_corpus_payload"],
                    graph_payload=authority["_graph_payload"],
                    section_id=authority_section_id,
                )
                if not hydrated:
                    raise GraphSkillEmbeddingAllocationError(
                        f"{section_id}: embedding query returned no eligible assertions"
                    )
                rows: list[dict[str, Any]] = []
                for row in hydrated:
                    exact = dict(row)
                    exact["authority_section_id"] = authority_section_id
                    rows.append(exact)
                candidates_by_section[section_id] = rows
                query_receipts[section_id] = {
                    "query_sha256": hashlib.sha256(
                        query_text.encode("utf-8")
                    ).hexdigest(),
                    "authority_section_id": authority_section_id,
                    "candidate_count": len(raw_candidates),
                    "candidate_ids_sha256": canonical_sha256(raw_candidates),
                    "candidate_payload_fields": ["assertion_id", "similarity"],
                    "exact_rehydration_pass": True,
                }
    except GraphSkillEmbeddingContractError as exc:
        raise GraphSkillEmbeddingAllocationError(
            f"embedding candidate rehydration failed: {exc}"
        ) from exc
    projection_after = _file_sha256(projection_path)
    if (
        projection_before != projection_after
        or projection_after != authority["projection_sha256"]
    ):
        raise GraphSkillEmbeddingAllocationError(
            "immutable graph skill embedding projection changed during query"
        )

    return {
        "schema_version": "apps_rg.graph_skill_embedding_candidates.v1",
        "authority": _authority_pins(authority),
        "candidates_by_section": candidates_by_section,
        "query_receipts": query_receipts,
        "runtime_proof": runtime_proof,
        "projection_sha256_before": projection_before,
        "projection_sha256_after": projection_after,
        "network_used": False,
        "fallback_used": False,
        "pass": True,
    }


def candidate_skill_scores_by_section(
    candidates_by_section: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {}
    for section_id, candidates in candidates_by_section.items():
        section_scores: dict[str, float] = {}
        for candidate in candidates:
            skill_id = str(candidate.get("skill_id") or "").strip()
            if not skill_id:
                raise GraphSkillEmbeddingAllocationError(
                    f"{section_id}: rehydrated assertion is missing skill_id"
                )
            similarity = float(candidate.get("similarity") or 0.0)
            section_scores[skill_id] = max(
                similarity,
                section_scores.get(skill_id, float("-inf")),
            )
        scores[str(section_id)] = section_scores
    return scores


def _strings(values: Sequence[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def build_lane_embedding_allowlists(
    *,
    allocation_plan: Mapping[str, Any],
    candidates_by_section: Mapping[str, Sequence[Mapping[str, Any]]],
    authority_pins: Mapping[str, Any],
    section_order: Sequence[str] = ALL_EMBEDDING_LANES,
) -> dict[str, Any]:
    """Intersect exact assertion candidates with one frozen whole-resume allocation."""
    allocation_digest = str(allocation_plan.get("allocation_plan_digest") or "")
    if not allocation_digest:
        raise GraphSkillEmbeddingAllocationError("allocation plan digest is missing")
    assignments = [
        dict(row)
        for row in allocation_plan.get("assignments") or []
        if isinstance(row, Mapping)
    ]
    lanes: dict[str, dict[str, Any]] = {}
    for section_id in section_order:
        section_assignments = [
            row for row in assignments if str(row.get("section_id") or "") == section_id
        ]
        if not section_assignments:
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: frozen allocation contains no assignments"
            )
        candidates = [
            dict(row)
            for row in candidates_by_section.get(section_id) or []
            if isinstance(row, Mapping)
        ]
        candidates.sort(
            key=lambda row: (
                -float(row.get("similarity") or 0.0),
                str(row.get("assertion_id") or ""),
            )
        )
        candidate_payload = [
            {
                "assertion_id": str(row.get("assertion_id") or ""),
                "similarity": float(row.get("similarity") or 0.0),
            }
            for row in candidates
        ]
        allocated_skill_ids = _strings(
            [row.get("skill_id") for row in section_assignments]
        )
        accepted = [
            row
            for row in candidates
            if str(row.get("skill_id") or "") in allocated_skill_ids
        ]
        accepted_skill_ids = {str(row.get("skill_id") or "") for row in accepted}
        missing = sorted(set(allocated_skill_ids) - accepted_skill_ids)
        if missing:
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: allocated skills lack exact assertion candidates: {missing}"
            )
        derived_from = str(section_assignments[0].get("derived_from_section_id") or "")
        authority_section_id = derived_from or section_id
        if any(
            str(row.get("authority_section_id") or "") != authority_section_id
            for row in accepted
        ):
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: assertion section authority does not match allocation"
            )
        accepted_bindings = [
            {
                "assertion_id": str(row.get("assertion_id") or ""),
                "skill_id": str(row.get("skill_id") or ""),
                "similarity": float(row.get("similarity") or 0.0),
                "fact_links": _strings(list(row.get("fact_links") or [])),
                "assertion_document_sha256": str(
                    row.get("assertion_document_sha256") or ""
                ),
                "authority_envelope_sha256": str(
                    row.get("authority_envelope_sha256") or ""
                ),
                "skill_row_sha256": str(row.get("skill_row_sha256") or ""),
            }
            for row in accepted
        ]
        accepted_bindings.sort(
            key=lambda row: (-float(row["similarity"]), str(row["assertion_id"]))
        )
        lane: dict[str, Any] = {
            "schema_version": "apps_rg.lane_graph_skill_embedding_allowlist.v1",
            "section_id": section_id,
            "assertion_authority_section_id": authority_section_id,
            "derived_from_section_id": derived_from,
            "allocation_plan_digest": allocation_digest,
            "candidate_assertions": candidate_payload,
            "candidate_count": len(candidate_payload),
            "accepted_assertion_bindings": accepted_bindings,
            "allowlists": {
                "assertion_ids": _strings(
                    [row.get("assertion_id") for row in accepted_bindings]
                ),
                "skill_ids": allocated_skill_ids,
                "fact_ids": _strings(
                    [row.get("fact_id") for row in section_assignments]
                ),
                "metric_ids": _strings(
                    [row.get("metric_outcome_id") for row in section_assignments]
                ),
            },
            "similarity_is_claim_authority": False,
            "exact_rehydration_pass": True,
            "allocation_intersection_pass": True,
            "pass": True,
        }
        lane["lane_allowlist_digest"] = canonical_sha256(lane)
        lanes[section_id] = lane

    payload: dict[str, Any] = {
        "schema_version": "apps_rg.lane_graph_skill_embedding_allowlists.v1",
        "allocation_plan_digest": allocation_digest,
        "authority": dict(authority_pins),
        "lane_order": list(section_order),
        "lanes": lanes,
        "similarity_is_claim_authority": False,
        "durable_graph_state_mutated": False,
        "pass": True,
    }
    payload["allowlists_digest"] = canonical_sha256(payload)
    return payload


def load_lane_embedding_allowlists(path: Path | str) -> dict[str, Any]:
    payload = _load_json_object(Path(path))
    _assert_self_digest(
        payload,
        "allowlists_digest",
        label="lane graph skill embedding allowlists",
    )
    if (
        payload.get("schema_version")
        != "apps_rg.lane_graph_skill_embedding_allowlists.v1"
    ):
        raise GraphSkillEmbeddingAllocationError(
            "lane graph skill embedding allowlist schema mismatch"
        )
    lanes = payload.get("lanes")
    lane_order = payload.get("lane_order")
    if not isinstance(lanes, Mapping) or not isinstance(lane_order, list):
        raise GraphSkillEmbeddingAllocationError(
            "lane graph skill embedding allowlist inventory is malformed"
        )
    ordered_sections = [str(value) for value in lane_order]
    if len(ordered_sections) != len(set(ordered_sections)) or set(ordered_sections) != {
        str(value) for value in lanes
    }:
        raise GraphSkillEmbeddingAllocationError(
            "lane graph skill embedding allowlist inventory mismatch"
        )
    allocation_digest = str(payload.get("allocation_plan_digest") or "")
    if not allocation_digest:
        raise GraphSkillEmbeddingAllocationError(
            "lane graph skill embedding allowlist allocation digest is missing"
        )
    if (
        payload.get("pass") is not True
        or payload.get("similarity_is_claim_authority") is not False
        or payload.get("durable_graph_state_mutated") is not False
    ):
        raise GraphSkillEmbeddingAllocationError(
            "lane graph skill embedding allowlist weakens authority invariants"
        )
    for section_id in ordered_sections:
        lane = lanes.get(section_id)
        if not isinstance(lane, Mapping):
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: lane graph skill embedding allowlist is malformed"
            )
        _assert_self_digest(
            lane,
            "lane_allowlist_digest",
            label=f"{section_id} lane graph skill embedding allowlist",
        )
        if (
            lane.get("schema_version")
            != "apps_rg.lane_graph_skill_embedding_allowlist.v1"
            or str(lane.get("section_id") or "") != section_id
            or str(lane.get("allocation_plan_digest") or "") != allocation_digest
            or lane.get("pass") is not True
            or lane.get("exact_rehydration_pass") is not True
            or lane.get("allocation_intersection_pass") is not True
            or lane.get("similarity_is_claim_authority") is not False
        ):
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: lane graph skill embedding authority invariants failed"
            )
    return payload


def validate_lane_embedding_allowlist_authority(
    payload: Mapping[str, Any],
    *,
    repo_root: Path | str,
    allocation_plan: Mapping[str, Any],
    section_id: str,
) -> dict[str, Any]:
    """Bind one loaded lane to current graph authority before it can affect a pool."""

    _assert_self_digest(
        payload,
        "allowlists_digest",
        label="lane graph skill embedding allowlists",
    )
    if (
        payload.get("schema_version")
        != "apps_rg.lane_graph_skill_embedding_allowlists.v1"
    ):
        raise GraphSkillEmbeddingAllocationError(
            "lane graph skill embedding allowlist schema mismatch"
        )
    allocation_digest = str(allocation_plan.get("allocation_plan_digest") or "")
    if not allocation_digest or str(payload.get("allocation_plan_digest") or "") != (
        allocation_digest
    ):
        raise GraphSkillEmbeddingAllocationError(
            f"{section_id}: embedding allowlist allocation digest mismatch"
        )

    active_authority = load_graph_skill_embedding_authority(repo_root)
    expected_authority = _authority_pins(active_authority)
    observed_authority = payload.get("authority")
    if not isinstance(observed_authority, Mapping) or dict(observed_authority) != (
        expected_authority
    ):
        raise GraphSkillEmbeddingAllocationError(
            f"{section_id}: embedding allowlist authority pins are stale or mismatched"
        )
    allocation_graph_digest = str(allocation_plan.get("graph_digest") or "")
    if (
        not allocation_graph_digest
        or allocation_graph_digest != expected_authority["graph_sha256"]
    ):
        raise GraphSkillEmbeddingAllocationError(
            f"{section_id}: embedding allowlist graph authority mismatch"
        )

    lanes = payload.get("lanes")
    lane = lanes.get(section_id) if isinstance(lanes, Mapping) else None
    if not isinstance(lane, Mapping):
        raise GraphSkillEmbeddingAllocationError(
            f"{section_id}: embedding allowlist is missing or malformed"
        )
    lane_payload = dict(lane)
    _assert_self_digest(
        lane_payload,
        "lane_allowlist_digest",
        label=f"{section_id} lane graph skill embedding allowlist",
    )

    candidate_rows = lane_payload.get("candidate_assertions")
    if not isinstance(candidate_rows, list) or not candidate_rows:
        raise GraphSkillEmbeddingAllocationError(
            f"{section_id}: embedding candidate assertion inventory is empty"
        )
    candidates: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    for raw in candidate_rows:
        if not isinstance(raw, Mapping) or set(raw) != {"assertion_id", "similarity"}:
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: embedding candidate payload is malformed"
            )
        assertion_id = str(raw.get("assertion_id") or "")
        try:
            similarity = float(raw.get("similarity"))
        except (TypeError, ValueError) as exc:
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: embedding candidate similarity is invalid"
            ) from exc
        if (
            not assertion_id
            or assertion_id in candidate_ids
            or not math.isfinite(similarity)
        ):
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: embedding candidate identity or similarity is invalid"
            )
        candidate_ids.add(assertion_id)
        candidates.append({"assertion_id": assertion_id, "similarity": similarity})

    authority_section_id = str(lane_payload.get("assertion_authority_section_id") or "")
    if not authority_section_id:
        raise GraphSkillEmbeddingAllocationError(
            f"{section_id}: embedding assertion section authority is missing"
        )
    try:
        hydrated = rehydrate_assertion_candidates(
            candidates,
            corpus=active_authority["_corpus_payload"],
            graph_payload=active_authority["_graph_payload"],
            section_id=authority_section_id,
        )
    except (KeyError, GraphSkillEmbeddingContractError) as exc:
        raise GraphSkillEmbeddingAllocationError(
            f"{section_id}: embedding candidate authority rehydration failed: {exc}"
        ) from exc
    hydrated_by_id = {str(row.get("assertion_id") or ""): row for row in hydrated}

    raw_bindings = lane_payload.get("accepted_assertion_bindings")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise GraphSkillEmbeddingAllocationError(
            f"{section_id}: accepted embedding assertion bindings are empty"
        )
    accepted_ids: list[str] = []
    expected_binding_fields = {
        "assertion_id",
        "skill_id",
        "similarity",
        "fact_links",
        "assertion_document_sha256",
        "authority_envelope_sha256",
        "skill_row_sha256",
    }
    for raw in raw_bindings:
        if not isinstance(raw, Mapping) or set(raw) != expected_binding_fields:
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: accepted embedding assertion binding is malformed"
            )
        assertion_id = str(raw.get("assertion_id") or "")
        if not assertion_id or assertion_id in accepted_ids:
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: accepted embedding assertion identity is invalid"
            )
        assertion = hydrated_by_id.get(assertion_id)
        if assertion is None:
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: accepted embedding assertion is not an authorized candidate"
            )
        expected_binding = {
            "assertion_id": assertion_id,
            "skill_id": str(assertion.get("skill_id") or ""),
            "similarity": float(assertion.get("similarity") or 0.0),
            "fact_links": _strings(list(assertion.get("fact_links") or [])),
            "assertion_document_sha256": str(
                assertion.get("assertion_document_sha256") or ""
            ),
            "authority_envelope_sha256": str(
                assertion.get("authority_envelope_sha256") or ""
            ),
            "skill_row_sha256": str(assertion.get("skill_row_sha256") or ""),
        }
        if dict(raw) != expected_binding:
            raise GraphSkillEmbeddingAllocationError(
                f"{section_id}: accepted embedding assertion binding drifted from authority"
            )
        accepted_ids.append(assertion_id)

    allowlists = lane_payload.get("allowlists")
    if not isinstance(allowlists, Mapping) or _strings(
        list(allowlists.get("assertion_ids") or [])
    ) != _strings(accepted_ids):
        raise GraphSkillEmbeddingAllocationError(
            f"{section_id}: embedding assertion allowlist differs from authorized bindings"
        )
    return lane_payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    staging = path.with_name(f".{path.name}.staging-{os.getpid()}")
    staging.write_text(rendered, encoding="utf-8", newline="\n")
    os.replace(staging, path)


def write_graph_skill_embedding_runtime_bundle(
    bundle: Mapping[str, Any],
    *,
    output_dir: Path,
) -> dict[str, str]:
    allowlists = dict(bundle.get("lane_allowlists") or {})
    _assert_self_digest(
        allowlists,
        "allowlists_digest",
        label="lane graph skill embedding allowlists",
    )
    runtime_receipt = dict(bundle.get("runtime_receipt") or {})
    runtime_receipt.pop("runtime_receipt_digest", None)
    runtime_receipt["runtime_receipt_digest"] = canonical_sha256(runtime_receipt)
    allowlists_path = output_dir / "lane_graph_skill_embedding_allowlists.json"
    runtime_path = output_dir / "graph_skill_embedding_runtime_receipt.json"
    _write_json_atomic(allowlists_path, allowlists)
    _write_json_atomic(runtime_path, runtime_receipt)
    return {
        "lane_allowlists": str(allowlists_path),
        "runtime_receipt": str(runtime_path),
    }


__all__ = [
    "ALL_EMBEDDING_LANES",
    "EMBEDDING_MODEL_PATH_ENV",
    "GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV",
    "GRAPH_SKILL_EMBEDDING_DEVICE_ENV",
    "GRAPH_SKILL_EMBEDDINGS_REQUIRED_ENV",
    "GraphSkillEmbeddingAllocationError",
    "assert_legacy_graph_skill_embedding_lane_not_retired",
    "build_lane_embedding_allowlists",
    "build_whole_resume_graph_embedding_candidates",
    "candidate_skill_scores_by_section",
    "graph_skill_embeddings_required",
    "load_graph_skill_embedding_authority",
    "load_legacy_graph_skill_embedding_retirement",
    "load_lane_embedding_allowlists",
    "validate_lane_embedding_allowlist_authority",
    "write_graph_skill_embedding_runtime_bundle",
]
