"""Unit tests: graph-backed C0 painting-plan metadata, narrative echo repair, and competency surface."""

from __future__ import annotations

from apps_rg.runtime.sections.executive_summary_composition import (
    build_executive_summary_composition_plan,
    build_sentence_arc,
    check_brushstroke_fact_support,
    check_composition_plan_present,
    check_dominant_brushstroke_coherence,
    check_graph_skill_coverage,
    check_mechanism_inventory_control,
    check_s1_dominant_brushstroke_thesis,
    is_mechanism_inventory_sentence,
)


def _facts() -> list[dict[str, object]]:
    return [
        {
            "fact_id": "fact_engineering_platform_001",
            "claim_text": (
                "Architected governed agentic AI platforms with deterministic routing, "
                "multi-agent orchestration, and GraphRAG retrieval."
            ),
        },
        {
            "fact_id": "fact_governance_003",
            "claim_text": "Implemented Basel III / CCAR data lineage and automated validation frameworks.",
        },
    ]


def test_s1_light_routing_qualifier_passes() -> None:
    s1 = (
        "Engineering executive building governed agentic AI platforms with routing discipline "
        "for regulated enterprise environments."
    )
    ok, reason = check_s1_dominant_brushstroke_thesis(s1)
    assert ok is True, reason


def test_s1_mechanism_list_fails() -> None:
    s1 = (
        "Engineering executive operationalizing platforms through deterministic routing, "
        "retrieval, and telemetry across the enterprise."
    )
    ok, reason = check_s1_dominant_brushstroke_thesis(s1)
    assert ok is False
    assert reason


def test_s1_through_routing_retrieval_telemetry_inventory_fails() -> None:
    s1 = (
        "Leader improving delivery through deterministic routing, retrieval, and telemetry "
        "while scaling programs."
    )
    inv, _ = is_mechanism_inventory_sentence(s1)
    assert inv is True
    ok, _ = check_mechanism_inventory_control(s1 + " Second. Third. Fourth.")
    assert ok is False


def test_composition_plan_missing_graph_refs_fails_when_claimed() -> None:
    plan = {
        "composition_style": "executive_painting",
        "brushstrokes": [{"brushstroke_id": "B1", "support_status": "SUPPORTED", "required_fact_ids": []}],
        "graph_skill_refs": [],
        "graph_backed_composition_claimed": True,
    }
    ok, reason = check_graph_skill_coverage(plan, {"graph_skill_refs": []})
    assert ok is False
    assert reason


def test_brushstroke_unsupported_fact_fails() -> None:
    plan = build_executive_summary_composition_plan(
        selected_facts=_facts(),
        allowed_fact_ids={"fact_engineering_platform_001", "fact_governance_003"},
        target_role="SVP Engineering",
        target_company="Brown & Brown",
    )
    for bs in plan["brushstrokes"]:
        if isinstance(bs, dict) and bs.get("brushstroke_id") == "B1_executive_identity":
            bs["support_status"] = "UNSUPPORTED"
    ledger = [{"claim_text": "x", "source_fact_ids": ["fact_governance_003"]}]
    ok, reason = check_brushstroke_fact_support(
        plan, ledger, {"fact_governance_003", "fact_engineering_platform_001"}
    )
    assert ok is False
    assert reason


def test_composition_plan_present_requires_artifact_fields() -> None:
    ok, reason = check_composition_plan_present(
        {"executive_summary_composition_plan": {"composition_style": "executive_painting", "brushstrokes": []}},
        artifacts_dir=None,
        proof_pool_metadata={"graph_skills_proof_pool": True, "proof_pool_type": "augmented_skills_graph"},
    )
    assert ok is False
    assert reason


def test_build_sentence_arc_v2_fits_3_to_4_sentence_band() -> None:
    arc = build_sentence_arc(target_role="VP Engineering", strategy_executive=False)
    assert 3 <= len(arc) <= 4
    assert arc[0]["brushstroke_id"] == "B1_executive_identity"


def test_dominant_brushstroke_coherence_passes_thesis() -> None:
    plan = build_executive_summary_composition_plan(
        selected_facts=_facts(),
        allowed_fact_ids={"fact_engineering_platform_001"},
        target_role="SVP",
        target_company="Corp",
    )
    text = (
        "Engineering executive building governed agentic platforms for regulated enterprises. "
        "Architected routing and orchestration with GraphRAG retrieval. "
        "Leads lifecycle commercialization across programs. "
        "Delivered proof-backed outcomes across enterprise deployments."
    )
    ok, _ = check_dominant_brushstroke_coherence(text, plan)
    assert ok is True


