"""PA prompt compiler, shared-vocabulary contract, and non-mutating JSON normalization for headline_v2."""
from __future__ import annotations
import json, re
from typing import Any
from apps_rg.runtime.contracts.prompt_validator_vocab_ssot import APPROVED_HEADLINE_SENIORITY_PREFIXES, HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS, HEADLINE_EXECUTIVE_ABSTRACTION_RE, HEADLINE_FORBIDDEN_PLUMBING_LABELS
from apps_rg.runtime.sections.headline_fact_id_resolution import apply_headline_claim_ledger_fact_id_resolution, proof_pool_requires_canonical_fact_namespace
from apps_rg.runtime.sections.headline_pa import compile_headline_prompt
from apps_rg.runtime.sections.lane_perf_sync_helpers import compact_overlong_headline_and_ledger
from apps_rg.runtime.sections.section_product_shape_ssot import HEADLINE_WORD_MAX, HEADLINE_WORD_MIN
from apps_rg.runtime.validators.headline_x2 import has_valid_headline_prefix, headline_runtime_self_check_truth, headline_word_count
from .evidence_firewall import HEADLINE_SELF_CHECK_PROOF_KEYS, bind_headline_graph_skill_lineage, coerce_segment_claim_ledger_rows, ensure_claim_ledger, sync_selected_fact_plan_required_ids
from .x2_invariants import headline_resume_native_clarity_report

SHARED_HEADLINE_VOCAB_SUMMARY: dict[str, Any] = {"approved_seniority_prefixes": APPROVED_HEADLINE_SENIORITY_PREFIXES, "executive_abstraction_nouns": HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS, "executive_abstraction_pattern": HEADLINE_EXECUTIVE_ABSTRACTION_RE.pattern, "forbidden_plumbing_labels": HEADLINE_FORBIDDEN_PLUMBING_LABELS}
_MACHINE_HEADLINE_SEGMENT_REWRITES: dict[str, str] = {"governed runtime architecture": "Runtime Governance Architecture", "governed runtime spine": "Runtime Governance Architecture", "runtime spine": "Runtime Governance Architecture", "governed runtime backbone": "Runtime Governance Architecture", "runtime backbone": "Runtime Governance Architecture", "partner alliance cosell": "Co-Sell Channel Alliance", "partner alliance co-sell": "Co-Sell Channel Alliance", "partner alliance co sell": "Co-Sell Channel Alliance", "hyperscaler alliance revenue": "Hyperscaler Partner Ecosystem", "runtime governance telemetry controls": "Runtime Governance", "agentic platform control plane": "Agentic Platform Architecture", "enterprise solution portfolio expansion": "Enterprise Portfolio Expansion", "portfolio quota leadership": "Enterprise Portfolio Leadership", "policy administration migration": "Policy Administration Platforms", "policy administration modernization": "Policy Administration Platforms", "aws migration execution": "Policy Administration Platforms", "aws migration modernization execution": "Policy Administration Platforms", "aws modernization execution": "Policy Administration Platforms", "regulated aws migration": "Regulated AWS Migration Execution", "governed data infrastructure": "Distributed Cloud Data Governance", "insurance platform migration": "Regulated Insurance Platforms", "aws insurance modernization": "Insurance Platform Modernization", "aws insurance modernization architecture": "Insurance Platform Modernization", "aws insurance modernization platform": "Insurance Platform Modernization", "insurance cloud modernization platform": "Insurance Platform Modernization", "insurance modernization architecture": "Insurance Platform Modernization", "legacy cloud modernization": "Insurance Platform Modernization", "legacy cloud modernization platform": "Insurance Platform Modernization", "governed override escalation": "Human Override Escalation Governance", "runtime gate mesh governance": "Runtime Gate Architecture", "runtime gate mesh": "Runtime Gate Architecture", "runtime gate governance": "Runtime Gate Architecture", "audit grade observability controls": "Audit Observability Controls", "audit grade observability systems": "Audit Observability Controls", "audit grade observability": "Audit Observability Controls", "three lines governance": "Regulated Insurance Governance", "three lines risk governance": "Regulated Insurance Governance", "three lines of defense governance": "Regulated Insurance Governance", "client adoption systems": "Cloud Data Modernization", "hyperscaler alliance ecosystem": "Hyperscaler Partner Ecosystem"}

def build_prompt_messages(runtime_payload: dict[str, Any], companion_context: str, fact_lines: str, employer_names: str) -> list[dict[str, str]]:
    return compile_headline_prompt(runtime_payload, companion_context=companion_context, fact_lines=fact_lines, forbidden_employer_lines=employer_names, run_id=str(runtime_payload.get("run_id") or "headline_prompt_build")).artifact.messages

