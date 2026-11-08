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
        *(root_fact.get("source_refs") or []),
    ]
    source_tokens = set().union(*(_surface_tokens(value) for value in graph_text))

    def _is_bound_token(token: str) -> bool:
        if token in source_tokens:
            return True
        if token.endswith("s") and token[:-1] in source_tokens:
            return True
        if f"{token}s" in source_tokens:
            return True
        if token == "validation" and "testing" in source_tokens:
            return True
        return False

    skill_id = str(assignment.get("skill_id") or "").strip()
    raw_sid_words = [
        w
        for w in skill_id.removeprefix("skill_").split("_")
        if w and w not in {"p2", "sr", "w12", "tech", "gtm", "unify", "ibm", "slalom"}
    ]
    sid_words: list[str] = []
    for w in raw_sid_words:
        if not sid_words or sid_words[-1] != w:
            sid_words.append(w)

    mech_candidates = [
        w for w in _MECH_ORDER if w in _SVP_AGENTIC_MECHANISM_TOKENS and _is_bound_token(w)
    ]
    ctx_candidates = [
        w for w in _CTX_ORDER if w in _SVP_EXECUTION_CONTEXT_TOKENS and _is_bound_token(w)
    ]

    words = list(sid_words)
    if not (set(words) & _SVP_AGENTIC_MECHANISM_TOKENS) and mech_candidates:
        m = next((w for w in mech_candidates if w not in words), mech_candidates[0])
        words.insert(0, m)
    if not (set(words) & _SVP_EXECUTION_CONTEXT_TOKENS) and ctx_candidates:
        c = next((w for w in ctx_candidates if w not in words), ctx_candidates[0])
        words.append(c)

    extra_pool = [w for w in [*mech_candidates, *ctx_candidates] if w not in words]
    while len(words) < 5:
        if len(words) == 3 and extra_pool:
            words.extend(["for", extra_pool.pop(0)])
        elif len(words) == 4 and "for" not in words and "across" not in words:
            words.insert(-1, "for")
        elif extra_pool:
            words.insert(-1, extra_pool.pop(0))
        else:
            conn = (
                "for"
                if "for" not in words
                else ("across" if "across" not in words else "with")
            )
            words.insert(-1, conn)

    if len(words) > 7:
        trimmed = words[:6]
        if not (set(trimmed) & _SVP_EXECUTION_CONTEXT_TOKENS) and (
            set(words) & _SVP_EXECUTION_CONTEXT_TOKENS
        ):
            ctx_w = next(
                w for w in reversed(words) if w in _SVP_EXECUTION_CONTEXT_TOKENS
            )
            trimmed[-1] = ctx_w
        if not (set(trimmed) & _SVP_AGENTIC_MECHANISM_TOKENS) and (
            set(words) & _SVP_AGENTIC_MECHANISM_TOKENS
        ):
            mech_w = next(w for w in words if w in _SVP_AGENTIC_MECHANISM_TOKENS)
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
