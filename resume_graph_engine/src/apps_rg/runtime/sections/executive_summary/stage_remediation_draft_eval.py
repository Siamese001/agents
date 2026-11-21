"""Stage 3c: Post-X2 judge rescoring, G3 monotonicity check, and pool admission."""
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


def evaluate_remediation_draft_post_x2(ctx: dict[str, Any]) -> str | None:
    """Admit X2-passing regen drafts to pool or handle X2/G3 revert cleanly."""
    from apps_rg.runtime.section_repair_ledger import (
        KIND_REGEN_LLM,
        load_ledger,
        record_repair,
        record_x2_run,
        set_authoritative_attempt,
    )
    from apps_rg.runtime.sections.executive_summary_candidate_pool import (
        SCORES_FRESHNESS_FULL_PANEL,
        SCORES_FRESHNESS_SOFT_FAILED_ONLY,
        freeze_candidate_snapshot,
    )
    from apps_rg.runtime.sections.executive_summary_judge_regen_loop import (
        advance_regen_thread_for_next_cycle,
        write_judge_regen_x2_snapshot,
    )
    from apps_rg.runtime.sections.executive_summary_judge_remediation import (
        all_model_backed_judges_pass,
    )
    from apps_rg.runtime.sections.executive_summary_regen_delta_policy import (
        emit_judge_regen_operator_stderr,
        format_judge_regen_operator_stderr_line,
    )
    from apps_rg.runtime.sections.executive_summary_regen_observability import (
        finalize_regen_cycle_observability,
    )

    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    raw_output = ctx["raw_output"]
    parsed = ctx["parsed"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    coverage = ctx["coverage"]
    l2_output = ctx["l2_output"]
    x1d = ctx["x1d"]
    x2 = ctx["x2"]
    x2_regen = ctx["x2_regen"]
    _x2_failed = ctx["_x2_failed"]
    model_name = ctx["model_name"]
    prompt_hash = ctx["prompt_hash"]
    compiled_prompt = ctx["compiled_prompt"]
    selected_facts_for_x2 = ctx["selected_facts_for_x2"]
    _judge_jd = ctx["_judge_jd"]
    _judge_briefing = ctx["_judge_briefing"]
    judge_keys = ctx["judge_keys"]
    judge_mode = ctx["judge_mode"]
    judge_packet = ctx["judge_packet"]
    _cycle_idx = ctx["_cycle_idx"]
    _max_judge_cycles = ctx["_max_judge_cycles"]
    _regen_messages = ctx["_regen_messages"]
    _prior_regen_output_hash = ctx["_prior_regen_output_hash"]
    _cycles_receipt = ctx["_cycles_receipt"]
    _candidate_pool = ctx["_candidate_pool"]
    _provider_lane = ctx["_provider_lane"]
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
    _operator_judge_floor = ctx["_operator_judge_floor"]
    _judge_prompt_x1d = ctx["_judge_prompt_x1d"]
    _regen_incremental_anchor_parsed = ctx["_regen_incremental_anchor_parsed"]
    _regen_prior_cycle_judges = ctx["_regen_prior_cycle_judges"]
    _last_regen_candidate = ctx["_last_regen_candidate"]
    _regen_attempt_parsed_snapshot = ctx["_regen_attempt_parsed_snapshot"]

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
        })

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
            target_title=_lane_attr("_args_target_title", _args_target_title)(args),
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
        _lane_attr("write_json", write_json)(
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
        _lane_attr("write_json", write_json)(
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
            _lane_attr("write_json", write_json)(artifact_dir / "judge_remediation_receipt.json", _j_receipt)
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
                _sync_ctx()
                return "break"
            if _cycle_idx + 1 >= _max_judge_cycles:
                _cycles_receipt["stopped_reason"] = _reject_gate
                _sync_ctx()
                return "break"
            _sync_ctx()
            return "continue"

        x1d = _x1d_after_rescore
        _cycle_record["draft_parse_ok"] = True
        _cycle_record["accepted"] = True
        _cycle_record["publish_eligible"] = True
        _cycle_record["g3_passed"] = True
        _cycle_record["reject_gate"] = None
        _x1d_present_keys = {
            str(j.get("provider_key") or "")
            for j in x1d
            if isinstance(j, dict)
            and j.get("provider_key")
            and not j.get("provider_blocked")
        }
        _regen_scores_freshness = (
            SCORES_FRESHNESS_FULL_PANEL
            if _post_regen_x1d_receipt.get("rescore_mode") == "full_panel"
            and bool(judge_keys)
            and set(judge_keys) <= _x1d_present_keys
            else SCORES_FRESHNESS_SOFT_FAILED_ONLY
        )
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
            scores_freshness=_regen_scores_freshness,
            publish_eligible=True,
        )
        _cycle_record["candidate_digest"] = _regen_snap.candidate_digest
        _candidate_pool.add(_regen_snap)
        _lane_attr("_emit_dimension_upstream_triangulation", _emit_dimension_upstream_triangulation)(
            artifact_dir,
            x1d_judges=x1d,
            x2_gates=x2,
            runtime_payload=runtime_payload,
            judge_regen_cycles=_cycles_receipt,
        )
        _lane_attr("_write_x1d_judge_artifacts", _write_x1d_judge_artifacts)(artifact_dir, x1d)
        write_judge_regen_x2_snapshot(
            artifact_dir,
            "x2_gate_outputs_post_regen.json",
            x2,
            label="post_regen",
        )
        _lane_attr("write_x2_gate_outputs", write_x2_gate_outputs)(
            artifact_dir / "x2_gate_outputs.json", x2, section_id="executive_summary"
        )
        l2_output["resume_display_text"] = resume_display_text
        l2_output["claim_ledger"] = claim_ledger
        l2_output["text_claim_coverage"] = coverage
        _lane_attr("write_json", write_json)(artifact_dir / "l2_output.json", l2_output)
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
            _sync_ctx()
            return "break"
        if all_model_backed_judges_pass(x1d):
            _cycles_receipt["stopped_reason"] = "all_model_backed_judges_pass"
            _sync_ctx()
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
        _lane_attr("write_json", write_json)(artifact_dir / "judge_remediation_receipt.json", _j_receipt)
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
            _sync_ctx()
            return "break"
        if _cycle_idx + 1 >= _max_judge_cycles:
            _cycles_receipt["stopped_reason"] = _revert_tag
            _sync_ctx()
            return "break"
        _sync_ctx()
        return "continue"

    _sync_ctx()
    return None
