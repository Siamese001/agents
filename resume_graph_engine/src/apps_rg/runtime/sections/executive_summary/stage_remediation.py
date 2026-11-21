"""Stage 3: Initial X2/X1D evaluation and judge remediation coordination."""
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

from .stage_remediation_cycles import run_remediation_cycles


def _display_text_sha256(text: str | None) -> str:
    return hashlib.sha256(str(text or "").strip().encode("utf-8")).hexdigest()


def should_skip_unchanged_summary_judge_refresh(
    judges: Any,
    *,
    display_text: str | None,
    prior_display_sha256: str | None,
) -> bool:
    """Return True when display_text normalized SHA matches already model-judged text."""
    if not prior_display_sha256 or _display_text_sha256(display_text) != prior_display_sha256:
        return False
    rows = list(judges) if isinstance(judges, (list, tuple)) else []
    if not rows:
        return False
    return all(
        str(
            getattr(j, "evaluator_mode", None)
            or (j.get("evaluator_mode") if isinstance(j, dict) else "")
        ).upper()
        == "MODEL_BACKED"
        for j in rows
    )


def run_remediation_stage(
    ctx: dict[str, Any],
    *,
    emit_initial_gate_artifacts: bool = True,
) -> None:
    """Run X1D refresh, voice agent pre-repair, and bounded judge remediation cycles."""
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    token_budget_receipt = ctx["token_budget_receipt"]
    usage_doc = ctx["usage_doc"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    _word_budget_repair_accepted = ctx["_word_budget_repair_accepted"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    x2 = ctx["x2"]
    x1d = ctx["x1d"]
    _generation_material = ctx["_generation_material"]
    _bundle_mat = ctx["_bundle_mat"]
    _targeting_parity = ctx["_targeting_parity"]
    selected_facts_for_x2 = ctx["selected_facts_for_x2"]
    _judge_jd = ctx["_judge_jd"]
    _judge_briefing = ctx["_judge_briefing"]
    judge_keys = ctx["judge_keys"]
    judge_mode = ctx["judge_mode"]
    compiled_prompt = ctx["compiled_prompt"]
    x2_failed_initial = ctx.get("x2_failed_initial")
    if x2_failed_initial is None:
        x2_failed_initial = [g for g in x2 if not g["pass"]]
        ctx["x2_failed_initial"] = x2_failed_initial
    if emit_initial_gate_artifacts:
        if x2_failed_initial or runtime_generation_status != "REAL_LLM":
            _lane_attr("write_json", write_json)(
                artifact_dir / "fact_check_result.json",
                {
                    "passed": not x2_failed_initial,
                    "failed_gates": [g["gate_id"] for g in x2_failed_initial],
                },
            )
        _lane_attr(
            "set_word_budget_repair_authoritative_after_x2",
            set_word_budget_repair_authoritative_after_x2,
        )(
            artifact_dir,
            accepted=_word_budget_repair_accepted,
            x2_gates=x2,
        )
        if x2_failed_initial and not (artifact_dir / "x1d_llm_judge_outputs.json").is_file():
            _lane_attr("_write_x1d_judge_artifacts", _write_x1d_judge_artifacts)(artifact_dir, x1d)
    if x2_failed_initial:
        _lane_attr("_emit_dimension_upstream_triangulation", _emit_dimension_upstream_triangulation)(
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

    ctx.setdefault("_pool_publish_applied", False)
    _graph_bindings_lane = None
    _gtc_lane_dict = None
    if runtime_generation_status == "REAL_LLM" and not x2_failed_initial:
        from apps_rg.runtime.sections.executive_summary_judge_remediation import (
            refresh_x1d_judges_after_full_x2,
        )
        from apps_rg.runtime.validators.executive_summary_x2 import (
            append_executive_summary_x1d_x2_gate_dicts,
        )
        from apps_rg.runtime.c0.c03_graph_ref_policy import (
            extract_c03_bindings_from_runtime_payload,
        )

        _gtc_lane = runtime_payload.get("graph_targeting_capsule")
        _gtc_lane_dict = dict(_gtc_lane) if isinstance(_gtc_lane, dict) else None
        _graph_bindings_lane = extract_c03_bindings_from_runtime_payload(runtime_payload)
        _prior_judged_sha = str(ctx.get("_x1d_judged_display_sha256") or "")
        if should_skip_unchanged_summary_judge_refresh(
            x1d,
            display_text=resume_display_text,
            prior_display_sha256=_prior_judged_sha,
        ):
            _judged_display_sha = _prior_judged_sha
            _x1d_refresh_receipt = {"skipped": "unchanged_resume_display_text"}
        else:
            x1d, _x1d_refresh_receipt = refresh_x1d_judges_after_full_x2(
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
                prior_judges=[],
                graph_targeting_capsule=_gtc_lane_dict,
                material_targeting_bundle=_bundle_mat.to_dict()
                if hasattr(_bundle_mat, "to_dict")
                else runtime_payload.get("material_targeting_bundle"),
                graph_bindings=_graph_bindings_lane,
                repo_root=REPO_ROOT,
            )
            _judged_display_sha = _display_text_sha256(resume_display_text)
            ctx["_x1d_judged_display_sha256"] = _judged_display_sha
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
                targeting_context={
                    "target_title": _lane_attr("_args_target_title", _args_target_title)(args),
                    "target_company": str(args.target_company),
                },
                mock_mode=(judge_mode == "mocked"),
                artifact_dir=artifact_dir,
            )
            if repair_rec.repair_succeeded:
                repaired_text = str(repaired_cand.get("resume_display_text") or "")
                if should_skip_unchanged_summary_judge_refresh(
                    x1d,
                    display_text=repaired_text,
                    prior_display_sha256=_judged_display_sha,
                ) or _display_text_sha256(repaired_text) == _judged_display_sha:
                    if isinstance(_x1d_refresh_receipt, dict):
                        _x1d_refresh_receipt = {
                            **_x1d_refresh_receipt,
                            "voice_repair_rejudge_skipped": "unchanged_resume_display_text",
                        }
                elif repaired_text.strip():
                    from apps_rg.runtime.c0.resume_graph_claim_binding import (
                        GRAPH_CLAIM_BINDING_GATE_ID,
                        build_pre_x2_resume_graph_claim_binding_gate,
                    )
                    from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import (
                        write_synced_canonical_claim_ledger_v2,
                    )
                    from apps_rg.runtime.sections.executive_summary_judge_regen_loop import (
                        sync_claim_ledger_metrics_from_facts,
                    )
                    from apps_rg.runtime.sections.executive_summary_judge_remediation import (
                        rerun_x2_after_judge_remediation,
                    )
                    from apps_rg.runtime.sections.executive_summary_voice_repair import (
                        finalize_executive_summary_coherence,
                    )
                    from apps_rg.runtime.sections.section_authority_repairs import (
                        apply_exec_summary_display_authority_repairs,
                    )
                    from apps_rg.runtime.validators.executive_summary_sentence_utils import (
                        split_sentences,
                    )

                    _vr_orig_text = resume_display_text
                    _vr_orig_ledger = [dict(r) if isinstance(r, dict) else r for r in (claim_ledger or [])]
                    _vr_orig_parsed = dict(parsed) if isinstance(parsed, dict) else parsed
                    _vr_orig_parsed_for_x2 = (
                        dict(parsed_for_x2) if isinstance(parsed_for_x2, dict) else parsed_for_x2
                    )
                    _vr_orig_x2 = list(x2)
                    _vr_orig_coverage = ctx.get("coverage")
                    _vr_orig_l2 = dict(ctx["l2_output"]) if isinstance(ctx.get("l2_output"), dict) else None

                    _plan_facts_vr = list(
                        (ctx.get("selected_fact_plan") or {}).get("facts")
                        or selected_facts_for_x2
                        or []
                    )
                    _vr_text = repaired_text
                    repaired_sents = [
                        s for s in split_sentences(_vr_text) if str(s).strip()
                    ]
                    cand_ledger = repaired_cand.get("claim_ledger")
                    if (
                        isinstance(cand_ledger, list)
                        and len(cand_ledger) == len(repaired_sents)
                        and all(isinstance(r, dict) for r in cand_ledger)
                    ):
                        _vr_ledger = [dict(r) for r in cand_ledger]
                    elif repaired_sents:
                        all_prior_ids: list[str] = []
                        for row in _vr_orig_ledger:
                            if isinstance(row, dict):
                                for fid in row.get("source_fact_ids") or []:
                                    s = str(fid).strip()
                                    if s and s not in all_prior_ids:
                                        all_prior_ids.append(s)
                        synced_rows: list[dict[str, Any]] = []
                        for idx, sent in enumerate(repaired_sents):
                            base_row = (
                                dict(_vr_orig_ledger[idx])
                                if idx < len(_vr_orig_ledger)
                                and isinstance(_vr_orig_ledger[idx], dict)
                                else {"source_fact_ids": list(all_prior_ids)}
                            )
                            base_row["claim_text"] = sent
                            base_row["claim"] = sent[:80]
                            synced_rows.append(base_row)
                        _vr_ledger = synced_rows
                    else:
                        _vr_ledger = list(_vr_orig_ledger)

                    _vr_parsed = dict(_vr_orig_parsed) if isinstance(_vr_orig_parsed, dict) else _vr_orig_parsed
                    if isinstance(_vr_parsed, dict):
                        _vr_parsed["resume_display_text"] = _vr_text
                        _vr_parsed["claim_ledger"] = _vr_ledger
                        _vr_parsed = apply_exec_summary_display_authority_repairs(
                            _vr_parsed,
                            allowed_fact_ids=allowed_fact_ids,
                            plan_facts=_plan_facts_vr,
                            artifact_dir=artifact_dir,
                            target_company=str(getattr(args, "target_company", "") or ""),
                        )
                        _vr_parsed, _ = finalize_executive_summary_coherence(
                            _vr_parsed,
                            selected_facts=_plan_facts_vr,
                            allowed_fact_ids=allowed_fact_ids,
                            runtime_generation_status=str(runtime_generation_status or ""),
                        )
                        _vr_parsed, _ = sync_claim_ledger_metrics_from_facts(
                            _vr_parsed,
                            plan_facts=_plan_facts_vr,
                            allowed_fact_ids=allowed_fact_ids,
                        )
                        _vr_text = str(_vr_parsed.get("resume_display_text") or _vr_text)
                        _vr_ledger = list(_vr_parsed.get("claim_ledger") or _vr_ledger)

                    _vr_coverage = build_sentence_claim_coverage(
                        _vr_text, _vr_ledger, allowed_fact_ids
                    )
                    if isinstance(_vr_parsed, dict):
                        _vr_parsed_for_x2 = enrich_parsed_for_x2(
                            _vr_parsed,
                            coverage=_vr_coverage,
                            input_payload_hash=str(ctx.get("input_payload_hash") or ""),
                            allowed_fact_ids=allowed_fact_ids,
                            runtime_payload=runtime_payload,
                        )
                    elif isinstance(_vr_orig_parsed_for_x2, dict):
                        _vr_parsed_for_x2 = dict(_vr_orig_parsed_for_x2)
                        _vr_parsed_for_x2["resume_display_text"] = _vr_text
                        _vr_parsed_for_x2["claim_ledger"] = _vr_ledger
                    else:
                        _vr_parsed_for_x2 = _vr_orig_parsed_for_x2

                    def _persist_vr_artifacts(
                        text_val: str,
                        ledger_val: list[dict[str, Any]],
                        cov_val: Any,
                        l2_base: dict[str, Any] | None,
                    ) -> None:
                        if isinstance(l2_base, dict):
                            l2_doc = dict(l2_base)
                            l2_doc["resume_display_text"] = text_val
                            l2_doc["claim_ledger"] = ledger_val
                            l2_doc["text_claim_coverage"] = cov_val
                            ctx["l2_output"] = l2_doc
                            _lane_attr("write_json", write_json)(artifact_dir / "l2_output.json", l2_doc)
                        _wg.write_text(
                            artifact_dir / "resume_display_text.txt",
                            text_val + "\n",
                            encoding="utf-8",
                        )
                        _lane_attr("write_json", write_json)(artifact_dir / "claim_ledger.json", ledger_val)
                        _lane_attr("write_json", write_json)(
                            artifact_dir / "text_claim_coverage.json", cov_val
                        )
                        write_synced_canonical_claim_ledger_v2(
                            artifact_dir=artifact_dir,
                            claim_ledger=ledger_val,
                            parse_status=str(ctx.get("parse_status") or "OK"),
                            invalid_reason=ctx.get("invalid_reason"),
                            normalize_ledger_fn=normalize_exec_summary_claim_ledger,
                            build_payload_fn=build_canonical_claim_ledger_v2_payload,
                            write_json_fn=_lane_attr("write_json", write_json),
                        )
                        from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import (
                            sync_section_input_usage_ledger_claims,
                        )

                        _synced_vr_usage = sync_section_input_usage_ledger_claims(
                            artifact_dir=artifact_dir,
                            usage_doc=usage_doc if isinstance(usage_doc, dict) else None,
                            claim_ledger=ledger_val,
                            allowed_fact_ids=allowed_fact_ids,
                            write_json_fn=_lane_attr("write_json", write_json),
                        )
                        if _synced_vr_usage is not None:
                            usage_doc.clear()
                            usage_doc.update(_synced_vr_usage)

                    _persist_vr_artifacts(_vr_text, _vr_ledger, _vr_coverage, _vr_orig_l2)

                    _vr_x2_ok = True
                    _vr_det_failed_ids: list[str] = []
                    _vr_new_x2: list[dict[str, Any]] | None = None
                    _vr_pool = ctx.get("pool")
                    if _vr_pool is not None and ctx.get("selected_fact_plan") is not None:
                        _vr_x2_full = rerun_x2_after_judge_remediation(
                            resume_display_text=_vr_text,
                            parsed_for_x2=_vr_parsed_for_x2,
                            claim_ledger=_vr_ledger,
                            text_claim_coverage=_vr_coverage,
                            allowed_fact_ids=allowed_fact_ids,
                            args=args,
                            jd_text=_judge_jd,
                            temperature=float(ctx.get("temperature") or 0.0),
                            runtime_generation_status=runtime_generation_status,
                            artifact_dir=artifact_dir,
                            model_name=str(ctx.get("model_name") or ""),
                            prompt_hash=str(ctx.get("prompt_hash") or ""),
                            compiled_prompt=compiled_prompt,
                            raw_output=raw_output,
                            selected_facts=selected_facts_for_x2,
                            selected_fact_plan=ctx["selected_fact_plan"],
                            x1d_judges=x1d,
                            proof_pool_metadata=ctx.get("pp_x2") if ctx.get("proof_pool_x2_active") else None,
                            proof_pool_ref=str(getattr(_vr_pool, "proof_pool_ref", "") or ""),
                            proof_pool_digest=str(getattr(_vr_pool, "proof_pool_digest", "") or ""),
                        )
                        _vr_det_x2 = [
                            g
                            for g in _vr_x2_full
                            if not str(g.get("gate_id") or "").startswith("x2_x1d_")
                        ]
                        _vr_det_failed_ids = [
                            str(g.get("gate_id") or "")
                            for g in _vr_det_x2
                            if not g.get("pass")
                        ]
                        if _vr_det_failed_ids:
                            _vr_x2_ok = False
                        else:
                            _vr_new_x2 = _vr_det_x2
                    else:
                        _vr_binding_gate = build_pre_x2_resume_graph_claim_binding_gate(
                            section_id="executive_summary",
                            claim_rows=_vr_ledger,
                            selected_fact_plan=ctx.get("selected_fact_plan") or {},
                        )
                        if _vr_binding_gate is not None:
                            if not _vr_binding_gate.get("pass"):
                                _vr_x2_ok = False
                                _vr_det_failed_ids = [GRAPH_CLAIM_BINDING_GATE_ID]
                            else:
                                _vr_new_x2 = [
                                    gate
                                    for gate in _vr_orig_x2
                                    if str(gate.get("gate_id") or "") != GRAPH_CLAIM_BINDING_GATE_ID
                                ] + [_vr_binding_gate]

                    if not _vr_x2_ok:
                        resume_display_text = _vr_orig_text
                        claim_ledger = _vr_orig_ledger
                        parsed = _vr_orig_parsed
                        parsed_for_x2 = _vr_orig_parsed_for_x2
                        x2 = _vr_orig_x2
                        ctx["coverage"] = _vr_orig_coverage
                        ctx["claim_ledger"] = claim_ledger
                        _persist_vr_artifacts(
                            _vr_orig_text, _vr_orig_ledger, _vr_orig_coverage, _vr_orig_l2
                        )
                        if isinstance(_x1d_refresh_receipt, dict):
                            _x1d_refresh_receipt = {
                                **_x1d_refresh_receipt,
                                "voice_repair_rejected_x2_failed_gates": _vr_det_failed_ids,
                            }
                    else:
                        resume_display_text = _vr_text
                        claim_ledger = _vr_ledger
                        parsed = _vr_parsed
                        parsed_for_x2 = _vr_parsed_for_x2
                        if _vr_new_x2 is not None:
                            x2 = _vr_new_x2
                        ctx["coverage"] = _vr_coverage
                        ctx["claim_ledger"] = claim_ledger
                        x1d, _x1d_refresh_receipt = refresh_x1d_judges_after_full_x2(
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
                            prior_judges=[],
                            graph_targeting_capsule=_gtc_lane_dict,
                            material_targeting_bundle=_bundle_mat.to_dict()
                            if hasattr(_bundle_mat, "to_dict")
                            else runtime_payload.get("material_targeting_bundle"),
                            graph_bindings=_graph_bindings_lane,
                            repo_root=REPO_ROOT,
                        )
                        _judged_display_sha = _display_text_sha256(resume_display_text)
                        ctx["_x1d_judged_display_sha256"] = _judged_display_sha
        from apps_rg.runtime.sections.executive_summary_repair_policy import (
            judge_regeneration_enabled,
        )

        if isinstance(_x1d_refresh_receipt, dict):
            _x1d_refresh_receipt = {
                **_x1d_refresh_receipt,
                "phase": "post_x2_initial",
                "rescore_only": not judge_regeneration_enabled(),
            }
        _lane_attr("write_json", write_json)(artifact_dir / "post_x2_x1d_refresh_receipt.json", _x1d_refresh_receipt)
        _lane_attr("_write_x1d_judge_artifacts", _write_x1d_judge_artifacts)(artifact_dir, x1d)
        _lane_attr("_emit_dimension_upstream_triangulation", _emit_dimension_upstream_triangulation)(
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
        _lane_attr("write_x2_gate_outputs", write_x2_gate_outputs)(artifact_dir / "x2_gate_outputs.json", x2, section_id="executive_summary")
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
            write_json_fn=_lane_attr("write_json", write_json),
        )
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
    _regen_ok = False
    _regen_parity_reason = "x2_failed_initial"
    if runtime_generation_status == "REAL_LLM" and not x2_failed_initial and parsed_for_x2:
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
        ctx.update({
            "x1d": x1d,
            "x2": x2,
            "resume_display_text": resume_display_text,
            "claim_ledger": claim_ledger,
            "parsed": parsed,
            "parsed_for_x2": parsed_for_x2,
            "judge_packet": judge_packet,
            "judge_packet_ref": judge_packet_ref,
            "_targeting_parity": _targeting_parity,
            "usage_doc": usage_doc,
            "_composition_plan_refresh": _composition_plan_refresh,
            "_graph_bindings_lane": _graph_bindings_lane,
            "_gtc_lane_dict": _gtc_lane_dict,
            "_regen_ok": _regen_ok,
        })
        if judge_remediation_regen_allowed() and _regen_ok:
            run_remediation_cycles(ctx)
        elif judge_remediation_regen_allowed() and not _regen_ok:
            _lane_attr("write_json", write_json)(
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
            x2_passed=not x2_failed_initial,
        )
        _lane_attr("write_json", write_json)(artifact_dir / "judge_remediation_trigger.json", _trigger0)
