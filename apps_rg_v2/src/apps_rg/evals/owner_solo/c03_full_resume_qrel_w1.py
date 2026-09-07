"""W1 preflight for the full-resume owner-solo C0.3 QREL scope.

W1 may proceed to ranking generation only when every scoped resume section has
an active graph-evidence-cluster candidate universe.  This preflight does not
generate query vectors, rankings, labels, metrics, or release authority.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.evals.owner_solo.c03_full_resume_qrel_scope import (
    EXPECTED_SECTION_IDS,
    load_full_resume_scope,
    validate_full_resume_scope,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (
    REGISTRY_PATH,
)
from apps_rg.fact_inventory.c03_skill_embedding_builder import (
    build_local_model_manifest,
)
from apps_rg.runtime.graph_evidence_cluster_embedding_projection import (
    validate_cluster_embedding_projection,
)
from apps_rg.runtime.sections.headline_positioning_evidence import (
    build_headline_positioning_section_packet,
)
from apps_rg.runtime.sections.ibm_role_episode_evidence import (
    build_ibm_role_episode_section_packet,
)


W6_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave6_cluster_vector_generation_receipt.json"
)
PREflight_SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_qrel_w1_preflight.v1"
RUNTIME_RECEIPT_PATH = Path(
    ".runtime/c03-owner-solo-qrel/full_resume_w1_preflight_receipt.v1.json"
)


class FullResumeQrelW1Error(ValueError):
    """Raised when the W1 preflight cannot be evaluated safely."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FullResumeQrelW1Error(f"JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise FullResumeQrelW1Error(f"JSON object required: {path}")
    return value


def _file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FullResumeQrelW1Error(f"File unavailable: {path}") from exc
    return digest.hexdigest()


