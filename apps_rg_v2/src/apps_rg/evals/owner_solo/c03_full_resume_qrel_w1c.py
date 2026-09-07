"""W1C combined owner-solo C0.3 projection for the full-resume QREL lane.

The authoritative W4/W6 registry and projection remain immutable.  W1C creates
an ignored, owner-solo-only candidate universe by combining their 38 frozen
graph-evidence-cluster vectors with the 16 W1B multi-node runtime bundles.
Only W1B bundle texts are newly encoded with the locally pinned BGE-M3 model.
This module creates no human grade, QREL, ranking, activation, or release
authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.evals.owner_solo.c03_full_resume_qrel_derived_clusters import (
    build_derived_bundle_registry,
    validate_derived_bundle_registry,
    write_derived_bundle_registry,
)
from apps_rg.evals.owner_solo.c03_full_resume_qrel_scope import (
    EXPECTED_SECTION_IDS,
    RESULT_LABEL,
    SCOPE_PATH,
    load_full_resume_scope,
    validate_full_resume_scope,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (
    REGISTRY_PATH,
    W6_RECEIPT_PATH,
    validate_generation_manifest,
    validate_w6_receipt,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_registry import (
    validate_registry,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)
from apps_rg.fact_inventory.c03_skill_embedding_builder import (
    MODEL_DIMENSION,
    MODEL_ID,
    build_local_model_manifest,
    encode_bge_m3,
)
from apps_rg.runtime.graph_evidence_cluster_embedding_projection import (
    validate_cluster_embedding_projection,
)


COMBINED_REGISTRY_SCHEMA_VERSION = (
    "apps_rg.owner_solo_full_resume_combined_cluster_registry.v1"
)
COMBINED_REGISTRY_STATUS = "W1C_COMBINED_CANDIDATE_REGISTRY_READY_FOR_PROJECTION"
PROJECTION_SCHEMA_VERSION = (
    "apps_rg.owner_solo_full_resume_cluster_embedding_projection.v1"
)
PROJECTION_STATUS = "GENERATED_OWNER_SOLO_PROVISIONAL_NOT_QUALIFIED"
GENERATION_MANIFEST_SCHEMA_VERSION = (
    "apps_rg.owner_solo_full_resume_cluster_projection_generation.v1"
)
RECEIPT_SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_qrel_w1c_receipt.v1"
RECEIPT_STATUS = "W1C_READY_FOR_RANKING_GENERATION"
RUNTIME_DIR = Path(".runtime/c03-owner-solo-qrel/w1c")

_EXPECTED_MODEL = {
    "model_id": MODEL_ID,
    "revision": "5617a9f61b028005a4858fdac845db406aefb181",
    "artifact_sha256": (
        "38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263"
    ),
    "dimension": MODEL_DIMENSION,
    "normalization": "l2",
}
_EXPECTED_SECTION_CANDIDATE_COUNTS = {
    "headline": 8,
    "executive_summary": 12,
    "competencies": 22,
    "unify_bullets": 19,
    "unify_narrative": 3,
    "ibm_bullets": 8,
    "ibm_narrative": 8,
    "ey_bullets": 2,
    "ey_narrative": 2,
    "insurtech_bullets": 8,
    "insurtech_narrative": 8,
}


class FullResumeQrelW1CError(ValueError):
    """Raised when the isolated W1C projection cannot preserve authority."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FullResumeQrelW1CError(f"JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise FullResumeQrelW1CError(f"JSON object required: {path}")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FullResumeQrelW1CError(f"File unavailable: {path}") from exc
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _repository_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise FullResumeQrelW1CError(
            f"Path escapes the repository: {path}"
        ) from exc


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    data = rendered.encode("utf-8")
    if path.exists():
        if path.read_bytes() != data:
            raise FullResumeQrelW1CError(f"Immutable artifact collision: {path}")
        return hashlib.sha256(data).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.staging-{os.getpid()}")
    try:
        staging.write_bytes(data)
        os.replace(staging, path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return hashlib.sha256(data).hexdigest()


def _vector_bytes(values: Sequence[float], dimension: int) -> bytes:
    if len(values) != dimension:
        raise FullResumeQrelW1CError(
            f"vector dimension mismatch: expected {dimension}, observed {len(values)}"
        )
    vector = [float(value) for value in values]
    if not all(math.isfinite(value) for value in vector):
        raise FullResumeQrelW1CError("vector values must be finite")
    norm = math.sqrt(math.fsum(value * value for value in vector))
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-5):
        raise FullResumeQrelW1CError(
            f"vector must be L2 normalized; observed norm={norm:.9f}"
        )
    return struct.pack(f"<{dimension}f", *vector)


def _decode_vector(blob: bytes, dimension: int) -> tuple[float, ...]:
    expected_bytes = dimension * 4
    if len(blob) != expected_bytes:
        raise FullResumeQrelW1CError(
            "stored vector byte length mismatch: "
            f"expected {expected_bytes}, observed {len(blob)}"
        )
    return struct.unpack(f"<{dimension}f", blob)


