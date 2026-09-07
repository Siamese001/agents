from __future__ import annotations

import copy
from pathlib import Path

from apps_rg.fact_inventory.graph_evolution_author_gate import author_gate_decision, candidate_digest
from apps_rg.fact_inventory.graph_evolution_candidate_intake import intake_graph_evolution_candidate
from apps_rg.fact_inventory.graph_evolution_graph_validation import (
    GE_W4_COMPLETION_MARKER,
    load_candidate_graph_version,
    load_ge_w4_graph_validation_contract,
    validate_admitted_candidate_graph_version,
    validate_ge_w4_graph_validation_contract,
)
from apps_rg.fact_inventory.graph_evolution_uwg_commit import (
    GraphEvolutionUwgGateway,
    commit_author_approved_candidate,
)
from tests.unit.apps_rg.l5_uwg_fixture import verified_l5_exit_metadata


ROOT = Path(__file__).resolve().parents[4]
SOURCE_SHA = "a" * 64
L5_CERTIFICATION_REF = verified_l5_exit_metadata(
    request_id="ge-w4-test", run_id="ge-w4-test", trace_id="ge-w4-test"
)["l5_certification_packet_ref"]


def _candidate(assertion_text: str = "Built co-selling frameworks with SI and ISV partners.") -> dict[str, object]:
    result = intake_graph_evolution_candidate(
        {
            "assertion_text": assertion_text,
            "source_type": "base_resume",
            "proof_status": "proof_eligible",
            "source_document_id": "resume:2026-08",
            "source_span_ref": "resume:p1:bullet4",
            "source_excerpt": assertion_text,
            "source_file_sha256": SOURCE_SHA,
            "proposed_skill_ids": ["skill_partner_co_selling"],
            "producer_run_id": "ge-w4-test",
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
            "rationale": "Reviewed the source and atomized assertion.",
        },
        {
            "schema_version": "apps_rg.graph_evolution_author_review.v1",
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": digest,
            "reviewer_ref": "human-reviewer://graph-steward",
            "role": "GRAPH_STEWARD",
            "decision": "APPROVE",
            "checks": checks,
            "rationale": "Reviewed graph linkage and claim policy.",
        },
    ]
    result = author_gate_decision(candidate, reviews, repo_root=ROOT)
    assert result["route"] == "AUTHOR_APPROVED"
    return result["decision"]


def _admitted_version(tmp_path: Path, assertion_text: str = "Built co-selling frameworks with SI and ISV partners.") -> dict[str, object]:
    candidate = _candidate(assertion_text)
    path = tmp_path / "candidate_graph_version.json"
    result = commit_author_approved_candidate(
        candidate,
        _approved_decision(candidate),
        repo_root=ROOT,
        candidate_version_path=path,
        l5_certification_ref=L5_CERTIFICATION_REF,
        gateway=GraphEvolutionUwgGateway(),
    )
    assert result["route"] == "UWG_COMMITTED_CANDIDATE"
    return load_candidate_graph_version(path)


def test_ge_w4_contract_locks_read_only_graph_validation() -> None:
    contract = load_ge_w4_graph_validation_contract(ROOT)

    assert validate_ge_w4_graph_validation_contract(contract) == []
    assert contract["output"]["candidate_graph_write_forbidden"] is True
    assert contract["ge_w4_exit"]["embedding_materialized"] is False


def test_admitted_candidate_validates_to_graph_validated_without_projection(tmp_path: Path) -> None:
    version = _admitted_version(tmp_path)
    result = validate_admitted_candidate_graph_version(version, repo_root=ROOT)

    assert result["route"] == "GRAPH_VALIDATED"
    receipt = result["receipt"]
    assert receipt["completion_marker"] == GE_W4_COMPLETION_MARKER
    assert receipt["candidate_state"] == "GRAPH_VALIDATED"
    assert receipt["validated_delta"]["assertion_node_count"] == 1
    assert receipt["validated_delta"]["assertion_edge_count"] == 1
    assert receipt["projection_state"] == "NOT_BUILT"
    assert receipt["active_runtime_pointer_changed"] is False
    assert receipt["embedding_materialized"] is False


def test_tampered_candidate_overlay_fails_closed(tmp_path: Path) -> None:
    version = copy.deepcopy(_admitted_version(tmp_path))
    version["proposed_graph_delta"]["assertion_nodes"][0]["description"] = "Tampered assertion."

    result = validate_admitted_candidate_graph_version(version, repo_root=ROOT)

    assert result["route"] == "BLOCKED"
    assert "VERSION_DIGEST" in result["issues"]


def test_parent_graph_drift_fails_closed(tmp_path: Path) -> None:
    version = copy.deepcopy(_admitted_version(tmp_path))
    version["parent_graph"]["payload_sha256"] = "0" * 64

    result = validate_admitted_candidate_graph_version(version, repo_root=ROOT)

    assert result["route"] == "BLOCKED"
    assert "PARENT_GRAPH_DRIFT" in result["issues"]


def test_duplicate_assertion_is_rejected_against_parent_graph(tmp_path: Path) -> None:
    version = _admitted_version(tmp_path, "Amit Ayer — Governed AI Platform Leader")

    result = validate_admitted_candidate_graph_version(version, repo_root=ROOT)

    assert result["route"] == "BLOCKED"
    assert "ASSERTION_DUPLICATES_PARENT_GRAPH" in result["issues"]


def test_contract_detects_activation_boundary_drift() -> None:
    contract = copy.deepcopy(load_ge_w4_graph_validation_contract(ROOT))
    contract["output"]["active_runtime_pointer_changed"] = True

    assert "OUTPUT" in validate_ge_w4_graph_validation_contract(contract)
