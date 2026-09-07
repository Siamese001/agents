"""Deterministic competencies allocation-to-claim authority reconciliation."""
from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Mapping

from apps_rg.runtime.c0.c03_resume_graph_contracts import stable_digest

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_IDENTITY_NOISE = frozenset(
    {
        "skill",
        "p2",
        "sr",
        "w12",
        "tech",
        "the",
        "and",
        "for",
        "from",
        "with",
        "across",
    }
)
_ROLE_AXIS_SIGNALS: Mapping[str, tuple[str, ...]] = {
    "partner_motions": ("partner", "partnership", "alliance"),
    "co_sell": ("co_sell", "cosell", "co-selling", "co_selling"),
    "hyperscaler_alliance": ("hyperscaler", "aws", "cloud_vendor", "cloud-vendor"),
    "joint_solution": ("joint_solution", "joint solution", "partner_led_ai_solutions"),
    "gtm_enablement": ("enablement", "gtm", "technical_close", "go-to-market"),
}

# The allocation is intentionally more granular than the eight résumé
# categories.  When a selected graph skill has no matching visible term, these
# are the compact résumé surfaces for the small set of graph paths whose
# source labels are themselves too terse to meet the final competency-shape
# contract.  Each phrase is composed solely from the selected skill path and
# its root's graph-authored claim/domain/source text; `_composition_is_bound`
# below proves that before it can be emitted.  This is an output projection,
# not a new graph fact or an inferred competency.
_ALLOCATION_VISIBLE_SURFACE_COMPOSITIONS: Mapping[tuple[str, str], str] = {
    (
        "reb_slalom_ecosystem_accelerators",
        "skill_partner_aws_ecosystem",
    ): "Enterprise hyperscaler partner AWS accelerator ecosystem",
    (
        "reb_ey_ccar_capital_liquidity_stress_testing",
        "skill_capital_capital_modeling",
    ): "Regulated capital liquidity stress testing validation",
    (
        "reb_ey_capital_optimization_solvency",
        "skill_risk_greek_stress_testing",
    ): "Insurance derivatives Greek stress testing validation",
    (
        "reb_unify_agentic_platform_architecture",
        "skill_unify_agentic_l0_route_policy_dispatch",
    ): "Agentic platform route-policy dispatch architecture",
    (
        "reb_unify_agentic_platform_architecture",
        "skill_unify_agentic_graphrag_context_pack_grounding",
    ): "GraphRAG context pack grounding for governed execution",
    (
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_partner_cloud_vendor_joint_gtm",
    ): "Partner AI solution architecture and co-sell execution",
    (
        "reb_ibm_customer_success_value_realization",
        "skill_partner_customer_deal_support",
    ): "Partner value-realization operating cadence and deal support",
    (
        "reb_ibm_customer_success_value_realization",
        "skill_p2_gtm_presales_delivery_handoff",
    ): "Presales-to-delivery customer success operating handoff cadence",
    (
        "reb_insurtech_regulated_aws_control_implementation",
        "skill_pii_encryption_for_insurance_data",
    ): "PII encryption controls for regulated data",
    (
        "reb_insurtech_regulated_aws_control_implementation",
        "skill_aws_iam_kms_cloudtrail_controls",
    ): "IAM KMS CloudTrail controls for insurers",
    (
        "reb_insurtech_regulated_aws_control_implementation",
        "skill_soc2_zero_trust_security",
    ): "SOC2 zero-trust security controls for compliance",
    (
        "reb_insurtech_regulated_aws_control_implementation",
        "skill_sr_insurtech_regulated_insurer_controls",
    ): "SOC2 control frameworks for regulated insurers",
    (
        "reb_insurtech_regulated_aws_control_implementation",
        "skill_soc2_control_mapping_for_aws",
    ): "SOC2 AWS control mapping for insurers",
    (
        "reb_insurtech_aws_guidewire_core_modernization",
        "skill_insurance_core_data_model_mapping",
    ): "Insurance core data mapping for workflows",
    (
        "reb_insurtech_aws_migration_execution",
        "skill_sr_insurtech_legacy_cloud_modernization",
    ): "AWS-based policy administration architecture execution",
    (
        "reb_insurtech_aws_migration_execution",
        "skill_p2_tech_aws_modernization_patterns",
    ): "AWS migration patterns for legacy platforms",
    (
        "reb_insurtech_aws_migration_execution",
        "skill_aws_migration_readiness_assessment",
    ): "Readiness assessments for legacy platforms",
    (
        "reb_insurtech_aws_migration_execution",
        "skill_application_dependency_mapping",
    ): "Application dependency mapping for migration execution",
    (
        "reb_insurtech_aws_migration_execution",
        "skill_migration_wave_cutover_planning",
    ): "Migration wave cutover execution planning",
    (
        "reb_ey_insurance_core_modernization",
        "skill_insurance_claims_automation",
    ): "Insurance claims workflow automation integration",
    (
        "reb_ey_insurance_core_modernization",
        "skill_insurance_core_to_bi_reporting_handoff",
    ): "Core reporting workflow integration handoff",
    (
        "reb_ey_insurance_core_modernization",
        "skill_insurance_guidewire",
    ): "Guidewire platform workflow modernization integration",
    (
        "reb_ey_erm_risk_governance",
        "skill_credit_adjudication_default_risk",
    ): "AI credit adjudication for enterprise risk",
    (
        "reb_ey_erm_risk_governance",
        "skill_risk_three_lines_of_defense",
    ): "Enterprise three-lines-of-defense risk operating model",
    (
        "reb_ey_erm_risk_governance",
        "skill_risk_model_risk",
    ): "Model explainability for enterprise risk operating model",
    (
        "reb_ibm_offering_accelerator_management",
        "skill_sr_w12_industry_reference_architecture",
    ): "Industry reference architecture patterns for regulated modernization",
    (
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_partner_joint_solution_development",
    ): "AWS alliance modernization co-sell and joint development",
    (
        "reb_ibm_offering_accelerator_management",
        "skill_p2_tech_reusable_accelerators",
    ): "Reusable agentic platform service accelerators",
    (
        "reb_ibm_offering_accelerator_management",
        "skill_p2_tech_ibm_cloud_portfolio_anchor",
    ): "Cloud transformation portfolio architecture ownership",
    (
        "reb_ibm_devsecops_release_resilience",
        "skill_ibm_automated_release_pipelines",
    ): "Regulated DevSecOps release governance pipelines",
    (
        "reb_ibm_presales_solution_engineering",
        "skill_partner_pre_sales",
    ): "Buyer-specific solution mapping for enterprise pursuits",
    (
        "reb_ibm_revenue_sales_target_execution",
        "skill_partner_enterprise_negotiations",
    ): "Enterprise pursuit execution across portfolio expansion motions",
    (
        "reb_unify_partner_channel_cosell",
        "skill_partner_partner_led_ai_solutions",
    ): "AI co-sell bundling with strategic partners",
    (
        "reb_unify_partner_channel_cosell",
        "skill_partner_cloud_vendor_joint_gtm",
    ): "Vendor joint AI solution roadmaps for partners",
    (
        "reb_unify_partner_channel_cosell",
        "skill_partner_partner_revenue_3m",
    ): "Partner-derived AI revenue through alliance channels",
    (
        "reb_unify_partner_channel_cosell",
        "skill_partner_gtm_enablement",
    ): "AI GTM enablement for alliance channels",
    (
        "reb_unify_partner_channel_cosell",
        "skill_partner_partner_motions",
    ): "Global AI channel program inception motions",
    (
        "reb_unify_distributed_ecosystem_engineering",
        "skill_sr_cloud_data_platform_engineering",
    ): "Cloud-native architectures for financial-services clients",
    (
        "reb_unify_distributed_ecosystem_engineering",
        "skill_dense_sparse_exact_retrieval_design",
    ): "Dense-sparse retrieval execution for evidence grounding",
    (
        "reb_unify_distributed_ecosystem_engineering",
        "skill_sr_w12_databricks_lakehouse_fundamentals",
    ): "Databricks lakehouse architectures for AWS engineering",
    (
        "reb_unify_distributed_ecosystem_engineering",
        "skill_runtime_resilience_controls",
    ): "Fail-closed provider resilience control gate",
    (
        "reb_unify_distributed_ecosystem_engineering",
        "skill_provider_and_egress_governance",
    ): "Provider egress governance for generation paths",
    (
        "reb_unify_agentic_platform_architecture",
        "skill_unify_agentic_human_override_escalation_paths",
    ): "Governed human override and escalation paths",
    (
        "reb_unify_agentic_platform_architecture",
        "skill_unify_agentic_runtime_proof_bundle_lineage",
    ): "Runtime proof-bundle lineage for platforms",
    (
        "reb_unify_agentic_platform_architecture",
        "skill_unify_agentic_multi_agent_orchestration_contracts",
    ): "Multi-agent orchestration contracts for governed execution",
    (
        "reb_unify_agentic_platform_architecture",
        "skill_unify_agentic_replay_key_audit_manifest_design",
    ): "Agent replay audit architectures for reviewable runs",
    (
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_partner_hyperscaler_cosell",
    ): "Financial-services hyperscaler alliance co-sell execution",
    (
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_partner_ibm_aws_alliance_joint_revenue",
    ): "AI sales frameworks for AWS revenue motions",
    (
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_partner_alliance_gtm_execution",
    ): "AWS alliance joint architecture leadership",
    (
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_sr_w12_hyperscaler_alliance_co_sell",
    ): "Multi-year hyperscaler co-sell motions for AI growth",
    (
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_partner_joint_solution_development",
    ): "AI analytics framework co-development for partners",
    (
        "reb_ibm_offering_accelerator_management",
        "skill_p2_tech_demoable_accelerator",
    ): "Production-grade accelerator commercialization for client platforms",
    (
        "reb_ibm_offering_accelerator_management",
        "skill_p2_tech_ibm_cloud_portfolio_anchor",
    ): "Cloud transformation portfolio architecture ownership",
    (
        "reb_ibm_offering_accelerator_management",
        "skill_sr_w12_industry_reference_architecture",
    ): "Industry modernization reference architecture patterns",
    (
        "reb_ibm_aws_modernization_architecture",
        "skill_p2_tech_aws_modernization_patterns",
    ): "AWS migration and modernization for regulated workloads",
    (
        "reb_ibm_aws_modernization_architecture",
        "skill_p2_tech_reference_architecture",
    ): "Regulated financial-services cloud modernization patterns",
    (
        "reb_ibm_aws_modernization_architecture",
        "skill_sr_microservices_integration_platform",
    ): "Microservices integration for regulated systems",
    (
        "reb_ey_insurance_core_modernization",
        "skill_insurance_core_to_bi_reporting_handoff",
    ): "Insurance core reporting integration and BI workflows",
}