def _open_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def _validate_pinned_model(model: Mapping[str, Any]) -> None:
    mismatches = [
        field for field, expected in _EXPECTED_MODEL.items() if model.get(field) != expected
    ]
    if mismatches:
        raise FullResumeQrelW1CError(
            "local BGE-M3 model does not match the frozen W1C binding: "
            + ", ".join(mismatches)
        )


def _base_registry(root: Path) -> dict[str, Any]:
    registry = _read_json(root / REGISTRY_PATH)
    try:
        validate_registry(registry)
    except ValueError as exc:
        raise FullResumeQrelW1CError("authoritative W4 registry is invalid") from exc
    return registry


def _section_candidate_ids(
    clusters: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {section: [] for section in EXPECTED_SECTION_IDS}
    for cluster in clusters:
        cluster_id = str(cluster.get("cluster_id") or "")
        for section in cluster.get("allowed_sections") or []:
            if section in result:
                result[section].append(cluster_id)
    return {section: sorted(values) for section, values in result.items()}


def build_combined_registry(repo_root: Path | str) -> dict[str, Any]:
    """Combine unchanged W4 clusters with deterministic W1B bundle clusters."""

    root = Path(repo_root).resolve()
    scope = load_full_resume_scope(root)
    scope_issues = validate_full_resume_scope(scope, root)
    if scope_issues:
        raise FullResumeQrelW1CError(f"W0 scope invalid: {scope_issues}")
    base = _base_registry(root)
    derived = build_derived_bundle_registry(root)
    derived_issues = validate_derived_bundle_registry(derived, root)
    if derived_issues:
        raise FullResumeQrelW1CError(f"W1B registry invalid: {derived_issues}")

    base_graph_sha256 = (base.get("source_authority") or {}).get(
        "canonical_graph_sha256"
    )
    derived_source = derived.get("source_authority") or {}
    if (
        derived_source.get("base_registry_sha256") != base.get("registry_sha256")
        or derived_source.get("canonical_graph_sha256") != base_graph_sha256
    ):
        raise FullResumeQrelW1CError("W1B does not bind to the current W4 authority")

    base_clusters = sorted(
        (dict(row) for row in base.get("clusters") or [] if isinstance(row, Mapping)),
        key=lambda row: str(row.get("cluster_id") or ""),
    )
    derived_clusters = sorted(
        (dict(row) for row in derived.get("clusters") or [] if isinstance(row, Mapping)),
        key=lambda row: str(row.get("cluster_id") or ""),
    )
    if len(base_clusters) != 38 or any(
        row.get("activation_status") != "ACTIVE_CONFIRMED" for row in base_clusters
    ):
        raise FullResumeQrelW1CError("W4 active cluster source is not the frozen 38")
    if len(derived_clusters) != 16 or any(
        row.get("activation_status") != "DERIVED_REVIEW_ONLY"
        for row in derived_clusters
    ):
        raise FullResumeQrelW1CError("W1B source is not the expected review-only 16")

    base_ids = [str(row.get("cluster_id") or "") for row in base_clusters]
    derived_ids = [str(row.get("cluster_id") or "") for row in derived_clusters]
    if (
        not all(base_ids)
        or not all(derived_ids)
        or len(set(base_ids)) != len(base_ids)
        or len(set(derived_ids)) != len(derived_ids)
        or set(base_ids) & set(derived_ids)
    ):
        raise FullResumeQrelW1CError("combined cluster identities are not conserved")

    clusters = sorted(base_clusters + derived_clusters, key=lambda row: row["cluster_id"])
    section_ids = _section_candidate_ids(clusters)
    section_counts = {section: len(ids) for section, ids in section_ids.items()}
    if section_counts != _EXPECTED_SECTION_CANDIDATE_COUNTS:
        raise FullResumeQrelW1CError(
            "combined section candidate coverage changed: " f"{section_counts}"
        )
    target_count = len(scope.get("targets") or [])
    payload: dict[str, Any] = {
        "schema_version": COMBINED_REGISTRY_SCHEMA_VERSION,
        "status": COMBINED_REGISTRY_STATUS,
        "result_label": RESULT_LABEL,
        "purpose": (
            "Separate owner-solo full-resume candidate universe. It combines the "
            "unchanged authoritative W4 cluster registry with W1B multi-node "
            "runtime bundles for offline QREL ranking only."
        ),
        "authoritative_lane_boundary": {
            "authoritative_w4_registry_changed": False,
            "authoritative_w6_projection_changed": False,
            "existing_two_reviewer_contract_unchanged": True,
            "authoritative_release_qualification_not_satisfied": True,
            "production_promotion_authorized": False,
        },
        "source_authority": {
            "scope_path": SCOPE_PATH.as_posix(),
            "scope_manifest_sha256": scope["scope_manifest_sha256"],
            "base_registry_path": REGISTRY_PATH.as_posix(),
            "base_registry_sha256": base["registry_sha256"],
            "derived_registry_sha256": derived["derived_registry_sha256"],
            "canonical_graph_sha256": base_graph_sha256,
        },
        "vector_plan": {
            "logical_retrieval_unit": "graph_evidence_cluster",
            "base_vector_source": "FROZEN_W6_EXACT_VECTOR_COPY",
            "base_vector_count": len(base_clusters),
            "derived_vector_source": "LOCAL_PINNED_BGE_M3_W1B_BUNDLE_TEXT",
            "derived_vector_count": len(derived_clusters),
            "individual_graph_node_embedding_forbidden": True,
            "per_skill_vector_creation_forbidden": True,
            "production_activation_authorized": False,
        },
        "base_cluster_ids": base_ids,
        "derived_cluster_ids": derived_ids,
        "clusters": clusters,
        "section_candidate_cluster_ids": section_ids,
        "coverage": {
            "query_count": target_count,
            "section_count": len(EXPECTED_SECTION_IDS),
            "query_section_case_count": target_count * len(EXPECTED_SECTION_IDS),
            "candidate_count_by_section": section_counts,
            "candidate_judgment_count": target_count * sum(section_counts.values()),
            "full_finite_candidate_universe_required": True,
            "partial_top_k_judging_forbidden": True,
        },
    }
    payload["combined_registry_sha256"] = canonical_sha256(payload)
    return payload


def validate_combined_registry(
    payload: Mapping[str, Any], repo_root: Path | str
) -> list[str]:
    """Return fail-closed W1C candidate-universe validation issues."""

    root = Path(repo_root).resolve()
    issues: list[str] = []
    if (
        payload.get("schema_version") != COMBINED_REGISTRY_SCHEMA_VERSION
        or payload.get("status") != COMBINED_REGISTRY_STATUS
        or payload.get("result_label") != RESULT_LABEL
    ):
        issues.append("SCHEMA_OR_STATUS")
    unsigned = dict(payload)
    digest = unsigned.pop("combined_registry_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(unsigned) != digest:
        issues.append("COMBINED_REGISTRY_DIGEST")

    scope = load_full_resume_scope(root)
    if validate_full_resume_scope(scope, root):
        issues.append("W0_SCOPE")
    try:
        base = _base_registry(root)
    except FullResumeQrelW1CError:
        base = {}
        issues.append("BASE_REGISTRY")
    try:
        derived = build_derived_bundle_registry(root)
        derived_issues = validate_derived_bundle_registry(derived, root)
        if derived_issues:
            issues.append("W1B_REGISTRY")
    except (FullResumeQrelW1CError, ValueError):
        derived = {}
        issues.append("W1B_REGISTRY")

    source = payload.get("source_authority")
    if not isinstance(source, Mapping):
        issues.append("SOURCE_AUTHORITY")
    else:
        expected_source = {
            "scope_path": SCOPE_PATH.as_posix(),
            "scope_manifest_sha256": scope.get("scope_manifest_sha256"),
            "base_registry_path": REGISTRY_PATH.as_posix(),
            "base_registry_sha256": base.get("registry_sha256"),
            "derived_registry_sha256": derived.get("derived_registry_sha256"),
            "canonical_graph_sha256": (base.get("source_authority") or {}).get(
                "canonical_graph_sha256"
            ),
        }
        if any(source.get(field) != value for field, value in expected_source.items()):
            issues.append("SOURCE_BINDING")

    boundary = payload.get("authoritative_lane_boundary")
    if not isinstance(boundary, Mapping) or any(
        boundary.get(field) is not expected
        for field, expected in (
            ("authoritative_w4_registry_changed", False),
            ("authoritative_w6_projection_changed", False),
            ("existing_two_reviewer_contract_unchanged", True),
            ("authoritative_release_qualification_not_satisfied", True),
            ("production_promotion_authorized", False),
        )
    ):
        issues.append("AUTHORITATIVE_BOUNDARY")

    plan = payload.get("vector_plan")
    if not isinstance(plan, Mapping) or any(
        plan.get(field) != expected
        for field, expected in (
            ("logical_retrieval_unit", "graph_evidence_cluster"),
            ("base_vector_source", "FROZEN_W6_EXACT_VECTOR_COPY"),
            ("base_vector_count", 38),
            ("derived_vector_source", "LOCAL_PINNED_BGE_M3_W1B_BUNDLE_TEXT"),
            ("derived_vector_count", 16),
            ("individual_graph_node_embedding_forbidden", True),
            ("per_skill_vector_creation_forbidden", True),
            ("production_activation_authorized", False),
        )
    ):
        issues.append("VECTOR_PLAN")

    clusters = payload.get("clusters")
    if not isinstance(clusters, list) or len(clusters) != 54:
        issues.append("CLUSTER_COUNT")
        cluster_map: dict[str, Mapping[str, Any]] = {}
    else:
        cluster_map = {
            str(row.get("cluster_id") or ""): row
            for row in clusters
            if isinstance(row, Mapping) and str(row.get("cluster_id") or "")
        }
        if len(cluster_map) != 54:
            issues.append("CLUSTER_IDENTITIES")
    base_ids = [str(value) for value in payload.get("base_cluster_ids") or []]
    derived_ids = [str(value) for value in payload.get("derived_cluster_ids") or []]
    if len(base_ids) != 38 or len(derived_ids) != 16 or set(base_ids) & set(derived_ids):
        issues.append("CLUSTER_ORIGINS")
    else:
        expected_base = {
            str(row.get("cluster_id") or ""): row for row in base.get("clusters") or []
        }
        expected_derived = {
            str(row.get("cluster_id") or ""): row
            for row in derived.get("clusters") or []
        }
        if set(base_ids) != set(expected_base) or set(derived_ids) != set(expected_derived):
            issues.append("CLUSTER_ORIGIN_SET")
        for cluster_id in base_ids:
            if canonical_sha256(cluster_map.get(cluster_id)) != canonical_sha256(
                expected_base.get(cluster_id)
            ):
                issues.append("BASE_CLUSTER_MUTATION")
                break
        for cluster_id in derived_ids:
            if canonical_sha256(cluster_map.get(cluster_id)) != canonical_sha256(
                expected_derived.get(cluster_id)
            ):
                issues.append("DERIVED_CLUSTER_MUTATION")
                break

    expected_section_ids = _section_candidate_ids(list(cluster_map.values()))
    declared_section_ids = payload.get("section_candidate_cluster_ids")
    if declared_section_ids != expected_section_ids:
        issues.append("SECTION_CANDIDATE_IDENTITIES")
    coverage = payload.get("coverage")
    expected_counts = {section: len(ids) for section, ids in expected_section_ids.items()}
    expected_coverage = {
        "query_count": 6,
        "section_count": len(EXPECTED_SECTION_IDS),
        "query_section_case_count": 66,
        "candidate_count_by_section": expected_counts,
        "candidate_judgment_count": 6 * sum(expected_counts.values()),
        "full_finite_candidate_universe_required": True,
        "partial_top_k_judging_forbidden": True,
    }
    if coverage != expected_coverage or expected_counts != _EXPECTED_SECTION_CANDIDATE_COUNTS:
        issues.append("COVERAGE")
    return sorted(set(issues))


def write_combined_registry(repo_root: Path | str) -> tuple[Path, dict[str, Any]]:
    """Materialize the deterministic combined registry only under ``.runtime``."""

    root = Path(repo_root).resolve()
    payload = build_combined_registry(root)
    issues = validate_combined_registry(payload, root)
    if issues:
        raise FullResumeQrelW1CError(f"Combined registry invalid: {issues}")
    path = root / RUNTIME_DIR / (
        f"combined_cluster_registry.{payload['combined_registry_sha256']}.json"
    )
    _write_immutable_json(path, payload)
    return path, payload


def _base_projection_rows(
    path: Path, expected_cluster_ids: set[str]
) -> tuple[dict[str, str], dict[str, tuple[Any, ...]]]:
    try:
        with _open_read_only(path) as conn:
            metadata = dict(
                conn.execute("SELECT key, value FROM metadata ORDER BY key")
            )
            rows = conn.execute(
                "SELECT cluster_id, cluster_kind, canonical_embedding_text_sha256, "
                "authority_envelope_sha256, allowed_sections_json, vector_sha256, vector "
                "FROM cluster_vectors ORDER BY cluster_id"
            ).fetchall()
    except sqlite3.Error as exc:
        raise FullResumeQrelW1CError("W6 projection cannot be read") from exc
    by_id = {str(row[0]): row for row in rows}
    if set(by_id) != expected_cluster_ids:
        raise FullResumeQrelW1CError("W6 projection row set does not match frozen W4")
    return metadata, by_id


def _validate_base_projection(
    root: Path, base_registry: Mapping[str, Any], model: Mapping[str, Any]
) -> tuple[Path, dict[str, Any]]:
    receipt = _read_json(root / W6_RECEIPT_PATH)
    try:
        validate_w6_receipt(receipt)
    except ValueError as exc:
        raise FullResumeQrelW1CError("authoritative W6 receipt is invalid") from exc
    generation = receipt.get("generation") or {}
    manifest_path = root / str(generation.get("manifest_path") or "")
    manifest = _read_json(manifest_path)
    try:
        validate_generation_manifest(manifest)
    except ValueError as exc:
        raise FullResumeQrelW1CError("authoritative W6 generation manifest is invalid") from exc
    projection_record = manifest.get("projection") or {}
    projection_path = root / str(projection_record.get("path") or "")
    expected_digest = str(generation.get("projection_file_sha256") or "")
    if (
        not projection_path.is_file()
        or _file_sha256(projection_path) != expected_digest
        or expected_digest != projection_record.get("file_sha256")
    ):
        raise FullResumeQrelW1CError("authoritative W6 projection file binding failed")
    if (
        generation.get("projection_generation_sha256")
        != projection_record.get("generation_sha256")
        or generation.get("model_artifact_sha256") != model.get("artifact_sha256")
    ):
        raise FullResumeQrelW1CError("authoritative W6 generation binding failed")
    issues = validate_cluster_embedding_projection(
        projection_path, registry=base_registry, model_manifest=model
    )
    if issues:
        raise FullResumeQrelW1CError(f"authoritative W6 projection invalid: {issues}")
    return projection_path, dict(projection_record)


def build_combined_projection(
    output_path: Path | str,
    *,
    combined_registry: Mapping[str, Any],
    base_projection_path: Path | str,
    model_manifest: Mapping[str, Any],
    vectors_by_derived_cluster: Mapping[str, Sequence[float]],
) -> dict[str, Any]:
    """Create a separate projection with exact W6 copies plus W1B vectors."""

    path = Path(output_path)
    if path.exists():
        raise FullResumeQrelW1CError(f"immutable projection already exists: {path}")
    _validate_pinned_model(model_manifest)
    clusters = {
        str(row.get("cluster_id") or ""): row
        for row in combined_registry.get("clusters") or []
        if isinstance(row, Mapping) and str(row.get("cluster_id") or "")
    }
    base_ids = {str(value) for value in combined_registry.get("base_cluster_ids") or []}
    derived_ids = {
        str(value) for value in combined_registry.get("derived_cluster_ids") or []
    }
    if len(clusters) != 54 or len(base_ids) != 38 or len(derived_ids) != 16:
        raise FullResumeQrelW1CError("combined registry shape is invalid")
    if set(clusters) != base_ids | derived_ids or base_ids & derived_ids:
        raise FullResumeQrelW1CError("combined registry vector identities are invalid")
    if {str(value) for value in vectors_by_derived_cluster} != derived_ids:
        raise FullResumeQrelW1CError("derived cluster/vector parity mismatch")

    dimension = int(model_manifest["dimension"])
    base_path = Path(base_projection_path)
    base_metadata, base_rows = _base_projection_rows(base_path, base_ids)
    base_projection_sha256 = _file_sha256(base_path)
    if base_metadata.get("model_artifact_sha256") != model_manifest["artifact_sha256"]:
        raise FullResumeQrelW1CError("base projection model binding drifted")

    rows_by_id: dict[str, tuple[str, str, str, str, str, bytes]] = {}
    for cluster_id in sorted(base_ids):
        row = base_rows[cluster_id]
        _, kind, text_digest, authority_digest, allowed_json, vector_digest, blob = row
        cluster = clusters[cluster_id]
        if (
            kind != cluster.get("cluster_kind")
            or text_digest
            != canonical_sha256(str(cluster.get("canonical_embedding_text") or ""))
            or authority_digest != cluster.get("authority_envelope_sha256")
            or allowed_json
            != _canonical_json(sorted(str(value) for value in cluster.get("allowed_sections") or []))
            or hashlib.sha256(blob).hexdigest() != vector_digest
        ):
            raise FullResumeQrelW1CError(
                f"W6 vector authority drifted for base cluster: {cluster_id}"
            )
        _vector_bytes(_decode_vector(blob, dimension), dimension)
        rows_by_id[cluster_id] = (
            str(kind),
            str(text_digest),
            str(authority_digest),
            str(allowed_json),
            str(vector_digest),
            bytes(blob),
        )

    for cluster_id in sorted(derived_ids):
        cluster = clusters[cluster_id]
        blob = _vector_bytes(vectors_by_derived_cluster[cluster_id], dimension)
        rows_by_id[cluster_id] = (
            str(cluster.get("cluster_kind") or ""),
            canonical_sha256(str(cluster.get("canonical_embedding_text") or "")),
            str(cluster.get("authority_envelope_sha256") or ""),
            _canonical_json(
                sorted(str(value) for value in cluster.get("allowed_sections") or [])
            ),
            hashlib.sha256(blob).hexdigest(),
            blob,
        )

    source = combined_registry.get("source_authority") or {}
    generation_payload = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "combined_registry_sha256": combined_registry.get("combined_registry_sha256"),
        "base_registry_sha256": source.get("base_registry_sha256"),
        "derived_registry_sha256": source.get("derived_registry_sha256"),
        "scope_manifest_sha256": source.get("scope_manifest_sha256"),
        "base_projection_file_sha256": base_projection_sha256,
        "base_projection_generation_sha256": base_metadata.get("generation_sha256"),
        "model_artifact_sha256": model_manifest.get("artifact_sha256"),
        "model_id": model_manifest.get("model_id"),
        "model_revision": model_manifest.get("revision"),
        "dimension": dimension,
        "normalization": model_manifest.get("normalization"),
        "vectors": [
            {
                "cluster_id": cluster_id,
                "canonical_embedding_text_sha256": rows_by_id[cluster_id][1],
                "authority_envelope_sha256": rows_by_id[cluster_id][2],
                "vector_sha256": rows_by_id[cluster_id][4],
            }
            for cluster_id in sorted(rows_by_id)
        ],
    }
    generation_sha256 = canonical_sha256(generation_payload)
    metadata = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "status": PROJECTION_STATUS,
        "generation_sha256": generation_sha256,
        "combined_registry_sha256": str(generation_payload["combined_registry_sha256"]),
        "base_registry_sha256": str(generation_payload["base_registry_sha256"]),
        "derived_registry_sha256": str(generation_payload["derived_registry_sha256"]),
        "scope_manifest_sha256": str(generation_payload["scope_manifest_sha256"]),
        "base_projection_file_sha256": base_projection_sha256,
        "base_projection_generation_sha256": str(
            generation_payload["base_projection_generation_sha256"]
        ),
        "model_artifact_sha256": str(model_manifest["artifact_sha256"]),
        "model_id": str(model_manifest["model_id"]),
        "model_revision": str(model_manifest["revision"]),
        "dimension": str(dimension),
        "normalization": str(model_manifest["normalization"]),
        "vector_count": str(len(rows_by_id)),
        "base_vector_count": str(len(base_ids)),
        "derived_vector_count": str(len(derived_ids)),
        "logical_retrieval_unit": "graph_evidence_cluster",
        "result_label": RESULT_LABEL,
        "production_promotion_authorized": "false",
    }
    if any(not value for value in metadata.values()):
        raise FullResumeQrelW1CError("combined projection metadata is incomplete")

    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.staging-{os.getpid()}")
    try:
        if staging.exists():
            staging.unlink()
        conn = sqlite3.connect(staging)
        try:
            conn.execute("PRAGMA page_size=4096")
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
            conn.execute("PRAGMA locking_mode=EXCLUSIVE")
            conn.execute("PRAGMA auto_vacuum=NONE")
            conn.execute("PRAGMA application_id=1330797644")
            conn.execute("PRAGMA user_version=1")
            conn.execute(
                "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) "
                "WITHOUT ROWID"
            )
            conn.execute(
                "CREATE TABLE cluster_vectors ("
                "cluster_id TEXT PRIMARY KEY, "
                "cluster_kind TEXT NOT NULL, "
                "canonical_embedding_text_sha256 TEXT NOT NULL, "
                "authority_envelope_sha256 TEXT NOT NULL, "
                "allowed_sections_json TEXT NOT NULL, "
                "vector_sha256 TEXT NOT NULL, "
                "vector BLOB NOT NULL"
                ") WITHOUT ROWID"
            )
            conn.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                sorted(metadata.items()),
            )
            for cluster_id in sorted(rows_by_id):
                kind, text_digest, authority_digest, allowed_json, vector_digest, blob = (
                    rows_by_id[cluster_id]
                )
                conn.execute(
                    "INSERT INTO cluster_vectors VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        cluster_id,
                        kind,
                        text_digest,
                        authority_digest,
                        allowed_json,
                        vector_digest,
                        blob,
                    ),
                )
            conn.commit()
            conn.execute("VACUUM")
            conn.commit()
        finally:
            conn.close()
        os.replace(staging, path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "status": PROJECTION_STATUS,
        "generation_sha256": generation_sha256,
        "sqlite_sha256": _file_sha256(path),
        "vector_count": len(rows_by_id),
        "base_vector_count": len(base_ids),
        "derived_vector_count": len(derived_ids),
        "dimension": dimension,
        "normalization": str(model_manifest["normalization"]),
        "base_projection_file_sha256": base_projection_sha256,
        "base_projection_generation_sha256": base_metadata.get("generation_sha256"),
    }


