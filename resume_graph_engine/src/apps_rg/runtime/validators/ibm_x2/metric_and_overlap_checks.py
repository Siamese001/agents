"""Metric ownership, semantic overlap, and taxonomy prefix checks for IBM bullets."""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.validators.ibm_x2.constants import (
    IBM_METRIC_ANCHOR_RULES,
    TAXONOMY_LABEL_PREFIX_PATTERN,
    semantic_overlap_tokens,
)


def _combined_bullet_text(bullets: list[dict[str, Any]]) -> str:
    return "\n".join(str(b.get("bullet_text", "")) for b in bullets)


def _ibm_metric_anchors_on_assigned_bullets(
    bullets: list[dict[str, Any]],
    plan_facts: list[dict[str, Any]] | None = None,
) -> tuple[bool, list[str]]:
    """Each bul_ibm_* must have ANY recognizable metric token in its bullet_text.

    Accepts EITHER the canonical IBM_METRIC_ANCHOR_RULES token (when PROVIDER_MODEL + canonical
    bullet alignment holds) OR the active plan_fact's metric_raw (when the
    augmented_skills_graph selector has reassigned the bullet slot to a different fact
    with its own metric). Closes Bug:IbmLockedMetricInjectionGarblesGraphSelectedBullets
    by refusing to force the canonical metric onto bullets whose graph-selected fact
    carries a different one.
    """
    by_id = {str(b.get("bullet_id")): b for b in bullets if b.get("bullet_id")}
    plan_by_bid = {
        str(f.get("fact_id") or "").strip(): f
        for f in plan_facts or []
        if isinstance(f, dict)
    }
    for f in plan_facts or []:
        if isinstance(f, dict) and not f.get("fact_id"):
            for k, v in f.items():
                if isinstance(v, dict) and str(k).startswith("bul_ibm_") and k not in plan_by_bid:
                    plan_by_bid[str(k)] = v
    failures: list[str] = []
    for needles, root in IBM_METRIC_ANCHOR_RULES:
        bullet = by_id.get(root)
        if bullet is None:
            failures.append(f"missing_bullet:{root}")
            continue
        tl = str(bullet.get("bullet_text") or "").lower()
        has_canonical = any(n.lower() in tl for n in needles)
        if has_canonical:
            continue
        if any(any(n.lower() in str(b.get("bullet_text") or "").lower() for n in needles) for b in bullets):
            continue
        plan_fact = plan_by_bid.get(root) or {}
        plan_metric = str(plan_fact.get("metric_raw") or "").strip().lower()
        plan_has_metric = bool(plan_fact.get("has_metric") or plan_metric)
        if plan_fact and not plan_has_metric:
            continue
        if plan_metric and plan_metric in tl:
            continue
        if plan_metric:
            for chunk in re.findall(r"[\$\d][\$\d\.\,\%a-z\-]*", plan_metric):
                if chunk and chunk in tl:
                    has_canonical = True
                    break
            if has_canonical:
                continue
        failures.append(f"{root}_missing_metric_token")
    return (not failures, failures)


def ibm_cross_bullet_semantic_overlap_violations(
    bullets: list[dict[str, Any]],
    *,
    max_jaccard: float = 0.60,
) -> list[dict[str, Any]]:
    """Return pairs that repeat the same IBM outcome/mechanism in different words.

    Provider grading already evaluates cross-bullet diversity, but a soft model-backed
    pass cannot authorize a pair whose content words are two-thirds identical. This
    deterministic backstop evaluates the final materialized display, after frozen C0
    allocation projection, so a provider draft cannot hide a later rehydration defect.
    """
    token_rows: list[tuple[str, set[str]]] = []
    for row in bullets:
        if not isinstance(row, dict):
            continue
        bullet_id = str(row.get("bullet_id") or "").strip()
        tokens = semantic_overlap_tokens(str(row.get("bullet_text") or ""))
        if bullet_id and tokens:
            token_rows.append((bullet_id, tokens))

    violations: list[dict[str, Any]] = []
    for index, (left_id, left_tokens) in enumerate(token_rows):
        for right_id, right_tokens in token_rows[index + 1 :]:
            union = left_tokens | right_tokens
            similarity = len(left_tokens & right_tokens) / len(union) if union else 0.0
            if similarity >= max_jaccard:
                violations.append(
                    {
                        "bullet_ids": [left_id, right_id],
                        "token_jaccard": round(similarity, 3),
                        "shared_tokens": sorted(left_tokens & right_tokens),
                    }
                )
    return violations


