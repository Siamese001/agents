"""GE-W1 source-backed candidate assertion intake.

GE-W1 records proposals for the later Author Gate.  It deliberately has no
canonical graph writer, no embedding writer, and no activation capability.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.graph_evolution_authority import build_ge_w0_authority_baseline
from apps_rg.runtime.c0.constants import PROOF_ELIGIBLE
from apps_rg.runtime.c0.fact_vector_write_back import (
    ENRICH,
    EXTRACT,
    FUSE,
    REJECT,
    SEMANTIC_CACHE,
    STAGE_FOR_FACT_VECTORS,
    decide_write_back,
)

GE_W1_CONTRACT_RELATIVE_PATH = Path(
    "src/apps_rg/fact_inventory/graph_evolution_candidate_intake_contract.v1.json"
)
GE_W1_CONTRACT_SCHEMA_VERSION = "apps_rg.graph_evolution_candidate_intake_contract.v1"
GE_W1_COMPLETION_MARKER = "GE_W1_CANDIDATE_STAGED"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPERATIONS = frozenset({"CREATE", "UPDATE", "RETIRE"})
_TRANSFORMS = frozenset({EXTRACT, FUSE, ENRICH})


class GraphEvolutionCandidateIntakeError(ValueError):
    """Raised when the frozen GE-W1 intake contract cannot be loaded."""


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _text(value: object) -> str:
    return str(value or "").strip()


def _id_list(value: object) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return sorted({_text(item) for item in value if _text(item)})
    return []


def load_ge_w1_candidate_intake_contract(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    path = (root / GE_W1_CONTRACT_RELATIVE_PATH).resolve()
    try:
        path.relative_to(root)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise GraphEvolutionCandidateIntakeError(f"GE-W1 contract unavailable: {path}") from exc
    if not isinstance(payload, dict):
        raise GraphEvolutionCandidateIntakeError("GE-W1 contract must be a JSON object")
    return payload


def validate_ge_w1_candidate_intake_contract(contract: Mapping[str, Any]) -> list[str]:
    """Return deterministic frozen-contract failures; an empty list is valid."""

    issues: list[str] = []
    if contract.get("schema_version") != GE_W1_CONTRACT_SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if contract.get("contract_id") != "APPS_RG_GRAPH_EVOLUTION_CANDIDATE_INTAKE":
        issues.append("CONTRACT_ID")
    if contract.get("wave") != "GE_W1" or contract.get("status") != "FROZEN":
        issues.append("WAVE_OR_STATUS")
    authority = contract.get("authority_binding")
    if not isinstance(authority, Mapping) or any(
        authority.get(key) is not expected
        for key, expected in (
            ("base_graph_digest_required", True),
            ("candidate_runtime_claim_authority", False),
            ("candidate_may_not_activate_runtime", True),
        )
    ) or authority.get("base_authority_source") != "augmented_skills_graph" or authority.get(
        "canonical_graph_write_authority"
    ) != "UWG_ONLY":
        issues.append("AUTHORITY_BINDING")
    if contract.get("operations") != ["CREATE", "UPDATE", "RETIRE"]:
        issues.append("OPERATIONS")
    if contract.get("grounded_transforms") != [EXTRACT, FUSE, ENRICH]:
        issues.append("GROUNDED_TRANSFORMS")
    requirements = contract.get("source_requirements")
    if not isinstance(requirements, Mapping) or requirements.get("proof_status") != PROOF_ELIGIBLE or any(
        requirements.get(key) is not True
        for key in (
            "source_document_id_required",
            "source_pointer_required",
            "source_excerpt_required",
            "source_file_sha256_required",
            "fuse_requires_two_or_more_source_references",
        )
    ):
        issues.append("SOURCE_REQUIREMENTS")
    record = contract.get("candidate_record")
    if not isinstance(record, Mapping) or record.get("embedding_materialization") != "GE_W5_ONLY" or any(
        forbidden not in (record.get("forbidden_fields") or [])
        for forbidden in ("embedding", "vector", "embedding_id", "activation")
    ):
        issues.append("CANDIDATE_RECORD_BOUNDARY")
    exit_gate = contract.get("ge_w1_exit")
    if not isinstance(exit_gate, Mapping) or exit_gate.get("completion_marker") != GE_W1_COMPLETION_MARKER or any(
        exit_gate.get(key) is not False
        for key in (
            "canonical_graph_mutated",
            "cluster_registry_mutated",
            "cluster_projection_mutated",
            "uwg_called",
            "activation_created",
        )
    ):
        issues.append("GE_W1_EXIT")
    return issues


def _source_issues(proposal: Mapping[str, Any], *, transform: str, operation: str) -> list[str]:
    issues: list[str] = []
    if not _text(proposal.get("assertion_text")):
        issues.append("ASSERTION_TEXT_REQUIRED")
    if not _text(proposal.get("source_document_id")):
        issues.append("SOURCE_DOCUMENT_ID_REQUIRED")
    if not _text(proposal.get("source_span_ref") or proposal.get("source_ref")):
        issues.append("SOURCE_POINTER_REQUIRED")
    if not _text(proposal.get("source_excerpt")):
        issues.append("SOURCE_EXCERPT_REQUIRED")
    if not _SHA256.fullmatch(_text(proposal.get("source_file_sha256"))):
        issues.append("SOURCE_FILE_SHA256_REQUIRED")
    if transform == FUSE and len(_id_list(proposal.get("supporting_source_refs"))) < 2:
        issues.append("FUSE_SOURCE_REFS_REQUIRED")
    if operation in {"UPDATE", "RETIRE"} and not _text(proposal.get("target_fact_id")):
        issues.append("TARGET_FACT_ID_REQUIRED")
    return issues


def _base_graph(baseline: Mapping[str, Any]) -> dict[str, str]:
    graph = baseline["canonical_graph"]
    return {
        "authority_source": str(graph["authority_source"]),
        "path": str(graph["path"]),
        "payload_sha256": str(graph["payload_sha256"]),
        "graph_version": str(graph["graph_version"]),
    }


def intake_graph_evolution_candidate(
    proposal: Mapping[str, Any], *, repo_root: Path | str, existing_assertions: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """Classify and stage one candidate proposal without writing any graph surface.

    Generated/targeting text is returned as a semantic-cache handoff.  Grounded
    proposals are bound to the exact GE-W0 base graph and marked STAGED or HOLD;
    Author Gate and UWG are intentionally future-wave responsibilities.
    """

    contract = load_ge_w1_candidate_intake_contract(repo_root)
    contract_issues = validate_ge_w1_candidate_intake_contract(contract)
    if contract_issues:
        raise GraphEvolutionCandidateIntakeError(
            f"GE-W1 contract invalid: {', '.join(contract_issues)}"
        )
    atom = dict(proposal)
    decision = decide_write_back(atom)
    if decision.route == SEMANTIC_CACHE:
        return {
            "route": "SEMANTIC_CACHE_ONLY",
            "reason": decision.reason,
            "operation": decision.operation,
            "canonical_graph_mutated": False,
            "embedding_materialized": False,
            "activation_created": False,
        }
    if decision.route == REJECT:
        return {
            "route": "REJECTED",
            "reason": decision.reason,
            "operation": decision.operation,
            "issues": ["WRITEBACK_ROUTING_REJECTED"],
            "canonical_graph_mutated": False,
            "embedding_materialized": False,
            "activation_created": False,
        }
    if decision.route != STAGE_FOR_FACT_VECTORS:
        raise GraphEvolutionCandidateIntakeError(f"unexpected write-back route: {decision.route}")

    transform = _text(decision.operation).lower()
    operation = _text(proposal.get("operation") or "CREATE").upper()
    issues = _source_issues(proposal, transform=transform, operation=operation)
    if transform not in _TRANSFORMS:
        issues.append("UNSUPPORTED_TRANSFORM")
    if operation not in _OPERATIONS:
        issues.append("UNSUPPORTED_OPERATION")
    if _text(proposal.get("proof_status")) != PROOF_ELIGIBLE:
        issues.append("PROOF_STATUS_MUST_BE_PROOF_ELIGIBLE")
    if issues:
        return {
            "route": "REJECTED",
            "reason": "GE_W1_SOURCE_OR_OPERATION_INVALID",
            "operation": transform,
            "issues": issues,
            "canonical_graph_mutated": False,
            "embedding_materialized": False,
            "activation_created": False,
        }

    baseline = build_ge_w0_authority_baseline(repo_root)
    assertion_text = _text(proposal["assertion_text"])
    normalized = " ".join(assertion_text.casefold().split())
    duplicates = sorted(
        {
            _text(row.get("fact_id") or row.get("candidate_id"))
            for row in existing_assertions
            if isinstance(row, Mapping)
            and " ".join(_text(row.get("assertion_text")).casefold().split()) == normalized
            and _text(row.get("fact_id") or row.get("candidate_id"))
        }
    )
    conflicts = _id_list(proposal.get("potential_conflict_ids"))
    status = "HOLD" if duplicates or conflicts else "STAGED"
    source = {
        "document_id": _text(proposal["source_document_id"]),
        "span_ref": _text(proposal.get("source_span_ref") or proposal.get("source_ref")),
        "excerpt": _text(proposal["source_excerpt"]),
        "source_type": _text(proposal.get("source_type")),
        "file_sha256": _text(proposal["source_file_sha256"]),
        "supporting_source_refs": _id_list(proposal.get("supporting_source_refs")),
    }
    record: dict[str, Any] = {
        "schema_version": "apps_rg.graph_evolution_candidate_assertion.v1",
        "base_graph": _base_graph(baseline),
        "operation": operation,
        "target_fact_id": _text(proposal.get("target_fact_id")),
        "assertion_text": assertion_text,
        "source": source,
        "transform": transform,
        "proposed_links": {
            "skill_ids": _id_list(proposal.get("proposed_skill_ids")),
            "fact_ids": _id_list(proposal.get("proposed_fact_ids")),
            "node_ids": _id_list(proposal.get("proposed_node_ids")),
            "section_ids": _id_list(proposal.get("proposed_section_ids")),
        },
        "duplicate_ids": duplicates,
        "potential_conflict_ids": conflicts,
        "producer_run_id": _text(proposal.get("producer_run_id")),
        "status": status,
        "next_gate": "AUTHOR_GATE",
    }
    record["candidate_id"] = "ge_candidate:" + _canonical_sha256(record)[:24]
    return {
        "route": "CANDIDATE_STAGED",
        "reason": GE_W1_COMPLETION_MARKER if status == "STAGED" else "GE_W1_CANDIDATE_HELD",
        "candidate": record,
        "canonical_graph_mutated": False,
        "embedding_materialized": False,
        "activation_created": False,
    }


__all__ = [
    "GE_W1_COMPLETION_MARKER",
    "GE_W1_CONTRACT_RELATIVE_PATH",
    "GE_W1_CONTRACT_SCHEMA_VERSION",
    "GraphEvolutionCandidateIntakeError",
    "intake_graph_evolution_candidate",
    "load_ge_w1_candidate_intake_contract",
    "validate_ge_w1_candidate_intake_contract",
]
