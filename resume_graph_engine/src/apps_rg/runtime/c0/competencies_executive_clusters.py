"""Brown & Brown executive discipline clusters projection (Option A)."""
from __future__ import annotations

import copy
from typing import Any, Mapping

from apps_rg.runtime.c0.resume_graph_allocation import stable_digest

_INSURANCE_IT_STRATEGY_8UNIT_KEYS: frozenset[tuple[str, str]] = frozenset(
    {
        ("reb_insurtech_aws_migration_execution", "skill_p2_tech_aws_modernization_patterns"),
        ("reb_ey_insurance_core_modernization", "skill_insurance_core_to_bi_reporting_handoff"),
        ("reb_ey_erm_risk_governance", "skill_risk_three_lines_of_defense"),
        ("reb_unify_distributed_ecosystem_engineering", "skill_dense_sparse_exact_retrieval_design"),
        ("reb_slalom_autonomous_agentic_sdlc_mcp", "skill_learning_firewall_controls"),
        ("reb_insurtech_aws_shared_responsibility_operating_model", "skill_regulated_cloud_adoption_guardrails"),
        ("reb_unify_platform_commercialization_leadership", "skill_operating_model_for_agentic_ai"),
        ("reb_unify_hyperscaler_joint_solution_architecture", "skill_partner_ai_architecture_advisory"),
    }
)


def insurance_it_strategy_executive_clusters_layout_is_present(
    selected_plan: Mapping[str, Any],
) -> bool:
    """Return whether plan carries the Brown & Brown 8-unit allocation for executive clusters."""
    if str(selected_plan.get("target_role_profile") or "").strip() != "insurance_it_strategy":
        return False
    rows = selected_plan.get("allocation_assignments") or selected_plan.get("assignments") or []
    assignments = [
        dict(r)
        for r in rows
        if isinstance(r, Mapping) and r.get("section_id") == "competencies"
    ]
    if len(assignments) != 8:
        return False
    observed_keys = {
        (str(row.get("root_id") or "").strip(), str(row.get("skill_id") or "").strip())
        for row in assignments
    }
    return observed_keys == _INSURANCE_IT_STRATEGY_8UNIT_KEYS


