"""Metric surface normalization, visibility, and slot allowlist helpers for Unify bullets."""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.contracts.metric_lexical_primitives import (
    SURFACE_NORM_RE,
    canonicalize_unify_gate_metric_text,
    metric_surface_tokens,
    metric_token_visible_in_text,
    surface_norm,
    unify_metric_raw_values,
)
from apps_rg.runtime.validators.unify_bullets_x2 import UNIFY_BULLET_IDS
from ._parent import parent_attr

_canonicalize_unify_gate_metric_text = canonicalize_unify_gate_metric_text
_SURFACE_NORM_RE = SURFACE_NORM_RE
_surface_norm = surface_norm
_unify_metric_raw_values = unify_metric_raw_values


def _unify_metric_outcome_nodes() -> dict[str, dict[str, Any]]:
    from apps_rg.runtime.sections.role_episode_metric_registry import metric_outcome_nodes_from_path
    from apps_rg.runtime.sections.unify_graph_role_episode_registry import BUNDLES_PATH as UNIFY_BUNDLES_PATH

    return metric_outcome_nodes_from_path(UNIFY_BUNDLES_PATH)


def _metric_surface_tokens(metric_id: str) -> list[str]:
    nodes = parent_attr("_unify_metric_outcome_nodes", _unify_metric_outcome_nodes)()
    return metric_surface_tokens(metric_id, metric_nodes=nodes)


def _metric_token_visible_in_text(metric_id: str, text: str) -> str | None:
    tokens = parent_attr("_metric_surface_tokens", _metric_surface_tokens)(metric_id)
    return metric_token_visible_in_text(metric_id, text, surface_tokens=tokens)


def _slot_metric_allowlist(runtime_payload: dict[str, Any]) -> dict[str, set[str]]:
    meta = runtime_payload.get("proof_pool_metadata")
    meta = meta if isinstance(meta, dict) else {}
    slot_map = meta.get("unify_bullet_slot_bundle_map_resolved")
    slot_map = slot_map if isinstance(slot_map, dict) else {}
    bundles = {
        str(b.get("role_episode_bundle_id") or ""): b
        for b in (meta.get("role_episode_bundles") or [])
        if isinstance(b, dict)
    }
    out: dict[str, set[str]] = {}
    for bid in UNIFY_BULLET_IDS:
        bundle_id = str(slot_map.get(bid) or "")
        bundle = bundles.get(bundle_id) or {}
        mids = {
            str(x).strip()
            for x in (
                bundle.get("linked_metric_outcome_ids")
                or bundle.get("allowed_metric_outcome_ids")
                or []
            )
            if str(x).strip()
        }
        selected_plan_metrics = _selected_plan_metric_ids_for_slot(runtime_payload, bid)
        if selected_plan_metrics:
            mids &= selected_plan_metrics
        if mids:
            out[bid] = mids
    return out


def _selected_plan_metric_ids_for_slot(
    runtime_payload: dict[str, Any],
    bullet_id: str,
) -> set[str]:
    """Return the immutable allocation metric for a visible Unify slot."""
    plan = runtime_payload.get("selected_fact_plan")
    if not isinstance(plan, dict):
        return set()
    for fact in plan.get("facts") or []:
        if isinstance(fact, dict) and str(fact.get("fact_id") or "") == bullet_id:
            return {
                str(mid).strip()
                for mid in (fact.get("metric_outcome_ids") or [])
                if str(mid).strip()
            }
    return set()


def _selected_metric_ids_for_slot(out: dict[str, Any], bullet_id: str) -> list[str]:
    selected: list[str] = []
    plan = out.get("selected_fact_plan")
    if isinstance(plan, dict):
        for fact in plan.get("facts") or []:
            if isinstance(fact, dict) and str(fact.get("fact_id") or "") == bullet_id:
                selected.extend(str(x) for x in (fact.get("metric_outcome_ids") or []))
        slot_plan = plan.get(bullet_id)
        if isinstance(slot_plan, dict):
            selected.extend(str(x) for x in (slot_plan.get("selected_metric_outcome_ids") or []))
    for entry in out.get("change_log") or []:
        if not isinstance(entry, dict) or str(entry.get("bullet_id") or "") != bullet_id:
            continue
        selected.extend(str(x) for x in (entry.get("metric_outcome_ids") or []))
    return [x for x in dict.fromkeys(s.strip() for s in selected) if x]


