from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    GraphNodeSemanticHardeningError,
    canonical_sha256,
    collect_graph_node_semantic_issues,
    harden_graph_node_semantics,
    semantic_profile,
    validate_node_semantic_contract,
    validate_w1_receipt,
)
from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    collect_canonical_graph_issues,
)

ROOT = Path(__file__).resolve().parents[4]
GRAPH_PATH = ROOT / "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
FACTS_PATH = ROOT / (
    "artifacts/apps_rg/fact_inventory/"
    "master_candidate_skills_fact_ledger_20260518T1100Z.json"
)
BASE_RESUME_PATH = ROOT / "src/apps_rg/resume/base/amit_ayer_base_resume_v1.json"
CONTRACT_PATH = ROOT / (
    "src/apps_rg/fact_inventory/c03_graph_node_semantic_contract.v1.json"
)
W0_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave0_baseline_receipt.json"
)
W1_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave1_node_semantic_hardening_receipt.json"
)


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_all_canonical_nodes_pass_w1_semantic_hardening() -> None:
    graph = _load(GRAPH_PATH)
    profile = semantic_profile(graph)

    assert collect_graph_node_semantic_issues(graph) == []
    assert collect_canonical_graph_issues(graph) == []
    assert profile["node_count"] == 375
    assert profile["edge_count"] == 2315
    assert profile["skill_row_count"] == 254
    assert profile["sentinel_description_count"] == 0
    assert profile["generic_description_count"] == 0
    assert profile["fact_missing_graph_hop_count"] == 0
    assert profile["semantic_issue_count"] == 0
    assert profile["held_internal_only_node_count"] == 34


def test_w1_preserves_identity_and_edges_while_recording_legacy_staleness() -> None:
    graph = _load(GRAPH_PATH)
    marker = graph["graph_metadata"]["node_semantic_hardening"]

    assert marker["node_count"] == 375
    assert marker["hardened_node_count"] == 341
    assert marker["held_internal_only_node_count"] == 34
    assert marker["description_change_count"] == 293
    assert marker["fact_missing_removed_count"] == 5
    assert marker["graph_edges_sha256_before"] == marker["graph_edges_sha256_after"]
    assert graph["graph_metadata"]["legacy_skill_embedding_status"] == (
        "STALE_FAIL_CLOSED_AFTER_W1_NODE_SEMANTIC_HARDENING"
    )


def test_hardened_claims_have_evidence_or_an_explicit_hold() -> None:
    graph = _load(GRAPH_PATH)
    rows = {row["skill_id"]: row for row in graph["skill_rows"]}
    claim_nodes = [
        node
        for node in graph["graph_nodes"]
        if node["node_type"] in {"employment", "skill", "skill_row"}
    ]

    for node in claim_nodes:
        refs = node["authority_refs"]
        assert refs == sorted(set(refs))
        if node["semantic_hardening_status"] == "HARDENED":
            assert any(not ref.startswith("ledger:") for ref in refs)
        else:
            assert node["semantic_hardening_status"] == "HELD_INTERNAL_ONLY"
            assert rows[node["node_id"]]["retrieval_eligible"] is False


def test_w1_hardening_is_idempotent() -> None:
    graph = _load(GRAPH_PATH)
    hardened = harden_graph_node_semantics(
        graph,
        candidate_fact_payload=_load(FACTS_PATH),
        base_resume_payload=_load(BASE_RESUME_PATH),
    )
    assert canonical_sha256(hardened) == canonical_sha256(graph)


def test_w1_receipt_is_digest_bound_and_preserves_legacy_inventory() -> None:
    receipt = _load(W1_RECEIPT_PATH)
    w0 = _load(W0_RECEIPT_PATH)

    validate_w1_receipt(receipt)
    assert receipt["after"]["semantic_profile"]["semantic_issue_count"] == 0
    assert receipt["after"]["changed_description_count"] == 293
    assert (
        receipt["legacy_embedding_artifacts"]["artifacts"]
        == (w0["legacy_embedding_artifacts"]["artifacts"])
    )
    assert receipt["next_wave"] == ("C03_CLUSTER_EMBEDDING_W2_EDGE_ASSERTION_HARDENING")


def test_w1_validator_detects_semantic_and_authority_regressions() -> None:
    graph = _load(GRAPH_PATH)
    tampered = copy.deepcopy(graph)
    node = tampered["graph_nodes"][0]
    node["description"] = "["
    node["canonical_assertion_text"] = "["
    node["authority_refs"] = ["unregistered-authority"]

    issues = collect_graph_node_semantic_issues(tampered)

    assert any("GRAPH_NODE_DESCRIPTION_NOT_CONCRETE" in issue for issue in issues)
    assert any("GRAPH_NODE_AUTHORITY_REF_UNRESOLVED" in issue for issue in issues)


def test_w1_contract_rejects_edge_mutation_authority() -> None:
    contract = _load(CONTRACT_PATH)
    contract["mutation_boundaries"]["graph_edge_changes_allowed"] = True

    with pytest.raises(GraphNodeSemanticHardeningError, match="graph_edge_changes"):
        validate_node_semantic_contract(contract)