def ibm_bullet_text_has_taxonomy_label_prefix(text: str) -> bool:
    """True when ``bullet_text`` starts with a category-style ``Title: `` prefix (deterministic gate helper)."""
    return bool(TAXONOMY_LABEL_PREFIX_PATTERN.match((text or "").strip()))


def _taxonomy_prefix_violations(bullets: list[dict[str, Any]]) -> list[str]:
    bad: list[str] = []
    for b in bullets:
        if not isinstance(b, dict):
            continue
        bt = str(b.get("bullet_text") or "").strip()
        bid = str(b.get("bullet_id") or "").strip()
        if ibm_bullet_text_has_taxonomy_label_prefix(bt):
            bad.append(bid or bt[:72])
    return bad


def _metric_granularity_ok(
    bullets: list[dict[str, Any]],
    claim_ledger: list[dict[str, Any]],
    plan_facts: list[dict[str, Any]] | None = None,
) -> bool:
    """Metric-bearing bullet or ledger text must cite the matching bul_ibm_* root.

    Skips the canonical pairing assertion when the active plan_fact for the *citing*
    bullet/claim carries its own ``metric_raw`` that already appears in the text — in
    that case the augmented_skills_graph selector intentionally reassigned the slot and
    the canonical token in the text is graph-selected, not canonical-drift. Closes the
    second half of Bug:IbmLockedMetricInjectionGarblesGraphSelectedBullets.
    """
    rules: list[tuple[tuple[str, ...], str]] = list(IBM_METRIC_ANCHOR_RULES)
    plan_by_bid: dict[str, dict[str, Any]] = {
        str(f.get("fact_id") or "").strip(): f
        for f in (plan_facts or [])
        if isinstance(f, dict) and str(f.get("fact_id") or "").strip()
    }

    def _plan_metric_for(ids_raw: list[str]) -> str:
        """Return the metric_raw for the first matching plan_fact, lowercased."""
        for fid in ids_raw:
            base = str(fid).split("_metric_")[0]
            plan_fact = plan_by_bid.get(base) or plan_by_bid.get(str(fid))
            if plan_fact:
                m = str(plan_fact.get("metric_raw") or "").strip().lower()
                if m:
                    return m
        return ""

    def check_text(text: str, ids_raw: list[str]) -> bool:
        tl = text.lower()
        ids_lower = [i.lower() for i in ids_raw]
        plan_metric = _plan_metric_for(ids_raw)
        for needles, root in rules:
            if not any(n.lower() in tl for n in needles):
                continue
            if any(root in i for i in ids_lower):
                continue
            if plan_metric and any(n.lower() in plan_metric for n in needles):
                continue
            if any(n.lower() in ("20%", "20 %") for n in needles) and any(
                b in ids_lower for b in ("bul_ibm_004", "bul_ibm_005")
            ):
                continue
            return False
        return True

    for b in bullets:
        if not check_text(str(b.get("bullet_text", "")), [str(i) for i in (b.get("source_fact_ids") or [])]):
            return False
    for c in claim_ledger:
        if not check_text(str(c.get("claim_text", "")), [str(i) for i in (c.get("source_fact_ids") or [])]):
            return False
    return True


__all__ = [
    "_combined_bullet_text",
    "_ibm_metric_anchors_on_assigned_bullets",
    "_metric_granularity_ok",
    "_taxonomy_prefix_violations",
    "ibm_bullet_text_has_taxonomy_label_prefix",
    "ibm_cross_bullet_semantic_overlap_violations",
]