# A joint alliance/co-sell capability is commercial evidence, even when its
# graph root is also eligible for the applied-AI architecture category. Keep
# the visible term in the existing commercialization category so the category
# label and its terms tell one coherent résumé story. This affects only the
# selected graph path below; it does not create a new claim or alter graph
# selection.
_ALLOCATION_SURFACE_CATEGORY_OVERRIDES: Mapping[tuple[str, str], str] = {
    **{
        ("reb_unify_partner_channel_cosell", skill_id): "Cloud & Partner Ecosystems"
        for skill_id in (
            "skill_partner_cloud_vendor_joint_gtm",
            "skill_partner_gtm_enablement",
        )
    },
    **{
        ("reb_unify_partner_channel_cosell", skill_id): "Commercial & Operating Impact"
        for skill_id in (
            "skill_partner_partner_revenue_3m",
            "skill_partner_partner_motions",
            "skill_partner_partner_led_ai_solutions",
        )
    },
    **{
        ("reb_ibm_aws_alliance_partner_cosell_gtm", skill_id): "Commercial & Operating Impact"
        for skill_id in (
            "skill_partner_hyperscaler_cosell",
            "skill_partner_ibm_aws_alliance_joint_revenue",
            "skill_sr_w12_hyperscaler_alliance_co_sell",
        )
    },
    (
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_partner_alliance_gtm_execution",
    ): "Cloud & Partner Ecosystems",
    ("reb_ibm_aws_alliance_partner_cosell_gtm", "skill_partner_joint_solution_development"): "Cloud & Partner Ecosystems",
    ("reb_ibm_revenue_sales_target_execution", "skill_partner_enterprise_negotiations"): "Commercial & Operating Impact",
    (
        "reb_ibm_presales_solution_engineering",
        "skill_partner_pre_sales",
    ): "Cloud & Partner Ecosystems",
    (
        "reb_ibm_customer_success_value_realization",
        "skill_p2_gtm_presales_delivery_handoff",
    ): "Engineering & Delivery Leadership",
    (
        "reb_ibm_customer_success_value_realization",
        "skill_partner_customer_deal_support",
    ): "Commercial & Operating Impact",
    (
        "reb_ibm_devsecops_release_resilience",
        "skill_ibm_automated_release_pipelines",
    ): "Governance, Risk & Compliance",
    ("reb_unify_distributed_ecosystem_engineering", "skill_runtime_resilience_controls"): "LLMOps & Reliability",
    ("reb_unify_distributed_ecosystem_engineering", "skill_provider_and_egress_governance"): "Governance, Risk & Compliance",
    ("reb_unify_distributed_ecosystem_engineering", "skill_sr_w12_databricks_lakehouse_fundamentals"): "Data & Analytics Modernization",
    ("reb_unify_agentic_platform_architecture", "skill_unify_agentic_human_override_escalation_paths"): "Engineering & Delivery Leadership",
    ("reb_unify_agentic_platform_architecture", "skill_unify_agentic_runtime_proof_bundle_lineage"): "Engineering & Delivery Leadership",
    ("reb_unify_agentic_platform_architecture", "skill_unify_agentic_l0_route_policy_dispatch"): "AI Platform Leadership",
    ("reb_ibm_offering_accelerator_management", "skill_p2_tech_ibm_cloud_portfolio_anchor"): "Cloud & Partner Ecosystems",
    ("reb_ibm_offering_accelerator_management", "skill_p2_tech_reusable_accelerators"): "AI Platform Leadership",
    ("reb_ibm_offering_accelerator_management", "skill_sr_w12_industry_reference_architecture"): "Cloud & Partner Ecosystems",
    ("reb_ibm_offering_accelerator_management", "skill_p2_tech_demoable_accelerator"): "AI Platform Leadership",
    ("reb_ibm_aws_modernization_architecture", "skill_p2_tech_aws_modernization_patterns"): "Data & Analytics Modernization",
    ("reb_ibm_aws_modernization_architecture", "skill_p2_tech_reference_architecture"): "Data & Analytics Modernization",
    ("reb_insurtech_regulated_aws_control_implementation", "skill_aws_iam_kms_cloudtrail_controls"): "Governance, Risk & Compliance",
    ("reb_insurtech_regulated_aws_control_implementation", "skill_soc2_zero_trust_security"): "Governance, Risk & Compliance",
    ("reb_ey_insurance_core_modernization", "skill_insurance_core_to_bi_reporting_handoff"): "Data & Analytics Modernization",
    ("reb_slalom_ecosystem_accelerators", "skill_partner_aws_ecosystem"): "Cloud & Partner Ecosystems",
    ("reb_ey_ccar_capital_liquidity_stress_testing", "skill_capital_capital_modeling"): "LLMOps & Reliability",
    ("reb_ey_capital_optimization_solvency", "skill_risk_greek_stress_testing"): "Technology Strategy & Innovation",
}
_SURFACE_COMPOSITION_CONNECTIVES = frozenset(
    {"and", "for", "of", "the", "to", "with", "through", "across", "via"}
)

