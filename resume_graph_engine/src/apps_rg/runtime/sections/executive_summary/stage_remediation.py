"""Stage 3: Initial X2/X1D evaluation and judge remediation coordination."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .word_budget_repair import *
from .stage_remediation_cycles import run_remediation_cycles

def run_remediation_stage(ctx: dict[str, Any]) -> None:
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    proof_pool_metadata = ctx["proof_pool_metadata"]
    targeting_ingress = ctx["targeting_ingress"]
    messages = ctx["messages"]
    req = ctx["req"]
    scratch_max_tokens = ctx["scratch_max_tokens"]
    token_budget_receipt = ctx["token_budget_receipt"]
    usage_doc = ctx["usage_doc"]
    briefing_text_bounded = ctx["briefing_text_bounded"]
    pool = ctx["pool"]
    base_path = ctx["base_path"]
    base_hash = ctx["base_hash"]
    base = ctx["base"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    allowed_fact_ids_ordered = ctx["allowed_fact_ids_ordered"]
    result = ctx["result"]
    provider_result_data = ctx["provider_result_data"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    parse_error = ctx["parse_error"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    _word_budget_repair_accepted = ctx["_word_budget_repair_accepted"]
    _word_budget_repair_audit = ctx["_word_budget_repair_audit"]
    _composition_plan_early = ctx["_composition_plan_early"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    x2 = ctx["x2"]
    _generation_material = ctx["_generation_material"]
    _bundle_mat = ctx["_bundle_mat"]
    _targeting_parity = ctx["_targeting_parity"]

    if x2_failed_initial or runtime_generation_status != "REAL_LLM":
        write_json(
            artifact_dir / "fact_check_result.json",
            {
                "passed": not x2_failed_initial,
                "failed_gates": [g["gate_id"] for g in x2_failed_initial],
            },
        )
    set_word_budget_repair_authoritative_after_x2(
        artifact_dir,
        accepted=_word_budget_repair_accepted,
        x2_gates=x2,
    )
    if x2_failed_initial and not (artifact_dir / "x1d_llm_judge_outputs.json").is_file():
        _write_x1d_judge_artifacts(artifact_dir, x1d)
    if x2_failed_initial:
        _emit_dimension_upstream_triangulation(
            artifact_dir,
            x1d_judges=x1d,
            x2_gates=x2,
            runtime_payload=runtime_payload,
        )
    _composition_plan_refresh: dict[str, Any] = {}
    _comp_plan_path = artifact_dir / "executive_summary_composition_plan.json"
    if _comp_plan_path.is_file():
        try:
            _raw_plan = json.loads(_comp_plan_path.read_text(encoding="utf-8"))
            if isinstance(_raw_plan, dict):
                _composition_plan_refresh = _raw_plan
        except (OSError, json.JSONDecodeError):  # guardian: allow-default-fallback -- P2 burndown: fail-soft optional boundary
            _composition_plan_refresh = {}

    if runtime_generation_status == "REAL_LLM" and not x2_failed_initial:
        from apps_rg.runtime.sections.executive_summary_judge_remediation import (
            refresh_x1d_judges_after_full_x2,
        )
        from apps_rg.runtime.validators.executive_summary_x2 import (
            append_executive_summary_x1d_x2_gate_dicts,
        )

        _gtc_lane = runtime_payload.get("graph_targeting_capsule")
        _gtc_lane_dict = dict(_gtc_lane) if isinstance(_gtc_lane, dict) else None
        from apps_rg.runtime.c0.c03_graph_ref_policy import extract_c03_bindings_from_runtime_payload

        _graph_bindings_lane = extract_c03_bindings_from_runtime_payload(runtime_payload)
        x1d, _x1d_refresh_receipt = refresh_x1d_judges_after_full_x2(
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
            prior_judges=[],
            graph_targeting_capsule=_gtc_lane_dict,
            material_targeting_bundle=_bundle_mat.to_dict()
            if hasattr(_bundle_mat, "to_dict")
            else runtime_payload.get("material_targeting_bundle"),
            graph_bindings=_graph_bindings_lane,
            repo_root=REPO_ROOT,
        )
        from apps_rg.runtime.judges.x1d_panel_harness import extract_x1d_diagnostic
        from apps_rg.runtime.sections.ExecutiveVoiceRepairAgent import (
            repair_section_with_executive_voice_agent,
        )

        exec_diag = extract_x1d_diagnostic(x1d, "executive_summary")
        if exec_diag.get("repair_needed"):
            repaired_cand, repair_rec = repair_section_with_executive_voice_agent(
                section_id="executive_summary",
                candidate_data={"resume_display_text": resume_display_text, "claim_ledger": claim_ledger},
                diagnostic=exec_diag,
                allowed_facts=selected_facts_for_x2 if isinstance(selected_facts_for_x2, list) else None,
                targeting_context={"target_title": _args_target_title(args), "target_company": str(args.target_company)},
                mock_mode=(judge_mode == "mocked"),
                artifact_dir=artifact_dir,
            )
            if repair_rec.repair_succeeded and repaired_cand.get("resume_display_text") != resume_display_text:
                resume_display_text = str(repaired_cand["resume_display_text"])
                if isinstance(parsed, dict):
                    parsed["resume_display_text"] = resume_display_text
                if isinstance(parsed_for_x2, dict):
                    parsed_for_x2["resume_display_text"] = resume_display_text
                x1d, _x1d_refresh_receipt = refresh_x1d_judges_after_full_x2(
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
                    prior_judges=[],
                    graph_targeting_capsule=_gtc_lane_dict,
                    material_targeting_bundle=_bundle_mat.to_dict()
                    if hasattr(_bundle_mat, "to_dict")
                    else runtime_payload.get("material_targeting_bundle"),
                    graph_bindings=_graph_bindings_lane,
                    repo_root=REPO_ROOT,
                )
        from apps_rg.runtime.sections.executive_summary_repair_policy import (
            judge_regeneration_enabled,
        )

        if isinstance(_x1d_refresh_receipt, dict):
            _x1d_refresh_receipt = {
                **_x1d_refresh_receipt,
                "phase": "post_x2_initial",
                "rescore_only": not judge_regeneration_enabled(),
            }
        write_json(artifact_dir / "post_x2_x1d_refresh_receipt.json", _x1d_refresh_receipt)
        _write_x1d_judge_artifacts(artifact_dir, x1d)
        _emit_dimension_upstream_triangulation(
            artifact_dir,
            x1d_judges=x1d,
            x2_gates=x2,
            runtime_payload=runtime_payload,
        )
        x2.extend(
            append_executive_summary_x1d_x2_gate_dicts(
                x1d_judges=x1d,
                artifacts_dir=artifact_dir,
                required_providers=judge_keys,
            )
        )
        write_x2_gate_outputs(artifact_dir / "x2_gate_outputs.json", x2, section_id="executive_summary")
        judge_packet = resolve_judge_packet_for_parity(artifact_dir, fallback={})
        judge_packet_ref = str(
            artifact_dir / "executive_summary_judge_packet_post_x2.json"
        )
        _targeting_parity, usage_doc = publish_targeting_parity_and_usage_ledger(
            artifact_dir=artifact_dir,
            runtime_payload=runtime_payload,
            generation_material=_generation_material,
            judge_packet=judge_packet,
            usage_doc=usage_doc,
            write_json_fn=write_json,
        )


    ctx["x1d"] = x1d
    ctx["x2"] = x2
    ctx["x2_failed_initial"] = x2_failed_initial
    if "judge_packet" in locals():
        ctx["judge_packet"] = judge_packet
    if "judge_packet_ref" in locals():
        ctx["judge_packet_ref"] = judge_packet_ref

    if runtime_generation_status == "REAL_LLM" and not x2_failed_initial and parsed_for_x2:
        from apps_rg.runtime.section_repair_policy import judge_remediation_regen_allowed
        from apps_rg.runtime.sections.executive_summary_judge_remediation import (
            all_model_backed_judges_pass,
            build_judge_remediation_user_message,
            evaluate_judge_remediation_trigger,
            repair_judge_regen_after_x2_fail,
            rerun_soft_failed_judges,
            rerun_x2_after_judge_remediation,
            retry_provider_for_judge_remediation,
        )
        from apps_rg.runtime.sections.executive_summary_repair_policy import judge_regen_max_attempts
        from apps_rg.runtime.validators.executive_summary_x2 import collect_unused_allowed_fact_ids

        _regen_ok, _regen_parity_reason = parity_allows_judge_regen(
            runtime_payload,
            token_budget_receipt=token_budget_receipt,
        )
        _gtc_lane = runtime_payload.get("graph_targeting_capsule")
        _gtc_lane_dict = dict(_gtc_lane) if isinstance(_gtc_lane, dict) else None
        _pool_publish_applied = False
        from apps_rg.runtime.sections.executive_summary_publish_disposition import (
            best_effort_publish_allowed_from_env,
            resolve_publish_disposition,
        )

        ctx["_judge_prompt_x1d"] = _judge_prompt_x1d
        ctx["_gtc_lane_dict"] = _gtc_lane_dict
        ctx["_pool_publish_applied"] = _pool_publish_applied

        if judge_remediation_regen_allowed() and _regen_ok:
            run_remediation_cycles(ctx)
        elif judge_remediation_regen_allowed() and not _regen_ok:
            write_json(
                artifact_dir / "judge_remediation_cycles.json",
                {
                    "schema": "executive_summary_judge_remediation_cycles_v2",
                    "schema_version": 2,
                    "skipped": "targeting_parity_required",
                    "reason": _regen_parity_reason,
                    "generation_material_digest": _generation_material.generation_material_digest,
                },
            )
        else:
            _trigger_ok0, _trigger0 = evaluate_judge_remediation_trigger(
                x1d,
                runtime_generation_status=runtime_generation_status,
                x2_passed=True,
            )
            write_json(artifact_dir / "judge_remediation_trigger.json", _trigger0)

