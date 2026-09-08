"""GE-W6 QREL change-impact assessment for a candidate cluster projection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.evals.c03_graph_evidence_cluster_qualification import expected_judgment_keys

GE_W6_CONTRACT_RELATIVE_PATH = Path("src/apps_rg/evals/graph_evolution_qrel_change_impact_contract.v1.json")
GE_W6_CONTRACT_SCHEMA_VERSION = "apps_rg.graph_evolution_qrel_change_impact_contract.v1"
GE_W6_COMPLETION_MARKER = "GE_W6_QREL_CHANGE_IMPACT_ASSESSED"
QUERY_MANIFEST_RELATIVE_PATH = Path("src/apps_rg/evals/c03_graph_evidence_cluster_queries.v1.json")
ACTIVE_REGISTRY_RELATIVE_PATH = Path("artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/graph_evidence_cluster_registry.v1.json")


class GraphEvolutionQrelChangeImpactError(ValueError):
    """Raised when the frozen GE-W6 impact contract cannot be loaded."""


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphEvolutionQrelChangeImpactError(f"GE-W6 JSON unavailable: {path}") from exc
    if not isinstance(payload, dict):
        raise GraphEvolutionQrelChangeImpactError("GE-W6 JSON must be an object")
    return payload


def load_ge_w6_qrel_change_impact_contract(repo_root: Path | str) -> dict[str, Any]:
    return _read_json(Path(repo_root).resolve() / GE_W6_CONTRACT_RELATIVE_PATH)


def validate_ge_w6_qrel_change_impact_contract(contract: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if contract.get("schema_version") != GE_W6_CONTRACT_SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if contract.get("contract_id") != "APPS_RG_GRAPH_EVOLUTION_QREL_CHANGE_IMPACT":
        issues.append("CONTRACT_ID")
    if contract.get("wave") != "GE_W6" or contract.get("status") != "FROZEN":
        issues.append("WAVE_OR_STATUS")
    input_contract = contract.get("input")
    if not isinstance(input_contract, Mapping) or input_contract.get("required_candidate_projection_state") != "PROJECTION_BUILT" or any(input_contract.get(key) is not True for key in ("source_bound_query_manifest_required", "full_finite_candidate_universe_required", "candidate_registry_projection_digest_binding_required")):
        issues.append("INPUT")
    human = contract.get("human_review")
    if not isinstance(human, Mapping) or human.get("relevance_grades") != [0, 1, 2, 3] or any(human.get(key) is not True for key in ("two_distinct_human_reviewers_required", "adjudication_required", "synthetic_or_model_labels_forbidden", "metrics_before_frozen_human_qrels_forbidden")):
        issues.append("HUMAN_REVIEW")
    exit_gate = contract.get("ge_w6_exit")
    if not isinstance(exit_gate, Mapping) or exit_gate.get("completion_marker") != GE_W6_COMPLETION_MARKER or exit_gate.get("candidate_state") != "QREL_CHANGE_IMPACT_ASSESSED" or exit_gate.get("next_gate") != "BLINDED_QREL_REVIEW_AND_COMPARISON" or any(exit_gate.get(key) is not False for key in ("qrel_grades_created", "retrieval_metrics_computed", "active_runtime_pointer_changed", "activation_created")):
        issues.append("GE_W6_EXIT")
    return issues


def assess_candidate_qrel_change_impact(candidate_registry: Mapping[str, Any], candidate_projection: Mapping[str, Any], *, repo_root: Path | str, active_registry_path: Path | str | None = None) -> dict[str, Any]:
    """Compute label obligations, never relevance labels or retrieval metrics."""
    contract = load_ge_w6_qrel_change_impact_contract(repo_root)
    problems = validate_ge_w6_qrel_change_impact_contract(contract)
    if problems:
        raise GraphEvolutionQrelChangeImpactError(f"GE-W6 contract invalid: {', '.join(problems)}")
    root = Path(repo_root).resolve()
    if candidate_projection.get("status") != "GENERATED_NOT_QUALIFIED" or candidate_projection.get("registry_sha256") != candidate_registry.get("registry_sha256"):
        return {"route": "BLOCKED", "reason": "GE_W6_CANDIDATE_PROJECTION_BINDING"}
    candidate_clusters = {str(row.get("cluster_id")) for row in candidate_registry.get("clusters") or [] if isinstance(row, Mapping)}
    vectors = {str(row.get("cluster_id")) for row in candidate_projection.get("vectors") or [] if isinstance(row, Mapping)}
    if not candidate_clusters or candidate_clusters != vectors:
        return {"route": "BLOCKED", "reason": "GE_W6_CLUSTER_VECTOR_PARITY"}
    active = _read_json(Path(active_registry_path or (root / ACTIVE_REGISTRY_RELATIVE_PATH)))
    active_clusters = {str(row.get("cluster_id")) for row in active.get("clusters") or [] if isinstance(row, Mapping)}
    query_manifest = _read_json(root / QUERY_MANIFEST_RELATIVE_PATH)
    active_keys = expected_judgment_keys(query_manifest, active)
    candidate_keys = expected_judgment_keys(query_manifest, candidate_registry)
    added_clusters = sorted(candidate_clusters - active_clusters)
    removed_clusters = sorted(active_clusters - candidate_clusters)
    changed_keys = sorted(candidate_keys - active_keys)
    receipt: dict[str, Any] = {
        "schema_version": "apps_rg.graph_evolution_qrel_change_impact_receipt.v1",
        "completion_marker": GE_W6_COMPLETION_MARKER,
        "status": "BLOCKED_QREL_AUTHORITY",
        "candidate_state": "QREL_CHANGE_IMPACT_ASSESSED",
        "candidate_registry_sha256": candidate_registry["registry_sha256"],
        "candidate_projection_sha256": candidate_projection["projection_sha256"],
        "query_manifest_sha256": query_manifest.get("query_manifest_sha256"),
        "active_cluster_count": len(active_clusters),
        "candidate_cluster_count": len(candidate_clusters),
        "added_cluster_ids": added_clusters,
        "removed_cluster_ids": removed_clusters,
        "active_full_judgment_count": len(active_keys),
        "candidate_full_judgment_count": len(candidate_keys),
        "changed_judgment_count": len(changed_keys),
        "changed_judgment_keys": ["|".join(key) for key in changed_keys],
        "required_human_review": {
            "primary_reviewer_count": 2,
            "required_primary_judgment_count": 2 * len(candidate_keys),
            "adjudication_required": True,
            "required_adjudication_count": len(candidate_keys),
            "relevance_grades": [0, 1, 2, 3],
            "full_candidate_universe_required": True,
            "required_final_judgment_count": len(candidate_keys),
        },
        "qrel_grades_created": False,
        "retrieval_metrics_computed": False,
        "synthetic_labels_created": False,
        "active_runtime_pointer_changed": False,
        "activation_created": False,
        "next_gate": "BLINDED_QREL_REVIEW_AND_COMPARISON",
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return {"route": "BLOCKED_QREL_AUTHORITY", "reason": GE_W6_COMPLETION_MARKER, "receipt": receipt}


__all__ = ["GE_W6_COMPLETION_MARKER", "GE_W6_CONTRACT_RELATIVE_PATH", "GE_W6_CONTRACT_SCHEMA_VERSION", "GraphEvolutionQrelChangeImpactError", "assess_candidate_qrel_change_impact", "load_ge_w6_qrel_change_impact_contract", "validate_ge_w6_qrel_change_impact_contract"]
