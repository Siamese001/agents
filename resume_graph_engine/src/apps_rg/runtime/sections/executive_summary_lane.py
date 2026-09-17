"""Executive summary section lane — ``python -m apps_rg --section executive_summary``.

Lane-scoped modular runtime (proof pool → section graph binding shim → PA → L2 → section X2/X3/L6).
**Not** the integrated R4 governed spine (U0→L1→L0→C0→PA→L2→Exit). Invoked from
``apps_rg.runtime.orchestration.canonical_dispatch`` section branch only.

This module is a backward-compatible facade re-exporting from
``apps_rg.runtime.sections.executive_summary``.
"""
from __future__ import annotations

if __name__ == "__main__":
    raise ImportError(
        "This module is not an operator CLI entrypoint. "
        "Use the sole canonical public command: python -m apps_rg run"
    )

# Product shape rules, "this individual", and synthesis_regen_receipt.json compatibility
from apps_rg.runtime.sections.executive_summary_context_limits import (
    resolve_scratch_max_output_tokens,
)
from apps_rg.runtime.validators.executive_summary_x2 import (
    check_exec_summary_paragraph_max_words,
)

from apps_rg.runtime.sections.executive_summary.context_assembler import (
    _args_jd_text,
    _args_target_title,
    _fact_body_for_mock_synthesis,
    _finalize_executive_summary_l7_binding,
    _first_sentence_from_prose,
    _proof_pool_mode_from_payload,
    _reconcile_final_plan_c03_allowlist,
    _strip_targeting_cap_notice,
    build_mock_output,
    build_runtime_payload,
    build_selected_fact_plan,
    extract_allowed_facts,
    load_base_resume,
    resolve_provider_model_name,
    sha16,
    truncate_briefing_for_exec_summary_external_model,
    write_json,
    write_x2_gate_outputs,
)
from apps_rg.runtime.sections.executive_summary.lane_constants import (
    BASE_JSON_DEFAULT,
    BASE_POINTER,
    BRIEFING_DEFAULT,
    CHECKOUT_ROOT,
    EXEC_SUMMARY_TEMP_DEFAULT,
    EXEC_SUMMARY_TEMP_RANGE,
    JD_TEXT_DEFAULT,
    LANE_KEY,
    PROMPT_ID,
    PROMPT_TEMPLATE,
    REPO_ROOT,
    TARGET_COMPANY_DEFAULT,
    TARGET_TITLE_DEFAULT,
    W3_EXECUTION_PATH_BUCKET,
    W3_EXECUTION_PATH_PLAN_SLUG,
    _find_repo_root,
)
from apps_rg.runtime.sections.executive_summary.lane_runner import (
    run_executive_summary_execution,
)
from apps_rg.runtime.sections.executive_summary.parsing import (
    count_words,
    extract_bullets,
    tokenize_sentences,
)
from apps_rg.runtime.sections.executive_summary.prompt_builder import (
    L2_BRIDGE_PHRASE_PATTERN,
    L2_PASSIVE_CYCLE_PATTERN,
    _EXEC_SUMMARY_TARGET_SENTENCES,
    _repair_speculative_exec_summary_capstone,
    _split_compound_sentence,
    build_prompt_messages,
    check_executive_summary_narrative_shape,
    check_l2_resume_voice,
    coerce_resume_display_sentence_count_band,
    enrich_parsed_for_x2,
    infer_product_quality,
    normalize_executive_summary_llm_output,
    parse_model_json,
    prune_exec_summary_claim_ledger_orphans,
    reconcile_claim_ledger_to_sentence_count,
    salvage_truncated_executive_summary_json,
)
from apps_rg.runtime.sections.executive_summary.stage_closeout import (
    run_closeout_stage,
)
from apps_rg.runtime.sections.executive_summary.stage_generation import (
    run_generation_stage,
)
from apps_rg.runtime.sections.executive_summary.stage_ingress import (
    run_ingress_stage,
)
from apps_rg.runtime.sections.executive_summary.stage_remediation import (
    run_remediation_stage,
)
from apps_rg.runtime.sections.executive_summary.stage_remediation_cycles import (
    run_remediation_cycles,
)
from apps_rg.runtime.sections.executive_summary.stage_remediation_draft import (
    process_remediation_draft,
)
from apps_rg.runtime.sections.executive_summary.stage_remediation_pool import (
    finalize_remediation_candidate_pool,
)
from apps_rg.runtime.sections.executive_summary.synthesis_retry import (
    retry_provider_for_synthesis,
)
from apps_rg.runtime.sections.executive_summary.synthesis_shape_repair import (
    _build_synthesis_repair_user,
    _regen_candidate_preferred,
    _shape_failure_count,
    _synthesis_shape_reject_reason,
)
from apps_rg.runtime.sections.executive_summary.word_budget_repair import (
    WORD_BUDGET_REPAIR_RECEIPT_FILENAME,
    _build_word_budget_repair_user,
    _emit_dimension_upstream_triangulation,
    _write_x1d_judge_artifacts,
    apply_exec_summary_word_budget_repair,
    set_word_budget_repair_authoritative_after_x2,
)

__all__ = [
    "run_executive_summary_execution",
    "resolve_scratch_max_output_tokens",
    "check_exec_summary_paragraph_max_words",
    "LANE_KEY",
    "REPO_ROOT",
    "CHECKOUT_ROOT",
    "TARGET_TITLE_DEFAULT",
    "TARGET_COMPANY_DEFAULT",
    "JD_TEXT_DEFAULT",
    "BRIEFING_DEFAULT",
    "EXEC_SUMMARY_TEMP_DEFAULT",
    "EXEC_SUMMARY_TEMP_RANGE",
    "BASE_POINTER",
    "BASE_JSON_DEFAULT",
    "PROMPT_TEMPLATE",
    "PROMPT_ID",
]
