"""Shared cross-section signal-loss guards (apps_rg only).

Small, local helpers reused by headline, unify_bullets, and unify_narrative
bundle-consumption X2 gates. These deliberately reuse the existing vocab/threshold
constants from narrative_quality_x2 / bullet_ngram_overlap_x2 rather than redefining
them, to avoid drift. No apps_rg dependency.

Authority model recap (enforced upstream, surfaced here as detectors only):
- graph skills + linked source facts + role episode bundles = content/proof authority
- base resume = seniority / technical specificity / scope / voice calibration only
- archive resumes = provenance inventory only
- JD/briefing = targeting only
- E0 examples = style only
"""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.validators.bullet_ngram_overlap_x2 import (
    compute_max_ngram_overlap_multi_reference,
)
from apps_rg.runtime.validators.narrative_quality_x2 import (
    MECHANISM_VOCAB,
    NARRATIVE_CONSULTING_PHRASES,
    NARRATIVE_STRONG_VERBS,
)

# Generic consulting-delivery phrases that demote a senior engineering role arc.
GENERIC_CONSULTING_PHRASES: frozenset[str] = NARRATIVE_CONSULTING_PHRASES | frozenset({
    "delivered consulting engagements",
    "consulting delivery",
    "client delivery engagements",
    "professional services delivery",
    "managed client relationships",
    "delivery oversight",
    "stakeholder management",
    "cross-functional collaboration",
    "subject matter expertise",
    "drove business outcomes",
})

# Architecture / platform mechanism signal (technical specificity proxy).
ARCHITECTURE_MECHANISM_VOCAB: frozenset[str] = MECHANISM_VOCAB | frozenset({
    "deterministic", "routing", "sandboxed", "replayable", "trace", "traces",
    "graphrag", "vector", "gateway", "rollback", "lineage", "dependency",
    "accelerator", "policy", "gate", "gates", "validation", "telemetry",
    "lakehouse", "databricks", "multi-agent", "platform", "commercialization",
    "productization",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NGRAM_SIZE = 4


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text or "").lower())


def seniority_floor_score(text: str) -> int:
    """Count distinct strong executive ownership verbs present (proxy seniority signal)."""
    tokens = set(_tokenize(text))
    return len(NARRATIVE_STRONG_VERBS & tokens)


def technical_specificity_score(text: str, *, vocab: frozenset[str] | None = None) -> int:
    """Count distinct named mechanism/technology tokens (technical density proxy)."""
    tokens = set(_tokenize(text))
    return len((vocab or ARCHITECTURE_MECHANISM_VOCAB) & tokens)


def detect_generic_consulting_phrases(text: str) -> list[str]:
    """Return generic consulting-delivery phrases found in text (demotion risk)."""
    low = str(text or "").lower()
    return [p for p in GENERIC_CONSULTING_PHRASES if p in low]


_GENERIC_CONSULTING_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bconsulting delivery\b", re.IGNORECASE), "bespoke enterprise delivery"),
    (re.compile(r"\bdelivered consulting engagements\b", re.IGNORECASE), "delivered enterprise platform engagements"),
    (re.compile(r"\bclient delivery engagements\b", re.IGNORECASE), "client platform deployments"),
    (re.compile(r"\bprofessional services delivery\b", re.IGNORECASE), "enterprise platform delivery"),
    (re.compile(r"\bmanaged client relationships\b", re.IGNORECASE), "managed enterprise partner alliances"),
    (re.compile(r"\bdelivery oversight\b", re.IGNORECASE), "engineering delivery governance"),
    (re.compile(r"\bstakeholder management\b", re.IGNORECASE), "cross-functional executive alignment"),
    (re.compile(r"\bcross-functional collaboration\b", re.IGNORECASE), "cross-functional engineering execution"),
    (re.compile(r"\bsubject matter expertise\b", re.IGNORECASE), "deep technical domain expertise"),
    (re.compile(r"\bdrove business outcomes\b", re.IGNORECASE), "drove commercial platform adoption"),
    (re.compile(r"\bdrive strategic value\b", re.IGNORECASE), "drive commercial platform value"),
    (re.compile(r"\bensure alignment\b", re.IGNORECASE), "ensure architectural alignment"),
    (re.compile(r"\bleveraged best practices\b", re.IGNORECASE), "operationalized engineering standards"),
    (re.compile(r"\bworked closely with\b", re.IGNORECASE), "partnered with"),
    (re.compile(r"\bpartnered with stakeholders\b", re.IGNORECASE), "aligned cross-functional leadership"),
    (re.compile(r"\baligned with the business\b", re.IGNORECASE), "aligned with enterprise roadmaps"),
    (re.compile(r"\bfacilitating collaboration\b", re.IGNORECASE), "orchestrating technical execution"),
    (re.compile(r"\bdrove strategic alignment\b", re.IGNORECASE), "drove architectural convergence"),
    (re.compile(r"\bdrove alignment\b", re.IGNORECASE), "drove architectural convergence"),
    (re.compile(r"\benabling the business\b", re.IGNORECASE), "scaling platform capabilities"),
    (re.compile(r"\bproviding thought leadership\b", re.IGNORECASE), "establishing reference architecture"),
    (re.compile(r"\bthought leadership\b", re.IGNORECASE), "reference architecture"),
    (re.compile(r"\bbest practices\b", re.IGNORECASE), "engineering standards"),
)


