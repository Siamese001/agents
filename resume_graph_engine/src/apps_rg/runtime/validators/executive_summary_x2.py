"""Deterministic X2 gates for executive summary runtime slice."""
from __future__ import annotations

EXEC_SUMMARY_MIN_SENTENCES = 4
EXEC_SUMMARY_TARGET_SENTENCES = 5
EXEC_SUMMARY_MAX_SENTENCES = 6
EXEC_SUMMARY_MAX_WORDS = 150
EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE = 45

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
    EXECUTIVE_SUMMARY_SECTION_ID,
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES,
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES_LOOSE,
    EXEC_SUMMARY_MECHANICAL_OPENERS,
    EXEC_SUMMARY_ROBOTIC_TRANSITION_PREFIXES,
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
    REQUIRED_JUDGE_PROVIDERS,
    REQUIRED_JUDGE_PROVIDER_KEYS,
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
from apps_rg.runtime.validators.exec_summary_x2.surface_checks import (
    _DISPLAY_OVERRIDE_REQUIRED_SUBSTRINGS,
    _source_fact_base_id,
    check_cross_fact_display_conflation,
    check_exec_summary_display_override_compliance,
    check_exec_summary_mechanical_opener_stack,
    check_exec_summary_meta_filler_patterns,
    check_exec_summary_no_sentence_fragment,
    check_exec_summary_robotic_transition_stack,
    check_exec_summary_stock_bridge_count,
    check_exec_summary_strategy_no_commercialization_thread,
    check_judge_packet_display_override_parity,
    check_resume_display_colon_space_discipline,
    check_transport_envelope_stub_false,
    detect_bullet_like_stacking,
    has_jd_phrase_copy,
)
from apps_rg.runtime.validators.exec_summary_x2.narrative_grounding_checks import (
    _ledger_claim_tokens,
    _sensitive_phrase_present,
    check_claim_coverage_accounting,
    check_claim_ledger_claim_text_non_empty,
    check_claim_ledger_materialized_or_gap_excused,
    check_claim_ledger_orphan_source_ids,
    check_exec_summary_partner_narrative_continuity,
    check_exec_summary_speculative_capstone,
    check_executive_strategy_thesis,
    check_required_artifacts,
    check_required_fields,
    check_source_sensitive_phrases,
    check_synthesis_quality,
    gap_notes_excuse_ledger_claim,
    ledger_row_materialized_in_display,
)
from apps_rg.runtime.validators.exec_summary_x2.ledger_judge_checks import (
    append_executive_summary_x1d_x2_gate_dicts,
    check_briefing_as_proof_zero,
    check_inferred_bridge_claims,
    check_jd_as_proof_zero,
    check_json_parse_valid,
    check_judge_raw_responses_written,
    check_judge_rows_present,
    check_judge_schema_valid,
    check_material_clause_coverage,
    check_metric_fact_id_granularity,
    check_no_extra_fields,
    check_target_title_inflation,
    check_unsupported_industry_claims,
    check_x1d_judge_packet_hash_uniform,
    model_name_matches_allowed,
    required_judges_for_section,
)
from apps_rg.runtime.validators.exec_summary_x2.sentence_metric_checks import (
    _collapse_display_whitespace,
    _display_claim_token_overlap_matches,
    _matching_ledger_rows_for_display_sentence,
    _metric_tokens_from_text,
    _normalize_display_clause,
    _north_star_signature_supported_by_blob,
    _percent_values_from_text,
    _row_sentence_match_strength,
    _selected_facts_support_blob,
    _token_overlap_matches,
    build_sentence_claim_coverage,
    check_c03_selected_fact_ids_claimable_subset_allowed_fact_ids,
    check_claim_field_maps_to_display_sentence,
    check_claim_ledger_row_count_matches_sentence_count,
    check_exec_summary_cross_sentence_metric_dedup,
    check_exec_summary_display_roundtrip_integrity,
    check_exec_summary_jd_alignment_proof_flags,
    check_exec_summary_sentence_count_4_5,
    check_exec_summary_sentence_count_5_6,
    check_exec_summary_sentence_count_6,
    check_north_star_style_example_echo_unsupported,
    check_raw_json_no_selected_fact_plan_echo,
    check_self_check_claim_ledger_consistent,
    ledger_row_display_claim_materialized,
)
from apps_rg.runtime.validators.exec_summary_x2.utilization_checks import (
    _brushstroke_required_groups_for_gates,
    _fact_id_base_for_utilization,
    _is_cert_fact_id_for_utilization,
    _pool_too_small_excused,
    _selected_fact_pool_size,
    brushstroke_required_fact_ids_from_composition_plan,
    brushstroke_required_groups_from_composition_plan,
    check_exec_summary_allowed_fact_utilization,
    check_exec_summary_evidence_utilization,
    collect_cited_source_fact_ids,
    collect_unused_allowed_fact_ids,
    default_allowed_fact_utilization_waivers,
)
from apps_rg.runtime.validators.exec_summary_x2.shape_and_credential_checks import (
    _claim_row_uses_resume_fact_id,
    _exec_summary_painting_mode_active,
    _graph_evidence_credibility_sentence_opener_ok,
    _graph_evidence_lane_no_commercial_org_cred,
    _graph_evidence_outcomes_sentence_opener_ok,
    _resume_word_count,
    _sentence_fsa_rigor_only,
    _sentence_has_fsa_rigor,
    _vendor_named_cert_hits,
    check_exec_summary_no_bloated_sentence,
    check_exec_summary_no_certifications_section_duplication,
    check_exec_summary_no_competencies_duplication,
    check_exec_summary_no_credential_dump,
    check_exec_summary_no_mechanism_inventory,
    check_exec_summary_paragraph_max_words,
    check_graph_evidence_sentence_responsibility_shape,
    check_prompt_template_authority,
)
from pathlib import Path
from typing import Any