# This is a target-specific *output layout*, not a retrieval or evidence
# policy. Brown & Brown's insurance-IT section has a frozen 24-unit allocation
# (three source-backed detail terms in each of eight final competency groups).
# The generic competency-bundle anchor retained in each group carries the
# required cross-cutting SVP capability signal; the three allocation terms are
# the exact role-episode evidence that the visible résumé group must consume.
# A changed allocation fails closed rather than being squeezed into an
# unrelated heading by lexical proximity.
_INSURANCE_IT_STRATEGY_FROZEN_ALLOCATION_LAYOUT: tuple[Mapping[str, Any], ...] = (
    {
        "category_id": "cloud_partner_ecosystems",
        "category_label": "Cloud & Partner Ecosystems",
        "resume_display_label": "Partner Applied AI Architecture",
        "competency_bundle_id": "ccb_partner_applied_ai_architecture",
        "assignment_keys": (
            ("reb_ibm_offering_accelerator_management", "skill_sr_w12_industry_reference_architecture"),
            ("reb_unify_partner_channel_cosell", "skill_partner_partner_led_ai_solutions"),
            ("reb_unify_partner_channel_cosell", "skill_partner_cloud_vendor_joint_gtm"),
        ),
    },
    {
        "category_id": "ai_platform_leadership",
        "category_label": "AI Platform Leadership",
        "resume_display_label": "Governed Agentic AI Platform Architecture",
        "competency_bundle_id": "ccb_agentic_platforms",
        "assignment_keys": (
            ("reb_ibm_offering_accelerator_management", "skill_p2_tech_reusable_accelerators"),
            ("reb_unify_agentic_platform_architecture", "skill_unify_agentic_human_override_escalation_paths"),
            ("reb_unify_agentic_platform_architecture", "skill_unify_agentic_runtime_proof_bundle_lineage"),
        ),
    },
    {
        "category_id": "governance_risk_compliance",
        "category_label": "Governance, Risk & Compliance",
        "resume_display_label": "AI Runtime Governance & Control Gates",
        "competency_bundle_id": "ccb_runtime_governance",
        "generic_anchor_phrase": "policy enforcement across agent execution paths",
        "assignment_keys": (
            ("reb_insurtech_regulated_aws_control_implementation", "skill_soc2_zero_trust_security"),
            ("reb_insurtech_regulated_aws_control_implementation", "skill_sr_insurtech_regulated_insurer_controls"),
            ("reb_insurtech_regulated_aws_control_implementation", "skill_soc2_control_mapping_for_aws"),
        ),
    },
    {
        "category_id": "tech_strategy_innovation",
        "category_label": "Technology Strategy & Innovation",
        "resume_display_label": "AI Risk, Decisioning & Context Engineering",
        "competency_bundle_id": "ccb_retrieval_context_engineering",
        "assignment_keys": (
            ("reb_ey_erm_risk_governance", "skill_credit_adjudication_default_risk"),
            ("reb_ey_erm_risk_governance", "skill_risk_three_lines_of_defense"),
            ("reb_ey_erm_risk_governance", "skill_risk_model_risk"),
        ),
    },
    {
        "category_id": "commercial_operating_impact",
        "category_label": "Commercial & Operating Impact",
        "resume_display_label": "Cloud Security, Transformation & Productization",
        "competency_bundle_id": "ccb_platform_productization",
        "assignment_keys": (
            ("reb_insurtech_regulated_aws_control_implementation", "skill_pii_encryption_for_insurance_data"),
            ("reb_insurtech_regulated_aws_control_implementation", "skill_aws_iam_kms_cloudtrail_controls"),
            ("reb_ibm_offering_accelerator_management", "skill_p2_tech_ibm_cloud_portfolio_anchor"),
        ),
    },
    {
        "category_id": "llmops_reliability",
        "category_label": "LLMOps & Reliability",
        "resume_display_label": "Modernization Delivery & Reliability",
        "competency_bundle_id": "ccb_llmops_reliability",
        "assignment_keys": (
            ("reb_insurtech_aws_migration_execution", "skill_migration_wave_cutover_planning"),
            ("reb_insurtech_aws_migration_execution", "skill_application_dependency_mapping"),
            ("reb_ey_insurance_core_modernization", "skill_insurance_guidewire"),
        ),
    },
    {
        "category_id": "data_analytics_modernization",
        "category_label": "Data & Analytics Modernization",
        "resume_display_label": "Insurance Core Data & Workflow Modernization",
        "competency_bundle_id": "ccb_distributed_systems_engineering",
        "assignment_keys": (
            ("reb_insurtech_aws_guidewire_core_modernization", "skill_insurance_core_data_model_mapping"),
            ("reb_ey_insurance_core_modernization", "skill_insurance_claims_automation"),
            ("reb_ey_insurance_core_modernization", "skill_insurance_core_to_bi_reporting_handoff"),
        ),
    },
    {
        "category_id": "engineering_delivery_leadership",
        "category_label": "Engineering & Delivery Leadership",
        "resume_display_label": "AWS Migration Execution & Leadership",
        "competency_bundle_id": "ccb_engineering_leadership",
        "assignment_keys": (
            ("reb_insurtech_aws_migration_execution", "skill_sr_insurtech_legacy_cloud_modernization"),
            ("reb_insurtech_aws_migration_execution", "skill_p2_tech_aws_modernization_patterns"),
            ("reb_insurtech_aws_migration_execution", "skill_aws_migration_readiness_assessment"),
        ),
    },
)


def insurance_it_strategy_frozen_layout_is_present(
    selected_plan: Mapping[str, Any],
) -> bool:
    """Return whether a plan actually carries the complete frozen 24-unit layout.

    The ordinary whole-resume allocator reserves eight competency units.  The
    Brown & Brown visible-layout projection is a separate, fixed 24-unit
    surface and may run only when the selected plan contains that exact
    assignment universe.  Generic allocation plans continue through the
    normal allocation/reconciliation path; they must not be mistaken for a
    damaged copy of the dedicated projection layout.
    """

    if str(selected_plan.get("target_role_profile") or "").strip() != (
        "insurance_it_strategy"
    ):
        return False
    assignments = _allocation_assignments(selected_plan)
    observed_keys = {
        (
            str(row.get("root_id") or "").strip(),
            str(row.get("skill_id") or "").strip(),
        )
        for row in assignments
    }
    expected_keys = {
        (str(root_id), str(skill_id))
        for spec in _INSURANCE_IT_STRATEGY_FROZEN_ALLOCATION_LAYOUT
        for root_id, skill_id in spec["assignment_keys"]
    }
    return len(assignments) == len(observed_keys) == len(expected_keys) and (
        observed_keys == expected_keys
    )


def _strings(values: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(str(value or "").casefold())
        if token not in _IDENTITY_NOISE and len(token) >= 3
    }


def _term_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("text") or value.get("term") or "").strip()
    return str(value or "").strip()


def _role_axes(*values: Any) -> list[str]:
    text = " ".join(str(value or "") for value in values).casefold()
    return sorted(
        axis
        for axis, signals in _ROLE_AXIS_SIGNALS.items()
        if any(signal.casefold() in text for signal in signals)
    )


def _authority_by_root(plan: Mapping[str, Any]) -> dict[str, dict[str, set[str]]]:
    authority: dict[str, dict[str, set[str]]] = {}
    for raw in plan.get("facts") or []:
        if not isinstance(raw, Mapping):
            continue
        root_id = str(raw.get("role_episode_bundle_id") or raw.get("fact_id") or "")
        if not root_id:
            continue
        authority[root_id] = {
            "skills": set(_strings(raw.get("graph_skill_node_ids"))),
            "facts": set(
                _strings(
                    [
                        root_id,
                        raw.get("fact_id"),
                        *list(raw.get("linked_identity_fact_ids") or []),
                        *list(raw.get("linked_source_fact_ids") or []),
                    ]
                )
            ),
            "metrics": set(_strings(raw.get("metric_outcome_ids"))),
        }
    return authority


def _match_score(
    assignment: Mapping[str, Any],
    *,
    category: Mapping[str, Any],
    term: Any,
    root_authority: Mapping[str, Mapping[str, set[str]]],
) -> tuple[int, list[str]]:
    root_id = str(assignment.get("root_id") or "")
    skill_id = str(assignment.get("skill_id") or "")
    fact_id = str(assignment.get("fact_id") or "")
    category_skills = set(_strings(category.get("graph_skill_node_ids")))
    category_facts = set(_strings(category.get("source_fact_ids")))
    term_skills = set()
    if isinstance(term, Mapping):
        term_skills = set(
            _strings(
                [
                    *list(term.get("source_skill_ids") or []),
                    *list(term.get("graph_skill_node_ids") or []),
                ]
            )
        )
    term_sources = set(
        _strings(term.get("source_fact_ids")) if isinstance(term, Mapping) else []
    )
    if isinstance(term, Mapping) and term.get("source_fact_id"):
        term_sources.add(str(term.get("source_fact_id")))
    reasons: list[str] = []
    score = 0
    # A term-level list containing several skills is a category-support
    # inventory, not evidence that this *specific phrase* realizes each
    # member.  Treat it as direct only when it names exactly one skill; a
    # broader list still contributes through lexical phrase alignment.
    if skill_id and term_skills == {skill_id}:
        score += 2_000
        reasons.append("EXACT_TERM_SKILL_ID")
    if skill_id and skill_id in category_skills:
        score += 1000
        reasons.append("EXACT_CATEGORY_SKILL_ID")
    if root_id and root_id in category_facts | term_sources:
        score += 900
        reasons.append("EXACT_ROOT_ID")
    if fact_id and fact_id in category_facts | term_sources:
        score += 850
        reasons.append("EXACT_FACT_ID")
    sibling_skills = set((root_authority.get(root_id) or {}).get("skills") or set())
    sibling_overlap = sorted(sibling_skills & category_skills)
    if sibling_overlap:
        score += 700 + min(len(sibling_overlap), 9)
        reasons.append("EXACT_ROOT_SIBLING_SKILL_ID")
    lexical_overlap = sorted(_tokens(skill_id) & _tokens(_term_text(term)))
    # A single token (for example, ``insurance``) is not a meaningful skill
    # identity.  Require two non-noise tokens before it may establish a
    # visible claim binding.  Shared fact/root provenance remains valuable
    # supporting evidence, but can never bind an unrelated phrase by itself.
    if len(lexical_overlap) >= 2:
        score += 100 * len(lexical_overlap)
        reasons.append("SEMANTIC_SKILL_TERM_OVERLAP:" + ",".join(lexical_overlap))
    if not any(
        reason == "EXACT_TERM_SKILL_ID"
        or reason.startswith("SEMANTIC_SKILL_TERM_OVERLAP:")
        for reason in reasons
    ):
        return 0, []
    return score, reasons


def _allocation_assignments(selected_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (
            dict(row)
            for row in selected_plan.get("allocation_assignments") or []
            if isinstance(row, Mapping) and row.get("section_id") == "competencies"
        ),
        key=lambda row: str(row.get("claim_unit_id") or ""),
    )


