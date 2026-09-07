from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps_rg.fact_inventory.c03_graph_edge_semantic_hardening import (
    BASIS_KIND_BY_EDGE_TYPE,
    GraphEdgeSemanticHardeningError,
    collect_graph_edge_semantic_issues,
    edge_semantic_profile,
    harden_graph_edge_semantics,
    validate_edge_semantic_contract,
    validate_w2_receipt,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
    collect_graph_node_semantic_issues,
)
from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    collect_canonical_graph_issues,
)

ROOT = Path(__file__).resolve().parents[4]
GRAPH_PATH = ROOT / "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
CONTRACT_PATH = ROOT / (
    "src/apps_rg/fact_inventory/c03_graph_edge_semantic_contract.v1.json"
)
W1_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave1_node_semantic_hardening_receipt.json"
)
W2_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave2_edge_assertion_hardening_receipt.json"
)


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_all_canonical_edges_pass_w2_semantic_hardening() -> None:
    graph = _load(GRAPH_PATH)
    profile = edge_semantic_profile(graph)

    assert collect_graph_edge_semantic_issues(graph) == []
    assert collect_graph_node_semantic_issues(graph) == []
    assert collect_canonical_graph_issues(graph) == []
    assert profile["edge_count"] == 2315
    assert profile["edge_type_count"] == 32
    assert profile["missing_canonical_assertion_count"] == 0
    assert profile["missing_assertion_basis_count"] == 0
    assert profile["generic_assertion_count"] == 0
    assert profile["semantic_issue_count"] == 0
    assert profile["lifecycle_disposition_counts"] == {
        "ACTIVE_POLICY_GATED": 1291,
        "HELD_NON_ACTIVE_ENDPOINT": 767,
        "INTERNAL_TRAVERSAL_ONLY": 257,
    }
    assert profile["semantic_status_counts"] == {"HARDENED": 2315}


def test_w2_covers_every_registered_edge_type_and_basis_kind() -> None:
    graph = _load(GRAPH_PATH)
    contract = _load(CONTRACT_PATH)
    observed_types = {edge["edge_type"] for edge in graph["graph_edges"]}

    assert observed_types == set(BASIS_KIND_BY_EDGE_TYPE)
    assert contract["basis_kind_by_edge_type"] == BASIS_KIND_BY_EDGE_TYPE
    assert len(observed_types) == 32
    for edge in graph["graph_edges"]:
        assert edge["assertion_basis"] == BASIS_KIND_BY_EDGE_TYPE[edge["edge_type"]]
        assert edge["assertion_basis_refs"] == sorted(set(edge["assertion_basis_refs"]))


def test_w2_preserves_legacy_edge_payload_nodes_and_skill_rows() -> None:
    graph = _load(GRAPH_PATH)
    marker = graph["graph_metadata"]["edge_semantic_hardening"]

    assert marker["edge_count"] == 2114
    assert marker["semantically_specified_edge_count"] == 2114
    assert marker["hardened_edge_count"] == 2029
    assert marker["held_integrity_gap_edge_count"] == 85
    assert marker["integrity_gap_count"] == 85
    assert (
        marker["legacy_edge_payload_sha256_before"]
        == marker["legacy_edge_payload_sha256_after"]
    )
    assert marker["edge_identity_sha256_before"] == marker["edge_identity_sha256_after"]
    assert marker["edge_topology_sha256_before"] == marker["edge_topology_sha256_after"]
    assert marker["graph_nodes_sha256_before"] == marker["graph_nodes_sha256_after"]
    assert marker["skill_rows_sha256_before"] == marker["skill_rows_sha256_after"]
    assert marker["production_promotion_authorized"] is False


