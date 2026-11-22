"""IBM narrative and competencies rigor sanitization helpers."""
from __future__ import annotations

import re
from typing import Any

_IBM_META_TAIL_RE = re.compile(
    r"\s+without\s+(?:claiming|asserting)\b[^.]*\.?\s*$",
    re.IGNORECASE,
)
_IBM_CAREER_BRIDGE_RE = re.compile(
    r"\s+(?:supported\s+later|subsequent\s+roles|later\s+production\s+ai)\b[^.]*\.?\s*$",
    re.IGNORECASE,
)
def sanitize_ibm_narrative_display_text(narrative_sentence: str) -> tuple[str, bool]:
    """Strip non-product meta/career tails without changing claim substance.

    Specificity and opener quality are provider/X2 responsibilities. This
    sanitizer must never introduce a mechanism, change an evidence-bearing
    noun phrase, or replace a leadership verb after the claim ledger is built.
    """
    text = str(narrative_sentence or "").strip()
    if not text:
        return text, False
    original = text
    text = _IBM_META_TAIL_RE.sub(".", text).strip()
    text = _IBM_CAREER_BRIDGE_RE.sub(".", text).strip()
    text = re.sub(r"\s+\.", ".", text)
    text = re.sub(r"\.{2,}", ".", text)
    if text and text[-1] not in ".!?":
        text = text + "."
    return text, text != original


def prune_competencies_rigor_failing_terms(
    parsed: dict[str, Any],
    *,
    allow_prose_mutation: bool = True,
) -> list[str]:
    """Drop or remap terms that fail low-rigor / metrics-as-skills X2 gates."""
    if not allow_prose_mutation:
        return []
    from apps_rg.runtime.sections.competencies_certification_contract import (
        is_credential_competency_term,
    )
    from apps_rg.runtime.sections.competencies_capability_projection import map_to_capability_synonym
    from apps_rg.runtime.sections.competencies_rigor import (
        CAPABILITY_CONTEXT_WORDS,
        _METRICS_ONLY_RE,
        _is_low_rigor_two_word_phrase,
    )
    from apps_rg.runtime.sections.competencies_term_phrase import term_phrase
    from apps_rg.runtime.sections.competencies_v3_contract import sync_categories_competencies

    removed: list[str] = []
    cats = parsed.get("competencies") or parsed.get("categories") or []
    if not isinstance(cats, list):
        return removed
    for cat in cats:
        if not isinstance(cat, dict):
            continue
        label = str(cat.get("category_label") or cat.get("label") or "")
        terms_in = cat.get("terms") or []
        kept: list[Any] = []
        for raw in terms_in:
            phrase = term_phrase(raw)
            if not phrase:
                continue
            drop = False
            if _is_low_rigor_two_word_phrase(phrase):
                mapped = map_to_capability_synonym(phrase)
                if mapped and isinstance(raw, dict):
                    raw = dict(raw)
                    raw["text"] = mapped
                    raw["term"] = mapped
                    phrase = mapped
                else:
                    removed.append(f"low_rigor_two_word:{label}:{phrase}")
                    drop = True
            if not drop and _METRICS_ONLY_RE.search(phrase):
                low = phrase.lower()
                if not any(ctx in low for ctx in CAPABILITY_CONTEXT_WORDS) and not is_credential_competency_term(
                    phrase
                ):
                    mapped = map_to_capability_synonym(phrase)
                    if mapped and "platform" in mapped.lower():
                        if isinstance(raw, dict):
                            raw = dict(raw)
                            raw["text"] = mapped
                            raw["term"] = mapped
                    else:
                        removed.append(f"metrics_as_skill:{label}:{phrase}")
                        drop = True
            if not drop:
                kept.append(raw)
        cat["terms"] = kept
    sync_categories_competencies(parsed)
    return removed
