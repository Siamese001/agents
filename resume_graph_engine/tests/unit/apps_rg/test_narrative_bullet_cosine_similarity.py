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
