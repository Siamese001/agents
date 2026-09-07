"""GE-W3 UWG admission for immutable candidate graph-version artifacts.

The active augmented-skills graph is never overwritten here.  GE-W3 submits an
approved graph delta to UWG and, only after admission, writes a separate
candidate-version artifact for GE-W4 validation.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.runtime.core_io import write_gateway as _wg

from apps_rg.fact_inventory.graph_evolution_author_gate import (
    GE_W2_COMPLETION_MARKER,
    candidate_digest,
)
from apps_rg.fact_inventory.graph_evolution_authority import build_ge_w0_authority_baseline

GE_W3_CONTRACT_RELATIVE_PATH = Path(
    "src/apps_rg/fact_inventory/graph_evolution_uwg_commit_contract.v1.json"
)
GE_W3_CONTRACT_SCHEMA_VERSION = "apps_rg.graph_evolution_uwg_commit_contract.v1"
GE_W3_COMPLETION_MARKER = "GE_W3_UWG_COMMITTED_CANDIDATE"
GE_W3_TARGET_SURFACE = "l4.apps_rg.augmented_skills_graph_candidate_versions"
_BASE_GRAPH_RELATIVE_PATH = Path("src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json")


class GraphEvolutionUwgCommitError(ValueError):
    """Raised when the frozen GE-W3 contract cannot be loaded."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _text(value: object) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphEvolutionUwgCommitError(f"GE-W3 contract unavailable: {path}") from exc
    if not isinstance(payload, dict):
        raise GraphEvolutionUwgCommitError("GE-W3 contract must be a JSON object")
    return payload