def parse_model_json(raw: str) -> tuple[dict[str, Any] | None, str]:
    text = re.sub(r"```$", "", re.sub(r"^```(?:json)?", "", raw.strip()).strip()).strip()
    try:
        parsed = json.loads(text)
        return (parsed, "") if isinstance(parsed, dict) else (None, "Model output was not a JSON object.")
    except json.JSONDecodeError as exc:
        return None, f"JSON parse failed: {exc}"

def _rewrite_partner_enablement_segment(headline_line: str, *, selected_fact_plan: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None]:
    hl = str(headline_line or "").strip()
    if not hl or "gsi" not in hl.lower() or "enablement" not in hl.lower():
        return hl, None
    sfp = selected_fact_plan if isinstance(selected_fact_plan, dict) else {}
    skill_sources = {str(sk.get("skill_id") if isinstance(sk, dict) else sk or "").strip() for sk in [*(sfp.get("selected_skills") or []), *(sfp.get("selected_skill_ids") or [])] if str(sk.get("skill_id") if isinstance(sk, dict) else sk or "").strip()}
    if not (matched := skill_sources & {"skill_partner_partner_led_ai_solutions", "skill_partner_cloud_vendor_joint_gtm", "skill_partner_gtm_enablement"}):
        return hl, None
    parts = [p.strip() for p in hl.split(" | ")]
    if len(parts) != 4 or not re.search(r"\bgsi\b", parts[2], re.IGNORECASE) or not re.search(r"\benablement\b", parts[2], re.IGNORECASE) or parts[2] == "Partner-Led AI Solutions":
        return hl, None
    old_seg = parts[2]
    parts[2] = "Partner-Led AI Solutions"
    return " | ".join(parts), {"from": old_seg, "to": "Partner-Led AI Solutions", "selected_skill_ids": sorted(matched)}

def rewrite_machine_headline_segments(headline_line: str) -> tuple[str, list[dict[str, str]]]:
    hl = str(headline_line or "").strip()
    parts = [p.strip() for p in hl.split(" | ")]
    if len(parts) != 4 or not has_valid_headline_prefix(hl):
        return hl, []
    changes: list[dict[str, str]] = []
    for idx in range(1, 4):
        if (rep := _MACHINE_HEADLINE_SEGMENT_REWRITES.get(parts[idx].strip().lower())) and rep != parts[idx]:
            changes.append({"from": parts[idx], "to": rep})
            parts[idx] = rep
    return " | ".join(parts), changes

def deterministic_headline_word_count_expand(headline_line: str) -> str:
    hl = str(headline_line or "").strip()
    wc = headline_word_count(hl)
    if HEADLINE_WORD_MIN <= wc <= HEADLINE_WORD_MAX or wc >= 10 or not has_valid_headline_prefix(hl) or hl.count(" | ") != 3:
        return hl
    parts = [p.strip() for p in hl.split(" | ")]
    if len(parts) != 4:
        return hl
    for seg_idx, pattern, token in ((1, r"\balliance\s+co-?sell\b", "Motions"), (3, r"\bpartner\s+co-?sell\b", "Motions"), (1, r"\bruntime\s+governance\b", "Architecture"), (2, r"\bdatabricks\s+lakehouse\b", "Platform"), (1, r"\bgoverned\s+runtime\b", "Architecture"), (2, r"\bproduction\s+reliability\b", "Systems")):
        if re.search(pattern, parts[seg_idx], re.IGNORECASE) and not re.search(rf"\b{re.escape(token)}\b", parts[seg_idx], re.IGNORECASE):
            trial = " | ".join([*parts[:seg_idx], f"{parts[seg_idx]} {token}".strip(), *parts[seg_idx + 1:]])
            if HEADLINE_WORD_MIN <= headline_word_count(trial) <= HEADLINE_WORD_MAX:
                return trial
    return hl

