"""Wave 3 unit tests: mandate-adaptive two-page whole-resume solver, 3-era top sections, and commercial co-selection."""
from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.c0.c0_perf_sync_helpers import compute_candidate_alignment_and_independence
from apps_rg.runtime.c0.resume_graph_allocation import (
    ALL_CLAIM_BEARING_SECTIONS,
    build_whole_resume_graph_allocation,
    slice_section_plan_for_allocation,
    validate_resume_graph_allocation_plan,
)
from apps_rg.runtime.sections.role_narrative_v2.employer_specs import EMPLOYER_NARRATIVE_SPECS


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _bullet_counts(plan: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in plan["assignments"]:
        sec = str(row["section_id"])
        if sec.endswith("_bullets"):
            counts[sec] = counts.get(sec, 0) + 1
    return counts


def test_ethos_insurer_cto_allocates_three_eras_and_expands_actuarial_insurance_slots() -> None:
    repo = _repo_root()
    bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="Lead Engineer CTO",
        jd_text=(
            "Digital life insurer CTO leading underwriting modernization, actuarial reserving, "
            "policy administration, AWS cloud scale, and governed agentic AI platform engineering."
        ),
        briefing_text="Highlight FSA actuarial foundation alongside Track 3 agentic engineering and commercial impact.",
    )
    plan = bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(plan) == []
    assert plan["uniqueness_receipt"]["pass"] is True
    assert plan["mandate_route"]["selector_profile"] == "insurance_agentic_ai"
    assert "cert_fsa_001" in plan["credential_elevation_ids"]

    exec_lanes = {
        row["employer_lane"]
        for row in plan["assignments"]
        if row["section_id"] == "executive_summary"
    }
    assert {"slalom", "unify", "ibm"}.issubset(exec_lanes)
    assert exec_lanes & {"early_career", "ey", "insurtech"}

    headline_lanes = {
        row["employer_lane"]
        for row in plan["assignments"]
        if row["section_id"] == "headline"
    }
    assert headline_lanes & {"early_career", "ey", "insurtech"}

    counts = _bullet_counts(plan)
    assert counts["ey_bullets"] >= 2
    assert counts["early_career_bullets"] >= 2
    assert counts["insurtech_bullets"] >= 2
    total_bullets = sum(counts.values())
    assert 16 <= total_bullets <= 20

    # All 15 sections slice cleanly without error.
    for section_id in ALL_CLAIM_BEARING_SECTIONS:
        sliced = slice_section_plan_for_allocation(
            section_plan=bundle["section_plans"][section_id],
            allocation_plan=plan,
            final_evidence_contract=bundle["section_final_evidence_contracts"][section_id],
            section_id=section_id,
        )
        assert sliced["allocation_plan_digest"] == plan["allocation_plan_digest"]


def test_bank_caio_mrm_and_healthcare_payer_cdao_dynamic_sizing_and_credentials() -> None:
    repo = _repo_root()
    bank_bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="Chief AI Officer & Model Risk Governance",
        jd_text=(
            "Global bank Chief AI Officer owning SR 11-7 model risk management, BCBS 239 "
            "risk data aggregation, enterprise AI governance, and multi-agent control planes."
        ),
    )
    bank_plan = bank_bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(bank_plan) == []
    assert bank_plan["mandate_route"]["fde_context"] is False
    bank_counts = _bullet_counts(bank_plan)
    assert bank_counts["ey_bullets"] >= 2
    assert bank_counts["early_career_bullets"] >= 2
    bank_exec_lanes = {
        row["employer_lane"]
        for row in bank_plan["assignments"]
        if row["section_id"] == "executive_summary"
    }
    assert bank_exec_lanes & {"ey", "early_career"}

    payer_bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="Chief Data & AI Officer",
        jd_text=(
            "Healthcare payer CDAO leading biostatistics, claims analytics, medical loss ratio "
            "forecasting, actuarial reserving, and governed clinical AI platforms."
        ),
    )
    payer_plan = payer_bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(payer_plan) == []
    assert "edu_columbia_ms_biostat_001" in payer_plan["credential_elevation_ids"]
    payer_counts = _bullet_counts(payer_plan)
    assert payer_counts["early_career_bullets"] >= 2
    payer_early_roots = {
        row["root_id"]
        for row in payer_plan["assignments"]
        if row["section_id"] in {"early_career_bullets", "executive_summary", "headline"}
        and row["employer_lane"] == "early_career"
    }
    assert "reb_early_career_credentials_quantitative_pedigree" in payer_early_roots


def test_saas_svp_engineering_compresses_early_career_and_ey_while_keeping_three_eras() -> None:
    repo = _repo_root()
    saas_bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="SVP Engineering, Agentic AI Platforms",
        jd_text=(
            "SaaS SVP Engineering scaling multi-agent platform architecture, reliability, "
            "P&L commercial growth, and enterprise AI adoption."
        ),
    )
    plan = saas_bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(plan) == []
    counts = _bullet_counts(plan)
    assert counts["ey_bullets"] == 1
    assert counts["early_career_bullets"] == 1
    assert counts["slalom_bullets"] == 4
    assert counts["unify_bullets"] == 6
    assert plan["mandate_route"]["requires_commercial_pairing"] is True
    # Three-era top-section weaving remains present even on SaaS SVP Engineering.
    exec_lanes = {
        row["employer_lane"]
        for row in plan["assignments"]
        if row["section_id"] == "executive_summary"
    }
    assert len(exec_lanes) == 4
    assert exec_lanes & {"early_career", "ey", "insurtech"}


def test_proof_strength_no_longer_clamps_medium_085_to_high_10() -> None:
    proof_med, _, _ = compute_candidate_alignment_and_independence(
        root={"root_id": "reb_ey_erm_risk_governance", "authority_pass": True, "target_alignment_score": 1.0},
        skill={"candidate_id": "skill_test_med", "authority_pass": True, "proof_strength_raw": 0.85, "target_alignment_score": 1.0},
        metric=None,
        root_weight=1.0,
        citation_refs=["fact_1"],
        skill_sources=["src_1"],
    )
    proof_high, _, _ = compute_candidate_alignment_and_independence(
        root={"root_id": "reb_ey_erm_risk_governance", "authority_pass": True, "target_alignment_score": 1.0},
        skill={"candidate_id": "skill_test_high", "authority_pass": True, "proof_strength_raw": 1.2, "target_alignment_score": 1.0},
        metric=None,
        root_weight=1.0,
        citation_refs=["fact_1"],
        skill_sources=["src_1"],
    )
    assert proof_med == 0.85
    assert proof_high == 1.0
    assert proof_high > proof_med
    assert EMPLOYER_NARRATIVE_SPECS["ey_narrative"].zero_narrative_short_circuit is False
    assert "early_career_narrative" in EMPLOYER_NARRATIVE_SPECS
