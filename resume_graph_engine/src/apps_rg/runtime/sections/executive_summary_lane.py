"""Executive summary section lane — ``python -m apps_rg --section executive_summary``.

Lane-scoped modular runtime (proof pool -> section graph binding shim -> PA -> L2 -> section X2/X3/L6).
**Not** the integrated R4 governed spine (U0->L1->L0->C0->PA->L2->Exit). Invoked from
``apps_rg.runtime.orchestration.canonical_dispatch`` section branch only.

**W3 classification:** ``declared_temporary_slice`` until one-spine convergence.
"""
from __future__ import annotations

if __name__ == "__main__":
    raise ImportError(
        "This module is not an operator CLI entrypoint. "
        "Use the sole canonical public command: python -m resume_engine run"
    )

import argparse
from pathlib import Path
from typing import Any

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
    _wg,
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
from apps_rg.runtime.sections.executive_summary.prompt_builder import (
    _CLAUSE_SPLIT_PATTERNS,
    _EXEC_SUMMARY_TARGET_SENTENCES,
    L2_BRIDGE_PHRASE_PATTERN,
    L2_PASSIVE_CYCLE_PATTERN,
    _repair_speculative_exec_summary_capstone,
    _split_compound_sentence,
    build_prompt_messages,
    check_executive_summary_narrative_shape,
    check_l2_resume_voice,
    coerce_resume_display_sentence_count_band,
    enrich_parsed_for_x2,
    normalize_executive_summary_llm_output,
    parse_model_json,
    prune_exec_summary_claim_ledger_orphans,
    reconcile_claim_ledger_to_sentence_count,
    salvage_truncated_executive_summary_json,
)
from apps_rg.runtime.sections.executive_summary.synthesis_shape_repair import (
    _apply_pre_synthesis_candidate_repairs,
    _build_synthesis_repair_user,
    _regen_candidate_preferred,
    _shape_failure_count,
    _synthesis_shape_reject_reason,
)
from apps_rg.runtime.sections.executive_summary.synthesis_retry import (
    retry_provider_for_synthesis,
)
from apps_rg.runtime.sections.executive_summary.word_budget_repair import (
    WORD_BUDGET_REPAIR_RECEIPT_FILENAME,
    _build_word_budget_repair_user,
    _emit_dimension_upstream_triangulation,
    _write_x1d_judge_artifacts,
    apply_exec_summary_word_budget_repair,
    set_word_budget_repair_authoritative_after_x2,
)
from apps_rg.runtime.sections.executive_summary.stage_closeout import (
    run_closeout_post_x3,
    run_closeout_pre_x3,
)
from apps_rg.runtime.sections.executive_summary.stage_generation import (
    run_generation_stage,
)
from apps_rg.runtime.sections.executive_summary.stage_ingress import (
    run_ingress_dispatch,
    run_ingress_setup,
)
from apps_rg.runtime.sections.executive_summary.stage_remediation import (
    run_remediation_stage,
)
from apps_rg.runtime.validators.executive_summary_x2 import (
    check_exec_summary_paragraph_max_words,
)

# Retries check word bounds via check_exec_summary_paragraph_max_words, meta filler patterns including "this individual", and persist synthesis_regen_receipt.json.


def infer_product_quality(
    runtime_generation_status: str,
    x2_gates: list[dict[str, Any]],
    resume_display_text: str,
    claim_ledger: list[dict[str, Any]],
    *,
    graph_only_fact_tight_synthesis: bool = False,
    artifact_dir: Path | None = None,
) -> tuple[str, str]:
    """Product quality follows X2 + repair ledger (P1 counted regen policy)."""
    _ = (resume_display_text, claim_ledger, graph_only_fact_tight_synthesis)
    failed = [g["gate_id"] for g in x2_gates if not g.get("pass")]
    from apps_rg.runtime.section_repair_ledger import infer_product_quality_with_repair_ledger

    return infer_product_quality_with_repair_ledger(
        runtime_generation_status=runtime_generation_status,
        x2_failed_gate_ids=failed,
        pass_reason="REAL_LLM output passed all deterministic X2 gates.",
        artifact_dir=artifact_dir,
    )


def run_executive_summary_execution(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Single end-to-end executive_summary run: artifacts + X2/X1D/X3."""
    from apps_rg.runtime.section_repair_ledger import init_ledger

    ctx = run_ingress_setup(args, artifact_dir_override=artifact_dir_override)
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    init_ledger(
        artifact_dir,
        section_id="executive_summary",
        run_id=str(runtime_payload["run_id"]),
    )
    early_return = run_ingress_dispatch(ctx)
    if early_return is not None:
        return early_return
    run_generation_stage(ctx)

    x2 = ctx["x2"]
    x1d = ctx["x1d"]
    runtime_generation_status = ctx["runtime_generation_status"]
    x2_failed_initial = [g for g in x2 if not g["pass"]]
    ctx["x2_failed_initial"] = x2_failed_initial
    if x2_failed_initial or runtime_generation_status != "REAL_LLM":
        write_json(
            artifact_dir / "fact_check_result.json",
            {"passed": not x2_failed_initial, "failed_gates": [g["gate_id"] for g in x2_failed_initial]},
        )
    set_word_budget_repair_authoritative_after_x2(
        artifact_dir,
        accepted=ctx["_word_budget_repair_accepted"],
        x2_gates=x2,
    )
    if x2_failed_initial and not (artifact_dir / "x1d_llm_judge_outputs.json").is_file():
        _write_x1d_judge_artifacts(artifact_dir, x1d)

    run_remediation_stage(ctx, emit_initial_gate_artifacts=False)
    run_closeout_pre_x3(ctx)

    x3 = ctx["x3"]
    x2 = ctx["x2"]
    write_json(
        artifact_dir / "fact_check_result.json",
        {
            "passed": not [g for g in x2 if not g["pass"]],
            "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]],
            "x3_code": x3.get("x3_code") if isinstance(x3, dict) else None,
            "product_quality_status": ctx["product_quality_status"],
        },
    )
    return run_closeout_post_x3(ctx)


__all__ = [
    "BRIEFING_DEFAULT",
    "EXEC_SUMMARY_TEMP_DEFAULT",
    "EXEC_SUMMARY_TEMP_RANGE",
    "JD_TEXT_DEFAULT",
    "LANE_KEY",
    "PROMPT_ID",
    "PROMPT_TEMPLATE",
    "REPO_ROOT",
    "TARGET_COMPANY_DEFAULT",
    "TARGET_TITLE_DEFAULT",
    "BASE_JSON_DEFAULT",
    "BASE_POINTER",
    "truncate_briefing_for_exec_summary_external_model",
    "build_mock_output",
    "build_prompt_messages",
    "build_runtime_payload",
    "build_selected_fact_plan",
    "check_executive_summary_narrative_shape",
    "check_exec_summary_paragraph_max_words",
    "check_l2_resume_voice",
    "enrich_parsed_for_x2",
    "extract_allowed_facts",
    "infer_product_quality",
    "load_base_resume",
    "parse_model_json",
    "resolve_provider_model_name",
    "retry_provider_for_synthesis",
    "run_executive_summary_execution",
    "sha16",
    "write_json",
    "write_x2_gate_outputs",
]
