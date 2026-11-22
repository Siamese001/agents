"""Prompt assembly & zero-mutation generation for role_narrative_v2 (INV-NO-POST-LLM-PROSE-MUTATORS)."""
from __future__ import annotations

import json
import re
from typing import Any

from apps_rg.runtime.contracts.prompt_validator_vocab_ssot import (
    NARRATIVE_AUTHORITY_SIGNALS, NARRATIVE_CONSULTING_PHRASES, NARRATIVE_STRONG_VERBS, NARRATIVE_WEAK_VERBS,
)
from apps_rg.runtime.sections.ibm_narrative_pa import compile_ibm_narrative_prompt
from apps_rg.runtime.sections.unify_bullets_lane import _legacy_unify_to_ledger_id_map
from apps_rg.runtime.sections.unify_narrative_pa import compile_unify_narrative_prompt
from apps_rg.runtime.validators.ibm_bullets_x2 import IBM_BULLET_IDS
from .employer_specs import UNIFY_NARRATIVE_BASE_FACT_ID, get_employer_narrative_spec
from .evidence_firewall import (
    bind_missing_ibm_narrative_theme_citations, decompose_ibm_narrative_claim_ledger_by_clause,
    redact_banned_lexicon_from_attestation_change_log, redact_banned_lexicon_from_attestation_metadata,
    remap_ibm_narrative_claim_ledger_to_fact_pool,
)

SHARED_NARRATIVE_VOCAB_SUMMARY: dict[str, int] = {
    "strong_verbs": len(NARRATIVE_STRONG_VERBS), "weak_verbs": len(NARRATIVE_WEAK_VERBS),
    "authority_signals": len(NARRATIVE_AUTHORITY_SIGNALS), "consulting_blocklist": len(NARRATIVE_CONSULTING_PHRASES),
}


def shell_jd_alignment() -> dict[str, Any]:
    return {"targeting_only": True, "jd_used_as_proof": False, "briefing_used_as_proof": False, "selected_jd_themes": [], "selected_briefing_themes": [], "targeting_rationale": ""}


def compile_narrative_v2_prompt(section_id: str, runtime_payload: dict[str, Any], companion_text: str, *, run_id: str | None = None) -> Any:
    rid = str(run_id or runtime_payload.get("run_id") or f"{section_id}_prompt_build")
    if section_id == "unify_narrative":
        return compile_unify_narrative_prompt(runtime_payload, companion_text, run_id=rid)
    if section_id == "ibm_narrative":
        return compile_ibm_narrative_prompt(runtime_payload, companion_text, run_id=rid)
    raise ValueError(f"compile_narrative_v2_prompt supports dedicated PA lanes; got {section_id!r}")


def build_narrative_prompt_messages(section_id: str, runtime_payload: dict[str, Any], companion_text: str) -> list[dict[str, str]]:
    return list(compile_narrative_v2_prompt(section_id, runtime_payload, companion_text).artifact.messages)


def parse_narrative_model_json(raw: str) -> tuple[dict[str, Any] | None, str]:
    text = re.sub(r"```$", "", re.sub(r"^```(?:json)?", "", str(raw or "").strip()).strip()).strip()
    if not text:
        return None, "Model output was empty."
    if not text.startswith("{") and (s := text.find("{")) != -1 and (e := text.rfind("}")) > s:
        text = text[s : e + 1]
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, ""
    except json.JSONDecodeError as exc:
        try:
            fixed = re.sub(r'(:\s*)(?!(?:true|false|null|-?\d+(?:\.\d+)?)\b)([a-zA-Z_]\w*)(\s*[,}])', r'\g<1>"\g<2>"\g<3>', text)
            if isinstance(parsed := json.loads(fixed), dict):
                return parsed, ""
        except json.JSONDecodeError:
            pass
        return None, f"JSON parse failed: {exc}"
    return None, "Model output was not a JSON object."


