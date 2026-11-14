"""Wave 3 unit tests for Candidate Pool Ordering, FactAnchor Entailment, and X2 Gate Unification."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.aggregation.cross_section_x2 import (
    VERDICT_PASS,
    VERDICT_WARN,
    run_cross_section_x2_gates,
)
from apps_rg.runtime.c0.c0_fact_anchor import build_fact_anchor
from apps_rg.runtime.reasoning.bullet_fact_entailment import (
    build_slot_entailment_corpus,
    metric_phrase_entailed_in_text,
)
from apps_rg.runtime.reasoning.employment_bullet_pool import (
    build_employment_targeting_context,
)
from apps_rg.runtime.validators.bullet_quality_floor_x2 import (
    check_bullet_word_floor_and_gerund_rhythm,
    count_participial_gerunds,
)


def _apps_rg_root() -> Path:
    return Path(__file__).resolve().parents[3] / "resume_graph_engine"


def test_fact_anchor_stem_grounding_and_entailment_corpus() -> None:
    anchor = build_fact_anchor(
        {
            "root_id": "reb_unify_enterprise_adoption_revenue",
            "fact_id": "fact_engineering_platform_006",
            "skill_id": "skill_commercialization_ip_revenue",
            "skill_label": "Platform IP Commercialization & Revenue Scaling",
            "employer_lane": "unify",
            "metric_text": "$22M IP-led revenue and 20% gross margin expansion",
            "metric_value": "22",
            "metric_unit": "USD_M",
        },
        repo_root=_apps_rg_root(),
    )
    bullet_text = (
        "Commercialized reusable agentic AI services into platform IP across enterprise accounts, "
        "generating $22M in IP-led revenue and 20% gross margin expansion."
    )
    assert metric_phrase_entailed_in_text(
        "$22M IP-led revenue and 20% gross margin expansion",
        bullet_text,
        min_stem_ratio=0.60,
        fact_anchor=anchor,
    ) is True
    assert metric_phrase_entailed_in_text(
        "",
        bullet_text,
        min_stem_ratio=0.60,
        fact_anchor=anchor,
    ) is True

    selected_fact_plan = {
        "facts": [
            {
                "fact_id": "bul_unify_006",
                "claim_text": "Commercialized reusable agentic AI services",
                "metric_raw": "$22M IP-led revenue",
                "fact_anchor": anchor,
            }
        ]
    }
    corpus = build_slot_entailment_corpus("unify_bullets", selected_fact_plan)
    assert "bul_unify_006" in corpus
    assert "$22M" in corpus["bul_unify_006"]

    targeting_ctx = build_employment_targeting_context(
        {
            "target_title": "SVP Engineering",
            "target_company": "Enterprise AI",
            "jd_text": "Lead agentic AI platform architecture and partner GTM.",
            "briefing": "",
            "allowed_fact_ids": ["bul_unify_006"],
            "selected_fact_plan": selected_fact_plan,
        },
        section_lane="unify_bullets",
    )
    assert "bul_unify_006" in targeting_ctx["slot_fact_anchors"]


def test_bullet_word_floor_18_words_320_char_cap_and_max_2_gerund_rhythm() -> None:
    passing_bullet = (
        "Architected deterministic multi-agent orchestration and GraphRAG retrieval pipelines "
        "across regulated enterprise cloud workloads, cutting production release cycle time "
        "from six months to three weeks."
    )
    res_pass = check_bullet_word_floor_and_gerund_rhythm("bul_unify_001", passing_bullet)
    assert res_pass.passed is True
    assert len(count_participial_gerunds(passing_bullet)) <= 2

    short_bullet = "Architected cloud pipelines and improved release velocity across enterprise teams."
    res_short = check_bullet_word_floor_and_gerund_rhythm("bul_unify_002", short_bullet)
    assert res_short.passed is False
    assert "word_count=" in (res_short.failure_reason or "")

    excess_gerund_bullet = (
        "Architected cloud runtime controls across enterprise accounts, establishing governance, "
        "accelerating deployments, scaling adoption, and reducing operational risk across regions."
    )
    res_gerund = check_bullet_word_floor_and_gerund_rhythm("bul_unify_003", excess_gerund_bullet)
    assert res_gerund.passed is False
    assert "gerund_count=" in (res_gerund.failure_reason or "")


def test_cross_section_x2_enforces_cosine_ceilings_and_gerund_rhythm() -> None:
    clean_resume_blob = {
        "sections": [
            {
                "section_id": "executive_summary",
                "section_kind": "generated_lane",
                "l2_output_snapshot": {
                    "resume_display_text": (
                        "Enterprise AI executive who scales governed multi-agent platforms and hyperscaler alliances "
                        "across Fortune 500 financial and insurance institutions."
                    ),
                    "claim_ledger": [
                        {
                            "claim_text": "Scales governed multi-agent platforms across Fortune 500 institutions.",
                            "source_fact_ids": ["reb_slalom_governed_runtime_scaling"],
                        }
                    ],
                },
            },
            {
                "section_id": "slalom_narrative",
                "section_kind": "generated_lane",
                "l2_output_snapshot": {
                    "narrative_sentence": (
                        "Owned global AI engineering practice strategy and commercial ecosystem charter across "
                        "regulated healthcare, financial services, and technology accounts."
                    ),
                    "claim_ledger": [
                        {
                            "claim_text": "Owned global AI engineering practice strategy across regulated accounts.",
                            "source_fact_ids": ["reb_slalom_engineering_practice_leadership"],
                        }
                    ],
                },
            },
            {
                "section_id": "slalom_bullets",
                "section_kind": "generated_lane",
                "l2_output_snapshot": {
                    "bullets": [
                        {
                            "bullet_id": "bul_slalom_001",
                            "bullet_text": (
                                "Directed multi-partner co-sell motions across Google Cloud, Vertex AI, and Anthropic Claude, "
                                "securing $120M+ total contract value across 50+ enterprise accounts."
                            ),
                            "source_fact_ids": ["bul_slalom_001"],
                        },
                        {
                            "bullet_id": "bul_slalom_002",
                            "bullet_text": (
                                "Engineered bi-temporal knowledge graph and hybrid retrieval architectures for clinical workflows, "
                                "achieving sub-second query latency across distributed hospital networks."
                            ),
                            "source_fact_ids": ["bul_slalom_002"],
                        },
                    ],
                },
            },
        ]
    }
    gates, _, _, _, _ = run_cross_section_x2_gates(
        repo=_apps_rg_root(),
        final_resume_blob=clean_resume_blob,
        fingerprint={"review_lanes": []},
        sealed_index={"pointers": []},
    )
    intent_gate = next(g for g in gates if g.gate_id == "x2_cross_section_section_intent_conflict")
    assert intent_gate.verdict == VERDICT_PASS, f"Unexpected conflicts: {intent_gate.observed}"

    # Inject >2 participial gerunds in a bullet and verify conflict detection
    gerund_blob = {
        "sections": [
            clean_resume_blob["sections"][0],
            clean_resume_blob["sections"][1],
            {
                "section_id": "slalom_bullets",
                "section_kind": "generated_lane",
                "l2_output_snapshot": {
                    "bullets": [
                        {
                            "bullet_id": "bul_slalom_001",
                            "bullet_text": (
                                "Directed multi-partner co-sell motions across Google Cloud, establishing governance, "
                                "accelerating deployments, scaling adoption, and expanding enterprise revenue."
                            ),
                            "source_fact_ids": ["bul_slalom_001"],
                        }
                    ],
                },
            },
        ]
    }
    gates_bad, _, _, _, _ = run_cross_section_x2_gates(
        repo=_apps_rg_root(),
        final_resume_blob=gerund_blob,
        fingerprint={"review_lanes": []},
        sealed_index={"pointers": []},
    )
    intent_gate_bad = next(g for g in gates_bad if g.gate_id == "x2_cross_section_section_intent_conflict")
    assert intent_gate_bad.verdict == VERDICT_WARN
    assert "slalom_bullets_gerund_rhythm_excess" in (intent_gate_bad.observed or [])
