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


_INSURANCE_IT_STRATEGY_DISPLAY_LABEL_PRIORITY: dict[str, int] = {
    "P&C Insurance & Core Platform Modernization": 0,
    "Insurance Core Modernization & Guidewire (P&C)": 0,
    "Insurance Core Data & Workflow Modernization": 0,
    "Underwriting, Claims & Billing Workflow Reliability": 1,
    "Modernization Delivery & Reliability": 1,
    "Actuarial, Regulatory Risk & AI Control Gates": 2,
    "Model Risk Governance & AI Runtime Control Gates": 2,
    "Governance, Risk & Compliance": 2,
    "P&C Underwriting Decisioning & GraphRAG Context": 3,
    "GraphRAG, Hybrid Retrieval & Context Engineering": 3,
    "AI Risk, Decisioning & Context Engineering": 3,
    "Technology Strategy & Innovation": 3,
    "Governed Agentic AI Platform Architecture": 4,
    "AI Platform Leadership": 4,
    "Carrier & Brokerage Cloud Migration Leadership": 5,
    "Engineering Leadership & Operating Model": 5,
    "AWS Migration Execution & Leadership": 5,
    "Engineering & Delivery Leadership": 5,
    "Distributed Systems & Cloud Data Engineering": 6,
    "Data & Analytics Modernization": 6,
    "LLMOps, Evaluation & Runtime Reliability": 6,
    "LLMOps & Reliability": 6,
    "Platform Productization & Commercialization": 7,
    "Partner Commercialization & Value Realization": 7,
    "Cloud Security, Transformation & Productization": 7,
    "Commercial & Operating Impact": 7,
    "Partner Applied AI Architecture": 8,
    "Cloud & Partner Ecosystems": 8,
}


def _term_text(term: Any) -> str:
    from apps_rg.runtime.c0.competencies_graph_authority import (
        normalize_competency_surface_term,
    )

    if isinstance(term, dict):
        raw = str(term.get("text") or term.get("term") or "").strip()
    else:
        raw = str(term or "").strip()
    return normalize_competency_surface_term(raw)


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


def _is_insurance_it_strategy_snapshot(snapshot: dict[str, Any], categories: list[dict[str, Any]]) -> bool:
    for key in ("selected_fact_plan", "_selected_graph_evidence_plan", "competencies_frozen_allocation_output_projection"):
        sub = snapshot.get(key)
        if isinstance(sub, dict) and str(sub.get("target_role_profile") or "").strip() == "insurance_it_strategy":
            return True
    for cat in categories:
        if str(cat.get("resume_display_order_reason") or "").strip() == "insurance_it_strategy_relevance_first":
            return True
    return False


_COMPETENCY_LABEL_REWRITES: dict[str, str] = {
    "Insurance Core Modernization & Guidewire (P&C)": "P&C Insurance & Core Platform Modernization",
}


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

    is_insurance_it = _is_insurance_it_strategy_snapshot(snapshot, categories)

    # When the snapshot contains a rich, evidence-backed set of distinct categories (>= 6) with explicit labels,
    # display each category directly so all 6-8 categories are visible on the finished résumé.
    has_explicit_labels = sum(
        1 for c in categories if (c.get("resume_display_label") or c.get("category_label"))
    ) >= 6
    if has_explicit_labels:
        ordered_categories = list(categories)
        if is_insurance_it:
            ordered_categories.sort(
                key=lambda c: _INSURANCE_IT_STRATEGY_DISPLAY_LABEL_PRIORITY.get(
                    str(c.get("resume_display_label") or c.get("category_label") or "").strip(),
                    50,
                )
            )
        rows: list[tuple[str, list[str]]] = []
        for category in ordered_categories:
            label = str(
                category.get("resume_display_label") or category.get("category_label") or ""
            ).strip()
            label = _COMPETENCY_LABEL_REWRITES.get(label, label)
            terms: list[str] = []
            seen: set[str] = set()
            for term in category.get("terms") or []:
                text = _term_text(term)
                norm = _normalised(text)
                if text and norm not in seen:
                    seen.add(norm)
                    terms.append(text)
            if label and terms:
                rows.append((label, terms))
        if len(rows) >= 6:
            return rows

    claimed_ids: set[int] = set()
    rows = []
    display_groups = (
        (
            _DISPLAY_GROUPS[1],
            _DISPLAY_GROUPS[2],
            _DISPLAY_GROUPS[0],
        )
        if is_insurance_it
        else _DISPLAY_GROUPS
    )
    for label, category_ids in display_groups:
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


