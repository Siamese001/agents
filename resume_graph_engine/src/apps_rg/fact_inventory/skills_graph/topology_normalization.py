"""Topology ID normalization and polymorphic edge splitting (Wave 3)."""
from __future__ import annotations

from typing import Any

EMPLOYMENT_ALIAS_MAP: dict[str, str] = {
    "exp_ey_001": "employment_exp_ey_001",
    "exp_insurtech_001": "employment_exp_insurtech_001",
    "exp_unify_001": "employment_exp_unify_001",
    "exp_ibm_001": "employment_exp_ibm_001",
    "exp_early_career_001": "employment_exp_early_career_001",
    "exp_slalom_001": "employment_exp_slalom_001",
}

PILLAR_ALIAS_MAP: dict[str, str] = {
    "pillar_agentic_runtime_governance": "pillar_agentic_ai_platforms",
}

CANONICAL_EMPLOYMENT_EPOCHS: dict[str, str] = {
    "employment_exp_early_career_001": "epoch_actuarial_financial_engineering",
    "employment_exp_ey_001": "epoch_enterprise_risk_governance",
    "employment_exp_insurtech_001": "epoch_cloud_data_platform_engineering",
    "employment_exp_ibm_001": "epoch_partner_gtm_revenue_leadership",
    "employment_exp_unify_001": "epoch_agentic_ai_runtime_architecture",
    "employment_exp_slalom_001": "epoch_ai_platform_commercialization",
}

EMPLOYMENT_DATES_AND_TITLES: dict[str, dict[str, Any]] = {
    "employment_exp_early_career_001": {
        "title": "Actuarial Consultant and Quantitative Roles",
        "employer": "Early Career Roles",
        "start_date": "2002-10",
        "end_date": "2009-09",
        "is_current": 0,
        "operating_context": "Financial and actuarial quantitative consulting roles",
    },
    "employment_exp_ey_001": {
        "title": "Principal",
        "employer": "Ernst & Young",
        "start_date": "2009-10",
        "end_date": "2014-03",
        "is_current": 0,
        "operating_context": "Regulatory analytics modernization program for global banks",
    },
    "employment_exp_insurtech_001": {
        "title": "Chief Technology Officer",
        "employer": "InsurTech Cloud Solutions",
        "start_date": "2014-04",
        "end_date": "2017-03",
        "is_current": 0,
        "operating_context": "Cloud-native engineering firm modernizing legacy insurance technology stacks",
    },
    "employment_exp_ibm_001": {
        "title": "Partner",
        "employer": "IBM",
        "start_date": "2017-04",
        "end_date": "2022-10",
        "is_current": 0,
        "operating_context": "Cloud and AI transformation portfolio for Fortune 500 financial institutions",
    },
    "employment_exp_unify_001": {
        "title": "SVP Engineering, Agentic AI Platforms",
        "employer": "Unify Consulting",
        "start_date": "2023-02",
        "end_date": "2026-06",
        "is_current": 0,
        "operating_context": "Generative AI Solution Accelerator and multi-agent production platforms",
    },
    "employment_exp_slalom_001": {
        "title": "Senior Director",
        "employer": "Slalom",
        "start_date": "2026-06",
        "end_date": "",
        "is_current": 1,
        "operating_context": "Next-generation agentic AI client delivery and systems architecture practice",
    },
}

