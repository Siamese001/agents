"""GE-W0 authority/version baseline for governed graph evolution.

This module is deliberately read-only.  It distinguishes the augmented skills
graph (runtime authority) from candidate evidence and all derived retrieval
surfaces.  Later GE waves own staging, Author Gate, UWG graph mutation,
projection rebuild, and activation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.augmented_skills_graph import (
    SOURCE_AUTHORITY_AUGMENTED_SKILLS_GRAPH,
    augmented_skills_graph_path_explicit,
    graph_payload_digest,
    graph_version_from_payload,
    load_augmented_skills_graph,
)

GE_W0_CONTRACT_RELATIVE_PATH = Path(
    "src/apps_rg/fact_inventory/graph_evolution_authority_contract.v1.json"
)
GE_W0_BASELINE_RECEIPT_RELATIVE_PATH = Path(
    "artifacts/apps_rg/c03/graph_evolution/ge_w0_authority_baseline_receipt.json"
)
W4_RECEIPT_RELATIVE_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave4_cluster_registry_receipt.json"
)
W6_RECEIPT_RELATIVE_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave6_cluster_vector_generation_receipt.json"
)

GE_W0_CONTRACT_SCHEMA_VERSION = "apps_rg.graph_evolution_authority_contract.v1"
GE_W0_BASELINE_RECEIPT_SCHEMA_VERSION = (
    "apps_rg.graph_evolution_authority_baseline_receipt.v1"
)
GE_W0_COMPLETION_MARKER = "GE_W0_AUTHORITY_LOCKED"
CANONICAL_GRAPH_WRITE_AUTHORITY = "UWG_ONLY"
ACTIVE_POINTER_AUTHORITY = "OWNER_APPROVED_RELEASE_AUTHORITY_ONLY"
_SHA256_LENGTH = 64


class GraphEvolutionAuthorityError(ValueError):
    """Raised when a GE-W0 authority or baseline binding is invalid."""


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    candidate = str(value or "")
    return len(candidate) == _SHA256_LENGTH and all(
        character in "0123456789abcdef" for character in candidate
    )


def _repo_path(root: Path, relative_path: str | Path) -> Path:
    path = (root / Path(relative_path)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise GraphEvolutionAuthorityError(
            f"GE-W0 path escapes repository root: {relative_path}"
        ) from exc
    return path


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path.resolve())


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphEvolutionAuthorityError(f"GE-W0 JSON is unavailable: {path}") from exc
    if not isinstance(payload, dict):
        raise GraphEvolutionAuthorityError(f"GE-W0 JSON must be an object: {path}")
    return payload


def load_ge_w0_authority_contract(repo_root: Path | str) -> dict[str, Any]:
    """Load the frozen GE-W0 contract without changing repository state."""

    root = Path(repo_root).resolve()
    return _load_json(_repo_path(root, GE_W0_CONTRACT_RELATIVE_PATH))


def load_ge_w0_authority_baseline_receipt(repo_root: Path | str) -> dict[str, Any]:
    """Load the checked-in GE-W0 baseline receipt without changing repository state."""

    root = Path(repo_root).resolve()
    return _load_json(_repo_path(root, GE_W0_BASELINE_RECEIPT_RELATIVE_PATH))


def validate_ge_w0_authority_contract(contract: Mapping[str, Any]) -> list[str]:
    """Return deterministic GE-W0 contract failures; an empty list is valid."""

    issues: list[str] = []
    if contract.get("schema_version") != GE_W0_CONTRACT_SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if contract.get("contract_id") != "APPS_RG_GRAPH_EVOLUTION_AUTHORITY":
        issues.append("CONTRACT_ID")
    if contract.get("wave") != "GE_W0":
        issues.append("WAVE")
    if contract.get("status") != "FROZEN":
        issues.append("STATUS")

    canonical = contract.get("canonical_graph")
    if not isinstance(canonical, Mapping):
        issues.append("CANONICAL_GRAPH")
    else:
        if canonical.get("authority_source") != SOURCE_AUTHORITY_AUGMENTED_SKILLS_GRAPH:
            issues.append("CANONICAL_GRAPH_AUTHORITY")
        if canonical.get("artifact_path") != (
            "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
        ):
            issues.append("CANONICAL_GRAPH_PATH")
        if canonical.get("canonical_write_authority") != CANONICAL_GRAPH_WRITE_AUTHORITY:
            issues.append("CANONICAL_GRAPH_WRITE_AUTHORITY")
        if canonical.get("active_pointer_authority") != ACTIVE_POINTER_AUTHORITY:
            issues.append("ACTIVE_POINTER_AUTHORITY")
        if canonical.get("runtime_source") != "augmented_skills_graph_sqlite":
            issues.append("CANONICAL_RUNTIME_SOURCE")

    substrate = contract.get("claim_evidence_substrate")
    if not isinstance(substrate, Mapping):
        issues.append("CLAIM_EVIDENCE_SUBSTRATE")
    elif (
        substrate.get("source_type") != "candidate_fact_ledger"
        or substrate.get("runtime_claim_authority") is not False
        or substrate.get("may_propose_graph_mutation") is not True
        or substrate.get("requires_author_gate_before_uwg") is not True
    ):
        issues.append("CLAIM_EVIDENCE_SUBSTRATE_BOUNDARY")

    derived = contract.get("derived_surfaces")
    if not isinstance(derived, Mapping):
        issues.append("DERIVED_SURFACES")
    else:
        cluster_registry = derived.get("graph_evidence_cluster_registry")
        cluster_projection = derived.get("graph_evidence_cluster_projection")
        fact_vectors = derived.get("fact_vectors")
        semantic_cache = derived.get("r1b_semantic_cache")
        if not isinstance(cluster_registry, Mapping) or (
            cluster_registry.get("claim_authority") is not False
            or cluster_registry.get("must_bind_current_graph_digest") is not True
        ):
            issues.append("CLUSTER_REGISTRY_BOUNDARY")
        if not isinstance(cluster_projection, Mapping) or (
            cluster_projection.get("claim_authority") is not False
            or cluster_projection.get("logical_retrieval_unit") != "graph_evidence_cluster"
            or cluster_projection.get("must_bind_current_graph_digest") is not True
            or cluster_projection.get("exact_current_graph_rehydration_required") is not True
        ):
            issues.append("CLUSTER_PROJECTION_BOUNDARY")
        for name, surface in (("FACT_VECTORS", fact_vectors), ("R1B_SEMANTIC_CACHE", semantic_cache)):
            if not isinstance(surface, Mapping) or surface.get("claim_authority") is not False or surface.get(
                "may_not_mutate_canonical_graph"
            ) is not True:
                issues.append(f"{name}_BOUNDARY")

    states = contract.get("graph_version_states")
    expected_states = [
        "STAGED",
        "AUTHOR_APPROVED",
        "UWG_COMMITTED_CANDIDATE",
        "GRAPH_VALIDATED",
        "PROJECTION_BUILT",
        "RETRIEVAL_QUALIFIED",
        "ACTIVATED",
        "RETIRED",
    ]
    if states != expected_states:
        issues.append("GRAPH_VERSION_STATES")

    transitions = contract.get("allowed_transitions")
    if not isinstance(transitions, list) or ["STAGED", "ACTIVATED"] in transitions:
        issues.append("GRAPH_VERSION_TRANSITIONS")

    qrel = contract.get("qrel_binding")
    if not isinstance(qrel, Mapping) or any(
        qrel.get(field) is not True
        for field in (
            "frozen_graph_digest_required",
            "frozen_registry_digest_required",
            "frozen_projection_digest_required",
            "full_candidate_universe_required",
            "partial_top_k_judging_forbidden",
            "graph_change_invalidates_prior_ranking_identity",
        )
    ):
        issues.append("QREL_BINDING")

    runtime_boundary = contract.get("runtime_write_boundary")
    if not isinstance(runtime_boundary, Mapping) or any(
        runtime_boundary.get(field) is not True
        for field in (
            "u0_to_exit_cannot_mutate_canonical_graph",
            "shadow_cannot_mutate_current_run",
            "generated_or_targeting_text_cannot_be_claim_authority",
        )
    ):
        issues.append("RUNTIME_WRITE_BOUNDARY")

    ge_w0_exit = contract.get("ge_w0_exit")
    if not isinstance(ge_w0_exit, Mapping) or (
        ge_w0_exit.get("completion_marker") != GE_W0_COMPLETION_MARKER
        or any(
            ge_w0_exit.get(field) is not False
            for field in (
                "canonical_graph_mutated",
                "cluster_registry_mutated",
                "cluster_projection_mutated",
                "activation_created",
            )
        )
    ):
        issues.append("GE_W0_EXIT")
    return issues


def _derived_surface_receipt(root: Path, receipt_path: Path, key: str) -> dict[str, Any]:
    receipt = _load_json(receipt_path)
    if key == "registry":
        relative = str((receipt.get("registry") or {}).get("path") or "")
    else:
        relative = str((receipt.get("generation") or {}).get("projection_path") or "")
    if not relative:
        raise GraphEvolutionAuthorityError(f"GE-W0 {key} path is missing from {receipt_path}")
    artifact = _repo_path(root, relative)
    if not artifact.is_file():
        raise GraphEvolutionAuthorityError(f"GE-W0 {key} artifact is missing: {artifact}")
    return {
        "receipt_path": _relative_path(root, receipt_path),
        "receipt_file_sha256": _file_sha256(receipt_path),
        "path": _relative_path(root, artifact),
        "file_sha256": _file_sha256(artifact),
    }


def build_ge_w0_authority_baseline(repo_root: Path | str) -> dict[str, Any]:
    """Build a deterministic, read-only authority baseline receipt for Graph V0."""

    root = Path(repo_root).resolve()
    contract_path = _repo_path(root, GE_W0_CONTRACT_RELATIVE_PATH)
    contract = _load_json(contract_path)
    issues = validate_ge_w0_authority_contract(contract)
    if issues:
        raise GraphEvolutionAuthorityError(
            f"GE-W0 authority contract invalid: {', '.join(issues)}"
        )

    graph_path = augmented_skills_graph_path_explicit(None, repo_root=root)
    graph = load_augmented_skills_graph(repo_root=root, path=graph_path)
    graph_metadata = graph.get("metadata") if isinstance(graph.get("metadata"), Mapping) else {}
    candidate_ref = str(graph_metadata.get("candidate_fact_ledger_ref") or "")
    if not candidate_ref:
        raise GraphEvolutionAuthorityError("GE-W0 canonical graph omits candidate fact ledger reference")
    candidate_path = _repo_path(root, candidate_ref)
    if not candidate_path.is_file():
        raise GraphEvolutionAuthorityError(
            f"GE-W0 candidate fact ledger is missing: {candidate_path}"
        )

    registry = _derived_surface_receipt(
        root, _repo_path(root, W4_RECEIPT_RELATIVE_PATH), "registry"
    )
    projection = _derived_surface_receipt(
        root, _repo_path(root, W6_RECEIPT_RELATIVE_PATH), "projection"
    )
    receipt: dict[str, Any] = {
        "schema_version": GE_W0_BASELINE_RECEIPT_SCHEMA_VERSION,
        "wave": "GE_W0",
        "status": "PASS",
        "completion_marker": GE_W0_COMPLETION_MARKER,
        "contract": {
            "path": GE_W0_CONTRACT_RELATIVE_PATH.as_posix(),
            "file_sha256": _file_sha256(contract_path),
            "canonical_sha256": _canonical_sha256(contract),
        },
        "canonical_graph": {
            "authority_source": SOURCE_AUTHORITY_AUGMENTED_SKILLS_GRAPH,
            "path": _relative_path(root, graph_path),
            "file_sha256": _file_sha256(graph_path),
            "payload_sha256": graph_payload_digest(graph),
            "graph_version": graph_version_from_payload(graph),
            "canonical_write_authority": CANONICAL_GRAPH_WRITE_AUTHORITY,
            "runtime_source": "augmented_skills_graph_sqlite",
        },
        "claim_evidence_substrate": {
            "source_type": "candidate_fact_ledger",
            "path": _relative_path(root, candidate_path),
            "file_sha256": _file_sha256(candidate_path),
            "runtime_claim_authority": False,
        },
        "derived_surfaces": {
            "graph_evidence_cluster_registry": registry,
            "graph_evidence_cluster_projection": projection,
            "fact_vectors": {
                "target_surface": "l4.apps_rg.fact_vectors",
                "claim_authority": False,
                "may_not_mutate_canonical_graph": True,
            },
            "r1b_semantic_cache": {
                "claim_authority": False,
                "may_not_mutate_canonical_graph": True,
            },
        },
        "runtime_write_boundary": dict(contract["runtime_write_boundary"]),
        "qrel_binding": dict(contract["qrel_binding"]),
        "baseline_is_read_only": True,
        "activation_created": False,
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def validate_ge_w0_authority_baseline(
    receipt: Mapping[str, Any], *, repo_root: Path | str
) -> list[str]:
    """Validate a GE-W0 receipt against the current repository without writes."""

    root = Path(repo_root).resolve()
    issues: list[str] = []
    if receipt.get("schema_version") != GE_W0_BASELINE_RECEIPT_SCHEMA_VERSION:
        issues.append("RECEIPT_SCHEMA_VERSION")
    if receipt.get("status") != "PASS" or receipt.get("completion_marker") != GE_W0_COMPLETION_MARKER:
        issues.append("RECEIPT_STATUS")
    if receipt.get("baseline_is_read_only") is not True or receipt.get("activation_created") is not False:
        issues.append("RECEIPT_WRITE_BOUNDARY")

    unsigned = dict(receipt)
    recorded_receipt_digest = str(unsigned.pop("receipt_sha256", "") or "")
    if not _is_sha256(recorded_receipt_digest) or recorded_receipt_digest != _canonical_sha256(unsigned):
        issues.append("RECEIPT_DIGEST")

    expected = build_ge_w0_authority_baseline(root)
    for key in (
        "contract",
        "canonical_graph",
        "claim_evidence_substrate",
        "derived_surfaces",
        "runtime_write_boundary",
        "qrel_binding",
        "baseline_is_read_only",
        "activation_created",
    ):
        if receipt.get(key) != expected.get(key):
            issues.append(f"BASELINE_DRIFT:{key}")
    return issues


__all__ = [
    "ACTIVE_POINTER_AUTHORITY",
    "CANONICAL_GRAPH_WRITE_AUTHORITY",
    "GE_W0_BASELINE_RECEIPT_SCHEMA_VERSION",
    "GE_W0_BASELINE_RECEIPT_RELATIVE_PATH",
    "GE_W0_COMPLETION_MARKER",
    "GE_W0_CONTRACT_RELATIVE_PATH",
    "GE_W0_CONTRACT_SCHEMA_VERSION",
    "GraphEvolutionAuthorityError",
    "build_ge_w0_authority_baseline",
    "load_ge_w0_authority_contract",
    "load_ge_w0_authority_baseline_receipt",
    "validate_ge_w0_authority_baseline",
    "validate_ge_w0_authority_contract",
]
