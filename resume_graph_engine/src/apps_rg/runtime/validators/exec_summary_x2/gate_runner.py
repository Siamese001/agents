"""Primary run_x2_gates entry point for executive summary X2 validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

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
from apps_rg.runtime.validators.exec_summary_x2.gate_runner_tail import (
    _append_runtime_and_artifact_x2_gates,
)
from apps_rg.runtime.validators.exec_summary_x2.narrative_grounding_checks import (
    check_claim_ledger_claim_text_non_empty,
    check_claim_ledger_orphan_source_ids,
    check_executive_strategy_thesis,
)
from apps_rg.runtime.validators.exec_summary_x2.sentence_metric_checks import (
    check_c03_selected_fact_ids_claimable_subset_allowed_fact_ids,
    check_claim_field_maps_to_display_sentence,
    check_claim_ledger_row_count_matches_sentence_count,
    check_exec_summary_cross_sentence_metric_dedup,
    check_exec_summary_display_roundtrip_integrity,
    check_exec_summary_jd_alignment_proof_flags,
    check_exec_summary_sentence_band_3_to_4,
    check_self_check_claim_ledger_consistent,
)
from apps_rg.runtime.validators.exec_summary_x2.shape_and_credential_checks import (
    _exec_summary_painting_mode_active,
    check_exec_summary_no_abstract_noun_soup,
    check_exec_summary_no_ai_bridge_crutches,
    check_exec_summary_no_bloated_sentence,
    check_exec_summary_no_certifications_section_duplication,
    check_exec_summary_no_competencies_duplication,
    check_exec_summary_no_credential_dump,
    check_exec_summary_no_mechanism_inventory,
    check_exec_summary_paragraph_max_words,
    check_exec_summary_rhythm_and_cadence_variety,
    check_exec_summary_visual_char_band,
    check_graph_evidence_sentence_responsibility_shape,
    check_prompt_template_authority,
)
from apps_rg.runtime.validators.exec_summary_x2.surface_checks import (
    check_exec_summary_display_override_compliance,
    check_exec_summary_meta_filler_patterns,
    check_exec_summary_no_internal_plumbing_or_stutter,
    check_exec_summary_no_sentence_fragment,
    check_exec_summary_strategy_no_commercialization_thread,
    check_judge_packet_display_override_parity,
    check_resume_display_colon_space_discipline,
    has_jd_phrase_copy,
)
from apps_rg.runtime.validators.exec_summary_x2.utilization_checks import (
    _brushstroke_required_groups_for_gates,
    check_exec_summary_allowed_fact_utilization,
    check_exec_summary_evidence_utilization,
)

def _run_x2_gates_impl(
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
    from apps_rg.runtime.validators.executive_summary_x2 import (
        EXEC_SUMMARY_MAX_CHARS,
        EXEC_SUMMARY_MAX_SENTENCES,
        EXEC_SUMMARY_MAX_WORDS,
        EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE,
        EXEC_SUMMARY_MIN_CHARS,
        EXEC_SUMMARY_MIN_SENTENCES,
    )
    gates: list[X2GateResult] = []
    artifacts_dir = artifacts_dir or Path("artifacts/apps_rg/runtime_proofs/executive_summary")

    def add(gate_id: str, passed: bool, observed: Any, threshold: Any, reason: str | None = None) -> None:
        gates.append(X2GateResult(gate_id, "deterministic", passed, observed, threshold, None if passed else reason, gate_id))

    # Existing gates
    add("x2_schema_valid", parsed_output is not None, parsed_output is not None, True, "Model output did not parse to expected JSON object.")
    from apps_rg.runtime.sections.executive_summary_pa import is_strategy_executive_target_title

    strategy_lane = is_strategy_executive_target_title(str(target_role or ""))
    if strategy_lane:
        thesis_ok, thesis_reason = check_executive_strategy_thesis(parsed_output)
        add(
            "x2_executive_strategy_thesis_present",
            thesis_ok,
            (parsed_output or {}).get("executive_strategy_thesis") if parsed_output else None,
            "non_empty_thesis",
            thesis_reason,
        )
    add("x2_claim_ledger_present", bool(claim_ledger), len(claim_ledger), ">0", "claim_ledger is empty or missing.")
    add("x2_sentence_coverage_present", bool(text_claim_coverage.get("sentences")), len(text_claim_coverage.get("sentences", [])), ">0", "text_claim_coverage missing.")
    add("x2_sentence_coverage_pass", text_claim_coverage.get("overall_pass") is True, text_claim_coverage.get("overall_pass"), True, "One or more displayed sentences lack supported claims.")

    self_check_ok, self_check_reason = check_self_check_claim_ledger_consistent(
        parsed_output, text_claim_coverage
    )
    add(
        "x2_self_check_claim_ledger_consistent",
        self_check_ok,
        self_check_reason or "ok",
        "self_check_implies_coverage_pass",
        self_check_reason,
    )
    # Ledger/display parity gates are lane-agnostic rigor invariants (row count == sentence
    # count; each ledger claim materializes in the display body). They are listed as
    # rigor-critical for the lane in section_product_shape_ssot, so they must be emitted on
    # EVERY lane — not only the strategy-executive lane — otherwise the rigor convergence audit
    # injects a deterministic ``rigor_critical_gate_missing_from_runtime_bundle`` BLOCK for any
    # non-strategy target title (e.g. "VP, Global Head of Agentic AI Solutions").
    row_count_ok, row_count_reason = check_claim_ledger_row_count_matches_sentence_count(
        resume_display_text, claim_ledger
    )
    add(
        "x2_claim_ledger_row_count_matches_sentence_count",
        row_count_ok,
        row_count_reason or "ok",
        "sentences_eq_ledger_rows",
        row_count_reason,
    )
    claim_map_ok, claim_map_reason = check_claim_field_maps_to_display_sentence(
        resume_display_text, claim_ledger
    )
    add(
        "x2_claim_field_maps_to_display_sentence",
        claim_map_ok,
        claim_map_reason or "ok",
        "each_claim_in_display",
        claim_map_reason,
    )
    if strategy_lane:
        from apps_rg.runtime.sections.executive_summary_operator_reporting import (
            check_exec_summary_s5_no_derivatives_inventory,
            check_self_check_s5_no_derivatives_inventory,
        )

        s5_inv_ok, s5_inv_reason = check_exec_summary_s5_no_derivatives_inventory(
            resume_display_text,
            allowed_fact_ids=allowed_fact_ids,
            selected_facts=selected_facts,
        )
        add(
            "x2_exec_summary_s5_no_derivatives_inventory",
            s5_inv_ok,
            s5_inv_reason or "ok",
            "no_derivatives_inventory_without_hpc_metric",
            s5_inv_reason,
        )
        s5_sc_ok, s5_sc_reason = check_self_check_s5_no_derivatives_inventory(
            parsed_output,
            resume_display_text,
            allowed_fact_ids=allowed_fact_ids,
            selected_facts=selected_facts,
        )
        add(
            "x2_self_check_s5_no_derivatives_inventory",
            s5_sc_ok,
            s5_sc_reason or "ok",
            "self_check_s5_derivatives_consistent",
            s5_sc_reason,
        )

    source_coverage_ok = bool(claim_ledger) and all(
        any((sid in allowed_fact_ids) or ("_metric_" in sid) for sid in (claim.get("source_fact_ids") or []))
        for claim in claim_ledger
    )
    add("x2_source_fact_coverage_100", source_coverage_ok, "100%" if source_coverage_ok else "<100%", "100%", "One or more claims lack allowed source_fact_ids.")

    orphan_ok, orphan_reason = check_claim_ledger_orphan_source_ids(claim_ledger, allowed_fact_ids)
    add("x2_claim_ledger_orphan_zero", orphan_ok, orphan_reason or "ok", "no_orphans", orphan_reason)

    ledger_text_ok, ledger_text_reason = check_claim_ledger_claim_text_non_empty(claim_ledger)
    add(
        "x2_claim_ledger_claim_text_non_empty",
        ledger_text_ok,
        ledger_text_reason or "all_rows_non_empty",
        "non_empty_claim_text_each_row",
        ledger_text_reason,
    )

    unsupported = []
    mixed = []
    overbroad = []
    for row in text_claim_coverage.get("sentences", []):
        for claim in row.get("material_claims", []):
            status = claim.get("support_status")
            if status == "UNSUPPORTED":
                unsupported.append(claim)
            if status == "MIXED":
                mixed.append(claim)
            if status == "OVERBROAD":
                overbroad.append(claim)
    add("x2_unsupported_claim_zero", not unsupported, len(unsupported), 0, "Unsupported claims present.")
    add("x2_mixed_claim_zero", not mixed, len(mixed), 0, "Mixed claims present.")
    add("x2_overbroad_claim_zero", not overbroad, len(overbroad), 0, "Overbroad claims present.")

    copied, phrase = has_jd_phrase_copy(resume_display_text, jd_text)
    add("x2_jd_phrase_copy_violation_zero", not copied, phrase, None, f"JD phrase copied: {phrase}")
    jd_proof_ok, jd_proof_reason = check_exec_summary_jd_alignment_proof_flags(parsed_output)
    add(
        "x2_exec_summary_jd_alignment_proof_flags",
        jd_proof_ok,
        (parsed_output or {}).get("jd_alignment") if isinstance(parsed_output, dict) else "missing",
        "targeting_only_true_and_proof_flags_false",
        jd_proof_reason,
    )
    add("x2_em_dash_count_zero", EM_DASH not in resume_display_text, resume_display_text.count(EM_DASH), 0, "Em dash found.")
    add("x2_inline_source_tags_absent", not INLINE_SOURCE_PATTERN.search(resume_display_text), bool(INLINE_SOURCE_PATTERN.search(resume_display_text)), False, "Inline source/citation tag leaked into resume display text.")
    para_max_ok, para_max_reason = check_exec_summary_paragraph_max_words(
        resume_display_text, parsed_output
    )
    add(
        "x2_exec_summary_paragraph_max_words",
        para_max_ok,
        para_max_reason or "ok",
        f"max_{EXEC_SUMMARY_MAX_WORDS}_words",
        para_max_reason,
    )
    char_band_ok, char_band_reason = check_exec_summary_visual_char_band(resume_display_text)
    add(
        "x2_exec_summary_visual_char_band",
        char_band_ok,
        char_band_reason or "ok",
        f"{EXEC_SUMMARY_MIN_CHARS}-{EXEC_SUMMARY_MAX_CHARS}_chars",
        char_band_reason,
    )
    bloated_ok, bloated_reason = check_exec_summary_no_bloated_sentence(resume_display_text)
    add(
        "x2_exec_summary_no_bloated_sentence",
        bloated_ok,
        bloated_reason or "ok",
        f"max_{EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE}_words_per_sentence",
        bloated_reason,
    )
    bridge_crutch_ok, bridge_crutch_reason = check_exec_summary_no_ai_bridge_crutches(resume_display_text)
    add(
        "x2_exec_summary_no_ai_bridge_crutches",
        bridge_crutch_ok,
        bridge_crutch_reason or "ok",
        "zero_ai_bridge_crutches",
        bridge_crutch_reason,
    )
    abstract_soup_ok, abstract_soup_reason = check_exec_summary_no_abstract_noun_soup(resume_display_text)
    add(
        "x2_exec_summary_no_abstract_noun_soup",
        abstract_soup_ok,
        abstract_soup_reason or "ok",
        "zero_abstract_noun_soup",
        abstract_soup_reason,
    )
    cadence_ok, cadence_reason = check_exec_summary_rhythm_and_cadence_variety(resume_display_text)
    add(
        "x2_exec_summary_rhythm_and_cadence_variety",
        cadence_ok,
        cadence_reason or "ok",
        "varied_rhythm_and_openers",
        cadence_reason,
    )
    add("x2_no_monolithic_prompt", not monolithic_prompt_invoked, monolithic_prompt_invoked, False, "Monolithic prompt invoked.")
    add("x2_temperature_in_profile", 0.35 <= temperature <= 0.55, temperature, "0.35-0.55", "Temperature outside executive_summary profile.")
    add("x2_first_person_zero", not FIRST_PERSON_PATTERN.search(resume_display_text), bool(FIRST_PERSON_PATTERN.search(resume_display_text)), False, "First-person pronoun found.")
    lowered_text = resume_display_text.lower()
    lowered_company = (target_company or "").lower().strip()
    target_company_as_experience = bool(
        lowered_company and any(f"{prefix} {lowered_company}" in lowered_text for prefix in ("at", "for", "with"))
    )
    add("x2_target_company_as_experience_zero", not target_company_as_experience, target_company_as_experience, False, "Target company used as candidate experience/employer.")
    filler_hits = [phrase for phrase in GENERIC_FILLER if phrase in resume_display_text.lower()]
    add("x2_generic_filler_zero", not filler_hits, filler_hits, [], "Generic filler found.")
    meta_filler_ok, meta_filler_reason = check_exec_summary_meta_filler_patterns(resume_display_text)
    add(
        "x2_exec_summary_meta_filler_zero",
        meta_filler_ok,
        meta_filler_reason or "ok",
        [],
        meta_filler_reason,
    )
    plumbing_ok, plumbing_reason = check_exec_summary_no_internal_plumbing_or_stutter(resume_display_text)
    add(
        "x2_exec_summary_no_internal_plumbing_or_stutter",
        plumbing_ok,
        plumbing_reason or "ok",
        [],
        plumbing_reason,
    )
    colon_stitch_ok, colon_stitch_reason = check_resume_display_colon_space_discipline(resume_display_text)
    add(
        "x2_exec_summary_colon_stitch_zero",
        colon_stitch_ok,
        colon_stitch_reason or "ok",
        [],
        colon_stitch_reason,
    )
    sent_band_ok, sent_band_reason = check_exec_summary_sentence_band_3_to_4(resume_display_text)
    add(
        "x2_exec_summary_sentence_band_3_to_4",
        sent_band_ok,
        sent_band_reason or "ok",
        f"{EXEC_SUMMARY_MIN_SENTENCES}_to_{EXEC_SUMMARY_MAX_SENTENCES}_sentences",
        sent_band_reason,
    )
    roundtrip_ok, roundtrip_reason = check_exec_summary_display_roundtrip_integrity(
        resume_display_text
    )
    add(
        "x2_exec_summary_display_roundtrip_integrity",
        roundtrip_ok,
        roundtrip_reason or "ok",
        "split_join_and_no_control_chars",
        roundtrip_reason,
    )
    dedup_ok, dedup_reason = check_exec_summary_cross_sentence_metric_dedup(resume_display_text)
    add(
        "x2_exec_summary_cross_sentence_metric_dedup",
        dedup_ok,
        dedup_reason or "ok",
        "no_duplicate_high_signal_metrics",
        dedup_reason,
    )
    allowlist_ok, allowlist_reason = check_c03_selected_fact_ids_claimable_subset_allowed_fact_ids(
        allowed_fact_ids=allowed_fact_ids,
        proof_pool_metadata=proof_pool_metadata,
    )
    add(
        "x2_exec_summary_c03_selected_fact_ids_claimable_subset_allowed_fact_ids",
        allowlist_ok,
        allowlist_reason or "ok",
        "pool_wins_allowlist",
        allowlist_reason,
    )
    _brushstroke_groups = _brushstroke_required_groups_for_gates(parsed_output, artifacts_dir)
    util_pool_ok, util_pool_reason, util_pool_receipt = check_exec_summary_allowed_fact_utilization(
        claim_ledger,
        allowed_fact_ids,
        text_claim_coverage=text_claim_coverage,
        required_brushstroke_groups=_brushstroke_groups or None,
    )
    add(
        "x2_exec_summary_allowed_fact_utilization",
        util_pool_ok,
        util_pool_reason or "ok",
        "non_waived_allowed_facts_cited",
        util_pool_reason,
    )
    if isinstance(parsed_output, dict) and util_pool_receipt:
        parsed_output.setdefault("allowed_fact_utilization_receipt", util_pool_receipt)
    util_ok, util_reason = check_exec_summary_evidence_utilization(
        resume_display_text,
        parsed_output,
        selected_facts=selected_facts,
    )
    add(
        "x2_exec_summary_evidence_utilization",
        util_ok,
        util_reason or "ok",
        "structural_fact_weave",
        util_reason,
    )
    mech_ok, mech_reason = check_exec_summary_no_mechanism_inventory(
        resume_display_text, parsed_output
    )
    add(
        "x2_exec_summary_no_mechanism_inventory",
        mech_ok,
        mech_reason or "ok",
        "no_mechanism_dump",
        mech_reason,
    )
    cred_ok, cred_reason = check_exec_summary_no_credential_dump(resume_display_text)
    add(
        "x2_exec_summary_no_credential_dump",
        cred_ok,
        cred_reason or "ok",
        "no_credential_inventory_block",
        cred_reason,
    )
    frag_ok, frag_reason = check_exec_summary_no_sentence_fragment(resume_display_text)
    add(
        "x2_exec_summary_no_sentence_fragment",
        frag_ok,
        frag_reason or "ok",
        "no_grammatical_fragments",
        frag_reason,
    )
    override_ok, override_reason = check_exec_summary_display_override_compliance(
        resume_display_text,
        claim_ledger,
    )
    add(
        "x2_exec_summary_display_override_compliance",
        override_ok,
        override_reason or "ok",
        "display_override_anchor_present",
        override_reason,
    )
    comm_ok, comm_reason = check_exec_summary_strategy_no_commercialization_thread(
        resume_display_text,
        target_role=target_role,
    )
    add(
        "x2_exec_summary_strategy_no_commercialization_thread",
        comm_ok,
        comm_reason or "ok",
        "no_commercialization_identity_thread",
        comm_reason,
    )
    comp_dup_ok, comp_dup_reason = check_exec_summary_no_competencies_duplication(resume_display_text)
    add(
        "x2_exec_summary_no_competencies_duplication",
        comp_dup_ok,
        comp_dup_reason or "ok",
        "no_competencies_section_echo",
        comp_dup_reason,
    )
    cert_dup_ok, cert_dup_reason = check_exec_summary_no_certifications_section_duplication(
        resume_display_text
    )
    add(
        "x2_exec_summary_no_certifications_section_duplication",
        cert_dup_ok,
        cert_dup_reason or "ok",
        "no_certifications_heading_echo",
        cert_dup_reason,
    )
    prompt_auth_ok, prompt_auth_reason = check_prompt_template_authority(artifacts_dir)
    add(
        "x2_exec_summary_prompt_template_authority",
        prompt_auth_ok,
        prompt_auth_reason or "ok",
        EXPECTED_PROMPT_ID,
        prompt_auth_reason,
    )
    if _exec_summary_painting_mode_active(proof_pool_metadata):
        from apps_rg.runtime.sections.executive_summary_composition import (
            check_brushstroke_fact_support,
            check_composition_plan_present,
            check_dominant_brushstroke_coherence,
            check_graph_skill_coverage,
            check_human_exec_voice,
            check_mechanism_inventory_control,
            check_no_jd_keyword_stuffing_exec,
            resolve_composition_plan,
        )

        comp_plan = resolve_composition_plan(parsed_output, artifacts_dir=artifacts_dir)
        plan_ok, plan_reason = check_composition_plan_present(
            parsed_output,
            artifacts_dir=artifacts_dir,
            proof_pool_metadata=proof_pool_metadata,
        )
        add(
            "x2_exec_summary_composition_plan_present",
            plan_ok,
            plan_reason or "ok",
            "executive_summary_composition_plan.json",
            plan_reason,
        )
        bs_ok, bs_reason = check_brushstroke_fact_support(comp_plan, claim_ledger, allowed_fact_ids)
        add(
            "x2_exec_summary_brushstroke_fact_support",
            bs_ok,
            bs_reason or "ok",
            "brushstrokes_cite_allowed_facts",
            bs_reason,
        )
        gs_ok, gs_reason = check_graph_skill_coverage(comp_plan, parsed_output)
        add(
            "x2_exec_summary_graph_skill_coverage",
            gs_ok,
            gs_reason or "ok",
            "graph_skill_refs_when_claimed",
            gs_reason,
        )
        dom_ok, dom_reason = check_dominant_brushstroke_coherence(resume_display_text, comp_plan)
        add(
            "x2_exec_summary_dominant_brushstroke_coherence",
            dom_ok,
            dom_reason or "ok",
            "thesis_led_not_mechanism_inventory",
            dom_reason,
        )
        inv_ok, inv_reason = check_mechanism_inventory_control(resume_display_text)
        add(
            "x2_exec_summary_mechanism_inventory_control",
            inv_ok,
            inv_reason or "ok",
            "no_mechanism_dump",
            inv_reason,
        )
        voice_ok, voice_reason = check_human_exec_voice(resume_display_text)
        add(
            "x2_exec_summary_human_exec_voice",
            voice_ok,
            voice_reason or "ok",
            "credible_exec_prose",
            voice_reason,
        )
        jd_stuff_ok, jd_stuff_reason = check_no_jd_keyword_stuffing_exec(resume_display_text, jd_text)
        add(
            "x2_exec_summary_no_jd_keyword_stuffing",
            jd_stuff_ok,
            jd_stuff_reason or "ok",
            "no_jd_mirror_stuffing",
            jd_stuff_reason,
        )

    return _append_runtime_and_artifact_x2_gates(
        gates=gates,
        add=add,
        strategy_lane=strategy_lane,
        resume_display_text=resume_display_text,
        parsed_output=parsed_output,
        claim_ledger=claim_ledger,
        text_claim_coverage=text_claim_coverage,
        allowed_fact_ids=allowed_fact_ids,
        target_company=target_company,
        jd_text=jd_text,
        artifacts_dir=artifacts_dir,
        provider_requested=provider_requested,
        provider_attempted=provider_attempted,
        runtime_generation_status=runtime_generation_status,
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
