"""Wave 5 verification: role-routed actuarial elevation, 21-profile coverage, and ATS formatting."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    ROLE_FAMILY_TRACK_WEIGHTS,
    SENIOR_ROLE_TAXONOMY_IDS,
    blend_top_k_track_weights,
)
from apps_rg.runtime.c0.competencies_surface_synthesis import (
    format_ats_canonical_skill_phrase,
)
from apps_rg.runtime.c0.mandate_routing_engine import (
    MandateRoutingEngine,
)
from apps_rg.runtime.sections.competency_capability_evidence import (
    AGENTIC_ENGINEERING_COMPETENCIES_BUNDLE_ORDER,
    INSURANCE_IT_STRATEGY_COMPETENCIES_BUNDLE_ORDER,
    PARTNERSHIP_FIRST_COMPETENCIES_BUNDLE_ORDER,
)
from apps_rg.runtime.sections.headline_positioning_registry import (
    REQUIRED_POSITIONING_FAMILIES,
    get_bundle_by_id,
    validate_bundle,
)
from apps_rg.runtime.validators.competencies_quality_x2 import (
    REQUIRED_CAPABILITY_FAMILIES,
    _BUNDLE_ID_TO_REQUIRED_CAPABILITY_FAMILY,
    _GRAPH_FAMILY_TO_REQUIRED_CAPABILITY_FAMILY,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DB_PATH = REPO_ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"


def test_role_routed_actuarial_elevation_and_general_tech_restraint() -> None:
    engine = MandateRoutingEngine(repo_root=REPO_ROOT)

    # Insurance / Risk Chief AI Officer mandate elevates actuarial track & canonical credentials.
    ins_route = engine.route(
        target_role="Chief AI Officer, Regulated Insurance",
        jd_text=(
            "Lead enterprise AI governance, Solvency II capital modeling, AG43 reserving, "
            "Guidewire claims underwriting modernization, and FSA actuarial risk oversight on AWS."
        ),
    )
    assert ins_route.track_weights["track_actuarial_risk_derivatives"] >= 0.22
    assert "cert_fsa_001" in ins_route.credential_elevation_ids
    assert "edu_columbia_ms_001" in ins_route.credential_elevation_ids
    assert "cert_aws_sa_pro_001" in ins_route.credential_elevation_ids
    # No legacy non-existent credential IDs emitted.
    assert "edu_columbia_ms_biostat_001" not in ins_route.credential_elevation_ids
    assert "cert_aws_sap_001" not in ins_route.credential_elevation_ids

    # Pure general tech/cloud SVP Engineering mandate stays focused on platform & AI leadership.
    tech_route = engine.route(
        target_role="SVP of Software Engineering",
        jd_text=(
            "Scale multi-agent LLM platforms, distributed cloud microservices on AWS, "
            "platform reliability engineering, and 100+ engineer delivery organizations."
        ),
    )
    assert tech_route.canonical_projection_role == "SVP_ENGINEERING_AI_PLATFORM"
    assert tech_route.track_weights["track_actuarial_risk_derivatives"] <= 0.12
    assert tech_route.track_weights["track_actuarial_risk_derivatives"] >= 0.08
    assert "cert_aws_sa_pro_001" in tech_route.credential_elevation_ids
    assert "cert_fsa_001" not in tech_route.credential_elevation_ids
    # Early-career compact layout preserved.
    assert tech_route.slot_budget_profile["ey_bullets"] == 1
    assert tech_route.slot_budget_profile["early_career_bullets"] == 1


def test_insurance_competency_ranking_and_runtime_governance_family_alignment() -> None:
    # ccb_insurance_domain_erm is promoted to top-2 on insurance mandates only.
    assert INSURANCE_IT_STRATEGY_COMPETENCIES_BUNDLE_ORDER.index("ccb_insurance_domain_erm") == 1
    assert AGENTIC_ENGINEERING_COMPETENCIES_BUNDLE_ORDER[-1] == "ccb_insurance_domain_erm"
    assert PARTNERSHIP_FIRST_COMPETENCIES_BUNDLE_ORDER[-1] == "ccb_insurance_domain_erm"

    # Family mapping fixed from distributed_infra to runtime_governance.
    assert _BUNDLE_ID_TO_REQUIRED_CAPABILITY_FAMILY["ccb_insurance_domain_erm"] == "runtime_governance"
    assert _GRAPH_FAMILY_TO_REQUIRED_CAPABILITY_FAMILY["insurance_domain_modernization"] == "runtime_governance"
    rg_tokens = REQUIRED_CAPABILITY_FAMILIES["runtime_governance"]
    for tok in ("actuarial", "solvency", "ag43", "fsa", "erm", "guidewire"):
        assert tok in rg_tokens


def test_actuarial_headline_positioning_bundle_and_21_profile_projection() -> None:
    assert "quantitative_actuarial_ai_governance" in REQUIRED_POSITIONING_FAMILIES
    bundle = get_bundle_by_id("hpb_quantitative_actuarial_ai_governance")
    assert bundle is not None
    ok, violations = validate_bundle(bundle)
    assert ok, f"Invalid headline bundle: {violations}"
    assert "ccb_insurance_domain_erm" in bundle["source_competency_bundle_ids"]
    assert "fact_certs_001" in bundle["linked_source_fact_ids"]
    assert "fact_rag_insurance_001" in bundle["linked_source_fact_ids"]

    # All 5 previously missing taxonomy profiles are now in SENIOR_ROLE_TAXONOMY_IDS.
    for key in (
        "HEALTHCARE_PAYER_DATA_AI",
        "PE_OPERATING_PARTNER_TRANSFORMATION",
        "AI_FINANCIAL_SERVICES",
        "CHIEF_REVENUE_OFFICER_COMPOSITE",
        "THREE_PHASE_GENERALIST",
    ):
        assert key in SENIOR_ROLE_TAXONOMY_IDS

    # Convex top-K persona blending produces valid normalized weights.
    blended = blend_top_k_track_weights(
        {
            "INSURANCE_CARRIER_TRANSFORMATION": 0.6,
            "REGULATED_AI_GOVERNANCE": 0.3,
            "SVP_ENGINEERING_AI_PLATFORM": 0.1,
        },
        top_k=3,
    )
    assert abs(sum(blended.values()) - 1.0) <= 0.002
    assert blended["track_actuarial_risk_derivatives"] >= 0.30

    # SQLite role_family_projection covers all 21 ROLE_FAMILY_TRACK_WEIGHTS keys.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        projected = {
            row[0]
            for row in conn.execute(
                "SELECT projection_role_family_key FROM role_family_projection"
            ).fetchall()
        }
    finally:
        conn.close()
    missing = set(ROLE_FAMILY_TRACK_WEIGHTS) - projected
    assert not missing, f"Missing SQLite role_family_projection profiles: {sorted(missing)}"


def test_ats_canonical_skill_phrase_and_first_mention_acronym_pairing() -> None:
    seen: set[str] = set()
    first = format_ats_canonical_skill_phrase(
        "fsa actuarial erm governance",
        expand_first_mention=True,
        seen_acronyms=seen,
    )
    assert "Fellow of the Society of Actuaries (FSA)" in first
    assert "Enterprise Risk Management (ERM)" in first
    assert {"FSA", "ERM"} <= seen

    second = format_ats_canonical_skill_phrase(
        "fsa rag architecture",
        expand_first_mention=True,
        seen_acronyms=seen,
    )
    assert "Fellow of the Society of Actuaries (FSA)" not in second
    assert "FSA" in second
    assert "Retrieval-Augmented Generation (RAG)" in second

    compact = format_ats_canonical_skill_phrase(
        "enterprise_risk_management_erm_for_regulated_insurers_extra",
        expand_first_mention=False,
        max_words=5,
    )
    assert len(compact.split()) <= 5
    assert "ERM" in compact