FACT_TO_EMPLOYMENT_MAP: dict[str, str] = {
    # Early Career
    "fact_certs_001": "employment_exp_early_career_001",
    "fact_insurance_liabilities_001": "employment_exp_early_career_001",
    "fact_quant_act_001": "employment_exp_early_career_001",
    "fact_quant_act_002": "employment_exp_early_career_001",
    "fact_quant_act_003": "employment_exp_early_career_001",
    "fact_quant_hpc_003": "employment_exp_early_career_001",
    # Ernst & Young
    "fact_bcbs239_001": "employment_exp_ey_001",
    "fact_consulting_001": "employment_exp_ey_001",
    "fact_consulting_002": "employment_exp_ey_001",
    "fact_credit_001": "employment_exp_ey_001",
    "fact_ey_guidewire_001": "employment_exp_ey_001",
    "fact_governance_004": "employment_exp_ey_001",
    "fact_insurance_software_001": "employment_exp_ey_001",
    "fact_solvency_001": "employment_exp_ey_001",
    "fact_three_lines_001": "employment_exp_ey_001",
    # InsurTech Cloud Solutions
    "fact_insurtech_aws_001": "employment_exp_insurtech_001",
    # IBM
    "fact_data_analytics_001": "employment_exp_ibm_001",
    "fact_data_analytics_003": "employment_exp_ibm_001",
    "fact_governance_003": "employment_exp_ibm_001",
    "fact_partnerships_gtm_002": "employment_exp_ibm_001",
    "fact_quant_hpc_001": "employment_exp_ibm_001",
    "fact_revenue_ops_001": "employment_exp_ibm_001",
    "fact_revenue_ops_002": "employment_exp_ibm_001",
    "fact_revenue_ops_004": "employment_exp_ibm_001",
    "fact_revenue_ops_005": "employment_exp_ibm_001",
    "fact_sales_accounts_002": "employment_exp_ibm_001",
    "fact_sales_accounts_003": "employment_exp_ibm_001",
    # Unify Consulting
    "fact_engineering_platform_001": "employment_exp_unify_001",
    "fact_engineering_platform_002": "employment_exp_unify_001",
    "fact_engineering_platform_003": "employment_exp_unify_001",
    "fact_engineering_platform_004": "employment_exp_unify_001",
    "fact_engineering_platform_005": "employment_exp_unify_001",
    "fact_engineering_platform_006": "employment_exp_unify_001",
    "fact_exec_001": "employment_exp_unify_001",
    "fact_exec_002": "employment_exp_unify_001",
    "fact_governance_001": "employment_exp_unify_001",
    "fact_governance_002": "employment_exp_unify_001",
    "fact_governance_005": "employment_exp_unify_001",
    "fact_partnerships_gtm_001": "employment_exp_unify_001",
    "fact_partnerships_gtm_003": "employment_exp_unify_001",
    "fact_partnerships_gtm_004": "employment_exp_unify_001",
    "fact_partnerships_gtm_005": "employment_exp_unify_001",
    "fact_quant_hpc_002": "employment_exp_unify_001",
    "fact_quant_hpc_004": "employment_exp_unify_001",
    "fact_rag_insurance_001": "employment_exp_unify_001",
    "fact_revenue_ops_003": "employment_exp_unify_001",
    "fact_sales_accounts_001": "employment_exp_unify_001",
    "fact_solutions_001": "employment_exp_unify_001",
    "fact_solutions_002": "employment_exp_unify_001",
    # Slalom
    "fact_slalom_001": "employment_exp_slalom_001",
    "fact_slalom_002": "employment_exp_slalom_001",
    "fact_slalom_003": "employment_exp_slalom_001",
    "fact_slalom_004": "employment_exp_slalom_001",
    "fact_slalom_005": "employment_exp_slalom_001",
    "fact_slalom_006": "employment_exp_slalom_001",
}


def normalize_employment_id(raw_id: str) -> str:
    """Map legacy stub duplicate employment IDs to canonical employment_exp_* IDs."""
    clean = str(raw_id or "").strip()
    return EMPLOYMENT_ALIAS_MAP.get(clean, clean)


def normalize_section_id(raw_id: str) -> str:
    """Normalize section IDs to canonical section_* format."""
    clean = str(raw_id or "").strip()
    if clean == "*":
        return "*"
    clean = clean.removeprefix("section:").removeprefix("section_")
    return f"section_{clean}"


def split_polymorphic_edge(edge: dict[str, Any], src_type: str, tgt_type: str) -> str:
    """Return the exact, non-polymorphic edge_type based on endpoint types."""
    et = str(edge.get("edge_type") or "").strip()

    if et == "skill_supported_by_fact":
        if tgt_type == "fact":
            return "skill_supported_by_fact"
        if tgt_type == "locked_bullet":
            return "skill_supported_by_locked_bullet"
        if tgt_type == "employment":
            return "skill_supported_by_employment"
        if tgt_type == "certification":
            return "skill_supported_by_certification"
        return "skill_supported_by_fact"

    if et == "fact_has_metric_outcome":
        if src_type == "locked_bullet":
            return "locked_bullet_has_metric_outcome"
        return "fact_has_metric_outcome"

    if et == "capability_domain_contains_skill" and src_type == "pillar":
        return "pillar_contains_skill"

    if et == "srfs_requires_fact_id_only":
        if src_type == "policy_rule":
            return "srfs_rule_requires_fact_id_only"
        return "srfs_policy_requires_fact_id_only"

    return et


__all__ = [
    "EMPLOYMENT_ALIAS_MAP",
    "PILLAR_ALIAS_MAP",
    "CANONICAL_EMPLOYMENT_EPOCHS",
    "EMPLOYMENT_DATES_AND_TITLES",
    "FACT_TO_EMPLOYMENT_MAP",
    "normalize_employment_id",
    "normalize_section_id",
    "split_polymorphic_edge",
]
