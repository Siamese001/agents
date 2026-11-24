"""Canonical 15-artifact contract emitter & runner for headline_v2."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from apps_rg.runtime.c0.section_proof_loader import apply_proof_pool_to_usage_ledger, load_section_proof_for_lane
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import classify_ledger_parse_state
from apps_rg.runtime.claim_ledger.headline_claim_ledger import build_headline_canonical_claim_ledger_v2, build_headline_text_claim_coverage, normalize_headline_claim_ledger
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.exit.headline_x3 import aggregate_x3 as _aggregate_headline_x3
from apps_rg.runtime.judges.headline_x1d import run_headline_judges
from apps_rg.runtime.product_evidence_authority import x2_proof_pool_gate_flags
from apps_rg.runtime.providers.section_provider_call import call_section_model_provider
from apps_rg.runtime.reasoning.prompt_control_proof import summarize_reasoning_receipt_for_bundle
from apps_rg.runtime.runtime_proof_layout import finalize_runtime_proof_run, prepare_runtime_proof_run_dir, proof_bucket_for_provider, rel_posix
from apps_rg.runtime.section_execution_plan import dependencies_for_section
from apps_rg.runtime.section_l2_lane_integration import finalize_section_l2_after_output, prepare_section_l2_before_provider
from apps_rg.runtime.section_model_limits import resolve_section_generation_model
from apps_rg.runtime.section_one_spine_certification_lane_integration import finalize_section_one_spine_certification
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import allow_non_allow_exit_zero_ok, attach_lane_proof_bundle_fields, compute_lane_proof_bundle
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.section_repair_lane_integration import record_regen_llm
from apps_rg.runtime.section_repair_ledger import KIND_MECHANICAL, KIND_REGEN_LLM, attach_ledger_summary_to_l2, init_ledger, load_ledger, record_repair, record_x2_run, set_authoritative_attempt
from apps_rg.runtime.section_runtime_exhaust_lane_integration import finalize_section_runtime_exhaust_before_l6, gate_section_l6_shadow_after_exhaust
from apps_rg.runtime.sections.companion_lane_context import build_resume_support_blob, load_companion_context
from apps_rg.runtime.sections.graph_evidence_contract import merge_graph_evidence_reporting_into_dict
from apps_rg.runtime.sections.headline_fact_id_resolution import headline_fact_namespace_metric_fields
from apps_rg.runtime.sections.headline_pa import compile_headline_prompt
from apps_rg.runtime.sections.lane_perf_sync_helpers import execute_headline_judges_with_final_display_gate
from apps_rg.runtime.sections.prompt_trace_reasoning import attach_reasoning_to_prompt_trace
from apps_rg.runtime.sections.resume_employment_bullets import collect_employment_bullets
from apps_rg.runtime.sections.section_generation import build_section_request, merge_transport_context, tag_reasoning_lane
from apps_rg.runtime.sections.section_product_shape_ssot import HEADLINE_WORD_MAX, HEADLINE_WORD_MIN
from apps_rg.runtime.sections.upstream_evidence_block import wire_spine_c0_fec_or_block
from apps_rg.runtime.shadow.headline_l6 import build_l6_shadow_package, emit_headline_l6_shadow_learning_outputs
from apps_rg.runtime.shadow.l6_handoff_packet import repo_rel
from apps_rg.runtime.spine.c0_fec_compose import merge_compiled_prompt_artifact_fec_fields
from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3
from apps_rg.runtime.validators.headline_x2 import evaluate_headline_literal_grounding, has_valid_headline_prefix, headline_word_count, recite_canonical_segments_to_bundle_facts, repair_headline_segment_citations_for_grounding, run_headline_x2_gates, validate_raw_headline_claim_ledger
from apps_rg.runtime.validators.proof_pool_source_fact_validation import write_x2_source_fact_pool_receipt
from .blind_judge_and_loop import apply_headline_content_signal_repair, retry_headline_proof_shape, retry_headline_word_and_pipe, retry_provider_for_parse
from .evidence_firewall import BRIEFING_DEFAULT, HEADLINE_JSON_OUTPUT_STATUSES, HEADLINE_MAX_OUTPUT_TOKENS, JD_TEXT_DEFAULT, LANE_KEY, PROMPT_ID, REPO_ROOT, TARGET_COMPANY_DEFAULT, TARGET_TITLE_DEFAULT, TRACE_RUNTIME_PATH_DEFAULT, build_headline_allowed_fact_packet, build_runtime_payload, coerce_segment_claim_ledger_rows, collect_employer_names_lower, extract_candidate_name_tokens, sha16, snapshot_raw_jd_alignment, sync_selected_fact_plan_required_ids, write_json
from .prompt_and_generate import normalize_parsed_output, parse_model_json
from .x2_invariants import headline_proof_bundle_labels, headline_resume_native_clarity_report, infer_product_quality, snapshot_needs_headline_proof_retry, write_x2_gate_outputs

def _x2_gate_pass(x2_gates: list[dict[str, Any]], gate_id: str) -> bool:
    return any(g.get("gate_id") == gate_id and bool(g.get("pass")) for g in x2_gates)

def _x2_gate_failure_detail(x2_gates: list[dict[str, Any]], gate_id: str) -> list[str]:
    return [f"{g.get('failure_reason') or 'fail'} (observed={g.get('observed_value')!r})" for g in x2_gates if g.get("gate_id") == gate_id and not g.get("pass")]

def _emit_headline_final_evidence_reports(artifact_dir: Path, *, run_id: str, x2_gates: list[dict[str, Any]], x3_record: dict[str, Any], reasoning_summary: dict[str, Any], proof_bundle: dict[str, Any]) -> tuple[Path, Path]:
    bundle_index = artifact_dir / "RUN_BUNDLE_INDEX.json"
    bundle_required_ok: dict[str, Any] = {"present": bundle_index.is_file(), "required_missing": []}
    if bundle_index.is_file():
        try:
            doc = json.loads(bundle_index.read_text(encoding="utf-8"))
            if isinstance(entries := (doc.get("entries") if isinstance(doc, dict) else None), list):
                bundle_required_ok["required_missing"] = [e.get("relative_path") for e in entries if isinstance(e, dict) and e.get("required") and not e.get("exists")]
        except (json.JSONDecodeError, OSError):
            bundle_required_ok["parse_error"] = True
    l6_surface: dict[str, Any] = {"authoritative_l6_proof_surface": "runtime_bundle_json_under_this_run_dir", "offline_only_no_runtime_authority": True, "primary_artifacts": ["l6_shadow_eval_package.json", "l6_shadow_learning.json", "l6_future_run_proposals.json"], "note": "L6 headline artifacts are offline-only shadow packets; they do not mutate X2/X3/final headline output and carry no production runtime authority."}
    mf_path = artifact_dir / "run_manifest.json"
    if mf_path.is_file():
        try:
            mf_doc = json.loads(mf_path.read_text(encoding="utf-8"))
            if isinstance(links := (mf_doc.get("artifact_links") if isinstance(mf_doc, dict) else None), dict) and (l6_links := {k: links[k] for k in ("l6_shadow_eval_package.json", "l6_shadow_learning.json", "l6_future_run_proposals.json") if k in links}):
                l6_surface["run_manifest_artifact_links"] = l6_links
        except (json.JSONDecodeError, OSError):
            l6_surface["run_manifest_parse_error"] = True
    summary = {"section_id": "headline", "run_id": run_id, "prompt_control_receipt": reasoning_summary, "raw_model_claim_ledger_schema_valid": _x2_gate_pass(x2_gates, "x2_headline_raw_model_schema_valid"), "normalized_headline_schema_valid": _x2_gate_pass(x2_gates, "x2_headline_schema_valid"), "self_check_consistent": _x2_gate_pass(x2_gates, "x2_headline_self_check_consistent"), "x2_failed_gates": [g["gate_id"] for g in x2_gates if not g.get("pass")], "x3_code": x3_record.get("x3_code"), "proof_eligible": proof_bundle.get("proof_eligible"), "runtime_certification": proof_bundle.get("runtime_certification"), "bundle_index_required_audit": bundle_required_ok, "l6_proof_surface": l6_surface}
    json_path = artifact_dir / "headline_final_evidence_summary.json"
    write_json(json_path, summary)
    md_path = artifact_dir / "headline_final_evidence_report.md"
    _wg.write_text(md_path, f"# Headline final evidence report\n\n- run_id: `{run_id}`\n- proof_eligible (bundle): `{proof_bundle.get('proof_eligible')}`\n- runtime_certification label: `{proof_bundle.get('runtime_certification')}`\n- prompt receipt summary: `{json.dumps(reasoning_summary, sort_keys=True)}`\n- raw claim_ledger schema (X2): `{summary['raw_model_claim_ledger_schema_valid']}`\n- normalized headline schema (X2): `{summary['normalized_headline_schema_valid']}`\n- self_check consistent (X2): `{summary['self_check_consistent']}`\n- X3: `{x3_record.get('x3_code')}`\n- X2 failures: `{summary['x2_failed_gates']}`\n- RUN_BUNDLE_INDEX required_missing: `{bundle_required_ok.get('required_missing')}`\n", encoding="utf-8")
    return md_path, json_path

def build_headline_lane_args(*, provider: str, temperature: float, x1d_judges: str, mock_judges: bool, allow_test_mock_judges: bool = False, allow_non_allow_exit_zero: bool = False, target_title: str, target_company: str, jd_text: str, briefing: str, base_resume_ref: str = "", diagnostic_focus: str = "", force_new_seed: bool = False, reasoning_effort: str = "") -> SimpleNamespace:
    return SimpleNamespace(provider=str(provider).strip() or "external_claude", temperature=float(temperature), x1d_judges=str(x1d_judges), mock_judges=bool(mock_judges), allow_test_mock_judges=bool(allow_test_mock_judges), allow_non_allow_exit_zero=bool(allow_non_allow_exit_zero), target_title=str(target_title).strip() or TARGET_TITLE_DEFAULT, target_company=str(target_company).strip() or TARGET_COMPANY_DEFAULT, jd_text=str(jd_text).strip() or JD_TEXT_DEFAULT, briefing=str(briefing).strip() or BRIEFING_DEFAULT, base_resume_ref=str(base_resume_ref or ""), diagnostic_focus=str(diagnostic_focus or "").strip(), force_new_seed=bool(force_new_seed), reasoning_effort=str(reasoning_effort or "").strip().lower())

def _hl_override(attr: str, default: Any) -> Any:
    hl_mod = sys.modules.get("apps_rg.runtime.sections.headline_lane")
    return getattr(hl_mod, attr, default) if hl_mod is not None else default

def run_headline_v2(args: SimpleNamespace, *, artifact_dir_override: Path | None = None, trace_runtime_path: str = TRACE_RUNTIME_PATH_DEFAULT, print_output: bool = True, repo_root_override: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root_override or REPO_ROOT
    from apps_rg.runtime.c0 import section_proof_loader as _spl
    pool, base, base_path, base_hash, front_spine = _spl.load_section_proof_for_lane(section_id="headline", args=args, repo_root=repo_root, collect_employment_bullets_fn=collect_employment_bullets)
    selected_fact_plan, allowed_fact_ids, bullet_rows, proof_pool_metadata = dict(pool.selected_fact_plan), pool.allowed_fact_ids, pool.bullet_rows, pool.proof_pool_metadata
    candidate_pool_ids, employer_names, candidate_name_tokens = sorted(allowed_fact_ids), collect_employer_names_lower(base), extract_candidate_name_tokens(base)
    from apps_rg.runtime.env_bootstrap import get_env_str

    companion_context = "" if (dependencies_for_section("headline") == () and get_env_str("APPS_RG_HEADLINE_LOAD_COMPANION", "").strip() != "1") else _hl_override("load_companion_context", load_companion_context)()
    companion_nonempty, resume_blob, employer_blob = bool(companion_context.strip()), build_resume_support_blob(bullet_rows, companion_context), "\n".join(f"- {n}" for n in employer_names)
    runtime_payload = build_runtime_payload(base_json_path=base_path, base_hash=base_hash, selected_fact_plan=selected_fact_plan, allowed_fact_ids=allowed_fact_ids, target_title=args.target_title, target_company=args.target_company, jd_text=args.jd_text, briefing=args.briefing, repo_root=repo_root)
    runtime_payload["proof_pool_metadata"] = proof_pool_metadata
    if focus := str(getattr(args, "diagnostic_focus", "") or "").strip():
        runtime_payload["recovery_diagnostic_focus"] = focus
    artifact_dir = Path(artifact_dir_override).resolve() if artifact_dir_override is not None else prepare_runtime_proof_run_dir(repo_root, LANE_KEY, args.provider, runtime_payload["run_id"])
    _wg.ensure_dir(artifact_dir)
    init_ledger(artifact_dir, section_id="headline", run_id=str(runtime_payload["run_id"]))
    _wg.write_text(artifact_dir / "companion_generated_sections.txt", companion_context or "(none)\n", encoding="utf-8")
    merge_transport_context(artifact_dir=str(artifact_dir.resolve()), run_id=str(runtime_payload.get("run_id") or ""))
    from apps_rg.runtime.sections import upstream_evidence_block as _ueb
    if (blocked := _ueb.wire_spine_c0_fec_or_block(repo_root=repo_root, artifact_dir=artifact_dir, section_id="headline", front_spine=front_spine, pool=pool, runtime_payload=runtime_payload, provider=str(args.provider), temperature=float(args.temperature), max_tokens=HEADLINE_MAX_OUTPUT_TOKENS, output_filename="headline_output.txt")) is not None:
        return blocked
    fact_lines = "\n".join(f"- {row['fact_id']}: {row['claim_text']}" + (f" | tech: {', '.join(row['technologies'])}" if row.get("technologies") else "") for row in bullet_rows)
    input_payload_hash = sha16(json.dumps(runtime_payload, sort_keys=True))
    section_compiled = _hl_override("compile_headline_prompt", compile_headline_prompt)(runtime_payload, companion_context=companion_context, fact_lines=fact_lines, forbidden_employer_lines=employer_blob, run_id=runtime_payload["run_id"])
    messages = section_compiled.artifact.messages
    prompt_hash = sha16(json.dumps(messages, ensure_ascii=False, separators=(",", ":")))
    write_json(artifact_dir / "runtime_payload.json", runtime_payload)
    _wg.write_text(artifact_dir / "compiled_prompt.txt", json.dumps(messages, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_json(artifact_dir / "compiled_prompt_artifact.json", merge_compiled_prompt_artifact_fec_fields({"section_id": section_compiled.section_id, "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref, "compiler_template_id": section_compiled.artifact.template_id, "pa_prompt_hash": section_compiled.artifact.prompt_hash, "dispatch_sha256_prompt16": prompt_hash, "slot_count": section_compiled.artifact.slot_count}, runtime_payload))
    from apps_rg.runtime import section_l2_lane_integration as _sli
    _sli.prepare_section_l2_before_provider(artifact_dir, "headline", runtime_payload, provider_lane=str(args.provider))
    section_model = resolve_section_generation_model(LANE_KEY, provider_profile=str(args.provider))
    provider_req, provider_payload = build_section_request(messages=messages, prompt_hash=prompt_hash, input_payload_hash=input_payload_hash, temperature=args.temperature, max_tokens=HEADLINE_MAX_OUTPUT_TOKENS, model=section_model, provider_requested=str(args.provider), compiled_prompt_artifact=section_compiled.artifact, anthropic_workload_kind="ONE_SHOT", idempotent_replay_safe=True, reasoning_effort=getattr(args, "reasoning_effort", None), force_new_seed=bool(getattr(args, "force_new_seed", False)))
    provider_payload["reasoning_effort"] = "low"
    provider_request_data = provider_req.to_dict()
    write_json(artifact_dir / "provider_request.json", provider_request_data)
    from apps_rg.runtime.providers import section_provider_call as _spc
    result = _spc.call_section_model_provider(str(args.provider), tag_reasoning_lane(provider_payload, LANE_KEY), artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""))
    provider_result_data = result.to_dict()
    raw_output = provider_raw_output = result.raw_model_output
    write_json(artifact_dir / "provider_response.json", provider_result_data)
    reasoning_receipt = _rrec if isinstance(provider_result_data, dict) and isinstance(_rrec := provider_result_data.get("reasoning_execution_receipt"), dict) else None
    runtime_generation_status = result.runtime_generation_status
    parsed, parsed_raw_pre_normalize, parse_error = None, None, ""
    attempt1_pre_norm, proof_retry_attempted, proof_retry_reason = None, False, ""
    repair_receipt: dict[str, Any] | None = None
    repair_call_made, cs_accepted, fmt_accepted = False, False, False
    if runtime_generation_status in HEADLINE_JSON_OUTPUT_STATUSES:
        raw_orig = raw_output
        parsed, parse_error = parse_model_json(raw_orig)
        if parsed is None and str(args.provider) == "external_claude":
            repair_call_made = True
            raw_orig, parsed, parse_error = retry_provider_for_parse(messages, provider_payload, raw_orig, parse_error, artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""))
            if parsed is not None:
                record_repair(artifact_dir, kind=KIND_MECHANICAL, operation="parse_json_retry", reason=parse_error or "parse_retry", replaced_l2=False)
        if parsed is not None:
            attempt1 = json.loads(json.dumps(parsed))
            attempt1_pre_norm = json.loads(json.dumps(attempt1))
            raw_schema_ok, _, _ = validate_raw_headline_claim_ledger(attempt1)
            needs_proof_retry, proof_retry_reason = snapshot_needs_headline_proof_retry(attempt1, target_company=str(args.target_company or ""), employer_names_lower=employer_names)
            if needs_proof_retry and not raw_schema_ok:
                repair_call_made = True
                raw_r, parsed_r, snap_r = retry_headline_proof_shape(messages, provider_payload, raw_output, attempt1, runtime_payload, allowed_fact_ids, proof_retry_reason, companion_nonempty=companion_nonempty, employer_names_lower=employer_names, artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""))
                if parsed_r is not None and snap_r is not None:
                    proof_retry_attempted = True
                    record_repair(artifact_dir, kind=KIND_REGEN_LLM, operation="headline_proof_shape_retry", reason=proof_retry_reason[:240], replaced_l2=True)
                    parsed, raw_output, parsed_raw_pre_normalize = parsed_r, raw_r, snap_r
            if not proof_retry_attempted:
                hl0 = str(parsed.get("headline_line", "")).strip()
                snapshot_raw_jd_alignment(parsed)
                parsed_raw_pre_normalize = attempt1
                parsed = normalize_parsed_output(parsed, runtime_payload, allowed_fact_ids, hl0, companion_nonempty=companion_nonempty, employer_names_lower=employer_names, allow_prose_mutation=(runtime_generation_status != "REAL_LLM"))
                raw_output = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
            hl = str(parsed.get("headline_line", "")).strip()
            wc = headline_word_count(hl)
            if hl.count(" | ") != 3 or not has_valid_headline_prefix(hl) or not (HEADLINE_WORD_MIN <= wc <= HEADLINE_WORD_MAX):
                repair_call_made = True
                raw_output, parsed, rsnap = retry_headline_word_and_pipe(messages, provider_payload, raw_output, parsed, runtime_payload, allowed_fact_ids, f"word_count={wc} or pipe_format invalid", companion_nonempty=companion_nonempty, employer_names_lower=employer_names, artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""))
                if rsnap is not None:
                    record_regen_llm(artifact_dir, operation="headline_format_repair", reason=f"word_count={wc} or pipe_format invalid", replaced_l2=True)
                    parsed_raw_pre_normalize, fmt_accepted = rsnap, True
                if parsed is not None:
                    raw_output = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
            raw_output, parsed, cs_snap, cs_accepted = apply_headline_content_signal_repair(messages=messages, provider_payload=provider_payload, raw_output=raw_output, parsed=parsed, runtime_payload=runtime_payload, allowed_fact_ids=allowed_fact_ids, artifact_dir=artifact_dir, runtime_generation_status=runtime_generation_status, prior_repair_provider_call_made=repair_call_made, companion_nonempty=companion_nonempty, employer_names_lower=employer_names)
            if cs_snap is not None:
                parsed_raw_pre_normalize = cs_snap
        else:
            raw_output = raw_orig
    else:
        parse_error = result.exact_provider_error or "provider blocked"
    return _finalize_headline_v2(locals())

def _finalize_headline_v2(ctx: dict[str, Any]) -> dict[str, Any]:
    args, repo_root, artifact_dir, pool = ctx["args"], ctx["repo_root"], ctx["artifact_dir"], ctx["pool"]
    selected_fact_plan, allowed_fact_ids, proof_pool_metadata, candidate_pool_ids = ctx["selected_fact_plan"], ctx["allowed_fact_ids"], ctx["proof_pool_metadata"], ctx["candidate_pool_ids"]
    employer_names, candidate_name_tokens, companion_context, companion_nonempty, resume_blob = ctx["employer_names"], ctx["candidate_name_tokens"], ctx["companion_context"], ctx["companion_nonempty"], ctx["resume_blob"]
    runtime_payload, input_payload_hash, section_compiled, prompt_hash = ctx["runtime_payload"], ctx["input_payload_hash"], ctx["section_compiled"], ctx["prompt_hash"]
    provider_request_data, provider_result_data, raw_output, provider_raw_output = ctx["provider_request_data"], ctx["provider_result_data"], ctx["raw_output"], ctx["provider_raw_output"]
    reasoning_receipt, runtime_generation_status, parsed, parsed_raw_pre_normalize, parse_error = ctx["reasoning_receipt"], ctx["runtime_generation_status"], ctx["parsed"], ctx["parsed_raw_pre_normalize"], ctx["parse_error"]
    attempt1_pre_norm, proof_retry_attempted, proof_retry_reason = ctx["attempt1_pre_norm"], ctx["proof_retry_attempted"], ctx["proof_retry_reason"]
    repair_receipt, cs_accepted, fmt_accepted, trace_runtime_path, print_output = ctx["repair_receipt"], ctx["cs_accepted"], ctx["fmt_accepted"], ctx["trace_runtime_path"], ctx["print_output"]
    fid_rec = parsed.pop("fact_id_resolution_receipt", None) if isinstance(parsed, dict) and isinstance(parsed.get("fact_id_resolution_receipt"), dict) else None
    headline_line, claim_ledger = str((parsed or {}).get("headline_line") or "").strip(), list((parsed or {}).get("claim_ledger") or [])
    pos_bundles = proof_pool_metadata.get("headline_positioning_bundles") if isinstance(proof_pool_metadata, dict) else None
    if isinstance(parsed, dict) and claim_ledger and headline_line and isinstance(pos_bundles, list):
        recited_led, bundle_rec = recite_canonical_segments_to_bundle_facts(headline_line=headline_line, claim_ledger=claim_ledger, positioning_bundles=pos_bundles, allowed_fact_ids=allowed_fact_ids)
        if bundle_rec.get("any_changed"):
            claim_ledger = parsed["claim_ledger"] = recited_led
            sync_selected_fact_plan_required_ids(parsed, runtime_payload, allowed_fact_ids)
            write_json(artifact_dir / "headline_bundle_recitation_receipt.json", bundle_rec)
            if isinstance(cl := parsed.setdefault("change_log", []), list):
                cl.append({"operation": "recite_canonical_segments_to_bundle_facts", "reason": "canonical positioning segments re-cited to registry linked_source_fact_ids", "receipt_ref": "headline_bundle_recitation_receipt.json"})
    if isinstance(parsed, dict) and claim_ledger and headline_line:
        rep_led, rec_rec = repair_headline_segment_citations_for_grounding(headline_line=headline_line, parsed_output=parsed, claim_ledger=claim_ledger)
        if rec_rec.get("any_changed"):
            claim_ledger = parsed["claim_ledger"] = rep_led
            write_json(artifact_dir / "headline_segment_recitation_receipt.json", rec_rec)
            if isinstance(cl := parsed.setdefault("change_log", []), list):
                cl.append({"operation": "repair_headline_segment_citations_for_grounding", "reason": "Model mis-cited segments to facts with zero shared content nouns", "receipt_ref": "headline_segment_recitation_receipt.json"})
    if fid_rec is not None:
        write_json(artifact_dir / "headline_fact_id_resolution_receipt.json", fid_rec)
    if runtime_generation_status in HEADLINE_JSON_OUTPUT_STATUSES and parsed_raw_pre_normalize is not None:
        first_ok, first_det, first_obs = validate_raw_headline_claim_ledger(attempt1_pre_norm) if attempt1_pre_norm is not None else (True, "", None)
        final_ok, raw_det, raw_obs = validate_raw_headline_claim_ledger(parsed_raw_pre_normalize)
        if not first_ok or not final_ok or proof_retry_attempted:
            r_classes = (["normalize_claim_ledger_string_fact_ids"] if not first_ok and first_det == "claim_ledger_flat_string_fact_ids_invalid" else (["lane_normalize_claim_ledger"] if not first_ok else [])) + (["headline_proof_shape_retry_llm"] if proof_retry_attempted else [])
            tc_retry = str(args.target_company or "")
            f_sc_ok = (not snapshot_needs_headline_proof_retry(attempt1_pre_norm, target_company=tc_retry, employer_names_lower=employer_names)[0]) if attempt1_pre_norm is not None else None
            fin_sc_ok = not snapshot_needs_headline_proof_retry(parsed_raw_pre_normalize, target_company=tc_retry, employer_names_lower=employer_names)[0]
            r_tag = "word_count_self_check_mismatch" if ("word_count" in proof_retry_reason and "runtime" in proof_retry_reason) else ("flat_string_claim_ledger_shape" if proof_retry_reason == "claim_ledger_flat_string_fact_ids_invalid" else (proof_retry_reason or "unknown"))
            repair_receipt = {"section_id": "headline", "run_id": runtime_payload["run_id"], "retry_attempted": proof_retry_attempted, "first_attempt_raw_schema_valid": first_ok, "final_raw_model_schema_valid": final_ok, "raw_model_schema_valid": final_ok, "raw_schema_failure_code": raw_det if not final_ok else (first_det if not first_ok else None), "first_attempt_claim_ledger": attempt1_pre_norm.get("claim_ledger") if attempt1_pre_norm else None, "final_snapshot_claim_ledger": parsed_raw_pre_normalize.get("claim_ledger"), "raw_observation": raw_obs if not final_ok else first_obs, "proof_eligible_repair": False, "proof_eligible_repair_semantics": "false means retries did not fabricate proof-eligibility via a non-schema-compliant shortcut; post-run proof eligibility is recorded separately as proof_eligible_after_retry.", "first_attempt_self_check_consistent": f_sc_ok, "final_self_check_consistent": fin_sc_ok, "retry_reason": r_tag if proof_retry_attempted else None, "retry_policy": "same_authority_headline_proof_shape_retry" if proof_retry_attempted else None, "repair_did_not_mask_raw_schema_failure": bool(final_ok), "deterministic_repair_classes": r_classes or ["headline_proof_accounting"], "note": "Normalized headline artifacts may coerce invalid raw shapes; proof-eligible REAL_RUNTIME requires final raw model snapshot PASS after optional same-authority retry."}
    model_name = (provider_result_data or {}).get("model") or (provider_request_data or {}).get("model")
    _wg.write_text(artifact_dir / "raw_model_output.txt", raw_output or "", encoding="utf-8")
    parse_status, invalid_reason = classify_ledger_parse_state(parsed, parse_error=parse_error, raw_output=raw_output or "", lane_profile="headline")
    canon_doc = build_headline_canonical_claim_ledger_v2(normalize_headline_claim_ledger(claim_ledger) if parse_status == "OK" else [], parse_status=parse_status, invalid_reason=invalid_reason if parse_status != "OK" else None)
    write_json(artifact_dir / "parsed_output.json", {"parsed": ({k: v for k, v in parsed.items() if k != "_headline_ledger_rows_dropped"} if isinstance(parsed, dict) else parsed), "parse_error": parse_error, "parse_status": parse_status})
    write_json(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)
    coverage = build_headline_text_claim_coverage(headline_line or "", claim_ledger, allowed_fact_ids)
    write_json(artifact_dir / "text_claim_coverage.json", coverage)
    effective_sfp_h = parsed.get("selected_fact_plan") if isinstance(parsed, dict) and isinstance(parsed.get("selected_fact_plan"), dict) else selected_fact_plan
    write_json(artifact_dir / "selected_fact_plan.json", effective_sfp_h)
    req_id_h = str((provider_request_data or {}).get("request_id") or (provider_request_data or {}).get("id") or runtime_payload["run_id"])
    from apps_rg.runtime.c0 import section_proof_loader as _spl
    from apps_rg.runtime import section_l2_lane_integration as _sli
    from apps_rg.runtime import section_runtime_exhaust_lane_integration as _sreli
    from apps_rg.runtime import section_one_spine_certification_lane_integration as _soscli
    trace_rr_h = _hl_override("rel_posix", rel_posix)(artifact_dir, repo_root)
    usage_doc = build_section_input_usage_ledger_v1(section_id="headline", run_id=str(runtime_payload["run_id"]), request_id=req_id_h, trace_root=trace_rr_h, repo_root=repo_root, artifact_dir=artifact_dir, runtime_payload=runtime_payload, selected_fact_plan=effective_sfp_h, claim_ledger=claim_ledger, allowed_fact_ids=allowed_fact_ids, jd_text=str(runtime_payload.get("jd_text") or ""), target_title=str(runtime_payload.get("target_title") or ""), target_company=str(runtime_payload.get("target_company") or ""), briefing_text=str(runtime_payload.get("briefing") or ""), jd_alignment=(parsed or {}).get("jd_alignment") if isinstance(parsed, dict) else None)
    write_json(artifact_dir / "section_input_usage_ledger.json", _spl.apply_proof_pool_to_usage_ledger(usage_doc, pool))
    parsed_for_x2: dict[str, Any] = {**(parsed or {}), "text_claim_coverage": coverage}
    judge_keys = [j.strip() for j in args.x1d_judges.split(",") if j.strip()]
    judge_allowed_mock = bool(args.mock_judges and getattr(args, "allow_test_mock_judges", False))
    judge_mode = "mocked" if judge_allowed_mock else "blocked_if_unavailable"
    allowed_fact_packet = build_headline_allowed_fact_packet(selected_fact_plan=effective_sfp_h, proof_pool_ref=str(pool.proof_pool_ref or ""), proof_pool_digest=str(pool.proof_pool_digest or ""))
    raw_output_for_x2 = json.dumps(parsed_for_x2, ensure_ascii=False, separators=(",", ":")) if ("```" in raw_output and isinstance(parsed_for_x2, dict)) else raw_output
    pre_judge_hl = headline_line
    headline_line, claim_ledger, canon_doc, coverage, x1d = execute_headline_judges_with_final_display_gate(headline_line=headline_line, parsed=parsed if isinstance(parsed, dict) else None, parsed_for_x2=parsed_for_x2, claim_ledger=claim_ledger, canon_doc=canon_doc, coverage=coverage, allowed_fact_ids=allowed_fact_ids, proof_pool_metadata=proof_pool_metadata if isinstance(proof_pool_metadata, dict) else None, runtime_payload=runtime_payload, judge_keys=judge_keys, companion_context=companion_context, judge_mode=judge_mode, judge_allowed_mock=judge_allowed_mock, artifact_dir=artifact_dir, allowed_fact_packet=allowed_fact_packet, target_title=str(args.target_title or ""), target_company=str(args.target_company or ""), word_min=HEADLINE_WORD_MIN, word_max=HEADLINE_WORD_MAX, word_count_fn=headline_word_count, has_valid_prefix_fn=has_valid_headline_prefix, clarity_report_fn=headline_resume_native_clarity_report, evaluate_grounding_fn=evaluate_headline_literal_grounding, coerce_segment_ledger_fn=coerce_segment_claim_ledger_rows, recite_bundle_fn=recite_canonical_segments_to_bundle_facts, repair_grounding_fn=repair_headline_segment_citations_for_grounding, normalize_ledger_fn=normalize_headline_claim_ledger, build_canon_fn=build_headline_canonical_claim_ledger_v2, build_coverage_fn=build_headline_text_claim_coverage, run_judges_fn=_hl_override("run_headline_judges", run_headline_judges), write_json_fn=write_json)
    if headline_line != pre_judge_hl:
        usage_doc = build_section_input_usage_ledger_v1(section_id="headline", run_id=str(runtime_payload["run_id"]), request_id=req_id_h, trace_root=trace_rr_h, repo_root=repo_root, artifact_dir=artifact_dir, runtime_payload=runtime_payload, selected_fact_plan=effective_sfp_h, claim_ledger=claim_ledger, allowed_fact_ids=allowed_fact_ids, jd_text=str(runtime_payload.get("jd_text") or ""), target_title=str(runtime_payload.get("target_title") or ""), target_company=str(runtime_payload.get("target_company") or ""), briefing_text=str(runtime_payload.get("briefing") or ""), jd_alignment=(parsed or {}).get("jd_alignment") if isinstance(parsed, dict) else None)
        write_json(artifact_dir / "section_input_usage_ledger.json", _spl.apply_proof_pool_to_usage_ledger(usage_doc, pool))
        if "```" in raw_output and isinstance(parsed_for_x2, dict):
            raw_output_for_x2 = json.dumps(parsed_for_x2, ensure_ascii=False, separators=(",", ":"))
    write_json(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": x1d})
    pp_x2 = runtime_payload.get("proof_pool_metadata") or {}
    _, srfs_slice_x2_active = x2_proof_pool_gate_flags(pp_x2)
    x2 = [g.to_dict() for g in run_headline_x2_gates(headline_line=headline_line, parsed_output=parsed_for_x2, claim_ledger=claim_ledger, jd_text=args.jd_text, target_company=args.target_company, target_title=args.target_title, resume_support_blob=resume_blob, employer_names_lower=employer_names, allowed_fact_ids=allowed_fact_ids, runtime_generation_status=runtime_generation_status, provider_requested=args.provider, provider_attempted=args.provider, model_name=model_name, raw_output=raw_output_for_x2, x1d_judges=x1d, companion_context=companion_context, candidate_name_tokens=candidate_name_tokens, raw_model_parsed_before_normalize=parsed_raw_pre_normalize, reasoning_execution_receipt=reasoning_receipt, artifacts_dir=artifact_dir, text_claim_coverage=coverage, srfs_source_fact_slice_gate_active=srfs_slice_x2_active, proof_pool_metadata=pp_x2, proof_pool_ref=str(pool.proof_pool_ref or ""), proof_pool_digest=str(pool.proof_pool_digest or ""))]
    for g in x2:
        if isinstance(obs := g.get("observed_value"), dict) and obs.get("x2_source_fact_pool_status"):
            write_x2_source_fact_pool_receipt(artifact_dir, obs)
            break
    reasoning_summary = summarize_reasoning_receipt_for_bundle(reasoning_receipt)
    jd_fallback: dict[str, Any] = {"targeting_only": True, "jd_used_as_proof": False, "briefing_used_as_proof": False, "selected_theme": "base_resume_aligned", "anti_stuffing_check": "passed", **({"companion_used_as_proof": False} if companion_nonempty else {})}
    if isinstance(parsed, dict):
        parsed.pop("_headline_ledger_rows_dropped", None)
    l2_output = {"run_id": runtime_payload["run_id"], "section_id": "headline", "runtime_generation_status": runtime_generation_status, "product_quality_status": "PENDING", "headline_line": headline_line, "selected_fact_plan": (parsed or {}).get("selected_fact_plan") or selected_fact_plan, "claim_ledger": claim_ledger, "jd_alignment": (parsed or {}).get("jd_alignment") or jd_fallback, "gap_notes": (parsed or {}).get("gap_notes") or [], "change_log": (parsed or {}).get("change_log") or [], "self_check": (parsed or {}).get("self_check") or {"parse_error": parse_error}, "prompt_id": PROMPT_ID, "prompt_hash": prompt_hash, "section_prompt_adapter": True, "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref, "compiler_template_id": section_compiled.artifact.template_id, "input_payload_hash": input_payload_hash, "reasoning_execution_receipt_summary": reasoning_summary, "raw_model_claim_ledger_schema_valid": _x2_gate_pass(x2, "x2_headline_raw_model_schema_valid"), "normalized_headline_schema_valid": _x2_gate_pass(x2, "x2_headline_schema_valid"), "self_check_consistent": _x2_gate_pass(x2, "x2_headline_self_check_consistent"), "prompt_reasoning_receipt_clean": _x2_gate_pass(x2, "x2_headline_prompt_reasoning_receipt_clean"), "text_claim_coverage": coverage}
    if isinstance(_raw_jd := ((parsed or {}).get("raw_jd_alignment") if isinstance(parsed, dict) else None), dict):
        l2_output["raw_jd_alignment"] = dict(_raw_jd)
    _wg.write_text(artifact_dir / "headline_output.txt", headline_line + "\n", encoding="utf-8")
    write_json(artifact_dir / "claim_ledger.json", claim_ledger)
    write_json(artifact_dir / "prompt_selection_trace.json", attach_reasoning_to_prompt_trace({"runtime_path": trace_runtime_path, "prompt_id": PROMPT_ID, "provider": args.provider, "temperature": args.temperature, "section_prompt_adapter": True, "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref, "compiler_template_id": section_compiled.artifact.template_id}, provider=args.provider, lane_key=LANE_KEY, provider_result_data=provider_result_data if isinstance(provider_result_data, dict) else None))
    write_x2_gate_outputs(artifact_dir / "x2_gate_outputs.json", x2, section_id="headline")
    hl_ledger = load_ledger(artifact_dir) or {}
    record_x2_run(artifact_dir, run_number=len(list(hl_ledger.get("x2_runs") or [])) + 1, after_l2_source=str(hl_ledger.get("authoritative_l2_source") or "initial_llm"), x2_gates=x2)
    rep_ok = proof_retry_attempted or cs_accepted or fmt_accepted or any(r.get("kind") == "regen_llm" and r.get("replaced_l2") for r in list(hl_ledger.get("repairs") or []))
    if rep_ok and not [g for g in x2 if not g.get("pass")]:
        set_authoritative_attempt(artifact_dir, 2, reason="headline_proof_shape_retry_x2_pass" if proof_retry_attempted else ("headline_format_repair_x2_pass" if fmt_accepted else "headline_content_signal_repair_x2_pass"))
    write_json(artifact_dir / "fact_check_result.json", {"passed": not [g for g in x2 if not g["pass"]], "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]]})
    pq_status, pq_reason = infer_product_quality(runtime_generation_status, x2, artifact_dir=artifact_dir)
    x3 = _aggregate_headline_x3(resume_display_text=headline_line or raw_output, claim_ledger=claim_ledger, x2_gates=x2, x1d_judges=x1d, runtime_generation_status=runtime_generation_status, product_quality_status=pq_status, canonical_claims_for_hash=canon_doc.get("claims"), section_input_usage_ledger=usage_doc)
    bundle = headline_proof_bundle_labels(compute_lane_proof_bundle(args, section_id="headline", runtime_generation_status=runtime_generation_status, x1d_judges=x1d, x2_gates=x2, x3=x3))
    if repair_receipt is not None:
        repair_receipt["proof_eligible_after_retry"] = bool(bundle.get("proof_eligible"))
        write_json(artifact_dir / "repair_receipt.json", repair_receipt)
    manifest_acc = {"decisive_accounting_label": "X3_ALLOW_REAL_LLM_ALL_JUDGES_MODEL_BACKED_PASS", "generation_class": "REAL_LLM", "judge_class": "ALL_REQUIRED_MODEL_BACKED_PASS", "proof_class": "PROOF_ELIGIBLE", "certification_class": "SIGNED_OFF"} if (bool(bundle.get("proof_eligible")) and str(bundle.get("runtime_certification") or "") == "SIGNED_OFF" and runtime_generation_status == "REAL_LLM" and x3.x3_code == "X3_ALLOW" and bool(x3.pass_) and not (x3.mocked_judges or []) and not (x3.blocked_judges or [])) else {}
    l2_output["product_quality_status"], l2_output["product_quality_reason"] = pq_status, pq_reason
    attach_ledger_summary_to_l2(l2_output, artifact_dir)
    attach_lane_proof_bundle_fields(l2_output, runtime_generation_status=runtime_generation_status, bundle=bundle)
    write_json(artifact_dir / "l2_output.json", l2_output)
    x3 = finalize_section_lane_x3(artifact_dir=artifact_dir, section_id="headline", runtime_payload=runtime_payload, x3_result=x3)
    _sli.finalize_section_l2_after_output(artifact_dir, "headline", runtime_payload)
    _sreli.finalize_section_runtime_exhaust_before_l6(artifact_dir, "headline", runtime_payload, repo_root=repo_root)
    smr_h = {"run_id": runtime_payload["run_id"], "lane_id": "headline", "prompt_id": PROMPT_ID, "prompt_hash": prompt_hash, "input_payload_hash": input_payload_hash, "output_payload_hash": (parsed_for_x2 or {}).get("output_payload_hash"), "claim_ledger_hash": (parsed_for_x2 or {}).get("claim_ledger_hash"), "runtime_generation_status": runtime_generation_status, "product_quality_status": pq_status, "x2_failed_gates": [g["gate_id"] for g in x2 if not g["pass"]], "x3_code": x3.x3_code, "proof_eligible": bundle["proof_eligible"], "judge_proof_eligible": bundle["judge_proof_eligible"], "proof_authority_receipt": {"proof_authority": "graph_skills_plus_linked_source_facts", "base_resume_usage": "calibration_only", "jd_usage": "targeting_only", "e0_usage": "style_only", "new_gates_wired": ["x2_headline_no_narrowing_it_labels", "x2_headline_positioning_family_preserved", "x2_headline_e0_ngram_overlap", "x2_headline_base_ngram_overlap"]}}
    merge_graph_evidence_reporting_into_dict(smr_h, section_id="headline", runtime_payload=runtime_payload, x2_gates=x2, selected_fact_plan=l2_output.get("selected_fact_plan"), claim_ledger=claim_ledger)
    smr_h.update(headline_fact_namespace_metric_fields(parsed, fid_rec))
    write_json(artifact_dir / "section_metric_receipt.json", smr_h)
    _sreli.gate_section_l6_shadow_after_exhaust(artifact_dir, runtime_payload)
    l6 = build_l6_shadow_package(artifact_dir=artifact_dir, repo_root=repo_root, prompt_id=PROMPT_ID, temperature=float(args.temperature), max_tokens=HEADLINE_MAX_OUTPUT_TOKENS)
    write_json(artifact_dir / "l6_shadow_eval_package.json", l6)
    obs_failures = [g["gate_id"] for g in x2 if not g["pass"]]
    ledger_fact_union = sorted({str(fid).split("_metric_")[0] for row in claim_ledger if isinstance(row, dict) for fid in (row.get("source_fact_ids") or [])})
    jd_scan = (parsed.get("raw_jd_alignment") if isinstance(parsed, dict) and isinstance(parsed.get("raw_jd_alignment"), dict) else (parsed.get("jd_alignment") if isinstance(parsed, dict) else None)) or {}
    proof_misuse = [k for flag, k in (("jd_used_as_proof", "model_claimed_jd_used_as_proof"), ("briefing_used_as_proof", "model_claimed_briefing_used_as_proof"), ("companion_used_as_proof", "model_claimed_companion_used_as_proof")) if isinstance(jd_scan, dict) and jd_scan.get(flag) is True]
    _hl_override("emit_headline_l6_shadow_learning_outputs", emit_headline_l6_shadow_learning_outputs)(repo_root=repo_root, artifact_dir=artifact_dir, handoff_pkt=l6, prompt_hash=prompt_hash, final_headline_line=headline_line, x2_passed=not obs_failures, x3_record=x3.to_dict(), observed_failures=obs_failures, support_coverage_findings=[f"claim_ledger_fact_union={ledger_fact_union}", f"candidate_fact_pool_size={len(candidate_pool_ids)}"], proof_misuse_findings=proof_misuse, banned_content_findings=[], phrasing_quality_findings=[], future_run_recommendations=(["repair_claim_ledger_and_proof_alignment"] if obs_failures else []), prompt_control_receipt_findings=_x2_gate_failure_detail(x2, "x2_headline_prompt_reasoning_receipt_clean"), raw_schema_findings=_x2_gate_failure_detail(x2, "x2_headline_raw_model_schema_valid"), self_check_findings=_x2_gate_failure_detail(x2, "x2_headline_self_check_consistent"), l2_output_ref=repo_rel(repo_root.resolve(), artifact_dir.resolve() / "l2_output.json"), reasoning_execution_receipt_summary=reasoning_summary)
    rl2 = {"provider_attempted": args.provider, "runtime_generation_status": runtime_generation_status, "prompt_hash": prompt_hash, "model": model_name, "raw_model_output": raw_output, "raw_model_output_provider": provider_raw_output, "product_quality_status": pq_status, "x3_code": x3.x3_code}
    attach_lane_proof_bundle_fields(rl2, runtime_generation_status=runtime_generation_status, bundle=bundle)
    write_json(artifact_dir / "real_l2_generation_result.json", rl2)
    lines = ["HEADLINE_OUTPUT:", headline_line or f"BLOCKED: {parse_error}", "", f"WORD_COUNT: {headline_word_count(headline_line)}", "", "X1D_LLM_JUDGE_OUTPUTS:", "| Provider | Mode | Status | Score | Pass | Decisive Failure |", "|---|---|---|---:|---|---|", *[f"| {j['provider_name']} | {j['evaluator_mode']} | {j.get('provider_status')} | {j.get('score')} | {j.get('pass')} | {j.get('decisive_failure')} |" for j in x1d], "", "X2_DETERMINISTIC_GATE_OUTPUTS:", *[f"- {g['gate_id']}: {'PASS' if g['pass'] else 'FAIL'}" for g in x2], "", "X3_DISPOSITION:", json.dumps(x3.to_dict(), indent=2), "", "L6_SHADOW_EVAL_PACKAGE:", str(artifact_dir / "l6_shadow_eval_package.json"), "offline_only=true"]
    output_text = "\n".join(lines)
    _wg.write_text(artifact_dir / "command_output.txt", output_text + "\n", encoding="utf-8")
    if print_output:
        print(output_text)
    _soscli.finalize_section_one_spine_certification(artifact_dir, "headline", runtime_payload, proof_bundle=bundle, runtime_generation_status=runtime_generation_status)
    _hl_override("finalize_runtime_proof_run", finalize_runtime_proof_run)(repo_root, LANE_KEY, args.provider, artifact_dir, run_id=runtime_payload["run_id"], section_id="headline", runtime_generation_status=runtime_generation_status, provider_requested=str((provider_request_data or {}).get("provider_requested", args.provider)), provider_attempted=(provider_request_data or {}).get("provider_attempted", args.provider), command=" ".join(sys.argv), bundle_proof_strict=bool(bundle.get("proof_eligible")) and proof_bucket_for_provider(args.provider) == "real", proof_eligible=bundle["proof_eligible"], proof_scope=bundle["proof_scope"], test_only_mock_provider=bundle["test_only_mock_provider"], runtime_certification=bundle["runtime_certification"], x1d_runtime_status=bundle["x1d_runtime_status"], judge_proof_eligible=bundle["judge_proof_eligible"], provider_proof_eligible=bundle["provider_proof_eligible"], test_only_mock_judges=bundle["test_only_mock_judges"], proof_closeout_note=bundle["proof_closeout_note"] if bundle.get("proof_closeout_note") else None, **manifest_acc)
    _emit_headline_final_evidence_reports(artifact_dir, run_id=runtime_payload["run_id"], x2_gates=x2, x3_record=x3.to_dict(), reasoning_summary=reasoning_summary, proof_bundle=bundle)
    exit_code = 0 if allow_non_allow_exit_zero_ok(args) else (0 if x3.x3_code == "X3_ALLOW" else 2)
    return {"artifact_dir": artifact_dir, "repo_root": repo_root, "lane_key": LANE_KEY, "runtime_payload": runtime_payload, "x3": x3, "output_text": output_text, "exit_code": exit_code, "runtime_generation_status": runtime_generation_status}