def test_execution_fact_id_does_not_misclassify_as_b1_and_ai_partnerships_populates_all_brushstrokes() -> None:
    from apps_rg.runtime.sections.executive_summary_composition import _classify_fact_brushstroke_role

    assert (
        _classify_fact_brushstroke_role(
            "fact_insurtech_aws_migration_execution",
            "Led AWS modernization execution for monolithic policy administration workloads.",
        )
        != "B1_executive_identity"
    )
    partner_facts = [
        {
            "fact_id": "fact_unify_platform_commercialization",
            "role_episode_bundle_id": "reb_unify_platform_commercialization_leadership",
            "claim_text": "Led platform productization and governed delivery across enterprise AI programs, generating $22M in IP-led platform revenue.",
            "metric_raw": "$22M IP-led revenue",
        },
        {
            "fact_id": "fact_ibm_aws_alliance_cosell",
            "role_episode_bundle_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
            "claim_text": "Built AWS strategic alliance co-sell motion and solution architecture playbooks for enterprise adoption.",
        },
        {
            "fact_id": "fact_unify_partner_cosell",
            "role_episode_bundle_id": "reb_unify_partner_channel_cosell",
            "claim_text": "Scaled GSI and hyperscaler partner channel enablement with repeatable architecture standards.",
        },
    ]
    allowed_ids = {f["fact_id"] for f in partner_facts}
    plan = build_executive_summary_composition_plan(
        selected_facts=partner_facts,
        allowed_fact_ids=allowed_ids,
        target_role="Manager of Applied AI Architecture, Partnerships",
        target_company="Anthropic",
        jd_text="Partner solution architecture, GSI/SI co-sell enablement, enterprise AI deployment.",
    )
    assert plan["role_archetype"] == "ai_partnerships"
    assert plan["brushstroke_missing_ids"] == []
    assert all(bs["support_status"] == "SUPPORTED" for bs in plan["brushstrokes"])
    assert plan["sentence_arc"][0]["arc_role"] == "partnerships_thesis"


def test_slalom_narrative_echo_repair_avoids_cosell() -> None:
    from apps_rg.runtime.validators.narrative_quality_x2 import (
        repair_narrative_bullet_echo_from_graph,
    )

    slalom_text = (
        "Led a 105-person data and AI engineering organization at Slalom. "
        "Delivered enterprise lakehouse platforms across Fortune 500 clients."
    )
    slalom_repaired = repair_narrative_bullet_echo_from_graph(
        slalom_text,
        facts=[
            {
                "fact_id": "reb_slalom_agentic_client_delivery",
                "claim_text": "Directed forward-deployed multi-agent AI engineering delivery across 30+ Fortune 500 accounts.",
            }
        ],
        companion_bullet_texts="Delivered enterprise lakehouse platforms across Fortune 500 clients.",
        section_id="slalom_narrative",
    )
    assert "co-sell" not in slalom_repaired.lower()
    assert "multi-agent workflow orchestration" in slalom_repaired.lower()


def test_competencies_visible_graph_surface_svp_agentic_engineering_avoids_partner_label() -> None:
    from apps_rg.runtime.sections.competency_capability_evidence import (
        enrich_competencies_visible_graph_surface,
    )

    parsed: dict = {
        "competencies": [
            {
                "category_id": "cat_partner",
                "category_label": "Partner Applied AI Architecture",
                "competency_bundle_id": "ccb_partner_applied_ai_architecture",
                "terms": [{"term": "partner-ready applied AI reference architectures"}],
            },
            {
                "category_id": "cat_agentic",
                "category_label": "Agentic AI Platforms",
                "competency_bundle_id": "ccb_agentic_platforms",
                "terms": [{"term": "governed multi-agent orchestration control planes"}],
            },
        ]
    }
    receipt = enrich_competencies_visible_graph_surface(
        parsed,
        packet=None,
        allowed_fact_ids={"reb_unify_agentic_platform_architecture"},
        selected_graph_evidence_plan={
            "target_role_profile": "svp_agentic_engineering",
            "facts": [{"fact_id": "reb_unify_agentic_platform_architecture"}],
        },
    )
    assert receipt["order_policy"] == "svp_agentic_engineering_relevance_first"
    comps = parsed["competencies"]
    assert comps[0]["competency_bundle_id"] == "ccb_agentic_platforms"
    assert comps[1]["competency_bundle_id"] == "ccb_partner_applied_ai_architecture"
    assert comps[1]["resume_display_label"] == "Applied AI Reference Architecture & Enablement"
    terms_blob = " ".join(str(t.get("term") or "") for t in comps[1]["terms"]).lower()
    assert "partner" not in terms_blob
    assert "reference" in terms_blob
    assert "accelerators" in terms_blob
    assert "enablement" in terms_blob