def validate_combined_projection(
    path: Path | str,
    *,
    combined_registry: Mapping[str, Any],
    base_projection_path: Path | str,
    model_manifest: Mapping[str, Any],
) -> list[str]:
    """Validate the private projection's parity, bindings, and exact W6 copies."""

    issues: list[str] = []
    try:
        _validate_pinned_model(model_manifest)
    except FullResumeQrelW1CError:
        return ["MODEL_BINDING"]
    db_path = Path(path)
    if not db_path.is_file():
        return ["PROJECTION_MISSING"]
    clusters = {
        str(row.get("cluster_id") or ""): row
        for row in combined_registry.get("clusters") or []
        if isinstance(row, Mapping) and str(row.get("cluster_id") or "")
    }
    base_ids = {str(value) for value in combined_registry.get("base_cluster_ids") or []}
    derived_ids = {
        str(value) for value in combined_registry.get("derived_cluster_ids") or []
    }
    if len(clusters) != 54 or set(clusters) != base_ids | derived_ids:
        return ["COMBINED_REGISTRY_INVALID"]
    try:
        metadata, rows = _base_projection_rows(Path(base_projection_path), base_ids)
        with _open_read_only(db_path) as conn:
            observed_metadata = dict(
                conn.execute("SELECT key, value FROM metadata ORDER BY key")
            )
            observed_rows = conn.execute(
                "SELECT cluster_id, cluster_kind, canonical_embedding_text_sha256, "
                "authority_envelope_sha256, allowed_sections_json, vector_sha256, vector "
                "FROM cluster_vectors ORDER BY cluster_id"
            ).fetchall()
    except FullResumeQrelW1CError:
        return ["BASE_PROJECTION_INVALID"]
    except sqlite3.Error:
        return ["PROJECTION_SQLITE_ERROR"]

    source = combined_registry.get("source_authority") or {}
    expected_metadata = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "status": PROJECTION_STATUS,
        "combined_registry_sha256": str(
            combined_registry.get("combined_registry_sha256") or ""
        ),
        "base_registry_sha256": str(source.get("base_registry_sha256") or ""),
        "derived_registry_sha256": str(source.get("derived_registry_sha256") or ""),
        "scope_manifest_sha256": str(source.get("scope_manifest_sha256") or ""),
        "base_projection_file_sha256": _file_sha256(Path(base_projection_path)),
        "base_projection_generation_sha256": str(metadata.get("generation_sha256") or ""),
        "model_artifact_sha256": str(model_manifest.get("artifact_sha256") or ""),
        "model_id": str(model_manifest.get("model_id") or ""),
        "model_revision": str(model_manifest.get("revision") or ""),
        "dimension": str(model_manifest.get("dimension") or ""),
        "normalization": str(model_manifest.get("normalization") or ""),
        "vector_count": "54",
        "base_vector_count": "38",
        "derived_vector_count": "16",
        "logical_retrieval_unit": "graph_evidence_cluster",
        "result_label": RESULT_LABEL,
        "production_promotion_authorized": "false",
    }
    for key, value in expected_metadata.items():
        if observed_metadata.get(key) != value:
            issues.append(f"METADATA_MISMATCH:{key}")

    observed_by_id = {str(row[0]): row for row in observed_rows}
    if set(observed_by_id) != set(clusters):
        issues.append("CLUSTER_VECTOR_PARITY")
    dimension = int(model_manifest["dimension"])
    for cluster_id, row in observed_by_id.items():
        if cluster_id not in clusters:
            continue
        _, kind, text_digest, authority_digest, allowed_json, vector_digest, blob = row
        cluster = clusters[cluster_id]
        if kind != cluster.get("cluster_kind"):
            issues.append(f"CLUSTER_KIND:{cluster_id}")
        if text_digest != canonical_sha256(str(cluster.get("canonical_embedding_text") or "")):
            issues.append(f"TEXT_DIGEST:{cluster_id}")
        if authority_digest != cluster.get("authority_envelope_sha256"):
            issues.append(f"AUTHORITY_DIGEST:{cluster_id}")
        if allowed_json != _canonical_json(
            sorted(str(value) for value in cluster.get("allowed_sections") or [])
        ):
            issues.append(f"SECTION_BINDING:{cluster_id}")
        if hashlib.sha256(blob).hexdigest() != vector_digest:
            issues.append(f"VECTOR_DIGEST:{cluster_id}")
        try:
            _vector_bytes(_decode_vector(blob, dimension), dimension)
        except FullResumeQrelW1CError:
            issues.append(f"VECTOR_CONTRACT:{cluster_id}")
        if cluster_id in base_ids:
            base_row = rows.get(cluster_id)
            if base_row is None or tuple(row[1:]) != tuple(base_row[1:]):
                issues.append(f"BASE_VECTOR_NOT_EXACT_COPY:{cluster_id}")

    generation_payload = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "combined_registry_sha256": combined_registry.get("combined_registry_sha256"),
        "base_registry_sha256": source.get("base_registry_sha256"),
        "derived_registry_sha256": source.get("derived_registry_sha256"),
        "scope_manifest_sha256": source.get("scope_manifest_sha256"),
        "base_projection_file_sha256": _file_sha256(Path(base_projection_path)),
        "base_projection_generation_sha256": metadata.get("generation_sha256"),
        "model_artifact_sha256": model_manifest.get("artifact_sha256"),
        "model_id": model_manifest.get("model_id"),
        "model_revision": model_manifest.get("revision"),
        "dimension": dimension,
        "normalization": model_manifest.get("normalization"),
        "vectors": [
            {
                "cluster_id": cluster_id,
                "canonical_embedding_text_sha256": str(row[2]),
                "authority_envelope_sha256": str(row[3]),
                "vector_sha256": str(row[5]),
            }
            for cluster_id, row in sorted(observed_by_id.items())
        ],
    }
    if observed_metadata.get("generation_sha256") != canonical_sha256(generation_payload):
        issues.append("GENERATION_DIGEST")
    return sorted(set(issues))