def _ensure_change_log_entry(
    out: dict[str, Any],
    bullet_id: str,
    *,
    metric_ids: list[str],
) -> None:
    change_log = out.setdefault("change_log", [])
    if not isinstance(change_log, list):
        out["change_log"] = change_log = []
    target = None
    for entry in change_log:
        if isinstance(entry, dict) and str(entry.get("bullet_id") or "") == bullet_id:
            target = entry
            break
    if target is None:
        target = {"bullet_id": bullet_id}
        change_log.append(target)
    plan = out.get("selected_fact_plan")
    if isinstance(plan, dict):
        for fact in plan.get("facts") or []:
            if isinstance(fact, dict) and str(fact.get("fact_id") or "") == bullet_id:
                if not target.get("role_episode_bundle_id") and fact.get("role_episode_bundle_id"):
                    target["role_episode_bundle_id"] = str(fact["role_episode_bundle_id"])
                if not (target.get("skill_ids_used") or target.get("graph_skill_node_ids")):
                    sids = [str(s).strip() for s in (fact.get("graph_skill_node_ids") or []) if str(s).strip()]
                    if sids:
                        target["skill_ids_used"] = sids
                if not target.get("fact_ids_used"):
                    cand_fid = str(fact.get("candidate_fact_id") or "").strip()
                    target["fact_ids_used"] = [bullet_id, cand_fid] if cand_fid else [bullet_id]
                break
    existing = [str(x) for x in (target.get("metric_outcome_ids") or []) if str(x).strip()]
    for mid in metric_ids:
        if mid not in existing:
            existing.append(mid)
    target["metric_outcome_ids"] = existing


def _append_metric_surface_clause(text: str, token: str) -> str:
    clean = str(text or "").strip()
    surface = str(token or "").strip()
    if not clean or not surface:
        return clean
    stem = clean[:-1].rstrip() if clean.endswith(".") else clean
    s_low = surface.lower()
    if s_low.startswith(("$", "+", "1", "2", "3", "4", "5", "6", "7", "8", "9")):
        clause = f", delivering {surface}"
    elif any(k in s_low for k in ("gate", "control", "compliance", "audit", "telemetry")):
        clause = f", enforcing {surface}"
    elif any(k in s_low for k in ("co-sell", "playbook", "enablement", "motion", "framework")):
        clause = f", establishing {surface}"
    else:
        clause = f" across {surface}" if "account" in s_low or "program" in s_low else f", delivering {surface}"
    candidate = f"{stem}{clause}."
    if len(candidate) <= 300:
        return candidate
    return clean


def _ensure_selected_plan_metric_ids(out: dict[str, Any], bullet_id: str, metric_ids: list[str]) -> None:
    plan = out.get("selected_fact_plan")
    if not isinstance(plan, dict):
        return
    slot_plan = plan.get(bullet_id)
    if not isinstance(slot_plan, dict):
        return
    existing = [
        str(x)
        for x in (slot_plan.get("selected_metric_outcome_ids") or [])
        if str(x).strip()
    ]
    for mid in metric_ids:
        if mid not in existing:
            existing.append(mid)
    slot_plan["selected_metric_outcome_ids"] = existing


def _selected_fact_plan_has_runtime_facts(plan: Any) -> bool:
    return isinstance(plan, dict) and bool(
        [f for f in (plan.get("facts") or []) if isinstance(f, dict)]
    )


def _runtime_selected_fact_plan(runtime_payload: dict[str, Any]) -> dict[str, Any] | None:
    plan = runtime_payload.get("selected_fact_plan")
    return plan if _selected_fact_plan_has_runtime_facts(plan) else None


def _authoritative_selected_fact_plan(
    candidate: Any,
    runtime_payload: dict[str, Any],
) -> Any:
    """Prefer the runtime graph plan when model output only echoed a compact slot map."""
    if _selected_fact_plan_has_runtime_facts(candidate):
        return candidate
    runtime_plan = _runtime_selected_fact_plan(runtime_payload)
    return runtime_plan if runtime_plan is not None else candidate


