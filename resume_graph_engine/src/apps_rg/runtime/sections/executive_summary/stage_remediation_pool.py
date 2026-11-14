"""Stage 3d: Candidate pool final resolution and judge remediation receipt finalization."""
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


def finalize_remediation_candidate_pool(ctx: dict[str, Any]) -> None:
    """Select highest-scoring pool candidate and persist synced canonical/L2 artifacts."""
    from apps_rg.runtime.sections.executive_summary_candidate_pool import (
        SCORES_FRESHNESS_CARRIED_FORWARD,
        finalize_pool_publish,
    )
    from apps_rg.runtime.sections.executive_summary_judge_remediation import (
        all_model_backed_judges_pass,
    )
    from apps_rg.runtime.sections.executive_summary_publish_disposition import (
        best_effort_publish_allowed_from_env,
        resolve_publish_disposition,
    )
    from apps_rg.runtime.sections.executive_summary_regen_delta_policy import (
        compute_regen_outcome,
        emit_judge_regen_operator_stderr,
        format_judge_regen_operator_stderr_line,
    )

    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    input_payload_hash = ctx["input_payload_hash"]
    compiled_prompt = ctx["compiled_prompt"]
    selected_facts_for_x2 = ctx["selected_facts_for_x2"]
    _judge_jd = ctx["_judge_jd"]
    _judge_briefing = ctx["_judge_briefing"]
    judge_keys = ctx["judge_keys"]
    judge_mode = ctx["judge_mode"]
    _gtc_lane_dict = ctx["_gtc_lane_dict"]
    _bundle_mat = ctx["_bundle_mat"]
    _graph_bindings_lane = ctx["_graph_bindings_lane"]
    _candidate_pool = ctx["_candidate_pool"]
    _cycles_receipt = ctx["_cycles_receipt"]
    _scratch_anchor_resume = ctx["_scratch_anchor_resume"]
    _operator_judge_floor = ctx["_operator_judge_floor"]
    l2_output = ctx["l2_output"]
    parse_status = ctx["parse_status"]
    invalid_reason = ctx["invalid_reason"]
    raw_output = ctx["raw_output"]
    parsed = ctx["parsed"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    coverage = ctx["coverage"]
    x2 = ctx["x2"]
    x1d = ctx["x1d"]
    _pool_publish_applied = bool(ctx.get("_pool_publish_applied", False))

    if not _cycles_receipt.get("stopped_reason") and _cycles_receipt["cycles"]:
        _cycles_receipt["stopped_reason"] = "max_cycles_reached"
    _pub_freshness = SCORES_FRESHNESS_CARRIED_FORWARD
    if _candidate_pool.publish_eligible():
        from apps_rg.runtime.sections.executive_summary_candidate_pool import CandidateSnapshot, SCORES_FRESHNESS_FULL_PANEL
        from apps_rg.runtime.sections.executive_summary_judge_remediation import refresh_x1d_judges_after_full_x2
        from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import rescore_snapshot_or_reuse_full_panel, write_synced_canonical_claim_ledger_v2

        def _rescore_snapshot_full_panel(snap: CandidateSnapshot) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            return rescore_snapshot_or_reuse_full_panel(
                snap, full_panel_token=SCORES_FRESHNESS_FULL_PANEL, build_coverage_fn=build_sentence_claim_coverage,
                enrich_x2_fn=enrich_parsed_for_x2, refresh_x1d_fn=refresh_x1d_judges_after_full_x2,
                allowed_fact_ids=allowed_fact_ids, input_payload_hash=input_payload_hash, runtime_payload=runtime_payload,
                selected_facts_for_x2=selected_facts_for_x2, target_title=_lane_attr("_args_target_title", _args_target_title)(args), target_company=str(args.target_company),
                jd_text=_judge_jd, briefing_text=_judge_briefing, judge_keys=judge_keys, judge_mode=judge_mode,
                artifact_dir=artifact_dir, compiled_prompt=compiled_prompt, prior_judges=x1d,
                graph_targeting_capsule=_gtc_lane_dict,
                material_targeting_bundle=_bundle_mat.to_dict() if hasattr(_bundle_mat, "to_dict") else runtime_payload.get("material_targeting_bundle"),
                graph_bindings=_graph_bindings_lane, repo_root=REPO_ROOT,
            )

        _pub = finalize_pool_publish(
            _candidate_pool, artifact_dir=artifact_dir, write_json_fn=_lane_attr("write_json", write_json),
            rescore_full_panel=_rescore_snapshot_full_panel, enrich_parsed_for_x2_fn=enrich_parsed_for_x2,
            build_coverage_fn=build_sentence_claim_coverage, allowed_fact_ids=allowed_fact_ids,
            input_payload_hash=input_payload_hash, runtime_payload=runtime_payload,
            write_x2_fn=lambda path, gates: _lane_attr("write_x2_gate_outputs", write_x2_gate_outputs)(path, gates, section_id="executive_summary"),
            write_x1d_fn=_write_x1d_judge_artifacts, l2_output=l2_output, scratch_anchor_resume=_scratch_anchor_resume,
        )
        if _pub.selected is not None:
            _pool_publish_applied = True
            raw_output, parsed, resume_display_text = _pub.raw_output, _pub.parsed, _pub.resume_display_text
            claim_ledger, x2, x1d = _pub.claim_ledger, _pub.x2_gates, _pub.x1d_judges
            if _pub.coverage is not None:
                coverage = _pub.coverage
            write_synced_canonical_claim_ledger_v2(
                artifact_dir=artifact_dir, claim_ledger=claim_ledger, parse_status=parse_status, invalid_reason=invalid_reason,
                normalize_ledger_fn=normalize_exec_summary_claim_ledger, build_payload_fn=build_canonical_claim_ledger_v2_payload, write_json_fn=_lane_attr("write_json", write_json),
            )
            parsed_for_x2 = enrich_parsed_for_x2(
                parsed, coverage=coverage, input_payload_hash=input_payload_hash, allowed_fact_ids=allowed_fact_ids, runtime_payload=runtime_payload,
            )
            _cycles_receipt["final_publish_baseline"] = _pub.selected.candidate_id
            _cycles_receipt["publish_reason"] = _pub.receipt.get("publish_reason")
            _cycles_receipt["publish_selected_snapshot_id"] = _pub.selected.candidate_id
            _cycles_receipt["published_candidate_digest"] = _pub.selected.candidate_digest
            _cycles_receipt["scratch_anchor_resume_preserved_in_receipt"] = (
                _scratch_anchor_resume
            )
            _pub_freshness = SCORES_FRESHNESS_FULL_PANEL
    if not _cycles_receipt.get("final_publish_baseline"):
        _cycles_receipt["final_publish_baseline"] = "scratch"
    from apps_rg.runtime.sections.executive_summary_regen_delta_policy import (
        cert_block_for_published_scores_freshness,
        min_model_backed_holistic_from_judges,
    )

    _cycles_receipt["regen_outcome"] = compute_regen_outcome(
        cycles=list(_cycles_receipt.get("cycles") or []),
        final_publish_baseline=str(_cycles_receipt.get("final_publish_baseline") or "scratch"),
        all_model_backed_judges_pass=all_model_backed_judges_pass(x1d),
    )
    _scratch_digest = ""
    if _candidate_pool.entries():
        _scratch_digest = _candidate_pool.entries()[0].candidate_digest
    _published_digest = str(_cycles_receipt.get("published_candidate_digest") or "")
    _cert_blocked, _cert_reason = cert_block_for_published_scores_freshness(
        _pub_freshness,
        published_candidate_id=str(
            _cycles_receipt.get("final_publish_baseline") or "scratch"
        ),
        scratch_digest=_scratch_digest,
        published_digest=_published_digest,
    )
    _cycles_receipt["cert_publish_guard"] = {
        "cert_blocked": _cert_blocked,
        "cert_block_reason": _cert_reason,
        "scores_freshness": _pub_freshness,
    }
    _last_cycle_row = (
        (_cycles_receipt.get("cycles") or [])[-1]
        if _cycles_receipt.get("cycles")
        else {}
    )
    if _last_cycle_row:
        emit_judge_regen_operator_stderr(
            format_judge_regen_operator_stderr_line(
                cycle=int(_last_cycle_row.get("cycle") or 0) or 1,
                reject_gate=_last_cycle_row.get("reject_gate"),
                g3_verdicts=_last_cycle_row.get("g3_verdict_per_trigger_judge"),
                operator_floor=_operator_judge_floor,
                final_publish_baseline=str(
                    _cycles_receipt.get("final_publish_baseline") or "scratch"
                ),
                published_min_score=min_model_backed_holistic_from_judges(x1d),
            ),
        )
    _cycles_receipt["publish_disposition"] = resolve_publish_disposition(
        x1d,
        best_effort_publish_allowed=bool(getattr(args, "best_effort_publish_allowed", False))
        or best_effort_publish_allowed_from_env(),
        published_from_pool=_pool_publish_applied,
    )
    from apps_rg.runtime.sections.executive_summary_regen_observability import (
        finalize_judge_regen_cycles_receipt,
    )

    _cycles_receipt = finalize_judge_regen_cycles_receipt(
        _cycles_receipt,
        artifact_dir=artifact_dir,
        scratch_candidate_digest=_scratch_digest,
        published_candidate_digest=_published_digest,
    )
    _lane_attr("write_json", write_json)(artifact_dir / "judge_remediation_cycles.json", _cycles_receipt)
    ctx.update({
        "_pool_publish_applied": _pool_publish_applied,
        "raw_output": raw_output,
        "parsed": parsed,
        "parsed_for_x2": parsed_for_x2,
        "resume_display_text": resume_display_text,
        "claim_ledger": claim_ledger,
        "coverage": coverage,
        "x2": x2,
        "x1d": x1d,
        "_cycles_receipt": _cycles_receipt,
    })
