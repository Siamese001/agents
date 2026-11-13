"""Tests for Brown & Brown executive discipline clusters projection (Option A)."""
from __future__ import annotations

from typing import Any

from apps_rg.runtime.c0.competencies_executive_clusters import (
    _INSURANCE_IT_STRATEGY_8UNIT_EXECUTIVE_CLUSTER_LAYOUT,
    insurance_it_strategy_executive_clusters_layout_is_present,
    project_insurance_it_strategy_competencies_if_applicable,
    project_insurance_it_strategy_executive_clusters,
)
from apps_rg.runtime.c0.competencies_graph_authority import (
    reconcile_competencies_allocation_claim_units,
)
from apps_rg.runtime.sections.competencies_rigor import (
    check_competencies_approved_category_labels,
    check_competencies_keyword_repetition_limit,
    check_competencies_no_fragment_or_one_word_terms,
    check_competencies_visible_terms_svp_agentic_richness,
)
from apps_rg.runtime.validators.competencies_quality_x2 import (
    check_competencies_capability_family_coverage,
    check_per_category_confidence_nonconstant,
)


def _eight_unit_plan() -> dict[str, Any]:
    assignments = [
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:01",
            "root_id": "reb_insurtech_aws_migration_execution",
            "skill_id": "skill_p2_tech_aws_modernization_patterns",
            "fact_id": "exp_insurtech_001",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:02",
            "root_id": "reb_ey_insurance_core_modernization",
            "skill_id": "skill_insurance_core_to_bi_reporting_handoff",
            "fact_id": "fact_insurance_software_001",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:03",
            "root_id": "reb_ey_erm_risk_governance",
            "skill_id": "skill_risk_three_lines_of_defense",
            "fact_id": "fact_consulting_002",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:04",
            "root_id": "reb_unify_distributed_ecosystem_engineering",
            "skill_id": "skill_dense_sparse_exact_retrieval_design",
            "fact_id": "fact_engineering_platform_005",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:05",
            "root_id": "reb_slalom_autonomous_agentic_sdlc_mcp",
            "skill_id": "skill_learning_firewall_controls",
            "fact_id": "fact_slalom_012",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:06",
            "root_id": "reb_insurtech_aws_shared_responsibility_operating_model",
            "skill_id": "skill_regulated_cloud_adoption_guardrails",
            "fact_id": "exp_insurtech_001",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:07",
            "root_id": "reb_unify_platform_commercialization_leadership",
            "skill_id": "skill_operating_model_for_agentic_ai",
            "fact_id": "fact_engineering_platform_006",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:08",
            "root_id": "reb_unify_hyperscaler_joint_solution_architecture",
            "skill_id": "skill_partner_ai_architecture_advisory",
            "fact_id": "fact_partnerships_gtm_004",
        },
    ]
    return {
        "target_role_profile": "insurance_it_strategy",
        "allocation_plan_digest": "test_exec_cluster_digest",
        "allocation_assignments": assignments,
        "facts": [
            {
                "fact_id": a["fact_id"],
                "role_episode_bundle_id": a["root_id"],
                "graph_skill_node_ids": [a["skill_id"]],
            }
            for a in assignments
        ],
    }


def test_insurance_it_strategy_executive_clusters_layout_detection() -> None:
    plan = _eight_unit_plan()
    assert insurance_it_strategy_executive_clusters_layout_is_present(plan) is True

    bad_profile = dict(plan, target_role_profile="enterprise_cloud_ai")
    assert insurance_it_strategy_executive_clusters_layout_is_present(bad_profile) is False

    wrong_count = dict(plan, allocation_assignments=plan["allocation_assignments"][:7])
    assert insurance_it_strategy_executive_clusters_layout_is_present(wrong_count) is False


def test_insurance_it_strategy_executive_clusters_projection_and_reconciliation() -> None:
    plan = _eight_unit_plan()
    parsed: dict[str, Any] = {"competencies": [], "categories": [], "claim_ledger": []}
    allowed = {
        "exp_insurtech_001",
        "fact_consulting_002",
        "fact_engineering_platform_005",
        "fact_engineering_platform_006",
        "fact_insurance_software_001",
        "fact_partnerships_gtm_004",
        "fact_slalom_012",
    }
    receipt = project_insurance_it_strategy_executive_clusters(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=allowed,
    )
    assert receipt["applicable"] is True
    assert receipt["pass"] is True
    assert receipt["status"] == "APPLIED"
    assert receipt["category_count"] == 6
    assert receipt["allocation_claim_unit_count"] == 8

    reconciliation = reconcile_competencies_allocation_claim_units(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=allowed,
    )
    assert reconciliation["pass"] is True
    assert reconciliation["matched_claim_unit_count"] == 8
    assert reconciliation["unmatched_claim_unit_ids"] == []

    categories = parsed["categories"]
    assert check_competencies_visible_terms_svp_agentic_richness(categories) == (True, None)
    assert check_competencies_keyword_repetition_limit(categories) == (True, None)
    assert check_competencies_no_fragment_or_one_word_terms(categories) == (True, None)
    assert check_competencies_approved_category_labels(categories) == (True, None)
    assert check_per_category_confidence_nonconstant(categories).passed is True
    assert check_competencies_capability_family_coverage(categories).passed is True

    all_terms = [
        str(t.get("text") or t.get("term"))
        for cat in categories
        for t in cat.get("terms") or []
    ]
    assert len(all_terms) == 24
    total_words = sum(len(t.split()) for t in all_terms)
    assert total_words <= 125


def test_router_helper_selects_executive_clusters() -> None:
    plan = _eight_unit_plan()
    parsed: dict[str, Any] = {"competencies": [], "categories": [], "claim_ledger": []}
    allowed = {"exp_insurtech_001", "fact_consulting_002", "fact_engineering_platform_005", "fact_engineering_platform_006", "fact_insurance_software_001", "fact_partnerships_gtm_004", "fact_slalom_012"}
    receipt = project_insurance_it_strategy_competencies_if_applicable(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=allowed,
    )
    assert receipt["applicable"] is True
    assert receipt["status"] == "APPLIED"
    assert len(parsed["categories"]) == 6