def _build_generation_manifest(
    *,
    root: Path,
    combined_registry_path: Path,
    combined_registry: Mapping[str, Any],
    derived_registry_path: Path,
    model_manifest_path: Path,
    model_manifest: Mapping[str, Any],
    projection_path: Path,
    projection: Mapping[str, Any],
    runtime_proof: Mapping[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": GENERATION_MANIFEST_SCHEMA_VERSION,
        "status": PROJECTION_STATUS,
        "result_label": RESULT_LABEL,
        "source_authority": {
            **dict(combined_registry["source_authority"]),
            "combined_registry_path": _repository_path(combined_registry_path, root),
            "combined_registry_file_sha256": _file_sha256(combined_registry_path),
            "derived_registry_path": _repository_path(derived_registry_path, root),
            "derived_registry_file_sha256": _file_sha256(derived_registry_path),
        },
        "model": {
            "path": _repository_path(model_manifest_path, root),
            "file_sha256": _file_sha256(model_manifest_path),
            **dict(model_manifest),
        },
        "projection": {
            "path": _repository_path(projection_path, root),
            "file_sha256": _file_sha256(projection_path),
            **dict(projection),
        },
        "runtime_proof": dict(runtime_proof),
        "scope_guards": {
            "human_qrels_created": False,
            "rankings_frozen": False,
            "metrics_computable": False,
            "authoritative_release_qualification_satisfied": False,
            "activation_manifest_created": False,
            "production_promotion_authorized": False,
        },
    }
    payload["manifest_sha256"] = canonical_sha256(payload)
    return payload


def materialize_w1c_projection(
    repo_root: Path | str,
    *,
    model_path: Path | str,
    device: str,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Generate the private W1C 54-vector projection and readiness receipt."""

    root = Path(repo_root).resolve()
    derived_registry_path, _ = write_derived_bundle_registry(root)
    combined_registry_path, combined = write_combined_registry(root)
    issues = validate_combined_registry(combined, root)
    if issues:
        raise FullResumeQrelW1CError(f"Combined registry invalid: {issues}")
    base = _base_registry(root)
    model = build_local_model_manifest(model_path)
    _validate_pinned_model(model)
    base_projection_path, _ = _validate_base_projection(root, base, model)

    model_manifest_path = root / RUNTIME_DIR / (
        f"bge_m3_model_manifest.{model['artifact_sha256']}.json"
    )
    _write_immutable_json(model_manifest_path, model)
    derived_ids = sorted(str(value) for value in combined["derived_cluster_ids"])
    cluster_by_id = {str(row["cluster_id"]): row for row in combined["clusters"]}
    runtime_proof, vectors = encode_bge_m3(
        [str(cluster_by_id[cluster_id]["canonical_embedding_text"]) for cluster_id in derived_ids],
        model_path=model_path,
        device=device,
        batch_size=8,
    )
    if runtime_proof.get("fallback_used") is not False or runtime_proof.get(
        "vector_count"
    ) != len(derived_ids):
        raise FullResumeQrelW1CError("BGE-M3 runtime proof is incomplete")
    vectors_by_derived_cluster = dict(zip(derived_ids, vectors, strict=True))
    staging = root / RUNTIME_DIR / f".combined-vectors-{os.getpid()}.sqlite"
    projection = build_combined_projection(
        staging,
        combined_registry=combined,
        base_projection_path=base_projection_path,
        model_manifest=model,
        vectors_by_derived_cluster=vectors_by_derived_cluster,
    )
    projection_path = root / RUNTIME_DIR / (
        "full_resume_cluster_embeddings."
        f"{projection['generation_sha256']}.sqlite"
    )
    if projection_path.exists():
        if _file_sha256(projection_path) != projection["sqlite_sha256"]:
            staging.unlink(missing_ok=True)
            raise FullResumeQrelW1CError(
                f"Immutable projection collision: {projection_path}"
            )
        staging.unlink(missing_ok=True)
    else:
        os.replace(staging, projection_path)
    projection_issues = validate_combined_projection(
        projection_path,
        combined_registry=combined,
        base_projection_path=base_projection_path,
        model_manifest=model,
    )
    if projection_issues:
        raise FullResumeQrelW1CError(
            f"Combined projection invalid: {projection_issues}"
        )

    generation = _build_generation_manifest(
        root=root,
        combined_registry_path=combined_registry_path,
        combined_registry=combined,
        derived_registry_path=derived_registry_path,
        model_manifest_path=model_manifest_path,
        model_manifest=model,
        projection_path=projection_path,
        projection=projection,
        runtime_proof=runtime_proof,
    )
    generation_path = root / RUNTIME_DIR / (
        "full_resume_projection_generation."
        f"{generation['manifest_sha256']}.json"
    )
    _write_immutable_json(generation_path, generation)

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": RECEIPT_STATUS,
        "result_label": RESULT_LABEL,
        "combined_registry": {
            "path": _repository_path(combined_registry_path, root),
            "file_sha256": _file_sha256(combined_registry_path),
            "combined_registry_sha256": combined["combined_registry_sha256"],
            "base_cluster_count": len(combined["base_cluster_ids"]),
            "derived_cluster_count": len(combined["derived_cluster_ids"]),
        },
        "projection": {
            "path": _repository_path(projection_path, root),
            "file_sha256": _file_sha256(projection_path),
            **dict(projection),
        },
        "generation_manifest": {
            "path": _repository_path(generation_path, root),
            "file_sha256": _file_sha256(generation_path),
            "manifest_sha256": generation["manifest_sha256"],
        },
        "coverage": dict(combined["coverage"]),
        "runtime_proof": dict(runtime_proof),
        "scope_guards": dict(generation["scope_guards"]),
        "next_action": "W2_GENERATE_AND_FREEZE_ALL_66_RANKINGS",
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    receipt_path = root / RUNTIME_DIR / (
        f"w1c_combined_projection_receipt.{receipt['receipt_sha256']}.json"
    )
    _write_immutable_json(receipt_path, receipt)
    return receipt, {
        "derived_registry": derived_registry_path,
        "combined_registry": combined_registry_path,
        "model_manifest": model_manifest_path,
        "projection": projection_path,
        "generation_manifest": generation_path,
        "receipt": receipt_path,
    }


__all__ = [
    "COMBINED_REGISTRY_SCHEMA_VERSION",
    "COMBINED_REGISTRY_STATUS",
    "FullResumeQrelW1CError",
    "GENERATION_MANIFEST_SCHEMA_VERSION",
    "PROJECTION_SCHEMA_VERSION",
    "PROJECTION_STATUS",
    "RECEIPT_SCHEMA_VERSION",
    "RECEIPT_STATUS",
    "RUNTIME_DIR",
    "build_combined_projection",
    "build_combined_registry",
    "materialize_w1c_projection",
    "validate_combined_projection",
    "validate_combined_registry",
    "write_combined_registry",
]