def rewrite_generic_consulting_phrases(text: str) -> str:
    """Deterministically rewrite generic consulting-delivery phrases to platform engineering terms."""
    s = str(text or "")
    if not s:
        return s
    for pat, repl in _GENERIC_CONSULTING_REWRITES:
        def _match_repl(m: re.Match[str], replacement: str = repl) -> str:
            val = m.group(0)
            if val and val[0].isupper() and not replacement[0].isupper():
                return replacement[0].upper() + replacement[1:]
            return replacement
        s = pat.sub(_match_repl, s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def apply_narrative_consulting_clean(out: dict[str, Any], narrative: str) -> str:
    """Deterministically clean generic consulting language and sync narrative claim ledger."""
    cleaned = rewrite_generic_consulting_phrases(narrative)
    if cleaned != narrative:
        old = narrative
        out["narrative_sentence"] = cleaned
        ledger = out.get("claim_ledger")
        if isinstance(ledger, list):
            for entry in ledger:
                if isinstance(entry, dict) and str(entry.get("claim_text") or "").strip() == old:
                    entry["claim_text"] = cleaned
        out.setdefault("change_log", []).append({
            "operation": "consulting_language_deterministic_clean",
            "reason": "x2_unify_narrative_generic_consulting_language_forbidden",
        })
        out.setdefault("self_check", {})["consulting_language_cleaned"] = True
        return cleaned
    return narrative


def detect_jd_only_phrases(text: str, jd_text: str, *, min_run: int = 6) -> list[str]:
    """Return long verbatim phrase runs lifted from JD/briefing (JD-as-proof leakage).

    A "JD-only phrase" is a run of >= min_run consecutive shared tokens between the
    output and the JD/briefing text. JD is targeting only — never proof substrate.
    """
    out_tokens = _tokenize(text)
    jd_tokens = _tokenize(jd_text)
    if not out_tokens or not jd_tokens or min_run <= 0:
        return []
    jd_runs: set[str] = set()
    for i in range(len(jd_tokens) - min_run + 1):
        jd_runs.add(" ".join(jd_tokens[i : i + min_run]))
    hits: list[str] = []
    for i in range(len(out_tokens) - min_run + 1):
        run = " ".join(out_tokens[i : i + min_run])
        if run in jd_runs and run not in hits:
            hits.append(run)
    return hits


def base_archive_ngram_overlap(text: str, reference_texts: list[str], *, n: int = _NGRAM_SIZE) -> float:
    """Max n-gram overlap vs base/archive reference prose (anti-hydration proxy)."""
    refs = [r for r in (reference_texts or []) if str(r or "").strip()]
    if not refs:
        return 0.0
    return compute_max_ngram_overlap_multi_reference(str(text or ""), refs, n=n)


def is_flat_skill_only_graph_packet(packet: dict[str, Any] | None) -> bool:
    """True when graph context is flat skills only (no role-episode/positioning bundle binding).

    Generic across sections: a packet that exposes graph_skill_node_ids / bound_skills but
    no *_bundle_id, *_bundle_ids, or bundles list is flat-skill-only and forbidden as proof.
    """
    if not isinstance(packet, dict):
        return False
    bundle_id_keys = (
        "role_episode_bundle_id",
        "role_episode_bundle_ids",
        "headline_positioning_bundle_id",
        "headline_positioning_bundle_ids",
        "competency_bundle_id",
    )
    for k in bundle_id_keys:
        if packet.get(k):
            return False
    for list_key in ("role_episode_bundles", "headline_positioning_bundles", "bundles"):
        if packet.get(list_key):
            return False
    has_flat_skills = bool(packet.get("graph_skill_node_ids") or packet.get("bound_skills"))
    return has_flat_skills


__all__ = [
    "ARCHITECTURE_MECHANISM_VOCAB",
    "GENERIC_CONSULTING_PHRASES",
    "apply_narrative_consulting_clean",
    "base_archive_ngram_overlap",
    "detect_generic_consulting_phrases",
    "detect_jd_only_phrases",
    "is_flat_skill_only_graph_packet",
    "rewrite_generic_consulting_phrases",
    "seniority_floor_score",
    "technical_specificity_score",
]