def _surface_tokens(value: Any) -> set[str]:
    """Normalize graph-source and résumé surface tokens for bounded matching."""

    return set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _composition_is_bound(
    phrase: str,
    *,
    assignment: Mapping[str, Any],
    root_fact: Mapping[str, Any],
) -> bool:
    """Return whether every substantive surface word is already graph-authored.

    The allowed vocabulary is deliberately limited to the selected leaf's
    label/ID/source snippets and the selected root's graph fields.  A plural
    may match its singular source token (and vice versa), but no new semantic
    word can enter a visible allocation recovery term.
    """

    graph_text = [
        assignment.get("skill_id"),
        assignment.get("skill_label"),
        assignment.get("root_bundle_theme"),
        assignment.get("root_claim_text"),
        assignment.get("root_claim_action"),
        assignment.get("root_claim_scope"),
        assignment.get("root_claim_outcome"),
        *(assignment.get("source_refs") or []),
        root_fact.get("domain"),
        root_fact.get("bundle_theme"),
        root_fact.get("claim_text"),
        root_fact.get("claim_action"),
        root_fact.get("claim_scope"),
        root_fact.get("claim_outcome"),
        *(root_fact.get("source_refs") or []),
    ]
    source_tokens = set().union(*(_surface_tokens(value) for value in graph_text))
    for token in _surface_tokens(phrase):
        if token in _SURFACE_COMPOSITION_CONNECTIVES or token in source_tokens:
            continue
        # Graph source prose commonly spells the certification "SOC 2" while
        # node labels use the compact résumé surface "SOC2".
        if token == "soc2" and {"soc", "2"} <= source_tokens:
            continue
        if token == "validation" and "testing" in source_tokens:
            continue
        if token.endswith("s") and token[:-1] in source_tokens:
            continue
        if f"{token}s" in source_tokens:
            continue
        return False
    return True


def _allocation_surface_phrase(
    assignment: Mapping[str, Any],
    *,
    selected_plan: Mapping[str, Any],
) -> tuple[str, str]:
    """Resolve one human-readable, graph-authored competency surface.

    The frozen allocation identifies the graph skill and supporting fact, but
    graph IDs are deliberately not résumé text. Prefer the role-episode
    bundle's author-authored theme, carried into the sealed allocation. Its
    selected-plan domain and skill label are bounded fallbacks. This is a
    projection of existing graph content, never an LLM paraphrase or a newly
    inferred claim.
    """

    root_id = str(assignment.get("root_id") or "").strip()
    skill_id = str(assignment.get("skill_id") or "").strip()
    fact_by_root = {
        str(row.get("role_episode_bundle_id") or row.get("fact_id") or "").strip(): row
        for row in selected_plan.get("facts") or []
        if isinstance(row, Mapping)
    }
    root_fact = fact_by_root.get(root_id) or {}
    composition = _ALLOCATION_VISIBLE_SURFACE_COMPOSITIONS.get((root_id, skill_id))
    if composition and _composition_is_bound(
        composition,
        assignment=assignment,
        root_fact=root_fact,
    ):
        return composition, "graph_authority_surface_composition"
    candidates: list[tuple[str, str]] = [
        ("root_bundle_theme", str(assignment.get("root_bundle_theme") or "").strip()),
        ("selected_graph_plan_domain", str(root_fact.get("domain") or "").strip()),
        ("skill_label", str(assignment.get("skill_label") or "").strip()),
        ("skill_id_surface", skill_id.removeprefix("skill_").replace("_", " ")),
    ]
    for ref in assignment.get("source_refs") or []:
        candidates.append(("skill_source_ref", str(ref or "").strip()))
    for row in selected_plan.get("graph_candidate_decision_ledger") or []:
        if not isinstance(row, Mapping):
            continue
        if (
            str(row.get("candidate_type") or "") == "leaf_skill"
            and str(row.get("candidate_id") or "") == skill_id
            and str(row.get("root_id") or "") == root_id
        ):
            candidates.extend(
                [
                    ("decision_ledger_skill_label", str(row.get("skill_label") or "").strip()),
                    *[
                        ("decision_ledger_source_ref", str(ref or "").strip())
                        for ref in row.get("source_refs") or []
                    ],
                ]
            )
    for source_field, candidate in candidates:
        phrase = " ".join(candidate.replace("_", " ").split()).strip()
        if not phrase or phrase.casefold().startswith(("reb ", "skill ", "fact ")):
            continue
        # A visible competency is a compact executive phrase, not an opaque
        # graph identifier or a full source sentence.  Continue to the next
        # graph-authored alternative rather than returning the first (possibly
        # unusable) field.
        if 5 <= len(phrase.split()) <= 7:
            return phrase, source_field
    return "", ""


