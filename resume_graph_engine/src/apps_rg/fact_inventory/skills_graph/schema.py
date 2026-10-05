"""Database DDL statements and registered graph types / epochs."""
from __future__ import annotations

from .schema_ddl import DDL_STATEMENTS

CANONICAL_NODE_TYPES = frozenset(
    {
        "pillar",
        "skill",
        "fact",
        "role_family",
        "career_track",
        "career_epoch",
        "capability_domain",
        "employment",
        "locked_bullet",
        "certification",
        "section",
        "concept",
        "repo_evidence",
        "policy",
        "policy_rule",
        "graph_ref",
        "metric",
        "metric_bucket",
        # W2.0 (typed-edge-role-facet-guardrails-a6f3d2): first-class metric_outcome
        # nodes materialized from role_episode_bundle metric_outcome_nodes dicts.
        "metric_outcome",
        # W3: first-class engagement nodes materialized from role_episode_bundle files.
        "engagement",
    }
)

RAW_TO_CANONICAL_NODE_TYPE: dict[str, str] = {
    "atomic_proof_fact": "fact",
    "bullet_fact": "locked_bullet",
    "capability_domain": "capability_domain",
    "career_epoch": "career_epoch",
    "career_track": "career_track",
    "certification_evidence": "certification",
    "domain_pillar": "pillar",
    "employment": "employment",
    "engagement": "engagement",
    "experience_evidence": "employment",
    "external_claim_policy": "policy",
    "identity_north_star": "role_family",
    "metric": "metric",
    "metric_bucket": "metric_bucket",
    "policy": "policy",
    "policy_rule": "policy_rule",
    "repository_evidence": "repo_evidence",
    "resume_section_projection": "section",
    "skill": "skill",
    "skill_row": "skill",
    "source_concept": "concept",
    "targeting_input": "graph_ref",
}

CANONICAL_CAREER_EPOCHS: tuple[str, ...] = (
    "epoch_actuarial_financial_engineering",
    "epoch_enterprise_risk_governance",
    "epoch_cloud_data_platform_engineering",
    "epoch_partner_gtm_revenue_leadership",
    "epoch_agentic_ai_runtime_architecture",
    "epoch_ai_platform_commercialization",
)

EPOCH_ORDINAL: dict[str, int] = {
    "epoch_actuarial_financial_engineering": 1,
    "epoch_enterprise_risk_governance": 2,
    "epoch_cloud_data_platform_engineering": 3,
    "epoch_partner_gtm_revenue_leadership": 4,
    "epoch_agentic_ai_runtime_architecture": 5,
    "epoch_ai_platform_commercialization": 6,
}

ORDINAL_TO_EPOCH: dict[int, str] = {v: k for k, v in EPOCH_ORDINAL.items()}

EPOCH_LABELS: dict[str, str] = {
    "epoch_actuarial_financial_engineering": "Actuarial & Financial Engineering",
    "epoch_enterprise_risk_governance": "Enterprise Risk & Governance",
    "epoch_cloud_data_platform_engineering": "Cloud & Data Platform Engineering",
    "epoch_partner_gtm_revenue_leadership": "Partner GTM & Revenue Leadership",
    "epoch_agentic_ai_runtime_architecture": "Agentic AI Runtime Architecture",
    "epoch_ai_platform_commercialization": "AI Platform Commercialization",
}

P6_SKILLS: frozenset[str] = frozenset(
    {
        "skill_agentic_platform_productization",
        "skill_reusable_ai_ip_design",
        "skill_app_specific_runtime_overlay_design",
        "skill_enterprise_workflow_adoption",
        "skill_operating_model_for_agentic_ai",
        "skill_ai_platform_commercialization",
    }
)

LEGACY_SKILL_EPOCHS: dict[str, str] = {
    "skill_meddpicc_sales_qualification": "epoch_partner_gtm_revenue_leadership",
    "skill_cpq_deal_velocity_automation": "epoch_ai_platform_commercialization",
    "skill_soc2_zero_trust_security": "epoch_enterprise_risk_governance",
    "skill_saas_arr_ltv_cac_metrics": "epoch_ai_platform_commercialization",
    "skill_confluent_streaming_platforms": "epoch_cloud_data_platform_engineering",
    "skill_watson_studio_fraud_aml": "epoch_cloud_data_platform_engineering",
    "skill_nps_customer_health_scoring": "epoch_ai_platform_commercialization",
    "skill_credit_adjudication_default_risk": "epoch_enterprise_risk_governance",
}

EMPLOYMENT_PHASES: dict[str, tuple[int, int]] = {
    "employment_exp_early_career_001": (1, 1),
    "employment_exp_ey_001": (2, 2),
    "employment_exp_insurtech_001": (3, 3),
    "employment_exp_ibm_001": (3, 4),
    "employment_exp_unify_001": (5, 6),
}

__all__ = [
    "CANONICAL_NODE_TYPES",
    "RAW_TO_CANONICAL_NODE_TYPE",
    "CANONICAL_CAREER_EPOCHS",
    "EPOCH_ORDINAL",
    "ORDINAL_TO_EPOCH",
    "EPOCH_LABELS",
    "P6_SKILLS",
    "LEGACY_SKILL_EPOCHS",
    "EMPLOYMENT_PHASES",
    "DDL_STATEMENTS",
]