from apps_rg.runtime.validators.exec_summary_x2.gate_runner import (
    _run_x2_gates_impl,
)
from apps_rg.runtime.validators.exec_summary_x2.gate_runner_tail import (
    failed_gate_ids,
    gates_pass,
)


def resolve_utilization_waived_fact_ids(allowed_fact_ids: set[str]) -> set[str]:
    """Env override: APPS_RG_EXEC_SUMMARY_UTILIZATION_WAIVE_FACT_IDS=comma-separated fact ids."""
    import os

    raw = str(os.environ.get("APPS_RG_EXEC_SUMMARY_UTILIZATION_WAIVE_FACT_IDS") or "").strip()
    if raw:
        explicit = {x.strip() for x in raw.split(",") if x.strip()}
        return {fid for fid in explicit if fid in allowed_fact_ids}
    return set(default_allowed_fact_utilization_waivers(allowed_fact_ids))
def run_x2_gates(
    *,
    resume_display_text: str,
    parsed_output: dict[str, Any] | None,
    claim_ledger: list[dict[str, Any]],
    text_claim_coverage: dict[str, Any],
    allowed_fact_ids: set[str],
    target_company: str,
    jd_text: str,
    temperature: float,
    runtime_generation_status: str,
    monolithic_prompt_invoked: bool,
    strategic_tailor_v1_invoked: bool,
    artifacts_dir: Path | None = None,
    provider_requested: str | None = None,
    provider_attempted: str | None = None,
    model_name: str | None = None,
    prompt_hash: str | None = None,
    compiled_prompt: str | None = None,
    raw_output: str | None = None,
    x1d_judges: list[dict[str, Any]] | None = None,
    defer_x1d_gates: bool = False,
    target_role: str | None = None,
    selected_facts: list[dict[str, Any]] | None = None,
    proof_pool_metadata: dict[str, Any] | None = None,
    proof_pool_ref: str = "",
    proof_pool_digest: str = "",
) -> list[X2GateResult]:
    gates = _run_x2_gates_impl(
        resume_display_text=resume_display_text,
        parsed_output=parsed_output,
        claim_ledger=claim_ledger,
        text_claim_coverage=text_claim_coverage,
        allowed_fact_ids=allowed_fact_ids,
        target_company=target_company,
        jd_text=jd_text,
        temperature=temperature,
        runtime_generation_status=runtime_generation_status,
        monolithic_prompt_invoked=monolithic_prompt_invoked,
        strategic_tailor_v1_invoked=strategic_tailor_v1_invoked,
        artifacts_dir=artifacts_dir,
        provider_requested=provider_requested,
        provider_attempted=provider_attempted,
        model_name=model_name,
        prompt_hash=prompt_hash,
        compiled_prompt=compiled_prompt,
        raw_output=raw_output,
        x1d_judges=x1d_judges,
        defer_x1d_gates=defer_x1d_gates,
        target_role=target_role,
        selected_facts=selected_facts,
        proof_pool_metadata=proof_pool_metadata,
        proof_pool_ref=proof_pool_ref,
        proof_pool_digest=proof_pool_digest,
    )
    known = {g.gate_id for g in gates}

    def add(gate_id: str) -> bool:
        return gate_id in known

    add("x2_schema_valid")
    add("x2_claim_ledger_present")
    add("x2_sentence_coverage_present")
    add("x2_sentence_coverage_pass")
    add("x2_self_check_claim_ledger_consistent")
    add("x2_claim_ledger_row_count_matches_sentence_count")
    add("x2_claim_field_maps_to_display_sentence")
    add("x2_source_fact_coverage_100")
    add("x2_claim_ledger_orphan_zero")
    add("x2_claim_ledger_claim_text_non_empty")
    add("x2_unsupported_claim_zero")
    add("x2_mixed_claim_zero")
    add("x2_overbroad_claim_zero")
    add("x2_jd_phrase_copy_violation_zero")
    add("x2_exec_summary_jd_alignment_proof_flags")
    add("x2_em_dash_count_zero")
    add("x2_inline_source_tags_absent")
    add("x2_exec_summary_paragraph_max_words")
    add("x2_exec_summary_no_bloated_sentence")
    add("x2_no_monolithic_prompt")
    add("x2_temperature_in_profile")
    add("x2_first_person_zero")
    add("x2_target_company_as_experience_zero")
    add("x2_generic_filler_zero")
    add("x2_exec_summary_meta_filler_zero")
    add("x2_exec_summary_colon_stitch_zero")
    add("x2_exec_summary_sentence_count_6")
    add("x2_exec_summary_display_roundtrip_integrity")
    add("x2_exec_summary_cross_sentence_metric_dedup")
    add("x2_exec_summary_c03_selected_fact_ids_claimable_subset_allowed_fact_ids")
    add("x2_exec_summary_allowed_fact_utilization")
    add("x2_exec_summary_evidence_utilization")
    add("x2_exec_summary_no_mechanism_inventory")
    add("x2_exec_summary_no_credential_dump")
    add("x2_exec_summary_no_sentence_fragment")
    add("x2_exec_summary_display_override_compliance")
    add("x2_exec_summary_strategy_no_commercialization_thread")
    add("x2_exec_summary_no_competencies_duplication")
    add("x2_exec_summary_no_certifications_section_duplication")
    add("x2_exec_summary_prompt_template_authority")
    add("x2_sentence_stacking_zero")
    add("x2_executive_summary_synthesis_quality")
    add("x2_exec_summary_partner_narrative_continuity")
    add("x2_exec_summary_speculative_capstone_zero")
    add("x2_exec_summary_mechanical_opener_stack_zero")
    add("x2_exec_summary_robotic_transition_stack_zero")
    add("x2_exec_summary_cross_fact_conflation_zero")
    add("x2_north_star_style_echo_unsupported_zero")
    add("x2_claim_coverage_accounting_consistent")
    add("x2_claim_ledger_materialized_or_gap_excused")
    add("x2_required_fields_complete")
    add("x2_required_artifacts_written")
    add("x2_json_parse_valid")
    add("x2_no_selected_fact_plan_model_echo")
    add("x2_no_extra_unrecognized_fields")
    add("x2_material_clause_coverage_100")
    add("x2_metric_fact_id_granularity")
    add("x2_no_inferred_bridge_claims")
    add("x2_jd_as_proof_zero")
    add("x2_briefing_as_proof_zero")
    add("x2_target_title_inflation_zero")
    add("x2_unsupported_industry_claim_zero")
    add("x2_provider_requested_attempted")
    add("x2_no_silent_mock_fallback")
    add("x2_PROVIDER_MODEL_provider_stub_transport_zero")
    add("x2_model_name_allowed")
    add("x2_prompt_hash_known")
    add("x2_input_output_hashes_present")
    add("x2_executive_strategy_thesis_present")
    add("x2_exec_summary_s5_no_derivatives_inventory")
    add("x2_self_check_s5_no_derivatives_inventory")
    add("x2_exec_summary_composition_plan_present")
    add("x2_exec_summary_brushstroke_fact_support")
    add("x2_exec_summary_graph_skill_coverage")
    add("x2_exec_summary_dominant_brushstroke_coherence")
    add("x2_exec_summary_mechanism_inventory_control")
    add("x2_exec_summary_human_exec_voice")
    add("x2_exec_summary_no_jd_keyword_stuffing")
    add("x2_exec_summary_stock_bridge_max_two")
    add("x2_source_sensitive_phrases_supported")
    add("x2_x1d_required_judges_present")
    add("x2_x1d_raw_responses_written")
    add("x2_x1d_schema_valid")
    add("x2_x1d_judge_packet_hash_uniform")
    return gates
