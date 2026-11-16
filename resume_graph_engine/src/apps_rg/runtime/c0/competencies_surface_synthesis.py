"""Graph-bound competency surface phrase synthesis for allocation materialization."""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping

_SURFACE_COMPOSITION_CONNECTIVES = frozenset(
    {"and", "for", "of", "the", "to", "with", "through", "across", "via"}
)

_MECH_ORDER = (
    "agentic",
    "architecture",
    "governance",
    "governed",
    "runtime",
    "orchestration",
    "retrieval",
    "graphrag",
    "deterministic",
    "validation",
    "evaluation",
    "control",
    "controls",
    "policy",
    "commercialization",
    "modernization",
    "migration",
    "assessment",
    "mapping",
    "routing",
    "telemetry",
    "workflow",
    "workflows",
    "engineering",
    "decision",
    "bounded",
    "operating",
    "prompt",
    "assembly",
    "reliability",
    "hyperscaler",
    "ai",
)

_CTX_ORDER = (
    "platforms",
    "platform",
    "systems",
    "enterprise",
    "workflows",
    "workflow",
    "pipelines",
    "architectures",
    "execution",
    "copilot",
    "sdlc",
    "motions",
    "partners",
    "alliance",
    "ecosystems",
    "regulated",
    "insurers",
    "insurance",
    "design",
    "leadership",
    "operations",
    "compliance",
    "assurance",
    "trails",
    "gate",
    "planes",
    "paths",
    "intelligence",
    "reserving",
    "portfolio",
    "practice",
    "pursuits",
    "ranking",
    "reference",
)


def _surface_tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def phrase_passes_svp_richness(phrase: str) -> bool:
    """Return True if phrase is 5-7 words and passes SVP agentic richness check."""
    if not phrase or not (5 <= len(phrase.split()) <= 7):
        return False
    from apps_rg.runtime.sections.competencies_rigor import (
        check_competencies_visible_terms_svp_agentic_richness,
    )

    ok, _reason = check_competencies_visible_terms_svp_agentic_richness(
        [
            {
                "category_label": "AI Platform Leadership",
                "visible_graph_surface": True,
                "terms": [phrase],
            }
        ]
    )
    return bool(ok)


_COMPOUND_HYPHEN_PAIRS: Mapping[tuple[str, str], str] = {
    ("graph", "aware"): "graph-aware",
    ("relationship", "aware"): "relationship-aware",
    ("policy", "bound"): "policy-bound",
    ("fail", "closed"): "fail-closed",
    ("multi", "step"): "multi-step",
    ("audit", "grade"): "audit-grade",
    ("dense", "sparse"): "dense-sparse",
    ("confidence", "based"): "confidence-based",
    ("side", "effect"): "side-effect",
    ("zero", "trust"): "zero-trust",
    ("cloud", "native"): "cloud-native",
    ("event", "driven"): "event-driven",
    ("multi", "agent"): "multi-agent",
    ("co", "sell"): "co-sell",
    ("pre", "sales"): "pre-sales",
    ("bi", "temporal"): "bi-temporal",
}

_ACRONYM_CASE: Mapping[str, str] = {
    "ai": "AI",
    "llm": "LLM",
    "hitl": "HITL",
    "acl": "ACL",
    "sdlc": "SDLC",
    "gtm": "GTM",
    "aws": "AWS",
    "bcbs": "BCBS",
    "ccar": "CCAR",
    "hpc": "HPC",
    "gsi": "GSI",
    "tco": "TCO",
    "naic": "NAIC",
    "ip": "IP",
    "graphrag": "GraphRAG",
    "devsecops": "DevSecOps",
    "llmops": "LLMOps",
    "soc2": "SOC2",
}