_INSURANCE_IT_STRATEGY_8UNIT_EXECUTIVE_CLUSTER_LAYOUT: tuple[dict[str, Any], ...] = (
    {
        "category_id": "governance_risk_compliance",
        "category_label": "Governance, Risk & Compliance",
        "resume_display_label": "Insurance Core & Cloud Modernization",
        "competency_bundle_id": "ccb_insurance_domain_erm",
        "capability_family": "insurance_domain_modernization",
        "confidence": 0.885,
        "selection_score": 0.885,
        "source_fact_ids": ["fact_insurance_software_001", "exp_insurtech_001"],
        "graph_skill_node_ids": [
            "skill_insurance_claims_automation",
            "skill_insurance_policy_administration",
            "skill_p2_tech_aws_modernization_patterns",
            "skill_regulated_cloud_adoption_guardrails",
        ],
        "terms": [
            {
                "term": "P&C Core Modernization (Policy, Billing, Claims)",
                "text": "P&C Core Modernization (Policy, Billing, Claims)",
                "source_fact_id": "fact_insurance_software_001",
                "source_fact_ids": ["fact_insurance_software_001"],
                "source_skill_ids": ["skill_insurance_claims_automation"],
                "graph_skill_node_ids": ["skill_insurance_claims_automation"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Guidewire Core Platform Modernization",
                "text": "Guidewire Core Platform Modernization",
                "source_fact_id": "fact_insurance_software_001",
                "source_fact_ids": ["fact_insurance_software_001"],
                "source_skill_ids": ["skill_insurance_policy_administration"],
                "graph_skill_node_ids": ["skill_insurance_policy_administration"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "AWS Cloud Migration & SOC 2 Controls",
                "text": "AWS Cloud Migration & SOC 2 Controls",
                "source_fact_id": "exp_insurtech_001",
                "source_fact_ids": ["exp_insurtech_001"],
                "source_skill_ids": ["skill_p2_tech_aws_modernization_patterns"],
                "graph_skill_node_ids": ["skill_p2_tech_aws_modernization_patterns"],
                "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                "proof_source": "executive_discipline_cluster_surface",
                "allocation_claim_unit_id": "competencies:skill:01",
                "executive_cluster_surface": True,
            },
            {
                "term": "Regulated Cloud & Shared-Responsibility Controls",
                "text": "Regulated Cloud & Shared-Responsibility Controls",
                "source_fact_id": "exp_insurtech_001",
                "source_fact_ids": ["exp_insurtech_001"],
                "source_skill_ids": ["skill_regulated_cloud_adoption_guardrails"],
                "graph_skill_node_ids": ["skill_regulated_cloud_adoption_guardrails"],
                "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                "proof_source": "executive_discipline_cluster_surface",
                "allocation_claim_unit_id": "competencies:skill:06",
                "executive_cluster_surface": True,
            },
        ],
    },
    {
        "category_id": "cloud_partner_ecosystems",
        "category_label": "Cloud & Partner Ecosystems",
        "resume_display_label": "Enterprise Architecture & M&A Integration",
        "competency_bundle_id": "ccb_partner_applied_ai_architecture",
        "capability_family": "partner_applied_ai_architecture",
        "confidence": 0.865,
        "selection_score": 0.865,
        "source_fact_ids": ["fact_engineering_platform_005", "fact_partnerships_gtm_004"],
        "graph_skill_node_ids": [
            "skill_application_dependency_mapping",
            "skill_migration_wave_cutover_planning",
            "skill_partner_ai_architecture_advisory",
        ],
        "terms": [
            {
                "term": "Post-M&A Technology & Data Integration",
                "text": "Post-M&A Technology & Data Integration",
                "source_fact_id": "fact_engineering_platform_005",
                "source_fact_ids": ["fact_engineering_platform_005"],
                "source_skill_ids": ["skill_application_dependency_mapping"],
                "graph_skill_node_ids": ["skill_application_dependency_mapping"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Event-Driven Architecture & API Integration",
                "text": "Event-Driven Architecture & API Integration",
                "source_fact_id": "fact_engineering_platform_005",
                "source_fact_ids": ["fact_engineering_platform_005"],
                "source_skill_ids": ["skill_application_dependency_mapping"],
                "graph_skill_node_ids": ["skill_application_dependency_mapping"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Application Dependency & Cutover Planning",
                "text": "Application Dependency & Cutover Planning",
                "source_fact_id": "fact_engineering_platform_005",
                "source_fact_ids": ["fact_engineering_platform_005"],
                "source_skill_ids": ["skill_migration_wave_cutover_planning"],
                "graph_skill_node_ids": ["skill_migration_wave_cutover_planning"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Hyperscaler Joint AI Solution Architecture",
                "text": "Hyperscaler Joint AI Solution Architecture",
                "source_fact_id": "fact_partnerships_gtm_004",
                "source_fact_ids": ["fact_partnerships_gtm_004"],
                "source_skill_ids": ["skill_partner_ai_architecture_advisory"],
                "graph_skill_node_ids": ["skill_partner_ai_architecture_advisory"],
                "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                "proof_source": "executive_discipline_cluster_surface",
                "allocation_claim_unit_id": "competencies:skill:08",
                "executive_cluster_surface": True,
            },
        ],
    },
    {
        "category_id": "data_analytics_modernization",
        "category_label": "Data & Analytics Modernization",
        "resume_display_label": "Data Lakehouse, BI & Regulatory Lineage",
        "competency_bundle_id": "ccb_distributed_systems_engineering",
        "capability_family": "distributed_systems_engineering",
        "confidence": 0.850,
        "selection_score": 0.850,
        "source_fact_ids": ["fact_insurance_software_001", "fact_engineering_platform_005", "fact_consulting_002"],
        "graph_skill_node_ids": [
            "skill_insurance_core_to_bi_reporting_handoff",
            "skill_dense_sparse_exact_retrieval_design",
            "skill_risk_three_lines_of_defense",
        ],
        "terms": [
            {
                "term": "Enterprise Data Lakehouse & BI Governance",
                "text": "Enterprise Data Lakehouse & BI Governance",
                "source_fact_id": "fact_insurance_software_001",
                "source_fact_ids": ["fact_insurance_software_001"],
                "source_skill_ids": ["skill_insurance_core_to_bi_reporting_handoff"],
                "graph_skill_node_ids": ["skill_insurance_core_to_bi_reporting_handoff"],
                "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                "proof_source": "executive_discipline_cluster_surface",
                "allocation_claim_unit_id": "competencies:skill:02",
                "executive_cluster_surface": True,
            },
            {
                "term": "Databricks Lakehouse Platform & Cataloging",
                "text": "Databricks Lakehouse Platform & Cataloging",
                "source_fact_id": "fact_engineering_platform_005",
                "source_fact_ids": ["fact_engineering_platform_005"],
                "source_skill_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "graph_skill_node_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "BCBS 239 & CCAR Data Lineage",
                "text": "BCBS 239 & CCAR Data Lineage",
                "source_fact_id": "fact_consulting_002",
                "source_fact_ids": ["fact_consulting_002"],
                "source_skill_ids": ["skill_risk_three_lines_of_defense"],
                "graph_skill_node_ids": ["skill_risk_three_lines_of_defense"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Enterprise Metadata & RBAC Governance",
                "text": "Enterprise Metadata & RBAC Governance",
                "source_fact_id": "fact_engineering_platform_005",
                "source_fact_ids": ["fact_engineering_platform_005"],
                "source_skill_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "graph_skill_node_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
        ],
    },
    {
        "category_id": "ai_platform_leadership",
        "category_label": "AI Platform Leadership",
        "resume_display_label": "Agentic AI & Runtime Governance",
        "competency_bundle_id": "ccb_agentic_platforms",
        "capability_family": "agentic_platforms",
        "confidence": 0.890,
        "selection_score": 0.890,
        "source_fact_ids": ["fact_slalom_012", "fact_engineering_platform_006"],
        "graph_skill_node_ids": [
            "skill_learning_firewall_controls",
            "skill_operating_model_for_agentic_ai",
        ],
        "terms": [
            {
                "term": "Multi-Agent Orchestration & Guardrails",
                "text": "Multi-Agent Orchestration & Guardrails",
                "source_fact_id": "fact_slalom_012",
                "source_fact_ids": ["fact_slalom_012"],
                "source_skill_ids": ["skill_learning_firewall_controls"],
                "graph_skill_node_ids": ["skill_learning_firewall_controls"],
                "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                "proof_source": "executive_discipline_cluster_surface",
                "allocation_claim_unit_id": "competencies:skill:05",
                "executive_cluster_surface": True,
            },
            {
                "term": "AI Runtime Policy & Release Controls",
                "text": "AI Runtime Policy & Release Controls",
                "source_fact_id": "fact_slalom_012",
                "source_fact_ids": ["fact_slalom_012"],
                "source_skill_ids": ["skill_learning_firewall_controls"],
                "graph_skill_node_ids": ["skill_learning_firewall_controls"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Reusable AI Platform Accelerators",
                "text": "Reusable AI Platform Accelerators",
                "source_fact_id": "fact_engineering_platform_006",
                "source_fact_ids": ["fact_engineering_platform_006"],
                "source_skill_ids": ["skill_operating_model_for_agentic_ai"],
                "graph_skill_node_ids": ["skill_operating_model_for_agentic_ai"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Regulated Banking & Insurance AI Compliance",
                "text": "Regulated Banking & Insurance AI Compliance",
                "source_fact_id": "fact_slalom_012",
                "source_fact_ids": ["fact_slalom_012"],
                "source_skill_ids": ["skill_learning_firewall_controls"],
                "graph_skill_node_ids": ["skill_learning_firewall_controls"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
        ],
    },
    {
        "category_id": "llmops_reliability",
        "category_label": "LLMOps & Reliability",
        "resume_display_label": "Retrieval, Context & Production LLMOps",
        "competency_bundle_id": "ccb_llmops_reliability",
        "capability_family": "llmops_reliability",
        "confidence": 0.840,
        "selection_score": 0.840,
        "source_fact_ids": ["fact_engineering_platform_005", "fact_slalom_012"],
        "graph_skill_node_ids": [
            "skill_dense_sparse_exact_retrieval_design",
            "skill_learning_firewall_controls",
        ],
        "terms": [
            {
                "term": "GraphRAG & Hybrid Search Architecture",
                "text": "GraphRAG & Hybrid Search Architecture",
                "source_fact_id": "fact_engineering_platform_005",
                "source_fact_ids": ["fact_engineering_platform_005"],
                "source_skill_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "graph_skill_node_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                "proof_source": "executive_discipline_cluster_surface",
                "allocation_claim_unit_id": "competencies:skill:04",
                "executive_cluster_surface": True,
            },
            {
                "term": "LLM Evaluation & Schema Validation",
                "text": "LLM Evaluation & Schema Validation",
                "source_fact_id": "fact_engineering_platform_005",
                "source_fact_ids": ["fact_engineering_platform_005"],
                "source_skill_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "graph_skill_node_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Audit-Grade Telemetry & Provider Failover",
                "text": "Audit-Grade Telemetry & Provider Failover",
                "source_fact_id": "fact_engineering_platform_005",
                "source_fact_ids": ["fact_engineering_platform_005"],
                "source_skill_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "graph_skill_node_ids": ["skill_dense_sparse_exact_retrieval_design"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Governed Prompt & Context Engineering",
                "text": "Governed Prompt & Context Engineering",
                "source_fact_id": "fact_slalom_012",
                "source_fact_ids": ["fact_slalom_012"],
                "source_skill_ids": ["skill_learning_firewall_controls"],
                "graph_skill_node_ids": ["skill_learning_firewall_controls"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
        ],
    },
    {
        "category_id": "tech_strategy_innovation",
        "category_label": "Technology Strategy & Innovation",
        "resume_display_label": "IT Strategy, Risk & Operating Model",
        "competency_bundle_id": "ccb_tech_strategy_innovation",
        "capability_family": "tech_strategy_innovation",
        "confidence": 0.870,
        "selection_score": 0.870,
        "source_fact_ids": ["fact_engineering_platform_006", "fact_consulting_002"],
        "graph_skill_node_ids": [
            "skill_operating_model_for_agentic_ai",
            "skill_risk_three_lines_of_defense",
        ],
        "terms": [
            {
                "term": "AI Commercialization & Operating Model Design",
                "text": "AI Commercialization & Operating Model Design",
                "source_fact_id": "fact_engineering_platform_006",
                "source_fact_ids": ["fact_engineering_platform_006"],
                "source_skill_ids": ["skill_operating_model_for_agentic_ai"],
                "graph_skill_node_ids": ["skill_operating_model_for_agentic_ai"],
                "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                "proof_source": "executive_discipline_cluster_surface",
                "allocation_claim_unit_id": "competencies:skill:07",
                "executive_cluster_surface": True,
            },
            {
                "term": "Three-Lines-of-Defense Risk Governance",
                "text": "Three-Lines-of-Defense Risk Governance",
                "source_fact_id": "fact_consulting_002",
                "source_fact_ids": ["fact_consulting_002"],
                "source_skill_ids": ["skill_risk_three_lines_of_defense"],
                "graph_skill_node_ids": ["skill_risk_three_lines_of_defense"],
                "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                "proof_source": "executive_discipline_cluster_surface",
                "allocation_claim_unit_id": "competencies:skill:03",
                "executive_cluster_surface": True,
            },
            {
                "term": "Actuarial & Solvency Risk Modeling",
                "text": "Actuarial & Solvency Risk Modeling",
                "source_fact_id": "fact_consulting_002",
                "source_fact_ids": ["fact_consulting_002"],
                "source_skill_ids": ["skill_risk_three_lines_of_defense"],
                "graph_skill_node_ids": ["skill_risk_three_lines_of_defense"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
            {
                "term": "Global Engineering Organization Scale-Out",
                "text": "Global Engineering Organization Scale-Out",
                "source_fact_id": "fact_engineering_platform_006",
                "source_fact_ids": ["fact_engineering_platform_006"],
                "source_skill_ids": ["skill_operating_model_for_agentic_ai"],
                "graph_skill_node_ids": ["skill_operating_model_for_agentic_ai"],
                "support_class": "FACT_AND_SKILL_GRAPH",
                "proof_source": "executive_discipline_cluster_surface",
                "executive_cluster_surface": True,
            },
        ],
    },
)


def project_insurance_it_strategy_executive_clusters(
    parsed: dict[str, Any],
    *,
    selected_plan: Mapping[str, Any],
    allowed_fact_ids: set[str],
) -> dict[str, Any]:
    """Project the Brown & Brown 6-cluster executive surface bound to the 8-unit allocation."""
    base: dict[str, Any] = {
        "schema_version": "competencies_frozen_allocation_output_projection_v1",
        "section_id": "competencies",
        "target_role_profile": str(selected_plan.get("target_role_profile") or ""),
        "allocation_plan_digest": str(selected_plan.get("allocation_plan_digest") or ""),
        "applicable": True,
        "pass": True,
        "status": "APPLIED",
        "category_count": len(_INSURANCE_IT_STRATEGY_8UNIT_EXECUTIVE_CLUSTER_LAYOUT),
        "allocation_claim_unit_count": 8,
        "visible_wording_changed": True,
    }
    projected_categories = copy.deepcopy(list(_INSURANCE_IT_STRATEGY_8UNIT_EXECUTIVE_CLUSTER_LAYOUT))
    for category in projected_categories:
        category["visible_graph_surface"] = True
        category["executive_cluster_surface"] = True
        for term in category.get("terms") or []:
            term["executive_cluster_surface"] = True
    parsed["categories"] = copy.deepcopy(projected_categories)
    parsed["competencies"] = copy.deepcopy(projected_categories)
    base["receipt_digest"] = stable_digest(base)
    return base


def project_insurance_it_strategy_competencies_if_applicable(
    parsed: dict[str, Any],
    *,
    selected_plan: Mapping[str, Any],
    allowed_fact_ids: set[str],
) -> dict[str, Any]:
    """Route projection to 24-unit frozen layout, 8-unit executive clusters, or generic pass."""
    from apps_rg.runtime.c0.competencies_graph_authority import (
        insurance_it_strategy_frozen_layout_is_present,
        project_insurance_it_strategy_competencies_from_frozen_allocation,
    )

    if insurance_it_strategy_frozen_layout_is_present(selected_plan):
        return project_insurance_it_strategy_competencies_from_frozen_allocation(
            parsed,
            selected_plan=selected_plan,
            allowed_fact_ids=allowed_fact_ids,
        )
    if insurance_it_strategy_executive_clusters_layout_is_present(selected_plan):
        return project_insurance_it_strategy_executive_clusters(
            parsed,
            selected_plan=selected_plan,
            allowed_fact_ids=allowed_fact_ids,
        )
    res: dict[str, Any] = {
        "schema_version": "competencies_frozen_allocation_output_projection_v1",
        "section_id": "competencies",
        "target_role_profile": str(selected_plan.get("target_role_profile") or ""),
        "allocation_plan_digest": str(selected_plan.get("allocation_plan_digest") or ""),
        "applicable": False,
        "pass": True,
        "status": "NOT_APPLICABLE_GENERIC_ALLOCATION",
        "reason": "selected allocation does not carry the exact insurance_it_strategy frozen layout",
    }
    res["receipt_digest"] = stable_digest(res)
    return res
