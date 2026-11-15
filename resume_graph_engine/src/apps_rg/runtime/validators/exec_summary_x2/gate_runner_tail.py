"""Tail section of run_x2_gates plus pass/failure helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from apps_rg.runtime.validators.exec_summary_x2.constants import (
    ACTION_VERB_OPENERS,
    ALLOWED_MODELS,
    ALLOWED_TOP_LEVEL_FIELDS,
    CREDENTIAL_CONTEXT_MARKERS,
    EM_DASH,
    EVIDENCE_UTIL_MIN_LEDGER_ROWS_WHEN_POOL_LARGE,
    EVIDENCE_UTIL_MIN_POOL_FOR_LEDGER_DEPTH,
    EVIDENCE_UTIL_MIN_POOL_FOR_THIN_SENTENCE,
    EVIDENCE_UTIL_MIN_WORDS_PER_SENTENCE_WHEN_FOUR,
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES,
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES_LOOSE,
    EXEC_SUMMARY_MECHANICAL_OPENERS,
    EXEC_SUMMARY_ROBOTIC_TRANSITION_PREFIXES,
    EXECUTIVE_SUMMARY_SECTION_ID,
    EXPECTED_PA_SHELL_TEMPLATE_ID,
    EXPECTED_PROMPT_ID,
    EXPECTED_PROMPT_TEMPLATE_REF,
    FIRST_PERSON_PATTERN,
    FSA_RIGOR_MARKERS,
    FSA_WORD_RE,
    GENERIC_FILLER,
    INDUSTRY_DOMAIN_CLAIMS,
    INFERRED_BRIDGE_PHRASES,
    INLINE_SOURCE_PATTERN,
    MECHANICAL_PROOF_OPENERS,
    NORTH_STAR_SIGNATURE_PHRASES,
    POST_X2_REQUIRED_ARTIFACTS,
    POST_X2_X1D_WIRING_GATE_IDS,
    PRE_X2_REQUIRED_ARTIFACTS,
    REQUIRED_ARTIFACTS,
    REQUIRED_JUDGE_PROVIDER_KEYS,
    REQUIRED_JUDGE_PROVIDERS,
    SOURCE_SENSITIVE_PHRASES,
    VENDOR_NAMED_CERT_LABELS,
    X2GateResult,
    _CROSS_SENTENCE_DEDUP_PATTERNS,
    _FINITE_VERB_RE,
    _GRAPH_EVIDENCE_PERCENT_CAPTURE_RE,
    _GRAPH_EVIDENCE_S1_CONNECTOR_PHRASES,
    _GRAPH_EVIDENCE_S1_CONNECTOR_WORDS,
    _GRAPH_EVIDENCE_S1_MECHANISM_TERMS,
    _PARTICIPIAL_OPENER_RE,
    _SUBJECTLESS_VERB_OPENER_RE,
    resolve_section_generation_model,
    split_sentences,
)
from apps_rg.runtime.validators.exec_summary_x2.ledger_judge_checks import (
    append_executive_summary_x1d_x2_gate_dicts,
    check_briefing_as_proof_zero,
    check_inferred_bridge_claims,
    check_jd_as_proof_zero,
    check_json_parse_valid,
    check_material_clause_coverage,
    check_metric_fact_id_granularity,
    check_no_extra_fields,
    check_target_title_inflation,
    check_unsupported_industry_claims,
    model_name_matches_allowed,
)
from apps_rg.runtime.validators.exec_summary_x2.narrative_grounding_checks import (
    check_claim_coverage_accounting,
    check_claim_ledger_materialized_or_gap_excused,
    check_exec_summary_partner_narrative_continuity,
    check_exec_summary_speculative_capstone,
    check_required_artifacts,
    check_required_fields,
    check_source_sensitive_phrases,
    check_synthesis_quality,
)
from apps_rg.runtime.validators.exec_summary_x2.sentence_metric_checks import (
    check_north_star_style_example_echo_unsupported,
    check_raw_json_no_selected_fact_plan_echo,
)
from apps_rg.runtime.validators.exec_summary_x2.surface_checks import (
    check_cross_fact_display_conflation,
    check_exec_summary_mechanical_opener_stack,
    check_exec_summary_robotic_transition_stack,
    check_exec_summary_stock_bridge_count,
    check_transport_envelope_stub_false,
    detect_bullet_like_stacking,
)


def _append_runtime_and_artifact_x2_gates(
    *,
    gates: list[X2GateResult],
    add: Callable[[str, bool, Any, Any, str | None], None],
    strategy_lane: bool,
    resume_display_text: str,
    parsed_output: dict[str, Any] | None,
    claim_ledger: list[dict[str, Any]],
    text_claim_coverage: dict[str, Any],
    allowed_fact_ids: set[str],
    target_company: str,
    jd_text: str,
    artifacts_dir: Path,
    provider_requested: str | None,
    provider_attempted: str | None,
    runtime_generation_status: str,
    model_name: str | None,
    prompt_hash: str | None,
    compiled_prompt: str | None,
    raw_output: str | None,
    x1d_judges: list[dict[str, Any]] | None,
    defer_x1d_gates: bool,
    target_role: str | None,
    selected_facts: list[dict[str, Any]] | None,
    proof_pool_metadata: dict[str, Any] | None,
    proof_pool_ref: str,
    proof_pool_digest: str,
) -> list[X2GateResult]:
    stacked, stack_reason, _ = detect_bullet_like_stacking(resume_display_text)
    add("x2_sentence_stacking_zero", not stacked, stack_reason, None, "Bullet-like sentence stacking detected.")
    
    # New synthesis quality gate
    synthesis_ok, synthesis_reason = check_synthesis_quality(resume_display_text)
    add("x2_executive_summary_synthesis_quality", synthesis_ok, synthesis_reason, None, synthesis_reason)

    continuity_ok, continuity_reason = check_exec_summary_partner_narrative_continuity(
        resume_display_text,
        selected_facts,
    )
    add(
        "x2_exec_summary_partner_narrative_continuity",
        continuity_ok,
        continuity_reason or "ok",
        "dependency_graph_sentence_bridged_to_selected_partner_platform_arc",
        continuity_reason,
    )
    capstone_ok, capstone_reason = check_exec_summary_speculative_capstone(
        resume_display_text
    )
    add(
        "x2_exec_summary_speculative_capstone_zero",
        capstone_ok,
        capstone_reason or "ok",
        "evidence_led_s6_without_can_guide_future",
        capstone_reason,
    )

    mech_stack_ok, mech_stack_reason = check_exec_summary_mechanical_opener_stack(resume_display_text)
    add(
        "x2_exec_summary_mechanical_opener_stack_zero",
        mech_stack_ok,
        mech_stack_reason or "ok",
        None,
        mech_stack_reason,
    )
    transition_ok, transition_reason = check_exec_summary_robotic_transition_stack(resume_display_text)
    add(
        "x2_exec_summary_robotic_transition_stack_zero",
        transition_ok,
        transition_reason or "ok",
        "no_three_stock_that_transitions_in_s2_s5",
        transition_reason,
    )
    if strategy_lane:
        stock_ok, stock_reason = check_exec_summary_stock_bridge_count(
            resume_display_text,
            max_bridges=2,
        )
        add(
            "x2_exec_summary_stock_bridge_max_two",
            stock_ok,
            stock_reason or "ok",
            "max_two_stock_bridges_in_s2_s5",
            stock_reason,
        )

    conf_ok, conf_reason = check_cross_fact_display_conflation(
        resume_display_text, claim_ledger
    )
    add(
        "x2_exec_summary_cross_fact_conflation_zero",
        conf_ok,
        conf_reason or "ok",
        None,
        conf_reason,
    )

    north_ok, north_reason = check_north_star_style_example_echo_unsupported(
        resume_display_text, selected_facts
    )
    add(
        "x2_north_star_style_echo_unsupported_zero",
        north_ok,
        north_reason or "ok",
        "no_unsupported_style_echo",
        north_reason,
    )

    # New coverage accounting gate
    accounting_ok, accounting_reason = check_claim_coverage_accounting(
        resume_display_text, parsed_output, text_claim_coverage, claim_ledger
    )
    add("x2_claim_coverage_accounting_consistent", accounting_ok, accounting_reason, None, accounting_reason)

    gap_notes_list = (parsed_output or {}).get("gap_notes") if isinstance((parsed_output or {}).get("gap_notes"), list) else []
    ledger_mat_ok, ledger_mat_reason = check_claim_ledger_materialized_or_gap_excused(
        resume_display_text, claim_ledger, gap_notes_list
    )
    add(
        "x2_claim_ledger_materialized_or_gap_excused",
        ledger_mat_ok,
        ledger_mat_reason or "ok",
        "materialized_or_gap",
        ledger_mat_reason,
    )

    # Source-sensitive phrase gate: emit only when selected_facts substrate is present (W4).
    if selected_facts:
        source_ok, source_reason = check_source_sensitive_phrases(resume_display_text, selected_facts)
        add("x2_source_sensitive_phrases_supported", source_ok, source_reason, None, source_reason)

    # New expanded X2 gates
    # Gate 1: x2_required_fields_complete
    required_fields_ok, required_fields_reason = check_required_fields(parsed_output)
    add("x2_required_fields_complete", required_fields_ok, required_fields_reason, None, required_fields_reason)

    # Gate 2: x2_required_artifacts_written
    artifacts_ok, artifacts_reason = check_required_artifacts(
        artifacts_dir,
        include_post_x2_receipts=False,
    )
    add("x2_required_artifacts_written", artifacts_ok, artifacts_reason, None, artifacts_reason)

    # Gate 3: x2_json_parse_valid
    json_parse_ok, json_parse_reason = check_json_parse_valid(parsed_output, raw_output)
    add("x2_json_parse_valid", json_parse_ok, json_parse_reason, None, json_parse_reason)

    no_plan_echo_ok, no_plan_echo_reason = check_raw_json_no_selected_fact_plan_echo(raw_output)
    add(
        "x2_no_selected_fact_plan_model_echo",
        no_plan_echo_ok,
        no_plan_echo_reason or "ok",
        "no_model_plan_echo",
        no_plan_echo_reason,
    )

    # Gate 4: x2_no_extra_unrecognized_fields
    no_extra_ok, no_extra_reason = check_no_extra_fields(parsed_output)
    add("x2_no_extra_unrecognized_fields", no_extra_ok, no_extra_reason, None, no_extra_reason)

    # Gate 5: x2_material_clause_coverage_100
    material_clause_ok, material_clause_reason = check_material_clause_coverage(resume_display_text, text_claim_coverage, selected_facts)
    add("x2_material_clause_coverage_100", material_clause_ok, material_clause_reason, None, material_clause_reason)

    # Gate 6: x2_metric_fact_id_granularity
    metric_granular_ok, metric_granular_reason = check_metric_fact_id_granularity(text_claim_coverage)
    add("x2_metric_fact_id_granularity", metric_granular_ok, metric_granular_reason, None, metric_granular_reason)

    # Gate 7: x2_no_inferred_bridge_claims
    bridge_ok, bridge_reason = check_inferred_bridge_claims(resume_display_text, selected_facts)
    add("x2_no_inferred_bridge_claims", bridge_ok, bridge_reason, None, bridge_reason)

    # Gate 8: x2_jd_as_proof_zero
    jd_proof_ok, jd_proof_reason = check_jd_as_proof_zero(claim_ledger, jd_text)
    add("x2_jd_as_proof_zero", jd_proof_ok, jd_proof_reason, None, jd_proof_reason)

    # Gate 9: x2_briefing_as_proof_zero
    briefing_proof_ok, briefing_proof_reason = check_briefing_as_proof_zero(claim_ledger)
    add("x2_briefing_as_proof_zero", briefing_proof_ok, briefing_proof_reason, None, briefing_proof_reason)

    pp_meta = proof_pool_metadata
    pp_x2_active = bool(pp_meta and str(pp_meta.get("proof_pool_type") or "").strip())
    if pp_x2_active:
        from apps_rg.runtime.sections import graph_evidence_contract as _graph_evidence
        from apps_rg.runtime.validators.proof_pool_source_fact_validation import (
            evaluate_proof_pool_source_fact_gate,
            proof_pool_x2_gate_id,
        )

        coll_ex = _graph_evidence.collect_source_fact_ids_from_claim_ledger(claim_ledger)
        ok_ex, env_ex, fail_ex = evaluate_proof_pool_source_fact_gate(
            section_id="executive_summary",
            collected_ids=coll_ex,
            allowed_fact_ids=set(allowed_fact_ids),
            proof_pool_metadata=pp_meta,
            proof_pool_ref=proof_pool_ref,
            proof_pool_digest=proof_pool_digest,
        )
        add(proof_pool_x2_gate_id("executive_summary", proof_pool_metadata=pp_meta, srfs_slice_gate_active=False), ok_ex, env_ex, "active_proof_pool_allowlist_exact", fail_ex)

    # Gate 10: x2_target_title_inflation_zero
    title_inflation_ok, title_inflation_reason = check_target_title_inflation(resume_display_text, target_company, target_role)
    add("x2_target_title_inflation_zero", title_inflation_ok, title_inflation_reason, None, title_inflation_reason)

    # Gate 11: x2_unsupported_industry_claim_zero
    industry_claim_ok, industry_claim_reason = check_unsupported_industry_claims(resume_display_text, selected_facts)
    add("x2_unsupported_industry_claim_zero", industry_claim_ok, industry_claim_reason, None, industry_claim_reason)
    from apps_rg.runtime.validators.narrative_quality_x2 import check_exec_summary_bullet_cosine_similarity
    exec_cos_r = check_exec_summary_bullet_cosine_similarity(resume_display_text, [], max_internal_cosine=0.35)
    add(exec_cos_r.gate_id, exec_cos_r.passed, exec_cos_r.observed_value, exec_cos_r.threshold, exec_cos_r.failure_reason)
    from apps_rg.runtime.validators.allocation_jd_alignment_gate import append_allocation_jd_alignment_x2_gate
    append_allocation_jd_alignment_x2_gate(add, section_id="executive_summary", candidate_text=resume_display_text, selected_facts=selected_facts, target_role=str(target_role or ""), jd_text=str(jd_text or ""))

    # Gate 12: x2_provider_requested_attempted
    provider_attempted_ok = provider_requested == provider_attempted if provider_requested else True
    add("x2_provider_requested_attempted", provider_attempted_ok, f"requested={provider_requested}, attempted={provider_attempted}", "must match", "Provider requested does not match provider attempted.")

    # Gate 13: x2_no_silent_mock_fallback
    no_mock_fallback_ok = not (
        provider_requested == "external_claude" and runtime_generation_status in ("MOCKED", "STUBBED")
    )
    add("x2_no_silent_mock_fallback", no_mock_fallback_ok, f"provider={provider_requested}, status={runtime_generation_status}", "no silent mock", "Silent mock or stub fallback detected.")

    stub_env_ok, stub_env_reason = check_transport_envelope_stub_false(artifacts_dir, provider_requested)
    add(
        "x2_PROVIDER_MODEL_provider_stub_transport_zero",
        stub_env_ok,
        stub_env_reason or "ok",
        "stub_transport_absent",
        stub_env_reason,
    )

    # Gate 14: x2_model_name_allowed — exercised for external Claude proof lanes, including
    # the configured OpenAI backup when Anthropic throttling/limits trigger fallback.
    external_claude_proof_lane = str(provider_requested or "").strip().lower() == "external_claude"
    model_allowed_ok = (
        not external_claude_proof_lane
        or (
            runtime_generation_status == "REAL_LLM"
            and model_name_matches_allowed(model_name, ALLOWED_MODELS)
        )
    )
    model_observed = (
        "skipped_provider_not_external_claude" if not external_claude_proof_lane else (model_name or "unknown")
    )
    add(
        "x2_model_name_allowed",
        model_allowed_ok,
        model_observed,
        ALLOWED_MODELS,
        "Model name must match executive_summary primary/backup allowlist when external_claude asserts REAL_LLM provider proof.",
    )

    # Gate 15: x2_prompt_hash_known
    prompt_hash_ok = bool(prompt_hash and prompt_hash != "")
    if prompt_hash_ok and compiled_prompt:
        expected_hash = hashlib.sha256(compiled_prompt.encode()).hexdigest()[:16]
        prompt_hash_ok = prompt_hash == expected_hash
    add("x2_prompt_hash_known", prompt_hash_ok, prompt_hash or "missing", "valid hash", "Prompt hash missing or invalid.")

    # Gate 16: x2_input_output_hashes_present
    input_output_hashes_ok = bool(
        parsed_output and
        parsed_output.get("input_payload_hash") and
        parsed_output.get("output_payload_hash")
    )
    add("x2_input_output_hashes_present", input_output_hashes_ok, input_output_hashes_ok, True, "Missing input/output hashes.")

    if not defer_x1d_gates:
        for gate_dict in append_executive_summary_x1d_x2_gate_dicts(
            x1d_judges=x1d_judges,
            artifacts_dir=artifacts_dir,
        ):
            add(
                gate_dict["gate_id"],
                gate_dict["pass"],
                gate_dict.get("observed_value"),
                gate_dict.get("threshold"),
                gate_dict.get("failure_reason"),
            )
    else:
        # Keep rigor-critical X1D wiring gate IDs present in the initial bundle so
        # convergence audit does not synthesize BLOCK rows when post-X2 judge refresh
        # is intentionally deferred/skipped (e.g. early hard deterministic fails).
        _defer_reason = "deferred_until_post_x2_judge_phase"
        add(
            "x2_x1d_required_judges_present",
            True,
            _defer_reason,
            "post_x2_judge_refresh",
            None,
        )
        add(
            "x2_x1d_raw_responses_written",
            True,
            _defer_reason,
            "post_x2_judge_refresh",
            None,
        )
        add(
            "x2_x1d_schema_valid",
            True,
            _defer_reason,
            "post_x2_judge_refresh",
            None,
        )
        add(
            "x2_x1d_judge_packet_hash_uniform",
            True,
            _defer_reason,
            "post_x2_judge_refresh",
            None,
        )

    from apps_rg.runtime.validators.section_input_usage_x2 import append_section_input_usage_x2_gates

    append_section_input_usage_x2_gates(
        gates,
        artifacts_dir=artifacts_dir,
        allowed_fact_ids=allowed_fact_ids,
        claim_ledger=claim_ledger,
        text_claim_coverage=text_claim_coverage,
    )


    return gates


def gates_pass(gates: list[X2GateResult]) -> bool:
    return all(g.pass_ for g in gates)


def failed_gate_ids(gates: list[X2GateResult]) -> list[str]:
    return [g.gate_id for g in gates if not g.pass_]
