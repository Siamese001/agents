"""Coordinator for remediation retry cycles across attempt, evaluation, and pool selection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .stage_remediation_draft import process_remediation_draft
from .stage_remediation_pool import finalize_remediation_candidate_pool

def run_remediation_cycles(ctx: dict[str, Any]) -> None:
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    messages = ctx["messages"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    x2 = ctx["x2"]
    _generation_material = ctx["_generation_material"]
    _bundle_mat = ctx["_bundle_mat"]
    _targeting_parity = ctx["_targeting_parity"]
    x1d = ctx["x1d"]
    _judge_prompt_x1d = ctx["_judge_prompt_x1d"]
    _gtc_lane_dict = ctx["_gtc_lane_dict"]
    _pool_publish_applied = ctx["_pool_publish_applied"]
    token_budget_receipt = ctx["token_budget_receipt"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    selected_fact_plan = ctx["selected_fact_plan"]
    pool = ctx["pool"]

    _max_judge_cycles = judge_regen_max_attempts()
    _regen_messages = list(messages)
    from apps_rg.runtime.sections.executive_summary_regen_delta_policy import (
        build_judge_remediation_cycles_receipt,
        compute_regen_outcome,
        emit_judge_regen_operator_stderr,
        evaluate_g5_delta_scope_v2,
        format_judge_regen_operator_stderr_line,
        resolve_delta_class,
    )
    from apps_rg.runtime.sections.executive_summary_repair_policy import (
        judge_pass_floor_0_to_5,
    )

    _operator_judge_floor = judge_pass_floor_0_to_5()
    _judge_prompt_x1d = list(x1d)
    _cycles_receipt = build_judge_remediation_cycles_receipt(
        max_cycles=_max_judge_cycles,
        generation_material_digest=_generation_material.generation_material_digest,
        targeting_parity_at_regen_start=_targeting_parity,
        judge_packet_targeting_audit=audit_judge_packet_targeting_digests(
            artifact_dir,
            generation_material=_generation_material,
        ),
        operator_judge_pass_floor=_operator_judge_floor,
    )
    _cycles_receipt["allowed_fact_ids"] = sorted(allowed_fact_ids)
    _last_regen_candidate: dict[str, Any] | None = None
    _scratch_anchor_resume = resume_display_text
    _regen_incremental_anchor_parsed: dict[str, Any] | None = None
    _regen_prior_cycle_judges: list[dict[str, Any]] | None = None
    _prior_regen_output_hash: str | None = None
    from apps_rg.runtime.sections.executive_summary_regen_observability import (
        finalize_regen_cycle_observability,
    )
    from apps_rg.runtime.sections.executive_summary_candidate_pool import (
        SCORES_FRESHNESS_CARRIED_FORWARD,
        SCORES_FRESHNESS_SOFT_FAILED_ONLY,
        CandidatePool,
        finalize_pool_publish,
        freeze_candidate_snapshot,
    )

    _candidate_pool = CandidatePool()
    _provider_lane = str(
        provider_payload.get("provider") or provider_payload.get("lane") or ""
    )
    _candidate_pool.add(
        freeze_candidate_snapshot(
            candidate_id="scratch",
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
                "provider_request": str(artifact_dir / "provider_request.json"),
                "provider_response": str(artifact_dir / "provider_response.json"),
            },
            scores_freshness=SCORES_FRESHNESS_CARRIED_FORWARD,
            publish_eligible=True,
        ),
    )



    for _cycle_idx in range(_max_judge_cycles):
        if all_model_backed_judges_pass(x1d):
            _cycles_receipt["stopped_reason"] = "all_model_backed_judges_pass"
            break

        trigger_ok, trigger_receipt = evaluate_judge_remediation_trigger(
            _judge_prompt_x1d,
            runtime_generation_status=runtime_generation_status,
            x2_passed=True,
        )
        trigger_receipt["cycle"] = _cycle_idx + 1
        write_json(
            artifact_dir / f"judge_remediation_trigger_cycle_{_cycle_idx + 1}.json",
            trigger_receipt,
        )
        if _cycle_idx == 0:
            write_json(artifact_dir / "judge_remediation_trigger.json", trigger_receipt)

        if not trigger_ok:
            _cycles_receipt["stopped_reason"] = str(
                trigger_receipt.get("reason") or "trigger_not_ok"
            )
            break

        _pre_raw = raw_output
        _pre_parsed = dict(parsed_for_x2)
        _pre_resume = resume_display_text
        _pre_ledger = list(claim_ledger)
        _pre_x2 = list(x2)
        _pre_wc = len(re.findall(r"\S+", _pre_resume))
        _pre_ledger_rows = len(_pre_ledger)
        from apps_rg.runtime.sections.executive_summary_judge_regen_loop import (
            advance_regen_thread_for_next_cycle,
            post_regen_x2_repair_eligible,
            preserve_judge_regen_claim_ledger_from_baseline,
            prepare_parsed_after_judge_regen,
            resume_display_text_from_regen_messages,
            snapshot_regen_candidate,
            sync_claim_ledger_metrics_from_facts,
            write_judge_regen_x2_snapshot,
        )

        write_judge_regen_x2_snapshot(
            artifact_dir,
            "x2_gate_outputs_pre_regen.json",
            _pre_x2,
            label="pre_regen",
        )
        from apps_rg.runtime.sections.executive_summary_judge_remediation import (
            snapshot_model_backed_judge_scores,
        )

        _x1d_before_regen = list(_judge_prompt_x1d)
        _scores_before_regen = snapshot_model_backed_judge_scores(_x1d_before_regen)
        _cycle_delta_class = resolve_delta_class(
            _x1d_before_regen,
            operator_judge_pass_floor=_operator_judge_floor,
        )
        unused_ids = collect_unused_allowed_fact_ids(claim_ledger, allowed_fact_ids)
        from apps_rg.runtime.sections.executive_summary_pa import (
            is_strategy_executive_target_title,
        )

        _strategy_exec_regen = is_strategy_executive_target_title(
            str(
                runtime_payload.get("target_role")
                or runtime_payload.get("target_title")
                or getattr(args, "target_role", "")
                or getattr(args, "target_title", "")
                or ""
            ).strip()
        )
        raw_output, parsed_regen, _j_receipt = retry_provider_for_judge_remediation(
            _regen_messages,
            provider_payload,
            raw_output,
            parsed_for_x2,
            x1d_judges=_judge_prompt_x1d,
            trigger_receipt=trigger_receipt,
            selected_fact_plan=selected_fact_plan,
            allowed_fact_ids=allowed_fact_ids,
            unused_fact_ids=unused_ids,
            composition_plan=_composition_plan_refresh,
            artifact_dir=artifact_dir,
            run_id=str(runtime_payload.get("run_id") or "") or None,
            max_attempts=1,
            prior_word_count=_pre_wc,
            prior_ledger_rows=_pre_ledger_rows,
            cycle_index=_cycle_idx,
            incremental_anchor_parsed=_regen_incremental_anchor_parsed,
            baseline_resume_display_text=_scratch_anchor_resume,
            prior_cycle_judges=_regen_prior_cycle_judges,
        )
        _feedback_pack = dict(_j_receipt.get("feedback_pack") or {})
        _draft_parse_ok = bool(
            _j_receipt.get("draft_parse_ok", _j_receipt.get("accepted")),
        )
        _cycle_record: dict[str, Any] = {
            "cycle": _cycle_idx + 1,
            "trigger_mode": trigger_receipt.get("trigger_mode"),
            "draft_parse_ok": _draft_parse_ok,
            "accepted": False,
            "output_changed": bool(_j_receipt.get("output_changed")),
            "scores_before": _scores_before_regen,
            "delta_class": _cycle_delta_class,
        }
        for _fb_key in (
            "judge_feedback_lines_total",
            "judge_feedback_lines_included",
            "judge_feedback_lines_dropped",
            "dropped_reason",
        ):
            if _fb_key in _feedback_pack:
                _cycle_record[_fb_key] = _feedback_pack[_fb_key]
        _regen_attempt_parsed_snapshot: dict[str, Any] | None = None

        if _draft_parse_ok or _j_receipt.get("prefilter_applied"):
            ctx["_cycle_idx"] = _cycle_idx
            ctx["_max_judge_cycles"] = _max_judge_cycles
            ctx["_regen_messages"] = _regen_messages
            ctx["_prior_regen_output_hash"] = _prior_regen_output_hash
            ctx["_cycles_receipt"] = _cycles_receipt
            ctx["_candidate_pool"] = _candidate_pool
            ctx["_scratch_digest"] = _scratch_digest
            ctx["_published_digest"] = _published_digest
            ctx["_wg"] = _wg
            ctx["_cycle_record"] = _cycle_record
            ctx["_draft_parse_ok"] = _draft_parse_ok
            ctx["_j_receipt"] = _j_receipt
            ctx["_pre_parsed"] = _pre_parsed
            ctx["_pre_raw"] = _pre_raw
            ctx["_pre_resume"] = _pre_resume
            ctx["_pre_ledger"] = _pre_ledger
            ctx["_pre_x2"] = _pre_x2
            ctx["_pre_wc"] = _pre_wc
            ctx["_pre_ledger_rows"] = _pre_ledger_rows
            ctx["_x1d_before_regen"] = _x1d_before_regen
            ctx["_scores_before_regen"] = _scores_before_regen
            ctx["_cycle_delta_class"] = _cycle_delta_class
            ctx["selected_facts_for_x2"] = selected_facts_for_x2
            ctx["provider_payload"] = provider_payload
            ctx["model_name"] = model_name
            ctx["prompt_hash"] = prompt_hash
            ctx["compiled_prompt"] = compiled_prompt
            ctx["temperature"] = temperature
            ctx["pp_x2"] = pp_x2
            ctx["proof_pool_x2_active"] = proof_pool_x2_active
            ctx["input_payload_hash"] = input_payload_hash
            ctx["_judge_jd"] = _judge_jd
            ctx["_reject_gate"] = _reject_gate
            ctx["raw_output"] = raw_output
            ctx["parsed"] = parsed
            ctx["parsed_for_x2"] = parsed_for_x2
            ctx["resume_display_text"] = resume_display_text
            ctx["claim_ledger"] = claim_ledger
            ctx["x1d"] = x1d
            ctx["x2"] = x2

            action = process_remediation_draft(ctx)
            x1d = ctx["x1d"]
            x2 = ctx["x2"]
            parsed_for_x2 = ctx["parsed_for_x2"]
            parsed = ctx["parsed"]
            claim_ledger = ctx["claim_ledger"]
            resume_display_text = ctx["resume_display_text"]
            raw_output = ctx["raw_output"]
            _prior_regen_output_hash = ctx["_prior_regen_output_hash"]

            if action == "break":
                break
            elif action == "continue":
                continue
        else:
            _cycle_record["skipped"] = "regen_not_accepted"
            _prior_regen_output_hash, _conv = finalize_regen_cycle_observability(
                _cycles_receipt,
                _cycle_record,
                cycle_index=_cycle_idx,
                artifact_dir=artifact_dir,
                judge_remediation_receipt=_j_receipt,
                prior_regen_output_hash=_prior_regen_output_hash,
            )
            if _conv:
                break
            if _cycle_idx + 1 >= _max_judge_cycles:
                _cycles_receipt["stopped_reason"] = "regen_not_accepted"
                break
            continue


    ctx["_cycles_receipt"] = _cycles_receipt
    ctx["_candidate_pool"] = _candidate_pool
    ctx["_scratch_digest"] = _scratch_digest
    ctx["_published_digest"] = _published_digest
    ctx["_generation_material"] = _generation_material
    ctx["_targeting_parity"] = _targeting_parity
    ctx["raw_output"] = raw_output
    ctx["parsed_for_x2"] = parsed_for_x2
    ctx["parsed"] = parsed
    ctx["resume_display_text"] = resume_display_text
    ctx["claim_ledger"] = claim_ledger
    ctx["x2"] = x2
    ctx["x1d"] = x1d
    ctx["_wg"] = _wg

    finalize_remediation_candidate_pool(ctx)
