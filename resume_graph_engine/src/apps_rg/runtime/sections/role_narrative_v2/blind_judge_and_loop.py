"""Bounded pre-judge X2 + X1D judge-healing loop for role_narrative_v2 (zero post-LLM prose mutators)."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Callable
from apps_rg.runtime.judges.ibm_narrative_x1d import run_ibm_narrative_judges
from apps_rg.runtime.judges.unify_narrative_x1d import JUDGE_RUBRIC_VERSION as UNIFY_NARRATIVE_RUBRIC_VERSION, run_unify_narrative_judges
from apps_rg.runtime.providers.section_provider_call import call_section_model_provider
from apps_rg.runtime.section_judge_policy import get_section_judge_policy
from apps_rg.runtime.section_repair_ledger import KIND_REGEN_LLM, load_ledger, record_repair, set_authoritative_attempt
from apps_rg.runtime.sections.lane_perf_sync_helpers import build_blocked_pre_judge_rows
from apps_rg.runtime.sections.section_generation import generate_section, tag_reasoning_lane
from .evidence_firewall import write_json
from .prompt_and_generate import normalize_ibm_narrative_parsed, normalize_unify_narrative_parsed, parse_narrative_model_json
from .x2_invariants import companion_bullets_as_list, cosine_echo_diagnostic_summary, pre_judge_failed_gate_ids

def _judge_rank(rows: list[dict[str, Any]]) -> tuple[int, float]:
    active = [r for r in rows if isinstance(r, dict) and not r.get("advisory_only")]
    if not active:
        return (0, 0.0)
    scores = [float(r.get("score") or 0.0) for r in active if r.get("score") is not None]
    return (sum(1 for r in active if r.get("pass")), min(scores) if scores else 0.0)

def _format_judge_findings(x1d_rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    findings, suggestions = [], []
    for row in x1d_rows:
        if not isinstance(row, dict) or row.get("advisory_only") or row.get("pass"):
            continue
        if rat := str(row.get("rationale") or "").strip():
            findings.append(f"[{row.get('provider_name') or row.get('provider_key') or 'judge'}] {rat[:280]}")
        findings.extend(str(f).strip() for f in (row.get("findings") or []) if str(f).strip())
        suggestions.extend(str(s).strip() for s in (row.get("remediation_suggestions") or []) if str(s).strip())
    return findings, suggestions

def _record_authoritative_regen(artifact_dir: Path, operation: str, reason: str) -> None:
    record_repair(artifact_dir, kind=KIND_REGEN_LLM, operation=operation, reason=reason, replaced_l2=True)
    cur_led = load_ledger(artifact_dir) or {}
    set_authoritative_attempt(artifact_dir, 1 + sum(1 for r in (cur_led.get("repairs") or []) if r.get("kind") == KIND_REGEN_LLM and r.get("replaced_l2")), reason=operation)

def run_unify_narrative_v2_healing_loop(
    *, messages: list[dict[str, str]], provider_payload: dict[str, Any], provider_name: str, raw_output: str,
    parsed: dict[str, Any] | None, runtime_payload: dict[str, Any], artifact_dir: Path, runtime_generation_status: str,
    companion_text: str, judge_keys: list[str], judge_mode: str, allowed_fact_packet: dict[str, Any] | None,
    targeting_context: dict[str, Any] | None,
    run_x2_fn: Callable[[dict[str, Any], dict[str, Any]], list[dict[str, Any]]] | None = None,
    sync_artifacts_fn: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]], bool]:
    if sync_artifacts_fn is None:
        sync_artifacts_fn = lambda cp, _cr: cp
    if run_x2_fn is None:
        from apps_rg.runtime.validators.narrative_quality_x2 import check_narrative_bullet_cosine_similarity, check_narrative_no_consulting_language, check_narrative_seniority_floor, check_narrative_technical_specificity
        run_x2_fn = lambda cp, _cpx2: [{"gate_id": r.gate_id, "pass": r.passed} for r in (check_narrative_seniority_floor(str(cp.get("narrative_sentence") or "").strip()), check_narrative_no_consulting_language(str(cp.get("narrative_sentence") or "").strip()), check_narrative_technical_specificity(str(cp.get("narrative_sentence") or "").strip()), check_narrative_bullet_cosine_similarity(str(cp.get("narrative_sentence") or "").strip(), companion_bullets_as_list(companion_text), max_pairwise_cosine=0.35))]
    if not isinstance(parsed, dict) or runtime_generation_status != "REAL_LLM":
        return raw_output, parsed, [j.to_dict() for j in run_unify_narrative_judges(narrative_sentence=str((parsed or {}).get("narrative_sentence") or "").strip(), claim_ledger=list((parsed or {}).get("claim_ledger") or []), judge_keys=judge_keys, companion_bullets_context=companion_text, mode=judge_mode, artifact_base=artifact_dir, allowed_fact_packet=allowed_fact_packet, targeting_context=targeting_context)], False
    cur_raw, cur_parsed, any_accepted = raw_output, parsed, False
    usage_path = artifact_dir / "section_input_usage_ledger.json"
    usage_snap = usage_path.read_bytes() if usage_path.is_file() else None
    pre_failed = pre_judge_failed_gate_ids(run_x2_fn(cur_parsed, sync_artifacts_fn(cur_parsed, cur_raw)))
    healing_on = os.environ.get("APPS_RG_UNIFY_NARRATIVE_IN_LANE_HEALING", "1").strip().lower() not in ("0", "false", "no", "off")
    comp_list = companion_bullets_as_list(companion_text)
    pre_receipt: dict[str, Any] = {"attempted": False, "accepted": False, "initial_failed_gates": list(pre_failed)}
    if pre_failed and healing_on and judge_mode != "mocked":
        pre_receipt["attempted"] = True
        cur_narr = str(cur_parsed.get("narrative_sentence") or "").strip()
        pre_prompt = f"DETERMINISTIC_X2_REVISION: Draft failed unify_narrative gates: {pre_failed}.\nCurrent narrative_sentence: {cur_narr!r}\nCompanion echo diagnostic: {cosine_echo_diagnostic_summary(cur_narr, comp_list)}\nRewrite narrative_sentence as ONE crisp executive sentence (28-52 words, <=355 chars, zero digits/$/%) at Unify Consulting using a strong ownership verb and concrete mechanism vocabulary (agentic AI, GraphRAG, runtime governance) without repeating companion bullet phrases (cosine <= 0.35) or mentioning IBM/Slalom/InsurTech/EY. Cite ONLY allowed Unify source_fact_ids in claim_ledger. Return one JSON object only."
        rw_payload = {**provider_payload, "messages": [*messages, {"role": "assistant", "content": cur_raw}, {"role": "user", "content": pre_prompt}], "max_tokens": max(int(provider_payload.get("max_tokens") or 4000), 4000)}
        rw_res = call_section_model_provider(provider_name, tag_reasoning_lane(rw_payload, "unify_narrative"), artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""))
        if rw_res.runtime_generation_status == "REAL_LLM" and rw_res.raw_model_output:
            cand_in, _ = parse_narrative_model_json(rw_res.raw_model_output)
            cand_p = normalize_unify_narrative_parsed(cand_in, runtime_payload, companion_text=companion_text, allow_prose_mutation=False) if cand_in else None
            if isinstance(cand_p, dict) and str(cand_p.get("narrative_sentence") or "").strip():
                cand_failed = pre_judge_failed_gate_ids(run_x2_fn(cand_p, sync_artifacts_fn(cand_p, rw_res.raw_model_output)))
                pre_receipt["post_failed_gates"] = list(cand_failed)
                if len(cand_failed) < len(pre_failed):
                    cur_raw, cur_parsed, pre_failed, any_accepted = rw_res.raw_model_output, cand_p, cand_failed, True
                    pre_receipt["accepted"] = True
                    usage_snap = usage_path.read_bytes() if usage_path.is_file() else usage_snap
                    _record_authoritative_regen(artifact_dir, "unify_narrative_pre_judge_in_lane_rewrite", "; ".join(pre_failed[:4]) or "pre_x2_healed")
                elif usage_snap is not None:
                    usage_path.write_bytes(usage_snap)
    if pre_failed and judge_mode != "mocked":
        default_judges = tuple(get_section_judge_policy("unify_narrative").required_judge_providers) or ("gemini_pro", "openai_chatgpt")
        return cur_raw, cur_parsed, build_blocked_pre_judge_rows(section_id="unify_narrative", judge_keys=judge_keys, failed_gate_ids=pre_failed, rubric_version=UNIFY_NARRATIVE_RUBRIC_VERSION, default_judge_keys=default_judges), any_accepted
    x1d = [j.to_dict() for j in run_unify_narrative_judges(narrative_sentence=str(cur_parsed.get("narrative_sentence") or "").strip(), claim_ledger=list(cur_parsed.get("claim_ledger") or []), judge_keys=judge_keys, companion_bullets_context=companion_text, mode=judge_mode, artifact_base=artifact_dir, allowed_fact_packet=allowed_fact_packet, targeting_context=targeting_context)]
    if not healing_on or judge_mode == "mocked" or all(bool(j.get("pass", True)) for j in x1d if not j.get("advisory_only")):
        if pre_receipt["attempted"]:
            write_json(artifact_dir / "unify_narrative_judge_rewrite_receipt.json", {"attempted": True, "accepted": any_accepted, "pre_judge_rewrite": pre_receipt, "judge_feedback_rewrite": {"attempted": False, "accepted": False}})
        return cur_raw, cur_parsed, x1d, any_accepted
    findings, suggestions = _format_judge_findings(x1d)
    if not findings and not suggestions:
        if pre_receipt["attempted"]:
            write_json(artifact_dir / "unify_narrative_judge_rewrite_receipt.json", {"attempted": True, "accepted": any_accepted, "pre_judge_rewrite": pre_receipt, "judge_feedback_rewrite": {"attempted": False, "accepted": False}})
        return cur_raw, cur_parsed, x1d, any_accepted
    old_rank, cur_narr = _judge_rank(x1d), str(cur_parsed.get("narrative_sentence") or "").strip()
    j_prompt = f"X1D_JUDGE_FEEDBACK_REVISION:\nFindings: {findings[:6]}\nSuggestions: {suggestions[:5]}\nCompanion echo diagnostic: {cosine_echo_diagnostic_summary(cur_narr, comp_list)}\nRewrite narrative_sentence and claim_ledger in ONE crisp executive sentence (28-52 words, <=355 chars, zero digits/$/%) grounded strictly in Unify Consulting facts in ALLOWED_FACT_PACKET with pairwise content cosine <= 0.35 against companion bullets. Return one JSON object only."
    rw_payload = {**provider_payload, "messages": [*messages, {"role": "assistant", "content": cur_raw}, {"role": "user", "content": j_prompt}], "max_tokens": max(int(provider_payload.get("max_tokens") or 4000), 4000)}
    rw_res = call_section_model_provider(provider_name, tag_reasoning_lane(rw_payload, "unify_narrative"), artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""))
    jf_receipt: dict[str, Any] = {"attempted": True, "accepted": False, "old_rank": list(old_rank)}
    receipt: dict[str, Any] = {"attempted": True, "accepted": False, "old_rank": list(old_rank), "pre_judge_rewrite": pre_receipt, "judge_feedback_rewrite": jf_receipt}
    if rw_res.runtime_generation_status == "REAL_LLM" and rw_res.raw_model_output:
        cand_in, _ = parse_narrative_model_json(rw_res.raw_model_output)
        cand_p = normalize_unify_narrative_parsed(cand_in, runtime_payload, companion_text=companion_text, allow_prose_mutation=False) if cand_in else None
        if isinstance(cand_p, dict) and str(cand_p.get("narrative_sentence") or "").strip():
            cand_failed = pre_judge_failed_gate_ids(run_x2_fn(cand_p, sync_artifacts_fn(cand_p, rw_res.raw_model_output)))
            if not cand_failed:
                cand_x1d = [j.to_dict() for j in run_unify_narrative_judges(narrative_sentence=str(cand_p.get("narrative_sentence") or "").strip(), claim_ledger=list(cand_p.get("claim_ledger") or []), judge_keys=judge_keys, companion_bullets_context=companion_text, mode=judge_mode, artifact_base=artifact_dir, allowed_fact_packet=allowed_fact_packet, targeting_context=targeting_context)]
                new_rank = _judge_rank(cand_x1d)
                receipt["new_rank"] = jf_receipt["new_rank"] = list(new_rank)
                if new_rank > old_rank:
                    receipt["accepted"] = jf_receipt["accepted"] = True
                    write_json(artifact_dir / "unify_narrative_judge_rewrite_receipt.json", receipt)
                    _record_authoritative_regen(artifact_dir, "unify_narrative_x1d_judge_feedback_rewrite", "; ".join(findings[:2])[:160] or "x1d_judge_feedback")
                    return rw_res.raw_model_output, cand_p, cand_x1d, True
                receipt["rejected_reason"] = jf_receipt["rejected_reason"] = "rejudge_not_improved"
            else:
                receipt["rejected_reason"] = jf_receipt["rejected_reason"] = f"x2_failed_after_rewrite:{cand_failed}"
            if usage_snap is not None:
                usage_path.write_bytes(usage_snap)
    write_json(artifact_dir / "unify_narrative_judge_rewrite_receipt.json", receipt)
    return cur_raw, cur_parsed, x1d, any_accepted

def apply_ibm_narrative_judge_feedback_rewrite(
    *, messages: list[dict[str, str]], provider_payload: dict[str, Any], raw_output: str, parsed: dict[str, Any] | None,
    x1d: list[dict[str, Any]], runtime_payload: dict[str, Any], artifact_dir: Path, runtime_generation_status: str,
    companion_text: str, judge_keys: list[str], judge_mode: str, allowed_fact_packet: dict[str, Any] | None = None,
    targeting_context: dict[str, Any] | None = None, x2_check_fn: Callable[[dict[str, Any], str], list[str]] | None = None,
) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]], bool]:
    if not isinstance(parsed, dict) or runtime_generation_status != "REAL_LLM" or judge_mode == "mocked" or all(bool(j.get("pass", True)) for j in x1d if isinstance(j, dict) and not j.get("advisory_only")):
        return raw_output, parsed, x1d, False
    findings, suggestions = _format_judge_findings(x1d)
    if not findings and not suggestions:
        return raw_output, parsed, x1d, False
    old_rank = _judge_rank(x1d)
    usage_path = artifact_dir / "section_input_usage_ledger.json"
    usage_snap = usage_path.read_bytes() if usage_path.is_file() else None
    cur_narr = str(parsed.get("narrative_sentence") or "").strip()
    prompt = f"X1D_JUDGE_FEEDBACK_REVISION:\nFindings: {findings[:6]}\nSuggestions: {suggestions[:5]}\nCompanion echo diagnostic: {cosine_echo_diagnostic_summary(cur_narr, companion_bullets_as_list(companion_text))}\nRewrite narrative_sentence and claim_ledger from scratch in ONE crisp executive sentence (<=58 words, <=360 chars) at IBM synthesizing 2 to 4 concrete delivered technical capabilities attested in the companion IBM bullets using ', establishing' clause structure, citing ONLY literal bul_ibm_001..bul_ibm_005 IDs (max 2 per clause row), and keeping pairwise content cosine <= 0.35 with each companion bullet. Return one JSON object only."
    rw_payload = {**provider_payload, "messages": [*messages, {"role": "assistant", "content": raw_output}, {"role": "user", "content": prompt}], "max_tokens": max(int(provider_payload.get("max_tokens") or 4000), 4000)}
    res = generate_section(tag_reasoning_lane(rw_payload, "ibm_narrative"), artifact_dir=artifact_dir, run_id=str(runtime_payload.get("run_id") or ""))
    receipt: dict[str, Any] = {"attempted": True, "accepted": False, "old_rank": list(old_rank)}
    if res.runtime_generation_status != "REAL_LLM" or not res.raw_model_output:
        receipt["rejected_reason"] = "provider_not_real_llm"
        write_json(artifact_dir / "ibm_narrative_judge_rewrite_receipt.json", receipt)
        return raw_output, parsed, x1d, False
    cand_raw = str(res.raw_model_output or "")
    cand_in, _ = parse_narrative_model_json(cand_raw)
    cand_parsed = normalize_ibm_narrative_parsed(cand_in, runtime_payload, companion_text, allow_echo_repair=False) if cand_in else None
    if not isinstance(cand_parsed, dict) or not str(cand_parsed.get("narrative_sentence") or "").strip():
        receipt["rejected_reason"] = "parse_failed"
        write_json(artifact_dir / "ibm_narrative_judge_rewrite_receipt.json", receipt)
        return raw_output, parsed, x1d, False
    if x2_check_fn is not None and (x2_errs := x2_check_fn(cand_parsed, cand_raw)):
        if usage_snap is not None:
            usage_path.write_bytes(usage_snap)
        receipt["rejected_reason"] = f"x2_failed_after_rewrite:{x2_errs}"
        write_json(artifact_dir / "ibm_narrative_judge_rewrite_receipt.json", receipt)
        return raw_output, parsed, x1d, False
    cand_x1d = [j.to_dict() for j in run_ibm_narrative_judges(narrative_sentence=str(cand_parsed.get("narrative_sentence") or "").strip(), claim_ledger=list(cand_parsed.get("claim_ledger") or []), judge_keys=judge_keys, companion_bullets_context=companion_text, mode=judge_mode, artifact_base=artifact_dir, allowed_fact_packet=allowed_fact_packet, targeting_context=targeting_context)]
    new_rank = _judge_rank(cand_x1d)
    receipt["new_rank"] = list(new_rank)
    if new_rank <= old_rank:
        if usage_snap is not None:
            usage_path.write_bytes(usage_snap)
        receipt["rejected_reason"] = "rejudge_not_improved"
        write_json(artifact_dir / "ibm_narrative_judge_rewrite_receipt.json", receipt)
        return raw_output, parsed, x1d, False
    receipt["accepted"] = True
    write_json(artifact_dir / "ibm_narrative_judge_rewrite_receipt.json", receipt)
    _record_authoritative_regen(artifact_dir, "ibm_narrative_x1d_judge_feedback_rewrite", "; ".join(findings[:2])[:160] or "x1d_judge_feedback")
    return cand_raw, cand_parsed, cand_x1d, True
