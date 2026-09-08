"""GE-W2 human Author Gate for staged graph-evolution candidates.

This module validates and compiles decisions supplied by people.  It never
manufactures a human judgment and it has no canonical graph or vector writer.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.graph_evolution_authority import build_ge_w0_authority_baseline

GE_W2_CONTRACT_RELATIVE_PATH = Path(
    "src/apps_rg/fact_inventory/graph_evolution_author_gate_contract.v1.json"
)
GE_W2_CONTRACT_SCHEMA_VERSION = "apps_rg.graph_evolution_author_gate_contract.v1"
GE_W2_COMPLETION_MARKER = "GE_W2_AUTHOR_GATE_DECIDED"
_REVIEW_ROLES = ("EVIDENCE_REVIEWER", "GRAPH_STEWARD")
_DECISIONS = frozenset({"APPROVE", "HOLD", "REJECT"})
_APPROVAL_CHECKS = (
    "source_fidelity",
    "assertion_atomicity",
    "graph_linkage_fit",
    "claim_policy_fit",
)


class GraphEvolutionAuthorGateError(ValueError):
    """Raised when the GE-W2 frozen contract cannot be loaded."""


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
        raise GraphEvolutionAuthorGateError(f"GE-W2 contract unavailable: {path}") from exc
    if not isinstance(payload, dict):
        raise GraphEvolutionAuthorGateError("GE-W2 contract must be a JSON object")
    return payload


def load_ge_w2_author_gate_contract(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    path = (root / GE_W2_CONTRACT_RELATIVE_PATH).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise GraphEvolutionAuthorGateError("GE-W2 contract path escapes repository root") from exc
    return _read_json(path)


def validate_ge_w2_author_gate_contract(contract: Mapping[str, Any]) -> list[str]:
    """Return deterministic contract errors; an empty list is valid."""

    issues: list[str] = []
    if contract.get("schema_version") != GE_W2_CONTRACT_SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if contract.get("contract_id") != "APPS_RG_GRAPH_EVOLUTION_AUTHOR_GATE":
        issues.append("CONTRACT_ID")
    if contract.get("wave") != "GE_W2" or contract.get("status") != "FROZEN":
        issues.append("WAVE_OR_STATUS")
    input_contract = contract.get("input")
    if not isinstance(input_contract, Mapping) or input_contract.get(
        "candidate_schema_version"
    ) != "apps_rg.graph_evolution_candidate_assertion.v1" or input_contract.get(
        "accepted_candidate_statuses"
    ) != ["STAGED", "HOLD"] or input_contract.get("current_base_graph_digest_required") is not True:
        issues.append("INPUT")
    review = contract.get("human_review")
    if not isinstance(review, Mapping) or review.get("identity_prefix") != "human-reviewer://" or review.get(
        "required_roles"
    ) != list(_REVIEW_ROLES) or review.get("review_decisions") != ["APPROVE", "HOLD", "REJECT"] or review.get(
        "approval_checks"
    ) != list(_APPROVAL_CHECKS) or any(
        review.get(key) is not True
        for key in ("distinct_reviewer_identities_required", "candidate_digest_binding_required")
    ):
        issues.append("HUMAN_REVIEW")
    adjudication = contract.get("adjudication")
    if not isinstance(adjudication, Mapping) or adjudication.get("resolutions") != [
        "APPROVE",
        "HOLD",
        "REJECT",
    ] or any(
        adjudication.get(key) is not True
        for key in (
            "required_for_candidate_hold_or_reviewer_disagreement",
            "adjudicator_must_be_distinct_from_reviewers",
            "candidate_digest_binding_required",
        )
    ):
        issues.append("ADJUDICATION")
    exit_gate = contract.get("ge_w2_exit")
    if not isinstance(exit_gate, Mapping) or exit_gate.get("completion_marker") != GE_W2_COMPLETION_MARKER or exit_gate.get(
        "next_gate_after_approval"
    ) != "UWG_COMMIT" or any(
        exit_gate.get(key) is not False
        for key in (
            "canonical_graph_mutated",
            "cluster_registry_mutated",
            "cluster_projection_mutated",
            "uwg_called",
            "embedding_materialized",
            "activation_created",
        )
    ):
        issues.append("GE_W2_EXIT")
    return issues


def candidate_digest(candidate: Mapping[str, Any]) -> str:
    """Canonical, immutable binding value for a GE-W1 candidate record."""

    return _canonical_sha256(dict(candidate))


def _candidate_issues(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if candidate.get("schema_version") != "apps_rg.graph_evolution_candidate_assertion.v1":
        issues.append("CANDIDATE_SCHEMA_VERSION")
    if not _text(candidate.get("candidate_id")):
        issues.append("CANDIDATE_ID")
    if candidate.get("status") not in {"STAGED", "HOLD"}:
        issues.append("CANDIDATE_STATUS")
    base = candidate.get("base_graph")
    current = baseline["canonical_graph"]
    if not isinstance(base, Mapping) or any(
        _text(base.get(key)) != _text(current.get(key))
        for key in ("authority_source", "payload_sha256", "graph_version")
    ):
        issues.append("BASE_GRAPH_DRIFT")
    return issues


def _review_issues(
    review: Mapping[str, Any], *, candidate: Mapping[str, Any], expected_role: str, digest: str
) -> list[str]:
    issues: list[str] = []
    if review.get("schema_version") != "apps_rg.graph_evolution_author_review.v1":
        issues.append(f"{expected_role}:SCHEMA_VERSION")
    if _text(review.get("candidate_id")) != _text(candidate.get("candidate_id")):
        issues.append(f"{expected_role}:CANDIDATE_ID")
    if _text(review.get("candidate_sha256")) != digest:
        issues.append(f"{expected_role}:CANDIDATE_DIGEST")
    if _text(review.get("reviewer_ref")).startswith("human-reviewer://") is False:
        issues.append(f"{expected_role}:REVIEWER_IDENTITY")
    if _text(review.get("role")) != expected_role:
        issues.append(f"{expected_role}:ROLE")
    decision = _text(review.get("decision")).upper()
    if decision not in _DECISIONS:
        issues.append(f"{expected_role}:DECISION")
    if not _text(review.get("rationale")):
        issues.append(f"{expected_role}:RATIONALE")
    checks = review.get("checks")
    if decision == "APPROVE" and (
        not isinstance(checks, Mapping) or any(checks.get(check) is not True for check in _APPROVAL_CHECKS)
    ):
        issues.append(f"{expected_role}:APPROVAL_CHECKS")
    return issues


def _adjudication_issues(
    adjudication: Mapping[str, Any], *, candidate: Mapping[str, Any], digest: str, reviewer_refs: set[str]
) -> list[str]:
    issues: list[str] = []
    if adjudication.get("schema_version") != "apps_rg.graph_evolution_author_adjudication.v1":
        issues.append("ADJUDICATION:SCHEMA_VERSION")
    if _text(adjudication.get("candidate_id")) != _text(candidate.get("candidate_id")):
        issues.append("ADJUDICATION:CANDIDATE_ID")
    if _text(adjudication.get("candidate_sha256")) != digest:
        issues.append("ADJUDICATION:CANDIDATE_DIGEST")
    adjudicator_ref = _text(adjudication.get("adjudicator_ref"))
    if not adjudicator_ref.startswith("human-reviewer://") or adjudicator_ref in reviewer_refs:
        issues.append("ADJUDICATION:IDENTITY")
    if _text(adjudication.get("resolution")).upper() not in _DECISIONS:
        issues.append("ADJUDICATION:RESOLUTION")
    if not _text(adjudication.get("rationale")):
        issues.append("ADJUDICATION:RATIONALE")
    return issues


def author_gate_decision(
    candidate: Mapping[str, Any],
    reviews: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path | str,
    adjudication: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile supplied human reviews into a GE-W2 decision without any write.

    Review records are only validated here; callers must obtain them from people.
    A graph-digest drift, incomplete review, or invalid attestation blocks the
    candidate rather than treating it as approval.
    """

    contract = load_ge_w2_author_gate_contract(repo_root)
    contract_issues = validate_ge_w2_author_gate_contract(contract)
    if contract_issues:
        raise GraphEvolutionAuthorGateError(f"GE-W2 contract invalid: {', '.join(contract_issues)}")
    baseline = build_ge_w0_authority_baseline(repo_root)
    issues = _candidate_issues(candidate, baseline)
    digest = candidate_digest(candidate)
    by_role = {
        _text(review.get("role")): review
        for review in reviews
        if isinstance(review, Mapping) and _text(review.get("role")) in _REVIEW_ROLES
    }
    if len(reviews) != len(_REVIEW_ROLES) or set(by_role) != set(_REVIEW_ROLES):
        issues.append("REVIEW_COVERAGE")
    for role in _REVIEW_ROLES:
        review = by_role.get(role)
        if review is None:
            continue
        issues.extend(_review_issues(review, candidate=candidate, expected_role=role, digest=digest))
    reviewer_refs = {_text(review.get("reviewer_ref")) for review in by_role.values()}
    if len(reviewer_refs) != len(_REVIEW_ROLES):
        issues.append("REVIEWER_IDENTITIES_NOT_DISTINCT")
    if issues:
        return {
            "route": "BLOCKED",
            "reason": "GE_W2_REVIEW_INPUTS_INVALID",
            "issues": sorted(set(issues)),
            "canonical_graph_mutated": False,
            "embedding_materialized": False,
            "activation_created": False,
        }

    decisions = {_text(by_role[role]["decision"]).upper() for role in _REVIEW_ROLES}
    needs_adjudication = candidate.get("status") == "HOLD" or len(decisions) > 1
    if needs_adjudication and adjudication is None:
        return {
            "route": "HOLD",
            "reason": "GE_W2_ADJUDICATION_REQUIRED",
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": digest,
            "canonical_graph_mutated": False,
            "embedding_materialized": False,
            "activation_created": False,
        }
    if adjudication is not None:
        adjudication_errors = _adjudication_issues(
            adjudication, candidate=candidate, digest=digest, reviewer_refs=reviewer_refs
        )
        if adjudication_errors:
            return {
                "route": "BLOCKED",
                "reason": "GE_W2_ADJUDICATION_INVALID",
                "issues": adjudication_errors,
                "canonical_graph_mutated": False,
                "embedding_materialized": False,
                "activation_created": False,
            }
        outcome = _text(adjudication["resolution"]).upper()
    else:
        outcome = next(iter(decisions))
    status = {"APPROVE": "AUTHOR_APPROVED", "HOLD": "HOLD", "REJECT": "REJECTED"}[outcome]
    receipt: dict[str, Any] = {
        "schema_version": "apps_rg.graph_evolution_author_gate_decision.v1",
        "completion_marker": GE_W2_COMPLETION_MARKER,
        "candidate_id": candidate["candidate_id"],
        "candidate_sha256": digest,
        "base_graph": dict(candidate["base_graph"]),
        "reviewer_refs": sorted(reviewer_refs),
        "review_decisions": {role: _text(by_role[role]["decision"]).upper() for role in _REVIEW_ROLES},
        "adjudication_ref": _text(adjudication.get("adjudicator_ref")) if adjudication else None,
        "status": status,
        "next_gate": "UWG_COMMIT" if status == "AUTHOR_APPROVED" else None,
        "canonical_graph_mutated": False,
        "cluster_registry_mutated": False,
        "cluster_projection_mutated": False,
        "uwg_called": False,
        "embedding_materialized": False,
        "activation_created": False,
    }
    receipt["decision_sha256"] = _canonical_sha256(receipt)
    return {"route": status, "reason": GE_W2_COMPLETION_MARKER, "decision": receipt}


__all__ = [
    "GE_W2_COMPLETION_MARKER",
    "GE_W2_CONTRACT_RELATIVE_PATH",
    "GE_W2_CONTRACT_SCHEMA_VERSION",
    "GraphEvolutionAuthorGateError",
    "author_gate_decision",
    "candidate_digest",
    "load_ge_w2_author_gate_contract",
    "validate_ge_w2_author_gate_contract",
]