def _plan_metric_raw_for_slot(runtime_payload: dict[str, Any], bullet_id: str) -> str:
    facts = list((runtime_payload.get("selected_fact_plan") or {}).get("facts") or [])
    for fact in facts:
        if isinstance(fact, dict) and str(fact.get("fact_id") or "") == bullet_id:
            return str(fact.get("metric_raw") or "").lower()
    return ""


def _metric_raw_traces_to_plan_or_outcomes(
    raw: Any,
    *,
    bullet_id: str,
    runtime_payload: dict[str, Any],
    approved_metric_ids: set[str],
) -> bool:
    tokens = _unify_metric_raw_values(raw)
    if not tokens:
        return False
    joined = ", ".join(tokens).lower()
    plan_metric = _plan_metric_raw_for_slot(runtime_payload, bullet_id)
    if plan_metric and (plan_metric in joined or joined in plan_metric):
        return True
    return bool(approved_metric_ids) and all(token in approved_metric_ids for token in tokens)


def _enforce_unify_metric_outcome_surfaces(
    out: dict[str, Any],
    runtime_payload: dict[str, Any],
) -> None:
    """Bind visible bullet prose to the role-episode metric registry without weakening X2."""
    allow_by_slot = _slot_metric_allowlist(runtime_payload)
    if not allow_by_slot:
        return
    bullets = [b for b in (out.get("bullets") or []) if isinstance(b, dict)]
    repairs: list[dict[str, Any]] = []
    for bullet in bullets:
        bid = str(bullet.get("bullet_id") or "").strip()
        if bid not in allow_by_slot:
            continue
        allowed = allow_by_slot[bid]
        text = str(bullet.get("bullet_text") or "")
        visible_allowed = [
            mid for mid in allowed if parent_attr("_metric_token_visible_in_text", _metric_token_visible_in_text)(mid, text)
        ]
        selected = [
            mid for mid in _selected_metric_ids_for_slot(out, bid)
            if mid in allowed
        ]
        if visible_allowed:
            _ensure_change_log_entry(out, bid, metric_ids=visible_allowed)
            _ensure_selected_plan_metric_ids(out, bid, visible_allowed)
            approved_lower = {mid.lower() for mid in allowed}
            if not _metric_raw_traces_to_plan_or_outcomes(
                bullet.get("metric_raw"),
                bullet_id=bid,
                runtime_payload=runtime_payload,
                approved_metric_ids=approved_lower,
            ):
                previous_metric_raw = bullet.get("metric_raw")
                bullet["metric_raw"] = list(visible_allowed)
                repairs.append(
                    {
                        "operation": "normalize_unify_metric_raw_to_approved_outcome_ids",
                        "target_bullet_id": bid,
                        "previous_metric_raw": previous_metric_raw,
                        "metric_outcome_ids": list(visible_allowed),
                    }
                )
            bullet["has_metric"] = True
            continue

        candidates = selected or sorted(allowed)
        repaired_mid = ""
        repaired_token = ""
        repaired_text = text
        for mid in candidates:
            token = next(iter(parent_attr("_metric_surface_tokens", _metric_surface_tokens)(mid)), "")
            candidate_text = _append_metric_surface_clause(text, token)
            if candidate_text != text and parent_attr("_metric_token_visible_in_text", _metric_token_visible_in_text)(mid, candidate_text):
                repaired_mid = mid
                repaired_token = token
                repaired_text = candidate_text
                break
        if repaired_mid:
            bullet["bullet_text"] = repaired_text
            bullet["has_metric"] = True
            bullet["metric_raw"] = repaired_mid
            _ensure_change_log_entry(out, bid, metric_ids=[repaired_mid])
            _ensure_selected_plan_metric_ids(out, bid, [repaired_mid])
            repairs.append(
                {
                    "operation": "repair_unify_metric_outcome_surface",
                    "target_bullet_id": bid,
                    "metric_outcome_id": repaired_mid,
                    "surface_token": repaired_token,
                }
            )
    if repairs:
        change_log = out.setdefault("change_log", [])
        if isinstance(change_log, list):
            change_log.extend(repairs)