def test_w2_historical_marker_preserves_conflicts_reconciled_by_w3() -> None:
    graph = _load(GRAPH_PATH)
    marker = graph["graph_metadata"]["edge_semantic_hardening"]
    held = [
        edge
        for edge in graph["graph_edges"]
        if edge["edge_semantic_status"] == "HELD_INTEGRITY_GAP"
    ]
    assert held == []
    assert marker["held_integrity_gap_edge_count"] == 85
    assert marker["integrity_gap_reason_counts"] == {
        "SOURCE_FIELD_CONFLICT:pillar": 18,
        "SOURCE_FIELD_CONFLICT:domain_id": 9,
        "SECTION_NOT_IN_SKILL_ROW_ALLOWLIST": 32,
        "INTERNAL_ONLY_EDGE_CONFLICTS_WITH_RETRIEVAL_ELIGIBLE_ROW": 26,
    }


def test_non_causal_relationship_edges_are_explicitly_bounded() -> None:
    graph = _load(GRAPH_PATH)
    non_causal_types = {
        "career_track_precedes_career_track",
        "pillar_phase_bridge",
        "skill_reinforces_skill",
    }
    edges = [
        edge for edge in graph["graph_edges"] if edge["edge_type"] in non_causal_types
    ]

    assert len(edges) == 28
    assert all(edge["assertion_basis"] == "non_causal_bridge" for edge in edges)
    assert all("non-causal" in edge["canonical_assertion_text"] for edge in edges)
    assert all(edge.get("causal") is not True for edge in edges)


def test_w2_hardening_is_idempotent() -> None:
    graph = _load(GRAPH_PATH)
    hardened = harden_graph_edge_semantics(graph)

    assert canonical_sha256(hardened) == canonical_sha256(graph)


def test_w2_receipt_is_digest_bound_and_preserves_legacy_inventory() -> None:
    receipt = _load(W2_RECEIPT_PATH)
    w1 = _load(W1_RECEIPT_PATH)

    validate_w2_receipt(receipt)
    assert receipt["after"]["edge_semantic_profile"]["semantic_issue_count"] == 0
    assert receipt["scope"]["edge_assertions_semantically_specified"] is True
    assert receipt["scope"]["edge_assertions_fully_reconciled"] is False
    assert receipt["preservation"] == {
        "edge_count_preserved": True,
        "edge_identity_set_preserved": True,
        "edge_topology_preserved": True,
        "legacy_edge_payload_preserved": True,
        "graph_nodes_preserved": True,
        "skill_rows_preserved": True,
    }
    assert (
        receipt["legacy_embedding_artifacts"]["artifacts"]
        == w1["legacy_embedding_artifacts"]["artifacts"]
    )
    assert receipt["next_wave"] == ("C03_CLUSTER_EMBEDDING_W3_AUTHORITY_RECONCILIATION")
    assert receipt["wave_exit_gates"]["edge_assertion_hardening"] == (
        "PASS_WITH_85_HELD_INTEGRITY_GAPS"
    )
    assert receipt["wave_exit_gates"]["authority_reconciliation"] == "OPEN_W3"


def test_w2_validator_detects_assertion_basis_and_lifecycle_regressions() -> None:
    graph = _load(GRAPH_PATH)
    tampered = copy.deepcopy(graph)
    edge = tampered["graph_edges"][0]
    edge["canonical_assertion_text"] = edge["rationale"]
    edge["assertion_basis_refs"] = ["unregistered-authority"]
    edge["lifecycle_disposition"] = "ACTIVE_POLICY_GATED"

    issues = collect_graph_edge_semantic_issues(tampered)

    assert any("GRAPH_EDGE_ASSERTION_NOT_CONCRETE" in issue for issue in issues)
    assert any("GRAPH_EDGE_ASSERTION_BASIS_REFS_INVALID" in issue for issue in issues)
    assert any("GRAPH_EDGE_ASSERTION_BASIS_REF_UNRESOLVED" in issue for issue in issues)
    assert any("GRAPH_EDGE_LIFECYCLE_DISPOSITION_INVALID" in issue for issue in issues)


def test_w2_contract_rejects_topology_mutation_authority() -> None:
    contract = _load(CONTRACT_PATH)
    contract["mutation_boundaries"]["edge_endpoint_changes_allowed"] = True

    with pytest.raises(GraphEdgeSemanticHardeningError, match="edge_endpoint_changes"):
        validate_edge_semantic_contract(contract)
