"""End-to-end verification of INV-GRAPH-PROMOTION-HYGIENE and 6-JD multi-domain IBM Partner allocation."""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
RG_ROOT = REPO_ROOT / "resume_graph_engine"
RG_SRC = RG_ROOT / "src"
for p in (str(RG_SRC), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from apps_rg.runtime.c0.resume_graph_allocation import (  # noqa: E402
    build_whole_resume_graph_allocation,
    slice_section_plan_for_allocation,
    validate_resume_graph_allocation_plan,
)
from apps_rg.runtime.sections.ibm_bullets.frozen_allocation import (  # noqa: E402
    _materialize_ibm_bullets_from_frozen_allocation,
)
from tools.run_resume_graph_traversal_probe import (  # noqa: E402
    run_resume_graph_traversal_probe,
)
from tools.verify_graph_integrity_and_embeddings import (  # noqa: E402
    verify_graph_promotion_and_bundle_hygiene,
)


SIX_JD_CORPUS: tuple[dict[str, str], ...] = (
    {
        "company": "Truist Financial Corporation",
        "target_role": "Head of Forward Deployed Engineering",
        "jd_text": (
            "Head of Forward Deployed Engineering - Truist Financial Corporation. "
            "Build and lead the Forward Deployed Engineering organization, embed with business "
            "and technology teams as design partners, translate complex workflows into rapid "
            "AI prototypes and production-grade enterprise solutions on AWS, and enforce SR 11-7 "
            "model risk management, auditability, and cybersecurity guardrails."
        ),
        "briefing_text": (
            "Target Role: Head of Forward Deployed Engineering at Truist Financial Corporation. "
            "Emphasize 105-person engineering organization leadership, rapid prototyping to production "
            "activation, governed agentic AI runtime controls, and regulated banking MRM/SR 11-7 compliance."
        ),
        "expected_archetype": "fde_regulated_banking",
    },
    {
        "company": "Citi",
        "target_role": "Managing Director, Firmwide AI Strategy & Cloud Architecture",
        "jd_text": (
            "Citi Institutional Banking - Managing Director, Firmwide AI Strategy & Cloud Architecture. "
            "Lead firmwide AI governance, SR 11-7 model risk management, BCBS 239 data lineage, "
            "AWS cloud modernization, microservices event-driven architectures, and DevSecOps release resilience."
        ),
        "briefing_text": (
            "Target Role: Managing Director, Firmwide AI Strategy & Cloud Architecture at Citi. "
            "Emphasize regulated banking AI governance, BCBS 239 lineage, and AWS cloud modernization."
        ),
        "expected_archetype": "regulated_banking_cloud",
    },
    {
        "company": "Anthropic",
        "target_role": "Manager, Applied AI Architecture & Partnerships",
        "jd_text": (
            "Manager, Applied AI Architecture & Partnerships - Anthropic. "
            "Lead technical partner architecture and co-sell execution across AWS, Google Cloud (Vertex AI / Model Armor), "
            "and strategic GSI/SI partners. Drive joint go-to-market solution blueprints, enterprise customer architecture "
            "workshops, production Claude deployment patterns, and partner-sourced revenue growth."
        ),
        "briefing_text": (
            "Target Role: Manager, Applied AI Architecture & Partnerships at Anthropic. "
            "Emphasize hyperscaler (AWS/GCP) and GSI/SI partner ecosystems, joint co-sell GTM execution, "
            "reusable enterprise architecture blueprints, and executive customer workshops."
        ),
        "expected_archetype": "partnerships_gtm",
    },
    {
        "company": "Brown & Brown Insurance",
        "target_role": "Senior Vice President, IT Strategy & Innovation",
        "jd_text": (
            "Brown & Brown Insurance - Senior Vice President, IT Strategy & Innovation. "
            "Lead enterprise technology strategy, core P&C insurance platform modernization, "
            "underwriting and claims automation, Guidewire policy administration, enterprise architecture, and AI governance."
        ),
        "briefing_text": (
            "Target role: SVP IT Strategy & Innovation at Brown & Brown Insurance. "
            "Emphasize P&C insurance platform modernization, regulated cloud/AI governance, "
            "and enterprise architecture."
        ),
        "expected_archetype": "insurance_it_strategy",
    },
    {
        "company": "Neo4j",
        "target_role": "VP, GraphRAG & Knowledge Graph AI Partnerships",
        "jd_text": (
            "VP, GraphRAG & Knowledge Graph AI Partnerships - Neo4j. "
            "Lead strategic hyperscaler (AWS, GCP, Azure) and GSI/SI partner ecosystems, joint GraphRAG reference "
            "architectures, co-sell GTM execution, enterprise solution accelerators, and partner-sourced ARR growth."
        ),
        "briefing_text": (
            "Target Role: VP, GraphRAG & Knowledge Graph AI Partnerships at Neo4j. "
            "Emphasize AWS/GCP partner co-sell GTM, joint reference architectures, and GraphRAG platform commercialization."
        ),
        "expected_archetype": "partnerships_gtm",
    },
    {
        "company": "Invesco",
        "target_role": "Head of AI & Quantitative Investment Platform Engineering",
        "jd_text": (
            "Head of AI & Quantitative Investment Platform Engineering - Invesco. "
            "Lead enterprise AI platform engineering, quantitative investment decision-support systems, "
            "multi-agent orchestration, cloud data platforms on AWS, and regulated asset-management governance."
        ),
        "briefing_text": (
            "Target Role: Head of AI & Quantitative Investment Platform Engineering at Invesco. "
            "Emphasize quantitative decision support, governed agentic AI architecture, and AWS data modernization."
        ),
        "expected_archetype": "ai_platform_quant",
    },
)


def test_graph_promotion_hygiene_and_traversal_probe() -> None:
    hygiene = verify_graph_promotion_and_bundle_hygiene(REPO_ROOT)
    assert hygiene["status"] == "PASS"
    assert hygiene["unpromoted_archive_facts"] == 0
    assert hygiene["draft_archive_skills"] == 0
    assert hygiene["orphaned_archive_skills"] == 0
    assert hygiene["zero_metric_active_bundles"] == 0
    assert int(hygiene["active_archive_skills_bound"]) >= 100

    probe = run_resume_graph_traversal_probe(max_paths=100)
    assert probe["status"] == "PASS"
    assert probe["archetype_jd_fit_alignment_pass"] is True


def test_six_jd_multi_domain_ibm_partner_and_allocation_benchmark() -> None:
    partner_gtm_roots = {
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "reb_ibm_offering_accelerator_management",
        "reb_ibm_presales_solution_engineering",
        "reb_ibm_customer_success_value_realization",
        "reb_ibm_revenue_sales_target_execution",
    }
    anachronism_tokens = ("genai", "gen ai", "llm", "graphrag", "mcp", "claude", "confluent kafka")

    for spec in SIX_JD_CORPUS:
        bundle = build_whole_resume_graph_allocation(
            repo_root=RG_ROOT,
            target_role=spec["target_role"],
            jd_text=spec["jd_text"],
            briefing_text=spec["briefing_text"],
        )
        plan = bundle["allocation_plan"]
        assert validate_resume_graph_allocation_plan(plan) == [], f"Validation failed for {spec['company']}"
        assert plan["uniqueness_receipt"]["pass"] is True
        assert plan["budget_receipt"]["pass"] is True

        by_slot = {row["claim_unit_id"]: row for row in plan["assignments"]}
        ibm_slots = [by_slot[f"ibm_bullets:bul_ibm_{i:03d}"] for i in range(1, 6)]
        ibm_roots = {row["root_id"] for row in ibm_slots}
        assert len(ibm_roots) == 5, f"Expected 5 distinct IBM roots for {spec['company']}"

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
        for banned in anachronism_tokens:
            assert banned not in rendered_lower, f"Anachronism/quarantined token {banned!r} in IBM bullets for {spec['company']}"

        if spec["expected_archetype"] == "partnerships_gtm":
            assert "reb_ibm_aws_alliance_partner_cosell_gtm" in ibm_roots, (
                f"Expected reb_ibm_aws_alliance_partner_cosell_gtm in ibm_bullets for {spec['company']}"
            )
            assert len(ibm_roots & partner_gtm_roots) >= 4, (
                f"Expected >= 4 IBM Partner/GTM roots for {spec['company']}, got {ibm_roots}"
            )
            assert "reb_ibm_devsecops_release_resilience" not in ibm_roots
            assert "20%" in rendered
            assert "$10m" in rendered_lower
        elif spec["expected_archetype"] == "fde_regulated_banking":
            assert "reb_ibm_aws_alliance_partner_cosell_gtm" not in ibm_roots
            assert "reb_ibm_aws_modernization_architecture" in ibm_roots
