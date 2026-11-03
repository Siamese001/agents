"""Unit tests: synthesis regen bounds and repair prompts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from apps_rg.runtime.sections.executive_summary_lane import (
    _build_synthesis_repair_user,
    _regen_candidate_preferred,
    _shape_failure_count,
    _synthesis_shape_reject_reason,
    retry_provider_for_synthesis,
)
from apps_rg.runtime.sections.executive_summary_repair_policy import (
    SYNTHESIS_REGEN_MAX_ATTEMPTS,
    synthesis_regen_max_attempts,
)

# apps-test-model: APP CONTRACT


def test_synthesis_regen_max_attempts_default_is_three(monkeypatch) -> None:
    monkeypatch.delenv("APPS_RG_EXEC_SUMMARY_SYNTHESIS_REGEN_MAX_ATTEMPTS", raising=False)
    assert synthesis_regen_max_attempts() == SYNTHESIS_REGEN_MAX_ATTEMPTS == 3


def test_synthesis_regen_max_attempts_env_clamped_only_when_caps_enabled(monkeypatch) -> None:
    monkeypatch.delenv("APPS_RG_EXEC_SUMMARY_REGEN_CAPS", raising=False)
    monkeypatch.setenv("APPS_RG_EXEC_SUMMARY_SYNTHESIS_REGEN_MAX_ATTEMPTS", "9")
    assert synthesis_regen_max_attempts() == 9
    monkeypatch.setenv("APPS_RG_EXEC_SUMMARY_REGEN_CAPS", "1")
    assert synthesis_regen_max_attempts() == 3
    monkeypatch.setenv("APPS_RG_EXEC_SUMMARY_SYNTHESIS_REGEN_MAX_ATTEMPTS", "1")
    assert synthesis_regen_max_attempts() == 1


def test_synthesis_regen_receipt_distinguishes_improvement_from_shape_acceptance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import apps_rg.runtime.sections.executive_summary_lane as lane

    monkeypatch.setenv("APPS_RG_EXEC_SUMMARY_SYNTHESIS_REGEN_MAX_ATTEMPTS", "2")
    responses = iter(("retry one", "retry two"))

    def fake_shape(text, *_args, **_kwargs):
        return False, "cross_fact_display_conflation:too_many_source_fact_ids_in_one_sentence"

    def fake_budgeted(*_args, **_kwargs):
        text = next(responses)
        result = SimpleNamespace(
            runtime_generation_status="REAL_LLM",
            raw_model_output=json.dumps(
                {"resume_display_text": text, "claim_ledger": []}
            ),
            to_dict=lambda: {"raw_model_output": text},
        )
        attempt = int(_kwargs["attempt_index"])
        return SimpleNamespace(
            result=result,
            call_id=f"retry-{attempt}",
            dispatch_allowed=True,
            block_reason=None,
        )

    monkeypatch.setattr(lane, "_synthesis_shape_reject_reason", fake_shape)
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_regen_dispatch.budgeted_regen_call",
        fake_budgeted,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_regen_dispatch.mark_regen_call_parse",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_synthesis_monotonic.evaluate_synthesis_regen_monotonicity",
        lambda **_kwargs: (True, {"accepted": True}),
    )

    raw = json.dumps({"resume_display_text": "initial", "claim_ledger": []})
    returned_raw, _, _ = retry_provider_for_synthesis(
        [{"role": "user", "content": "prompt"}],
        {"model": "test"},
        raw,
        {"resume_display_text": "initial", "claim_ledger": []},
        artifact_dir=tmp_path,
    )

    assert returned_raw == raw
    receipt = json.loads(
        (tmp_path / "synthesis_regen_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["accepted"] is False
    assert receipt["reverted_to_first_pass"] is True
    assert receipt["judge_stage_eligible_from_retry"] is False
    assert receipt["initial_candidate_digest"]
    assert receipt["authoritative_candidate_digest"] == receipt["initial_candidate_digest"]
    assert all(
        row["acceptance_scope"] == "MONOTONIC_IMPROVEMENT_ONLY"
        for row in receipt["attempts"]
    )
    assert all(row["shape_gate_snapshot"]["pass"] is False for row in receipt["attempts"])


def test_repair_user_includes_evidence_weave_and_anti_shrink() -> None:
    msg = _build_synthesis_repair_user(
        "claim_ledger_rows_4_with_pool_7_need_at_least_5; sentence 0: mechanism_inventory:6_terms",
        attempt_index=0,
        prior_word_count=102,
        prior_ledger_rows=4,
        last_monotonicity_rejected=True,
    )
    assert "EVIDENCE_WEAVE" in msg
    assert "MECHANISM_CONTROL" in msg
    assert "PRIOR REGEN SHRANK" in msg
    assert "102" in msg


def test_repair_user_treats_mechanism_comma_list_as_mechanism_failure() -> None:
    msg = _build_synthesis_repair_user(
        "sentence 1: mechanism_comma_list; dominant_source_fact=unknown",
        attempt_index=2,
        prior_word_count=128,
        prior_ledger_rows=6,
    )

    assert "MECHANISM_CONTROL" in msg
    assert "two or more commas" in msg


def test_mechanism_comma_list_repair_may_reduce_density_without_false_regression() -> None:
    from apps_rg.runtime.sections.executive_summary_synthesis_monotonic import (
        evaluate_synthesis_regen_monotonicity,
    )

    prior = {
        "resume_display_text": " ".join(["word"] * 128),
        "claim_ledger": [
            {"source_fact_ids": [f"fact_{index}"]} for index in range(6)
        ],
    }
    repaired = {
        "resume_display_text": " ".join(["word"] * 105),
        "claim_ledger": [
            {"source_fact_ids": [f"fact_{index}"]} for index in range(6)
        ],
    }

    accepted, detail = evaluate_synthesis_regen_monotonicity(
        prior_parsed=prior,
        prior_reject_reason="sentence 1: mechanism_comma_list",
        new_parsed=repaired,
    )

    assert accepted is True
    assert detail["prior_needs_prose_tighten"] is True
    assert detail["prior_needs_density_reduction"] is True
    assert detail["shrink_waived"] is True


def test_regen_candidate_preferred_rejects_mono_rejected_shrink_with_lower_fail_count() -> None:
    assert (
        _regen_candidate_preferred(
            new_fail_count=1,
            new_ledger_rows=4,
            new_word_count=62,
            best_fail_count=2,
            best_ledger_rows=5,
            best_word_count=81,
            monotonicity_accepted=False,
        )
        is False
    )


def test_regen_candidate_preferred_accepts_mono_ok_weave_gain() -> None:
    assert (
        _regen_candidate_preferred(
            new_fail_count=2,
            new_ledger_rows=5,
            new_word_count=81,
            best_fail_count=4,
            best_ledger_rows=4,
            best_word_count=74,
            monotonicity_accepted=True,
        )
        is True
    )


def test_build_synthesis_repair_user_includes_conflation_guidance() -> None:
    msg = _build_synthesis_repair_user(
        "cross_fact_display_conflation:platform_and_governance",
        attempt_index=1,
        prior_word_count=80,
        prior_ledger_rows=5,
    )
    assert "fact_governance_003" in msg
    assert "Led/Successfully/Also/Built" in msg


def test_synthesis_shape_rejects_robotic_transition_and_overcompression() -> None:
    text = (
        "Technology strategy executive who led AWS modernization execution for monolithic policy administration and insurance platform workloads across regulated cloud migration. "
        "Through that migration discipline, IBM-AWS alliance co-sell motions for financial-services modernization pair with agentic AI platform control-plane architecture and distributed cloud and data execution infrastructure to align partner GTM with governed runtime delivery. "
        "That operating foundation also connects decision-support data models and BI views to reusable offering accelerators packaging cloud, data, and AI modernization patterns for repeatable client pursuits. "
        "In parallel, insurer and regulatory engagement on cloud controls and data security standards keeps partner-led deployment aligned with adoption requirements. "
        "Building on that governance base, platform productization and IP-led revenue growth scale team capacity while expanding operating margins across partner-enabled programs. "
        "AI partnerships and alliance GTM leadership position continued scale of partner-led AI solution architecture across cloud and GSI ecosystems."
    )
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {
                "claim_text": "s1",
                "source_fact_ids": ["reb_insurtech_aws_migration_execution"],
            },
            {
                "claim_text": "s2",
                "source_fact_ids": [
                    "reb_ibm_aws_alliance_partner_cosell_gtm",
                    "reb_unify_agentic_platform_architecture",
                    "reb_unify_distributed_ecosystem_engineering",
                    "reb_ibm_aws_modernization_architecture",
                ],
            },
        ],
    }

    ok, reason = _synthesis_shape_reject_reason(text, parsed, selected_facts=[])

    assert ok is False
    assert "robotic_transition_stack" in reason
    assert "too_many_source_fact_ids" in reason


def test_build_synthesis_repair_user_includes_robotic_transition_guidance() -> None:
    msg = _build_synthesis_repair_user(
        "robotic_transition_stack:3_in_s2_s5; cross_fact_display_conflation:too_many_source_fact_ids_in_one_sentence",
        attempt_index=0,
        prior_word_count=105,
        prior_ledger_rows=6,
    )
    assert "That operating foundation" in msg
    assert "more than three source_fact_ids" in msg


def test_shape_failure_count_increases_with_more_issues() -> None:
    bad = {
        "resume_display_text": "I am bad. Short. Short.",
        "claim_ledger": [],
    }
    n = _shape_failure_count(bad["resume_display_text"], bad, selected_facts=[])
    assert n >= 2


def test_synthesis_repair_sentence_count_note_fires_on_5_sentences() -> None:
    """sentence_count_note must fire when reject reason names wrong sentence count."""
    reject = (
        "resume_display_text must have exactly 6 sentences; found 5 "
        "(legacy 4–5 and 5–6 bands retired)"
    )
    msg = _build_synthesis_repair_user(
        reject,
        attempt_index=0,
        prior_word_count=85,
        prior_ledger_rows=5,
    )
    assert "SENTENCE COUNT HARD FAIL" in msg, (
        "sentence_count_note must fire when reject reason reports found 5 sentences"
    )
    assert "EXACTLY 6" in msg or "exactly 6" in msg, (
        "sentence_count_note must state EXACTLY 6"
    )
    assert "use 5" not in msg.lower(), (
        "No ambiguous 'use 5' guidance when sentence count failed — gate requires exactly 6"
    )


def test_synthesis_repair_evidence_weave_fires_on_sentences_blob() -> None:
    """utilization_note must fire when 'sentences' appears in reject reason."""
    reject = "Output has 5 sentences; executive synthesis requires exactly 6 sentences"
    msg = _build_synthesis_repair_user(
        reject,
        attempt_index=0,
        prior_word_count=85,
        prior_ledger_rows=5,
    )
    assert "EVIDENCE_WEAVE" in msg, (
        "utilization_note must fire when reject reason contains 'sentences'"
    )
    # Ensure the ambiguous fallback is gone
    assert "use 5 when the pool is tighter" not in msg, (
        "Ambiguous 'use 5 when the pool is tighter' must be removed — gate requires exactly 6"
    )


def test_synthesis_repair_no_ambiguous_fallback_when_count_fails() -> None:
    """'Prefer 6 ... use 5 when tighter' phrase must not appear in any sentence-count failure."""
    for reject in [
        "resume_display_text must have exactly 6 sentences; found 4 (legacy 4–5 and 5–6 bands retired)",
        "Output has 5 sentences; executive synthesis requires exactly 6 sentences",
    ]:
        msg = _build_synthesis_repair_user(
            reject,
            attempt_index=1,
            prior_word_count=90,
            prior_ledger_rows=5,
        )
        assert "use 5 when the pool is tighter" not in msg, (
            f"Ambiguous fallback must be absent for reject: {reject!r}"
        )


def test_pre_synthesis_repairs_resolve_inline_unallocated_metric_and_conflation_without_retry(
    monkeypatch,
) -> None:
    """Wave 1 anti-spin contract: repairable conflation + inline 20% metric must not spin retries or overwrite S3."""
    from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
        APPROVED_NON_STOCK_OPENERS,
        EXEC_SUMMARY_STOCK_BRIDGE_PREFIXES,
    )

    for opener in APPROVED_NON_STOCK_OPENERS:
        low = opener.lower()
        assert not any(low.startswith(prefix) for prefix in EXEC_SUMMARY_STOCK_BRIDGE_PREFIXES)
        assert not low.startswith("that operating foundation")

    selected_fact_plan = {
        "allocation_plan_digest": "digest_wave1",
        "facts": [
            {"fact_id": "reb_ibm_aws_alliance_partner_cosell_gtm", "claim_text": "Led IBM-AWS alliance co-sell motions."},
            {"fact_id": "reb_unify_agentic_platform_architecture", "claim_text": "Architected enterprise agentic AI platform control-plane capabilities."},
            {"fact_id": "reb_unify_platform_commercialization", "claim_text": "Generated $22M in IP-led platform revenue through reusable AI capabilities."},
            {"fact_id": "reb_slalom_cloud_ai_gtm_practice_leadership", "claim_text": "Scaled cloud and AI offering accelerators for repeatable enterprise partner pursuits."},
        ],
        "allocation_assignments": [
            {
                "section_id": "executive_summary",
                "claim_unit_id": "cu_unify_agentic_s1",
                "root_id": "reb_unify_agentic_platform_architecture",
                "fact_id": "reb_unify_agentic_platform_architecture",
                "root_bundle_theme": "Applied AI partnerships executive agentic platform architecture",
                "root_claim_text": "Applied AI partnerships executive aligning agentic platform architecture and hyperscaler co-sell execution.",
                "claim_entailment_score": 0.96,
                "target_alignment_score": 0.95,
                "metric_value": "",
                "metric_unit": "",
            },
            {
                "section_id": "executive_summary",
                "claim_unit_id": "cu_ibm_cosell_s2",
                "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "fact_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "root_bundle_theme": "IBM AWS alliance partner co-sell financial-services modernization",
                "root_claim_text": "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities.",
                "claim_entailment_score": 0.95,
                "target_alignment_score": 0.94,
                "metric_value": "",
                "metric_unit": "",
            },
            {
                "section_id": "executive_summary",
                "claim_unit_id": "cu_ibm_cosell_s3",
                "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "fact_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "skill_id": "skill_ibm_alliance_cadence",
                "root_bundle_theme": "AI-driven sales frameworks alliance cadence joint revenue growth partner channels",
                "root_claim_text": "Paired AI-driven sales frameworks with an alliance cadence across partner channels.",
                "claim_entailment_score": 0.94,
                "target_alignment_score": 0.93,
                "metric_value": "",
                "metric_unit": "",
            },
            {
                "section_id": "executive_summary",
                "claim_unit_id": "cu_unify_agentic_s4",
                "root_id": "reb_unify_agentic_platform_architecture",
                "fact_id": "reb_unify_agentic_platform_architecture",
                "skill_id": "skill_unify_control_plane",
                "root_bundle_theme": "Enterprise agentic AI platform control-plane governed model orchestration",
                "root_claim_text": "Architected enterprise agentic AI platform control-plane capabilities across cloud deployments.",
                "claim_entailment_score": 0.96,
                "target_alignment_score": 0.95,
                "metric_value": "",
                "metric_unit": "",
            },
            {
                "section_id": "executive_summary",
                "claim_unit_id": "cu_unify_22m_s5",
                "root_id": "reb_unify_platform_commercialization",
                "fact_id": "reb_unify_platform_commercialization",
                "metric_outcome_id": "metric_unify_22m_ip_revenue",
                "root_bundle_theme": "Unify platform productization IP-led platform revenue",
                "root_claim_text": "Generated $22M in IP-led platform revenue through reusable AI capabilities.",
                "claim_entailment_score": 0.97,
                "target_alignment_score": 0.96,
                "metric_value": "22",
                "metric_unit": "USD_M",
            },
            {
                "section_id": "executive_summary",
                "claim_unit_id": "cu_slalom_gtm_s6",
                "root_id": "reb_slalom_cloud_ai_gtm_practice_leadership",
                "fact_id": "reb_slalom_cloud_ai_gtm_practice_leadership",
                "root_bundle_theme": "Slalom reusable AI offering accelerators ecosystem architecture adoption",
                "root_claim_text": "Scaled cloud and AI offering accelerators for repeatable enterprise partner pursuits.",
                "claim_entailment_score": 0.93,
                "target_alignment_score": 0.92,
                "metric_value": "",
                "metric_unit": "",
            },
        ],
    }

    s1 = "Applied AI partnerships executive aligning agentic platform architecture and hyperscaler co-sell execution across enterprise ecosystems."
    s2 = "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities."
    s3 = "Building on that foundation, IBM-AWS alliance co-sell motions paired with AI-driven sales frameworks and an alliance cadence drove 20% joint revenue growth across partner channels."
    s4 = "In parallel, enterprise agentic AI platform control-plane capabilities standardized governed model orchestration across cloud deployments."
    s5 = "That platform productization discipline generated $22M in IP-led platform revenue across enterprise programs."
    s6 = "Reusable AI offering accelerators and partner co-sell governance position ecosystem architecture teams to scale enterprise AI adoption."
    initial_text = f"{s1} {s2} {s3} {s4} {s5} {s6}"
    initial_parsed = {
        "executive_strategy_thesis": s1,
        "resume_display_text": initial_text,
        "claim_ledger": [
            {"claim_text": s1, "source_fact_ids": ["reb_unify_agentic_platform_architecture"]},
            {"claim_text": s2, "source_fact_ids": ["reb_ibm_aws_alliance_partner_cosell_gtm"]},
            {
                "claim_text": s3,
                "source_fact_ids": [
                    "reb_ibm_aws_alliance_partner_cosell_gtm",
                    "skill_ibm_alliance_cadence",
                    "reb_unify_agentic_platform_architecture",
                    "reb_slalom_cloud_ai_gtm_practice_leadership",
                ],
            },
            {"claim_text": s4, "source_fact_ids": ["reb_unify_agentic_platform_architecture", "skill_unify_control_plane"]},
            {
                "claim_text": s5,
                "source_fact_ids": ["reb_unify_platform_commercialization", "metric_unify_22m_ip_revenue"],
            },
            {"claim_text": s6, "source_fact_ids": ["reb_slalom_cloud_ai_gtm_practice_leadership"]},
        ],
    }

    regen_calls = {"count": 0}

    def fail_if_dispatched(*_args, **_kwargs):
        regen_calls["count"] += 1
        raise AssertionError("budgeted_regen_call should not be invoked when deterministic repair closes shape gates")

    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_regen_dispatch.budgeted_regen_call",
        fail_if_dispatched,
    )

    _, out_parsed, err = retry_provider_for_synthesis(
        [{"role": "user", "content": "prompt"}],
        {"model": "test"},
        json.dumps(initial_parsed),
        initial_parsed,
        selected_facts=selected_fact_plan["facts"],
        selected_fact_plan=selected_fact_plan,
    )

    assert err == ""
    assert regen_calls["count"] == 0
    repaired_s3 = out_parsed["claim_ledger"][2]["claim_text"]
    assert "20%" not in repaired_s3
    assert "drove joint revenue growth across partner channels." in repaired_s3
    assert repaired_s3 != s2
    assert len(out_parsed["claim_ledger"][2]["source_fact_ids"]) <= 2


def test_inline_unallocated_metric_scrub_normalizes_indefinite_articles() -> None:
    """Stripping '20% ' from 'drove a 20% increase' must repair 'a increase' to 'an increase'."""
    from apps_rg.runtime.sections.section_authority_repairs import (
        repair_exec_summary_unallocated_metric_rows,
    )

    selected_fact_plan = {
        "allocation_plan_digest": "digest_article_norm",
        "facts": [
            {
                "fact_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "role_episode_bundle_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "allowed_graph_evidence_ids": [
                    "reb_ibm_aws_alliance_partner_cosell_gtm",
                    "skill_partner_partner_led_ai_solutions",
                    "metric_ibm_20pct_joint_revenue_growth",
                ],
            }
        ],
        "allocation_assignments": [
            {
                "section_id": "executive_summary",
                "claim_unit_id": "cu_ibm_cosell",
                "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "fact_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "root_bundle_theme": "IBM AWS alliance partner co-sell joint revenue growth",
                "root_claim_text": "Led IBM-AWS alliance co-sell motions for financial-services modernization.",
                "claim_entailment_score": 0.95,
                "target_alignment_score": 0.94,
                "metric_value": "",
                "metric_unit": "",
            },
        ],
    }
    s1 = "Applied AI partnerships leader aligning hyperscaler co-sell execution with governed platform commercialization."
    s2 = "Within that ecosystem model, IBM-AWS alliance co-sell motions drove a 20% increase in joint revenue growth through sustained cadence."
    s3 = "In parallel, governed platform standards achieved an 18% reduction in partner onboarding friction across cloud ecosystems."
    s4 = "Complementing that alliance foundation, partner-led AI solutions and cloud-vendor joint go-to-market plays drove joint revenue growth of 20% across the partner channel."
    parsed = {
        "resume_display_text": f"{s1} {s2} {s3} {s4}",
        "selected_fact_plan": selected_fact_plan,
        "claim_ledger": [
            {"claim_text": s1, "source_fact_ids": ["reb_ibm_aws_alliance_partner_cosell_gtm"]},
            {"claim_text": s2, "source_fact_ids": ["reb_ibm_aws_alliance_partner_cosell_gtm"]},
            {"claim_text": s3, "source_fact_ids": ["reb_ibm_aws_alliance_partner_cosell_gtm"]},
            {
                "claim_text": s4,
                "source_fact_ids": [
                    "skill_partner_partner_led_ai_solutions",
                    "metric_ibm_20pct_joint_revenue_growth",
                ],
            },
        ],
    }

    repairs = repair_exec_summary_unallocated_metric_rows(parsed)

    assert len(repairs) == 3
    assert "drove an increase in joint revenue growth" in parsed["resume_display_text"]
    assert "a increase" not in parsed["resume_display_text"]
    assert "achieved a reduction in partner onboarding friction" in parsed["resume_display_text"]
    assert "an reduction" not in parsed["resume_display_text"]
    assert "drove joint revenue growth across the partner channel." in parsed["resume_display_text"]
    assert "of 20%" not in parsed["resume_display_text"]


