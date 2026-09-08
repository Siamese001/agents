from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps_rg.fact_inventory.c03_graph_authority_reconciliation_wave3 import (
    GraphAuthorityReconciliationWave3Error,
    authority_reconciliation_profile,
    collect_graph_authority_reconciliation_issues,
    reconcile_graph_authority_wave3,
    validate_authority_reconciliation_contract,
    validate_w3_receipt,
)
from apps_rg.fact_inventory.c03_graph_edge_semantic_hardening import (
    collect_graph_edge_semantic_issues,
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
    "src/apps_rg/fact_inventory/"
    "c03_graph_authority_reconciliation_contract.v1.json"
)
W2_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave2_edge_assertion_hardening_receipt.json"
)
W3_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave3_authority_reconciliation_receipt.json"
)


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_w3_canonical_graph_is_fully_authority_reconciled() -> None:
    graph = _load(GRAPH_PATH)
    profile = authority_reconciliation_profile(graph)

    assert collect_graph_authority_reconciliation_issues(graph) == []
    assert collect_graph_edge_semantic_issues(graph) == []
    assert collect_graph_node_semantic_issues(graph) == []
    assert collect_canonical_graph_issues(graph) == []
    assert profile["node_count"] == 375
    assert profile["edge_count"] == 2315
    assert profile["skill_row_count"] == 254
    assert profile["retrieval_eligible_skill_count"] == 198
    assert profile["retired_node_count"] == 5
    assert profile["semantic_status_counts"] == {"HARDENED": 2315}
    assert profile["authority_issue_count"] == 0


def test_w3_closes_exact_section_and_policy_partitions() -> None:
    graph = _load(GRAPH_PATH)
    counts = authority_reconciliation_profile(graph)["edge_type_counts"]

    assert counts["section_can_select_skill"] == 32
    assert counts["skill_allowed_in_section"] == 709
    assert counts["skill_external_claim_eligible"] == 198
    assert counts["skill_projection_only_internal"] == 56
    assert counts["skill_requires_human_confirmation"] == 33
    assert counts["projection_excludes_blocked_skill"] == 40


def test_w3_marker_records_exact_retirements_and_additions() -> None:
    graph = _load(GRAPH_PATH)
    marker = graph["graph_metadata"]["authority_reconciliation"]

    assert marker["source_edge_count"] == 2114
    assert marker["current_edge_count"] == 2315
    assert marker["retired_edge_count"] == 122
    assert marker["retired_edge_reason_counts"] == {
        "EXTERNAL_ELIGIBLE_EDGE_CONFLICTS_WITH_INELIGIBLE_ROW": 24,
        "SECTION_EDGE_NOT_IN_SKILL_ROW_ALLOWLIST": 13,
        "W2_INTEGRITY_GAP:INTERNAL_ONLY_EDGE_CONFLICTS_WITH_RETRIEVAL_ELIGIBLE_ROW": 26,
        "W2_INTEGRITY_GAP:SECTION_NOT_IN_SKILL_ROW_ALLOWLIST": 32,
        "W2_INTEGRITY_GAP:SOURCE_FIELD_CONFLICT:domain_id": 9,
        "W2_INTEGRITY_GAP:SOURCE_FIELD_CONFLICT:pillar": 18,
    }
    assert marker["added_edge_count"] == 323
    assert marker["added_edge_type_counts"] == {
        "projection_excludes_blocked_skill": 30,
        "skill_allowed_in_section": 153,
        "skill_external_claim_eligible": 62,
        "skill_projection_only_internal": 54,
        "skill_requires_human_confirmation": 24,
    }
    assert marker["changed_hop_row_count"] == 237
    assert marker["retired_orphan_node_count"] == 5
    assert marker["production_promotion_authorized"] is False


def test_w3_is_idempotent_and_preserves_graph_and_row_identity() -> None:
    graph = _load(GRAPH_PATH)
    receipt = _load(W3_RECEIPT_PATH)
    reconciled = reconcile_graph_authority_wave3(graph)

    assert canonical_sha256(reconciled) == canonical_sha256(graph)
    assert receipt["preservation"] == {
        "graph_node_identity_set_preserved": True,
        "skill_row_identity_set_preserved": True,
        "retrieval_eligibility_preserved": True,
        "fact_id_links_preserved": True,
        "allowed_sections_preserved": True,
    }


def test_w3_receipt_is_digest_bound_and_legacy_embeddings_are_unchanged() -> None:
    receipt = _load(W3_RECEIPT_PATH)
    w2 = _load(W2_RECEIPT_PATH)

    validate_w3_receipt(receipt)
    assert receipt["scope"]["authority_reconciled"] is True
    assert receipt["scope"]["claim_authority_expanded"] is False
    assert receipt["scope"]["replacement_vectors_generated"] is False
    assert receipt["scope"]["production_promotion_authorized"] is False
    assert (
        receipt["legacy_embedding_artifacts"]["artifacts"]
        == w2["legacy_embedding_artifacts"]["artifacts"]
    )
    assert receipt["legacy_embedding_artifacts"]["artifact_count"] == 13
    assert receipt["wave_exit_gates"]["authority_reconciliation"] == "PASS_W3"
    assert receipt["wave_exit_gates"]["cluster_registry_materialization"] == (
        "OPEN_W4"
    )


def test_w3_historical_snapshots_are_explicitly_stale() -> None:
    receipt = _load(W3_RECEIPT_PATH)
    snapshots = receipt["historical_runtime_snapshots"]

    assert snapshots["status"] == (
        "STALE_SNAPSHOT_REQUIRES_CURRENT_GRAPH_ID_REHYDRATION"
    )
    assert snapshots["retired_edge_reference_file_count"] == 13
    assert "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json.bak" in (
        snapshots["files"]
    )
    assert any(path.endswith("augmented_skills_graph.sqlite") for path in snapshots["files"])


def test_w3_validator_detects_section_policy_path_and_marker_regressions() -> None:
    graph = _load(GRAPH_PATH)
    tampered = copy.deepcopy(graph)
    row = tampered["skill_rows"][0]
    row["allowed_sections"] = []
    row["graph_hop_path"] = ["missing", "path"]
    edge = next(
        item
        for item in tampered["graph_edges"]
        if item["edge_type"] == "skill_external_claim_eligible"
    )
    edge["edge_type"] = "skill_projection_only_internal"
    tampered["graph_metadata"]["authority_reconciliation"]["current_edge_count"] = 1

    issues = collect_graph_authority_reconciliation_issues(tampered)

    assert any("GRAPH_AUTHORITY_SECTION_DRIFT" in issue for issue in issues)
    assert any("GRAPH_AUTHORITY_HOP_PATH_NOT_TRAVERSABLE" in issue for issue in issues)
    assert any("GRAPH_AUTHORITY_RETRIEVAL_POLICY_DRIFT" in issue for issue in issues)
    assert any("GRAPH_AUTHORITY_RECONCILIATION_MARKER_MISMATCH" in issue for issue in issues)


def test_w3_contract_rejects_production_promotion_authority() -> None:
    contract = _load(CONTRACT_PATH)
    contract["acceptance"]["production_promotion_authorized"] = True

    with pytest.raises(
        GraphAuthorityReconciliationWave3Error,
        match="production_promotion_authorized",
    ):
        validate_authority_reconciliation_contract(contract)
