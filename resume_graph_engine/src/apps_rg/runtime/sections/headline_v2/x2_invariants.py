"""Pre-judge and post-judge deterministic X2 evaluation for headline_v2."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from apps_rg.runtime.c0.resume_graph_claim_binding import build_pre_x2_resume_graph_claim_binding_gate
from apps_rg.runtime.claim_ledger.headline_claim_ledger import _headline_positioning_segments
from apps_rg.runtime.section_repair_ledger import infer_product_quality_with_repair_ledger
from apps_rg.runtime.sections.section_x2_gate_outputs import write_section_x2_gate_outputs
from apps_rg.runtime.validators.headline_quality_x2 import POSITIONING_FAMILIES
from apps_rg.runtime.validators.headline_x2 import headline_runtime_self_check_truth, headline_segment_theme_overlap_issues, validate_raw_headline_claim_ledger
from .evidence_firewall import HEADLINE_SELF_CHECK_PROOF_KEYS, write_json

def headline_resume_native_clarity_report(headline_line: str) -> dict[str, Any]:
    segments = _headline_positioning_segments(headline_line)
    if segments is None:
        return {"pass": False, "shape_valid": False, "opaque_segments": [], "segment_observations": []}
    familiar_phrases = sorted({str(p).strip().lower() for phrases in POSITIONING_FAMILIES.values() for p in phrases if len(str(p).strip().split()) >= 2})
    observations, opaque = [], []
    for segment in segments:
        normalized = " ".join(segment.lower().split())
        wc = len(normalized.split())
        matched = [p for p in familiar_phrases if f" {p} " in f" {normalized} "]
        seg_pass = (wc <= 3 or bool(matched)) and not (normalized.endswith(" enterprise") and wc >= 3 and not normalized.startswith("enterprise "))
        if not seg_pass:
            opaque.append(segment)
        observations.append({"segment": segment, "word_count": wc, "familiar_positioning_phrases": matched, "pass": seg_pass})
    semantic_overlap_issues = headline_segment_theme_overlap_issues(list(segments))
    return {"pass": not opaque and not semantic_overlap_issues, "shape_valid": True, "opaque_segments": opaque, "semantic_overlap_issues": semantic_overlap_issues, "segment_observations": observations}

def snapshot_needs_headline_proof_retry(snapshot_pre: dict[str, Any], *, target_company: str, employer_names_lower: list[str]) -> tuple[bool, str]:
    raw_ok, detail, _ = validate_raw_headline_claim_ledger(snapshot_pre)
    if not raw_ok:
        return True, str(detail)
    hl = str(snapshot_pre.get("headline_line") or "").strip()
    rt = headline_runtime_self_check_truth(hl, target_company=target_company, employer_names_lower=employer_names_lower)
    sc_model = snapshot_pre.get("self_check")
    if not isinstance(sc_model, dict):
        return True, "self_check_missing_or_not_object"
    for key in HEADLINE_SELF_CHECK_PROOF_KEYS:
        if key not in sc_model:
            return True, f"model_missing_self_check:{key}"
        mv, rv = sc_model[key], rt[key]
        if key == "word_count":
            try:
                mv_int = int(float(mv))
            except (TypeError, ValueError):
                return True, f"{key}:non_numeric_model_value"
            if mv_int != int(rv):
                return True, f"{key}:model={mv_int}_runtime={int(rv)}"
            continue
        if (isinstance(mv, bool) and isinstance(rv, bool) and mv != rv) or (not (isinstance(mv, bool) and isinstance(rv, bool)) and mv != rv):
            return True, f"{key}:model={mv}_runtime={rv}" if isinstance(mv, bool) else f"{key}:model={mv!r}_runtime={rv!r}"
    return False, ""

def headline_graph_content_contract_active(parsed: dict[str, Any] | None, runtime_payload: dict[str, Any], allowed_fact_ids: set[str]) -> bool:
    plan = parsed.get("selected_fact_plan") if isinstance(parsed, dict) else None
    if not isinstance(plan, dict) or not list(plan.get("facts") or []):
        plan = runtime_payload.get("selected_fact_plan") if isinstance(runtime_payload.get("selected_fact_plan"), dict) else None
    return bool(isinstance(plan, dict) and list(plan.get("facts") or []) and any(str(fid).startswith(("reb_", "skill_")) for fid in allowed_fact_ids))

def headline_graph_binding_repair_state(parsed: dict[str, Any] | None, runtime_payload: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not isinstance(parsed, dict):
        return None, []
    plan = parsed.get("selected_fact_plan") if isinstance(parsed.get("selected_fact_plan"), dict) else runtime_payload.get("selected_fact_plan")
    if not isinstance(plan, dict):
        return None, []
    gate = build_pre_x2_resume_graph_claim_binding_gate(section_id="headline", claim_rows=list(parsed.get("claim_ledger") or []), selected_fact_plan=plan)
    if not isinstance(gate, dict) or gate.get("pass") is True:
        return gate, []
    obs = gate.get("observed_value")
    failures = list(obs.get("failure_reasons") or []) if isinstance(obs, dict) else []
    orphan_ids = {x for f in failures if str(f or "").startswith("orphan_allocation_claim_units:") for x in str(f)[len("orphan_allocation_claim_units:"):].split(",") if x}
    context = [{"claim_unit_id": cuid, "root_id": str(r.get("root_id") or ""), "skill_id": str(r.get("skill_id") or ""), "root_claim_text": str(r.get("root_claim_text") or ""), "root_claim_outcome": str(r.get("root_claim_outcome") or "")} for r in (plan.get("allocation_assignments") or []) if isinstance(r, dict) and str(r.get("section_id") or "") == "headline" and ((cuid := str(r.get("claim_unit_id") or "")) or True) and (not orphan_ids or cuid in orphan_ids)]
    return gate, context

def infer_product_quality(runtime_generation_status: str, x2_gates: list[dict[str, Any]], *, artifact_dir: Path | None = None) -> tuple[str, str]:
    return infer_product_quality_with_repair_ledger(runtime_generation_status=runtime_generation_status, x2_failed_gate_ids=[g["gate_id"] for g in x2_gates if not g.get("pass")], pass_reason="REAL_LLM output passed all deterministic headline gates.", artifact_dir=artifact_dir)

def write_x2_gate_outputs(path: Path, gates: list[dict[str, Any]], *, section_id: str | None = "headline") -> None:
    if section_id:
        write_section_x2_gate_outputs(path.parent, section_id, gates)
        return
    failed = [g["gate_id"] for g in gates if not g["pass"]]
    write_json(path, {"gates": gates, "failed_gates": failed, "x2_passed": sum(1 for g in gates if g["pass"]), "x2_failed": len(failed), "total_x2_gates": len(gates)})

def headline_proof_bundle_labels(bundle: dict[str, Any]) -> dict[str, Any]:
    out = dict(bundle)
    pe = bool(out.get("proof_eligible"))
    out["generation_runtime_status"] = str(out.get("generation_runtime_status") or "")
    out["proof_runtime_status"] = out["runtime_proof_status"] = "PROOF_ELIGIBLE" if pe else "NOT_PROOF_ELIGIBLE"
    out["mocked_provider"] = bool(out.get("mocked_provider_selected"))
    out["runtime_certification"] = "SIGNED_OFF" if pe else "NOT_SIGNED_OFF"
    return out
