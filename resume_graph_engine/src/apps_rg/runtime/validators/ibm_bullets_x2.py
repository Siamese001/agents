"""Deterministic X2 gates for ibm_bullets runtime slice (five IBM employment bullets)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.validators.executive_summary_x2 import (
    EM_DASH,
    FIRST_PERSON_PATTERN,
    GENERIC_FILLER,
    INLINE_SOURCE_PATTERN,
    REQUIRED_JUDGE_PROVIDERS,
    check_claim_ledger_claim_text_non_empty,
    check_json_parse_valid,
    check_judge_rows_present,
    check_judge_schema_valid,
    has_jd_phrase_copy,
)
from apps_rg.runtime.validators.ibm_x2 import (
    CORE_METRIC_TOKENS,
    IBM_BULLET_GRAPH_SKILL_NODE_IDS_GATE_ID,
    IBM_BULLET_IDS,
    IBM_BULLET_METRIC_SOURCE_GATE_ID,
    IBM_METRIC_ANCHOR_RULES,
    REQUIRED_TOP_LEVEL,
    TAXONOMY_LABEL_PREFIX_PATTERN,
    UNIFY_RUNTIME_TERM_PATTERNS,
    X2GateResult,
    _COVERAGE_WS_RE,
    _SEMANTIC_OVERLAP_STOPWORDS,
    _SEMANTIC_OVERLAP_TOKEN_RE,
    _all_source_fact_ids,
    _combined_bullet_text,
    _ibm_metric_anchors_on_assigned_bullets,
    _ibm_root_from_source_fact_ids,
    _metric_granularity_ok,
    _norm_claim_ws,
    _taxonomy_prefix_violations,
    build_ibm_bullets_text_claim_coverage,
    check_ibm_bullets_text_claim_coverage_integrity,
    ibm_bullet_text_has_taxonomy_label_prefix,
    ibm_cross_bullet_semantic_overlap_violations,
    semantic_overlap_tokens,
)
from apps_rg.runtime.validators.ibm_x2.gate_evals import (
    _eval_blocked_judge_schemas,
    _eval_hold_metrics,
    _eval_ibm_scope_and_coverage,
    _eval_ledger_claim_text,
    _eval_skill_ids_and_bundles,
    _resolve_ibm_proof_context,
    _resolve_plan_facts_for_anchors,
)

TEXT_COVERAGE_INTEGRITY_GATE_ID = "x2_text_claim_coverage_integrity"


def run_ibm_bullets_x2_gates(
    *,
    bullets: list[dict[str, Any]],
    parsed_output: dict[str, Any] | None,
    claim_ledger: list[dict[str, Any]],
    allowed_fact_ids: set[str],
    jd_text: str,
    runtime_generation_status: str,
    artifacts_dir: Path | None = None,
    provider_requested: str | None = None,
    provider_attempted: str | None = None,
    model_name: str | None = None,
    raw_output: str | None = None,
    x1d_judges: list[dict[str, Any]] | None = None,
    srfs_source_fact_slice_gate_active: bool = False,
    proof_pool_metadata: dict[str, Any] | None = None,
    proof_pool_ref: str = "",
    proof_pool_digest: str = "",
    base_resume: dict[str, Any] | None = None,
    runtime_payload: dict[str, Any] | None = None,
) -> list[X2GateResult]:
    """Run all deterministic X2 validation gates for the ``ibm_bullets`` runtime slice."""
    (
        allowed_fact_ids,
        proof_pool_digest,
        proof_pool_metadata,
        selected_plan,
        selection_method,
        expected_bullet_ids,
    ) = _resolve_ibm_proof_context(
        allowed_fact_ids,
        proof_pool_digest,
        proof_pool_metadata,
        parsed_output,
        runtime_payload,
    )
    gates: list[X2GateResult] = []

    def add(
        gate_id: str,
        passed: bool,
        observed: Any,
        threshold: Any = None,
        failure: str | None = None,
    ) -> None:
        gates.append(
            X2GateResult(
                gate_id=gate_id,
                gate_type="deterministic",
                pass_=passed,
                observed_value=observed,
                threshold=threshold,
                failure_reason=failure,
                evidence_ref=gate_id,
            )
        )

    from apps_rg.runtime.c0.graph_story_authority import (
        x2_gate_base_resume_story_forbidden,
        x2_gate_graph_only_proof_pool,
    )
    from apps_rg.runtime.sections.ibm_bullets_graph_evidence import (
        IBM_TRACK_RANKED_SELECTION_METHOD,
        check_ibm_bullets_phase2_career_track_scope,
    )

    graph_ok, graph_obs, graph_exp, graph_detail = x2_gate_graph_only_proof_pool(
        proof_pool_metadata, section_id="ibm_bullets"
    )
    add("x2_ibm_augmented_skills_graph_proof_pool_only", graph_ok, graph_obs, graph_exp, str(graph_detail))

    if selection_method == IBM_TRACK_RANKED_SELECTION_METHOD:
        phase2_ok, phase2_obs = check_ibm_bullets_phase2_career_track_scope(
            proof_pool_metadata=proof_pool_metadata,
            selected_fact_plan=selected_plan,
        )
        add(
            "x2_ibm_phase2_career_track_scope",
            phase2_ok,
            phase2_obs,
            "track_data_tech_cloud_ml_only; employment 2017-04 to 2022-10",
            None if phase2_ok else str(phase2_obs.get("reason") or phase2_obs),
        )

    story_ok, story_obs, story_exp, story_detail = x2_gate_base_resume_story_forbidden(
        section_id="ibm_bullets",
        parsed_output=parsed_output,
        base_resume=base_resume,
        runtime_payload=runtime_payload,
    )
    add("x2_ibm_graph_only_no_base_resume_bullets", story_ok, story_obs, story_exp, str(story_detail))

    combined = _combined_bullet_text(bullets)
    expected_count = len(expected_bullet_ids)
    add(
        f"x2_ibm_bullet_count_{expected_count}",
        len(bullets) == expected_count,
        len(bullets),
        expected_count,
        f"Must output exactly {expected_count} IBM bullets.",
    )
    if expected_count != 5:
        add(
            "x2_ibm_bullet_count_5",
            len(bullets) == expected_count,
            len(bullets),
            expected_count,
            f"Must output exactly {expected_count} IBM bullets (allocated count).",
        )

    semantic_overlap = ibm_cross_bullet_semantic_overlap_violations(bullets)
    add(
        "x2_ibm_cross_bullet_semantic_overlap_zero",
        not semantic_overlap,
        semantic_overlap or "none",
        "pairwise_content_token_jaccard<0.60",
        f"Near-duplicate IBM bullet pairs: {semantic_overlap}" if semantic_overlap else None,
    )

    from apps_rg.runtime.validators.bullet_line_discipline_x2 import (
        register_bullet_line_discipline_x2_gates,
    )

    register_bullet_line_discipline_x2_gates(
        add,
        bullets,
        lane_prefix="ibm",
        section_id="ibm_bullets",
    )

    po_raw = parsed_output or {}
    missing_top_level = sorted(k for k in REQUIRED_TOP_LEVEL if k not in po_raw)
    add(
        "x2_required_top_level_json_keys",
        not missing_top_level,
        missing_top_level,
        sorted(REQUIRED_TOP_LEVEL),
        f"Missing required top-level JSON keys: {', '.join(missing_top_level)}" if missing_top_level else None,
    )

    from apps_rg.runtime.reasoning.employment_bullet_output_sanitize import (
        find_rewrite_intensity_model_violations,
    )

    intensity_violations = find_rewrite_intensity_model_violations(parsed_output=po_raw, bullets=bullets)
    add(
        "x2_ibm_no_rewrite_intensity_model",
        not intensity_violations,
        intensity_violations or "absent",
        "no rewrite_distribution / rewrite_intensity fields",
        (
            f"Retired rewrite-intensity model fields present: {', '.join(intensity_violations)}"
            if intensity_violations
            else None
        ),
    )

    ledger_text_ok, ledger_text_reason = _eval_ledger_claim_text(claim_ledger)
    add(
        "x2_claim_ledger_claim_text_non_empty",
        ledger_text_ok,
        ledger_text_reason or ("ok" if ledger_text_ok else "failed"),
        "non-empty trimmed claim_text for every ledger row",
        ledger_text_reason,
    )

    cov_gate_payload = po_raw.get("text_claim_coverage") if isinstance(po_raw.get("text_claim_coverage"), dict) else {}
    cov_ok, cov_reason = check_ibm_bullets_text_claim_coverage_integrity(
        bullets=bullets,
        claim_ledger=claim_ledger,
        text_claim_coverage=cov_gate_payload,
        allowed_fact_ids=allowed_fact_ids,
        active_bullet_ids=expected_bullet_ids,
    )
    add(
        TEXT_COVERAGE_INTEGRITY_GATE_ID,
        cov_ok,
        cov_reason or "structural_alignment_ok",
        "matches structural rebuild",
        cov_reason,
    )

    plan_facts_for_anchors = _resolve_plan_facts_for_anchors(selected_plan)
    anchor_ok, anchor_fail = _ibm_metric_anchors_on_assigned_bullets(
        bullets, plan_facts=plan_facts_for_anchors
    )
    add(
        "x2_ibm_metric_anchor_bullet_ownership",
        anchor_ok,
        anchor_fail or "ok",
        "each core metric on assigned bul_ibm_* bullet_text (canonical or plan-fact metric_raw)",
        None if anchor_ok else f"Metric anchor ownership failed: {anchor_fail}",
    )

    forbidden_hits, metrics_obs = _eval_hold_metrics(bullets)
    add(
        "x2_ibm_hold_metric_forbidden_in_output",
        not forbidden_hits,
        forbidden_hits or "none",
        "no $15M/$30M or overloaded 25/30/35/40% in bullet text",
        f"Forbidden metrics in output: {forbidden_hits}" if forbidden_hits else None,
    )
    add(
        "x2_ibm_metrics_preserved",
        not forbidden_hits,
        metrics_obs,
        "no HOLD/DO_NOT_PROMOTE metrics; promotable only via metric_outcome_ids",
        None if not forbidden_hits else f"Forbidden metrics: {forbidden_hits}",
    )

    (
        bullets_missing_skill_ids,
        bundles_present,
        flat_only,
        pp_meta,
        bullets_missing_bundle_id,
        bullets_metric_unsupported,
    ) = _eval_skill_ids_and_bundles(bullets, parsed_output, proof_pool_metadata, runtime_payload)
    add(
        "x2_ibm_bullet_graph_skill_node_ids_required",
        not bullets_missing_skill_ids,
        bullets_missing_skill_ids or "all_present",
        "non-empty graph_skill_node_ids per bul_ibm_* in change_log",
        (
            f"Missing graph_skill_node_ids in change_log for: {bullets_missing_skill_ids}"
            if bullets_missing_skill_ids
            else None
        ),
    )
    add(
        "x2_ibm_role_episode_bundles_in_proof_pool",
        bundles_present and not flat_only,
        {
            "bundles_present": bundles_present,
            "flat_skill_only": flat_only,
            "consumption_mode": pp_meta.get("role_episode_bundle_consumption_mode"),
        },
        "role_episode_bundles in proof_pool_metadata",
        (
            "IBM proof pool missing role_episode_bundles or flat skill-only context"
            if not bundles_present or flat_only
            else None
        ),
    )
    add(
        "x2_ibm_bullet_role_episode_bundle_id_required",
        not bullets_missing_bundle_id,
        bullets_missing_bundle_id or "all_present",
        "role_episode_bundle_id per bul_ibm_* in change_log",
        (
            f"Missing or wrong role_episode_bundle_id: {bullets_missing_bundle_id}"
            if bullets_missing_bundle_id
            else None
        ),
    )
    add(
        "x2_ibm_metric_outcome_id_required_when_has_metric",
        not bullets_metric_unsupported,
        bullets_metric_unsupported or "all_traceable",
        "metric_outcome_ids from PROMOTABLE allow-list when has_metric=true",
        (
            f"Unsupported metric outcome binding: {bullets_metric_unsupported}"
            if bullets_metric_unsupported
            else None
        ),
    )

    from apps_rg.runtime.validators.bullet_ngram_overlap_x2 import (
        GATE_ID_BASE_RESUME,
        GATE_ID_E0_EXAMPLE,
        run_bullet_ngram_overlap_gates,
    )

    ngram_base_pass, ngram_base_results, ngram_e0_pass, ngram_e0_results = run_bullet_ngram_overlap_gates(
        bullets, section_id="ibm_bullets", warn_only=True
    )
    ngram_base_violations = [r for r in ngram_base_results if r.failure_reason]
    add(
        GATE_ID_BASE_RESUME + "_ibm",
        ngram_base_pass,
        [r.failure_reason for r in ngram_base_violations] or "all_below_threshold",
        f"<= {int(0.25 * 100)}% 4-gram overlap with base resume (WARN mode)",
        "; ".join(r.failure_reason for r in ngram_base_violations if r.failure_reason) or None,
    )
    ngram_e0_violations = [r for r in ngram_e0_results if r.failure_reason]
    add(
        GATE_ID_E0_EXAMPLE + "_ibm",
        ngram_e0_pass,
        [r.failure_reason for r in ngram_e0_violations] or "all_below_threshold",
        f"<= {int(0.20 * 100)}% 4-gram overlap with E0 examples (WARN mode)",
        "; ".join(r.failure_reason for r in ngram_e0_violations if r.failure_reason) or None,
    )

    from apps_rg.runtime.sections.ibm_bullets_graph_evidence import IBM_BULLET_MECHANISM_VOCAB
    from apps_rg.runtime.validators.bullet_quality_floor_x2 import (
        check_experience_bullet_evidence_density,
        run_bullet_quality_floor_gates,
    )

    sen_pass, sen_results, tech_pass, tech_results, cons_pass, cons_results = run_bullet_quality_floor_gates(
        bullets, section_id="ibm_bullets", mechanism_vocab_by_slot=IBM_BULLET_MECHANISM_VOCAB
    )
    sen_failures = [r.failure_reason for r in sen_results if r.failure_reason]
    add(
        "x2_bullet_seniority_floor",
        sen_pass,
        sen_failures or "all_pass",
        "score >= 1 (strong_verb OR scale_signal + no weak_verb)",
        "; ".join(sen_failures) if sen_failures else None,
    )
    tech_failures = [r.failure_reason for r in tech_results if r.failure_reason]
    add(
        "x2_bullet_technical_specificity_floor",
        tech_pass,
        tech_failures or "all_pass",
        "at least one named mechanism/technology per bullet",
        "; ".join(tech_failures) if tech_failures else None,
    )
    cons_failures = [r.failure_reason for r in cons_results if r.failure_reason]
    add(
        "x2_no_generic_consulting_substitution",
        cons_pass,
        cons_failures or "all_pass",
        "zero consulting-speak substitution phrases per bullet",
        "; ".join(cons_failures) if cons_failures else None,
    )
    evidence_density_results = [
        check_experience_bullet_evidence_density(
            str(bullet.get("bullet_id") or ""),
            str(bullet.get("bullet_text") or ""),
            mechanism_vocab=IBM_BULLET_MECHANISM_VOCAB.get(str(bullet.get("bullet_id") or "")),
        )
        for bullet in bullets
        if isinstance(bullet, dict) and str(bullet.get("bullet_id") or "").startswith("bul_ibm_")
    ]
    evidence_density_failures = [
        result.failure_reason for result in evidence_density_results if result.failure_reason
    ]
    add(
        "x2_experience_bullet_evidence_density_required",
        not evidence_density_failures,
        evidence_density_failures or "all_pass",
        "every experience bullet has a specific action, concrete delivery detail, and bound outcome",
        "; ".join(evidence_density_failures) if evidence_density_failures else None,
    )

    (
        scope_ok,
        source_ids,
        scope_threshold,
        scope_fail,
        serialized,
        coverage_ok,
        output_ids,
        ledger_roots,
        coverage_threshold,
        coverage_msg,
    ) = _eval_ibm_scope_and_coverage(
        bullets,
        parsed_output,
        claim_ledger,
        allowed_fact_ids,
        proof_pool_metadata,
        expected_bullet_ids,
    )
    add("x2_ibm_only_fact_scope", scope_ok, sorted(source_ids), scope_threshold, None if scope_ok else scope_fail)
    add("x2_no_unify_fact_leakage", "bul_unify_" not in serialized, "bul_unify_", "absent", "Unify bullet fact leakage detected.")

    term_hits = [pat for pat in UNIFY_RUNTIME_TERM_PATTERNS if re.search(pat, combined, re.I)]
    add("x2_no_unify_runtime_terms", not term_hits, term_hits, [], "Unify runtime vocabulary leaked into IBM bullets.")
    add("x2_no_agentic_inflation", not re.search(r"\bagentic\b", combined, re.I), "agentic token", "absent", "Agentic inflation language in IBM bullets.")

    prefix_hits = _taxonomy_prefix_violations(bullets)
    add("x2_no_taxonomy_label_prefix_in_display_text", not prefix_hits, prefix_hits, [], "bullet_text must not start with a category-style Title: prefix.")

    jd_copy, jd_phrase = has_jd_phrase_copy(combined, jd_text)
    add("x2_no_jd_only_claims", not jd_copy, jd_phrase or "none", "no JD copy as proof", "JD phrase copied into bullet proof.")
    add(
        "x2_claim_ledger_coverage_100",
        coverage_ok and len(claim_ledger) >= len(output_ids) and len(output_ids) >= 1,
        {"output_ids": sorted(output_ids), "ledger_roots": sorted(ledger_roots)},
        coverage_threshold,
        coverage_msg,
    )
    add(
        "x2_metric_fact_id_granularity",
        _metric_granularity_ok(bullets, claim_ledger, plan_facts=plan_facts_for_anchors),
        len(claim_ledger),
        "metric claims map to bul_ibm_* (canonical pairing OR plan-fact metric ownership)",
        "Metric claims lack matching bul_ibm_* source_fact_ids in claim_ledger.",
    )
    add("x2_no_inline_source_tags", not INLINE_SOURCE_PATTERN.search(combined), "inline tags", "absent", "Inline source tags found in bullet text.")
    add("x2_no_first_person", not FIRST_PERSON_PATTERN.search(combined), "first person", "absent", "First-person pronoun found.")
    add("x2_no_em_dash", EM_DASH not in combined, "em dash", "absent", "Em dash found.")
    filler_hit = next((f for f in GENERIC_FILLER if f.lower() in combined.lower()), None)
    add("x2_no_generic_filler", filler_hit is None, filler_hit or "none", "absent", "Generic filler phrase found.")

    json_ok, json_reason = check_json_parse_valid(parsed_output, raw_output)
    add("x2_json_parse_valid", json_ok, json_reason, None, json_reason)

    provider_ok = provider_requested == provider_attempted if provider_requested else True
    add("x2_provider_requested_attempted", provider_ok, f"{provider_requested}->{provider_attempted}", "match", "Provider requested does not match attempted.")
    no_silent_mock = not (provider_requested == "external_claude" and runtime_generation_status == "MOCKED")
    add("x2_no_silent_mock_fallback", no_silent_mock, runtime_generation_status, "REAL_LLM when PROVIDER_MODEL requested", "Silent mock fallback detected.")

    from apps_rg.runtime.section_judge_policy import get_section_judge_policy

    required_judge_providers = list(get_section_judge_policy("ibm_bullets").required_judge_providers)
    judges_ok, judges_reason = check_judge_rows_present(x1d_judges, required_providers=required_judge_providers)
    add("x2_x1d_required_judges_present", judges_ok, judges_reason, required_judge_providers, judges_reason)

    if x1d_judges:
        blocked_invalid = _eval_blocked_judge_schemas(x1d_judges)
        add("x2_x1d_schema_valid", not blocked_invalid, blocked_invalid, [], f"Blocked judges with invalid schema: {blocked_invalid}")
    else:
        add("x2_x1d_schema_valid", False, "no judges", "present", "No X1D judges.")

    from apps_rg.runtime.validators.section_input_usage_x2 import append_section_input_usage_x2_gates

    if srfs_source_fact_slice_gate_active or proof_pool_metadata:
        from apps_rg.runtime.sections import graph_evidence_contract as _graph_evidence
        from apps_rg.runtime.validators.proof_pool_source_fact_validation import (
            evaluate_proof_pool_source_fact_gate,
            proof_pool_x2_gate_id,
        )

        coll_ib = _graph_evidence.collect_source_fact_ids_from_bullets_and_ledger(parsed_output, claim_ledger)
        ok_ib, env_ib, fail_ib = evaluate_proof_pool_source_fact_gate(
            section_id="ibm_bullets",
            collected_ids=coll_ib,
            allowed_fact_ids=set(allowed_fact_ids),
            proof_pool_metadata=proof_pool_metadata,
            proof_pool_ref=proof_pool_ref,
            proof_pool_digest=proof_pool_digest,
        )
        add(
            proof_pool_x2_gate_id("ibm_bullets", proof_pool_metadata=proof_pool_metadata, srfs_slice_gate_active=srfs_source_fact_slice_gate_active),
            ok_ib,
            env_ib,
            "active_proof_pool_allowlist_exact",
            fail_ib,
        )

    from apps_rg.runtime.validators.narrative_quality_x2 import check_within_section_bullet_cosine_similarity

    ibm_b_cos = check_within_section_bullet_cosine_similarity(
        [str(b.get("bullet_text") or "") for b in (bullets or []) if isinstance(b, dict)],
        max_pairwise_cosine=0.35,
    )
    add(ibm_b_cos.gate_id, ibm_b_cos.passed, ibm_b_cos.observed_value, ibm_b_cos.threshold, ibm_b_cos.failure_reason)

    append_section_input_usage_x2_gates(
        gates,
        artifacts_dir=artifacts_dir or Path("artifacts/apps_rg/runtime_proofs/ibm_bullets"),
        allowed_fact_ids=allowed_fact_ids,
        claim_ledger=claim_ledger,
        text_claim_coverage=(parsed_output or {}).get("text_claim_coverage") if isinstance(parsed_output, dict) else None,
        runtime_payload=runtime_payload,
    )
    return gates


__all__ = [
    "IBM_BULLET_GRAPH_SKILL_NODE_IDS_GATE_ID",
    "IBM_BULLET_IDS",
    "IBM_BULLET_METRIC_SOURCE_GATE_ID",
    "IBM_METRIC_ANCHOR_RULES",
    "REQUIRED_TOP_LEVEL",
    "TAXONOMY_LABEL_PREFIX_PATTERN",
    "TEXT_COVERAGE_INTEGRITY_GATE_ID",
    "build_ibm_bullets_text_claim_coverage",
    "check_ibm_bullets_text_claim_coverage_integrity",
    "ibm_bullet_text_has_taxonomy_label_prefix",
    "run_ibm_bullets_x2_gates",
]
