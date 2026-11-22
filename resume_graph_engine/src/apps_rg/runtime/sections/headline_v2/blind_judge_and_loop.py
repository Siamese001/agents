"""Bounded fresh-turn pre-judge X2 and post-judge healing loop for headline_v2."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from apps_rg.runtime.claim_ledger.headline_claim_ledger import _headline_positioning_segments
from apps_rg.runtime.section_repair_ledger import KIND_REGEN_LLM, load_ledger, record_repair
from apps_rg.runtime.sections.lane_perf_sync_helpers import extract_all_headline_graph_allocations, format_headline_clarity_reason
from apps_rg.runtime.sections.section_generation import generate_section, tag_reasoning_lane
from apps_rg.runtime.sections.section_product_shape_ssot import HEADLINE_WORD_MAX, HEADLINE_WORD_MIN
from apps_rg.runtime.validators.headline_positioning_x2 import GOVERNANCE_SIGNAL_FAMILIES, POSITIONING_FAMILY_FLOOR, governance_signal_families_matched, headline_positioning_consumption_active, narrowing_labels_found, positioning_families_matched
from apps_rg.runtime.validators.headline_quality_x2 import POSITIONING_FAMILIES
from apps_rg.runtime.validators.headline_x2 import evaluate_headline_literal_grounding, has_valid_headline_prefix, headline_executive_abstraction_report, headline_word_count, repair_headline_segment_citations_for_grounding
from .evidence_firewall import HEADLINE_MAX_OUTPUT_TOKENS, LANE_KEY, content_signal_repair_enabled, content_signal_repair_env_state, resolve_content_signal_repair_max_attempts, snapshot_raw_jd_alignment, sync_selected_fact_plan_required_ids, write_json
from .prompt_and_generate import normalize_parsed_output, parse_model_json
from .x2_invariants import headline_graph_binding_repair_state, headline_graph_content_contract_active, headline_resume_native_clarity_report

_SPECIFICITY_EMPHASIS_FAMILY_IDS: tuple[str, ...] = ("agentic_ai_platforms", "distributed_ai_infrastructure", "runtime_governance", "partner_applied_ai_architecture")

def _specificity_floor_vocab_emphasis() -> str:
    return "; ".join(f"{fam} ({', '.join(sorted(POSITIONING_FAMILIES.get(fam, frozenset())))})" for fam in _SPECIFICITY_EMPHASIS_FAMILY_IDS)

def _content_signal_arms(trigger_arm: str) -> set[str]:
    return {"governance_signal", "specificity_floor"} if trigger_arm == "both" else {a for a in trigger_arm.split("+") if a}

def _compact_headline_repair_anchor(parsed: dict[str, Any], *, fallback_raw: str) -> str:
    if not isinstance(parsed, dict):
        return str(fallback_raw or "")
    plan = parsed.get("selected_fact_plan")
    compact_plan = {k: plan.get(k) for k in ("section_id", "selection_method", "required_fact_ids", "plan_id", "plan_digest", "allocation_plan_digest") if isinstance(plan, dict) and k in plan}
    return json.dumps({"headline_line": parsed.get("headline_line"), "selected_fact_plan": compact_plan, "claim_ledger": parsed.get("claim_ledger") or [], "jd_alignment": parsed.get("jd_alignment") or {}, "gap_notes": parsed.get("gap_notes") or [], "change_log": parsed.get("change_log") or [], "self_check": parsed.get("self_check") or {}}, sort_keys=True, separators=(",", ":"))

def _call_headline_generate_section(payload: dict[str, Any], *, artifact_dir: Path | None = None, run_id: str = "") -> Any:
    import sys
    hl_mod = sys.modules.get("apps_rg.runtime.sections.headline_lane")
    fn = getattr(hl_mod, "generate_section", None) if hl_mod is not None else None
    return (fn or generate_section)(payload, artifact_dir=artifact_dir, run_id=run_id)

def retry_provider_for_parse(messages: list[dict[str, str]], provider_payload: dict[str, Any], raw_output: str, parse_error: str, *, artifact_dir: Path | None = None, run_id: str = "") -> tuple[str, dict[str, Any] | None, str]:
    repair_msgs = [*messages, {"role": "assistant", "content": raw_output}, {"role": "user", "content": f"JSON INVALID: {parse_error}. Return one compact JSON object with headline_line (exact prefix SVP Engineering | ; 3 separators ' | '; 4 segments; 10-13 words total), selected_fact_plan, claim_ledger, jd_alignment (jd_used_as_proof=false, briefing_used_as_proof=false), gap_notes, change_log, and self_check."}]
    res = _call_headline_generate_section(tag_reasoning_lane({**provider_payload, "messages": repair_msgs, "max_tokens": HEADLINE_MAX_OUTPUT_TOKENS, "anthropic_workload_kind": "REPAIR"}, LANE_KEY), artifact_dir=artifact_dir, run_id=run_id)
    if res.runtime_generation_status != "REAL_LLM":
        return raw_output, None, parse_error
    new_p, new_err = parse_model_json(res.raw_model_output)
    return res.raw_model_output, new_p, new_err

def retry_headline_word_and_pipe(messages: list[dict[str, str]], provider_payload: dict[str, Any], raw_output: str, parsed: dict[str, Any], runtime_payload: dict[str, Any], allowed_fact_ids: set[str], reason: str, *, companion_nonempty: bool, employer_names_lower: list[str], artifact_dir: Path | None = None, run_id: str = "") -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    prompt = f"DETERMINISTIC_REVISION: {reason}. headline_line must start with an approved executive prefix (such as 'SVP Agentic Transformation | ', 'SVP Engineering | ', or matching the target role), contain exactly three ' | ' separators (four segments), be 10 to 13 total words (each X/Y/Z segment 3-4 words), each segment must include or terminate in an approved executive abstraction noun (Platform, Architecture, Systems, Governance, Ecosystem, Commercialization, Infrastructure, Controls), preserve >=2 positioning families, and contain no employer names, target company names, metrics, or first person."
    res = _call_headline_generate_section(tag_reasoning_lane({**provider_payload, "messages": [*messages, {"role": "assistant", "content": _compact_headline_repair_anchor(parsed, fallback_raw=raw_output)}, {"role": "user", "content": prompt}], "max_tokens": HEADLINE_MAX_OUTPUT_TOKENS, "anthropic_workload_kind": "REPAIR"}, LANE_KEY), artifact_dir=artifact_dir, run_id=run_id)
    if res.runtime_generation_status != "REAL_LLM":
        return raw_output, parsed, None
    new_p, _ = parse_model_json(res.raw_model_output)
    if new_p is None:
        return raw_output, parsed, None
    raw_snap = json.loads(json.dumps(new_p))
    snapshot_raw_jd_alignment(new_p)
    new_p = normalize_parsed_output(new_p, runtime_payload, allowed_fact_ids, str(new_p.get("headline_line", "")).strip(), companion_nonempty=companion_nonempty, employer_names_lower=employer_names_lower, allow_prose_mutation=False) or parsed
    final_hl = str(new_p.get("headline_line") or "").strip()
    if final_hl.count(" | ") != 3 or not has_valid_headline_prefix(final_hl) or not (HEADLINE_WORD_MIN <= headline_word_count(final_hl) <= HEADLINE_WORD_MAX):
        return raw_output, parsed, None
    new_p["change_log"] = [*list(parsed.get("change_log") or []), *list(new_p.get("change_log") or []), {"operation": "headline_format_repair", "reason": reason}]
    return json.dumps(new_p, sort_keys=True, separators=(",", ":")), new_p, raw_snap

def retry_headline_proof_shape(messages: list[dict[str, str]], provider_payload: dict[str, Any], raw_output: str, failed_snapshot: dict[str, Any], runtime_payload: dict[str, Any], allowed_fact_ids: set[str], reason: str, *, companion_nonempty: bool, employer_names_lower: list[str], artifact_dir: Path | None = None, run_id: str = "") -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    hl_fail = str(failed_snapshot.get("headline_line") or "").strip()
    cl_fail = failed_snapshot.get("claim_ledger")
    sc_fail = failed_snapshot.get("self_check") if isinstance(failed_snapshot.get("self_check"), dict) else {}
    prompt = f"PROOF_COMPLIANCE_REVISION ({reason}). claim_ledger MUST be a JSON array of OBJECT rows only (one per X/Y/Z segment with claim_text equal to that segment phrase and non-empty source_fact_ids; never flat ID strings). self_check MUST be recomputed from the FINAL headline_line before emitting JSON. Prior headline_line: {hl_fail!r}\nPrior claim_ledger: {json.dumps(cl_fail, ensure_ascii=False)[:900]}\nPrior self_check: {json.dumps(sc_fail, ensure_ascii=False)[:900]}\nReturn one corrected compact JSON object only."
    res = _call_headline_generate_section(tag_reasoning_lane({**provider_payload, "messages": [*messages, {"role": "assistant", "content": _compact_headline_repair_anchor(failed_snapshot, fallback_raw=raw_output)}, {"role": "user", "content": prompt}], "max_tokens": HEADLINE_MAX_OUTPUT_TOKENS, "anthropic_workload_kind": "REPAIR"}, LANE_KEY), artifact_dir=artifact_dir, run_id=run_id)
    if res.runtime_generation_status != "REAL_LLM":
        return raw_output, failed_snapshot, None
    new_p, _ = parse_model_json(res.raw_model_output)
    if new_p is None:
        return raw_output, failed_snapshot, None
    raw_snap = json.loads(json.dumps(new_p))
    snapshot_raw_jd_alignment(new_p)
    new_p = normalize_parsed_output(new_p, runtime_payload, allowed_fact_ids, str(new_p.get("headline_line", "")).strip(), companion_nonempty=companion_nonempty, employer_names_lower=employer_names_lower, allow_prose_mutation=False) or failed_snapshot
    new_p["change_log"] = [*list(failed_snapshot.get("change_log") or []), *list(new_p.get("change_log") or []), {"operation": "headline_proof_shape_retry", "reason": reason}]
    return json.dumps(new_p, sort_keys=True, separators=(",", ":")), new_p, raw_snap

def _content_signal_emphasis(trigger_arm: str, families_matched_pre: list[str], narrowing_labels_pre: list[str] | None = None, missing_abstraction_pre: list[str] | None = None, grounding_failure_pre: str | None = None, clarity_report_pre: dict[str, Any] | None = None, graph_binding_context_pre: list[dict[str, Any]] | None = None, all_graph_allocations: list[dict[str, Any]] | None = None) -> str:
    arms = _content_signal_arms(trigger_arm)
    parts: list[str] = []
    if "governance_signal" in arms:
        parts.append("CONTENT_SIGNAL_REVISION (x2_headline_governance_or_regulated_ai_signal_required): At least one of X/Y/Z MUST express a governance or regulated-AI positioning family (governance, governed, runtime, gates, policy, deterministic, regulated, regulatory, compliance).")
    if "specificity_floor" in arms:
        parts.append(f"CONTENT_SIGNAL_REVISION (x2_headline_technical_specificity_floor_met): matched {len(families_matched_pre)} of {POSITIONING_FAMILY_FLOOR} families ({families_matched_pre}). Express >= {POSITIONING_FAMILY_FLOOR} distinct families from: {_specificity_floor_vocab_emphasis()}.")
    if "narrowing_labels" in arms:
        parts.append(f"CONTENT_SIGNAL_REVISION (x2_headline_no_narrowing_it_labels / x2_headline_generic_it_strategy_demote_forbidden): remove forbidden narrowing label(s) {list(narrowing_labels_pre or [])} and replace with senior platform/engineering positioning vocabulary.")
    if "executive_abstraction" in arms:
        parts.append(f"CONTENT_SIGNAL_REVISION (x2_headline_executive_abstraction_floor): segment(s) {list(missing_abstraction_pre or [])} lack an executive operating abstraction (platform, architecture, governance, ecosystem, commercialization, regulated systems, partner, enterprise, runtime, infrastructure, productization, controls, co-sell).")
    if "literal_grounding" in arms:
        parts.append(f"CONTENT_SIGNAL_REVISION (x2_headline_xyz_literal_grounding): {str(grounding_failure_pre or 'one or more segments are not grounded')}. Keep >=1 non-generic content noun and >=50% non-generic nouns literally in the cited fact claim_text.")
    if "resume_native_clarity" in arms:
        parts.append(f"CONTENT_SIGNAL_REVISION (headline_pre_x1d_resume_native_clarity): opaque={list((clarity_report_pre or {}).get('opaque_segments') or [])}; overlap={list((clarity_report_pre or {}).get('semantic_overlap_issues') or [])}. Use 3-4 words per segment (10-13 total words) without repeating runtime/governance/policy/controls across segments.")
    if "graph_claim_binding" in arms:
        all_txt = f" All mandatory 1-to-1 headline allocations: {json.dumps(list(all_graph_allocations), ensure_ascii=False, sort_keys=True)}." if all_graph_allocations else ""
        parts.append(f"CONTENT_SIGNAL_REVISION (x2_resume_graph_claim_binding): Unbound allocation authority: {json.dumps(list(graph_binding_context_pre or []), ensure_ascii=False, sort_keys=True)}.{all_txt}")
    parts.append("Keep every other constraint (exact prefix 'SVP Engineering | ', exactly three ' | ' separators, 10 to 13 total words, no metrics, no employer or target company names, no first person). Rebind claim_ledger rows per segment, recompute self_check, and return one compact JSON object only.")
    return " ".join(parts)

def retry_headline_content_signal(
    messages: list[dict[str, str]], provider_payload: dict[str, Any], raw_output: str, parsed: dict[str, Any],
    runtime_payload: dict[str, Any], allowed_fact_ids: set[str], *, companion_nonempty: bool, employer_names_lower: list[str],
    trigger_arm: str = "governance_signal", families_matched_pre: list[str] | None = None, narrowing_labels_pre: list[str] | None = None,
    missing_abstraction_pre: list[str] | None = None, grounding_failure_pre: str | None = None, clarity_report_pre: dict[str, Any] | None = None,
    graph_binding_context_pre: list[dict[str, Any]] | None = None, trigger_reason: str = "x2_headline_governance_or_regulated_ai_signal_required:none",
    artifact_dir: Path | None = None, run_id: str = "", attempt_index: int = 1,
) -> tuple[str, dict[str, Any], dict[str, Any] | None, str | None, dict[str, Any]]:
    emphasis = _content_signal_emphasis(trigger_arm, list(families_matched_pre or []), list(narrowing_labels_pre or []), list(missing_abstraction_pre or []), grounding_failure_pre, clarity_report_pre, graph_binding_context_pre, extract_all_headline_graph_allocations(parsed, runtime_payload))
    res = _call_headline_generate_section(tag_reasoning_lane({**provider_payload, "messages": [*messages, {"role": "assistant", "content": _compact_headline_repair_anchor(parsed, fallback_raw=raw_output)}, {"role": "user", "content": emphasis}], "max_tokens": HEADLINE_MAX_OUTPUT_TOKENS, "anthropic_workload_kind": "REPAIR"}, LANE_KEY), artifact_dir=artifact_dir, run_id=run_id)
    prov_res = {"runtime_generation_status": str(res.runtime_generation_status or ""), "provider_requested": str(res.provider_requested or ""), "provider_attempted": bool(res.provider_attempted), "provider_available": bool(res.provider_available), "model": str(res.model or ""), "exact_provider_error": str(res.exact_provider_error or ""), "provider_response_ref": f"headline_content_signal_repair_provider_response_attempt_{int(attempt_index)}.json"}
    if artifact_dir is not None:
        write_json(Path(artifact_dir) / prov_res["provider_response_ref"], res.to_dict())
    if res.runtime_generation_status != "REAL_LLM":
        return raw_output, parsed, None, "provider_not_real", prov_res
    new_p, _ = parse_model_json(res.raw_model_output)
    if new_p is None:
        return raw_output, parsed, None, "parse_failed", prov_res
    raw_snap = json.loads(json.dumps(new_p))
    snapshot_raw_jd_alignment(new_p)
    new_p = normalize_parsed_output(new_p, runtime_payload, allowed_fact_ids, str(new_p.get("headline_line", "")).strip(), companion_nonempty=companion_nonempty, employer_names_lower=employer_names_lower, allow_prose_mutation=False) or parsed
    final_hl = str(new_p.get("headline_line") or "").strip()
    if _headline_positioning_segments(final_hl) is None or not (HEADLINE_WORD_MIN <= headline_word_count(final_hl) <= HEADLINE_WORD_MAX):
        return res.raw_model_output, new_p, raw_snap, "shape_invalid", prov_res
    graph_active = headline_graph_content_contract_active(new_p, runtime_payload, allowed_fact_ids)
    final_abs: dict[str, Any] = {"segments_missing_executive_abstraction": []}
    final_grounding_ok, final_graph_ok = True, True
    if graph_active:
        fb_facts = runtime_payload.get("selected_fact_plan", {}).get("facts") if isinstance(runtime_payload.get("selected_fact_plan"), dict) else None
        rep_led, _ = repair_headline_segment_citations_for_grounding(headline_line=final_hl, parsed_output=new_p, claim_ledger=list(new_p.get("claim_ledger") or []), fallback_facts=fb_facts, allowed_fact_ids=allowed_fact_ids)
        new_p["claim_ledger"] = rep_led
        sync_selected_fact_plan_required_ids(new_p, runtime_payload, allowed_fact_ids)
        final_abs = headline_executive_abstraction_report(final_hl)
        final_grounding_ok, _, _ = evaluate_headline_literal_grounding(headline_line=final_hl, parsed_output=new_p, claim_ledger=rep_led, proof_pool_metadata=runtime_payload.get("proof_pool_metadata") if isinstance(runtime_payload.get("proof_pool_metadata"), dict) else None, allowed_fact_ids=allowed_fact_ids, fallback_facts=fb_facts)
        fg_gate, _ = headline_graph_binding_repair_state(new_p, runtime_payload)
        final_graph_ok = bool(fg_gate is None or fg_gate.get("pass") is True)
    final_sig_missing = bool(not governance_signal_families_matched(final_hl) or len(positioning_families_matched(final_hl)) < POSITIONING_FAMILY_FLOOR or narrowing_labels_found(final_hl) or final_abs.get("segments_missing_executive_abstraction"))
    cl_fin = headline_resume_native_clarity_report(final_hl)
    final_clarity_ok = not cl_fin.get("opaque_segments") and (bool(cl_fin.get("pass")) if graph_active else True)
    if final_sig_missing or not final_grounding_ok or not final_clarity_ok or not final_graph_ok:
        rej = "graph_claim_binding_still_missing" if not final_graph_ok else ("literal_grounding_still_missing" if not final_grounding_ok else ("signal_still_missing" if final_sig_missing else "resume_clarity_still_missing"))
        return res.raw_model_output, new_p, raw_snap, rej, prov_res
    new_p["change_log"] = [*list(parsed.get("change_log") or []), *list(new_p.get("change_log") or []), {"operation": "headline_content_signal_repair", "reason": trigger_reason}]
    return json.dumps(new_p, sort_keys=True, separators=(",", ":")), new_p, raw_snap, None, prov_res

def _evaluate_content_signal_state(hl: str, parsed: dict[str, Any] | None, runtime_payload: dict[str, Any], allowed_fact_ids: set[str], pp_meta: dict[str, Any] | None) -> dict[str, Any]:
    gov, spec, narrow = governance_signal_families_matched(hl), positioning_families_matched(hl), narrowing_labels_found(hl)
    missing_abs = list(headline_executive_abstraction_report(hl).get("segments_missing_executive_abstraction") or [])
    graph_active = headline_graph_content_contract_active(parsed, runtime_payload, allowed_fact_ids)
    fb_facts = runtime_payload.get("selected_fact_plan", {}).get("facts") if isinstance(runtime_payload.get("selected_fact_plan"), dict) else None
    g_ok, g_obs, g_fail = evaluate_headline_literal_grounding(headline_line=hl, parsed_output=parsed or {}, claim_ledger=list((parsed or {}).get("claim_ledger") or []), proof_pool_metadata=pp_meta, allowed_fact_ids=allowed_fact_ids, fallback_facts=fb_facts) if graph_active else (True, {}, None)
    gb_gate, gb_ctx = headline_graph_binding_repair_state(parsed, runtime_payload) if graph_active else (None, [])
    clarity = headline_resume_native_clarity_report(hl)
    arms, gates, reasons = [], [], []
    if not gov:
        arms.append("governance_signal"); gates.append("x2_headline_governance_or_regulated_ai_signal_required"); reasons.append("x2_headline_governance_or_regulated_ai_signal_required:none")
    if len(spec) < POSITIONING_FAMILY_FLOOR:
        arms.append("specificity_floor"); gates.append("x2_headline_technical_specificity_floor_met"); reasons.append(f"x2_headline_technical_specificity_floor_met:{len(spec)}_of_{POSITIONING_FAMILY_FLOOR}")
    if narrow:
        arms.append("narrowing_labels"); gates.extend(("x2_headline_no_narrowing_it_labels", "x2_headline_generic_it_strategy_demote_forbidden")); reasons.append("x2_headline_no_narrowing_it_labels:" + "|".join(narrow))
    if graph_active and missing_abs:
        arms.append("executive_abstraction"); gates.append("x2_headline_executive_abstraction_floor"); reasons.append("x2_headline_executive_abstraction_floor:" + "|".join(missing_abs))
    if graph_active and not g_ok:
        arms.append("literal_grounding"); gates.append("x2_headline_xyz_literal_grounding"); reasons.append("x2_headline_xyz_literal_grounding:failed")
    if clarity.get("opaque_segments") or (graph_active and not bool(clarity.get("pass"))):
        arms.append("resume_native_clarity"); gates.append("headline_pre_x1d_resume_native_clarity"); reasons.append(format_headline_clarity_reason(clarity))
    if graph_active and gb_gate is not None and gb_gate.get("pass") is not True:
        arms.append("graph_claim_binding"); gates.append("x2_resume_graph_claim_binding"); reasons.append("x2_resume_graph_claim_binding:orphan_allocation")
    return {"gov": gov, "spec": spec, "narrow": narrow, "missing_abs": missing_abs, "g_ok": g_ok, "g_obs": g_obs, "g_fail": g_fail, "gb_gate": gb_gate, "gb_ctx": gb_ctx, "clarity": clarity, "arms": arms, "gates": gates, "reasons": reasons}

def apply_headline_content_signal_repair(*, messages: list[dict[str, str]], provider_payload: dict[str, Any], raw_output: str, parsed: dict[str, Any] | None, runtime_payload: dict[str, Any], allowed_fact_ids: set[str], artifact_dir: Path, runtime_generation_status: str, prior_repair_provider_call_made: bool, companion_nonempty: bool, employer_names_lower: list[str]) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None, bool]:
    if not isinstance(parsed, dict):
        return raw_output, parsed, None, False
    hl_pre = str(parsed.get("headline_line", "")).strip()
    pp_meta = runtime_payload.get("proof_pool_metadata") if isinstance(runtime_payload.get("proof_pool_metadata"), dict) else None
    if runtime_generation_status != "REAL_LLM" or not headline_positioning_consumption_active(pp_meta) or _headline_positioning_segments(hl_pre) is None:
        return raw_output, parsed, None, False
    st = _evaluate_content_signal_state(hl_pre, parsed, runtime_payload, allowed_fact_ids, pp_meta)
    if not st["arms"]:
        return raw_output, parsed, None, False
    trigger_arm, trigger_reason = "+".join(st["arms"]), "+".join(st["reasons"])
    ledger = load_ledger(artifact_dir) or {}
    replaced_regens = [r for r in (ledger.get("repairs") or []) if r.get("kind") == KIND_REGEN_LLM and r.get("replaced_l2")]
    only_proof_shape = bool(replaced_regens) and all(str(r.get("operation") or "") == "headline_proof_shape_retry" for r in replaced_regens)
    budget_consumed = any(str(r.get("operation") or "") != "headline_proof_shape_retry" for r in replaced_regens) or (prior_repair_provider_call_made and not only_proof_shape)
    receipt: dict[str, Any] = {"section_id": "headline", "run_id": str(runtime_payload.get("run_id") or ""), "gate_id": "+".join(st["gates"]), "trigger_arm": trigger_arm, "trigger": {"required_families": list(GOVERNANCE_SIGNAL_FAMILIES), "specificity_floor": POSITIONING_FAMILY_FLOOR, "families_matched_pre": {"governance_signal": st["gov"], "specificity_floor": st["spec"], "narrowing_labels": st["narrow"], "segments_missing_executive_abstraction": st["missing_abs"], "literal_grounding": st["g_obs"], "resume_native_clarity": st["clarity"], "resume_graph_claim_binding": st["gb_gate"], "unbound_graph_allocations": st["gb_ctx"]}, "headline_pre": hl_pre}, "attempted": False, "regen_call_made": False, "accepted": False, "headline_post": hl_pre, "families_matched_post": {"governance_signal": [], "specificity_floor": [], "narrowing_labels": [], "segments_missing_executive_abstraction": [], "literal_grounding": {}, "resume_native_clarity": {}, "resume_graph_claim_binding": {}}, "rejected_reason": None, "bounded": {"max_attempts": resolve_content_signal_repair_max_attempts(), "attempts_used": 0}, "env_kill_switch_state": content_signal_repair_env_state()}
    accepted, snap = False, None
    if not content_signal_repair_enabled():
        receipt["rejected_reason"] = "kill_switch_off"
    elif budget_consumed:
        receipt["rejected_reason"] = "regen_budget_consumed"
    else:
        receipt["attempted"] = receipt["regen_call_made"] = True
        cur_raw, cur_p, cur_st, cur_arm, cur_reason = raw_output, parsed, st, trigger_arm, trigger_reason
        new_raw, new_p, new_snap, rej, prov_res, rows = raw_output, parsed, None, "not_attempted", {}, []
        remediable = {"shape_invalid", "signal_still_missing", "literal_grounding_still_missing", "resume_clarity_still_missing", "graph_claim_binding_still_missing"}
        for attempt_idx in range(1, int(receipt["bounded"]["max_attempts"]) + 1):
            receipt["bounded"]["attempts_used"] = attempt_idx
            new_raw, new_p, new_snap, rej, prov_res = retry_headline_content_signal(messages, provider_payload, cur_raw, cur_p, runtime_payload, allowed_fact_ids, companion_nonempty=companion_nonempty, employer_names_lower=employer_names_lower, trigger_arm=cur_arm, families_matched_pre=cur_st["spec"], narrowing_labels_pre=cur_st["narrow"], missing_abstraction_pre=cur_st["missing_abs"], grounding_failure_pre=cur_st["g_fail"], clarity_report_pre=cur_st["clarity"], graph_binding_context_pre=cur_st["gb_ctx"], trigger_reason=cur_reason, artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""), attempt_index=attempt_idx)
            rows.append({"attempt": attempt_idx, "headline": str((new_p or {}).get("headline_line") or ""), "trigger_arm": cur_arm, "trigger_reason": cur_reason, "rejected_reason": rej, "provider_result": prov_res})
            if (rej is None and new_snap is not None) or rej not in remediable:
                break
            cur_raw, cur_p = new_raw, new_p
            cur_st = _evaluate_content_signal_state(str((cur_p or {}).get("headline_line") or ""), cur_p, runtime_payload, allowed_fact_ids, pp_meta)
            cur_arm, cur_reason = "+".join(cur_st["arms"]), "+".join(cur_st["reasons"])
        receipt["attempts"], receipt["regen_provider_result"], receipt["regen_provider_response_ref"] = rows, prov_res, prov_res.get("provider_response_ref")
        if rej is None and new_snap is not None:
            record_repair(artifact_dir, kind=KIND_REGEN_LLM, operation="headline_content_signal_repair", reason=trigger_reason, replaced_l2=True)
            raw_output, parsed, snap, accepted = new_raw, new_p, new_snap, True
            hl_post = str(parsed.get("headline_line", "")).strip()
            post_st = _evaluate_content_signal_state(hl_post, parsed, runtime_payload, allowed_fact_ids, pp_meta)
            receipt["accepted"], receipt["headline_post"] = True, hl_post
            receipt["families_matched_post"] = {"governance_signal": post_st["gov"], "specificity_floor": post_st["spec"], "narrowing_labels": post_st["narrow"], "segments_missing_executive_abstraction": post_st["missing_abs"], "literal_grounding": post_st["g_obs"], "resume_native_clarity": post_st["clarity"], "resume_graph_claim_binding": post_st["gb_gate"]}
        else:
            receipt["rejected_reason"] = rej or "parse_failed"
    write_json(artifact_dir / "headline_content_signal_repair_receipt.json", receipt)
    return raw_output, parsed, snap, accepted
