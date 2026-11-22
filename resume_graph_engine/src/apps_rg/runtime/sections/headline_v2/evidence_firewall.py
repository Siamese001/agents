"""Evidence firewall, non-prose claim-ledger segment binder, and defaults for headline_v2."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from typing import Any, Mapping
from apps_rg.config.runtime_env import get_runtime_env_str, get_runtime_environ
from apps_rg.runtime.briefing_resolution import resolve_briefing_for_lanes
from apps_rg.runtime.claim_ledger.headline_claim_ledger import _headline_positioning_segments
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.jd_resolution import resolve_jd_for_lanes
from apps_rg.runtime.offline_contract_status import OFFLINE_CONTRACT_STUB_RUNTIME_STATUS
from apps_rg.runtime.sections.graph_evidence_contract import build_graph_evidence_runtime_payload, build_selected_graph_evidence_plan
from apps_rg.runtime.validators.fact_id_typo_repair import repair_fact_id_against_allowlist
from apps_rg.runtime.validators.headline_x2 import polish_claim_text_when_headline_has_no_metrics

PROMPT_ID, LANE_KEY, HEADLINE_TEMP_DEFAULT, HEADLINE_MAX_OUTPUT_TOKENS = "headline_section_v1", "headline", 0.55, 2400
TARGET_TITLE_DEFAULT, TARGET_COMPANY_DEFAULT = "SVP Engineering, Agentic AI Platforms", "Synthetic Enterprise Corp."
JD_TEXT_DEFAULT = resolve_jd_for_lanes().description
BRIEFING_DEFAULT = resolve_briefing_for_lanes(briefing_artifact_ref=None).text
TRACE_RUNTIME_PATH_DEFAULT = "apps_rg.runtime.sections.headline_lane"
HEADLINE_JSON_OUTPUT_STATUSES: frozenset[str] = frozenset({"REAL_LLM", OFFLINE_CONTRACT_STUB_RUNTIME_STATUS})
HEADLINE_SELF_CHECK_PROOF_KEYS: tuple[str, ...] = ("word_count", "segment_count", "separator_count", "word_count_in_range", "fixed_prefix", "no_metrics", "no_employer_names", "no_company_names")
RELEASE_HEADLINE_CONTENT_SIGNAL_REPAIR_ENABLED, CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS, CONTENT_SIGNAL_REPAIR_LIVE_MAX_ATTEMPTS = True, 3, 1
_FORBIDDEN_BACKOFFICE_HEADLINE_SEGMENTS: frozenset[str] = frozenset({"three lines governance", "three lines risk governance", "client adoption systems"})
_SHARP_POSITIONING_SEGMENT_REWRITES: dict[str, str] = {"three lines governance": "Regulated Insurance Governance", "three lines risk governance": "Regulated Insurance Governance", "three lines of defense governance": "Regulated Insurance Governance", "client adoption systems": "Cloud Data Modernization", "client value realization systems": "Cloud Data Modernization", "regulated aws migration execution": "Cloud Data Modernization", "regulated insurance cloud modernization": "Cloud Data Modernization", "governed agentic ai platforms": "Agentic AI Platforms", "enterprise agentic ai platforms": "Agentic AI Platforms"}

def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    return next((p for p in [here.parent, *here.parents] if (p / "apps_rg" / "resume" / "base").exists()), Path.cwd())

REPO_ROOT = _find_repo_root()

def sha16(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()[:16]

def write_json(path: Path, data: Any) -> None:
    _wg.ensure_dir(path.parent)
    _wg.write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def resolve_content_signal_repair_max_attempts(environ: Mapping[str, str] | None = None) -> int:
    env = get_runtime_environ() if environ is None else environ
    if explicit := str(env.get("APPS_RG_HEADLINE_REPAIR_MAX_ATTEMPTS") or "").strip():
        try:
            return max(1, min(CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS, int(explicit)))
        except ValueError:
            pass
    if str(env.get("APPS_RG_PRODUCTION_RUN") or "").strip() == "1" or str(env.get("APPS_RG_WHOLE_RUN_ENVELOPE") or "").strip() == "1" or not str(env.get("PYTEST_CURRENT_TEST") or "").strip():
        return CONTENT_SIGNAL_REPAIR_LIVE_MAX_ATTEMPTS
    return CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS

def content_signal_repair_enabled() -> bool:
    raw = (get_runtime_env_str("APPS_RG_HEADLINE_CONTENT_SIGNAL_REPAIR", "1") or "1").strip().lower()
    return RELEASE_HEADLINE_CONTENT_SIGNAL_REPAIR_ENABLED and raw not in ("0", "false", "no", "off")

def content_signal_repair_env_state() -> str:
    raw = get_runtime_env_str("APPS_RG_HEADLINE_CONTENT_SIGNAL_REPAIR")
    return raw.strip() if isinstance(raw, str) and raw.strip() else "unset"

def candidate_3word_subsequences(seg: str) -> list[str]:
    low = (seg or "").strip().lower()
    if low in _SHARP_POSITIONING_SEGMENT_REWRITES:
        return [_SHARP_POSITIONING_SEGMENT_REWRITES[low]]
    words = seg.split()
    if len(words) < 4:
        return []
    out: list[str] = []
    for c in (" ".join(words[:3]), " ".join([words[0], words[2], words[3]]), " ".join([words[0], words[1], words[3]]), " ".join(words[-3:])):
        c_val = _SHARP_POSITIONING_SEGMENT_REWRITES.get(c.strip().lower(), "") if c.strip().lower() in _FORBIDDEN_BACKOFFICE_HEADLINE_SEGMENTS else c
        if c_val and c_val not in out:
            out.append(c_val)
    return out

def collect_employer_names_lower(base_resume: dict[str, Any]) -> list[str]:
    return [e for emp in base_resume.get("facts", base_resume).get("employment", []) if (e := str(emp.get("employer", "")).strip().lower())]

def extract_candidate_name_tokens(base_resume: dict[str, Any]) -> list[str]:
    hdr = base_resume.get("header")
    return [tok.lower() for part in str(hdr.get("name") or "").strip().split() if len(tok := re.sub(r"^[^\w]+|[^\w]+$", "", part)) >= 3] if isinstance(hdr, dict) else []

def build_selected_fact_plan(facts: list[dict[str, Any]], candidate_fact_pool_ids: list[str]) -> dict[str, Any]:
    return build_selected_graph_evidence_plan(section_id="headline", selection_method="canonical_base_resume_employment_bullets", facts=facts, required_fact_ids=[], facts_semantics="candidate_fact_pool_full_records", candidate_fact_pool_ids=candidate_fact_pool_ids, selected_required_fact_ids=[], selected_claim_fact_ids=[])

def build_runtime_payload(*, base_json_path: Path, base_hash: str, selected_fact_plan: dict[str, Any], allowed_fact_ids: set[str], target_title: str, target_company: str, jd_text: str, briefing: str, repo_root: Path | None = None) -> dict[str, Any]:
    return build_graph_evidence_runtime_payload(run_id_prefix="headline", section_id="headline", prompt_id=PROMPT_ID, repo_root=repo_root or REPO_ROOT, base_json_path=base_json_path, base_hash=base_hash, selected_graph_evidence_plan=selected_fact_plan, allowed_graph_evidence_ids=sorted(allowed_fact_ids), target_title=target_title, target_company=target_company, jd_text=jd_text, briefing=briefing, writable_context_scope="headline_only")

def resolve_canonical_source_fact_id(fid: str, allowed_fact_ids: set[str]) -> str | None:
    repaired = repair_fact_id_against_allowlist(str(fid).strip(), allowed_fact_ids)
    if not repaired:
        return None
    if repaired in allowed_fact_ids:
        return repaired
    base = repaired.split("_metric_")[0]
    if base in allowed_fact_ids:
        return base
    mc = sorted(a for a in allowed_fact_ids if str(a).startswith(f"{base}_metric_"))
    return mc[0] if len(mc) == 1 else (next((c for c in mc if c == repaired or c.startswith(repaired)), None) if mc and repaired.startswith(base + "_metric_") else None)

def _segment_claim_rows_already_valid(rows: list[dict[str, Any]], segments: tuple[str, str, str]) -> bool:
    return len(rows) >= 3 and {str(r.get("claim_text") or "").strip().lower() for r in rows if isinstance(r, dict)} >= {s.strip().lower() for s in segments}

def coerce_segment_claim_ledger_rows(headline_line: str, source_fact_ids: list[str], existing_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    segs, ids = _headline_positioning_segments(headline_line), sorted({str(x) for x in source_fact_ids if str(x).strip()})
    if not segs or not ids:
        return list(existing_rows or [])
    rows = [r for r in (existing_rows or []) if isinstance(r, dict)]
    return rows if _segment_claim_rows_already_valid(rows, segs) else [{"claim_text": seg, "source_fact_ids": list(ids)} for seg in segs]

def ensure_claim_ledger(headline: str, parsed: dict[str, Any], allowed_fact_ids: set[str], *, retain_bullet_aliases: bool = False) -> None:
    ledger_raw, hl = parsed.get("claim_ledger"), headline.strip()
    if not isinstance(ledger_raw, list):
        parsed["claim_ledger"] = []
        return
    dict_rows = [e for e in ledger_raw if isinstance(e, dict)]
    string_ids_raw = [str(e).strip() for e in ledger_raw if isinstance(e, str) and str(e).strip()]
    rows_before = len(dict_rows)
    for entry in dict_rows:
        if isinstance(raw_ids := entry.get("source_fact_ids"), list):
            cleaned: list[str] = []
            for x in raw_ids:
                raw_s = str(x).strip()
                if not raw_s:
                    continue
                is_bul = retain_bullet_aliases and repair_fact_id_against_allowlist(raw_s, allowed_fact_ids).split("_metric_")[0].startswith("bul_")
                resolved = resolve_canonical_source_fact_id(raw_s, allowed_fact_ids)
                if is_bul and raw_s not in cleaned:
                    cleaned.append(raw_s)
                elif resolved and resolved not in cleaned:
                    cleaned.append(resolved)
            entry["source_fact_ids"] = cleaned
        if isinstance(ct0 := entry.get("claim_text"), str):
            entry["claim_text"] = polish_claim_text_when_headline_has_no_metrics(hl, ct0)
    norm_ids = sorted({res for s in string_ids_raw if (res := resolve_canonical_source_fact_id(s, allowed_fact_ids)) is not None})
    if norm_ids:
        merged = sorted(set(norm_ids) | {str(fid) for e in dict_rows if isinstance(e.get("source_fact_ids"), list) for fid in (e.get("source_fact_ids") or []) if str(fid).strip()})
        if isinstance(cl := parsed.setdefault("change_log", []), list):
            cl.append({"operation": "normalize_claim_ledger_string_fact_ids", "reason": "claim_ledger flat bul_* strings coerced into dict rows", "normalized_source_fact_ids": merged})
        parsed["claim_ledger"] = coerce_segment_claim_ledger_rows(hl, merged)
        return
    if dict_rows:
        kept = [r for r in dict_rows if isinstance(r.get("source_fact_ids"), list) and bool(r.get("source_fact_ids"))]
        union_ids = sorted({str(fid) for r in kept for fid in (r.get("source_fact_ids") or []) if str(fid).strip()})
        if union_ids and len(kept) == 1 and str(kept[0].get("claim_text") or "").strip() == hl:
            parsed["claim_ledger"] = coerce_segment_claim_ledger_rows(hl, union_ids)
            if isinstance(cl := parsed.setdefault("change_log", []), list):
                cl.append({"operation": "normalize_claim_ledger_segment_decomposition", "reason": "single_row_full_headline_coerced_to_xyz_segments"})
            return
        segs = _headline_positioning_segments(hl)
        if union_ids and segs and not _segment_claim_rows_already_valid(kept, segs) and (coerced := coerce_segment_claim_ledger_rows(hl, union_ids, kept)):
            parsed["claim_ledger"] = coerced
            return
        parsed["claim_ledger"] = kept
        if rows_before > 0 and not kept:
            parsed["_headline_ledger_rows_dropped"] = rows_before
        return
    parsed["claim_ledger"] = []
    if rows_before > 0:
        parsed["_headline_ledger_rows_dropped"] = rows_before

def sync_selected_fact_plan_required_ids(parsed: dict[str, Any], runtime_payload: dict[str, Any], allowed_fact_ids: set[str]) -> None:
    union_sorted = sorted({res for r in (parsed.get("claim_ledger") or []) if isinstance(r, dict) for fid in (r.get("source_fact_ids") or []) if (res := resolve_canonical_source_fact_id(str(fid), allowed_fact_ids))})
    base = dict(runtime_payload["selected_fact_plan"])
    base["required_fact_ids"] = base["selected_required_fact_ids"] = base["selected_claim_fact_ids"] = list(union_sorted)
    parsed["selected_fact_plan"] = base

def bind_headline_graph_skill_lineage(parsed: dict[str, Any]) -> dict[str, Any] | None:
    sfp = parsed.get("selected_fact_plan")
    if not isinstance(sfp, dict):
        return None
    cited = list(dict.fromkeys(str(fid).strip() for r in (parsed.get("claim_ledger") or []) if isinstance(r, dict) for fid in (r.get("source_fact_ids") or []) if str(fid).strip().startswith(("reb_", "fact_")))) or [str(x).strip() for x in (sfp.get("selected_claim_fact_ids") or sfp.get("selected_required_fact_ids") or []) if str(x).strip()]
    if not cited:
        return None
    by_fact: dict[str, list[str]] = {}
    for fact in sfp.get("facts") or []:
        if isinstance(fact, dict) and (fid := str(fact.get("fact_id") or fact.get("role_episode_bundle_id") or "").strip()):
            for sid in (fact.get("graph_skill_node_ids") or []):
                if (s := str(sid or "").strip()) and s not in by_fact.setdefault(fid, []):
                    by_fact[fid].append(s)
    for skill in sfp.get("selected_skills") or []:
        if isinstance(skill, dict) and (fid := str(skill.get("role_episode_bundle_id") or "").strip()) and (sid := str(skill.get("skill_id") or "").strip()) and sid not in by_fact.setdefault(fid, []):
            by_fact[fid].append(sid)
    skill_ids = list(dict.fromkeys(sid for fid in cited for sid in by_fact.get(fid, [])))
    if not skill_ids:
        return None
    lineage_refs = [str(r).strip() for r in (sfp.get("graph_lineage_refs") or []) if str(r).strip()] or list(cited)
    receipt = {"operation": "headline_graph_skill_lineage_binding", "reason": "project selected graph skills for visible cited headline facts", "source_fact_ids": list(cited), "graph_skill_node_ids": list(skill_ids), "graph_lineage_refs": list(lineage_refs)}
    if isinstance(cl := parsed.setdefault("change_log", []), list) and not any(isinstance(r, dict) and r.get("operation") == "headline_graph_skill_lineage_binding" for r in cl):
        cl.append(dict(receipt))
    parsed.setdefault("graph_skill_node_ids", list(skill_ids))
    parsed.setdefault("source_fact_ids", list(cited))
    parsed.setdefault("graph_lineage_refs", list(lineage_refs))
    return receipt

def snapshot_raw_jd_alignment(parsed: dict[str, Any]) -> None:
    if isinstance(jd0 := parsed.get("jd_alignment"), dict):
        parsed["raw_jd_alignment"] = json.loads(json.dumps(jd0))

def build_headline_allowed_fact_packet(*, selected_fact_plan: dict[str, Any], proof_pool_ref: str, proof_pool_digest: str) -> list[dict[str, Any]]:
    packet = [dict(row) for row in list(selected_fact_plan.get("facts") or []) if isinstance(row, dict)]
    if proof_pool_ref:
        packet.append({"fact_id": "__proof_pool_anchor__", "kind": "proof_pool_anchor", "proof_pool_ref": proof_pool_ref.replace("\\", "/"), "proof_pool_digest": proof_pool_digest})
    return packet