def _allocation_surface_category(
    categories: list[dict[str, Any]],
    *,
    phrase: str,
    assignment: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Place a graph-authored allocation term in its closest existing category."""

    if not categories:
        return None
    override_label = _ALLOCATION_SURFACE_CATEGORY_OVERRIDES.get(
        (
            str(assignment.get("root_id") or "").strip(),
            str(assignment.get("skill_id") or "").strip(),
        )
    )
    if override_label:
        for category in categories:
            if override_label in {
                str(category.get("category_label") or "").strip(),
                str(category.get("resume_display_label") or "").strip(),
            } and _category_can_accept_allocation(category):
                return category
    phrase_tokens = _tokens(phrase) | _tokens(assignment.get("skill_id"))
    commercial_tokens = {"customer", "deal", "revenue", "sales", "target", "value"}
    best: tuple[int, int, int, dict[str, Any]] | None = None
    for index, category in enumerate(categories):
        terms = category.get("terms") or []
        nonempty_terms = sum(1 for term in terms if _term_text(term))
        if not _category_can_accept_allocation(category):
            continue
        category_text = " ".join(
            [
                str(category.get("category_label") or ""),
                str(category.get("resume_display_label") or ""),
                *[_term_text(term) for term in terms],
            ]
        )
        category_tokens = _tokens(category_text)
        score = 10 * len(phrase_tokens & category_tokens)
        category_lower = category_text.casefold()
        if phrase_tokens & commercial_tokens and any(
            signal in category_lower for signal in ("commercial", "operating", "impact")
        ):
            score += 100
        if "partner" in phrase_tokens and "partner" in category_lower:
            score += 50
        candidate = (score, -nonempty_terms, -index, category)
        if best is None or candidate[:3] > best[:3]:
            best = candidate
    return best[3] if best is not None else None


def _category_can_accept_allocation(category: Mapping[str, Any]) -> bool:
    """Whether a category has a free slot or a non-authoritative term to replace."""

    terms = [term for term in category.get("terms") or [] if _term_text(term)]
    if len(terms) < 6:
        return True
    return any(
        not (
            isinstance(term, Mapping)
            and str(term.get("allocation_claim_unit_id") or "").strip()
        )
        for term in terms
    )


def _make_category_capacity(
    category: dict[str, Any],
    *,
    ceiling: int = 6,
) -> dict[str, Any] | None:
    """Open one slot without deleting a frozen allocation identity.

    Model-authored bundle anchors are optional once a more specific frozen
    allocation is projected into the same capability family.  Removing the
    last optional term is deterministic and preserves the 3-item category
    floor. Most categories use the six-item schema ceiling. A category rebound
    to the partnership-execution bundle uses a three-item display ceiling so
    its three frozen allocation terms replace generic bundle anchors instead
    of creating the 27-item keyword-dense Retry 15 surface.
    """

    terms = list(category.get("terms") or [])
    nonempty = [index for index, term in enumerate(terms) if _term_text(term)]
    if len(nonempty) < ceiling:
        return None
    for index in reversed(nonempty):
        term = terms[index]
        if isinstance(term, Mapping) and str(
            term.get("allocation_claim_unit_id") or ""
        ).strip():
            continue
        removed = terms.pop(index)
        category["terms"] = terms
        return {
            "visible_term": _term_text(removed),
            "reason": "category_ceiling_replaced_optional_bundle_anchor",
        }
    return None


def _partner_gtm_allocation_display_ceiling(
    category: Mapping[str, Any],
    assignment: Mapping[str, Any],
) -> int:
    """Return the compact display ceiling for a partner-GTM rebound category."""

    # The Anthropic partner allocation starts from an eight-by-three surface.
    # Recovery terms from these roots replace optional anchors in their
    # semantically routed categories instead of increasing resume density.
    if str(category.get("category_label") or "").strip() in {
        "Cloud & Partner Ecosystems",
        "Governance, Risk & Compliance",
        "Commercial & Operating Impact",
        "Engineering & Delivery Leadership",
        "Technology Strategy & Innovation",
        "LLMOps & Reliability",
    } and str(assignment.get("root_id") or "").strip() in {
        "reb_unify_partner_channel_cosell",
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "reb_ibm_revenue_sales_target_execution",
        "reb_ibm_customer_success_value_realization",
        "reb_ibm_devsecops_release_resilience",
        "reb_ibm_presales_solution_engineering",
        "reb_slalom_ecosystem_accelerators",
        "reb_ey_ccar_capital_liquidity_stress_testing",
        "reb_ey_capital_optimization_solvency",
    }:
        return 3
    return 6


def _apply_allocation_category_authority(
    category: dict[str, Any],
    *,
    assignment: Mapping[str, Any],
) -> dict[str, str] | None:
    """Preserve the governed category family while adding frozen evidence.

    Rebinding the sole commercial category after the first co-sell allocation
    erased the required platform-productization family. Category routing now
    separates partner architecture, delivery leadership, and commercial
    productization, so no authority mutation is required.
    """

    del category, assignment
    return None


def _recompute_category_authority_from_visible_terms(
    categories: Iterable[dict[str, Any]],
) -> None:
    """Remove stale category provenance after optional-term replacement.

    Category-level source and skill lists are a projection of the currently
    visible terms.  Keeping facts from terms that recovery replaced creates a
    false concentration signal and makes the durable category disagree with
    its claim ledger.
    """

    for category in categories:
        facts: list[str] = []
        skills: list[str] = []
        claim_units: list[str] = []
        for term in category.get("terms") or []:
            if not isinstance(term, Mapping) or not _term_text(term):
                continue
            facts.extend(_strings(term.get("source_fact_ids")))
            if term.get("source_fact_id"):
                facts.append(str(term.get("source_fact_id")))
            skills.extend(_strings(term.get("source_skill_ids")))
            skills.extend(_strings(term.get("graph_skill_node_ids")))
            if term.get("allocation_claim_unit_id"):
                claim_units.append(str(term.get("allocation_claim_unit_id")))
        category["source_fact_ids"] = _strings(facts)
        category["graph_skill_node_ids"] = _strings(skills)
        category["allocation_claim_unit_ids"] = _strings(claim_units)


def _align_partner_commercial_display_label(
    categories: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    """Keep a fully allocated commercial category honest about its contents.

    When partner allocation replaces all three optional productization anchors,
    retaining the narrower ``Platform Productization`` display label makes the
    visible category disagree with its evidence.  The governed taxonomy and
    bundle IDs remain unchanged; only the resume wrapper is made specific to
    the three source-bound commercial terms.
    """

    changes: list[dict[str, str]] = []
    for category in categories:
        if str(category.get("competency_bundle_id") or "") != (
            "ccb_platform_productization"
        ):
            continue
        terms = [term for term in category.get("terms") or [] if _term_text(term)]
        if len(terms) != 3 or not all(
            isinstance(term, Mapping)
            and bool(str(term.get("allocation_claim_unit_id") or "").strip())
            for term in terms
        ):
            continue
        before = str(
            category.get("resume_display_label")
            or category.get("category_label")
            or ""
        )
        after = "Partner Commercialization & Value Realization"
        category["resume_display_label"] = after
        if before != after:
            changes.append({"before": before, "after": after})
    return changes


def materialize_unmatched_competencies_allocation_terms(
    parsed: dict[str, Any],
    *,
    selected_plan: Mapping[str, Any],
    allowed_fact_ids: set[str],
    claim_unit_ids: Iterable[str],
) -> dict[str, Any]:
    """Add only missing frozen-allocation terms to the final résumé surface.

    This is a narrow deterministic bridge between a valid graph allocation and
    the final competency display.  It runs only after normal model generation
    and graph-surface enrichment leave a frozen allocation unit unmatched.
    Each added term retains the assignment's exact skill and source-fact IDs.
    """

    requested = {str(value or "").strip() for value in claim_unit_ids if str(value or "").strip()}
    assignments = {
        str(row.get("claim_unit_id") or ""): row
        for row in _allocation_assignments(selected_plan)
        if str(row.get("claim_unit_id") or "") in requested
    }
    additions: list[dict[str, Any]] = []
    replacements: list[dict[str, Any]] = []
    category_authority_rebindings: list[dict[str, str]] = []
    unresolved: list[str] = []
    surfaces = [
        (name, parsed.get(name))
        for name in ("categories", "competencies")
        if isinstance(parsed.get(name), list)
    ]
    if not surfaces:
        unresolved.extend(sorted(requested))

    for claim_unit_id in sorted(requested):
        assignment = assignments.get(claim_unit_id)
        if not assignment:
            unresolved.append(claim_unit_id)
            continue
        fact_id = str(assignment.get("fact_id") or "").strip()
        skill_id = str(assignment.get("skill_id") or "").strip()
        phrase, source_field = _allocation_surface_phrase(
            assignment,
            selected_plan=selected_plan,
        )
        # A recovery surface must itself be résumé-quality. If the frozen
        # graph cannot provide a compact theme, retain the failed-closed
        # allocation mismatch rather than append a raw node-ID fragment.
        phrase_word_count = len(phrase.split())
        if (
            not fact_id
            or fact_id not in allowed_fact_ids
            or not skill_id
            or not phrase
            or phrase_word_count < 5
            or phrase_word_count > 7
        ):
            unresolved.append(claim_unit_id)
            continue
        unit_added = False
        for surface_name, raw_categories in surfaces:
            categories = [row for row in raw_categories if isinstance(row, dict)]
            category = _allocation_surface_category(
                categories,
                phrase=phrase,
                assignment=assignment,
            )
            if category is None:
                continue
            authority_rebinding = _apply_allocation_category_authority(
                category,
                assignment=assignment,
            )
            if authority_rebinding is not None:
                category_authority_rebindings.append(
                    {"surface": surface_name, **authority_rebinding}
                )
            terms = list(category.get("terms") or [])
            same_phrase_terms = [
                term
                for term in terms
                if _term_text(term).casefold() == phrase.casefold()
            ]
            if same_phrase_terms:
                # A shared recovery phrase cannot silently satisfy two frozen
                # allocation units.  It is complete only when the existing
                # visible term already carries *this* exact unit identity;
                # otherwise leave the unit unresolved so the later
                # reconciliation fails closed.  A distinct, source-bound
                # composition is required to recover a second assignment.
                if any(
                    isinstance(term, Mapping)
                    and str(term.get("allocation_claim_unit_id") or "")
                    == claim_unit_id
                    for term in same_phrase_terms
                ):
                    unit_added = True
                continue
            display_ceiling = _partner_gtm_allocation_display_ceiling(
                category,
                assignment,
            )
            replacement = _make_category_capacity(
                category,
                ceiling=display_ceiling,
            )
            if (
                sum(1 for term in category.get("terms") or [] if _term_text(term))
                >= display_ceiling
            ):
                continue
            if replacement is not None:
                replacements.append(
                    {
                        "surface": surface_name,
                        "category_label": str(
                            category.get("resume_display_label")
                            or category.get("category_label")
                            or ""
                        ),
                        **replacement,
                    }
                )
            terms = list(category.get("terms") or [])
            terms.append(
                {
                    "term": phrase,
                    "text": phrase,
                    "source_fact_id": fact_id,
                    "source_fact_ids": [fact_id],
                    "source_skill_ids": [skill_id],
                    "graph_skill_node_ids": [skill_id],
                    "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                    "proof_source": "allocation_visible_graph_surface",
                    "allocation_claim_unit_id": claim_unit_id,
                    "allocation_surface_source_field": source_field,
                }
            )
            category["terms"] = terms
            category["source_fact_ids"] = _strings(
                [*list(category.get("source_fact_ids") or []), fact_id]
            )
            category["graph_skill_node_ids"] = _strings(
                [*list(category.get("graph_skill_node_ids") or []), skill_id]
            )
            category["allocation_claim_unit_ids"] = _strings(
                [*list(category.get("allocation_claim_unit_ids") or []), claim_unit_id]
            )
            additions.append(
                {
                    "surface": surface_name,
                    "claim_unit_id": claim_unit_id,
                    "category_label": str(
                        category.get("resume_display_label")
                        or category.get("category_label")
                        or ""
                    ),
                    "visible_term": phrase,
                    "skill_id": skill_id,
                    "fact_id": fact_id,
                    "source": "frozen_graph_role_episode_theme",
                }
            )
            unit_added = True
        if not unit_added:
            unresolved.append(claim_unit_id)

    display_label_adjustments: list[dict[str, str]] = []
    for surface_name, raw_categories in surfaces:
        _recompute_category_authority_from_visible_terms(
            row for row in raw_categories if isinstance(row, dict)
        )
        display_label_adjustments.extend(
            {"surface": surface_name, **change}
            for change in _align_partner_commercial_display_label(
                row for row in raw_categories if isinstance(row, dict)
            )
        )

    receipt: dict[str, Any] = {
        "schema_version": "competencies_allocation_visible_surface_v1",
        "section_id": "competencies",
        "allocation_plan_digest": str(selected_plan.get("allocation_plan_digest") or ""),
        "requested_claim_unit_ids": sorted(requested),
        "added_claim_unit_ids": sorted(
            {str(row.get("claim_unit_id") or "") for row in additions}
        ),
        "unresolved_claim_unit_ids": sorted(set(unresolved)),
        "additions": additions,
        "optional_term_replacements": replacements,
        "category_authority_rebindings": category_authority_rebindings,
        "display_label_adjustments": display_label_adjustments,
        "pass": not unresolved,
    }
    receipt["receipt_digest"] = stable_digest(receipt)
    return receipt


def project_insurance_it_strategy_competencies_from_frozen_allocation(
    parsed: dict[str, Any],
    *,
    selected_plan: Mapping[str, Any],
    allowed_fact_ids: set[str],
) -> dict[str, Any]:
    """Build the final Brown & Brown competency surface from its frozen allocation.

    The target's existing competency-bundle anchors retain the cross-cutting
    SVP capability vocabulary required by the section contract.  This function
    adds the exact three role-episode allocation units assigned to each final
    group, rather than relying on lexical category proximity.  It is applicable
    only to the explicitly configured ``insurance_it_strategy`` layout and
    fails closed if the frozen assignment universe changes.
    """

    target_profile = str(selected_plan.get("target_role_profile") or "").strip()
    base: dict[str, Any] = {
        "schema_version": "competencies_frozen_allocation_output_projection_v1",
        "section_id": "competencies",
        "target_role_profile": target_profile,
        "allocation_plan_digest": str(selected_plan.get("allocation_plan_digest") or ""),
        "applicable": target_profile == "insurance_it_strategy",
        "projection_policy": "insurance_it_strategy_frozen_role_episode_layout_v1",
        "visible_wording_changed": False,
    }
    if not base["applicable"]:
        base.update({"pass": True, "status": "NOT_APPLICABLE"})
        base["receipt_digest"] = stable_digest(base)
        return base

    assignments = _allocation_assignments(selected_plan)
    assignment_by_key = {
        (
            str(row.get("root_id") or "").strip(),
            str(row.get("skill_id") or "").strip(),
        ): row
        for row in assignments
    }
    expected_keys = {
        (str(root_id), str(skill_id))
        for spec in _INSURANCE_IT_STRATEGY_FROZEN_ALLOCATION_LAYOUT
        for root_id, skill_id in spec["assignment_keys"]
    }
    observed_keys = set(assignment_by_key)
    missing_keys = sorted(expected_keys - observed_keys)
    unexpected_keys = sorted(observed_keys - expected_keys)
    if len(assignments) != len(assignment_by_key) or missing_keys or unexpected_keys:
        base.update(
            {
                "pass": False,
                "status": "BLOCKED_FROZEN_ALLOCATION_LAYOUT_MISMATCH",
                "expected_assignment_count": len(expected_keys),
                "observed_assignment_count": len(assignments),
                "missing_assignment_keys": [list(value) for value in missing_keys],
                "unexpected_assignment_keys": [list(value) for value in unexpected_keys],
            }
        )
        base["receipt_digest"] = stable_digest(base)
        return base

    fact_by_root = {
        str(row.get("role_episode_bundle_id") or row.get("fact_id") or "").strip(): row
        for row in selected_plan.get("facts") or []
        if isinstance(row, Mapping)
    }
    source_categories = [
        row
        for surface_name in ("categories", "competencies")
        for row in parsed.get(surface_name) or []
        if isinstance(row, Mapping)
    ]
    anchor_by_bundle: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for category in source_categories:
        bundle_id = str(category.get("competency_bundle_id") or "").strip()
        if not bundle_id or bundle_id in anchor_by_bundle:
            continue
        for raw_term in category.get("terms") or []:
            phrase = _term_text(raw_term)
            if not phrase:
                continue
            term = copy.deepcopy(raw_term) if isinstance(raw_term, Mapping) else {"text": phrase}
            source_fact_ids = _strings(
                [
                    term.get("source_fact_id"),
                    *list(term.get("source_fact_ids") or []),
                ]
            )
            source_skill_ids = _strings(
                [
                    *list(term.get("source_skill_ids") or []),
                    *list(term.get("graph_skill_node_ids") or []),
                ]
            )
            if (
                source_fact_ids
                and set(source_fact_ids) <= allowed_fact_ids
                and source_skill_ids
            ):
                term["text"] = phrase
                term["term"] = phrase
                anchor_by_bundle[bundle_id] = (dict(category), term)
                break

    missing_anchors = sorted(
        str(spec["competency_bundle_id"])
        for spec in _INSURANCE_IT_STRATEGY_FROZEN_ALLOCATION_LAYOUT
        if str(spec["competency_bundle_id"]) not in anchor_by_bundle
    )
    if missing_anchors:
        base.update(
            {
                "pass": False,
                "status": "BLOCKED_COMPETENCY_BUNDLE_ANCHOR_MISSING",
                "missing_competency_bundle_ids": missing_anchors,
            }
        )
        base["receipt_digest"] = stable_digest(base)
        return base

    projected_categories: list[dict[str, Any]] = []
    projected_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    for order, spec in enumerate(_INSURANCE_IT_STRATEGY_FROZEN_ALLOCATION_LAYOUT, start=1):
        bundle_id = str(spec["competency_bundle_id"])
        source_category, generic_anchor = anchor_by_bundle[bundle_id]
        preferred_anchor_phrase = str(spec.get("generic_anchor_phrase") or "").strip()
        if preferred_anchor_phrase:
            preferred_anchor: dict[str, Any] | None = None
            for raw_term in source_category.get("terms") or []:
                if _term_text(raw_term) != preferred_anchor_phrase:
                    continue
                candidate = (
                    copy.deepcopy(raw_term)
                    if isinstance(raw_term, Mapping)
                    else {"text": preferred_anchor_phrase}
                )
                candidate_fact_ids = _strings(
                    [
                        candidate.get("source_fact_id"),
                        *list(candidate.get("source_fact_ids") or []),
                    ]
                )
                candidate_skill_ids = _strings(
                    [
                        *list(candidate.get("source_skill_ids") or []),
                        *list(candidate.get("graph_skill_node_ids") or []),
                    ]
                )
                if (
                    candidate_fact_ids
                    and set(candidate_fact_ids) <= allowed_fact_ids
                    and candidate_skill_ids
                ):
                    candidate["text"] = preferred_anchor_phrase
                    candidate["term"] = preferred_anchor_phrase
                    preferred_anchor = candidate
                    break
            if preferred_anchor is None:
                failure_rows.append(
                    {
                        "competency_bundle_id": bundle_id,
                        "preferred_anchor_phrase": preferred_anchor_phrase,
                        "reason": "preferred_generic_anchor_not_source_bound",
                    }
                )
            else:
                generic_anchor = preferred_anchor
        terms: list[dict[str, Any]] = [copy.deepcopy(generic_anchor)]
        source_fact_ids = [
            fact_id
            for fact_id in _strings(
                [
                    generic_anchor.get("source_fact_id"),
                    *list(generic_anchor.get("source_fact_ids") or []),
                ]
            )
            if fact_id in allowed_fact_ids
        ]
        graph_skill_ids = _strings(
            [
                *list(generic_anchor.get("source_skill_ids") or []),
                *list(generic_anchor.get("graph_skill_node_ids") or []),
            ]
        )
        claim_unit_ids: list[str] = []
        for root_id, skill_id in spec["assignment_keys"]:
            assignment = assignment_by_key[(str(root_id), str(skill_id))]
            fact_id = str(assignment.get("fact_id") or "").strip()
            phrase, source_field = _allocation_surface_phrase(
                assignment,
                selected_plan=selected_plan,
            )
            phrase_word_count = len(phrase.split())
            root_fact = fact_by_root.get(str(root_id)) or {}
            if (
                not fact_id
                or fact_id not in allowed_fact_ids
                or not phrase
                or not _composition_is_bound(
                    phrase,
                    assignment=assignment,
                    root_fact=root_fact,
                )
                or phrase_word_count < 5
                or phrase_word_count > 7
            ):
                failure_rows.append(
                    {
                        "root_id": str(root_id),
                        "skill_id": str(skill_id),
                        "fact_id": fact_id,
                        "phrase": phrase,
                        "source_field": source_field,
                    }
                )
                continue
            claim_unit_id = str(assignment.get("claim_unit_id") or "").strip()
            terms.append(
                {
                    "term": phrase,
                    "text": phrase,
                    "source_fact_id": fact_id,
                    "source_fact_ids": [fact_id],
                    "source_skill_ids": [str(skill_id)],
                    "graph_skill_node_ids": [str(skill_id)],
                    "support_class": "FROZEN_RESUME_GRAPH_ALLOCATION",
                    "proof_source": "frozen_allocation_targeted_visible_projection",
                    "allocation_claim_unit_id": claim_unit_id,
                    "allocation_surface_source_field": source_field,
                }
            )
            source_fact_ids = _strings([*source_fact_ids, fact_id])
            graph_skill_ids = _strings([*graph_skill_ids, str(skill_id)])
            claim_unit_ids.append(claim_unit_id)
        category = {
            "category_id": str(spec["category_id"]),
            "category_label": str(spec["category_label"]),
            "resume_display_label": str(spec["resume_display_label"]),
            "competency_bundle_id": bundle_id,
            "capability_family": source_category.get("capability_family"),
            "terms": terms,
            "source_fact_ids": source_fact_ids,
            "graph_skill_node_ids": graph_skill_ids,
            "allocation_claim_unit_ids": claim_unit_ids,
            "confidence": source_category.get("confidence"),
            "selection_score": source_category.get("selection_score"),
            "selector_confidence": source_category.get("selector_confidence"),
            "visible_graph_surface": True,
            "graph_surface_term_source": "frozen_allocation_targeted_visible_projection",
            "resume_display_order_reason": "insurance_it_strategy_frozen_role_episode_layout",
        }
        projected_categories.append(category)
        projected_rows.append(
            {
                "order": order,
                "category_id": category["category_id"],
                "resume_display_label": category["resume_display_label"],
                "competency_bundle_id": bundle_id,
                "generic_anchor": _term_text(generic_anchor),
                "allocation_claim_unit_ids": claim_unit_ids,
                "allocation_terms": [_term_text(term) for term in terms[1:]],
            }
        )

    expected_claim_unit_ids = {
        str(row.get("claim_unit_id") or "") for row in assignments
    }
    projected_claim_unit_ids = {
        str(raw.get("allocation_claim_unit_id") or "")
        for category in projected_categories
        for raw in category.get("terms") or []
        if isinstance(raw, Mapping) and str(raw.get("allocation_claim_unit_id") or "")
    }
    if failure_rows or projected_claim_unit_ids != expected_claim_unit_ids:
        base.update(
            {
                "pass": False,
                "status": "BLOCKED_FROZEN_ALLOCATION_VISIBLE_SURFACE",
                "projection_failures": failure_rows,
                "expected_claim_unit_ids": sorted(expected_claim_unit_ids),
                "projected_claim_unit_ids": sorted(projected_claim_unit_ids),
            }
        )
        base["receipt_digest"] = stable_digest(base)
        return base

    # Commit only after every mapping, authority binding, and exact-once check
    # succeeds.  The categories and legacy display surface intentionally start
    # from independent copies so later V3 synchronization remains one-way.
    parsed["categories"] = copy.deepcopy(projected_categories)
    parsed["competencies"] = copy.deepcopy(projected_categories)
    base.update(
        {
            "pass": True,
            "status": "APPLIED",
            "category_count": len(projected_categories),
            "allocation_claim_unit_count": len(projected_claim_unit_ids),
            "rows": projected_rows,
            "visible_wording_changed": True,
        }
    )
    base["receipt_digest"] = stable_digest(base)
    return base


def reconcile_competencies_allocation_claim_units(
    parsed: dict[str, Any],
    *,
    selected_plan: Mapping[str, Any],
    allowed_fact_ids: set[str],
) -> dict[str, Any]:
    """Bind each competencies allocation unit to one visible term without changing text."""

    assignments = _allocation_assignments(selected_plan)
    categories = [
        row
        for row in parsed.get("competencies") or []
        if isinstance(row, dict)
    ]
    claim_ledger = [
        dict(row)
        for row in parsed.get("claim_ledger") or []
        if isinstance(row, Mapping)
    ]
    root_authority = _authority_by_root(selected_plan)
    candidates: list[dict[str, Any]] = []
    for assignment in assignments:
        for category_index, category in enumerate(categories):
            for term_index, term in enumerate(category.get("terms") or []):
                text = _term_text(term)
                if not text:
                    continue
                assignment_unit_id = str(assignment.get("claim_unit_id") or "")
                explicit_unit_id = (
                    str(term.get("allocation_claim_unit_id") or "").strip()
                    if isinstance(term, Mapping)
                    else ""
                )
                # A term carrying an explicit frozen identity may never be
                # reassigned to a sibling unit by the semantic greedy pass.
                # This was the source of exact-once regressions after recovery:
                # a newly materialized term was correct, then a higher sibling
                # similarity score silently stole it on the second reconcile.
                if explicit_unit_id and explicit_unit_id != assignment_unit_id:
                    continue
                score, reasons = _match_score(
                    assignment,
                    category=category,
                    term=term,
                    root_authority=root_authority,
                )
                if explicit_unit_id == assignment_unit_id and score > 0:
                    score += 1_000_000
                    reasons = ["EXPLICIT_ALLOCATION_CLAIM_UNIT_ID", *reasons]
                if score <= 0:
                    continue
                candidates.append(
                    {
                        "claim_unit_id": str(assignment.get("claim_unit_id") or ""),
                        "category_index": category_index,
                        "term_index": term_index,
                        "score": score,
                        "reasons": reasons,
                        "assignment": assignment,
                    }
                )
    candidates.sort(
        key=lambda row: (
            -int(row["score"]),
            str(row["claim_unit_id"]),
            int(row["category_index"]),
            int(row["term_index"]),
        )
    )
    matched_units: set[str] = set()
    matched_terms: set[tuple[int, int]] = set()
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        unit_id = str(candidate["claim_unit_id"])
        term_key = (int(candidate["category_index"]), int(candidate["term_index"]))
        if unit_id in matched_units or term_key in matched_terms:
            continue
        assignment = candidate["assignment"]
        fact_id = str(assignment.get("fact_id") or "")
        if not fact_id or fact_id not in allowed_fact_ids:
            continue
        category = categories[term_key[0]]
        original = category.get("terms")[term_key[1]]
        term = dict(original) if isinstance(original, Mapping) else {"text": _term_text(original)}
        term["source_fact_id"] = fact_id
        term["source_fact_ids"] = [fact_id]
        term["source_skill_ids"] = _strings(
            [*list(term.get("source_skill_ids") or []), assignment.get("skill_id")]
        )
        term["allocation_claim_unit_id"] = unit_id
        category["terms"][term_key[1]] = term
        category["allocation_claim_unit_ids"] = _strings(
            [*list(category.get("allocation_claim_unit_ids") or []), unit_id]
        )
        matched_units.add(unit_id)
        matched_terms.add(term_key)
        claim_row = next(
            (
                row
                for row in claim_ledger
                if str(row.get("claim_text") or row.get("claim") or "").strip()
                == term["text"]
                and not str(row.get("claim_unit_id") or "").strip()
            ),
            None,
        )
        if claim_row is None:
            claim_row = {"claim_text": term["text"]}
            claim_ledger.append(claim_row)
        claim_row["source_fact_ids"] = [fact_id]
        claim_row["claim_unit_id"] = unit_id
        matches.append(
            {
                "claim_unit_id": unit_id,
                "visible_claim_text": term["text"],
                "category_id": str(
                    category.get("category_id") or category.get("category_label") or ""
                ),
                "skill_id": str(assignment.get("skill_id") or ""),
                "fact_id": fact_id,
                "root_id": str(assignment.get("root_id") or ""),
                "graph_path_ids": _strings(assignment.get("graph_path_ids")),
                "citation_refs": _strings(assignment.get("citation_refs")),
                "score": int(candidate["score"]),
                "match_reasons": list(candidate["reasons"]),
            }
        )
    expected_units = {
        str(row.get("claim_unit_id") or "") for row in assignments if row.get("claim_unit_id")
    }
    unmatched = sorted(expected_units - matched_units)
    receipt: dict[str, Any] = {
        "schema_version": "competencies_allocation_claim_reconciliation_v1",
        "section_id": "competencies",
        "allocation_plan_digest": str(selected_plan.get("allocation_plan_digest") or ""),
        "allocated_claim_unit_count": len(expected_units),
        "matched_claim_unit_count": len(matched_units),
        "matched_visible_term_count": len(matched_terms),
        "unmatched_claim_unit_ids": unmatched,
        "matches": sorted(matches, key=lambda row: row["claim_unit_id"]),
        "visible_wording_changed": False,
        "authority_source": "FROZEN_RESUME_GRAPH_ALLOCATION",
        "pass": bool(expected_units) and not unmatched and len(matches) == len(expected_units),
    }
    receipt["receipt_digest"] = stable_digest(receipt)
    parsed["claim_ledger"] = claim_ledger
    return receipt


def synchronize_competencies_allocation_bindings_to_categories(
    parsed: dict[str, Any],
) -> dict[str, Any]:
    """Copy final allocation provenance from the display mirror to V3 categories.

    ``categories`` is the canonical rich résumé representation used by X2,
    while ``competencies`` remains the legacy display mirror used by the
    allocation reconciler.  The two surfaces have identical visible wording
    after the graph-surface rewrite, but the legacy reconciliation previously
    left the V3 surface with stale source facts.  This bridge copies only
    deterministic graph/allocation provenance for exact text matches; it never
    changes a visible phrase or manufactures a source binding.
    """

    categories = [
        row for row in parsed.get("categories") or [] if isinstance(row, dict)
    ]
    competencies = [
        row for row in parsed.get("competencies") or [] if isinstance(row, dict)
    ]
    category_by_key: dict[str, list[dict[str, Any]]] = {}
    for index, category in enumerate(categories):
        keys = {
            str(category.get("category_id") or "").strip().casefold(),
            str(category.get("category_label") or "").strip().casefold(),
        }
        for key in keys:
            if key:
                category_by_key.setdefault(key, []).append(category)

    copied_claim_unit_ids: list[str] = []
    unmatched: list[dict[str, str]] = []
    for index, legacy_category in enumerate(competencies):
        keys = (
            str(legacy_category.get("category_id") or "").strip().casefold(),
            str(legacy_category.get("category_label") or "").strip().casefold(),
        )
        target: dict[str, Any] | None = None
        for key in keys:
            if category_by_key.get(key):
                target = category_by_key[key][0]
                break
        if target is None and index < len(categories):
            target = categories[index]
        if target is None:
            continue

        target_terms = [
            row for row in target.get("terms") or [] if isinstance(row, dict)
        ]
        used_target_indexes: set[int] = set()
        for legacy_term in legacy_category.get("terms") or []:
            if not isinstance(legacy_term, Mapping):
                continue
            claim_unit_id = str(
                legacy_term.get("allocation_claim_unit_id") or ""
            ).strip()
            if not claim_unit_id:
                continue
            phrase = _term_text(legacy_term).casefold()
            target_index = next(
                (
                    term_index
                    for term_index, target_term in enumerate(target_terms)
                    if term_index not in used_target_indexes
                    and _term_text(target_term).casefold() == phrase
                ),
                None,
            )
            if target_index is None:
                unmatched.append(
                    {
                        "claim_unit_id": claim_unit_id,
                        "phrase": _term_text(legacy_term),
                    }
                )
                continue
            target_term = target_terms[target_index]
            used_target_indexes.add(target_index)
            for field in (
                "source_fact_id",
                "source_fact_ids",
                "source_skill_ids",
                "graph_skill_node_ids",
                "support_class",
                "proof_source",
                "allocation_claim_unit_id",
                "allocation_surface_source_field",
            ):
                if field in legacy_term:
                    target_term[field] = legacy_term[field]
            target["source_fact_ids"] = _strings(
                [
                    *list(target.get("source_fact_ids") or []),
                    *list(legacy_term.get("source_fact_ids") or []),
                    legacy_term.get("source_fact_id"),
                ]
            )
            target["graph_skill_node_ids"] = _strings(
                [
                    *list(target.get("graph_skill_node_ids") or []),
                    *list(legacy_term.get("source_skill_ids") or []),
                    *list(legacy_term.get("graph_skill_node_ids") or []),
                ]
            )
            target["allocation_claim_unit_ids"] = _strings(
                [
                    *list(target.get("allocation_claim_unit_ids") or []),
                    claim_unit_id,
                ]
            )
            copied_claim_unit_ids.append(claim_unit_id)

    receipt: dict[str, Any] = {
        "schema_version": "competencies_allocation_v3_sync_v1",
        "section_id": "competencies",
        "copied_claim_unit_ids": sorted(set(copied_claim_unit_ids)),
        "copied_claim_unit_count": len(set(copied_claim_unit_ids)),
        "unmatched_legacy_bindings": unmatched,
        "visible_wording_changed": False,
        "pass": not unmatched,
    }
    receipt["receipt_digest"] = stable_digest(receipt)
    return receipt


def build_competencies_graph_authority_discrepancy_ledger(
    *,
    selected_plan: Mapping[str, Any],
    proof_pool_metadata: Mapping[str, Any],
    parsed: Mapping[str, Any],
    reconciliation_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Record every authority-eligible graph candidate and its final disposition."""

    assignments = [
        dict(row)
        for row in selected_plan.get("allocation_assignments") or []
        if isinstance(row, Mapping) and row.get("section_id") == "competencies"
    ]
    assertion_by_skill: dict[str, dict[str, Any]] = {}
    for raw in proof_pool_metadata.get("graph_skill_embedding_assertion_bindings") or []:
        if not isinstance(raw, Mapping):
            continue
        skill_id = str(raw.get("skill_id") or "")
        if skill_id:
            assertion_by_skill[skill_id] = dict(raw)
    visible_by_unit = {
        str(row.get("claim_unit_id") or ""): str(row.get("visible_claim_text") or "")
        for row in reconciliation_receipt.get("matches") or []
        if isinstance(row, Mapping)
    }
    rows: list[dict[str, Any]] = []
    for raw in selected_plan.get("graph_candidate_decision_ledger") or []:
        if not isinstance(raw, Mapping) or raw.get("authority_pass") is not True:
            continue
        candidate_id = str(raw.get("candidate_id") or "")
        candidate_type = str(raw.get("candidate_type") or "")
        root_id = str(raw.get("root_id") or candidate_id)
        skill_ids = _strings(
            [candidate_id if candidate_type == "leaf_skill" else "", *list(raw.get("graph_skill_node_ids") or [])]
        )
        metric_ids = _strings(
            [candidate_id if candidate_type == "metric_outcome" else "", *list(raw.get("metric_outcome_ids") or [])]
        )
        fact_ids = _strings(
            [candidate_id if candidate_type == "source_fact" else "", *list(raw.get("linked_source_fact_ids") or [])]
        )
        related_assignments = [
            row
            for row in assignments
            if candidate_id
            in {
                str(row.get("root_id") or ""),
                str(row.get("skill_id") or ""),
                str(row.get("fact_id") or ""),
                str(row.get("metric_outcome_id") or ""),
            }
            or root_id == str(row.get("root_id") or "")
        ]
        assertion = next(
            (assertion_by_skill[skill_id] for skill_id in skill_ids if skill_id in assertion_by_skill),
            {},
        )
        claim_units = _strings(row.get("claim_unit_id") for row in related_assignments)
        authority = raw.get("authority") if isinstance(raw.get("authority"), Mapping) else {}
        rows.append(
            {
                "candidate_id": candidate_id,
                "candidate_type": candidate_type,
                "assertion_id": str(assertion.get("assertion_id") or ""),
                "skill_ids": skill_ids,
                "fact_ids": fact_ids,
                "source_references": _strings(
                    list(raw.get("source_refs") or []) + list(authority.get("source_refs") or [])
                ),
                "graph_paths": _strings(
                    [raw.get("candidate_path_id"), raw.get("path_signature")]
                ),
                "metric_outcome_ids": metric_ids,
                "role_axis_labels": _role_axes(candidate_id, root_id, raw.get("claim_text")),
                "embedding_rank": assertion.get("rank")
                or assertion.get("embedding_rank")
                or assertion.get("dense_rank"),
                "exact_eligibility_result": "ELIGIBLE",
                "allocation_decision": (
                    "ALLOCATED_PRIMARY"
                    if candidate_id
                    in {
                        str(row.get(field) or "")
                        for row in related_assignments
                        for field in ("skill_id", "fact_id", "metric_outcome_id")
                    }
                    else "ALLOCATED_ROOT_AUTHORITY"
                    if related_assignments
                    else "NOT_ALLOCATED"
                ),
                "selector_decision": str(raw.get("decision") or ""),
                "rejection_reason": _strings(raw.get("reason_codes")),
                "allocation_claim_unit_ids": claim_units,
                "visible_claim_unit_usage": [
                    {"claim_unit_id": unit_id, "visible_claim_text": visible_by_unit[unit_id]}
                    for unit_id in claim_units
                    if unit_id in visible_by_unit
                ],
            }
        )
    selected_skills = _strings(selected_plan.get("selected_skill_ids"))
    selected_metrics = _strings(selected_plan.get("selected_metrics"))
    ledger: dict[str, Any] = {
        "schema_version": "competencies_graph_authority_discrepancy_ledger_v1",
        "section_id": "competencies",
        "allocation_plan_digest": str(selected_plan.get("allocation_plan_digest") or ""),
        "eligible_candidate_count": len(rows),
        "selected_unique_leaf_skill_count": len(selected_skills),
        "selected_unique_metric_count": len(selected_metrics),
        "co_sell_authority_ids": sorted(
            candidate_id
            for candidate_id in selected_skills
            if "co_sell" in candidate_id.casefold() or "cosell" in candidate_id.casefold()
        ),
        "allocation_reconciliation_pass": reconciliation_receipt.get("pass") is True,
        "production_graph_mutated": False,
        "rows": rows,
    }
    ledger["ledger_digest"] = stable_digest(ledger)
    return ledger


__all__ = [
    "build_competencies_graph_authority_discrepancy_ledger",
    "insurance_it_strategy_frozen_layout_is_present",
    "materialize_unmatched_competencies_allocation_terms",
    "project_insurance_it_strategy_competencies_from_frozen_allocation",
    "reconcile_competencies_allocation_claim_units",
    "synchronize_competencies_allocation_bindings_to_categories",
]