def _active_cluster_counts(registry: Mapping[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in registry.get("clusters") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("activation_status") != "ACTIVE_CONFIRMED":
            continue
        for section_id in row.get("allowed_sections") or []:
            counts[str(section_id)] += 1
    return counts


def _model_path() -> Path:
    value = str(os.environ.get("APPS_RG_EMBEDDING_MODEL_PATH") or "").strip()
    if not value:
        raise FullResumeQrelW1Error("APPS_RG_EMBEDDING_MODEL_PATH is not set")
    path = Path(value).resolve()
    if not path.is_dir():
        raise FullResumeQrelW1Error(f"local BGE-M3 model directory is missing: {path}")
    return path


def _runtime_graph_source_coverage(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Prove runtime graph source packets exist independently of C0 projection rows."""

    headline = build_headline_positioning_section_packet(repo_root=repo_root)
    coverage: dict[str, dict[str, Any]] = {
        "headline": {
            "source_present": True,
            "source_type": "headline_positioning_bundles",
            "bundle_count": len(headline["headline_positioning_bundles"]),
            "graph_skill_node_count": len(headline["graph_skill_node_ids"]),
            "linked_source_fact_count": len(headline["source_fact_ids"]),
        }
    }
    for section_id in ("ibm_bullets", "ibm_narrative"):
        packet = build_ibm_role_episode_section_packet(section_id, repo_root=repo_root)
        bundles = packet["role_episode_bundles"]
        coverage[section_id] = {
            "source_present": True,
            "source_type": "ibm_role_episode_bundles",
            "bundle_count": len(bundles),
            "graph_skill_node_count": len(
                {
                    str(skill_id)
                    for bundle in bundles
                    for skill_id in bundle["graph_skill_node_ids"]
                }
            ),
            "linked_source_fact_count": len(
                {
                    str(fact_id)
                    for bundle in bundles
                    for fact_id in bundle["linked_source_fact_ids"]
                }
            ),
        }
    return coverage


def run_w1_preflight(repo_root: Path | str) -> dict[str, Any]:
    """Validate W1 inputs and report whether ranking generation may begin."""

    root = Path(repo_root).resolve()
    scope = load_full_resume_scope(root)
    issues = validate_full_resume_scope(scope, root)
    registry_path = root / REGISTRY_PATH
    w6_path = root / W6_RECEIPT_PATH
    if not registry_path.is_file():
        issues.append("REGISTRY_MISSING")
    if not w6_path.is_file():
        issues.append("W6_RECEIPT_MISSING")
    registry: dict[str, Any] = {}
    w6: dict[str, Any] = {}
    if registry_path.is_file():
        registry = _read_json(registry_path)
    if w6_path.is_file():
        w6 = _read_json(w6_path)

    model_manifest: dict[str, Any] = {}
    model_path: Path | None = None
    try:
        model_path = _model_path()
        model_manifest = build_local_model_manifest(model_path)
    except FullResumeQrelW1Error as exc:
        issues.append(f"MODEL:{exc}")

    generation = w6.get("generation") if isinstance(w6.get("generation"), Mapping) else {}
    projection_path = root / str(generation.get("projection_path") or "")
    if not projection_path.is_file():
        issues.append("PROJECTION_MISSING")
    else:
        expected_model = model_manifest or None
        issues.extend(
            f"PROJECTION:{issue}"
            for issue in validate_cluster_embedding_projection(
                projection_path,
                registry=registry,
                model_manifest=expected_model,
            )
        )

    counts = _active_cluster_counts(registry)
    missing_sections = [section for section in EXPECTED_SECTION_IDS if counts[section] == 0]
    runtime_source_coverage: dict[str, dict[str, Any]] = {}
    try:
        runtime_source_coverage = _runtime_graph_source_coverage(root)
    except (KeyError, TypeError, ValueError) as exc:
        issues.append(f"RUNTIME_GRAPH_SOURCE_PACKET:{type(exc).__name__}")
    if missing_sections:
        issues.append(
            "C0_PROJECTION_CANDIDATE_UNIVERSE_MISSING:"
            + ",".join(missing_sections)
        )

    available_section_counts = {
        section: counts[section] for section in EXPECTED_SECTION_IDS if counts[section] > 0
    }
    target_count = len(scope.get("targets") or [])
    available_case_count = target_count * len(available_section_counts)
    available_judgment_count = target_count * sum(available_section_counts.values())
    return {
        "schema_version": PREflight_SCHEMA_VERSION,
        "status": (
            "W1_READY_FOR_RANKING_GENERATION"
            if not issues
            else "W1_BLOCKED_PROJECTION_COVERAGE"
        ),
        "scope_status": scope.get("status"),
        "target_count": target_count,
        "target_ids": [str(row.get("query_id") or "") for row in scope.get("targets") or []],
        "section_count": len(EXPECTED_SECTION_IDS),
        "section_ids": list(EXPECTED_SECTION_IDS),
        "query_section_case_count": target_count * len(EXPECTED_SECTION_IDS),
        "candidate_judgment_count": None,
        "available_candidate_universe_by_section": available_section_counts,
        "available_case_count_before_missing_sections": available_case_count,
        "available_candidate_judgment_count_before_missing_sections": available_judgment_count,
        "missing_c0_sections": missing_sections,
        "runtime_graph_source_coverage": runtime_source_coverage,
        "registry_sha256": registry.get("registry_sha256"),
        "projection_path": str(projection_path.relative_to(root)) if projection_path.is_file() else None,
        "projection_file_sha256": _file_sha256(projection_path) if projection_path.is_file() else None,
        "model_id": model_manifest.get("model_id"),
        "model_revision": model_manifest.get("revision"),
        "model_artifact_sha256": model_manifest.get("artifact_sha256"),
        "ranking_identity_sha256": None,
        "human_qrels_created": False,
        "metrics_computable": False,
        "release_authorizing": False,
        "issues": sorted(set(issues)),
        "next_action": (
            "MATERIALIZE_DERIVED_SECTION_BUNDLES_FROM_EXISTING_GRAPH_AUTHORITY_AND_REGENERATE_PROJECTION"
            if missing_sections
            else "GENERATE_AND_FREEZE_ALL_66_RANKINGS_AND_FULL_CANDIDATE_UNIVERSES"
        ),
    }


def write_w1_preflight_receipt(
    repo_root: Path | str, receipt_path: Path | str = RUNTIME_RECEIPT_PATH
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    result = run_w1_preflight(root)
    path = Path(receipt_path)
    path = path if path.is_absolute() else root / path
    runtime = (root / ".runtime").resolve()
    try:
        path.resolve().relative_to(runtime)
    except ValueError as exc:
        raise FullResumeQrelW1Error("W1 receipt must remain under ignored .runtime") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
