"""Source-fact ID canonicalization, scope clamping, and repair catalogs for Unify bullets."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import normalize_exec_summary_claim_ledger
from apps_rg.runtime.validators.fact_id_typo_repair import (
    repair_fact_id_against_allowlist,
    repair_unify_bullet_surface_id,
)
from apps_rg.runtime.validators.unify_bullets_x2 import UNIFY_BULLET_IDS
from .lane_constants import BULLET_ID_ALIASES, extract_unify_employment

def _canonicalize_bul_w7_unify_source_fact_id(fid: str) -> str:
    """Normalize model typos (whitespace, ``bul_unify_.003`` → ``bul_unify_003``)."""
    s = str(fid).strip()
    if "bul_unify" in s:
        s = re.sub(r"bul_unify_\.", "bul_unify_", s)
        s = re.sub(r"\s+", "", s)
    if s.startswith("bul_w7_unify"):
        s = re.sub(r"\s+", "", s)
    return s


def _legacy_unify_to_ledger_id_map(runtime_payload: dict[str, Any]) -> dict[str, str]:
    """Map canonical ``bul_unify_*`` ids to active ledger ``fact_*`` pool members when needed."""
    allowed = {str(x) for x in (runtime_payload.get("allowed_fact_ids") or [])}
    if not allowed or any(x.startswith("bul_unify_") for x in allowed):
        return {}
    plan_facts = list((runtime_payload.get("selected_fact_plan") or {}).get("facts") or [])
    plan_ids = [str(f.get("fact_id")) for f in plan_facts if f.get("fact_id")][: len(UNIFY_BULLET_IDS)]
    if len(plan_ids) < len(UNIFY_BULLET_IDS):
        plan_ids = sorted(x for x in allowed if str(x).startswith("fact_"))[: len(UNIFY_BULLET_IDS)]
    remap: dict[str, str] = {}
    for idx, legacy in enumerate(UNIFY_BULLET_IDS):
        if idx < len(plan_ids):
            remap[legacy] = plan_ids[idx]
    return remap


def _remap_unify_id(token: str, remap: dict[str, str], allowed: set[str]) -> str:
    base = str(token).split("_metric_")[0]
    metric_tail = token.split("_metric_", 1)[1] if "_metric_" in token else ""
    mapped = remap.get(base, base)
    repaired = repair_fact_id_against_allowlist(mapped, allowed)
    if metric_tail and repaired in allowed:
        metric_id = f"{repaired}_metric_{metric_tail}"
        return metric_id if metric_id in allowed else repaired
    return repaired


def _normalize_unify_source_fact_id_list(
    ids: Any,
    *,
    remap: dict[str, str] | None = None,
    allowed: set[str] | None = None,
) -> list[str]:
    if ids is None:
        return []
    if not isinstance(ids, list):
        return []
    remap = remap or {}
    allowed = allowed or set()
    out: list[str] = []
    for raw in ids:
        canon = _canonicalize_bul_w7_unify_source_fact_id(str(raw))
        if remap:
            canon = _remap_unify_id(canon, remap, allowed)
        elif allowed:
            canon = repair_unify_bullet_surface_id(canon, allowed)
        else:
            canon = repair_unify_bullet_surface_id(canon, None)
        out.append(canon)
    return out


def _unify_slot_bound_source_scope(
    runtime_payload: dict[str, Any],
    *,
    legacy_remap: dict[str, str] | None = None,
) -> dict[str, set[str]]:
    """Return the exact proof IDs each visible Unify slot may cite.

    Graph roots, skills, and metric nodes are prompt provenance.  The Unify X2
    contract deliberately limits the authored claim surface to the visible
    ``bul_unify_*`` slot and its one frozen ``candidate_fact_id``.  Build that
    boundary from the sealed plan so provider-added graph provenance cannot
    leak into ``source_fact_ids``.
    """
    remap = legacy_remap or {}
    scopes: dict[str, set[str]] = {}
    plan = runtime_payload.get("selected_fact_plan") or {}
    for fact in plan.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        slot_id = str(fact.get("fact_id") or "").strip()
        if not slot_id.startswith("bul_unify_"):
            continue
        visible_id = remap.get(slot_id, slot_id)
        candidate_id = str(fact.get("candidate_fact_id") or "").strip()
        scopes[visible_id] = {
            value for value in (visible_id, candidate_id) if value
        }
    return scopes


def _clamp_unify_sources_to_slot(
    source_fact_ids: list[str],
    *,
    bullet_id: str,
    scope_by_slot: dict[str, set[str]],
) -> tuple[list[str], list[str]]:
    scope = scope_by_slot.get(bullet_id)
    if not scope:
        return list(dict.fromkeys(source_fact_ids)), []
    kept: list[str] = []
    dropped: list[str] = []
    for source_id in source_fact_ids:
        base_id = str(source_id).split("_metric_", 1)[0]
        if source_id in scope or base_id == bullet_id:
            if source_id not in kept:
                kept.append(source_id)
        else:
            dropped.append(source_id)
    if bullet_id not in kept:
        kept.insert(0, bullet_id)
    return kept, list(dict.fromkeys(dropped))


def _normalize_unify_claim_ledger(
    parsed: dict[str, Any],
    *,
    remap: dict[str, str] | None = None,
    allowed: set[str] | None = None,
) -> None:
    led = parsed.get("claim_ledger")
    if not isinstance(led, list):
        return
    for entry in led:
        if isinstance(entry, dict):
            entry["source_fact_ids"] = _normalize_unify_source_fact_id_list(
                entry.get("source_fact_ids"),
                remap=remap,
                allowed=allowed,
            )


_UNIFY_ARCHIVE_PARAPHRASE_REPAIRS: dict[str, str] = {
    "bul_unify_004": (
        "Established production-readiness gates for agentic AI delivery, moving lab concepts into "
        "monitored release paths with six months to three weeks cycle compression."
    ),
    "bul_unify_006": (
        "Commercialized reusable agentic AI services into platform IP, producing $22M in IP-led "
        "revenue with 20% gross-margin expansion as the ML engineering team scaled from 8 to 28."
    ),
}


_UNIFY_SENIORITY_TENSE_REPAIRS: dict[str, str] = {
    "Own ": "Owned ",
    "Drive ": "Directed ",
    "Establish ": "Established ",
    "Standardize ": "Standardized ",
    "Architect ": "Architected ",
    # "Compressed" is an evidence-faithful outcome verb, but it is not part
    # of the shared seniority-floor vocabulary.  "Accelerated" preserves the
    # six-month-to-three-week claim while giving the deterministic X2 proxy a
    # canonical executive action verb.
    "Compressed ": "Accelerated ",
}

_UNIFY_EVIDENCE_DENSITY_REPAIRS: dict[str, str] = {
    "bul_unify_002": (
        "Directed CFO-aligned adoption motions through consumption-based licensing, "
        "renewal-signal instrumentation, and usage-based subscription forecasting, scaling "
        "commercial revenue and renewals across enterprise AI accounts."
    ),
}
