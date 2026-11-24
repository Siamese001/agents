"""Canonical 15-artifact contract emitter & unified runner for role_narrative_v2."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from typing import Any
from apps_rg.runtime.c0.resume_graph_claim_binding import merge_resume_graph_claim_binding_fields
from apps_rg.runtime.c0.section_proof_loader import apply_proof_pool_to_usage_ledger, load_section_proof_for_lane
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import build_canonical_claim_ledger_v2_payload, classify_ledger_parse_state, normalize_exec_summary_claim_ledger
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.exit.ibm_narrative_x3 import aggregate_x3 as _aggregate_ibm_narrative_x3
from apps_rg.runtime.exit.unify_narrative_x3 import aggregate_x3 as _aggregate_unify_narrative_x3
from apps_rg.runtime.ibm_narrative_judge_preflight import run_ibm_narrative_judge_credentials_preflight
from apps_rg.runtime.ibm_narrative_proof_accounting import build_clean_x3_allow_readiness_document, classify_certification_class, classify_generation_class, classify_judge_class, classify_proof_class, compute_decisive_accounting_label
from apps_rg.runtime.judges.ibm_narrative_x1d import JUDGE_RUBRIC_VERSION as _IBM_NARR_RUBRIC_VERSION, run_ibm_narrative_judges
from apps_rg.runtime.product_evidence_authority import x2_proof_pool_gate_flags
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.providers.section_provider_call import call_section_model_provider
from apps_rg.runtime.runtime_proof_layout import finalize_runtime_proof_run, prepare_runtime_proof_run_dir, rel_posix, resolve_effective_lane_l2_path
from apps_rg.runtime.section_judge_policy import get_section_judge_policy
from apps_rg.runtime.section_l2_lane_integration import finalize_section_l2_after_output, prepare_section_l2_before_provider
from apps_rg.runtime.section_model_limits import external_claude_generation_model, external_openai_generation_model
from apps_rg.runtime.section_one_spine_certification_lane_integration import finalize_section_one_spine_certification
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import allow_non_allow_exit_zero_ok, attach_lane_proof_bundle_fields, compute_lane_proof_bundle
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.section_repair_ledger import KIND_REGEN_LLM, attach_ledger_summary_to_l2, init_ledger, load_ledger, record_repair, record_x2_run, set_authoritative_attempt
from apps_rg.runtime.section_runtime_exhaust_lane_integration import finalize_section_runtime_exhaust_before_l6, gate_section_l6_shadow_after_exhaust
from apps_rg.runtime.sections import graph_evidence_contract as _graph_evidence
from apps_rg.runtime.sections.executive_summary_lane import resolve_provider_model_name, write_x2_gate_outputs
from apps_rg.runtime.sections.graph_evidence_contract import merge_graph_evidence_reporting_into_dict
from apps_rg.runtime.sections.lane_perf_sync_helpers import build_blocked_pre_judge_rows
from apps_rg.runtime.sections.prompt_trace_reasoning import attach_reasoning_to_prompt_trace
from apps_rg.runtime.sections.resume_employment_bullets import collect_employment_bullets
from apps_rg.runtime.sections.section_generation import build_section_request, generate_section, merge_transport_context, tag_reasoning_lane
from apps_rg.runtime.sections.unify_role_episode_evidence import UNIFY_BULLET_SLOT_BUNDLE_MAP
from apps_rg.runtime.sections.upstream_evidence_block import wire_spine_c0_fec_or_block
from apps_rg.runtime.shadow.ibm_narrative_l6 import build_l6_shadow_package as _build_ibm_l6
from apps_rg.runtime.shadow.l6_shadow_learning import build_l6_shadow_learning_record
from apps_rg.runtime.shadow.unify_narrative_l6 import build_l6_shadow_package as _build_unify_l6
from apps_rg.runtime.spine.c0_fec_compose import merge_compiled_prompt_artifact_fec_fields
from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3
from apps_rg.runtime.validators.companion_bullet_finalization import UPSTREAM_NOT_FINALIZED_RUNTIME_STATUS, companion_blocks_narrative_llm
from apps_rg.runtime.validators.executive_summary_x2 import build_sentence_claim_coverage
from apps_rg.runtime.validators.ibm_narrative_x2 import run_ibm_narrative_x2_gates
from apps_rg.runtime.validators.proof_pool_source_fact_validation import write_x2_source_fact_pool_receipt
from apps_rg.runtime.validators.unify_narrative_x2 import run_unify_narrative_x2_gates
from .blind_judge_and_loop import apply_ibm_narrative_judge_feedback_rewrite, run_unify_narrative_v2_healing_loop
from .employer_specs import get_employer_narrative_spec
from .evidence_firewall import BRIEFING_DEFAULT, JD_TEXT_DEFAULT, REPO_ROOT, TARGET_COMPANY_DEFAULT, TARGET_TITLE_DEFAULT, build_narrative_runtime_payload, build_narrative_selected_fact_plan, extract_employer_employment, load_companion_bullets_context, sha16, write_json
from .prompt_and_generate import compile_narrative_v2_prompt, normalize_ibm_narrative_parsed, normalize_unify_narrative_parsed, parse_narrative_model_json, shell_jd_alignment
from .x2_invariants import companion_bullets_as_list, cosine_echo_diagnostic_summary, enrich_unify_narrative_parsed_for_x2, infer_narrative_product_quality, pre_judge_failed_gate_ids

def run_role_narrative_v2(
    section_id: str, args: argparse.Namespace | Any, *, artifact_dir_override: Path | None = None,
    trace_runtime_path: str | None = None, print_output: bool = False, repo_root_override: Path | None = None,
) -> dict[str, Any]:
    spec = get_employer_narrative_spec(section_id)
    if spec.uses_role_episode_pipeline:
        from apps_rg.runtime.sections.role_episode_lane import _run_role_episode_pipeline_internal
        return _run_role_episode_pipeline_internal(section_id, args, artifact_dir_override=artifact_dir_override)
    repo_root = repo_root_override or REPO_ROOT
    pool, base, base_path, base_hash, front_spine = load_section_proof_for_lane(section_id=section_id, args=args, repo_root=repo_root, collect_employment_bullets_fn=collect_employment_bullets)
    candidate_name = str(base.get("candidate_name") or (base.get("header") or {}).get("name") or "").strip()
    emp_header, canon_bullets, canon_allowed = extract_employer_employment(base, employer_match=spec.employer_match_substring, default_fact_id=spec.default_employment_fact_id, base_narrative_fact_id=spec.base_narrative_fact_id)
    plan_facts = [_graph_evidence.plan_fact_to_employment_bullet_row(f) for f in pool.selected_fact_plan.get("facts", [])]
    if section_id == "unify_narrative":
        selected_fact_plan = build_narrative_selected_fact_plan(section_id, plan_facts, role_narrative=str(emp_header.get("role_narrative") or ""), employment_fact_id=str(emp_header.get("fact_id") or spec.default_employment_fact_id))
        allowed_fact_ids = set(pool.allowed_fact_ids) | {str(fid).strip() for fid in canon_allowed if str(fid).strip().startswith("bul_unify_")}
    else:
        plan_facts.sort(key=lambda r: spec.canonical_bullet_ids.index(r["fact_id"]) if r.get("fact_id") in spec.canonical_bullet_ids else 99)
        selected_fact_plan, allowed_fact_ids = {**pool.selected_fact_plan, "facts": plan_facts}, set(pool.allowed_fact_ids) | set(canon_allowed)
    companion_context = load_companion_bullets_context(section_id, repo_root=repo_root)
    companion_text = str(companion_context.get("text") or "")
    ibm_l2 = resolve_effective_lane_l2_path(repo_root, "ibm_bullets") if section_id == "ibm_narrative" else None
    companion_ref = (rel_posix(ibm_l2, repo_root) if ibm_l2 is not None and companion_text else companion_context.get("l2_ref")) if section_id == "ibm_narrative" else (companion_context.get("l2_ref") if companion_text else None)
    runtime_payload = build_narrative_runtime_payload(section_id, base_json_path=base_path, base_hash=base_hash, header=emp_header, selected_fact_plan=selected_fact_plan, allowed_fact_ids=allowed_fact_ids, companion_bullets_ref=companion_ref, companion_bullets_status=str(companion_context.get("status") or "UNKNOWN"), companion_bullets_reason=str(companion_context.get("reason") or ""), companion_bullet_ids=list(companion_context.get("bullet_ids") or []), companion_x3_code=str(companion_context.get("x3_code") or "UNKNOWN"), companion_product_quality_status=str(companion_context.get("product_quality_status") or "UNKNOWN"), target_title=str(getattr(args, "target_title", "") or "").strip() or TARGET_TITLE_DEFAULT, target_company=str(getattr(args, "target_company", "") or "").strip() or TARGET_COMPANY_DEFAULT, jd_text=str(getattr(args, "jd_text", "") or "").strip() or JD_TEXT_DEFAULT, briefing=str(getattr(args, "briefing", "") or "").strip() or BRIEFING_DEFAULT, candidate_name=candidate_name, repo_root=repo_root)
    runtime_payload["proof_pool_metadata"] = pool.proof_pool_metadata
    if focus := str(getattr(args, "diagnostic_focus", "") or "").strip():
        runtime_payload["recovery_diagnostic_focus"] = focus
    artifact_dir = Path(artifact_dir_override) if artifact_dir_override is not None else prepare_runtime_proof_run_dir(repo_root, section_id, args.provider, runtime_payload["run_id"])
    _wg.ensure_dir(artifact_dir)
    init_ledger(artifact_dir, section_id=section_id, run_id=str(runtime_payload["run_id"]))
    merge_transport_context(artifact_dir=str(artifact_dir.resolve()), run_id=str(runtime_payload.get("run_id") or ""))
    write_json(artifact_dir / f"companion_{spec.employer_key}_bullets_context.json", companion_context)
    _wg.write_text(artifact_dir / f"companion_{spec.employer_key}_bullets_context.txt", (companion_text or "(none)") + "\n", encoding="utf-8")
    if (blocked := wire_spine_c0_fec_or_block(repo_root=repo_root, artifact_dir=artifact_dir, section_id=section_id, front_spine=front_spine, pool=pool, runtime_payload=runtime_payload, provider=str(args.provider), temperature=float(args.temperature), max_tokens=spec.max_output_tokens, output_filename=spec.output_filename)) is not None:
        return blocked
    runtime_payload["allowed_fact_ids"] = sorted(set(runtime_payload.get("allowed_fact_ids") or []) | set(allowed_fact_ids))
    input_payload_hash = sha16(json.dumps(runtime_payload, sort_keys=True))
    section_compiled = compile_narrative_v2_prompt(section_id, runtime_payload, companion_text, run_id=runtime_payload["run_id"])
    messages = section_compiled.artifact.messages
    prompt_hash = sha16(json.dumps(messages, ensure_ascii=False, separators=(",", ":")))
    write_json(artifact_dir / "runtime_payload.json", runtime_payload)
    _wg.write_text(artifact_dir / "compiled_prompt.txt", json.dumps(messages, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_json(artifact_dir / "compiled_prompt_artifact.json", merge_compiled_prompt_artifact_fec_fields({"section_id": section_compiled.section_id, "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref, "compiler_template_id": section_compiled.artifact.template_id, "pa_prompt_hash": section_compiled.artifact.prompt_hash, "provider_prompt_hash": prompt_hash, "dispatch_sha256_prompt16": prompt_hash, "slot_count": section_compiled.artifact.slot_count, "allowed_fact_ids": list(runtime_payload.get("allowed_fact_ids") or [])}, runtime_payload))
    judge_keys = [j.strip() for j in str(getattr(args, "x1d_judges", "") or "").split(",") if j.strip()]
    if not judge_keys and section_id == "ibm_narrative":
        judge_keys = list(get_section_judge_policy("ibm_narrative").required_judge_providers)
    judge_allowed_mock = bool(getattr(args, "mock_judges", False) and (section_id == "unify_narrative" or getattr(args, "allow_test_mock_judges", False)))
    preflight_art: dict[str, Any] = {"skipped": True, "reason": "non_ibm_or_mock"}
    preflight_blocked = False
    if section_id == "ibm_narrative":
        from apps_rg.runtime.env_bootstrap import snapshot_process_env

        preflight_art = {"skipped": True, "reason": "mock_judge_cli_flags"} if judge_allowed_mock else dict(run_ibm_narrative_judge_credentials_preflight(judge_keys, snapshot_process_env()))
        preflight_blocked = bool(preflight_art.get("preflight_blocked"))
        write_json(artifact_dir / "ibm_narrative_judge_preflight.json", preflight_art)
    prepare_section_l2_before_provider(artifact_dir, section_id, runtime_payload, provider_lane=str(args.provider))
    section_model = external_openai_generation_model(section_id=section_id) if str(args.provider) == "external_openai" else external_claude_generation_model(section_id=section_id)
    provider_req, provider_payload = build_section_request(messages=messages, prompt_hash=prompt_hash, input_payload_hash=input_payload_hash, temperature=args.temperature, max_tokens=spec.max_output_tokens, temperature_bounds=spec.temp_range, model=section_model, provider_requested=str(args.provider), idempotent_replay_safe=True, reasoning_effort=getattr(args, "reasoning_effort", None), force_new_seed=bool(getattr(args, "force_new_seed", False)))
    provider_payload = tag_reasoning_lane(provider_payload, section_id)
    provider_request_data = provider_req.to_dict()
    write_json(artifact_dir / "provider_request.json", provider_request_data)
    req_model = str(provider_request_data.get("model") or section_model)
    upstream_blocked = companion_blocks_narrative_llm(companion_context)
    if upstream_blocked:
        preflight_blocked = False
    raw_output, parse_error, runtime_generation_status, parsed = "", "", "BLOCKED", None
    if upstream_blocked:
        parse_error, runtime_generation_status = f"upstream {spec.companion_bullet_lane} not finalized: {companion_context.get('status')}; {companion_context.get('reason')}", UPSTREAM_NOT_FINALIZED_RUNTIME_STATUS
        provider_result_data = {**ProviderResult(provider_requested=str(provider_req.provider_requested), provider_attempted=False, provider_available=False, exact_provider_error=parse_error, runtime_generation_status=runtime_generation_status, model=req_model, raw_model_output="", provider_response={"upstream_companion_blocked": True, "companion": companion_context}).to_dict(), "upstream_companion_blocked": True}
    elif preflight_blocked and not judge_allowed_mock:
        parse_error = "IBM narrative X1D judge credential preflight blocked narrative generation."
        provider_result_data = ProviderResult(provider_requested=str(provider_req.provider_requested), provider_attempted=bool(provider_req.provider_attempted), provider_available=False, exact_provider_error=parse_error, runtime_generation_status="BLOCKED", model=req_model, raw_model_output="", provider_response={"preflight_blocked": True, "preflight": preflight_art}).to_dict()
    else:
        result = call_section_model_provider(str(args.provider), provider_payload, artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""))
        raw_output, runtime_generation_status = result.raw_model_output, result.runtime_generation_status
        provider_result_data = {**result.to_dict(), "runtime_generation_status": runtime_generation_status}
        if runtime_generation_status in ("REAL_LLM", "MOCKED", "OFFLINE_CONTRACT_STUB"):
            parsed_in, parse_error = parse_narrative_model_json(raw_output)
            if parsed_in is not None:
                parsed = normalize_unify_narrative_parsed(parsed_in, runtime_payload, companion_text=companion_text, allow_prose_mutation=False) if section_id == "unify_narrative" else normalize_ibm_narrative_parsed(parsed_in, runtime_payload, companion_text=companion_text, allow_echo_repair=False)
        else:
            parse_error = result.exact_provider_error or "provider blocked"
    write_json(artifact_dir / "provider_response.json", provider_result_data)
    req_id = str(provider_request_data.get("request_id") or provider_request_data.get("id") or runtime_payload["run_id"])
    trace_rr = rel_posix(artifact_dir, repo_root)
    pp_x2 = runtime_payload.get("proof_pool_metadata") or {}
    _, srfs_slice_x2_active = x2_proof_pool_gate_flags(pp_x2)
    model_name = resolve_provider_model_name(provider_request_data, provider_result_data)
    temperature = float(args.temperature) if args.provider == "external_claude" else spec.temp_default
    ctx = locals()
    return _finalize_unify_narrative_v2(ctx) if section_id == "unify_narrative" else _finalize_ibm_narrative_v2(ctx)

def _finalize_unify_narrative_v2(ctx: dict[str, Any]) -> dict[str, Any]:
    args, spec, repo_root, artifact_dir, pool = ctx["args"], ctx["spec"], ctx["repo_root"], ctx["artifact_dir"], ctx["pool"]
    emp_header, canon_bullets, selected_fact_plan, allowed_fact_ids = ctx["emp_header"], ctx["canon_bullets"], ctx["selected_fact_plan"], ctx["allowed_fact_ids"]
    companion_context, companion_text, runtime_payload, input_payload_hash = ctx["companion_context"], ctx["companion_text"], ctx["runtime_payload"], ctx["input_payload_hash"]
    section_compiled, messages, prompt_hash, provider_payload = ctx["section_compiled"], ctx["messages"], ctx["prompt_hash"], ctx["provider_payload"]
    provider_request_data, provider_result_data, raw_output, parsed = ctx["provider_request_data"], ctx["provider_result_data"], ctx["raw_output"], ctx["parsed"]
    parse_error, runtime_generation_status, req_id, trace_rr = ctx["parse_error"], ctx["runtime_generation_status"], ctx["req_id"], ctx["trace_rr"]
    pp_x2, srfs_slice_x2_active, model_name, temperature, candidate_name, judge_keys = ctx["pp_x2"], ctx["srfs_slice_x2_active"], ctx["model_name"], ctx["temperature"], ctx["candidate_name"], ctx["judge_keys"]
    def _sync(cur_p: dict[str, Any] | None, cur_raw: str, cur_err: str) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any] | None, str, dict[str, Any]]:
        narr, led = str((cur_p or {}).get("narrative_sentence") or "").strip(), list((cur_p or {}).get("claim_ledger") or [])
        p_stat, inv_r = classify_ledger_parse_state(cur_p, parse_error=cur_err, raw_output=cur_raw, lane_profile="unify_narrative")
        c_doc = build_canonical_claim_ledger_v2_payload(normalize_exec_summary_claim_ledger(led) if p_stat == "OK" else [], parse_status=p_stat, invalid_reason=inv_r if p_stat != "OK" else None, claim_id_prefix="unify_narrative_claim")
        cov = build_sentence_claim_coverage(narr, led, allowed_fact_ids)
        px2 = enrich_unify_narrative_parsed_for_x2(cur_p, coverage=cov, input_payload_hash=input_payload_hash, allowed_fact_ids=allowed_fact_ids)
        raw_x2 = json.dumps(px2, ensure_ascii=False, separators=(",", ":")) if ("```" in cur_raw and isinstance(px2, dict)) else cur_raw
        ja_r = (cur_p or {}).get("jd_alignment")
        l2_doc = {"run_id": runtime_payload["run_id"], "section_id": "unify_narrative", "runtime_generation_status": runtime_generation_status, "product_quality_status": "PENDING", "product_quality_reason": "", "unify_header": emp_header, "companion_unify_bullets_context": companion_context, "narrative_sentence": narr, "selected_fact_plan": (cur_p or {}).get("selected_fact_plan") or selected_fact_plan, "claim_ledger": led, "jd_alignment": {**shell_jd_alignment(), **ja_r} if isinstance(ja_r, dict) else shell_jd_alignment(), "gap_notes": (cur_p or {}).get("gap_notes") or [], "change_log": (cur_p or {}).get("change_log") or [], "self_check": (cur_p or {}).get("self_check") or {"parse_error": cur_err}, "text_claim_coverage": cov, "prompt_id": spec.prompt_id, "prompt_hash": prompt_hash, "section_prompt_adapter": True, "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref, "compiler_template_id": section_compiled.artifact.template_id, "input_payload_hash": input_payload_hash, "output_payload_hash": (px2 or {}).get("output_payload_hash"), "claim_ledger_hash": (px2 or {}).get("claim_ledger_hash"), "allowed_fact_ids_hash": (px2 or {}).get("allowed_fact_ids_hash")}
        _wg.write_text(artifact_dir / "raw_model_output.txt", cur_raw or "", encoding="utf-8")
        write_json(artifact_dir / "parsed_output.json", {"parsed": cur_p, "parse_error": cur_err, "parse_status": p_stat})
        write_json(artifact_dir / "canonical_claim_ledger_v2.json", c_doc)
        write_json(artifact_dir / "l2_output.json", l2_doc)
        _wg.write_text(artifact_dir / "unify_narrative_output.txt", narr + "\n", encoding="utf-8")
        write_json(artifact_dir / "selected_fact_plan.json", l2_doc["selected_fact_plan"])
        write_json(artifact_dir / "claim_ledger.json", led)
        write_json(artifact_dir / "text_claim_coverage.json", cov)
        u_doc = build_section_input_usage_ledger_v1(section_id="unify_narrative", run_id=str(runtime_payload["run_id"]), request_id=req_id, trace_root=trace_rr, repo_root=repo_root, artifact_dir=artifact_dir, runtime_payload=runtime_payload, selected_fact_plan=l2_doc["selected_fact_plan"], claim_ledger=led, allowed_fact_ids=allowed_fact_ids, jd_text=str(runtime_payload.get("jd_text") or ""), target_title=str(runtime_payload.get("target_title") or ""), target_company=str(runtime_payload.get("target_company") or ""), briefing_text=str(runtime_payload.get("briefing") or ""), jd_alignment=l2_doc.get("jd_alignment"))
        write_json(artifact_dir / "section_input_usage_ledger.json", apply_proof_pool_to_usage_ledger(u_doc, pool))
        return narr, led, c_doc, cov, px2, raw_x2, l2_doc
    narrative, claim_ledger, canon_doc, coverage, parsed_for_x2, raw_output_for_x2, l2_output = _sync(parsed, raw_output, parse_error)
    judge_mode = "mocked" if getattr(args, "mock_judges", False) else "blocked_if_unavailable"
    compact_facts = [{"fact_id": f.get("fact_id"), "role_episode_bundle_id": f.get("role_episode_bundle_id"), "claim_text": f.get("claim_text"), "domain": f.get("domain"), "allowed_graph_evidence_ids": f.get("allowed_graph_evidence_ids"), "raw_chunk": str(f.get("raw_chunk") or "")[:1500]} for f in ((runtime_payload.get("selected_fact_plan") or {}).get("facts") or []) if isinstance(f, dict)]
    seen_fids = {str(f.get("fact_id") or "").strip() for f in compact_facts if str(f.get("fact_id") or "").strip()}
    comp_by_bid = {k.strip(): v.strip() for ln in str(companion_text or "").splitlines() if ":" in ln.strip().lstrip("-*").strip() for k, v in [ln.strip().lstrip("-*").strip().split(":", 1)] if k.strip().startswith("bul_unify_") and v.strip()}
    slot_map = (runtime_payload.get("proof_pool_metadata") or {}).get("unify_bullet_slot_bundle_map_resolved") or UNIFY_BULLET_SLOT_BUNDLE_MAP
    for c_row in canon_bullets:
        bid = str(c_row.get("fact_id") or "").strip() if isinstance(c_row, dict) else ""
        if bid and bid not in seen_fids and bid in allowed_fact_ids:
            seen_fids.add(bid)
            m_reb = str(slot_map.get(bid) or "").strip() if isinstance(slot_map, dict) else ""
            compact_facts.append({"fact_id": bid, "role_episode_bundle_id": m_reb or None, "claim_text": comp_by_bid.get(bid) or str(c_row.get("claim_text") or ""), "domain": c_row.get("domain") or "Unify Consulting finalized companion bullet", "allowed_graph_evidence_ids": [bid, *([m_reb] if m_reb else [])], "raw_chunk": str(c_row.get("claim_text") or "")[:1500]})
    def _pre_x2(cand_p: dict[str, Any], cand_px2: dict[str, Any]) -> list[dict[str, Any]]:
        return [g.to_dict() for g in run_unify_narrative_x2_gates(narrative_sentence=str(cand_p.get("narrative_sentence") or "").strip(), parsed_output=cand_px2, claim_ledger=list(cand_p.get("claim_ledger") or []), jd_text=runtime_payload["jd_text"], briefing_text=str(runtime_payload.get("briefing") or ""), runtime_generation_status=runtime_generation_status, companion_bullet_texts=companion_text or None, companion_bullets_status=str(companion_context.get("status") or "UNKNOWN"), companion_bullets_reason=str(companion_context.get("reason") or ""), candidate_name=candidate_name, provider_requested=args.provider, provider_attempted=args.provider, model_name=model_name, raw_output=json.dumps(cand_px2, ensure_ascii=False, separators=(",", ":")), x1d_judges=[], allowed_fact_ids=allowed_fact_ids, artifacts_dir=artifact_dir, srfs_source_fact_slice_gate_active=srfs_slice_x2_active, proof_pool_metadata=pp_x2, proof_pool_ref=str(pool.proof_pool_ref or ""), proof_pool_digest=str(pool.proof_pool_digest or ""))]
    raw_output, parsed, x1d, accepted = run_unify_narrative_v2_healing_loop(messages=messages, provider_payload=provider_payload, provider_name=str(args.provider), raw_output=raw_output, parsed=parsed, runtime_payload=runtime_payload, artifact_dir=artifact_dir, runtime_generation_status=runtime_generation_status, companion_text=companion_text, judge_keys=judge_keys, judge_mode=judge_mode, allowed_fact_packet={"allowed_fact_ids": sorted(str(x) for x in allowed_fact_ids), "facts": compact_facts}, targeting_context={"target_title": str(runtime_payload.get("target_title") or ""), "target_company": str(runtime_payload.get("target_company") or ""), "jd_text": str(runtime_payload.get("jd_text") or ""), "briefing": str(runtime_payload.get("briefing") or ""), "targeting_only": True}, run_x2_fn=_pre_x2, sync_artifacts_fn=lambda cp, cr: _sync(cp, cr, "")[4] or cp)
    if accepted and isinstance(parsed, dict):
        provider_result_data["raw_model_output"] = raw_output or ""
        write_json(artifact_dir / "provider_response.json", provider_result_data)
        narrative, claim_ledger, canon_doc, coverage, parsed_for_x2, raw_output_for_x2, l2_output = _sync(parsed, raw_output, "")
    write_json(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": x1d})
    write_json(artifact_dir / "prompt_selection_trace.json", attach_reasoning_to_prompt_trace({"runtime_path": ctx.get("trace_runtime_path") or "apps_rg.runtime.sections.unify_narrative_lane", "prompt_id": spec.prompt_id, "provider": args.provider, "temperature": temperature, "section_prompt_adapter": True, "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref, "compiler_template_id": section_compiled.artifact.template_id}, provider=args.provider, lane_key="unify_narrative", provider_result_data=provider_result_data))
    write_json(artifact_dir / "x3_disposition.json", {"x3_code": "PENDING", "status": "pending"})
    write_x2_gate_outputs(artifact_dir / "x2_gate_outputs.json", [], section_id="unify_narrative")
    x2 = [g.to_dict() for g in run_unify_narrative_x2_gates(narrative_sentence=narrative, parsed_output=parsed_for_x2, claim_ledger=claim_ledger, jd_text=runtime_payload["jd_text"], briefing_text=str(runtime_payload.get("briefing") or ""), runtime_generation_status=runtime_generation_status, companion_bullet_texts=companion_text or None, companion_bullets_status=str(companion_context.get("status") or "UNKNOWN"), companion_bullets_reason=str(companion_context.get("reason") or ""), candidate_name=candidate_name, provider_requested=args.provider, provider_attempted=args.provider, model_name=model_name, raw_output=raw_output_for_x2, x1d_judges=x1d, allowed_fact_ids=allowed_fact_ids, artifacts_dir=artifact_dir, srfs_source_fact_slice_gate_active=srfs_slice_x2_active, proof_pool_metadata=pp_x2, proof_pool_ref=str(pool.proof_pool_ref or ""), proof_pool_digest=str(pool.proof_pool_digest or ""))]
    for g in x2:
        if isinstance(obs := g.get("observed_value"), dict) and obs.get("x2_source_fact_pool_status"):
            write_x2_source_fact_pool_receipt(artifact_dir, obs)
            break
    write_x2_gate_outputs(artifact_dir / "x2_gate_outputs.json", x2, section_id="unify_narrative")
    u_led = load_ledger(artifact_dir) or {}
    record_x2_run(artifact_dir, run_number=len(list(u_led.get("x2_runs") or [])) + 1, after_l2_source=str(u_led.get("authoritative_l2_source") or "initial_llm"), x2_gates=x2)
    write_json(artifact_dir / "fact_check_result.json", {"passed": not [g for g in x2 if not g["pass"]], "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]]})
    pq_status, pq_reason = infer_narrative_product_quality("unify_narrative", runtime_generation_status, x2, artifact_dir=artifact_dir)
    usage_final = json.loads((artifact_dir / "section_input_usage_ledger.json").read_text(encoding="utf-8"))
    x3 = finalize_section_lane_x3(artifact_dir=artifact_dir, section_id="unify_narrative", runtime_payload=runtime_payload, defer_graph_binding_l2_persistence=True, aggregate_x3_fn=_aggregate_unify_narrative_x3, resume_display_text=narrative, claim_ledger=claim_ledger, x2_gates=x2, x1d_judges=x1d, runtime_generation_status=runtime_generation_status, product_quality_status=pq_status, canonical_claims_for_hash=canon_doc.get("claims"), section_input_usage_ledger=usage_final)
    proof_bundle = compute_lane_proof_bundle(args, section_id="unify_narrative", runtime_generation_status=runtime_generation_status, x1d_judges=x1d, x2_gates=x2, x3=x3)
    l2_output["product_quality_status"], l2_output["product_quality_reason"] = pq_status, pq_reason
    attach_ledger_summary_to_l2(l2_output, artifact_dir)
    attach_lane_proof_bundle_fields(l2_output, runtime_generation_status=runtime_generation_status, bundle=proof_bundle)
    l2_output = merge_resume_graph_claim_binding_fields(l2_output, artifact_dir=artifact_dir)
    write_json(artifact_dir / "l2_output.json", l2_output)
    finalize_section_l2_after_output(artifact_dir, "unify_narrative", runtime_payload)
    finalize_section_runtime_exhaust_before_l6(artifact_dir, "unify_narrative", runtime_payload, repo_root=repo_root)
    gate_section_l6_shadow_after_exhaust(artifact_dir, runtime_payload)
    write_json(artifact_dir / "l6_shadow_eval_package.json", _build_unify_l6(artifact_dir=artifact_dir, repo_root=repo_root, prompt_id=spec.prompt_id, temperature=temperature, max_tokens=spec.max_output_tokens))
    write_json(artifact_dir / "l6_shadow_learning.json", build_l6_shadow_learning_record(artifact_dir=artifact_dir, repo_root=repo_root, section_id="unify_narrative", lane_key="unify_narrative"))
    write_json(artifact_dir / "real_l2_generation_result.json", {"provider_attempted": args.provider, "provider_available": bool(provider_result_data.get("provider_available")), "exact_provider_error": provider_result_data.get("exact_provider_error"), "runtime_generation_status": runtime_generation_status, "prompt_id": spec.prompt_id, "prompt_hash": prompt_hash, "model": model_name, "temperature": temperature, "input_payload_hash": input_payload_hash, "output_payload_hash": (parsed_for_x2 or {}).get("output_payload_hash"), "claim_ledger_hash": (parsed_for_x2 or {}).get("claim_ledger_hash"), "allowed_fact_ids_hash": (parsed_for_x2 or {}).get("allowed_fact_ids_hash"), "raw_model_output": raw_output, "parsed_model_output": parsed_for_x2, "narrative_sentence": narrative, "selected_fact_plan": l2_output["selected_fact_plan"], "claim_ledger": claim_ledger, "text_claim_coverage": coverage, "fact_check_result": {"passed": not [g for g in x2 if not g["pass"]], "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]]}, "product_quality_status": pq_status, "x3_disposition_ref": str(artifact_dir / "x3_disposition.json"), "l6_shadow_eval_package_ref": str(artifact_dir / "l6_shadow_eval_package.json"), "l6_shadow_learning_ref": str(artifact_dir / "l6_shadow_learning.json")})
    smr = {"run_id": runtime_payload["run_id"], "lane_id": "unify_narrative", "prompt_id": spec.prompt_id, "prompt_hash": prompt_hash, "input_payload_hash": input_payload_hash, "output_payload_hash": (parsed_for_x2 or {}).get("output_payload_hash"), "claim_ledger_hash": (parsed_for_x2 or {}).get("claim_ledger_hash"), "runtime_generation_status": runtime_generation_status, "product_quality_status": pq_status, "x2_failed_gates": [g["gate_id"] for g in x2 if not g["pass"]], "x3_code": x3.x3_code, "proof_eligible": proof_bundle["proof_eligible"], "judge_proof_eligible": proof_bundle["judge_proof_eligible"]}
    merge_graph_evidence_reporting_into_dict(smr, section_id="unify_narrative", runtime_payload=runtime_payload, x2_gates=x2, selected_fact_plan=l2_output.get("selected_fact_plan"), claim_ledger=claim_ledger)
    write_json(artifact_dir / "section_metric_receipt.json", smr)
    out_text = f"L2_UNIFY_NARRATIVE_OUTPUT:\n{narrative or f'BLOCKED: {parse_error}'}\nX3={x3.x3_code}\noffline_only=true\n"
    _wg.write_text(artifact_dir / "command_output.txt", out_text, encoding="utf-8")
    finalize_section_one_spine_certification(artifact_dir, "unify_narrative", runtime_payload, proof_bundle=proof_bundle, runtime_generation_status=runtime_generation_status)
    finalize_runtime_proof_run(repo_root, "unify_narrative", args.provider, artifact_dir, run_id=runtime_payload["run_id"], section_id="unify_narrative", runtime_generation_status=runtime_generation_status, provider_requested=str(provider_request_data.get("provider_requested", args.provider)), provider_attempted=provider_request_data.get("provider_attempted", args.provider), command=" ".join(sys.argv), proof_eligible=proof_bundle["proof_eligible"], judge_proof_eligible=proof_bundle["judge_proof_eligible"], proof_scope=proof_bundle["proof_scope"], proof_status=proof_bundle["proof_status"], runtime_certification=proof_bundle["runtime_certification"], x1d_runtime_status=proof_bundle["x1d_runtime_status"], provider_proof_eligible=proof_bundle["provider_proof_eligible"], test_only_mock_judges=proof_bundle["test_only_mock_judges"])
    return {"artifact_dir": artifact_dir, "repo_root": repo_root, "lane_key": "unify_narrative", "args": args, "runtime_payload": runtime_payload, "x3": x3, "output_text": out_text}

def _finalize_ibm_narrative_v2(ctx: dict[str, Any]) -> dict[str, Any]:
    args, spec, repo_root, artifact_dir, pool = ctx["args"], ctx["spec"], ctx["repo_root"], ctx["artifact_dir"], ctx["pool"]
    emp_header, selected_fact_plan, allowed_fact_ids = ctx["emp_header"], ctx["selected_fact_plan"], ctx["allowed_fact_ids"]
    companion_context, companion_text, runtime_payload = ctx["companion_context"], ctx["companion_text"], ctx["runtime_payload"]
    input_payload_hash, section_compiled, messages, prompt_hash = ctx["input_payload_hash"], ctx["section_compiled"], ctx["messages"], ctx["prompt_hash"]
    provider_payload, provider_request_data, provider_result_data = ctx["provider_payload"], ctx["provider_request_data"], ctx["provider_result_data"]
    raw_output, parsed, parse_error, runtime_generation_status = ctx["raw_output"], ctx["parsed"], ctx["parse_error"], ctx["runtime_generation_status"]
    req_id, trace_rr, pp_x2, srfs_slice_x2_active = ctx["req_id"], ctx["trace_rr"], ctx["pp_x2"], ctx["srfs_slice_x2_active"]
    model_name, candidate_name, judge_keys = ctx["model_name"], ctx["candidate_name"], ctx["judge_keys"]
    judge_allowed_mock, preflight_art, preflight_blocked = ctx["judge_allowed_mock"], ctx["preflight_art"], ctx["preflight_blocked"]
    test_only_mock_prov = str(getattr(args, "provider", "") or "").strip().lower() == "mock" and (bool(getattr(args, "allow_test_mock_provider", False)) or bool(getattr(args, "allow_non_allow_exit_zero", False)))
    allowed_ids_list = list(runtime_payload.get("allowed_fact_ids") or [])
    def _sync_ibm(cur_p: dict[str, Any] | None, cur_raw: str) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str]:
        c_narr, c_led = str((cur_p or {}).get("narrative_sentence") or "").strip(), list((cur_p or {}).get("claim_ledger") or [])
        p_stat, inv_r = classify_ledger_parse_state(cur_p, parse_error=parse_error, raw_output=cur_raw or "", lane_profile="ibm_narrative")
        c_doc = build_canonical_claim_ledger_v2_payload(normalize_exec_summary_claim_ledger(c_led) if p_stat == "OK" else [], parse_status=p_stat, invalid_reason=inv_r if p_stat != "OK" else None, claim_id_prefix="ibm_narrative_claim")
        (artifact_dir / "raw_model_output.txt").write_text(cur_raw or "", encoding="utf-8")
        write_json(artifact_dir / "parsed_output.json", {"parsed": cur_p, "parse_error": parse_error, "parse_status": p_stat})
        write_json(artifact_dir / "canonical_claim_ledger_v2.json", c_doc)
        c_cov = build_sentence_claim_coverage(c_narr, c_led, allowed_fact_ids)
        write_json(artifact_dir / "text_claim_coverage.json", c_cov)
        write_json(artifact_dir / "selected_fact_plan.json", (cur_p or {}).get("selected_fact_plan") or selected_fact_plan)
        u_doc = build_section_input_usage_ledger_v1(section_id="ibm_narrative", run_id=str(runtime_payload["run_id"]), request_id=req_id, trace_root=trace_rr, repo_root=repo_root, artifact_dir=artifact_dir, runtime_payload=runtime_payload, selected_fact_plan=(cur_p or {}).get("selected_fact_plan") or selected_fact_plan, claim_ledger=c_led, allowed_fact_ids=allowed_fact_ids, jd_text=str(runtime_payload.get("jd_text") or ""), target_title=str(runtime_payload.get("target_title") or ""), target_company=str(runtime_payload.get("target_company") or ""), briefing_text=str(runtime_payload.get("briefing") or ""), jd_alignment=(cur_p or {}).get("jd_alignment") if isinstance(cur_p, dict) else None)
        write_json(artifact_dir / "section_input_usage_ledger.json", apply_proof_pool_to_usage_ledger(u_doc, pool))
        px2: dict[str, Any] = {**(cur_p or {}), "text_claim_coverage": c_cov}
        return c_narr, c_led, c_doc, c_cov, u_doc, px2, (json.dumps(px2, ensure_ascii=False, separators=(",", ":")) if "```" in cur_raw else cur_raw)
    def _run_ibm_det_x2(c_narr: str, c_led: list[dict[str, Any]], c_px2: dict[str, Any], c_cov: dict[str, Any], c_raw_x2: str) -> list[str]:
        return pre_judge_failed_gate_ids([g.to_dict() for g in run_ibm_narrative_x2_gates(narrative_sentence=c_narr, parsed_output=c_px2, claim_ledger=c_led, jd_text=args.jd_text, runtime_generation_status=runtime_generation_status, companion_bullet_texts=companion_text or None, companion_bullets_status=str(companion_context.get("status") or "UNKNOWN"), companion_bullets_reason=str(companion_context.get("reason") or ""), companion_aware=not test_only_mock_prov, candidate_name=candidate_name, provider_requested=args.provider, provider_attempted=args.provider, model_name=model_name, raw_output=c_raw_x2, x1d_judges=[], allowed_fact_ids=allowed_ids_list, test_only_mock_provider=test_only_mock_prov, artifacts_dir=artifact_dir, text_claim_coverage=c_cov, srfs_source_fact_slice_gate_active=srfs_slice_x2_active, proof_pool_metadata=pp_x2, proof_pool_ref=str(pool.proof_pool_ref or ""), proof_pool_digest=str(pool.proof_pool_digest or ""))])
    narrative, claim_ledger, canon_doc, coverage, usage_doc, parsed_for_x2, raw_output_for_x2 = _sync_ibm(parsed, raw_output)
    pre_x2_failed = _run_ibm_det_x2(narrative, claim_ledger, parsed_for_x2, coverage, raw_output_for_x2)
    judge_mode, rewrite_accepted = ("mocked" if judge_allowed_mock else "blocked_if_unavailable"), False
    if pre_x2_failed and runtime_generation_status == "REAL_LLM" and not judge_allowed_mock and not preflight_blocked and isinstance(parsed, dict):
        usage_path = artifact_dir / "section_input_usage_ledger.json"
        usage_snap = usage_path.read_bytes() if usage_path.is_file() else None
        cos_diag = cosine_echo_diagnostic_summary(narrative, companion_bullets_as_list(companion_text))
        pre_msgs = [*messages, {"role": "assistant", "content": raw_output}, {"role": "user", "content": f"DETERMINISTIC_X2_REVISION: the draft failed section invariants: [{', '.join(pre_x2_failed[:8])}]. Companion echo diagnostic: {cos_diag}. Rewrite narrative_sentence and claim_ledger from scratch in one crisp executive sentence at IBM synthesizing 2 to 4 concrete delivered technical capabilities attested in the companion IBM bullets using ', establishing' clause structure, cite ONLY literal bul_ibm_001..bul_ibm_005 IDs (max 2 per clause row), and keep pairwise content cosine <= 0.35 with each companion bullet. Return one JSON object only."}]
        pre_res = generate_section(tag_reasoning_lane({**provider_payload, "messages": pre_msgs, "max_tokens": 4000}, "ibm_narrative"), artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""))
        if pre_res.runtime_generation_status == "REAL_LLM":
            cand_in, _ = parse_narrative_model_json(str(pre_res.raw_model_output or ""))
            cand_p = normalize_ibm_narrative_parsed(cand_in, runtime_payload, companion_text, allow_echo_repair=False) if cand_in else None
            if isinstance(cand_p, dict):
                c_narr, c_led, c_doc, c_cov, c_use, c_px2, c_raw_x2 = _sync_ibm(cand_p, str(pre_res.raw_model_output or ""))
                if not _run_ibm_det_x2(c_narr, c_led, c_px2, c_cov, c_raw_x2):
                    raw_output, parsed, narrative, claim_ledger, canon_doc, coverage, usage_doc, parsed_for_x2, raw_output_for_x2 = str(pre_res.raw_model_output or ""), cand_p, c_narr, c_led, c_doc, c_cov, c_use, c_px2, c_raw_x2
                    pre_x2_failed, rewrite_accepted = [], True
                    record_repair(artifact_dir, kind=KIND_REGEN_LLM, operation="ibm_narrative_x2_prejudge_rewrite", reason="pre_x2_failed", replaced_l2=True)
                    cur_led = load_ledger(artifact_dir) or {}
                    set_authoritative_attempt(artifact_dir, 1 + sum(1 for r in (cur_led.get("repairs") or []) if r.get("kind") == KIND_REGEN_LLM and r.get("replaced_l2")), reason="ibm_narrative_x2_prejudge_rewrite")
                elif usage_snap is not None:
                    usage_path.write_bytes(usage_snap)
    ibm_fact_packet = {"allowed_fact_ids": sorted(str(x) for x in allowed_fact_ids), "facts": [{"fact_id": f.get("fact_id"), "role_episode_bundle_id": f.get("role_episode_bundle_id"), "claim_text": f.get("claim_text"), "domain": f.get("domain"), "allowed_graph_evidence_ids": f.get("allowed_graph_evidence_ids"), "raw_chunk": str(f.get("raw_chunk") or "")[:1500]} for f in ((runtime_payload.get("selected_fact_plan") or {}).get("facts") or []) if isinstance(f, dict)]}
    ibm_targeting = {"target_title": str(runtime_payload.get("target_title") or ""), "target_company": str(runtime_payload.get("target_company") or ""), "jd_text": str(runtime_payload.get("jd_text") or ""), "briefing": str(runtime_payload.get("briefing") or ""), "targeting_only": True}
    default_ibm_j = tuple(get_section_judge_policy("ibm_narrative").required_judge_providers) or ("gemini_pro", "openai_chatgpt")
    if preflight_blocked and not judge_allowed_mock:
        x1d = build_blocked_pre_judge_rows(section_id="ibm_narrative", judge_keys=judge_keys, failed_gate_ids=list(preflight_art.get("preflight_decisive_blockers") or ["judge_preflight_blocked"]), rubric_version=_IBM_NARR_RUBRIC_VERSION, default_judge_keys=default_ibm_j)
    elif (pre_x2_failed or runtime_generation_status != "REAL_LLM") and not judge_allowed_mock:
        x1d = build_blocked_pre_judge_rows(section_id="ibm_narrative", judge_keys=judge_keys, failed_gate_ids=pre_x2_failed or [f"runtime_status:{runtime_generation_status}"], rubric_version=_IBM_NARR_RUBRIC_VERSION, default_judge_keys=default_ibm_j)
    else:
        x1d = [j.to_dict() for j in run_ibm_narrative_judges(narrative_sentence=narrative, claim_ledger=claim_ledger, judge_keys=judge_keys, companion_bullets_context=companion_text, mode=judge_mode, artifact_base=artifact_dir, allowed_fact_packet=ibm_fact_packet, targeting_context=ibm_targeting)]
        raw_output, parsed, x1d, j_accepted = apply_ibm_narrative_judge_feedback_rewrite(messages=messages, provider_payload=provider_payload, raw_output=raw_output, parsed=parsed, x1d=x1d, runtime_payload=runtime_payload, artifact_dir=artifact_dir, runtime_generation_status=runtime_generation_status, companion_text=companion_text, judge_keys=judge_keys, judge_mode=judge_mode, allowed_fact_packet=ibm_fact_packet, targeting_context=ibm_targeting, x2_check_fn=lambda cp, cr: _run_ibm_det_x2(*_sync_ibm(cp, cr)[:2], _sync_ibm(cp, cr)[5], _sync_ibm(cp, cr)[3], _sync_ibm(cp, cr)[6]))
        if j_accepted and isinstance(parsed, dict):
            rewrite_accepted = True
            narrative, claim_ledger, canon_doc, coverage, usage_doc, parsed_for_x2, raw_output_for_x2 = _sync_ibm(parsed, raw_output)
    if rewrite_accepted:
        provider_result_data["raw_model_output"] = raw_output or ""
        write_json(artifact_dir / "provider_response.json", provider_result_data)
    write_json(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": x1d})
    x2 = [g.to_dict() for g in run_ibm_narrative_x2_gates(narrative_sentence=narrative, parsed_output=parsed_for_x2, claim_ledger=claim_ledger, jd_text=args.jd_text, runtime_generation_status=runtime_generation_status, companion_bullet_texts=companion_text or None, companion_bullets_status=str(companion_context.get("status") or "UNKNOWN"), companion_bullets_reason=str(companion_context.get("reason") or ""), companion_aware=not test_only_mock_prov, candidate_name=candidate_name, provider_requested=args.provider, provider_attempted=args.provider, model_name=model_name, raw_output=raw_output_for_x2, x1d_judges=x1d, allowed_fact_ids=allowed_ids_list, test_only_mock_provider=test_only_mock_prov, artifacts_dir=artifact_dir, text_claim_coverage=coverage, srfs_source_fact_slice_gate_active=srfs_slice_x2_active, proof_pool_metadata=pp_x2, proof_pool_ref=str(pool.proof_pool_ref or ""), proof_pool_digest=str(pool.proof_pool_digest or ""))]
    for g in x2:
        if isinstance(obs := g.get("observed_value"), dict) and obs.get("x2_source_fact_pool_status"):
            write_x2_source_fact_pool_receipt(artifact_dir, obs)
            break
    l2_output = {"run_id": runtime_payload["run_id"], "section_id": "ibm_narrative", "runtime_generation_status": runtime_generation_status, "product_quality_status": "PENDING", "ibm_header": emp_header, "narrative_sentence": narrative, "selected_fact_plan": (parsed or {}).get("selected_fact_plan") or selected_fact_plan, "claim_ledger": claim_ledger, "jd_alignment": (parsed or {}).get("jd_alignment") or {"targeting_only": True}, "gap_notes": (parsed or {}).get("gap_notes") or [], "change_log": (parsed or {}).get("change_log") or [], "self_check": (parsed or {}).get("self_check") or {"parse_error": parse_error}, "prompt_id": spec.prompt_id, "prompt_hash": prompt_hash, "section_prompt_adapter": True, "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref, "compiler_template_id": section_compiled.artifact.template_id, "input_payload_hash": input_payload_hash, "judge_preflight_blocked": bool(preflight_blocked), "text_claim_coverage": coverage}
    (artifact_dir / "ibm_narrative_output.txt").write_text(narrative + "\n", encoding="utf-8")
    write_json(artifact_dir / "claim_ledger.json", claim_ledger)
    write_json(artifact_dir / "prompt_selection_trace.json", {"runtime_path": ctx.get("trace_runtime_path") or "apps_rg.runtime.sections.ibm_narrative_lane", "prompt_id": spec.prompt_id, "provider": args.provider, "temperature": args.temperature, "section_prompt_adapter": True, "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref, "compiler_template_id": section_compiled.artifact.template_id})
    write_x2_gate_outputs(artifact_dir / "x2_gate_outputs.json", x2, section_id="ibm_narrative")
    ibm_led = load_ledger(artifact_dir) or {}
    record_x2_run(artifact_dir, run_number=len(list(ibm_led.get("x2_runs") or [])) + 1, after_l2_source=str(ibm_led.get("authoritative_l2_source") or "initial_llm"), x2_gates=x2)
    if rewrite_accepted and not [g for g in x2 if not g.get("pass")]:
        set_authoritative_attempt(artifact_dir, max(2, 1 + sum(1 for r in (ibm_led.get("repairs") or []) if isinstance(r, dict) and r.get("replaced_l2"))), reason="ibm_narrative_v2_rewrite_x2_pass")
    write_json(artifact_dir / "fact_check_result.json", {"passed": not [g for g in x2 if not g["pass"]], "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]]})
    pq_status, pq_reason = infer_narrative_product_quality("ibm_narrative", runtime_generation_status, x2, artifact_dir=artifact_dir)
    x3 = finalize_section_lane_x3(artifact_dir=artifact_dir, section_id="ibm_narrative", runtime_payload=runtime_payload, defer_graph_binding_l2_persistence=True, aggregate_x3_fn=_aggregate_ibm_narrative_x3, resume_display_text=narrative or raw_output, claim_ledger=claim_ledger, x2_gates=x2, x1d_judges=x1d, runtime_generation_status=runtime_generation_status, product_quality_status=pq_status, canonical_claims_for_hash=canon_doc.get("claims"), section_input_usage_ledger=usage_doc)
    bundle = compute_lane_proof_bundle(args, section_id="ibm_narrative", runtime_generation_status=runtime_generation_status, x1d_judges=x1d, x2_gates=x2, x3=x3)
    gen_cls = classify_generation_class(runtime_generation_status=runtime_generation_status, offline_contract_stub_active=False, test_only_mock_provider=bool(bundle.get("test_only_mock_provider")))
    jdg_cls, prf_cls, crt_cls = classify_judge_class(x1d), classify_proof_class(bundle=bundle, x3_code=x3.x3_code, x3_pass=bool(x3.pass_)), classify_certification_class(bundle=bundle, x3_code=x3.x3_code, x3_pass=bool(x3.pass_))
    dec_lbl = compute_decisive_accounting_label(command_fault=False, runtime_generation_status=runtime_generation_status, x2_failure_count=sum(1 for g in x2 if not g.get("pass")), x3_code=x3.x3_code, x3_pass=bool(x3.pass_), proceed_to_runtime=bool(x3.proceed_to_runtime), mock_judges_active=bool(judge_allowed_mock), proof_eligible=bool(bundle.get("proof_eligible")), preflight_blocked=bool(preflight_blocked), bundle_proof_scope=str(bundle.get("proof_scope") or ""))
    write_json(artifact_dir / "clean_x3_allow_readiness.json", build_clean_x3_allow_readiness_document(section_id="ibm_narrative", run_id=str(runtime_payload["run_id"]), clean_allow_possible_at_start=bool(preflight_art.get("all_required_available") and not judge_allowed_mock), required_judges=list(judge_keys), provider_preflight_status_by_judge=dict(preflight_art.get("provider_preflight_status_by_judge") or {}), mocked_judges_present=any(str(j.get("evaluator_mode")) == "MOCKED" for j in x1d), blocked_judges_present=any(str(j.get("evaluator_mode", "")).startswith("BLOCKED_") for j in x1d), mocked_judge_flags_active=judge_allowed_mock, x2_hard_gates_required=len(x2), x2_hard_gates_passed=sum(1 for g in x2 if g.get("pass")), x3_code=x3.x3_code, proceed_to_runtime=bool(x3.proceed_to_runtime), product_authorized=bool(x3.pass_), proof_eligible=bool(bundle.get("proof_eligible")), proof_scope=str(bundle.get("proof_scope") or ""), decisive_blockers=[], recommended_next_action="review x3_disposition.json", preflight_artifact_written=True))
    l2_output.update({"product_quality_status": pq_status, "product_quality_reason": pq_reason, "generation_class": gen_cls, "judge_class": jdg_cls, "proof_class": prf_cls, "certification_class": crt_cls, "decisive_accounting_label": dec_lbl})
    attach_ledger_summary_to_l2(l2_output, artifact_dir)
    attach_lane_proof_bundle_fields(l2_output, runtime_generation_status=runtime_generation_status, bundle=bundle)
    l2_output = merge_resume_graph_claim_binding_fields(l2_output, artifact_dir=artifact_dir)
    write_json(artifact_dir / "l2_output.json", l2_output)
    finalize_section_l2_after_output(artifact_dir, "ibm_narrative", runtime_payload)
    finalize_section_runtime_exhaust_before_l6(artifact_dir, "ibm_narrative", runtime_payload, repo_root=repo_root)
    gate_section_l6_shadow_after_exhaust(artifact_dir, runtime_payload)
    write_json(artifact_dir / "l6_shadow_eval_package.json", _build_ibm_l6(artifact_dir=artifact_dir, repo_root=repo_root, prompt_id=spec.prompt_id, temperature=float(args.temperature), max_tokens=spec.max_output_tokens))
    rl2 = {"provider_attempted": args.provider, "runtime_generation_status": runtime_generation_status, "prompt_hash": prompt_hash, "model": model_name, "raw_model_output": raw_output, "narrative_sentence": narrative, "product_quality_status": pq_status, "x3_code": x3.x3_code, "generation_class": gen_cls, "judge_class": jdg_cls, "proof_class": prf_cls, "certification_class": crt_cls}
    attach_lane_proof_bundle_fields(rl2, runtime_generation_status=runtime_generation_status, bundle=bundle)
    smr = {"run_id": runtime_payload["run_id"], "lane_id": "ibm_narrative", "prompt_id": spec.prompt_id, "prompt_hash": prompt_hash, "input_payload_hash": input_payload_hash, "output_payload_hash": (parsed_for_x2 or {}).get("output_payload_hash"), "claim_ledger_hash": (parsed_for_x2 or {}).get("claim_ledger_hash"), "runtime_generation_status": runtime_generation_status, "product_quality_status": pq_status, "x2_failed_gates": [g["gate_id"] for g in x2 if not g["pass"]], "x3_code": x3.x3_code, "proof_eligible": bundle["proof_eligible"], "judge_proof_eligible": bundle["judge_proof_eligible"]}
    merge_graph_evidence_reporting_into_dict(smr, section_id="ibm_narrative", runtime_payload=runtime_payload, x2_gates=x2, selected_fact_plan=l2_output.get("selected_fact_plan"), claim_ledger=claim_ledger)
    write_json(artifact_dir / "section_metric_receipt.json", smr)
    write_json(artifact_dir / "real_l2_generation_result.json", rl2)
    out_text = f"IBM_NARRATIVE_OUTPUT:\n{narrative or f'BLOCKED: {parse_error}'}\nX3={x3.x3_code}\noffline_only=true\n"
    (artifact_dir / "command_output.txt").write_text(out_text, encoding="utf-8")
    if ctx.get("print_output"):
        print(out_text)
    finalize_section_one_spine_certification(artifact_dir, "ibm_narrative", runtime_payload, proof_bundle=bundle, runtime_generation_status=runtime_generation_status)
    finalize_runtime_proof_run(repo_root, "ibm_narrative", args.provider, artifact_dir, run_id=runtime_payload["run_id"], section_id="ibm_narrative", runtime_generation_status=runtime_generation_status, provider_requested=str(provider_request_data.get("provider_requested", args.provider)), provider_attempted=provider_request_data.get("provider_attempted", args.provider), command=" ".join(sys.argv), proof_eligible=bundle["proof_eligible"], proof_scope=bundle["proof_scope"], test_only_mock_provider=bundle["test_only_mock_provider"], runtime_certification=bundle["runtime_certification"], x1d_runtime_status=bundle["x1d_runtime_status"], judge_proof_eligible=bundle["judge_proof_eligible"], provider_proof_eligible=bundle["provider_proof_eligible"], test_only_mock_judges=bundle["test_only_mock_judges"], proof_closeout_note=bundle.get("proof_closeout_note") or None, decisive_accounting_label=dec_lbl, shell_exit_overridden_for_inspection=bool(getattr(args, "allow_non_allow_exit_zero", False)), product_authorized=bool(x3.pass_), x3_json_source_of_truth=True, not_release_signoff=True, generation_class=gen_cls, judge_class=jdg_cls, proof_class=prf_cls, certification_class=crt_cls, run_bundle_index_document_metadata={"generation_class": gen_cls, "judge_class": jdg_cls, "proof_class": prf_cls, "certification_class": crt_cls})
    exit_code = 0 if allow_non_allow_exit_zero_ok(args) else (0 if x3.x3_code == "X3_ALLOW" else 2)
    return {"artifact_dir": artifact_dir, "repo_root": repo_root, "lane_key": "ibm_narrative", "args": args, "runtime_payload": runtime_payload, "section_compiled": section_compiled, "messages": messages, "prompt_hash": prompt_hash, "input_payload_hash": input_payload_hash, "x3": x3, "output_text": out_text, "runtime_generation_status": runtime_generation_status, "allowed_fact_ids": allowed_fact_ids, "exit_code": exit_code}
