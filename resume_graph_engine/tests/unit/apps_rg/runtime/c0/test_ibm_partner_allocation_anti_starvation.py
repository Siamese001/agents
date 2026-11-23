"""Unit tests verifying IBM–AWS Partner allocation anti-starvation and executive_summary coexistence."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.c0.resume_graph_allocation import (
    build_whole_resume_graph_allocation,
    slice_section_plan_for_allocation,
    validate_resume_graph_allocation_plan,
)
from apps_rg.runtime.sections.ibm_bullets.frozen_allocation import (
    _materialize_ibm_bullets_from_frozen_allocation,
)
from apps_rg.runtime.sections.ibm_role_episode_evidence import (
    format_ibm_role_episode_evidence_pack,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_anthropic_ai_partnerships_gtm_ibm_partner_anti_starvation() -> None:
    repo = _repo_root()
    jd_text = (
        "Manager, Applied AI Architecture & Partnerships - Anthropic. "
        "Lead technical partner architecture and co-sell execution across AWS, Google Cloud (Vertex AI / Model Armor), "
        "and strategic GSI/SI partners. Drive joint go-to-market solution blueprints, enterprise customer architecture "
        "workshops, production Claude deployment patterns, and partner-sourced revenue growth."
    )
    briefing_text = (
        "Target Role: Manager, Applied AI Architecture & Partnerships at Anthropic. "
        "Emphasize hyperscaler (AWS/GCP) and GSI/SI partner ecosystems, joint co-sell GTM execution, "
        "reusable enterprise architecture blueprints, and executive customer workshops."
    )
    bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="Manager, Applied AI Architecture & Partnerships",
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    plan = bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(plan) == []
    assert plan["uniqueness_receipt"]["pass"] is True

    by_slot = {row["claim_unit_id"]: row for row in plan["assignments"]}
    exec_ibm = by_slot["executive_summary:claim:03"]
    ibm_slots = [by_slot[f"ibm_bullets:bul_ibm_{i:03d}"] for i in range(1, 6)]
    ibm_roots = {row["root_id"] for row in ibm_slots}

    # Verify facet-level coexistence: executive_summary and ibm_bullets can both draw from
    # reb_ibm_aws_alliance_partner_cosell_gtm using strictly disjoint skill_id and metric_outcome_id.
    assert exec_ibm["root_id"] == "reb_ibm_aws_alliance_partner_cosell_gtm"
    assert "reb_ibm_aws_alliance_partner_cosell_gtm" in ibm_roots
    ibm_skills = {row["skill_id"] for row in ibm_slots}
    ibm_metrics = {row["metric_outcome_id"] for row in ibm_slots if row.get("metric_outcome_id")}
    assert exec_ibm["skill_id"] not in ibm_skills
    assert exec_ibm["metric_outcome_id"] not in ibm_metrics

    # At least 4 of 5 IBM bullets on a partnerships JD are Partner/GTM/Alliance bundles,
    # with zero generic DevSecOps or BI-only fallback drift.
    partner_gtm_roots = {
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "reb_ibm_offering_accelerator_management",
        "reb_ibm_presales_solution_engineering",
        "reb_ibm_customer_success_value_realization",
        "reb_ibm_revenue_sales_target_execution",
    }
    assert len(ibm_roots & partner_gtm_roots) >= 4
    assert "reb_ibm_devsecops_release_resilience" not in ibm_roots
    assert "reb_ibm_data_modeling_bi_decision_support" not in ibm_roots

    # Verify the rendered IBM bullets from frozen allocation surface explicit pre-GenAI
    # IBM–AWS Partner outcomes (20% joint revenue growth, $10M ARR, AWS Partner).
    ibm_sliced = slice_section_plan_for_allocation(
        section_plan=bundle["section_plans"]["ibm_bullets"],
        allocation_plan=plan,
        final_evidence_contract=bundle["section_final_evidence_contracts"]["ibm_bullets"],
        section_id="ibm_bullets",
    )
    parsed: dict = {"bullets": []}
    assert _materialize_ibm_bullets_from_frozen_allocation(parsed, selected_fact_plan=ibm_sliced) is True
    rendered = " ".join(str(b.get("bullet_text") or "") for b in parsed["bullets"])
    rendered_lower = rendered.lower()
    assert "aws partner" in rendered_lower or "ibm-aws" in rendered_lower
    assert "20%" in rendered
    assert "$10m" in rendered_lower
    for banned in ("genai", "gen ai", "llm", "graphrag", "mcp", "claude", "confluent kafka"):
        assert banned not in rendered_lower

    evidence_pack = format_ibm_role_episode_evidence_pack(
        {"selected_fact_plan": ibm_sliced},
        section_id="ibm_bullets",
    )
    assert "reb_ibm_aws_alliance_partner_cosell_gtm" in evidence_pack
