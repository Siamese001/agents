"""Unit tests for pairwise narrative-to-bullet cosine similarity and graph-JD role thesis synthesis."""
# apps-test-model: APP CONTRACT

from __future__ import annotations

from apps_rg.runtime.sections import role_episode_lane
from apps_rg.runtime.validators.narrative_quality_x2 import (
    check_narrative_bullet_cosine_similarity,
    compute_text_cosine_similarity,
)


def test_compute_text_cosine_similarity_measures_content_and_raw_overlap() -> None:
    a = "Led a 105-person organization of software engineers and data leaders for a major energy enterprise."
    b = "Led enterprise AI transformation and 105-engineer practice leadership across client engagements."
    c = "Owned the executive consulting mandate for flagship enterprise modernization and operating models."
    assert compute_text_cosine_similarity(a, b, content_only=True) > compute_text_cosine_similarity(a, c, content_only=True)
    assert compute_text_cosine_similarity(a, a, content_only=False) == 1.0


def test_slalom_narrative_bullet_cosine_similarity_rejects_bullet_recap_and_synthesizes() -> None:
    companion_bullets = "\n".join(
        [
            "- bul_slalom_001: Led a 105-person organization of software engineers and data leaders for a major energy and utility enterprise, owning the full executive client relationship, delivery execution, and sales pipeline across the account.",
            "- bul_slalom_002: Directed agentic AI client delivery as Senior Director, architecting A2A multi-agent orchestration to coordinate distributed agent workflows across enterprise delivery engagements.",
            "- bul_slalom_003: Architected governed runtime scaling with deterministic proof lineage and a safety validation mesh, achieving 100% deterministic gate mesh conformance for safety-critical agent decisions.",
            "- bul_slalom_004: Built reusable enterprise solution accelerators in partnership with cloud hyperscaler ecosystems, establishing a co-innovation model that scaled delivery across engagements.",
        ]
    )
    echo_narrative = (
        "Led enterprise AI transformation at executive scale, uniting multi-agent client delivery, "
        "governed runtime assurance, reusable cloud accelerators, and 105-engineer practice leadership "
        "to make complex modernization executable and trusted."
    )
    echo_gate = check_narrative_bullet_cosine_similarity(
        echo_narrative,
        companion_bullets,
        max_pairwise_cosine=0.28,
        max_pool_cosine=0.38,
        forbid_shared_opener=True,
        forbid_repeated_metrics=True,
    )
    assert echo_gate.passed is False
    assert echo_gate.observed_value["max_pairwise_content_cosine"] > 0.28
    assert echo_gate.observed_value["opener_collisions"] == ["bullet_1:led"]
    assert echo_gate.observed_value["metric_collisions"] == ["bullet_1:105"]

    facts = [
        {
            "fact_id": "reb_slalom_engineering_practice_leadership",
            "claim_text": "Leadership of 105 software engineers and data leaders across a leading energy and utility company, managing all client relationships, delivery execution, and sales pipeline",
            "allowed_graph_evidence_ids": [
                "reb_slalom_engineering_practice_leadership",
                "skill_operating_model_for_agentic_ai",
                "skill_enterprise_workflow_adoption",
                "skill_governed_agentic_systems_architecture",
            ],
        },
        {
            "fact_id": "reb_slalom_agentic_client_delivery",
            "claim_text": "Senior Director agentic AI client delivery and A2A multi-agent orchestration",
            "allowed_graph_evidence_ids": [
                "reb_slalom_agentic_client_delivery",
                "skill_governed_agentic_systems_architecture",
            ],
        },
        {
            "fact_id": "reb_slalom_governed_runtime_scaling",
            "claim_text": "Governed runtime scaling, deterministic proof lineage, and safety validation mesh",
            "allowed_graph_evidence_ids": [
                "reb_slalom_governed_runtime_scaling",
                "skill_runtime_resilience_controls",
            ],
        },
        {
            "fact_id": "reb_slalom_ecosystem_accelerators",
            "claim_text": "Reusable enterprise solution accelerators and cloud partner co-innovation",
            "allowed_graph_evidence_ids": [
                "reb_slalom_ecosystem_accelerators",
                "skill_partner_hyperscaler_cosell",
                "skill_partner_cloud_partner_ecosystem",
            ],
        },
    ]
    allowed = [f["fact_id"] for f in facts]
    synthesized, bound_ids, _, model_used = role_episode_lane._proof_authorized_narrative_from_selection(
        parsed={
            "narrative_sentence": echo_narrative,
            "claim_ledger": [{"claim_text": echo_narrative, "source_fact_ids": allowed}],
        },
        facts=facts,
        allowed=allowed,
        section_id="slalom_narrative",
        companion_bullet_texts=companion_bullets,
    )
    assert model_used is True
    assert set(bound_ids) == set(allowed)
    assert not synthesized.lower().startswith("led ")
    assert "105" not in synthesized

    synth_gate = check_narrative_bullet_cosine_similarity(
        synthesized,
        companion_bullets,
        max_pairwise_cosine=0.28,
        max_pool_cosine=0.38,
        forbid_shared_opener=True,
        forbid_repeated_metrics=True,
    )
    assert synth_gate.passed is True
    assert synth_gate.observed_value["max_pairwise_content_cosine"] <= 0.28
    assert synth_gate.observed_value["pool_content_cosine"] <= 0.38
    assert synth_gate.observed_value["opener_collisions"] == []
    assert synth_gate.observed_value["metric_collisions"] == []