def ensure_allocation_plan_coverage(
    parsed: dict[str, Any],
    *,
    selected_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize mid-line capitalized claim splices and align category ordering with target profile."""
    if not isinstance(parsed, dict):
        return parsed
    from apps_rg.runtime.c0.competencies_graph_authority import (
        normalize_competency_surface_term,
    )

    target_profile = str((selected_plan or {}).get("target_role_profile") or "").strip()
    for surface_key in ("categories", "competencies"):
        raw_cats = parsed.get(surface_key)
        if not isinstance(raw_cats, list):
            continue
        cats = [c for c in raw_cats if isinstance(c, dict)]
        for cat in cats:
            for lbl_key in ("resume_display_label", "category_label", "label", "category"):
                lbl_val = str(cat.get(lbl_key) or "").strip()
                if lbl_val in _COMPETENCY_LABEL_REWRITES:
                    cat[lbl_key] = _COMPETENCY_LABEL_REWRITES[lbl_val]
            new_terms: list[Any] = []
            for term in cat.get("terms") or []:
                if isinstance(term, dict):
                    raw_txt = str(term.get("text") or term.get("term") or "").strip()
                    norm_txt = normalize_competency_surface_term(raw_txt)
                    term["text"] = norm_txt
                    term["term"] = norm_txt
                    new_terms.append(term)
                elif isinstance(term, str):
                    new_terms.append(normalize_competency_surface_term(term))
                else:
                    new_terms.append(term)
            cat["terms"] = new_terms
        if target_profile == "insurance_it_strategy" and len(cats) >= 6:
            cats.sort(
                key=lambda c: _INSURANCE_IT_STRATEGY_DISPLAY_LABEL_PRIORITY.get(
                    str(c.get("resume_display_label") or c.get("category_label") or "").strip(),
                    50,
                )
            )
            parsed[surface_key] = cats
    if isinstance(parsed.get("claim_ledger"), list):
        for row in parsed["claim_ledger"]:
            if isinstance(row, dict) and row.get("claim_text"):
                row["claim_text"] = normalize_competency_surface_term(str(row["claim_text"]))
    return parsed


def render_competencies(snapshot: dict[str, Any]) -> str:
    """Render reader-facing competency clusters without a section heading."""
    return "\n".join(
        f"{label}: {', '.join(terms)}"
        for label, terms in competency_display_rows(snapshot)
    )


def csuite_capability_display_rows(
    base_or_snapshot: dict[str, Any],
    *,
    target_company: str = "",
    target_role: str = "",
) -> list[tuple[str, str]]:
    """Return the 6 flagship-absorbed C-suite capability categories for Section 2, with JD-aware graph bundle routing."""
    co_low = str(target_company or "").strip().lower()
    role_low = str(target_role or "").strip().lower()
    graph_plan = base_or_snapshot.get("_selected_graph_evidence_plan") if isinstance(base_or_snapshot, dict) else None
    profile = str((graph_plan or {}).get("target_role_profile") or "").strip()
    families = set((graph_plan or {}).get("selected_competency_families") or [])
    if profile == "insurance_it_strategy" or "brown" in co_low or ("strategy" in role_low and "innovation" in role_low):
        return [
            (
                "P&C Insurance & Core Platform Modernization",
                "Policy administration, claims, and billing platform workflow modernization, P&C carrier and brokerage policy administration migration on AWS, and core-to-analytics data integration across InsurTech CTO and EY insurance advisory.",
            ),
            (
                "Insurance Domain, Actuarial Risk & Carrier Operations",
                "FSA-chartered actuarial foundation, Solvency II and AG43 statutory reserving, P&C and life underwriting/claims core modernization, and enterprise risk management (ERM) across InsurTech CTO and EY insurance advisory.",
            ),
            (
                "Enterprise Architecture & IT Strategy Modernization",
                "Multi-year IT strategy, M&A brokerage and carrier platform integration, software dependency-graph legacy modernization, and 106-engineer organization leadership across regulated enterprises.",
            ),
            (
                "Applied AI & Decision Intelligence Governance",
                "Governed multi-agent workflows, Bayesian 20%-margin human-in-the-loop risk controls, and X1-to-X3 release verification for insurance brokerage, underwriting, and enterprise operations.",
            ),
            (
                "Enterprise Knowledge Graph & Data Governance",
                "Bi-temporal knowledge graphs, 1024-d BGE-M3 hybrid retrieval across 11 release gates, end-to-end regulatory lineage, and Universal Write Gateway 5-check write custody.",
            ),
            (
                "Cloud Modernization, FinOps & Commercial P&L",
                "IP-led AI solution accelerators ($22M revenue, +20% gross margin expansion), cloud-native AWS/Azure/Databricks lakehouse migration (40% infrastructure cost reduction), and 6-month-to-3-week delivery compression.",
            ),
        ]
    if profile == "insurance_agentic_ai" or ("insurance_domain_modernization" in families and "agentic_platforms" in families) or "aig" in co_low or ("agentic" in role_low and "global head" in role_low):
        return [
            (
                "Governed Agentic AI & Decision Intelligence",
                "18-role / 6-modality dialectical reasoning engines (W1 to W7 waves), A2A coordination, <250ms Dual-Track Live Executive Copilot, and 18-agent / 32-gate autonomous delivery.",
            ),
            (
                "Insurance Underwriting, Claims & Actuarial Risk (FSA)",
                "FSA-chartered actuarial foundation, Solvency II and AG43 capital modeling, P&C/life underwriting and claims workflow automation, and regulated-insurer ERM controls across InsurTech CTO and EY insurance advisory.",
            ),
            (
                "Model Risk & Fail-Closed Runtime Governance",
                "Bayesian 20%-margin / 65%-floor human-in-the-loop ambiguity gating, X1-to-X3 exit verification, orthogonal LLM judge panels, and 0% silent signal loss across regulated insurer workflows.",
            ),
            (
                "Bi-Temporal Knowledge Graph & Hybrid Grounding",
                "1024-d BGE-M3 dense + lexical fusion across 11 release qualification gates, Merkle subgraph prefix alignment, and <250ms 2-hop RAM graph retrieval.",
            ),
            (
                "Distributed Systems & Single-Door Write Custody",
                "Universal Write Gateway with 5-check physical disk proofs, generational atomic swaps, and cloud-native microservices across AWS, Azure, and Databricks lakehouses.",
            ),
            (
                "Platform Commercialization & Hyperscaler Co-Sell ($82M+ P&L)",
                "IP-led AI solution accelerators ($22M revenue, +20% gross margin), $15M AWS/Azure/Databricks alliances, and 106-engineer organization leadership.",
            ),
        ]
    facts = base_or_snapshot.get("facts") if isinstance(base_or_snapshot.get("facts"), dict) else base_or_snapshot
    raw_csuite = facts.get("csuite_capability_categories") if isinstance(facts, dict) else None
    if isinstance(raw_csuite, list) and raw_csuite:
        out: list[tuple[str, str]] = []
        for item in raw_csuite:
            if not isinstance(item, dict):
                continue
            label = str(item.get("category") or item.get("category_label") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if not summary:
                terms = [_term_text(t) for t in (item.get("terms") or []) if _term_text(t)]
                summary = ", ".join(terms)
            if label and summary:
                out.append((label, summary))
        if len(out) >= 6:
            return out[:6]
    return [
        (label, ", ".join(terms))
        for label, terms in competency_display_rows(base_or_snapshot)
    ][:6]