def normalize_parsed_output(
    parsed: dict[str, Any] | None, runtime_payload: dict[str, Any], allowed_fact_ids: set[str], headline_line: str,
    *, companion_nonempty: bool = False, employer_names_lower: list[str] | None = None,
    proof_pool_metadata: dict[str, Any] | None = None, allow_prose_mutation: bool = True,
) -> dict[str, Any] | None:
    if not parsed:
        return parsed
    out = dict(parsed)
    hl = str(out.get("headline_line") or headline_line or "").strip()
    if allow_prose_mutation:
        sfp_repair = out.get("selected_fact_plan") if isinstance(out.get("selected_fact_plan"), dict) else runtime_payload.get("selected_fact_plan")
        repaired_hl, repaired_meta = _rewrite_partner_enablement_segment(hl, selected_fact_plan=sfp_repair if isinstance(sfp_repair, dict) else None)
        if repaired_meta is not None and repaired_hl != hl:
            hl = out["headline_line"] = repaired_hl
            if isinstance(cl := out.setdefault("change_log", []), list):
                cl.append({"operation": "headline_partner_enablement_grounding_repair", "reason": "replace_abstract_gsi_enablement_with_grounded_partner_label", **repaired_meta})
        machine_hl, machine_repairs = rewrite_machine_headline_segments(hl)
        if machine_repairs and machine_hl != hl:
            hl = out["headline_line"] = machine_hl
            if isinstance(cl := out.setdefault("change_log", []), list):
                cl.append({"operation": "headline_machine_phrase_repair", "reason": "replace_unnatural_aiish_segment_with_positioning_family_phrase", "repairs": machine_repairs})
        expanded_hl = deterministic_headline_word_count_expand(hl)
        if expanded_hl != hl:
            if isinstance(cl := out.setdefault("change_log", []), list):
                cl.append({"operation": "headline_word_count_deterministic_expand", "reason": f"word_count={headline_word_count(hl)} below {HEADLINE_WORD_MIN}", "from": hl, "to": expanded_hl})
            hl = expanded_hl
        hl = compact_overlong_headline_and_ledger(hl, out, clarity_report_fn=headline_resume_native_clarity_report)
    out["headline_line"] = hl
    jd = dict(out.get("jd_alignment") or {})
    jd.setdefault("targeting_only", True)
    if companion_nonempty:
        jd.setdefault("companion_context_used", True)
    out["jd_alignment"] = jd
    out.setdefault("gap_notes", [])
    out.setdefault("change_log", [])
    pp_meta = proof_pool_metadata if proof_pool_metadata is not None else runtime_payload.get("proof_pool_metadata")
    retain_aliases = proof_pool_requires_canonical_fact_namespace(pp_meta if isinstance(pp_meta, dict) else None)
    ensure_claim_ledger(hl, out, allowed_fact_ids, retain_bullet_aliases=retain_aliases)
    if retain_aliases:
        rows_before = len(list(out.get("claim_ledger") or []))
        out, resolution_receipt = apply_headline_claim_ledger_fact_id_resolution(out, srfs_allowed_fact_ids=allowed_fact_ids, runtime_payload=runtime_payload, proof_pool_metadata=pp_meta if isinstance(pp_meta, dict) else {})
        if resolution_receipt is not None:
            out["fact_id_resolution_receipt"] = resolution_receipt
        if rows_before > (rows_after := len(list(out.get("claim_ledger") or []))):
            out["_headline_ledger_rows_dropped"] = int(out.get("_headline_ledger_rows_dropped") or 0) + (rows_before - rows_after)
        ensure_claim_ledger(hl, out, allowed_fact_ids, retain_bullet_aliases=False)
    sync_selected_fact_plan_required_ids(out, runtime_payload, allowed_fact_ids)
    bind_headline_graph_skill_lineage(out)
    sc_out: dict[str, Any] = dict(sc_in) if isinstance(sc_in := out.get("self_check"), dict) else {}
    rt_sc = headline_runtime_self_check_truth(hl, target_company=str(runtime_payload.get("target_company") or "").strip(), employer_names_lower=list(employer_names_lower or []))
    for key in HEADLINE_SELF_CHECK_PROOF_KEYS:
        sc_out[key] = rt_sc[key]
    out["self_check"] = sc_out
    return out

def build_mock_output(runtime_payload: dict[str, Any]) -> dict[str, Any]:
    hl = "SVP Engineering | Governed Agentic Platforms | Runtime Infrastructure | Regulated Delivery"
    wc = headline_word_count(hl)
    facts = list((runtime_payload.get("selected_fact_plan") or {}).get("facts") or [])
    stub_ids = [str(f.get("fact_id") or "").strip() for f in facts if f.get("fact_id")] or list((runtime_payload.get("allowed_fact_ids") or [])[:6]) or ["bul_unify_001", "bul_ibm_001", "bul_unify_004"]
    claim_ledger = coerce_segment_claim_ledger_rows(hl, stub_ids) or [{"claim_text": hl, "source_fact_ids": stub_ids}]
    return {"headline_line": hl, "selected_fact_plan": runtime_payload["selected_fact_plan"], "claim_ledger": claim_ledger, "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False, "briefing_used_as_proof": False, "companion_used_as_proof": False, "selected_theme": "agentic_platforms", "anti_stuffing_check": "passed"}, "gap_notes": [], "change_log": [{"operation": "mocked_runtime_slice", "reason": "provider not requested"}], "self_check": {"fixed_prefix": True, "segment_count": 4, "separator_count": 3, "word_count": wc, "word_count_in_range": True, "no_metrics": True, "no_company_names": True, "no_employer_names": True, "no_jd_phrase_lift": True, "base_identity_preserved": True, "jd_used_as_targeting_only": True}}
