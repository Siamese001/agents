"""Processing of parsed or prefiltered draft candidate during remediation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .word_budget_repair import *

def process_remediation_draft(ctx: dict[str, Any]) -> str | None:
    args, artifact_dir, runtime_payload, proof_pool_metadata = ctx["args"], ctx["artifact_dir"], ctx["runtime_payload"], ctx["proof_pool_metadata"]
    targeting_ingress, messages, req, scratch_max_tokens = ctx["targeting_ingress"], ctx["messages"], ctx["req"], ctx["scratch_max_tokens"]
    token_budget_receipt, usage_doc, briefing_text_bounded, pool = ctx["token_budget_receipt"], ctx["usage_doc"], ctx["briefing_text_bounded"], ctx["pool"]
    base_path, base_hash, base, selected_fact_plan = ctx["base_path"], ctx["base_hash"], ctx["base"], ctx["selected_fact_plan"]
    allowed_fact_ids, allowed_fact_ids_ordered, result, provider_result_data = ctx["allowed_fact_ids"], ctx["allowed_fact_ids_ordered"], ctx["result"], ctx["provider_result_data"]
    raw_output, runtime_generation_status, parsed, parse_error = ctx["raw_output"], ctx["runtime_generation_status"], ctx["parsed"], ctx["parse_error"]
    resume_display_text, claim_ledger = ctx["resume_display_text"], ctx["claim_ledger"]
    _word_budget_repair_accepted, _word_budget_repair_audit = ctx["_word_budget_repair_accepted"], ctx["_word_budget_repair_audit"]
    _composition_plan_early, parsed_for_x2, x2 = ctx["_composition_plan_early"], ctx["parsed_for_x2"], ctx["x2"]
    _generation_material, _bundle_mat, _targeting_parity = ctx["_generation_material"], ctx["_bundle_mat"], ctx["_targeting_parity"]
    x1d, x2_failed_initial, _judge_prompt_x1d = ctx["x1d"], ctx["x2_failed_initial"], ctx["_judge_prompt_x1d"]
    _gtc_lane_dict, _pool_publish_applied, _max_judge_cycles = ctx["_gtc_lane_dict"], ctx["_pool_publish_applied"], ctx["_max_judge_cycles"]
    _cycle_idx, _prior_regen_output_hash, _cycles_receipt = ctx["_cycle_idx"], ctx["_prior_regen_output_hash"], ctx["_cycles_receipt"]
    _candidate_pool, _wg, _cycle_record, _draft_parse_ok = ctx["_candidate_pool"], ctx["_wg"], ctx["_cycle_record"], ctx["_draft_parse_ok"]
    _j_receipt, _pre_parsed, _pre_raw, _pre_resume = ctx["_j_receipt"], ctx["_pre_parsed"], ctx["_pre_raw"], ctx["_pre_resume"]
    _pre_ledger, _pre_x2, _pre_wc, _pre_ledger_rows = ctx["_pre_ledger"], ctx["_pre_x2"], ctx["_pre_wc"], ctx["_pre_ledger_rows"]
    _x1d_before_regen, _scores_before_regen, _cycle_delta_class = ctx["_x1d_before_regen"], ctx["_scores_before_regen"], ctx["_cycle_delta_class"]
    selected_facts_for_x2, _regen_messages, provider_payload = ctx["selected_facts_for_x2"], ctx["_regen_messages"], ctx["provider_payload"]
    model_name, prompt_hash, compiled_prompt, temperature = ctx["model_name"], ctx["prompt_hash"], ctx["compiled_prompt"], ctx["temperature"]
    pp_x2, proof_pool_x2_active, input_payload_hash = ctx["pp_x2"], ctx["proof_pool_x2_active"], ctx["input_payload_hash"]
    _judge_jd, _reject_gate = ctx["_judge_jd"], ctx["_reject_gate"]

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
        write_json(
            artifact_dir / "judge_regen_prepare_receipt.json",
            _prepare_receipt,
        )
        write_json(
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
            write_json(
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
            return "break"
        if _cycle_idx + 1 >= _max_judge_cycles:
            _cycles_receipt["stopped_reason"] = _reject_gate
            return "break"
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
        write_json(
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
        write_json(artifact_dir / "judge_remediation_receipt.json", _j_receipt)
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
            return "break"
        if _cycle_idx + 1 >= _max_judge_cycles:
            _cycles_receipt["stopped_reason"] = _reject_gate
            return "break"
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
    write_json(artifact_dir / "claim_ledger.json", claim_ledger)
    write_json(artifact_dir / "text_claim_coverage.json", coverage)
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
    if not _x2_failed:
        record_repair(
            artifact_dir,
            kind=KIND_REGEN_LLM,
            operation="judge_remediation_regen",
            reason=str(_j_receipt.get("trigger_reason") or "judge_remediation")[:240],
            replaced_l2=True,
        )
        x2 = x2_regen
        _ledger2 = load_ledger(artifact_dir) or {}
        record_x2_run(
            artifact_dir,
            run_number=len(list(_ledger2.get("x2_runs") or [])) + 1,
            after_l2_source="regen_llm",
            x2_gates=x2,
        )
        set_authoritative_attempt(
            artifact_dir,
            2,
            reason="judge_remediation_regen_x2_pass",
        )
        from apps_rg.runtime.sections.executive_summary_judge_remediation import (
            evaluate_g3_trigger_judge_monotonicity,
            rescore_judges_after_regen,
        )

        _jp_rescore = resolve_judge_packet_for_parity(artifact_dir, fallback=judge_packet)
        _jp_rescore_ref = str(
            artifact_dir / "executive_summary_judge_packet_post_x2.json"
        )
        _x1d_after_rescore, _post_regen_x1d_receipt = rescore_judges_after_regen(
            x2_gates=x2,
            resume_display_text=resume_display_text,
            claim_ledger=claim_ledger,
            allowed_fact_packet=selected_facts_for_x2,
            allowed_fact_ids=allowed_fact_ids,
            target_title=_args_target_title(args),
            target_company=str(args.target_company),
            jd_text=_judge_jd,
            briefing_text=_judge_briefing,
            parsed_output=parsed_for_x2,
            judge_keys=judge_keys,
            judge_mode=judge_mode,
            artifact_dir=artifact_dir,
            compiled_prompt=compiled_prompt,
            prior_judges=_x1d_before_regen,
            judge_packet=_jp_rescore,
            judge_packet_ref=_jp_rescore_ref,
        )
        write_json(
            artifact_dir / "post_regen_x1d_rescore_receipt.json",
            _post_regen_x1d_receipt,
        )
        _cycle_record["scores_after"] = _post_regen_x1d_receipt.get("scores_after")
        _cycle_record["score_deltas"] = _post_regen_x1d_receipt.get("score_deltas")
        _g3 = evaluate_g3_trigger_judge_monotonicity(
            prior_judges=_x1d_before_regen,
            after_judges=_x1d_after_rescore,
            scores_before=_scores_before_regen,
            scores_after=_post_regen_x1d_receipt.get("scores_after"),
        )
        write_json(
            artifact_dir / f"g3_trigger_judge_cycle_{_cycle_idx + 1}.json",
            _g3,
        )
        _cycle_record["g3_verdict_per_trigger_judge"] = _g3.get(
            "g3_verdict_per_trigger_judge"
        )
        _regen_messages, _judge_prompt_x1d = advance_regen_thread_for_next_cycle(
            _regen_messages,
            raw_output=raw_output or "",
            x1d_judges=_x1d_after_rescore,
        )
        if not _g3.get("passed"):
            _reject_gate = str(
                _g3.get("reject_gate") or "trigger_judge_regression"
            )
            _cycle_record["accepted"] = False
            _cycle_record["draft_parse_ok"] = _draft_parse_ok
            _cycle_record["publish_eligible"] = False
            _cycle_record["reject_gate"] = _reject_gate
            _cycle_record["g3_passed"] = False
            _j_receipt["accepted"] = False
            _j_receipt["draft_parse_ok"] = _draft_parse_ok
            _j_receipt["g3_rejected"] = True
            _j_receipt["reject_gate"] = _reject_gate
            emit_judge_regen_operator_stderr(
                format_judge_regen_operator_stderr_line(
                    cycle=_cycle_idx + 1,
                    reject_gate=_reject_gate,
                    g3_verdicts=_g3.get("g3_verdict_per_trigger_judge"),
                    operator_floor=_operator_judge_floor,
                    final_publish_baseline="scratch",
                    published_min_score=None,
                ),
            )
            write_json(artifact_dir / "judge_remediation_receipt.json", _j_receipt)
            if _regen_attempt_parsed_snapshot is not None:
                _regen_incremental_anchor_parsed = _regen_attempt_parsed_snapshot
                _regen_prior_cycle_judges = list(_x1d_before_regen)
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
                return "break"
            if _cycle_idx + 1 >= _max_judge_cycles:
                _cycles_receipt["stopped_reason"] = _reject_gate
                return "break"
            return "continue"

        x1d = _x1d_after_rescore
        _cycle_record["draft_parse_ok"] = True
        _cycle_record["accepted"] = True
        _cycle_record["publish_eligible"] = True
        _cycle_record["g3_passed"] = True
        _cycle_record["reject_gate"] = None
        _regen_snap = freeze_candidate_snapshot(
            candidate_id=f"regen_cycle_{_cycle_idx + 1}",
            raw_output=raw_output or "",
            parsed=dict(parsed),
            resume_display_text=resume_display_text,
            claim_ledger=claim_ledger,
            x2_gates=x2,
            x1d_judges=x1d,
            allowed_fact_ids=allowed_fact_ids,
            prompt_hash=prompt_hash,
            model_name=model_name,
            provider_lane=_provider_lane,
            run_refs={
                "provider_request": str(
                    artifact_dir / f"provider_request_regen_{_cycle_idx + 1}.json"
                ),
                "provider_response": str(
                    artifact_dir / f"provider_response_regen_{_cycle_idx + 1}.json"
                ),
            },
            scores_freshness=SCORES_FRESHNESS_SOFT_FAILED_ONLY,
            publish_eligible=True,
        )
        _cycle_record["candidate_digest"] = _regen_snap.candidate_digest
        _candidate_pool.add(_regen_snap)
        _emit_dimension_upstream_triangulation(
            artifact_dir,
            x1d_judges=x1d,
            x2_gates=x2,
            runtime_payload=runtime_payload,
            judge_regen_cycles=_cycles_receipt,
        )
        _write_x1d_judge_artifacts(artifact_dir, x1d)
        write_judge_regen_x2_snapshot(
            artifact_dir,
            "x2_gate_outputs_post_regen.json",
            x2,
            label="post_regen",
        )
        write_x2_gate_outputs(
            artifact_dir / "x2_gate_outputs.json", x2, section_id="executive_summary"
        )
        l2_output["resume_display_text"] = resume_display_text
        l2_output["claim_ledger"] = claim_ledger
        l2_output["text_claim_coverage"] = coverage
        write_json(artifact_dir / "l2_output.json", l2_output)
        from apps_rg.runtime.sections.executive_summary_judge_regen_loop import (
            extend_regen_thread_after_success,
        )

        _regen_messages = extend_regen_thread_after_success(
            _regen_messages,
            raw_output or "",
        )
        _cycle_record["all_judges_pass"] = all_model_backed_judges_pass(x1d)
        _prior_regen_output_hash, _conv = finalize_regen_cycle_observability(
            _cycles_receipt,
            _cycle_record,
            cycle_index=_cycle_idx,
            artifact_dir=artifact_dir,
            judge_remediation_receipt=_j_receipt,
            x2_gates=x2_regen,
            prior_regen_output_hash=_prior_regen_output_hash,
        )
        if _conv:
            return "break"
        if all_model_backed_judges_pass(x1d):
            _cycles_receipt["stopped_reason"] = "all_model_backed_judges_pass"
            return "break"
    else:
        _revert_tag = (
            "post_regen_x2_failed_after_x2_repair"
            if _cycle_record.get("x2_repair")
            else "post_regen_x2_failed"
        )
        _cycle_record["reverted"] = _revert_tag
        _cycle_record["retained_regen_candidate"] = True
        _cycle_record["publish_baseline"] = "regen_candidate_retained"
        _j_receipt["reverted"] = _revert_tag
        _j_receipt["retained_regen_candidate"] = True
        _j_receipt["post_regen_x2_failed_gate_ids"] = [
            g["gate_id"] for g in x2_regen if not g["pass"]
        ]
        write_json(artifact_dir / "judge_remediation_receipt.json", _j_receipt)
        if _j_receipt.get("output_changed") and str(raw_output or "").strip():
            from apps_rg.runtime.sections.executive_summary_judge_regen_loop import (
                extend_regen_thread_after_success,
            )

            _regen_messages = extend_regen_thread_after_success(
                _regen_messages,
                str(raw_output or ""),
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
            x2_gates=x2_regen,
            prior_regen_output_hash=_prior_regen_output_hash,
        )
        if _conv:
            return "break"
        if _cycle_idx + 1 >= _max_judge_cycles:
            _cycles_receipt["stopped_reason"] = _revert_tag
            return "break"
        return "continue"

    ctx["x1d"] = x1d
    ctx["x2"] = x2
    ctx["parsed_for_x2"] = parsed_for_x2
    ctx["parsed"] = parsed
    ctx["claim_ledger"] = claim_ledger
    ctx["resume_display_text"] = resume_display_text
    ctx["raw_output"] = raw_output
    ctx["_prior_regen_output_hash"] = _prior_regen_output_hash
    if "_last_regen_candidate" in locals():
        ctx["_last_regen_candidate"] = _last_regen_candidate
    return None
