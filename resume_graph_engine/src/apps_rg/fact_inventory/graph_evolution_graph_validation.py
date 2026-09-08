"""GE-W4 validation for a UWG-admitted candidate graph-version overlay.

GE-W4 is deliberately read-only.  It validates a candidate version against the
current base graph and returns a receipt for GE-W5; it does not materialize an
active graph, projection, vector, or runtime-pointer change.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.graph_evolution_author_gate import candidate_digest
from apps_rg.fact_inventory.graph_evolution_authority import build_ge_w0_authority_baseline

GE_W4_CONTRACT_RELATIVE_PATH = Path(
    "src/apps_rg/fact_inventory/graph_evolution_graph_validation_contract.v1.json"
)
GE_W4_CONTRACT_SCHEMA_VERSION = "apps_rg.graph_evolution_graph_validation_contract.v1"
GE_W4_COMPLETION_MARKER = "GE_W4_CANDIDATE_GRAPH_VALIDATED"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class GraphEvolutionGraphValidationError(ValueError):
    """Raised when the frozen GE-W4 graph-validation contract is unavailable."""


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalized(value: object) -> str:
    return " ".join(_text(value).casefold().split())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphEvolutionGraphValidationError(f"GE-W4 JSON unavailable: {path}") from exc
    if not isinstance(payload, dict):
        raise GraphEvolutionGraphValidationError("GE-W4 JSON must be an object")
    return payload


def load_ge_w4_graph_validation_contract(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    path = (root / GE_W4_CONTRACT_RELATIVE_PATH).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise GraphEvolutionGraphValidationError("GE-W4 contract path escapes repository root") from exc
    return _read_json(path)


def load_candidate_graph_version(path: Path | str) -> dict[str, Any]:
    """Load one admitted GE-W3 candidate-version artifact without changing it."""

    return _read_json(Path(path))


def validate_ge_w4_graph_validation_contract(contract: Mapping[str, Any]) -> list[str]:
    """Return deterministic contract errors; an empty list is valid."""

    issues: list[str] = []
    if contract.get("schema_version") != GE_W4_CONTRACT_SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if contract.get("contract_id") != "APPS_RG_GRAPH_EVOLUTION_GRAPH_VALIDATION":
        issues.append("CONTRACT_ID")
    if contract.get("wave") != "GE_W4" or contract.get("status") != "FROZEN":
        issues.append("WAVE_OR_STATUS")
    input_contract = contract.get("input")
    if not isinstance(input_contract, Mapping) or input_contract.get(
        "required_candidate_status"
    ) != "UWG_COMMITTED_CANDIDATE" or input_contract.get(
        "required_completion_marker"
    ) != "GE_W3_UWG_COMMITTED_CANDIDATE" or any(
        input_contract.get(key) is not True
        for key in (
            "uwg_commit_receipt_required",
            "candidate_version_digest_required",
            "current_parent_graph_digest_required",
        )
    ):
        issues.append("INPUT")
    semantic = contract.get("semantic_validation")
    if not isinstance(semantic, Mapping) or semantic.get("assertion_node_type") != "atomic_proof_fact" or any(
        semantic.get(key) is not True
        for key in (
            "assertion_text_must_match_source_backed_candidate",
            "source_document_span_and_sha256_required",
            "proposed_skill_links_must_exist_in_parent_graph",
            "duplicate_assertion_against_parent_graph_forbidden",
        )
    ):
        issues.append("SEMANTIC_VALIDATION")
    output = contract.get("output")
    if not isinstance(output, Mapping) or output.get("candidate_state") != "GRAPH_VALIDATED" or output.get(
        "projection_state"
    ) != "NOT_BUILT" or output.get("retrieval_qualification_state") != "NOT_RUN" or any(
        output.get(key) is not expected
        for key, expected in (("candidate_graph_write_forbidden", True), ("active_runtime_pointer_changed", False))
    ):
        issues.append("OUTPUT")
    exit_gate = contract.get("ge_w4_exit")
    if not isinstance(exit_gate, Mapping) or exit_gate.get("completion_marker") != GE_W4_COMPLETION_MARKER or exit_gate.get(
        "next_gate"
    ) != "CLUSTER_AND_VECTOR_REBUILD" or any(
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
        issues.append("GE_W4_EXIT")
    return issues


def _version_digest_is_valid(version: Mapping[str, Any]) -> bool:
    unsigned = dict(version)
    recorded = _text(unsigned.pop("version_sha256", ""))
    for field in ("uwg_commit_receipt_id", "uwg_commit_receipt", "committed_at_utc", "completion_marker"):
        unsigned.pop(field, None)
    return bool(recorded) and recorded == _canonical_sha256(unsigned)


def _version_issues(version: Mapping[str, Any], baseline: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if version.get("schema_version") != "apps_rg.graph_evolution_candidate_graph_version.v1":
        issues.append("VERSION_SCHEMA")
    if version.get("status") != "UWG_COMMITTED_CANDIDATE":
        issues.append("VERSION_STATUS")
    if version.get("completion_marker") != "GE_W3_UWG_COMMITTED_CANDIDATE":
        issues.append("UWG_COMPLETION_MARKER")
    if not _text(version.get("uwg_commit_receipt_id")) or not isinstance(version.get("uwg_commit_receipt"), Mapping):
        issues.append("UWG_RECEIPT")
    if not _version_digest_is_valid(version):
        issues.append("VERSION_DIGEST")
    parent = version.get("parent_graph")
    current = baseline["canonical_graph"]
    if not isinstance(parent, Mapping) or any(
        _text(parent.get(key)) != _text(current.get(key))
        for key in ("authority_source", "payload_sha256", "graph_version")
    ):
        issues.append("PARENT_GRAPH_DRIFT")
    if version.get("projection_state") != "NOT_BUILT" or version.get("retrieval_qualification_state") != "NOT_RUN":
        issues.append("DERIVED_STATE_NOT_PRISTINE")
    if version.get("active_runtime_pointer_changed") is not False or version.get("activation_created") is not False:
        issues.append("ACTIVATION_BOUNDARY")
    return issues


def _delta_issues(version: Mapping[str, Any], graph: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    candidate = version.get("candidate")
    delta = version.get("proposed_graph_delta")
    if not isinstance(candidate, Mapping) or not isinstance(delta, Mapping):
        return ["CANDIDATE_OR_DELTA"]
    assertion_text = _text(candidate.get("assertion_text"))
    source = candidate.get("source")
    if not assertion_text or not isinstance(source, Mapping):
        return ["CANDIDATE_SOURCE"]
    if not all(_text(source.get(key)) for key in ("document_id", "span_ref", "excerpt")) or not _SHA256.fullmatch(
        _text(source.get("file_sha256"))
    ):
        issues.append("CANDIDATE_SOURCE_BINDING")
    nodes = delta.get("assertion_nodes")
    edges = delta.get("assertion_edges")
    if not isinstance(nodes, list) or len(nodes) != 1 or not isinstance(nodes[0], Mapping):
        return issues + ["ASSERTION_NODE_CARDINALITY"]
    if not isinstance(edges, list):
        return issues + ["ASSERTION_EDGES_NOT_LIST"]
    node = nodes[0]
    node_id = _text(node.get("node_id"))
    expected_source_ref = (
        f"source:{_text(source.get('document_id'))}#{_text(source.get('span_ref'))}"
        f"@sha256:{_text(source.get('file_sha256'))}"
    )
    if node.get("node_type") != "atomic_proof_fact" or _text(node.get("label")) != assertion_text or _text(
        node.get("description")
    ) != assertion_text or node.get("source_refs") != [expected_source_ref] or _text(node.get("candidate_id")) != _text(
        candidate.get("candidate_id")
    ) or node.get("proposed_only") is not True:
        issues.append("ASSERTION_NODE_BINDING")
    known_nodes = {
        _text(raw.get("node_id")): raw
        for raw in graph.get("graph_nodes") or []
        if isinstance(raw, Mapping) and _text(raw.get("node_id"))
    }
    if node_id in known_nodes:
        issues.append("ASSERTION_NODE_ALREADY_EXISTS")
    existing_texts = {
        _normalized(raw.get(field))
        for raw in known_nodes.values()
        for field in ("canonical_assertion_text", "description", "label")
        if _normalized(raw.get(field))
    }
    if _normalized(assertion_text) in existing_texts:
        issues.append("ASSERTION_DUPLICATES_PARENT_GRAPH")
    expected_skills = sorted(
        {_text(skill) for skill in (candidate.get("proposed_links") or {}).get("skill_ids") or [] if _text(skill)}
    )
    linked_skills = sorted(
        {
            _text(edge.get("source_node_id"))
            for edge in edges
            if isinstance(edge, Mapping)
            and edge.get("edge_type") == "skill_supported_by_fact"
            and _text(edge.get("target_node_id")) == node_id
            and _text(edge.get("candidate_id")) == _text(candidate.get("candidate_id"))
            and edge.get("proposed_only") is True
        }
    )
    if linked_skills != expected_skills or len(edges) != len(expected_skills):
        issues.append("ASSERTION_EDGE_BINDING")
    unknown_skills = [skill for skill in expected_skills if skill not in known_nodes]
    if unknown_skills:
        issues.append("PROPOSED_SKILL_NOT_IN_PARENT_GRAPH")
    return issues


def validate_admitted_candidate_graph_version(
    version: Mapping[str, Any], *, repo_root: Path | str
) -> dict[str, Any]:
    """Return a read-only GE-W4 receipt or a fail-closed blocking result."""

    contract = load_ge_w4_graph_validation_contract(repo_root)
    contract_issues = validate_ge_w4_graph_validation_contract(contract)
    if contract_issues:
        raise GraphEvolutionGraphValidationError(f"GE-W4 contract invalid: {', '.join(contract_issues)}")
    root = Path(repo_root).resolve()
    baseline = build_ge_w0_authority_baseline(root)
    issues = _version_issues(version, baseline)
    graph_path = root / baseline["canonical_graph"]["path"]
    graph = _read_json(graph_path)
    if not issues:
        issues.extend(_delta_issues(version, graph))
    if issues:
        return {
            "route": "BLOCKED",
            "reason": "GE_W4_GRAPH_VALIDATION_FAILED",
            "issues": sorted(set(issues)),
            "canonical_base_graph_mutated": False,
            "active_runtime_pointer_changed": False,
            "embedding_materialized": False,
            "activation_created": False,
        }
    delta = version["proposed_graph_delta"]
    receipt: dict[str, Any] = {
        "schema_version": "apps_rg.graph_evolution_graph_validation_receipt.v1",
        "completion_marker": GE_W4_COMPLETION_MARKER,
        "status": "PASS",
        "candidate_state": "GRAPH_VALIDATED",
        "candidate_version_id": version["version_id"],
        "candidate_version_sha256": version["version_sha256"],
        "uwg_commit_receipt_id": version["uwg_commit_receipt_id"],
        "parent_graph": dict(version["parent_graph"]),
        "candidate_id": version["candidate"]["candidate_id"],
        "candidate_sha256": candidate_digest(version["candidate"]),
        "validated_delta": {
            "assertion_node_count": len(delta["assertion_nodes"]),
            "assertion_edge_count": len(delta["assertion_edges"]),
            "assertion_node_ids": [node["node_id"] for node in delta["assertion_nodes"]],
            "assertion_edge_ids": [edge["edge_id"] for edge in delta["assertion_edges"]],
            "delta_sha256": _canonical_sha256(delta),
        },
        "projection_state": "NOT_BUILT",
        "retrieval_qualification_state": "NOT_RUN",
        "next_gate": "CLUSTER_AND_VECTOR_REBUILD",
        "canonical_base_graph_mutated": False,
        "active_runtime_pointer_changed": False,
        "cluster_registry_mutated": False,
        "cluster_projection_mutated": False,
        "embedding_materialized": False,
        "qrel_evaluation_run": False,
        "activation_created": False,
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return {"route": "GRAPH_VALIDATED", "reason": GE_W4_COMPLETION_MARKER, "receipt": receipt}


__all__ = [
    "GE_W4_COMPLETION_MARKER",
    "GE_W4_CONTRACT_RELATIVE_PATH",
    "GE_W4_CONTRACT_SCHEMA_VERSION",
    "GraphEvolutionGraphValidationError",
    "load_candidate_graph_version",
    "load_ge_w4_graph_validation_contract",
    "validate_admitted_candidate_graph_version",
    "validate_ge_w4_graph_validation_contract",
]
