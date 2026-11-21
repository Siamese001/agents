"""Pure non-mutating brushstroke facet classification helpers for C0 composition metadata."""
from __future__ import annotations

from typing import Any


def fact_supports_brushstroke_facet(
    fact: dict[str, Any],
    role: str,
    *,
    classify_fn: Any,
    fact_id_base_fn: Any,
) -> bool:
    fid = fact_id_base_fn(str(fact.get("fact_id") or "")).lower()
    bundle_id = str(fact.get("role_episode_bundle_id") or "").lower()
    claim = str(fact.get("claim_text") or "").lower()
    blob = f"{fid} {bundle_id} {claim}"
    if classify_fn(fid, claim) == role:
        return True
    if role == "B1_executive_identity":
        return any(k in blob for k in ("leadership", "partner", "cosell", "co-sell", "alliance", "transformation", "advisory", "scaled", "head of", "svp", "director", "practice"))
    if role == "B2_governed_platform_system":
        return any(k in blob for k in ("platform", "architecture", "agentic", "rag", "graphrag", "solution", "reference architecture", "reusable", "modernization", "cloud", "policy administration", "underwriting", "claims", "billing"))
    if role == "B3_control_evidence_discipline":
        return any(k in blob for k in ("governed", "governance", "audit", "traceable", "telemetry", "routing", "validation", "enablement", "repeatable", "compliance", "lineage", "risk", "standard", "playbook", "solvency", "solvency ii", "stochastic", "containerized", "actuarial", "regulatory", "capital modeling"))
    if role == "B4_business_role_fit":
        return bool(fact.get("metric_raw") or fact.get("metric_outcome_ids")) or any(k in blob for k in ("revenue", "margin", "growth", "$", "%", "commercial", "adoption", "pipeline", "scaled"))
    return False


def resolve_fallback_brushstroke_facts(
    facts: list[dict[str, Any]], role: str, *, classify_fn: Any, fact_id_base_fn: Any,
) -> list[dict[str, Any]]:
    facet_facts = [
        f for f in facts
        if isinstance(f, dict) and fact_supports_brushstroke_facet(f, role, classify_fn=classify_fn, fact_id_base_fn=fact_id_base_fn)
    ]
    if facet_facts:
        return facet_facts
    if role == "B1_executive_identity":
        primary_b1 = [
            f for f in facts
            if isinstance(f, dict) and any(k in f"{str(f.get('fact_id') or '')} {str(f.get('role_episode_bundle_id') or '')}".lower() for k in ("slalom", "unify", "partner", "leadership", "transformation"))
        ]
        if primary_b1:
            return [primary_b1[0]]
        preferred_b1 = [
            f for f in facts
            if isinstance(f, dict) and any(k in f"{str(f.get('fact_id') or '')} {str(f.get('role_episode_bundle_id') or '')}".lower() for k in ("ibm", "insurtech", "ey", "insurance"))
        ]
        return [preferred_b1[0]] if preferred_b1 else [facts[0]]
    return [facts[0]]


def expand_covered_brushstroke_roles(
    bindings: list[dict[str, Any]], facts: list[dict[str, Any]], allowed: set[str],
    brushstroke_roles: tuple[str, ...] | list[str], *, classify_fn: Any, fact_id_base_fn: Any,
) -> list[str]:
    covered_set = {b["brushstroke_role"] for b in bindings if b.get("in_allowed_pool")}
    for role in brushstroke_roles:
        if role not in covered_set and any(
            isinstance(f, dict) and fact_id_base_fn(str(f.get("fact_id") or "")) in allowed
            and fact_supports_brushstroke_facet(f, role, classify_fn=classify_fn, fact_id_base_fn=fact_id_base_fn)
            for f in facts
        ):
            covered_set.add(role)
    return sorted(covered_set)


def resolve_target_picture_for_archetype(*, role_archetype: str, strategy_executive: bool, role_s: str) -> str:
    if role_archetype == "ai_partnerships":
        return (
            "Executive portrait: leadership-first applied AI architecture and ecosystem partnerships leader "
            "aligning reusable agentic platforms, hyperscaler/GSI co-sell execution, and commercial platform adoption "
            f"(targeting context: {role_s or 'AI Partnerships role'}; company name never in prose)."
        )
    if strategy_executive:
        return (
            "Executive portrait: leadership-first insurance and financial services technology executive aligning P&C carrier and "
            "brokerage core modernization (policy administration, underwriting, claims, and billing), digital innovation, governed agentic AI "
            "platforms, and FSA-chartered actuarial risk governance into one enterprise IT direction "
            f"(targeting context: {role_s or 'SVP IT strategy'}; company name never in prose)."
        )
    return (
        "Executive portrait: leadership-first senior engineering and AI platform executive uniting "
        "organizational leadership scale, forward-deployed prototype-to-production client activation, "
        "governed agentic AI runtime architecture, and regulated financial-services/enterprise risk governance "
        f"(targeting: {role_s or 'target role'}; company name never in prose)."
    )


def attach_non_strategy_s6_anchor(
    sentence_arc: list[dict[str, Any]],
    arc_meta: dict[str, Any],
    *,
    briefing_text: str,
    jd_text: str,
    anchor_fn: Any,
) -> None:
    arc_meta["s6_targeting_forward_anchor"] = anchor_fn(
        briefing_text=str(briefing_text or ""),
        jd_text=str(jd_text or ""),
    )
    if len(sentence_arc) >= 6:
        sentence_arc[5] = {
            **sentence_arc[5],
            "s6_targeting_forward_anchor": arc_meta["s6_targeting_forward_anchor"],
        }