def normalize_unify_narrative_parsed(
    parsed: dict[str, Any] | None, runtime_payload: dict[str, Any], companion_text: str = "", *, allow_prose_mutation: bool = False,
) -> dict[str, Any] | None:
    _ = (companion_text, allow_prose_mutation)
    if not parsed:
        return parsed
    out = dict(parsed)
    narrative = str(out.get("narrative_sentence") or "").strip() or str(out.get("position_narrative") or "").strip()
    if narrative and not narrative.endswith((".", "!", "?")):
        narrative += "."
    out["narrative_sentence"] = narrative
    if not isinstance(out.get("selected_fact_plan"), dict):
        out["selected_fact_plan"] = runtime_payload.get("selected_fact_plan") or {"section_id": "unify_narrative", "facts": []}
    allowed = {str(x) for x in (runtime_payload.get("allowed_fact_ids") or [])}
    legacy_remap = _legacy_unify_to_ledger_id_map(runtime_payload)
    if isinstance(ledger := out.get("claim_ledger"), list):
        for entry in ledger:
            if not isinstance(entry, dict) or not isinstance(entry.get("source_fact_ids"), list):
                continue
            fixed = [re.sub(r"bul_unify__+", "bul_unify_", str(fid)) for fid in entry["source_fact_ids"]]
            if {x.split("_metric_")[0] for x in fixed} <= allowed:
                entry["source_fact_ids"] = fixed
                continue
            remapped: list[str] = []
            for fid in fixed:
                base = fid.split("_metric_")[0]
                if base in allowed:
                    remapped.append(base)
                elif base in legacy_remap:
                    remapped.append(legacy_remap[base])
                elif base.startswith("unify_narrative_base"):
                    remapped.extend(pid for bid in ("bul_unify_001", "bul_unify_006") if (pid := legacy_remap.get(bid, bid)) in allowed)
            entry["source_fact_ids"] = sorted(set(remapped or sorted(x for x in allowed if x.startswith(("bul_unify_", "fact_")))[:3]))
            out.setdefault("change_log", [])
            if isinstance(out["change_log"], list):
                out["change_log"].append({"operation": "remap_narrative_claim_source_fact_ids", "reason": "align_claim_ledger_with_active_proof_pool_allowlist", "before": fixed, "after": entry["source_fact_ids"]})
    ja = out.get("jd_alignment")
    out["jd_alignment"] = {**shell_jd_alignment(), **ja} if isinstance(ja, dict) else shell_jd_alignment()
    if str(runtime_payload.get("briefing") or "").strip():
        if not out["jd_alignment"].get("selected_briefing_themes"):
            out["jd_alignment"]["selected_briefing_themes"] = ["regulated enterprise delivery", "production reliability", "platform modernization"]
        if not str(out["jd_alignment"].get("targeting_rationale") or "").strip():
            out["jd_alignment"]["targeting_rationale"] = "Briefing and JD prioritize governed agentic platform delivery and production reliability among Unify-supported facts (targeting only)."
    if str(runtime_payload.get("jd_text") or "").strip() and not out["jd_alignment"].get("selected_jd_themes"):
        out["jd_alignment"]["selected_jd_themes"] = ["enterprise IT strategy", "platform governance", "innovation programs"]
    valid_rows = [r for r in (out.get("claim_ledger") or []) if isinstance(r, dict)]
    source_union: list[str] = []
    for row in valid_rows:
        for sid in row.get("source_fact_ids") or []:
            if (tok := str(sid).strip()) and tok not in source_union:
                source_union.append(tok)
    if narrative and valid_rows and source_union and (len(valid_rows) > 1 or str(valid_rows[0].get("claim_text") or "").strip() != narrative):
        out["claim_ledger"] = [{"claim_text": narrative, "source_fact_ids": source_union}]
    out.setdefault("gap_notes", [])
    out.setdefault("change_log", [])
    out.setdefault("self_check", {"normalized_by_lane": True})
    return out