def load_ge_w3_uwg_commit_contract(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    path = (root / GE_W3_CONTRACT_RELATIVE_PATH).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise GraphEvolutionUwgCommitError("GE-W3 contract path escapes repository root") from exc
    return _read_json(path)


def validate_ge_w3_uwg_commit_contract(contract: Mapping[str, Any]) -> list[str]:
    """Return deterministic GE-W3 contract failures; an empty list is valid."""

    issues: list[str] = []
    if contract.get("schema_version") != GE_W3_CONTRACT_SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if contract.get("contract_id") != "APPS_RG_GRAPH_EVOLUTION_UWG_COMMIT":
        issues.append("CONTRACT_ID")
    if contract.get("wave") != "GE_W3" or contract.get("status") != "FROZEN":
        issues.append("WAVE_OR_STATUS")
    input_contract = contract.get("input")
    if not isinstance(input_contract, Mapping) or input_contract.get(
        "required_author_gate_status"
    ) != "AUTHOR_APPROVED" or input_contract.get("required_author_gate_next_gate") != "UWG_COMMIT" or any(
        input_contract.get(key) is not True
        for key in (
            "current_base_graph_digest_required",
            "candidate_and_author_gate_digest_binding_required",
            "l5_certification_ref_required",
        )
    ):
        issues.append("INPUT")
    authority = contract.get("write_authority")
    if not isinstance(authority, Mapping) or authority.get("authority") != "UWG_ONLY" or authority.get(
        "target_surface"
    ) != GE_W3_TARGET_SURFACE or authority.get("operation_type") != "version_insert" or authority.get(
        "base_graph_file_overwrite_forbidden"
    ) is not True:
        issues.append("WRITE_AUTHORITY")
    version = contract.get("candidate_version")
    if not isinstance(version, Mapping) or version.get("projection_state") != "NOT_BUILT" or version.get(
        "retrieval_qualification_state"
    ) != "NOT_RUN" or any(
        version.get(key) is not expected
        for key, expected in (
            ("immutable_after_admission", True),
            ("must_bind_parent_graph_digest", True),
            ("must_include_assertion_node_and_proposed_links", True),
            ("active_runtime_pointer_changed", False),
        )
    ):
        issues.append("CANDIDATE_VERSION")
    exit_gate = contract.get("ge_w3_exit")
    if not isinstance(exit_gate, Mapping) or exit_gate.get("completion_marker") != GE_W3_COMPLETION_MARKER or exit_gate.get(
        "next_gate"
    ) != "GRAPH_VALIDATION" or any(
        exit_gate.get(key) is not False
        for key in (
            "canonical_base_graph_mutated",
            "active_runtime_pointer_changed",
            "cluster_registry_mutated",
            "cluster_projection_mutated",
            "embedding_materialized",
            "qrel_evaluation_run",
            "activation_created",
        )
    ):
        issues.append("GE_W3_EXIT")
    return issues


def _decision_sha256_is_valid(decision: Mapping[str, Any]) -> bool:
    unsigned = dict(decision)
    recorded = _text(unsigned.pop("decision_sha256", ""))
    return bool(recorded) and recorded == _canonical_sha256(unsigned)


def _approval_issues(
    candidate: Mapping[str, Any], decision: Mapping[str, Any], baseline: Mapping[str, Any]
) -> list[str]:
    issues: list[str] = []
    digest = candidate_digest(candidate)
    if decision.get("schema_version") != "apps_rg.graph_evolution_author_gate_decision.v1":
        issues.append("AUTHOR_GATE_SCHEMA")
    if decision.get("completion_marker") != "GE_W2_AUTHOR_GATE_DECIDED":
        issues.append("AUTHOR_GATE_MARKER")
    if decision.get("status") != "AUTHOR_APPROVED" or decision.get("next_gate") != "UWG_COMMIT":
        issues.append("AUTHOR_GATE_NOT_APPROVED")
    if _text(decision.get("candidate_id")) != _text(candidate.get("candidate_id")):
        issues.append("AUTHOR_GATE_CANDIDATE_ID")
    if _text(decision.get("candidate_sha256")) != digest:
        issues.append("AUTHOR_GATE_CANDIDATE_DIGEST")
    if not _decision_sha256_is_valid(decision):
        issues.append("AUTHOR_GATE_RECEIPT_DIGEST")
    base = candidate.get("base_graph")
    current = baseline["canonical_graph"]
    if not isinstance(base, Mapping) or any(
        _text(base.get(key)) != _text(current.get(key))
        for key in ("authority_source", "payload_sha256", "graph_version")
    ):
        issues.append("BASE_GRAPH_DRIFT")
    if decision.get("base_graph") != candidate.get("base_graph"):
        issues.append("AUTHOR_GATE_BASE_GRAPH_BINDING")
    return issues


def _assertion_node(candidate: Mapping[str, Any]) -> dict[str, Any]:
    digest = candidate_digest(candidate)
    source = candidate["source"]
    return {
        "node_id": f"ge_assertion_{digest[:24]}",
        "node_type": "atomic_proof_fact",
        "label": _text(candidate["assertion_text"]),
        "description": _text(candidate["assertion_text"]),
        "source_refs": [
            "source:"
            f"{_text(source.get('document_id'))}#{_text(source.get('span_ref'))}"
            f"@sha256:{_text(source.get('file_sha256'))}"
        ],
        "candidate_id": _text(candidate["candidate_id"]),
        "proposed_only": True,
    }


def _proposed_edges(candidate: Mapping[str, Any], *, known_node_ids: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    assertion = _assertion_node(candidate)
    skill_ids = list((candidate.get("proposed_links") or {}).get("skill_ids") or [])
    unknown = sorted({_text(skill_id) for skill_id in skill_ids if _text(skill_id) not in known_node_ids})
    if unknown:
        return [], unknown
    edges: list[dict[str, Any]] = []
    for skill_id in sorted({_text(skill_id) for skill_id in skill_ids if _text(skill_id)}):
        edge_material = f"{candidate_digest(candidate)}|{skill_id}|{assertion['node_id']}"
        edges.append(
            {
                "edge_id": "ge_edge_" + hashlib.sha256(edge_material.encode("utf-8")).hexdigest()[:24],
                "edge_type": "skill_supported_by_fact",
                "source_node_id": skill_id,
                "target_node_id": assertion["node_id"],
                "candidate_id": _text(candidate["candidate_id"]),
                "proposed_only": True,
            }
        )
    return edges, []


def build_candidate_graph_version(
    candidate: Mapping[str, Any], decision: Mapping[str, Any], *, repo_root: Path | str
) -> dict[str, Any]:
    """Build a deterministic, non-active candidate graph version in memory."""

    baseline = build_ge_w0_authority_baseline(repo_root)
    issues = _approval_issues(candidate, decision, baseline)
    if issues:
        raise GraphEvolutionUwgCommitError(f"GE-W3 approval invalid: {', '.join(sorted(set(issues)))}")
    graph_path = Path(repo_root).resolve() / baseline["canonical_graph"]["path"]
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    known_node_ids = {
        _text(node.get("node_id")) for node in graph.get("graph_nodes") or [] if isinstance(node, Mapping)
    }
    edges, unknown_skills = _proposed_edges(candidate, known_node_ids=known_node_ids)
    if unknown_skills:
        raise GraphEvolutionUwgCommitError(
            f"GE-W3 proposed graph links reference unknown skills: {', '.join(unknown_skills)}"
        )
    assertion = _assertion_node(candidate)
    version: dict[str, Any] = {
        "schema_version": "apps_rg.graph_evolution_candidate_graph_version.v1",
        "version_id": f"ge_graph_version:{candidate_digest(candidate)[:24]}",
        "status": "UWG_COMMITTED_CANDIDATE",
        "parent_graph": dict(candidate["base_graph"]),
        "author_gate": {
            "decision_sha256": _text(decision["decision_sha256"]),
            "reviewer_refs": list(decision.get("reviewer_refs") or []),
            "adjudication_ref": decision.get("adjudication_ref"),
        },
        "candidate": dict(candidate),
        "proposed_graph_delta": {"assertion_nodes": [assertion], "assertion_edges": edges},
        "projection_state": "NOT_BUILT",
        "retrieval_qualification_state": "NOT_RUN",
        "active_runtime_pointer_changed": False,
        "activation_created": False,
    }
    version["version_sha256"] = _canonical_sha256(version)
    return version


def build_ge_w3_commit_bundle(
    candidate_version: Mapping[str, Any], *, decision: Mapping[str, Any], l5_certification_ref: str
) -> tuple[Any, list[Any], Any, Any]:
    """Build the canonical UWG request and one graph-candidate StateDiff."""

    from apps_rg.runtime.local_state import (
        CommitRequest,
        ReadSurfaceRefreshPlan,
        RollbackPlan,
        StateDiff,
        stamp_digest,
    )
    from apps_rg.runtime.local_state import compute_state_diffs_digest

    version_id = _text(candidate_version["version_id"])
    parent_digest = _text((candidate_version.get("parent_graph") or {}).get("payload_sha256"))
    rollback = stamp_digest(
        RollbackPlan(
            rollback_plan_id=f"ge_w3_rp:{version_id}",
            blast_radius="single_surface",
            target_surfaces=(GE_W3_TARGET_SURFACE,),
            before_snapshot_refs=(f"graph:{parent_digest}",),
            rollback_operation_types=("tombstone_candidate_version",),
        )
    )
    state_diff = stamp_digest(
        StateDiff(
            state_diff_id=f"ge_w3_sd:{version_id}",
            target_surface=GE_W3_TARGET_SURFACE,
            operation_type="version_insert",
            after_candidate=f"candidate_graph_version:{candidate_version['version_sha256']}",
            schema_ref="schema:apps_rg.graph_evolution.candidate_version@1",
            blast_radius="single_surface",
            rollback_plan_ref=rollback.rollback_plan_id,
            proposed_by_surface="UWG",
            created_at=_utc_now(),
            replay_refs=(f"candidate:{candidate_version['candidate']['candidate_id']}",),
            audit_refs=(f"author_gate:{decision['decision_sha256']}",),
        )
    )
    state_diffs = [state_diff]
    state_diff_hash = compute_state_diffs_digest(state_diffs)
    commit_request_id = f"ge_w3_cr:{version_id}"
    commit_request = stamp_digest(
        CommitRequest(
            commit_request_id=commit_request_id,
            cleared_exit_review_packet_ref=f"author_gate:{decision['decision_sha256']}",
            request_id=_text(candidate_version["candidate"]["candidate_id"]),
            run_id=version_id,
            trace_root=f"ge_w3:{version_id}",
            tenant_id="apps_rg",
            policy_hash="apps_rg.graph_evolution_authority_contract.v1",
            blueprint_hash="apps_rg.graph_evolution_uwg_commit_contract.v1",
            route_contract_ref="route:apps_rg:graph_evolution:GE_W3",
            replay_key=f"graph_candidate:{candidate_version['version_sha256']}",
            rollback_plan_ref=rollback.rollback_plan_id,
            blast_radius="single_surface",
            source_surface="Exit",
            state_diff_refs=(state_diff.state_diff_id,),
            gate_verdict_refs=("gv:apps_rg:GE_W2:AUTHOR_APPROVED",),
            l5_certification_ref=l5_certification_ref,
            l5_certification_refs=(l5_certification_ref,),
            hitl_reclearance_refs=tuple(decision.get("reviewer_refs") or ()),
            affected_state_surfaces=(GE_W3_TARGET_SURFACE,),
            expected_read_surface_refreshes=("graph_candidate_validation_only",),
            audit_refs=(f"author_gate:{decision['decision_sha256']}",),
            registry_digest_set=(f"graph:{parent_digest}",),
            capability_token_ref=f"capability:apps_rg:GE_W3:{version_id}",
            clearance_proof_id=f"author_gate:{decision['decision_sha256']}",
            validator_receipt_id=GE_W2_COMPLETION_MARKER,
            staged_diff_hash=state_diff_hash,
            commit_request_signature=_canonical_sha256(
                {
                    "commit_request_id": commit_request_id,
                    "staged_diff_hash": state_diff_hash,
                    "author_gate_decision_sha256": decision["decision_sha256"],
                }
            ),
        )
    )
    refresh = stamp_digest(
        ReadSurfaceRefreshPlan(
            refresh_plan_id=f"ge_w3_rfp:{version_id}",
            source_commit_receipt_ref="<pending>",
            before_snapshot=f"graph:{parent_digest}",
            expected_after_snapshot=f"candidate_graph_version:{candidate_version['version_sha256']}",
            stale_projection_policy="fail_closed",
            retry_policy="none",
            policy_hash="apps_rg.graph_evolution_authority_contract.v1",
            blueprint_hash="apps_rg.graph_evolution_uwg_commit_contract.v1",
            affected_surfaces=(GE_W3_TARGET_SURFACE,),
            required_refreshes=("graph_candidate_validation_only",),
            refresh_order=("graph_candidate_validation_only",),
        )
    )
    return commit_request, state_diffs, rollback, refresh


def _durable_write_gateway_base() -> type:
    from apps_rg.runtime.local_state import DurableWriteGateway

    return DurableWriteGateway


class GraphEvolutionUwgGateway(_durable_write_gateway_base()):  # type: ignore[misc,valid-type]
    """Stable Apps RG surface for the canonical DurableWriteGateway."""


def commit_author_approved_candidate(
    candidate: Mapping[str, Any],
    decision: Mapping[str, Any],
    *,
    repo_root: Path | str,
    candidate_version_path: Path | str,
    l5_certification_ref: str = "",
    gateway: Any | None = None,
) -> dict[str, Any]:
    """Admit and persist one candidate version; the base graph remains untouched."""

    contract = load_ge_w3_uwg_commit_contract(repo_root)
    contract_issues = validate_ge_w3_uwg_commit_contract(contract)
    if contract_issues:
        raise GraphEvolutionUwgCommitError(f"GE-W3 contract invalid: {', '.join(contract_issues)}")
    root = Path(repo_root).resolve()
    target = Path(candidate_version_path).resolve()
    base_graph_path = (root / _BASE_GRAPH_RELATIVE_PATH).resolve()
    if target == base_graph_path:
        return {
            "route": "BLOCKED",
            "reason": "GE_W3_BASE_GRAPH_OVERWRITE_FORBIDDEN",
            "canonical_base_graph_mutated": False,
        }
    if target.exists():
        return {
            "route": "BLOCKED",
            "reason": "GE_W3_CANDIDATE_VERSION_IMMUTABLE",
            "canonical_base_graph_mutated": False,
        }
    if not _text(l5_certification_ref):
        return {
            "route": "BLOCKED",
            "reason": "GE_W3_L5_CERTIFICATION_REQUIRED",
            "canonical_base_graph_mutated": False,
        }
    try:
        version = build_candidate_graph_version(candidate, decision, repo_root=root)
    except GraphEvolutionUwgCommitError as exc:
        return {
            "route": "BLOCKED",
            "reason": "GE_W3_PRECONDITION_FAILED",
            "issues": str(exc).removeprefix("GE-W3 approval invalid: ").split(", "),
            "canonical_base_graph_mutated": False,
        }
    commit_request, state_diffs, rollback, refresh = build_ge_w3_commit_bundle(
        version, decision=decision, l5_certification_ref=_text(l5_certification_ref)
    )
    gateway_instance = gateway or GraphEvolutionUwgGateway()
    try:
        commit_receipt, blocked_receipt, _refresh = gateway_instance.commit(
            commit_request=commit_request,
            state_diffs=state_diffs,
            rollback_plan=rollback,
            refresh_plan=refresh,
        )
    except ValueError as exc:
        return {
            "route": "BLOCKED",
            "reason": "GE_W3_UWG_ERROR",
            "issues": [str(exc)],
            "canonical_base_graph_mutated": False,
        }
    if commit_receipt is None:
        return {
            "route": "BLOCKED",
            "reason": "GE_W3_UWG_BLOCKED",
            "blocked_reason_codes": list(getattr(blocked_receipt, "blocked_reason_codes", ()) or ()),
            "blocked_commit_receipt_id": _text(
                getattr(blocked_receipt, "blocked_commit_receipt_id", "")
            ),
            "canonical_base_graph_mutated": False,
        }
    version = dict(version)
    version["uwg_commit_receipt_id"] = commit_receipt.commit_receipt_id
    version["uwg_commit_receipt"] = asdict(commit_receipt)
    version["committed_at_utc"] = _utc_now()
    version["completion_marker"] = GE_W3_COMPLETION_MARKER
    _wg.ensure_dir(target.parent)
    _wg.write_text(target, json.dumps(version, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "route": "UWG_COMMITTED_CANDIDATE",
        "reason": GE_W3_COMPLETION_MARKER,
        "candidate_version_path": str(target),
        "candidate_version": version,
        "uwg_commit_receipt_id": commit_receipt.commit_receipt_id,
        "canonical_base_graph_mutated": False,
        "active_runtime_pointer_changed": False,
        "embedding_materialized": False,
        "activation_created": False,
    }


__all__ = [
    "GE_W3_COMPLETION_MARKER",
    "GE_W3_CONTRACT_RELATIVE_PATH",
    "GE_W3_CONTRACT_SCHEMA_VERSION",
    "GE_W3_TARGET_SURFACE",
    "GraphEvolutionUwgCommitError",
    "GraphEvolutionUwgGateway",
    "build_candidate_graph_version",
    "build_ge_w3_commit_bundle",
    "commit_author_approved_candidate",
    "load_ge_w3_uwg_commit_contract",
    "validate_ge_w3_uwg_commit_contract",
]
