"""Unit tests for query-input quality gates, anti-obviousness nuanced answer validation, and 5-layer pool deduplication."""
from __future__ import annotations

from pathlib import Path

from apps_eval.graders.judge.blind_pool_deduplicator import (
    compute_content_jaccard,
    deduplicate_blind_candidates,
    is_clear_reactable_prompt,
    split_prompt_core_and_lineage,
    validate_nuanced_answer_calibration_difficulty,
    validate_query_input_quality,
)
from apps_eval.graders.judge.gold_corpus import (
    FORBIDDEN_BLIND_KEYS,
    build_studio_blind_pool_dict,
    load_gold_candidates_jsonl,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_bare_header_and_keyword_soup_queries_are_rejected() -> None:
    excerpts = [
        {
            "source": "resume_engine:Unify",
            "excerpt": "Generated $22M in IP-led revenue and cut banking regulatory findings by 35%.",
        }
    ]
    assert not is_clear_reactable_prompt(
        "Target Role: SVP of AI Platforms & Forward Deployed Engineering (Regulated Financial Services)"
    )
    ok_bare, reasons_bare = validate_query_input_quality(
        "Target Role: SVP of AI Platforms & Forward Deployed Engineering",
        excerpts,
    )
    assert not ok_bare
    assert any("QUERY_BARE_HEADER_PREFIX" in r for r in reasons_bare)

    ok_good, reasons_good = validate_query_input_quality(
        "Does this Unify Consulting summary preserve factual grounding on the $22M revenue and 35% regulatory reduction?",
        excerpts,
    )
    assert ok_good, reasons_good


def test_obvious_caricature_and_noun_stack_answers_are_rejected() -> None:
    excerpts = [
        {
            "source": "resume_engine:Slalom",
            "excerpt": "Directed $2.4M Anthropic Claude enablement workstream and scaled Gemini Enterprise to 5,750+ seats.",
        },
        {
            "source": "resume_engine:Unify",
            "excerpt": "Generated $22M in IP-led platform revenue and cut banking regulatory findings by 35%.",
        },
    ]

    ok_noun, reasons_noun = validate_nuanced_answer_calibration_difficulty(
        "Runtime Control Plane Orchestration Topology: multi-layer deterministic graph routing policy enforcement mesh and fail-closed telemetry gate architecture for Anthropic Claude.",
        excerpts,
        judge_surface="competencies",
        nuance_profile="DENSE_INSIDER_SHORTHAND_OR_CADENCE",
    )
    assert not ok_noun
    assert any("ANSWER_NOUN_STACK_CARICATURE" in r for r in reasons_noun)

    ok_car, reasons_car = validate_nuanced_answer_calibration_difficulty(
        "Hi Marcus, I am desperately seeking my next role and would be forever grateful if you look at my $2.4M Anthropic Claude workstream! ACT NOW before Q4 closes!",
        excerpts,
        judge_surface="x1d_quorum",
        nuance_profile="FRICTION_OR_PROPORTION_MISMATCH",
    )
    assert not ok_car
    assert any("ANSWER_OBVIOUS_CARICATURE_DEFECT" in r for r in reasons_car)


def test_all_48_curated_gold_candidates_pass_query_nuance_and_studio_dedup() -> None:
    rg = load_gold_candidates_jsonl(REPO_ROOT / "data" / "judge_calibration" / "resume_gold_candidates.v1.jsonl")
    lic = load_gold_candidates_jsonl(REPO_ROOT / "data" / "judge_calibration" / "outreach_gold_candidates.v1.jsonl")
    assert len(rg) == 24 and len(lic) == 24

    for engine, items in (("resume_engine", rg), ("outreach_engine", lic)):
        pool = build_studio_blind_pool_dict(items, engine=engine, repo_root=REPO_ROOT)
        assert pool["schema_version"] == "ide-judge-blind-sample-pool:1.2.0"
        assert pool["sample_count"] == 24
        assert pool["deduplication_stats"]["kept_unique_count"] == 24
        assert pool["deduplication_stats"]["max_observed_prompt_jaccard"] < 0.40
        assert pool["deduplication_stats"]["max_observed_body_jaccard"] < 0.35
        for it in pool["items"]:
            assert not (set(it.keys()) & FORBIDDEN_BLIND_KEYS)
            prompt, core, _ = split_prompt_core_and_lineage(it["core_answer_text"], explicit_prompt=it["prompt_text"])
            assert is_clear_reactable_prompt(prompt)
            assert len(core.split()) >= 10


def test_five_layer_deduplicator_drops_near_duplicates() -> None:
    cands = [
        {
            "case_id": "c1",
            "artifact_sha256": "a" * 64,
            "topic_family": "t1",
            "prompt_text": "Does this Unify Consulting summary ground the $22M revenue and 35% banking regulatory reduction?",
            "core_answer_text": "At Unify Consulting, we generated $22M in IP-led platform revenue and cut banking regulatory findings by 35% across six-month to three-week cycles.",
        },
        {
            "case_id": "c2",
            "artifact_sha256": "b" * 64,
            "topic_family": "t2",
            "prompt_text": "Does this Unify Consulting summary ground the $22M revenue and 35% banking regulatory reduction accurately?",
            "core_answer_text": "Completely distinct candidate answer discussing IBM Partner AWS alliance co-sell revenue growth of 20% across regulated insurance institutions.",
        },
    ]
    assert compute_content_jaccard(cands[0]["prompt_text"], cands[1]["prompt_text"]) >= 0.40
    kept, stats = deduplicate_blind_candidates(cands, max_prompt_jaccard=0.40, max_body_jaccard=0.35)
    assert len(kept) == 1
    assert stats["dropped_near_duplicate_prompt"] == 1