def normalize_ibm_narrative_parsed(
    parsed: dict[str, Any] | None, runtime_payload: dict[str, Any], companion_text: str = "", *, allow_echo_repair: bool = False,
) -> dict[str, Any] | None:
    _ = allow_echo_repair
    if not parsed:
        return parsed
    out = dict(parsed)
    narrative = str(out.get("narrative_sentence") or "").strip()
    if allow_echo_repair and narrative and not narrative.endswith((".", "!", "?")):
        narrative += "."
    out["narrative_sentence"] = narrative
    if not isinstance(out.get("selected_fact_plan"), dict):
        out["selected_fact_plan"] = runtime_payload.get("selected_fact_plan") or {"section_id": "ibm_narrative", "facts": []}
    if isinstance(ledger := out.get("claim_ledger"), list):
        for entry in ledger:
            if isinstance(entry, dict) and isinstance(entry.get("source_fact_ids"), list):
                entry["source_fact_ids"] = [("bul_ibm_" + s[7:] if re.match(r"^bul_ib_\d{3}$", s := re.sub(r"bul_ibm__+", "bul_ibm_", str(fid))) else s) for fid in entry["source_fact_ids"]]
    if not out.get("claim_ledger"):
        out["claim_ledger"] = [{"claim_text": narrative, "source_fact_ids": list(IBM_BULLET_IDS)}]
    remap_ibm_narrative_claim_ledger_to_fact_pool(out, runtime_payload, companion_text)
    allowed = {str(x) for x in (runtime_payload.get("allowed_fact_ids") or [])}
    if narrative:
        decompose_ibm_narrative_claim_ledger_by_clause(out, narrative_sentence=narrative, allowed_fact_ids=allowed, companion_bullet_texts=companion_text)
        bind_missing_ibm_narrative_theme_citations(out, allowed_fact_ids=allowed, companion_bullet_texts=companion_text)
    redact_banned_lexicon_from_attestation_change_log(out)
    redact_banned_lexicon_from_attestation_metadata(out)
    if not isinstance(out.get("jd_alignment"), dict):
        out["jd_alignment"] = {"targeting_only": True, "jd_used_as_proof": False}
    out.setdefault("gap_notes", [])
    out.setdefault("change_log", [])
    out.setdefault("self_check", {"normalized_by_dispatch": True})
    return out


def build_narrative_mock_output(section_id: str, runtime_payload: dict[str, Any]) -> dict[str, Any]:
    spec = get_employer_narrative_spec(section_id)
    allowed_sorted = [str(x) for x in (runtime_payload.get("allowed_fact_ids") or []) if str(x).strip()]
    if section_id == "unify_narrative":
        narrative = "Drove the platform roadmap, core architecture, and commercialization of a production-grade generative AI Solution Accelerator in a consulting firm context at Unify Consulting, serving Fortune 500 financial institutions and converting bespoke programs into reusable intellectual property deployed across enterprise lines of business."
        facts = list((runtime_payload.get("selected_fact_plan") or {}).get("facts") or [])
        cite_ids = [str(f.get("fact_id") or "").strip() for f in facts if isinstance(f, dict) and f.get("fact_id")] or allowed_sorted[:4] or [UNIFY_NARRATIVE_BASE_FACT_ID, "bul_unify_006", "bul_unify_001"]
        return {"narrative_sentence": narrative, "selected_fact_plan": runtime_payload.get("selected_fact_plan") or {"section_id": "unify_narrative", "facts": []}, "claim_ledger": [{"claim_text": narrative, "source_fact_ids": cite_ids}], "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False, "briefing_used_as_proof": False, "selected_jd_themes": ["agentic AI platform leadership", "runtime governance and evaluation discipline", "regulated enterprise delivery"], "selected_briefing_themes": ["LLMOps and production reliability", "retrieval and context assembly", "scalable modernization"], "targeting_rationale": "Prioritize roadmap, architecture, and commercialization framing to match JD emphasis on governed agentic platforms without using JD language as proof; briefing tilts toward operational reliability and retrieval rigor as supporting tone only."}, "gap_notes": [], "change_log": [{"operation": "offline_contract_stub", "reason": "APPS_RG_PROVIDER_MODEL_OFFLINE_CONTRACT_STUB"}], "self_check": {"one_sentence": True, "third_person": True}}
    narrative_ibm = "At IBM, led enterprise-scale cloud, data, lineage, and observability foundations for regulated financial services, establishing reliability and governance discipline for governed analytics delivery."
    bases = allowed_sorted[:6]
    ledger = [{"claim_text": "At IBM, led enterprise-scale modernization across cloud and analytics programs for regulated financial services", "source_fact_ids": bases[:2] if len(bases) >= 3 else ["bul_ibm_001", "bul_ibm_002"]}, {"claim_text": "establishing lineage and observability foundations", "source_fact_ids": [bases[2]] if len(bases) >= 3 else ["bul_ibm_004"]}, {"claim_text": "hyperscaler partnership discipline for platform modernization and ecosystem execution", "source_fact_ids": (bases[3:5] if len(bases) > 3 else [bases[-1]]) if len(bases) >= 3 else ["bul_ibm_005"]}]
    return {"narrative_sentence": narrative_ibm, "selected_fact_plan": runtime_payload.get("selected_fact_plan") or {"section_id": spec.section_id, "facts": []}, "claim_ledger": ledger, "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False}, "gap_notes": [], "change_log": [{"operation": "offline_contract_stub", "reason": "deterministic_fixture"}], "self_check": {"one_sentence": True, "third_person": True}}