_CTX_NOUN_ORDER = (
    "workflows",
    "systems",
    "platforms",
    "execution",
    "pipelines",
    "architectures",
    "operations",
    "compliance",
    "governance",
    "insurers",
    "insurance",
    "pursuits",
    "modernization",
    "delivery",
    "retrieval",
    "assurance",
    "trails",
    "planes",
    "paths",
    "intelligence",
    "reserving",
    "portfolio",
    "practice",
    "ranking",
    "ecosystems",
    "partners",
    "alliance",
    "motions",
    "leadership",
)


def _normalize_sid_words(raw_words: list[str]) -> list[str]:
    merged: list[str] = []
    i = 0
    while i < len(raw_words):
        if i + 1 < len(raw_words):
            pair = (raw_words[i].lower(), raw_words[i + 1].lower())
            if pair in _COMPOUND_HYPHEN_PAIRS:
                merged.append(_COMPOUND_HYPHEN_PAIRS[pair])
                i += 2
                continue
        w = raw_words[i]
        merged.append(_ACRONYM_CASE.get(w.lower(), w))
        i += 1
    out: list[str] = []
    for w in merged:
        if not out or out[-1].lower() != w.lower():
            out.append(w)
    return out


def synthesize_graph_bound_surface_phrase(
    assignment: Mapping[str, Any],
    *,
    root_fact: Mapping[str, Any],
    composition_is_bound_fn: Callable[..., bool],
) -> str:
    """Synthesize a 5-7 word graph-bound competency phrase from skill + root tokens."""
    from apps_rg.runtime.sections.competencies_rigor import (
        _SVP_AGENTIC_MECHANISM_TOKENS,
        _SVP_EXECUTION_CONTEXT_TOKENS,
    )

    fact_anchor = root_fact.get("fact_anchor")
    resolved_raw = fact_anchor.get("resolved_raw_chunk") if isinstance(fact_anchor, Mapping) else None
    graph_text = [
        assignment.get("skill_id"),
        assignment.get("skill_label"),
        assignment.get("root_bundle_theme"),
        assignment.get("root_claim_text"),
        assignment.get("root_claim_action"),
        assignment.get("root_claim_scope"),
        assignment.get("root_claim_outcome"),
        *(assignment.get("source_refs") or []),
        root_fact.get("domain"),
        root_fact.get("bundle_theme"),
        root_fact.get("claim_text"),
        root_fact.get("claim_action"),
        root_fact.get("claim_scope"),
        root_fact.get("claim_outcome"),
        root_fact.get("raw_chunk"),
        resolved_raw,
        *(root_fact.get("source_refs") or []),
    ]
    source_tokens = set().union(*(_surface_tokens(value) for value in graph_text))

    def _is_bound_token(token: str) -> bool:
        t = token.lower()
        if t in source_tokens:
            return True
        if "-" in t and set(t.split("-")) <= source_tokens:
            return True
        if t.endswith("s") and t[:-1] in source_tokens:
            return True
        if f"{t}s" in source_tokens:
            return True
        if t == "validation" and "testing" in source_tokens:
            return True
        return False

    skill_id = str(assignment.get("skill_id") or "").strip()
    clean_sid = skill_id.removeprefix("skill:c03:").removeprefix("skill_")
    raw_sid_words = [
        w
        for w in re.split(r"[_:]+", clean_sid)
        if w and w.lower() not in {"p2", "sr", "w12", "tech", "gtm", "unify", "ibm", "slalom", "c03", "skill"}
    ]
    sid_words = _normalize_sid_words(raw_sid_words)

    mech_candidates = [
        w for w in _MECH_ORDER if w in _SVP_AGENTIC_MECHANISM_TOKENS and _is_bound_token(w)
    ]
    ctx_candidates = [
        w for w in _CTX_ORDER if w in _SVP_EXECUTION_CONTEXT_TOKENS and _is_bound_token(w)
    ]
    ctx_noun_candidates = [
        w for w in _CTX_NOUN_ORDER if _is_bound_token(w)
    ]

    words = list(sid_words)
    lower_tokens = {t.lower() for w in words for t in re.findall(r"[a-z0-9-]+", w.lower())}
    if not (lower_tokens & _SVP_AGENTIC_MECHANISM_TOKENS) and mech_candidates:
        m = next((w for w in mech_candidates if w.lower() not in lower_tokens), mech_candidates[0])
        words.insert(0, _ACRONYM_CASE.get(m.lower(), m))
        lower_tokens.add(m.lower())
    if not (lower_tokens & _SVP_EXECUTION_CONTEXT_TOKENS) and ctx_candidates:
        c = next(
            (w for w in ctx_noun_candidates if w in _SVP_EXECUTION_CONTEXT_TOKENS and w.lower() not in lower_tokens),
            next((w for w in ctx_candidates if w.lower() not in lower_tokens), ctx_candidates[0]),
        )
        if len(words) <= 4 and "for" not in lower_tokens:
            words.extend(["for", _ACRONYM_CASE.get(c.lower(), c)])
            lower_tokens.update({"for", c.lower()})
        else:
            words.append(_ACRONYM_CASE.get(c.lower(), c))
            lower_tokens.add(c.lower())

    extra_nouns = [w for w in [*ctx_noun_candidates, *ctx_candidates, *mech_candidates] if w.lower() not in lower_tokens]
    while len(words) < 5:
        if len(words) == 3 and extra_nouns:
            nxt = extra_nouns.pop(0)
            words.extend(["for", _ACRONYM_CASE.get(nxt.lower(), nxt)])
            lower_tokens.update({"for", nxt.lower()})
        elif len(words) == 4 and "for" not in lower_tokens and extra_nouns:
            nxt = extra_nouns.pop(0)
            if words[-1].lower() in {"design", "architecture", "controls", "governance", "selection", "execution", "routing", "grounding", "modeling", "validation", "pipelines"}:
                words.extend(["for", _ACRONYM_CASE.get(nxt.lower(), nxt)])
            else:
                words.insert(-1, _ACRONYM_CASE.get(nxt.lower(), nxt))
            lower_tokens.add(nxt.lower())
        elif len(words) == 4 and "for" not in lower_tokens and "across" not in lower_tokens:
            words.insert(-1, "for")
            lower_tokens.add("for")
        elif extra_nouns:
            nxt = extra_nouns.pop(0)
            words.insert(-1, _ACRONYM_CASE.get(nxt.lower(), nxt))
            lower_tokens.add(nxt.lower())
        else:
            conn = (
                "for"
                if "for" not in lower_tokens
                else ("across" if "across" not in lower_tokens else "with")
            )
            words.insert(-1, conn)
            lower_tokens.add(conn)

    if len(words) > 7:
        trimmed = words[:6]
        trimmed_tokens = {t.lower() for w in trimmed for t in re.findall(r"[a-z0-9-]+", w.lower())}
        if not (trimmed_tokens & _SVP_EXECUTION_CONTEXT_TOKENS) and (
            lower_tokens & _SVP_EXECUTION_CONTEXT_TOKENS
        ):
            ctx_w = next(
                w for w in reversed(words) if w.lower() in _SVP_EXECUTION_CONTEXT_TOKENS
            )
            trimmed[-1] = ctx_w
        if not (trimmed_tokens & _SVP_AGENTIC_MECHANISM_TOKENS) and (
            lower_tokens & _SVP_AGENTIC_MECHANISM_TOKENS
        ):
            mech_w = next(w for w in words if w.lower() in _SVP_AGENTIC_MECHANISM_TOKENS)
            trimmed[0] = mech_w
        words = trimmed

    phrase = " ".join(words)
    if (
        composition_is_bound_fn(phrase, assignment=assignment, root_fact=root_fact)
        and phrase_passes_svp_richness(phrase)
    ):
        return phrase
    return ""


__all__ = [
    "phrase_passes_svp_richness",
    "synthesize_graph_bound_surface_phrase",
]
