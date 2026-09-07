"""Reader-facing projection for the evidence-backed competencies model.

The competencies lane retains its full graph-backed category inventory for
traceability and deterministic validation.  A finished résumé should not dump
that internal inventory verbatim: it presents the allocation-bound claims in a
small number of distinct executive capability clusters instead.
"""
from __future__ import annotations

from typing import Any


_DISPLAY_GROUPS: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "Partner AI Architecture & Commercialization",
        frozenset({"cloud_partner_ecosystems", "commercial_operating_impact"}),
    ),
    (
        "Governed AI Platforms & Reliability",
        frozenset({"ai_platform_leadership", "governance_risk_compliance", "llmops_reliability"}),
    ),
    (
        "Enterprise Architecture & Delivery",
        frozenset({"tech_strategy_innovation", "data_analytics_modernization", "engineering_delivery_leadership"}),
    ),
)
_MIN_TERMS_PER_DISPLAY_CLUSTER = 3
_MAX_TERMS_PER_DISPLAY_CLUSTER = 5


def _term_text(term: Any) -> str:
    if isinstance(term, dict):
        return str(term.get("text") or term.get("term") or "").strip()
    return str(term or "").strip()


def _normalised(text: str) -> str:
    return " ".join(text.casefold().split())


def _cluster_terms(categories: list[dict[str, Any]]) -> list[str]:
    """Keep allocation-bound terms, then add only enough context for a cluster."""
    allocated: list[str] = []
    supporting: list[str] = []
    seen: set[str] = set()
    for category in categories:
        for term in category.get("terms") or []:
            text = _term_text(term)
            normalised = _normalised(text)
            if not text or normalised in seen:
                continue
            seen.add(normalised)
            if isinstance(term, dict) and str(term.get("allocation_claim_unit_id") or "").strip():
                allocated.append(text)
            else:
                supporting.append(text)

    terms = allocated[:_MAX_TERMS_PER_DISPLAY_CLUSTER]
    for text in supporting:
        if len(terms) >= _MIN_TERMS_PER_DISPLAY_CLUSTER:
            break
        terms.append(text)
    return terms


def competency_display_rows(snapshot: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Return the concise, reader-facing competency rows for a final résumé.

    Category/term records are intentionally not mutated.  The projection is a
    display concern only, so X2 can continue to prove the frozen full L2
    snapshot and its graph claim bindings.
    """
    raw_categories = snapshot.get("competencies") or []
    categories = [row for row in raw_categories if isinstance(row, dict)]
    if not categories:
        return []

    claimed_ids: set[int] = set()
    rows: list[tuple[str, list[str]]] = []
    for label, category_ids in _DISPLAY_GROUPS:
        selected = [
            category
            for category in categories
            if str(category.get("category_id") or "").strip() in category_ids
        ]
        if not selected:
            continue
        claimed_ids.update(id(category) for category in selected)
        terms = _cluster_terms(selected)
        if terms:
            rows.append((label, terms))

    # Preserve resilience for a future, ungrouped taxonomy without reverting to
    # a keyword dump.  Its allocation-bound terms lead; at most three display.
    for category in categories:
        if id(category) in claimed_ids:
            continue
        label = str(
            category.get("resume_display_label") or category.get("category_label") or "Capabilities"
        ).strip()
        terms = _cluster_terms([category])[:_MIN_TERMS_PER_DISPLAY_CLUSTER]
        if label and terms:
            rows.append((label, terms))
    return rows


def render_competencies(snapshot: dict[str, Any]) -> str:
    """Render reader-facing competency clusters without a section heading."""
    return "\n".join(
        f"{label}: {', '.join(terms)}"
        for label, terms in competency_display_rows(snapshot)
    )
