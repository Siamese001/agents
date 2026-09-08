from __future__ import annotations

import copy
from pathlib import Path

from apps_rg.fact_inventory.graph_evolution_authority import (
    GE_W0_COMPLETION_MARKER,
    build_ge_w0_authority_baseline,
    load_ge_w0_authority_baseline_receipt,
    load_ge_w0_authority_contract,
    validate_ge_w0_authority_baseline,
    validate_ge_w0_authority_contract,
)


ROOT = Path(__file__).resolve().parents[4]


def test_ge_w0_contract_locks_authority_boundaries() -> None:
    contract = load_ge_w0_authority_contract(ROOT)

    assert validate_ge_w0_authority_contract(contract) == []
    assert contract["canonical_graph"]["authority_source"] == "augmented_skills_graph"
    assert contract["claim_evidence_substrate"]["runtime_claim_authority"] is False
    assert contract["derived_surfaces"]["graph_evidence_cluster_projection"]["claim_authority"] is False


def test_ge_w0_contract_rejects_candidate_ledger_as_runtime_authority() -> None:
    contract = copy.deepcopy(load_ge_w0_authority_contract(ROOT))
    contract["claim_evidence_substrate"]["runtime_claim_authority"] = True

    assert "CLAIM_EVIDENCE_SUBSTRATE_BOUNDARY" in validate_ge_w0_authority_contract(contract)


def test_ge_w0_contract_rejects_direct_staged_to_active_transition() -> None:
    contract = copy.deepcopy(load_ge_w0_authority_contract(ROOT))
    contract["allowed_transitions"].append(["STAGED", "ACTIVATED"])

    assert "GRAPH_VERSION_TRANSITIONS" in validate_ge_w0_authority_contract(contract)


def test_ge_w0_baseline_is_deterministic_read_only_and_current() -> None:
    first = build_ge_w0_authority_baseline(ROOT)
    second = build_ge_w0_authority_baseline(ROOT)

    assert first == second
    assert first["completion_marker"] == GE_W0_COMPLETION_MARKER
    assert first["canonical_graph"]["authority_source"] == "augmented_skills_graph"
    assert first["baseline_is_read_only"] is True
    assert first["activation_created"] is False
    assert validate_ge_w0_authority_baseline(first, repo_root=ROOT) == []


def test_checked_in_ge_w0_baseline_receipt_matches_current_authority() -> None:
    receipt = load_ge_w0_authority_baseline_receipt(ROOT)

    assert receipt == build_ge_w0_authority_baseline(ROOT)
    assert validate_ge_w0_authority_baseline(receipt, repo_root=ROOT) == []


def test_ge_w0_baseline_detects_graph_version_drift() -> None:
    receipt = build_ge_w0_authority_baseline(ROOT)
    receipt["canonical_graph"]["payload_sha256"] = "0" * 64

    assert "RECEIPT_DIGEST" in validate_ge_w0_authority_baseline(receipt, repo_root=ROOT)
    assert "BASELINE_DRIFT:canonical_graph" in validate_ge_w0_authority_baseline(
        receipt, repo_root=ROOT
    )
