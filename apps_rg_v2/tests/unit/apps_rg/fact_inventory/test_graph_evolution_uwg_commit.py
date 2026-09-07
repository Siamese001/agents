from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from apps_rg.fact_inventory.graph_evolution_author_gate import author_gate_decision, candidate_digest
from apps_rg.fact_inventory.graph_evolution_candidate_intake import intake_graph_evolution_candidate
from apps_rg.fact_inventory.graph_evolution_uwg_commit import (
    GE_W3_COMPLETION_MARKER,
    GraphEvolutionUwgGateway,
    build_candidate_graph_version,
    commit_author_approved_candidate,
    load_ge_w3_uwg_commit_contract,
    validate_ge_w3_uwg_commit_contract,
)
from tests.unit.apps_rg.l5_uwg_fixture import verified_l5_exit_metadata


ROOT = Path(__file__).resolve().parents[4]
SOURCE_SHA = "a" * 64
L5_CERTIFICATION_REF = verified_l5_exit_metadata(
    request_id="ge-w3-test",
    run_id="ge-w3-test",
    trace_id="ge-w3-test",
)["l5_certification_packet_ref"]


def _candidate() -> dict[str, object]:
    result = intake_graph_evolution_candidate(
        {
            "assertion_text": "Built co-selling frameworks with SI and ISV partners.",
            "source_type": "base_resume",
            "proof_status": "proof_eligible",
            "source_document_id": "resume:2026-08",
            "source_span_ref": "resume:p1:bullet4",
            "source_excerpt": "Built co-selling frameworks with SI and ISV partners.",
            "source_file_sha256": SOURCE_SHA,
            "proposed_skill_ids": ["skill_partner_co_selling"],
            "producer_run_id": "ge-w3-test",
        },
        repo_root=ROOT,
    )
    return result["candidate"]


def _approved_decision(candidate: dict[str, object]) -> dict[str, object]:
    digest = candidate_digest(candidate)
    checks = {
        "source_fidelity": True,
        "assertion_atomicity": True,
        "graph_linkage_fit": True,
        "claim_policy_fit": True,
    }
    reviews = [
        {
            "schema_version": "apps_rg.graph_evolution_author_review.v1",
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": digest,
            "reviewer_ref": "human-reviewer://evidence-reviewer",
            "role": "EVIDENCE_REVIEWER",
            "decision": "APPROVE",
            "checks": checks,
            "rationale": "Reviewed source fidelity and assertion atomicity.",
        },
        {
            "schema_version": "apps_rg.graph_evolution_author_review.v1",
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": digest,
            "reviewer_ref": "human-reviewer://graph-steward",
            "role": "GRAPH_STEWARD",
            "decision": "APPROVE",
            "checks": checks,
            "rationale": "Reviewed proposed graph linkage and claim policy.",
        },
    ]
    result = author_gate_decision(candidate, reviews, repo_root=ROOT)
    assert result["route"] == "AUTHOR_APPROVED"
    return result["decision"]


def test_ge_w3_contract_locks_uwg_candidate_version_boundary() -> None:
    contract = load_ge_w3_uwg_commit_contract(ROOT)

    assert validate_ge_w3_uwg_commit_contract(contract) == []
    assert contract["write_authority"]["authority"] == "UWG_ONLY"
    assert contract["candidate_version"]["active_runtime_pointer_changed"] is False


def test_candidate_version_materializes_assertion_and_skill_link_without_activation() -> None:
    candidate = _candidate()
    version = build_candidate_graph_version(candidate, _approved_decision(candidate), repo_root=ROOT)

    assert version["status"] == "UWG_COMMITTED_CANDIDATE"
    assert version["parent_graph"]["authority_source"] == "augmented_skills_graph"
    assert version["proposed_graph_delta"]["assertion_nodes"][0]["node_type"] == "atomic_proof_fact"
    assert version["proposed_graph_delta"]["assertion_edges"][0]["edge_type"] == "skill_supported_by_fact"
    assert version["projection_state"] == "NOT_BUILT"
    assert version["active_runtime_pointer_changed"] is False
    assert version["activation_created"] is False


def test_real_uwg_admits_approved_candidate_then_writes_immutable_candidate_version(tmp_path: Path) -> None:
    candidate = _candidate()
    target = tmp_path / "candidate_graph_version.json"
    result = commit_author_approved_candidate(
        candidate,
        _approved_decision(candidate),
        repo_root=ROOT,
        candidate_version_path=target,
        l5_certification_ref=L5_CERTIFICATION_REF,
        gateway=GraphEvolutionUwgGateway(),
    )

    assert result["route"] == "UWG_COMMITTED_CANDIDATE"
    assert result["reason"] == GE_W3_COMPLETION_MARKER
    assert result["uwg_commit_receipt_id"]
    assert target.is_file()
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["completion_marker"] == GE_W3_COMPLETION_MARKER
    assert written["active_runtime_pointer_changed"] is False
    assert written["projection_state"] == "NOT_BUILT"


def test_nonapproved_author_gate_cannot_reach_uwg_or_write(tmp_path: Path) -> None:
    candidate = _candidate()
    decision = _approved_decision(candidate)
    decision = copy.deepcopy(decision)
    decision["status"] = "HOLD"
    target = tmp_path / "blocked.json"

    result = commit_author_approved_candidate(
        candidate, decision, repo_root=ROOT, candidate_version_path=target
    )

    assert result["route"] == "BLOCKED"
    assert not target.exists()


def test_missing_l5_certification_blocks_before_uwg_or_write(tmp_path: Path) -> None:
    candidate = _candidate()
    target = tmp_path / "blocked_without_l5.json"

    result = commit_author_approved_candidate(
        candidate, _approved_decision(candidate), repo_root=ROOT, candidate_version_path=target
    )

    assert result["route"] == "BLOCKED"
    assert result["reason"] == "GE_W3_L5_CERTIFICATION_REQUIRED"
    assert not target.exists()


def test_base_graph_overwrite_is_refused_without_touching_authority() -> None:
    candidate = _candidate()
    decision = _approved_decision(candidate)
    graph_path = ROOT / "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
    before = hashlib.sha256(graph_path.read_bytes()).hexdigest()

    result = commit_author_approved_candidate(
        candidate, decision, repo_root=ROOT, candidate_version_path=graph_path
    )

    assert result["route"] == "BLOCKED"
    assert result["reason"] == "GE_W3_BASE_GRAPH_OVERWRITE_FORBIDDEN"
    assert hashlib.sha256(graph_path.read_bytes()).hexdigest() == before


def test_contract_detects_activation_drift() -> None:
    contract = copy.deepcopy(load_ge_w3_uwg_commit_contract(ROOT))
    contract["ge_w3_exit"]["activation_created"] = True

    assert "GE_W3_EXIT" in validate_ge_w3_uwg_commit_contract(contract)
