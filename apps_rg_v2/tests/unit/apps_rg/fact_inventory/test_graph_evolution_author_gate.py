from __future__ import annotations

import copy
from pathlib import Path

from apps_rg.fact_inventory.graph_evolution_author_gate import (
    GE_W2_COMPLETION_MARKER,
    author_gate_decision,
    candidate_digest,
    load_ge_w2_author_gate_contract,
    validate_ge_w2_author_gate_contract,
)
from apps_rg.fact_inventory.graph_evolution_candidate_intake import intake_graph_evolution_candidate


ROOT = Path(__file__).resolve().parents[4]
SOURCE_SHA = "a" * 64


def _candidate(**overrides: object) -> dict[str, object]:
    proposal: dict[str, object] = {
        "assertion_text": "Built co-selling frameworks with SI and ISV partners.",
        "source_type": "base_resume",
        "proof_status": "proof_eligible",
        "source_document_id": "resume:2026-08",
        "source_span_ref": "resume:p1:bullet4",
        "source_excerpt": "Built co-selling frameworks with SI and ISV partners.",
        "source_file_sha256": SOURCE_SHA,
        "proposed_skill_ids": ["skill_partner_co_selling"],
        "producer_run_id": "ge-w2-test",
    }
    proposal.update(overrides)
    result = intake_graph_evolution_candidate(proposal, repo_root=ROOT)
    return result["candidate"]


def _reviews(candidate: dict[str, object], *, evidence: str = "APPROVE", graph: str = "APPROVE") -> list[dict[str, object]]:
    digest = candidate_digest(candidate)
    checks = {
        "source_fidelity": True,
        "assertion_atomicity": True,
        "graph_linkage_fit": True,
        "claim_policy_fit": True,
    }
    return [
        {
            "schema_version": "apps_rg.graph_evolution_author_review.v1",
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": digest,
            "reviewer_ref": "human-reviewer://evidence-reviewer",
            "role": "EVIDENCE_REVIEWER",
            "decision": evidence,
            "checks": checks if evidence == "APPROVE" else {},
            "rationale": "Reviewed the cited source and assertion.",
        },
        {
            "schema_version": "apps_rg.graph_evolution_author_review.v1",
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": digest,
            "reviewer_ref": "human-reviewer://graph-steward",
            "role": "GRAPH_STEWARD",
            "decision": graph,
            "checks": checks if graph == "APPROVE" else {},
            "rationale": "Reviewed graph links and claim policy.",
        },
    ]


def _adjudication(candidate: dict[str, object], resolution: str = "APPROVE") -> dict[str, object]:
    return {
        "schema_version": "apps_rg.graph_evolution_author_adjudication.v1",
        "candidate_id": candidate["candidate_id"],
        "candidate_sha256": candidate_digest(candidate),
        "adjudicator_ref": "human-reviewer://author-adjudicator",
        "resolution": resolution,
        "rationale": "Resolved the source and graph-review disagreement.",
    }


def test_ge_w2_contract_locks_human_and_no_write_boundaries() -> None:
    contract = load_ge_w2_author_gate_contract(ROOT)

    assert validate_ge_w2_author_gate_contract(contract) == []
    assert contract["human_review"]["distinct_reviewer_identities_required"] is True
    assert contract["ge_w2_exit"]["uwg_called"] is False


def test_two_human_approvals_authorize_only_the_next_uwg_gate() -> None:
    candidate = _candidate()
    result = author_gate_decision(candidate, _reviews(candidate), repo_root=ROOT)

    assert result["route"] == "AUTHOR_APPROVED"
    receipt = result["decision"]
    assert receipt["completion_marker"] == GE_W2_COMPLETION_MARKER
    assert receipt["next_gate"] == "UWG_COMMIT"
    assert receipt["canonical_graph_mutated"] is False
    assert receipt["embedding_materialized"] is False
    assert receipt["activation_created"] is False


def test_disagreement_requires_distinct_human_adjudication() -> None:
    candidate = _candidate()
    pending = author_gate_decision(candidate, _reviews(candidate, graph="HOLD"), repo_root=ROOT)
    resolved = author_gate_decision(
        candidate,
        _reviews(candidate, graph="HOLD"),
        repo_root=ROOT,
        adjudication=_adjudication(candidate),
    )

    assert pending["route"] == "HOLD"
    assert pending["reason"] == "GE_W2_ADJUDICATION_REQUIRED"
    assert resolved["route"] == "AUTHOR_APPROVED"
    assert resolved["decision"]["adjudication_ref"] == "human-reviewer://author-adjudicator"


def test_unanimous_rejection_rejects_candidate_without_graph_write() -> None:
    candidate = _candidate()
    result = author_gate_decision(
        candidate, _reviews(candidate, evidence="REJECT", graph="REJECT"), repo_root=ROOT
    )

    assert result["route"] == "REJECTED"
    assert result["decision"]["next_gate"] is None
    assert result["decision"]["canonical_graph_mutated"] is False


def test_stale_base_graph_binding_blocks_authorization() -> None:
    candidate = copy.deepcopy(_candidate())
    candidate["base_graph"]["payload_sha256"] = "0" * 64

    result = author_gate_decision(candidate, _reviews(candidate), repo_root=ROOT)

    assert result["route"] == "BLOCKED"
    assert "BASE_GRAPH_DRIFT" in result["issues"]


def test_same_reviewer_cannot_fill_both_required_roles() -> None:
    candidate = _candidate()
    reviews = _reviews(candidate)
    reviews[1]["reviewer_ref"] = reviews[0]["reviewer_ref"]

    result = author_gate_decision(candidate, reviews, repo_root=ROOT)

    assert result["route"] == "BLOCKED"
    assert "REVIEWER_IDENTITIES_NOT_DISTINCT" in result["issues"]


def test_contract_detects_write_boundary_drift() -> None:
    contract = copy.deepcopy(load_ge_w2_author_gate_contract(ROOT))
    contract["ge_w2_exit"]["uwg_called"] = True

    assert "GE_W2_EXIT" in validate_ge_w2_author_gate_contract(contract)
