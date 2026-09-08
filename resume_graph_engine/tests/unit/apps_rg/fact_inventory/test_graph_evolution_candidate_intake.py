from __future__ import annotations

import copy
from pathlib import Path

from apps_rg.fact_inventory.graph_evolution_authority import build_ge_w0_authority_baseline
from apps_rg.fact_inventory.graph_evolution_candidate_intake import (
    GE_W1_COMPLETION_MARKER,
    intake_graph_evolution_candidate,
    load_ge_w1_candidate_intake_contract,
    validate_ge_w1_candidate_intake_contract,
)


ROOT = Path(__file__).resolve().parents[4]
SOURCE_SHA = "a" * 64


def _grounded(**overrides: object) -> dict[str, object]:
    proposal: dict[str, object] = {
        "operation": "CREATE",
        "assertion_text": "Built co-selling frameworks with SI and ISV partners.",
        "source_type": "base_resume",
        "proof_status": "proof_eligible",
        "source_document_id": "resume:2026-08",
        "source_span_ref": "resume:p1:bullet4",
        "source_excerpt": "Built co-selling frameworks with SI and ISV partners.",
        "source_file_sha256": SOURCE_SHA,
        "proposed_skill_ids": ["skill_partner_co_selling"],
        "producer_run_id": "ge-w1-test",
    }
    proposal.update(overrides)
    return proposal


def test_ge_w1_contract_preserves_authority_and_embedding_boundaries() -> None:
    contract = load_ge_w1_candidate_intake_contract(ROOT)

    assert validate_ge_w1_candidate_intake_contract(contract) == []
    assert contract["authority_binding"]["candidate_runtime_claim_authority"] is False
    assert contract["candidate_record"]["embedding_materialization"] == "GE_W5_ONLY"


def test_grounded_proposal_stages_bound_to_current_graph_without_mutation() -> None:
    before = build_ge_w0_authority_baseline(ROOT)
    result = intake_graph_evolution_candidate(_grounded(), repo_root=ROOT)
    after = build_ge_w0_authority_baseline(ROOT)

    assert before == after
    assert result["route"] == "CANDIDATE_STAGED"
    assert result["reason"] == GE_W1_COMPLETION_MARKER
    assert result["candidate"]["status"] == "STAGED"
    assert result["candidate"]["base_graph"]["payload_sha256"] == before["canonical_graph"]["payload_sha256"]
    assert "embedding" not in result["candidate"]
    assert "vector" not in result["candidate"]
    assert result["canonical_graph_mutated"] is False
    assert result["embedding_materialized"] is False
    assert result["activation_created"] is False


def test_generated_targeting_text_routes_only_to_semantic_cache() -> None:
    result = intake_graph_evolution_candidate(
        _grounded(source_type="jd_payload", proof_status="targeting_only"), repo_root=ROOT
    )

    assert result["route"] == "SEMANTIC_CACHE_ONLY"
    assert "candidate" not in result
    assert result["canonical_graph_mutated"] is False


def test_missing_source_file_hash_rejects_grounded_proposal() -> None:
    result = intake_graph_evolution_candidate(_grounded(source_file_sha256=""), repo_root=ROOT)

    assert result["route"] == "REJECTED"
    assert "SOURCE_FILE_SHA256_REQUIRED" in result["issues"]


def test_duplicate_or_conflict_holds_for_author_gate() -> None:
    result = intake_graph_evolution_candidate(
        _grounded(potential_conflict_ids=["fact_partner_revenue_3m"]),
        repo_root=ROOT,
        existing_assertions=[
            {"fact_id": "fact_cosell_existing", "assertion_text": _grounded()["assertion_text"]}
        ],
    )

    assert result["route"] == "CANDIDATE_STAGED"
    assert result["candidate"]["status"] == "HOLD"
    assert result["candidate"]["duplicate_ids"] == ["fact_cosell_existing"]
    assert result["candidate"]["potential_conflict_ids"] == ["fact_partner_revenue_3m"]


def test_fuse_requires_multiple_source_references() -> None:
    result = intake_graph_evolution_candidate(
        _grounded(write_back_operation="fuse", supporting_source_refs=["resume:p1:bullet4"]),
        repo_root=ROOT,
    )

    assert result["route"] == "REJECTED"
    assert "FUSE_SOURCE_REFS_REQUIRED" in result["issues"]


def test_contract_detects_activation_boundary_drift() -> None:
    contract = copy.deepcopy(load_ge_w1_candidate_intake_contract(ROOT))
    contract["authority_binding"]["candidate_may_not_activate_runtime"] = False

    assert "AUTHORITY_BINDING" in validate_ge_w1_candidate_intake_contract(contract)
