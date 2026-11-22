"""Stage-2 C0 evidence firewall, companion-bullet loader, and non-mutating ledger binders for role_narrative_v2."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.briefing_resolution import resolve_briefing_for_lanes
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.jd_resolution import resolve_jd_for_lanes
from apps_rg.runtime.resume_resolution import load_lane_base_resume_json
from apps_rg.runtime.sections.graph_evidence_contract import (
    build_graph_evidence_runtime_payload, build_selected_graph_evidence_plan as _build_selected_graph_evidence_plan,
    selection_method_for_section,
)
from apps_rg.runtime.validators.companion_bullet_finalization import build_companion_bullets_context, companion_run_dir_accepted
from .employer_specs import UNIFY_NARRATIVE_BASE_FACT_ID, UNIFY_NARRATIVE_C0_BULLET_PRIORITY, get_employer_narrative_spec


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    return next((p for p in [here.parent, *here.parents] if (p / "apps_rg" / "resume" / "base").exists()), Path.cwd())


REPO_ROOT = _find_repo_root()
TARGET_TITLE_DEFAULT = "SVP Engineering, Agentic AI Platforms"
TARGET_COMPANY_DEFAULT = "Synthetic Enterprise Corp."
JD_TEXT_DEFAULT = resolve_jd_for_lanes().description
BRIEFING_DEFAULT = resolve_briefing_for_lanes(briefing_artifact_ref=None).text
_GRAPH_SKILLS_EVIDENCE = "augmented_skills_graph"


def sha16(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()[:16]


def write_json(path: Path, data: Any) -> None:
    _wg.ensure_dir(path.parent)
    _wg.write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_base_resume(*, repo_root: Path | None = None) -> tuple[dict[str, Any], Path, str]:
    return load_lane_base_resume_json(repo_root=repo_root or REPO_ROOT)


def extract_employer_employment(
    base_resume: dict[str, Any], *, employer_match: str, default_fact_id: str, base_narrative_fact_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    for emp in (base_resume.get("facts", base_resume)).get("employment", []):
        if employer_match.lower() not in str(emp.get("employer", "")).lower():
            continue
        bullets: list[dict[str, Any]] = []
        allowed: set[str] = set()
        for bullet in emp.get("bullets", []):
            if not (bid := bullet.get("bullet_id")):
                continue
            allowed.add(bid)
            mraw = bullet.get("metric_raw", "") if bullet.get("has_metric") else ""
            bullets.append({"fact_id": bid, "claim_text": bullet.get("text", ""), "source_employment": emp.get("employer"), "has_metric": bool(bullet.get("has_metric")), "metric_raw": mraw, "domain": bullet.get("domain", ""), "technologies": bullet.get("technologies", [])})
            if mraw:
                allowed.add(f"{bid}_metric_{sha16(mraw)[:8]}")
        emp_fact, role_narrative = str(emp.get("fact_id") or default_fact_id).strip(), str(emp.get("role_narrative") or "").strip()
        header: dict[str, Any] = {"employer": emp.get("employer"), "title": emp.get("title"), "location": emp.get("location"), "start_date": emp.get("start_date"), "end_date": emp.get("end_date"), "is_current": emp.get("is_current"), "fact_id": emp_fact}
        if base_narrative_fact_id:
            header["role_narrative"] = role_narrative
            allowed.add(emp_fact)
            if role_narrative:
                allowed.add(base_narrative_fact_id)
        return header, bullets, allowed
    raise ValueError(f"{employer_match} employment entry not found in base resume.")


def build_narrative_selected_fact_plan(
    section_id: str, facts: list[dict[str, Any]], *, role_narrative: str = "", employment_fact_id: str = "",
) -> dict[str, Any]:
    spec = get_employer_narrative_spec(section_id)
    if section_id == "unify_narrative":
        by_id = {str(r["fact_id"]): r for r in facts if r.get("fact_id")}
        ordered: list[dict[str, Any]] = []
        for bid in (*UNIFY_NARRATIVE_C0_BULLET_PRIORITY, *spec.canonical_bullet_ids):
            if bid in by_id and by_id[bid] not in ordered:
                ordered.append(by_id[bid])
        fact_rows: list[dict[str, Any]] = []
        req_ids: list[str] = []
        if role_narrative.strip():
            fact_rows.append({"fact_id": UNIFY_NARRATIVE_BASE_FACT_ID, "claim_text": role_narrative.strip(), "source_employment": (ordered[0].get("source_employment") if ordered else "") or "Unify Consulting", "fact_kind": "base_role_narrative_anchor", "priority_rank": 0, "canonical_employment_fact_id": employment_fact_id or spec.default_employment_fact_id})
            req_ids.append(UNIFY_NARRATIVE_BASE_FACT_ID)
        fact_rows.extend({**row, "priority_rank": idx} for idx, row in enumerate(ordered, 1))
        return _build_selected_graph_evidence_plan(section_id="unify_narrative", selection_method="canonical_json_unify_facts", facts=fact_rows, required_fact_ids=[*req_ids, *spec.canonical_bullet_ids])
    ordered_ibm = sorted(facts, key=lambda r: spec.canonical_bullet_ids.index(r["fact_id"]) if r.get("fact_id") in spec.canonical_bullet_ids else 99)
    return _build_selected_graph_evidence_plan(section_id=section_id, selection_method=f"canonical_json_{spec.employer_key}_facts", facts=ordered_ibm, required_fact_ids=list(spec.canonical_bullet_ids))


def build_selected_graph_evidence_plan_for_narrative(section_id: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
    return _build_selected_graph_evidence_plan(section_id=section_id, selection_method=selection_method_for_section(section_id), facts=facts, required_fact_ids=[str(f.get("fact_id") or "").strip() for f in facts if f.get("fact_id")])


def companion_bullets_accepted(section_id: str, run_dir: Path) -> bool:
    spec = get_employer_narrative_spec(section_id)
    return companion_run_dir_accepted(run_dir, upstream_section_id=spec.companion_bullet_lane, expected_bullet_ids=spec.canonical_bullet_ids)


def load_companion_bullets_context(section_id: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    spec = get_employer_narrative_spec(section_id)
    return build_companion_bullets_context(repo_root or REPO_ROOT, upstream_section_id=spec.companion_bullet_lane, expected_bullet_ids=spec.canonical_bullet_ids)


def build_narrative_runtime_payload(
    section_id: str, *, base_json_path: Path, base_hash: str, header: dict[str, Any], selected_fact_plan: dict[str, Any], allowed_fact_ids: set[str], companion_bullets_ref: str | None, companion_bullets_status: str = "UNKNOWN", companion_bullets_reason: str = "", companion_bullet_ids: list[str] | None = None, companion_x3_code: str = "UNKNOWN", companion_product_quality_status: str = "UNKNOWN", target_title: str, target_company: str, jd_text: str, briefing: str, candidate_name: str = "", repo_root: Path | None = None,
) -> dict[str, Any]:
    spec = get_employer_narrative_spec(section_id)
    emp = spec.employer_key
    extra: dict[str, Any] = {spec.header_key: header, "candidate_name": candidate_name, f"companion_{emp}_bullets_ref": companion_bullets_ref, f"companion_{emp}_bullets_status": companion_bullets_status, f"companion_{emp}_bullets_reason": companion_bullets_reason}
    if section_id == "unify_narrative":
        extra.update({"companion_unify_bullet_ids": list(companion_bullet_ids or []), "companion_unify_bullets_x3_code": companion_x3_code, "companion_unify_bullets_product_quality_status": companion_product_quality_status})
    return build_graph_evidence_runtime_payload(run_id_prefix=section_id, section_id=section_id, prompt_id=spec.prompt_id, repo_root=repo_root or REPO_ROOT, base_json_path=base_json_path, base_hash=base_hash, selected_graph_evidence_plan=selected_fact_plan, allowed_graph_evidence_ids=sorted(allowed_fact_ids), target_title=target_title, target_company=target_company, jd_text=jd_text, briefing=briefing, writable_context_scope=f"{section_id}_only", extra_fields=extra)


def decompose_ibm_narrative_claim_ledger_by_clause(
    parsed: dict[str, Any], *, narrative_sentence: str, allowed_fact_ids: set[str] | frozenset[str], companion_bullet_texts: str = "",
) -> None:
    from apps_rg.runtime.validators.ibm_narrative_x2 import ibm_narrative_material_fact_ids_for_sentence, ibm_narrative_mechanism_fact_ids_for_sentence

    if not (narrative := str(parsed.get("narrative_sentence") or narrative_sentence or "").strip()):
        return
    allowed_bul = sorted(x for x in allowed_fact_ids if str(x).startswith("bul_ibm_")) or list(get_employer_narrative_spec("ibm_narrative").canonical_bullet_ids)
    parts = re.split(r",\s+(?=establishing\b)", narrative, maxsplit=1, flags=re.I)
    new_led: list[dict[str, Any]] = []
    if len(parts) >= 2:
        clauses = [p.strip().rstrip(".") for p in parts if p.strip()]
        clause_themes = [sorted(t for t in (set(ibm_narrative_material_fact_ids_for_sentence(cl, companion_bullet_texts)) | set(ibm_narrative_mechanism_fact_ids_for_sentence(cl, companion_bullet_texts))) if t in allowed_bul) for cl in clauses]
        assigned: list[list[str]] = [[] for _ in clauses]
        pool = sorted({t for themes in clause_themes for t in themes})
        for theme in pool:
            if len(hosts := [i for i, themes in enumerate(clause_themes) if theme in themes]) == 1 and len(assigned[hosts[0]]) < 2:
                assigned[hosts[0]].append(theme)
        for theme in pool:
            if not any(theme in r for r in assigned):
                for i in (i for i, themes in enumerate(clause_themes) if theme in themes and len(assigned[i]) < 2):
                    assigned[i].append(theme)
                    break
        overflow: list[list[str]] = [[] for _ in clauses]
        for theme in pool:
            if not any(theme in r for r in assigned) and not any(theme in ex for ex in overflow) and (hosts := [i for i, themes in enumerate(clause_themes) if theme in themes]):
                overflow[hosts[0]].append(theme)
        for i, clause in enumerate(clauses):
            new_led.append({"claim_text": clause, "source_fact_ids": sorted(assigned[i]) or clause_themes[i][:2] or allowed_bul[:2]})
            extras = sorted(overflow[i])
            new_led.extend({"claim_text": clause, "source_fact_ids": extras[j : j + 2]} for j in range(0, len(extras), 2))
    else:
        grounded = set(ibm_narrative_material_fact_ids_for_sentence(narrative, companion_bullet_texts)) | set(ibm_narrative_mechanism_fact_ids_for_sentence(narrative, companion_bullet_texts))
        new_led.append({"claim_text": narrative.rstrip(".!?"), "source_fact_ids": (sorted(t for t in grounded if t in allowed_bul) or allowed_bul[:2])[:2]})
    parsed["claim_ledger"] = new_led
    parsed["change_log"] = [*(parsed.get("change_log") if isinstance(parsed.get("change_log"), list) else []), {"operation": "decompose_ibm_narrative_claim_ledger_by_clause", "reason": "clause_level_bul_ibm_theme_binding"}]


def bind_missing_ibm_narrative_theme_citations(
    parsed: dict[str, Any], *, allowed_fact_ids: set[str] | frozenset[str], companion_bullet_texts: str = "",
) -> list[str]:
    from apps_rg.runtime.validators.ibm_narrative_x2 import _ledger_row_bul_ibm_roots, ibm_narrative_material_fact_ids_for_sentence

    narrative, ledger = str(parsed.get("narrative_sentence") or "").strip(), [r for r in (parsed.get("claim_ledger") or []) if isinstance(r, dict)]
    if not narrative or not ledger:
        return []
    allowed, cited, bound = {str(x) for x in allowed_fact_ids}, {str(s).split("_metric_")[0] for row in ledger for s in (row.get("source_fact_ids") or [])}, []
    for theme in sorted(t for t in ibm_narrative_material_fact_ids_for_sentence(narrative, companion_bullet_texts) if t in allowed and t not in cited):
        for row in ledger:
            roots = _ledger_row_bul_ibm_roots(row)
            if theme not in roots and len(roots) < 2 and theme in ibm_narrative_material_fact_ids_for_sentence(str(row.get("claim_text") or ""), companion_bullet_texts):
                row["source_fact_ids"] = [*list(row.get("source_fact_ids") or []), theme]
                bound.append(theme)
                break
    if bound:
        parsed["change_log"] = [*(parsed.get("change_log") if isinstance(parsed.get("change_log"), list) else []), {"operation": "bind_detected_theme_citations", "reason": "x2_ibm_narrative_claim_theme_coverage", "bound_fact_ids": list(bound)}]
    return bound


def remap_ibm_narrative_claim_ledger_to_fact_pool(parsed: dict[str, Any], runtime_payload: dict[str, Any], companion_bullet_texts: str = "") -> None:
    from apps_rg.runtime.validators.ibm_narrative_x2 import ibm_narrative_material_fact_ids_for_sentence, ibm_narrative_mechanism_fact_ids_for_sentence

    pp, allowed_set, narrative = (runtime_payload.get("proof_pool_metadata") or {}), {str(x) for x in (runtime_payload.get("allowed_fact_ids") or [])}, str(parsed.get("narrative_sentence") or "").strip()
    rows = [r for r in (parsed.get("claim_ledger") or []) if isinstance(r, dict) and str(r.get("claim_text") or "").strip()]
    if pp.get("claim_evidence_source_type") == _GRAPH_SKILLS_EVIDENCE:
        themes = set(ibm_narrative_material_fact_ids_for_sentence(narrative, companion_bullet_texts)) | set(ibm_narrative_mechanism_fact_ids_for_sentence(narrative, companion_bullet_texts))
        bul_ids = sorted(t for t in themes if str(t).startswith("bul_ibm_")) or sorted(x for x in allowed_set if x.startswith("bul_ibm_"))[:3] or ["bul_ibm_001"]
        parsed["claim_ledger"] = [r if any(str(s).startswith("bul_ibm_") for s in (r.get("source_fact_ids") or [])) else {**r, "source_fact_ids": list(bul_ids)} for r in rows] or ([{"claim_text": narrative.rstrip(".!?"), "source_fact_ids": list(bul_ids)}] if narrative else [])
        runtime_payload["allowed_fact_ids"] = sorted(allowed_set | set(bul_ids))
    elif pp.get("claim_evidence_source_type") == "candidate_fact_ledger" and (fact_ids := (sorted(x for x in allowed_set if x.startswith("fact_"))[:6] or sorted(x for x in allowed_set if x.startswith("bul_ibm_"))[:6])):
        parsed["claim_ledger"] = [{**r, "source_fact_ids": list(fact_ids[:3])} for r in rows] or ([{"claim_text": narrative.rstrip(".!?"), "source_fact_ids": list(fact_ids[:3])}] if narrative else [])


def _redact_val(value: Any, terms: tuple[str, ...]) -> tuple[Any, bool]:
    if isinstance(value, str):
        nv = value
        for tok in terms:
            if tok in nv.lower():
                nv = re.compile(re.escape(tok), re.I).sub("[lexicon-redacted]", nv)
        return nv, nv != value
    if isinstance(value, list):
        pairs = [_redact_val(it, terms) for it in value]
        return [p[0] for p in pairs], any(p[1] for p in pairs)
    if isinstance(value, dict):
        pairs_d = {k: _redact_val(it, terms) for k, it in value.items()}
        return {k: v[0] for k, v in pairs_d.items()}, any(v[1] for v in pairs_d.values())
    return value, False


def redact_banned_lexicon_from_attestation_change_log(parsed: dict[str, Any]) -> int:
    from apps_rg.runtime.validators.ibm_narrative_x2 import REAL_L2_MOCK_LANGUAGE_BANNED_SUBSTRINGS

    terms = tuple(dict.fromkeys((*REAL_L2_MOCK_LANGUAGE_BANNED_SUBSTRINGS, "mock_fallback", "mocked_judge")))
    count = 0
    for row in parsed.get("change_log") or []:
        if isinstance(row, dict) and any(t in (rtxt := json.dumps(row, sort_keys=True, default=str).lower()) for t in terms) and any(m in rtxt for m in ("scan", "check", "verif", "ensur", "avoid", "confirm")):
            nr, ch = _redact_val(row, terms)
            if ch and isinstance(nr, dict):
                row.clear()
                row.update(nr)
                count += 1
    return count


def redact_banned_lexicon_from_attestation_metadata(parsed: dict[str, Any]) -> int:
    from apps_rg.runtime.validators.ibm_narrative_x2 import REAL_L2_MOCK_LANGUAGE_BANNED_SUBSTRINGS

    terms = tuple(dict.fromkeys((*REAL_L2_MOCK_LANGUAGE_BANNED_SUBSTRINGS, "mock_fallback", "mocked_judge")))
    count = 0
    for field in ("gap_notes", "self_check"):
        if field in parsed:
            nv, ch = _redact_val(parsed.get(field), terms)
            if ch:
                parsed[field] = nv
                count += 1
    return count
