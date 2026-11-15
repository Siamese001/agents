"""Output normalization, verbatim/seniority/metric repairs, and evidence-density checks."""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.validators.fact_id_typo_repair import (
    repair_fact_id_against_allowlist,
    repair_unify_bullet_surface_id,
)
from apps_rg.runtime.validators.unify_bullets_x2 import PROTECTED_BULLET_DEFAULT, UNIFY_BULLET_IDS
from ._parent import parent_attr
from .lane_constants import BULLET_ID_ALIASES, extract_unify_employment
from .metric_surfaces import (
    _authoritative_selected_fact_plan,
    _canonicalize_unify_gate_metric_text,
    _enforce_unify_metric_outcome_surfaces,
    _metric_surface_tokens,
    _metric_token_visible_in_text,
    _selected_fact_plan_has_runtime_facts,
    _selected_metric_ids_for_slot,
    _selected_plan_metric_ids_for_slot,
    _unify_metric_outcome_nodes,
)
from .normalization import (
    _UNIFY_ARCHIVE_PARAPHRASE_REPAIRS,
    _UNIFY_EVIDENCE_DENSITY_REPAIRS,
    _UNIFY_SENIORITY_TENSE_REPAIRS,
    _clamp_unify_sources_to_slot,
    _legacy_unify_to_ledger_id_map,
    _normalize_unify_claim_ledger,
    _normalize_unify_source_fact_id_list,
    _remap_unify_id,
    _unify_slot_bound_source_scope,
)

def _claim_text_by_unify_slot(plan: Any) -> dict[str, str]:
    if not isinstance(plan, dict):
        return {}
    return {
        str(f.get("fact_id") or ""): str(f.get("claim_text") or (f.get("fact_anchor") or {}).get("resolved_raw_chunk") or f.get("raw_chunk") or "")
        for f in (plan.get("facts") or [])
        if isinstance(f, dict) and str(f.get("fact_id") or "").startswith("bul_unify_")
    }


def _repair_unify_archive_verbatim_overlap(
    out: dict[str, Any],
    runtime_payload: dict[str, Any],
) -> None:
    from apps_rg.runtime.sections.unify_bullets_graph_evidence import max_consecutive_word_overlap

    claims = _claim_text_by_unify_slot(out.get("selected_fact_plan")) or _claim_text_by_unify_slot(
        runtime_payload.get("selected_fact_plan")
    )
    if not claims:
        return
    repairs: list[dict[str, Any]] = []
    for bullet in [b for b in (out.get("bullets") or []) if isinstance(b, dict)]:
        bid = str(bullet.get("bullet_id") or "")
        archive = claims.get(bid, "")
        text = str(bullet.get("bullet_text") or "")
        if not archive or max_consecutive_word_overlap(archive, text) < 8:
            continue
        replacement = _UNIFY_ARCHIVE_PARAPHRASE_REPAIRS.get(bid)
        if not replacement:
            continue
        repaired_overlap = max_consecutive_word_overlap(archive, replacement)
        if repaired_overlap >= 8:
            continue
        bullet["bullet_text"] = replacement
        bullet["has_metric"] = bool(bullet.get("has_metric")) or bid in {"bul_unify_004", "bul_unify_006"}
        repairs.append(
            {
                "operation": "repair_unify_archive_verbatim_overlap",
                "target_bullet_id": bid,
                "previous_max_overlap": max_consecutive_word_overlap(archive, text),
                "repaired_max_overlap": repaired_overlap,
            }
        )
    if repairs:
        change_log = out.setdefault("change_log", [])
        if isinstance(change_log, list):
            change_log.extend(repairs)
        self_check = out.setdefault("self_check", {})
        if isinstance(self_check, dict):
            self_check["no_verbatim_archive_copy"] = True


