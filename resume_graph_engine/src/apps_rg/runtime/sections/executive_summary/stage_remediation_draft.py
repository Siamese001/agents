"""Stage 3b: Prepare regenerated draft candidate, check G1/G5, and run X2 repair."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .word_budget_repair import *
from .parent_proxy import _lane_attr

from .stage_remediation_draft_eval import evaluate_remediation_draft_post_x2


def process_remediation_draft(ctx: dict[str, Any]) -> str | None:
    """Prepare candidate after judge regen, run G1/G5/X2, and delegate post-X2 pool eval."""
    from apps_rg.runtime.sections.executive_summary_judge_regen_loop import (
        advance_regen_thread_for_next_cycle,
        post_regen_x2_repair_eligible,
        prepare_parsed_after_judge_regen,
        preserve_judge_regen_claim_ledger_from_baseline,
        resume_display_text_from_regen_messages,
        snapshot_regen_candidate,
        sync_claim_ledger_metrics_from_facts,
    )
    from apps_rg.runtime.sections.executive_summary_judge_remediation import (
        repair_judge_regen_after_x2_fail,
        rerun_x2_after_judge_remediation,
    )
    from apps_rg.runtime.sections.executive_summary_regen_delta_policy import (
        emit_judge_regen_operator_stderr,
        evaluate_g5_delta_scope_v2,
        format_judge_regen_operator_stderr_line,
    )
    from apps_rg.runtime.sections.executive_summary_regen_observability import (
        finalize_regen_cycle_observability,
    )
    from apps_rg.runtime.sections.executive_summary_voice_repair import (
        finalize_executive_summary_coherence,
    )
    from apps_rg.runtime.sections.section_authority_repairs import (
        apply_exec_summary_display_authority_repairs,
    )

    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    pool = ctx["pool"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    provider_payload = ctx["provider_payload"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed_regen = ctx["parsed_regen"]
    parsed = ctx["parsed"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    coverage = ctx["coverage"]
    l2_output = ctx["l2_output"]
    x1d = ctx["x1d"]
    x2 = ctx["x2"]
    model_name = ctx["model_name"]
    prompt_hash = ctx["prompt_hash"]
    compiled_prompt = ctx["compiled_prompt"]
    temperature = ctx["temperature"]
    input_payload_hash = ctx["input_payload_hash"]
    pp_x2 = ctx["pp_x2"]
    proof_pool_x2_active = ctx["proof_pool_x2_active"]
    selected_facts_for_x2 = ctx["selected_facts_for_x2"]
    _judge_jd = ctx["_judge_jd"]
    _cycle_idx = ctx["_cycle_idx"]
    _max_judge_cycles = ctx["_max_judge_cycles"]
    _regen_messages = ctx["_regen_messages"]
    _prior_regen_output_hash = ctx["_prior_regen_output_hash"]
    _cycles_receipt = ctx["_cycles_receipt"]
    _cycle_record = ctx["_cycle_record"]
    _draft_parse_ok = ctx["_draft_parse_ok"]
    _j_receipt = ctx["_j_receipt"]
    _pre_parsed = ctx["_pre_parsed"]
    _pre_raw = ctx["_pre_raw"]
    _pre_resume = ctx["_pre_resume"]
    _pre_ledger = ctx["_pre_ledger"]
    _pre_x2 = ctx["_pre_x2"]
    _x1d_before_regen = ctx["_x1d_before_regen"]
    _scores_before_regen = ctx["_scores_before_regen"]
    _cycle_delta_class = ctx["_cycle_delta_class"]
    _strategy_exec_regen = ctx["_strategy_exec_regen"]
    _operator_judge_floor = ctx["_operator_judge_floor"]
    _judge_prompt_x1d = ctx["_judge_prompt_x1d"]
    _regen_incremental_anchor_parsed = ctx["_regen_incremental_anchor_parsed"]
    _regen_prior_cycle_judges = ctx["_regen_prior_cycle_judges"]
    _last_regen_candidate = ctx["_last_regen_candidate"]
    _regen_attempt_parsed_snapshot = ctx["_regen_attempt_parsed_snapshot"]
    _reject_gate = None

    def _sync_ctx() -> None:
        ctx.update({
            "raw_output": raw_output,
            "parsed": parsed,
            "parsed_for_x2": parsed_for_x2,
            "resume_display_text": resume_display_text,
            "claim_ledger": claim_ledger,
            "coverage": coverage,
            "x1d": x1d,
            "x2": x2,
            "_prior_regen_output_hash": _prior_regen_output_hash,
            "_regen_messages": _regen_messages,
            "_judge_prompt_x1d": _judge_prompt_x1d,
            "_regen_incremental_anchor_parsed": _regen_incremental_anchor_parsed,
            "_regen_prior_cycle_judges": _regen_prior_cycle_judges,
            "_last_regen_candidate": _last_regen_candidate,
            "_regen_attempt_parsed_snapshot": _regen_attempt_parsed_snapshot,
            "parsed_regen": parsed_regen,
            "_reject_gate": _reject_gate,
            "x2_regen": locals().get("x2_regen", []),
            "_x2_failed": locals().get("_x2_failed", []),
        })

    from apps_rg.runtime.section_repair_ledger import (
        KIND_REGEN_LLM,
        record_repair,
        set_authoritative_attempt,
    )

    parsed = parsed_regen
    parsed, _prepare_receipt = prepare_parsed_after_judge_regen(
        parsed,
        allowed_fact_ids=allowed_fact_ids,
        plan_facts=list(selected_fact_plan.get("facts") or []),
        artifact_dir=artifact_dir,
        target_company=str(getattr(args, "target_company", "") or ""),
    )
    parsed, _preserve_receipt = preserve_judge_regen_claim_ledger_from_baseline(
        parsed,
        baseline_parsed=_pre_parsed,
        allowed_fact_ids=allowed_fact_ids,
    )
    _prepare_receipt["preserve_ledger"] = _preserve_receipt
    parsed, _g1_receipt = sync_claim_ledger_metrics_from_facts(
        parsed,
        plan_facts=list(selected_fact_plan.get("facts") or []),
        allowed_fact_ids=allowed_fact_ids,
    )
    _prepare_receipt["g1_ledger_metric_sync"] = _g1_receipt
    _regen_attempt_parsed_snapshot = dict(parsed)
    if artifact_dir is not None:
        _lane_attr("write_json", write_json)(
            artifact_dir / "judge_regen_prepare_receipt.json",
            _prepare_receipt,
        )
        _lane_attr("write_json", write_json)(
            artifact_dir / "g1_ledger_metric_sync_receipt.json",
            _g1_receipt,
        )
    if not _g1_receipt.get("passed"):
        _reject_gate = str(
            _g1_receipt.get("reject_gate") or "ledger_metric_sync_ambiguous"
        )
        _cycle_record["accepted"] = False
        _cycle_record["draft_parse_ok"] = _draft_parse_ok
        _cycle_record["publish_eligible"] = False
        _cycle_record["reject_gate"] = _reject_gate
        _cycle_record["g1_passed"] = False
        _j_receipt["accepted"] = False
        _j_receipt["draft_parse_ok"] = _draft_parse_ok
        _j_receipt["g1_rejected"] = True
        _j_receipt["reject_gate"] = _reject_gate
        if artifact_dir is not None:
            _lane_attr("write_json", write_json)(
                artifact_dir / "judge_remediation_receipt.json",
                _j_receipt,
            )
        raw_output = _pre_raw
        parsed = dict(_pre_parsed)
        parsed_for_x2 = dict(_pre_parsed)
        resume_display_text = _pre_resume
        claim_ledger = list(_pre_ledger)
        x1d = list(_x1d_before_regen)
        x2 = list(_pre_x2)
        _prior_regen_output_hash, _conv = finalize_regen_cycle_observability(
            _cycles_receipt,
            _cycle_record,
            cycle_index=_cycle_idx,
            artifact_dir=artifact_dir,
            judge_remediation_receipt=_j_receipt,
            prior_regen_output_hash=_prior_regen_output_hash,
        )
        if _conv:
            _sync_ctx()
            return "break"
        if _cycle_idx + 1 >= _max_judge_cycles:
            _cycles_receipt["stopped_reason"] = _reject_gate
            _sync_ctx()
            return "break"
        _sync_ctx()
        return "continue"

    _cycle_record["g1_passed"] = True
    resume_display_text = str(parsed.get("resume_display_text") or resume_display_text)
    _g5_baseline = (
        resume_display_text_from_regen_messages(_regen_messages) or _pre_resume
    )
    _g5 = evaluate_g5_delta_scope_v2(
        _g5_baseline,
        resume_display_text,
        _cycle_delta_class,
        x1d_judges=_x1d_before_regen,
    )
    _cycle_record["g5_delta_scope"] = _g5
    if artifact_dir is not None:
        _lane_attr("write_json", write_json)(
            artifact_dir / f"g5_delta_scope_cycle_{_cycle_idx + 1}.json",
            _g5,
        )
    if not _g5.get("passed"):
        _reject_gate = str(_g5.get("reject_gate") or "delta_scope_violation")
        _regen_raw_for_thread = str(raw_output or "")
        _cycle_record["accepted"] = False
        _cycle_record["draft_parse_ok"] = _draft_parse_ok
        _cycle_record["publish_eligible"] = False
        _cycle_record["reject_gate"] = _reject_gate
        _cycle_record["g5_passed"] = False
        _j_receipt["accepted"] = False
        _j_receipt["draft_parse_ok"] = _draft_parse_ok
        _j_receipt["g5_rejected"] = True
        _j_receipt["reject_gate"] = _reject_gate
        emit_judge_regen_operator_stderr(
            format_judge_regen_operator_stderr_line(
                cycle=_cycle_idx + 1,
                reject_gate=_reject_gate,
                g3_verdicts=None,
                operator_floor=_operator_judge_floor,
                final_publish_baseline="scratch",
                published_min_score=None,
            ),
        )
        _lane_attr("write_json", write_json)(artifact_dir / "judge_remediation_receipt.json", _j_receipt)
        raw_output = _pre_raw
        parsed = dict(_pre_parsed)
        parsed_for_x2 = dict(_pre_parsed)
        resume_display_text = _pre_resume
        claim_ledger = list(_pre_ledger)
        x1d = list(_x1d_before_regen)
        x2 = list(_pre_x2)
        if _j_receipt.get("output_changed") and _regen_raw_for_thread.strip():
            from apps_rg.runtime.sections.executive_summary_judge_regen_loop import (
                extend_regen_thread_after_success,
            )

            _regen_messages = extend_regen_thread_after_success(
                _regen_messages,
                _regen_raw_for_thread,
            )
        if _regen_attempt_parsed_snapshot is not None:
            _regen_incremental_anchor_parsed = _regen_attempt_parsed_snapshot
            _regen_prior_cycle_judges = list(_x1d_before_regen)
        _prior_regen_output_hash, _conv = finalize_regen_cycle_observability(
            _cycles_receipt,
            _cycle_record,
            cycle_index=_cycle_idx,
            artifact_dir=artifact_dir,
            judge_remediation_receipt=_j_receipt,
            prior_regen_output_hash=_prior_regen_output_hash,
        )
        if _conv:
            _sync_ctx()
            return "break"
        if _cycle_idx + 1 >= _max_judge_cycles:
            _cycles_receipt["stopped_reason"] = _reject_gate
            _sync_ctx()
            return "break"
        _sync_ctx()
        return "continue"

    _cycle_record["g5_passed"] = True
    claim_ledger = list(parsed.get("claim_ledger") or claim_ledger)
    coverage = build_sentence_claim_coverage(
        resume_display_text, claim_ledger, allowed_fact_ids
    )
    parsed_for_x2 = enrich_parsed_for_x2(
        parsed,
        coverage=coverage,
        input_payload_hash=input_payload_hash,
        allowed_fact_ids=allowed_fact_ids,
        runtime_payload=runtime_payload,
    )
    _wg.write_text(artifact_dir / "raw_model_output.txt", raw_output or "", encoding="utf-8")
    _wg.write_text(
        artifact_dir / "resume_display_text.txt",
        resume_display_text + "\n", encoding="utf-8"
    )
    _lane_attr("write_json", write_json)(artifact_dir / "claim_ledger.json", claim_ledger)
    _lane_attr("write_json", write_json)(artifact_dir / "text_claim_coverage.json", coverage)
    x2_regen = rerun_x2_after_judge_remediation(
        resume_display_text=resume_display_text,
        parsed_for_x2=parsed_for_x2,
        claim_ledger=claim_ledger,
        text_claim_coverage=coverage,
        allowed_fact_ids=allowed_fact_ids,
        args=args,
        jd_text=_judge_jd,
        temperature=temperature,
        runtime_generation_status=runtime_generation_status,
        artifact_dir=artifact_dir,
        model_name=model_name,
        prompt_hash=prompt_hash,
        compiled_prompt=compiled_prompt,
        raw_output=raw_output,
        selected_facts=selected_facts_for_x2,
        selected_fact_plan=selected_fact_plan,
        x1d_judges=x1d,
        proof_pool_metadata=pp_x2 if proof_pool_x2_active else None,
        proof_pool_ref=str(pool.proof_pool_ref or ""),
        proof_pool_digest=str(pool.proof_pool_digest or ""),
    )
    _x2_failed = [g for g in x2_regen if not g["pass"]]
    _last_regen_candidate = snapshot_regen_candidate(
        raw_output=raw_output or "",
        parsed=parsed,
        resume_display_text=resume_display_text,
        claim_ledger=claim_ledger,
        x2_gates=x2_regen,
    )
    if _x2_failed and post_regen_x2_repair_eligible(_x2_failed):
        _raw_x2r, _parsed_x2r, _x2_repair_rcpt = repair_judge_regen_after_x2_fail(
            _regen_messages,
            provider_payload,
            baseline_parsed=_pre_parsed,
            regen_raw=raw_output,
            regen_parsed=parsed,
            failed_x2_gates=x2_regen,
            selected_fact_plan=selected_fact_plan,
            allowed_fact_ids=allowed_fact_ids,
            strategy_executive=_strategy_exec_regen,
            artifact_dir=artifact_dir,
            run_id=str(runtime_payload.get("run_id") or "") or None,
        )
        _cycle_record["x2_repair"] = _x2_repair_rcpt
        if _x2_repair_rcpt.get("accepted"):
            parsed_regen = _parsed_x2r
            raw_output = _raw_x2r
            parsed = parsed_regen
            parsed = apply_exec_summary_display_authority_repairs(
                parsed,
                allowed_fact_ids=allowed_fact_ids,
                plan_facts=list(selected_fact_plan.get("facts") or []),
                artifact_dir=artifact_dir,
                target_company=str(getattr(args, "target_company", "") or ""),
            )
            parsed, _finalize_receipt = finalize_executive_summary_coherence(
                parsed,
                selected_facts=list(selected_fact_plan.get("facts") or []),
                allowed_fact_ids=allowed_fact_ids,
            )
            resume_display_text = str(
                parsed.get("resume_display_text") or resume_display_text
            )
            claim_ledger = list(parsed.get("claim_ledger") or claim_ledger)
            coverage = build_sentence_claim_coverage(
                resume_display_text, claim_ledger, allowed_fact_ids
            )
            parsed_for_x2 = enrich_parsed_for_x2(
                parsed,
                coverage=coverage,
                input_payload_hash=input_payload_hash,
                allowed_fact_ids=allowed_fact_ids,
                runtime_payload=runtime_payload,
            )
            x2_regen = rerun_x2_after_judge_remediation(
                resume_display_text=resume_display_text,
                parsed_for_x2=parsed_for_x2,
                claim_ledger=claim_ledger,
                text_claim_coverage=coverage,
                allowed_fact_ids=allowed_fact_ids,
                args=args,
                jd_text=_judge_jd,
                temperature=temperature,
                runtime_generation_status=runtime_generation_status,
                artifact_dir=artifact_dir,
                model_name=model_name,
                prompt_hash=prompt_hash,
                compiled_prompt=compiled_prompt,
                raw_output=raw_output,
                selected_facts=selected_facts_for_x2,
                selected_fact_plan=selected_fact_plan,
                x1d_judges=x1d,
                proof_pool_metadata=pp_x2 if proof_pool_x2_active else None,
                proof_pool_ref=str(pool.proof_pool_ref or ""),
                proof_pool_digest=str(pool.proof_pool_digest or ""),
            )
            _x2_failed = [g for g in x2_regen if not g["pass"]]
            _last_regen_candidate = snapshot_regen_candidate(
                raw_output=raw_output or "",
                parsed=parsed,
                resume_display_text=resume_display_text,
                claim_ledger=claim_ledger,
                x2_gates=x2_regen,
            )

    _sync_ctx()
    return evaluate_remediation_draft_post_x2(ctx)