def test_all_role_narratives_within_bullets_and_exec_summary_cosine_similarity() -> None:
    from apps_rg.runtime.validators.narrative_quality_x2 import (
        check_exec_summary_bullet_cosine_similarity,
        check_within_section_bullet_cosine_similarity,
        repair_narrative_bullet_echo_from_graph,
    )

    insurtech_bullets = "\n".join(
        [
            "- bul_insurtech_001: Executed multi-wave AWS migration for monolithic policy administration and insurance platform workloads, classifying core systems by cloud fit and completing dependency-mapped cutover waves for critical billing infrastructure.",
            "- bul_insurtech_002: Implemented regulated AWS cloud security and compliance controls across insurance platform workloads, enforcing IAM least-privilege boundaries, KMS encryption, and audit-ready release gates.",
        ]
    )
    ins_repaired = repair_narrative_bullet_echo_from_graph(
        "Led AWS migration execution across monolithic policy administration and insurance platform workloads, paired with regulated cloud security and encryption controls.",
        facts=[], companion_bullet_texts=insurtech_bullets, section_id="insurtech_narrative",
    )
    assert check_narrative_bullet_cosine_similarity(
        ins_repaired, insurtech_bullets, max_pairwise_cosine=0.35, max_pool_cosine=0.38,
        forbid_shared_opener=True, forbid_repeated_metrics=True,
    ).passed is True

    unify_bullets = "\n".join(
        [
            "- bul_unify_001: Built and scaled Unify's AI consulting and platform engineering practice from 8 to 28 specialists while driving $22M in IP-led platform revenue and 20% gross margin expansion.",
            "- bul_unify_006: Designed and operated the control-plane architecture for an agentic AI platform, embedding governance directly into platform engineering to ensure safe, auditable execution across regulated enterprise deployments.",
        ]
    )
    unify_repaired = repair_narrative_bullet_echo_from_graph(
        "Built and scaled Unify Consulting's governed agentic AI platform and cloud engineering practice, converting reusable architecture IP into repeatable enterprise modernization.",
        facts=[], companion_bullet_texts=unify_bullets, section_id="unify_narrative",
    )
    assert check_narrative_bullet_cosine_similarity(
        unify_repaired, unify_bullets, max_pairwise_cosine=0.35, max_pool_cosine=0.38,
        forbid_shared_opener=True, forbid_repeated_metrics=True,
    ).passed is True

    ibm_bullets = "\n".join(
        [
            "- bul_ibm_001: Architected industry-specific AI, analytics, and cloud modernization reference architectures, establishing governed portfolio views and executive operating cadence for financial-services decision support.",
            "- bul_ibm_002: Led technical pre-sales discovery and solution architecture mapping for enterprise financial-services pursuits, establishing delivery-ready cloud platform blueprints to accelerate deal velocity.",
            "- bul_ibm_003: Owned P&L oversight and quota-aligned solution leadership across enterprise cloud platform pursuits, establishing account-level pipeline operating views to steer client portfolio expansion motions.",
        ]
    )
    assert check_within_section_bullet_cosine_similarity(ibm_bullets, max_pairwise_cosine=0.35).passed is True
    ibm_repaired = repair_narrative_bullet_echo_from_graph(
        "Directed enterprise cloud modernization, DevSecOps release governance, and AWS alliance co-sell execution across regulated financial-services portfolios.",
        facts=[], companion_bullet_texts=ibm_bullets, section_id="ibm_narrative",
    )
    assert check_narrative_bullet_cosine_similarity(
        ibm_repaired, ibm_bullets, max_pairwise_cosine=0.35, max_pool_cosine=0.38,
        forbid_shared_opener=True, forbid_repeated_metrics=True,
    ).passed is True

    exec_sents = [
        "Technology Strategy Executive who aligns governed cloud transformation, enterprise risk discipline, and agentic AI architecture into one IT strategy and digital innovation agenda for regulated enterprises.",
        "Architected control-plane boundaries for multi-agent enterprise workflows, pairing policy-gate auditability with strict cross-family judge governance.",
        "Guided phased cloud portfolio modernizations across regulated banking estates with zero ungrounded claim releases.",
        "Partnered with C-suite risk and engineering leaders to institutionalize a traceable lineage foundation across commercial accounts.",
    ]
    assert "a traceable lineage foundation" in exec_sents[3]
    assert check_exec_summary_bullet_cosine_similarity(
        " ".join(exec_sents), f"{insurtech_bullets}\n{unify_bullets}\n{ibm_bullets}",
        max_pairwise_cosine=0.35, max_internal_cosine=0.35,
    ).passed is True