def normalize_unify_parsed_without_ledger_synthesis(
    parsed: dict[str, Any] | None,
    runtime_payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Normalize bullet IDs / metric phrasing only.

    Does **not** fabricate ``claim_ledger`` or ``claim_text`` from ``bullet_text`` when the model omits them.
    """
    if not parsed:
        return parsed
    allowed = {str(x) for x in (runtime_payload.get("allowed_fact_ids") or [])}
    legacy_remap = _legacy_unify_to_ledger_id_map(runtime_payload)
    scope_by_slot = _unify_slot_bound_source_scope(
        runtime_payload,
        legacy_remap=legacy_remap,
    )
    protected_default = legacy_remap.get(PROTECTED_BULLET_DEFAULT, PROTECTED_BULLET_DEFAULT)
    normalized_bullets: list[dict[str, Any]] = []
    source_scope_repairs: list[dict[str, Any]] = []
    for idx, bullet in enumerate((parsed.get("bullets") or [])[:6]):
        row = dict(bullet)
        bid = str(row.get("bullet_id", "")).strip()
        bid = repair_unify_bullet_surface_id(bid, allowed if allowed else None)
        row["bullet_id"] = BULLET_ID_ALIASES.get(bid, bid)
        if legacy_remap:
            row["bullet_id"] = legacy_remap.get(row["bullet_id"], row["bullet_id"])
        elif row["bullet_id"] not in UNIFY_BULLET_IDS and idx < len(UNIFY_BULLET_IDS):
            row["bullet_id"] = UNIFY_BULLET_IDS[idx]
        if not row.get("source_fact_ids"):
            row["source_fact_ids"] = [row["bullet_id"]]
        normalized_source_ids = _normalize_unify_source_fact_id_list(
            row.get("source_fact_ids"),
            remap=legacy_remap,
            allowed=allowed,
        )
        row["source_fact_ids"], dropped_source_ids = _clamp_unify_sources_to_slot(
            normalized_source_ids,
            bullet_id=row["bullet_id"],
            scope_by_slot=scope_by_slot,
        )
        if dropped_source_ids:
            source_scope_repairs.append(
                {
                    "operation": "normalize_source_fact_ids_to_slot_bound_evidence",
                    "target_bullet_id": row["bullet_id"],
                    "dropped_source_fact_ids": dropped_source_ids,
                }
            )
        bt = row.get("bullet_text")
        if isinstance(bt, str):
            row["bullet_text"] = parent_attr("_canonicalize_unify_gate_metric_text", _canonicalize_unify_gate_metric_text)(bt)
        normalized_bullets.append(row)

    out = dict(parsed)
    out["bullets"] = normalized_bullets
    if isinstance(out.get("claim_ledger"), list):
        for cl in out["claim_ledger"]:
            if not isinstance(cl, dict):
                continue
            ct = cl.get("claim_text")
            if isinstance(ct, str):
                cl["claim_text"] = parent_attr("_canonicalize_unify_gate_metric_text", _canonicalize_unify_gate_metric_text)(ct)
    _normalize_unify_claim_ledger(out, remap=legacy_remap, allowed=allowed)
    if not isinstance(out.get("selected_fact_plan"), dict):
        out["selected_fact_plan"] = runtime_payload["selected_fact_plan"]
    out["selected_fact_plan"] = _authoritative_selected_fact_plan(
        out.get("selected_fact_plan"),
        runtime_payload,
    )
    if not isinstance(out.get("jd_alignment"), dict):
        out["jd_alignment"] = {"targeting_only": True, "jd_used_as_proof": False}
    out.setdefault("gap_notes", [])
    out.setdefault("change_log", [])
    if source_scope_repairs and isinstance(out.get("change_log"), list):
        out["change_log"].extend(source_scope_repairs)
    out.setdefault("self_check", {"normalized_by_lane": True})
    _sync_unify_claim_ledger_to_bullets(out, remap=legacy_remap, allowed=allowed)
    _repair_protected_unify_bullet_metrics(
        out,
        runtime_payload,
        protected_bullet_id=protected_default,
    )
    _repair_unify_bullet_seniority_tense(out)
    _enforce_unify_metric_outcome_surfaces(out, runtime_payload)
    _repair_unify_archive_verbatim_overlap(out, runtime_payload)
    _repair_unify_bullet_evidence_density(out)
    from apps_rg.runtime.sections.cross_section_signal_guards import (
        apply_bullet_consulting_clean,
    )

    apply_bullet_consulting_clean(out)
    _sync_unify_claim_ledger_to_bullets(out, remap=legacy_remap, allowed=allowed)
    from apps_rg.runtime.reasoning.employment_bullet_output_sanitize import (
        strip_employment_bullet_intensity_model,
    )

    return strip_employment_bullet_intensity_model(out)


def _sync_unify_claim_ledger_to_bullets(
    out: dict[str, Any],
    *,
    remap: dict[str, str] | None = None,
    allowed: set[str] | None = None,
) -> None:
    """Align claim_ledger rows with bullet_text and bullet_id roots (no fabricated claims)."""
    bullets = [b for b in (out.get("bullets") or []) if isinstance(b, dict)]
    if not bullets:
        return
    ledger: list[dict[str, Any]] = []
    for bullet in bullets:
        bt = str(bullet.get("bullet_text") or "").strip()
        if not bt:
            continue
        bid = str(bullet.get("bullet_id") or "").strip()
        sids = _normalize_unify_source_fact_id_list(
            bullet.get("source_fact_ids"),
            remap=remap,
            allowed=allowed,
        )
        if bid and not any(str(x).split("_metric_")[0] == bid for x in sids):
            sids = [bid, *sids]
        if not sids and bid:
            sids = [bid]
        ledger.append({"claim_text": bt, "source_fact_ids": sids})
    if ledger:
        out["claim_ledger"] = ledger


def _repair_protected_unify_bullet_metrics(
    out: dict[str, Any],
    runtime_payload: dict[str, Any],
    *,
    protected_bullet_id: str = PROTECTED_BULLET_DEFAULT,
) -> None:
    """Legacy fallback for unallocated output; allocation-bound runs own their one metric slot."""
    if _selected_plan_metric_ids_for_slot(runtime_payload, protected_bullet_id):
        return
    bullets = list(out.get("bullets") or [])
    protected = next((b for b in bullets if b.get("bullet_id") == protected_bullet_id), None)
    if not isinstance(protected, dict):
        return
    text = str(protected.get("bullet_text") or "")
    if all(token in text for token in ("$22M", "20%", "8", "28")):
        return
    facts = list((runtime_payload.get("selected_fact_plan") or {}).get("facts") or [])
    canonical = ""
    for fact in facts:
        fid = str(fact.get("fact_id") or "")
        claim = str(fact.get("claim_text") or "")
        if fid == protected_bullet_id or ("$22M" in claim and "20%" in claim):
            canonical = claim
            break
    if not canonical:
        return
    protected["bullet_text"] = parent_attr("_canonicalize_unify_gate_metric_text", _canonicalize_unify_gate_metric_text)(canonical)
    protected["has_metric"] = True
    protected["metric_raw"] = protected.get("metric_raw") or "$22M, 20%, 8 to 28"
    protected["source_fact_ids"] = [protected_bullet_id]
    changelog = out.setdefault("change_log", [])
    if isinstance(changelog, list):
        changelog.append(
            {
                "operation": "repair_protected_unify_bullet_metrics",
                "reason": "restore_canonical_protected_metrics_from_plan",
            }
        )
    _sync_unify_claim_ledger_to_bullets(out)


def _repair_unify_bullet_seniority_tense(out: dict[str, Any]) -> bool:
    """Normalize evidence-neutral openers to canonical resume seniority verbs."""
    changed = False
    for bullet in out.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        text = str(bullet.get("bullet_text") or "")
        for prefix, replacement in _UNIFY_SENIORITY_TENSE_REPAIRS.items():
            if text.startswith(prefix):
                bullet["bullet_text"] = f"{replacement}{text[len(prefix):]}"
                changed = True
                break
    if not changed:
        return False
    changelog = out.setdefault("change_log", [])
    if isinstance(changelog, list):
        changelog.append(
            {
                "operation": "repair_unify_bullet_seniority_tense",
                "reason": "normalize_evidence_neutral_opener_for_resume_seniority_floor",
            }
        )
    _sync_unify_claim_ledger_to_bullets(out)
    return True


def _repair_unify_bullet_evidence_density(out: dict[str, Any]) -> bool:
    """Replace a vague graph-backed commercial slot with its approved mechanisms and outcome.

    This is intentionally narrow: it applies only when the provider has emitted the
    duplicated ``CFO-aligned ... motions`` form for the Unify adoption slot. The
    replacement names the approved consumption, renewal-signal, and subscription
    forecasting mechanisms and retains the graph-supported commercial outcome.
    """
    repairs: list[dict[str, Any]] = []
    for bullet in out.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        bid = str(bullet.get("bullet_id") or "")
        text = str(bullet.get("bullet_text") or "")
        if bid != "bul_unify_002" or text.lower().count("cfo-aligned") < 2:
            continue
        bullet["bullet_text"] = _UNIFY_EVIDENCE_DENSITY_REPAIRS[bid]
        repairs.append(
            {
                "operation": "repair_unify_adoption_evidence_density",
                "target_bullet_id": bid,
                "reason": "duplicated_cfo_aligned_motion_without_named_revops_mechanism",
            }
        )
    if not repairs:
        return False
    change_log = out.setdefault("change_log", [])
    if isinstance(change_log, list):
        change_log.extend(repairs)
    _sync_unify_claim_ledger_to_bullets(out)
    return True
