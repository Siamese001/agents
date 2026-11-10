"""Headline quality floor X2 gate helpers (Headline/Competencies/Narrative Rigor plan).

Implements deterministic proxy gates enforcing SVP Engineering positioning rigor:
- x2_headline_positioning_family_preserved: ≥2 positioning family signals in X/Y/Z segments
- x2_headline_no_narrowing_it_labels: blocklist of demoting / juniorizing label phrases
- x2_headline_e0_ngram_overlap: anti-leakage gate for E0 example text
- x2_headline_base_ngram_overlap: anti-hydration gate for base resume headline

These gates catch headlines that pass structural gates but narrow the candidate from
SVP Engineering / Agentic AI / Runtime Governance posture into generic IT labels.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from apps_rg.runtime.validators.bullet_ngram_overlap_x2 import (
    compute_max_ngram_overlap,
    compute_max_ngram_overlap_multi_reference,
)

# ---------------------------------------------------------------------------
# Positioning families — approved executive engineering signals
# ---------------------------------------------------------------------------

POSITIONING_FAMILIES: dict[str, frozenset[str]] = {
    "agentic_ai_platforms": frozenset({
        "agentic ai", "agentic platform", "agentic ai platform", "agentic ai platforms",
        "llm platform", "ai platform", "ai platforms", "agent orchestration",
        "multi-agent", "multiagent", "agentic orchestration",
    }),
    "distributed_ai_infrastructure": frozenset({
        "distributed ai", "distributed ai infrastructure", "distributed infrastructure",
        "ai infrastructure", "distributed systems", "distributed data",
        "distributed platform", "cloud data modernization", "cloud data platforms",
        "insurance platform modernization", "insurance core modernization",
        "insurance cloud architecture",
    }),
    "runtime_governance": frozenset({
        "runtime governance", "runtime control", "ai governance", "governance controls",
        "runtime gates", "policy gates", "deterministic gates", "governed ai",
        "regulatory ai", "compliance ai", "ai policy", "runtime policy",
    }),
    "enterprise_ai_architecture": frozenset({
        "enterprise ai", "enterprise architecture", "enterprise ai architecture",
        "enterprise platform", "enterprise systems", "enterprise-scale ai",
    }),
    "platform_productization": frozenset({
        "platform productization", "platform commercialization", "product platform",
        "saas platform", "ai productization", "platform engineering",
        "platform buildout", "platform roadmap", "insurance platform modernization",
    }),
    "regulated_ai_systems": frozenset({
        "regulated ai", "regulated enterprise ai", "regulated systems",
        "regulated financial", "regulated environments", "regulatory ai",
        "compliance systems", "regulated platform", "regulated insurance",
        "regulated insurance governance", "insurance governance",
        "insurance platform modernization", "insurance core modernization",
        "insurance cloud architecture", "policy administration platforms",
    }),
    # This family is required by headline_positioning_registry and backed by
    # hpb_partner_applied_ai_architecture.  Omitting it here made a graph-bound
    # partnership headline invisible to the technical-specificity gate.
    "partner_applied_ai_architecture": frozenset({
        "partner ai", "partner architecture", "partner solution architecture",
        "partner applied ai", "partner ecosystems", "partner co-sell",
        "co-sell channel", "alliance gtm", "alliance partnerships",
        "hyperscaler partner ecosystem",
    }),
    "executive_transformation_strategy": frozenset({
        "executive transformation", "transformation strategy", "agentic transformation",
        "enterprise transformation", "transformation advisory", "strategic transformation",
        "enterprise agentic transformation",
    }),
    "pe_due_diligence_value_creation": frozenset({
        "private equity", "portfolio value creation", "value creation",
        "m&a due diligence", "technology due diligence", "pe advisory", "due diligence",
        "private equity value creation", "portfolio value",
    }),
    "enterprise_operating_model": frozenset({
        "operating model", "enterprise operating model", "operating model redesign",
        "target operating model", "autonomous operating model", "agentic operating model",
    }),
    "csuite_transformation_advisory": frozenset({
        "c-suite advisory", "board governance", "c-suite transformation",
        "executive advisory", "board steering", "board alignment", "transformation governance",
        "c-suite transformation governance",
    }),
}

# A broader set of signal tokens used for fuzzy multi-token matching
_POSITIONING_SIGNAL_TOKENS: dict[str, frozenset[str]] = {
    "agentic_ai_platforms": frozenset({"agentic", "llm", "multiagent", "multi-agent", "agent"}),
    "distributed_ai_infrastructure": frozenset({"distributed", "infrastructure"}),
    "runtime_governance": frozenset({"runtime", "governance", "gates", "policy", "deterministic", "governed"}),
    "enterprise_ai_architecture": frozenset({"enterprise", "architecture"}),
    "platform_productization": frozenset({"productization", "commercialization", "saas"}),
    "regulated_ai_systems": frozenset({"regulated", "regulatory", "compliance", "ccar", "basel"}),
    "partner_applied_ai_architecture": frozenset(
        {"partner", "partners", "partnership", "partnerships", "alliance", "co-sell", "cosell"}
    ),
    "executive_transformation_strategy": frozenset({"transformation", "advisory", "strategic"}),
    "pe_due_diligence_value_creation": frozenset({"equity", "portfolio", "ebitda", "synergy", "synergies", "merger", "mergers", "acquisition", "acquisitions", "diligence"}),
    "enterprise_operating_model": frozenset({"operating", "model"}),
    "csuite_transformation_advisory": frozenset({"c-suite", "board", "executive", "steering"}),
}

# ---------------------------------------------------------------------------
# Narrowing / demoting IT label blocklist
# ---------------------------------------------------------------------------

NARROWING_IT_LABELS: frozenset[str] = frozenset({
    "it strategy",
    "data modernization",
    "cloud transformation",
    "digital transformation",
    "innovation leadership",
    "technology strategy",
    "technology innovation",
    "it transformation",
    "it modernization",
    "ai lifecycle standardization",
    "lakehouse microservices",
    "annual contract value",
    "cloud and ai vendors",
    "data & analytics modernization",
    "technology strategy & innovation",
    "cloud & partner ecosystems",
})

# ---------------------------------------------------------------------------
# E0 example texts extracted from headline_tailor_v1.yaml (old shapes)
# Updated when E0 is refreshed — used only for ngram overlap calibration.
# ---------------------------------------------------------------------------

HEADLINE_E0_REFERENCE_TEXTS: list[str] = [
    "SVP Engineering | Lakehouse Microservices Architecture | AI Lifecycle Standardization | Retrieval Telemetry Catalogs",
    "SVP Engineering | HPC Trading Platforms | Container Stress Analytics | Eval Pipeline Gates",
    "SVP Engineering | Data Lineage Catalogs | Validation Frameworks | Capital Modeling Rigor",
    "SVP Engineering | Databricks Lakehouse Workflows | Microservices Telemetry | Lineage Catalog Governance",
    "SVP Engineering | Retrieval Eval Harness | Stress Testing Frameworks | HPC Pipeline Orchestration",
    "SVP Engineering | Trading Platform Microservices | Telemetry Validation Pipelines | Lakehouse Modeling Workflows",
]

BASE_NGRAM_THRESHOLD = 0.25
E0_NGRAM_THRESHOLD = 0.20
NGRAM_SIZE = 4

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class HeadlineQualityResult:
    gate_id: str
    passed: bool
    observed_value: Any
    threshold: Any
    failure_reason: str | None
    signals: list[str]


# ---------------------------------------------------------------------------
# Helper: tokenize headline to lowercase words
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


_ALLOWED_HEADLINE_PREFIXES: tuple[str, ...] = (
    "SVP Engineering",
    "SVP Enterprise Architecture",
    "SVP AI Strategy",
    "SVP IT Strategy",
    "SVP Agentic Transformation",
    "SVP Transformation",
    "SVP Technology Strategy",
    "SVP Enterprise AI",
    "SVP Agentic AI Platforms",
    "Partner",
    "Executive Director",
    "Managing Director",
)


def _segments_xyz(headline_line: str) -> list[str]:
    """Return X, Y, Z segments (2-4) if pipe format valid, else full text."""
    h = (headline_line or "").strip()
    if h.count(" | ") == 3 and (h.startswith("SVP ") or any(h.startswith(f"{p} ") for p in ("Senior Vice President", "Executive Director", "Managing Director", "Partner"))):
        parts = [p.strip() for p in h.split(" | ")]
        if len(parts) == 4 and (
            parts[0] in _ALLOWED_HEADLINE_PREFIXES
            or (parts[0].startswith("SVP ") and len(parts[0].split()) in (2, 3, 4))
            or (parts[0].startswith(("Senior Vice President", "Executive Director", "Managing Director", "Partner")) and len(parts[0].split()) <= 4)
        ):
            return parts[1:]
    return [h]


# ---------------------------------------------------------------------------
# Gate: positioning family preservation
# ---------------------------------------------------------------------------


def check_headline_positioning_families(
    headline_line: str,
    min_families: int = 2,
) -> HeadlineQualityResult:
    """Require ≥min_families positioning family signals in the headline X/Y/Z segments.

    Matches against both exact phrase patterns and single token signals.
    """
    segments = _segments_xyz(headline_line)
    blob = " ".join(segments).lower()
    tokens = set(_tokenize(blob))

    matched_families: list[str] = []

    for family_name, phrases in POSITIONING_FAMILIES.items():
        for phrase in phrases:
            if phrase in blob:
                matched_families.append(family_name)
                break
        else:
            # Try token-level signals
            signal_tokens = _POSITIONING_SIGNAL_TOKENS.get(family_name, frozenset())
            if signal_tokens & tokens:
                matched_families.append(family_name)

    # Deduplicate
    matched_unique = list(dict.fromkeys(matched_families))
    passed = len(matched_unique) >= min_families
    return HeadlineQualityResult(
        gate_id="x2_headline_positioning_family_preserved",
        passed=passed,
        observed_value=matched_unique,
        threshold=f">={min_families} positioning families",
        failure_reason=(
            None
            if passed
            else (
                f"Only {len(matched_unique)} positioning families detected "
                f"(need {min_families}): {matched_unique}. "
                "Headline must preserve SVP Engineering positioning families "
                "(Agentic AI Platforms, Distributed AI Infrastructure, Runtime Governance, etc.)"
            )
        ),
        signals=matched_unique,
    )


# ---------------------------------------------------------------------------
# Gate: seniority floor (explicit SVP Engineering prefix)
# ---------------------------------------------------------------------------


def check_headline_seniority_floor(headline_line: str) -> HeadlineQualityResult:
    """Segment 0 must be an approved SVP prefix (e.g. 'SVP Engineering', 'SVP Enterprise Architecture', 'SVP AI Strategy')."""
    h = (headline_line or "").strip()
    parts = [p.strip() for p in h.split(" | ")] if " | " in h else [h]
    seg0 = parts[0] if parts else ""
    seg0_low = seg0.lower()
    is_narrowing = any(
        label in seg0_low
        for label in (
            "it transformation",
            "it modernization",
            "data modernization",
            "cloud transformation",
            "digital transformation",
            "innovation leadership",
        )
    )
    # Bare "Senior Vice President" without domain specialization degrades Segment 1.
    passed = not is_narrowing and seg0 != "Senior Vice President" and (
        seg0 in _ALLOWED_HEADLINE_PREFIXES
        or (seg0.startswith("SVP ") and len(seg0.split()) in (2, 3, 4))
        or (seg0.startswith(("Executive Director", "Managing Director", "Partner")) and len(seg0.split()) <= 4)
    )
    return HeadlineQualityResult(
        gate_id="x2_headline_seniority_floor",
        passed=passed,
        observed_value=seg0,
        threshold="SVP [Engineering/Enterprise Architecture/Strategy]",
        failure_reason=(
            None
            if passed
            else (
                f"First segment {seg0!r} is not an approved SVP prefix. "
                "Headline must open with a senior SVP title to preserve seniority posture."
            )
        ),
        signals=["svp_engineering_present"] if passed else [],
    )


# ---------------------------------------------------------------------------
# Gate: narrowing IT label blocklist
# ---------------------------------------------------------------------------


def check_headline_no_narrowing_it_labels(headline_line: str) -> HeadlineQualityResult:
    """Fail if headline X/Y/Z segments contain phrases from the narrowing/demoting IT label blocklist."""
    h = (headline_line or "").strip()
    if " | " in h and h.startswith(("SVP ", "Executive Director", "Managing Director", "Partner")):
        xyz_text = " | ".join(p.strip() for p in h.split(" | ")[1:]).lower()
    else:
        xyz_text = h.lower()
    # "Cloud Data Modernization" is an approved compact 3-word positioning phrase;
    # strip "cloud data modernization" before checking standalone "data modernization".
    scrubbed = xyz_text.replace("cloud data modernization", "cloud data platforms")
    found: list[str] = [label for label in NARROWING_IT_LABELS if label in scrubbed]
    passed = len(found) == 0
    return HeadlineQualityResult(
        gate_id="x2_headline_no_narrowing_it_labels",
        passed=passed,
        observed_value=found if found else "none",
        threshold="zero narrowing IT labels",
        failure_reason=(
            None
            if passed
            else (
                f"Narrowing IT strategy/generic labels detected: {found}. "
                "These phrases demote the SVP Engineering / Agentic AI positioning posture."
            )
        ),
        signals=[f"narrowing_label:{f}" for f in found],
    )


def check_headline_compact_four_segment_format(headline_line: str) -> HeadlineQualityResult:
    """Enforce compact 4-segment pipe format: 4 segments, <=3 words/segment, <=12 words, <=95 non-separator chars, zero dollar metrics."""
    h = (headline_line or "").strip()
    parts = [p.strip() for p in h.split(" | ")] if " | " in h else ([h] if h else [])
    seg_wcs = [len(p.split()) for p in parts]
    total_wc = sum(seg_wcs)
    char_len = len(re.sub(r"[\s|]+", "", h))
    raw_len = len(h)
    has_dollar = bool(re.search(r"\$\s*\d", h))
    seg0 = parts[0] if parts else ""
    passed = (
        len(parts) == 4
        and seg0 != "Senior Vice President"
        and all(2 <= wc <= 3 for wc in seg_wcs)
        and total_wc <= 12
        and char_len <= 95
        and raw_len <= 140
        and not has_dollar
    )
    return HeadlineQualityResult(
        gate_id="x2_headline_compact_four_segment_format",
        passed=passed,
        observed_value={
            "segment_count": len(parts),
            "segment_word_counts": seg_wcs,
            "total_words": total_wc,
            "char_length": char_len,
            "raw_length": raw_len,
            "has_dollar_metric": has_dollar,
        },
        threshold="4 segments, 2-3 words/segment, <=12 words, <=95 chars, zero dollar metrics",
        failure_reason=(
            None
            if passed
            else (
                f"Compact 4-segment format violated: segments={len(parts)}, "
                f"seg_words={seg_wcs}, total_words={total_wc}, chars={char_len}, raw_chars={raw_len}, dollar={has_dollar}"
            )
        ),
        signals=["compact_4_segment_ok"] if passed else [],
    )


# ---------------------------------------------------------------------------
# Gate: E0 n-gram overlap (anti-leakage)
# ---------------------------------------------------------------------------


def check_headline_e0_ngram_overlap(
    headline_line: str,
    e0_texts: list[str] | None = None,
    *,
    threshold: float = E0_NGRAM_THRESHOLD,
    warn_only: bool = True,
) -> HeadlineQualityResult:
    """Fail if headline has > threshold 4-gram overlap with any E0 example text."""
    references = e0_texts if e0_texts is not None else HEADLINE_E0_REFERENCE_TEXTS
    if not references:
        return HeadlineQualityResult(
            gate_id="x2_headline_e0_ngram_overlap",
            passed=True,
            observed_value=0.0,
            threshold=f"<={threshold:.0%} 4-gram overlap with E0 examples",
            failure_reason=None,
            signals=[],
        )
    overlap = compute_max_ngram_overlap_multi_reference(
        headline_line or "", references, n=NGRAM_SIZE
    )
    passed_gate = overlap <= threshold
    passed = passed_gate or warn_only
    return HeadlineQualityResult(
        gate_id="x2_headline_e0_ngram_overlap",
        passed=passed,
        observed_value=round(overlap, 4),
        threshold=f"<={threshold:.0%} 4-gram overlap with E0 examples (WARN={'Y' if warn_only else 'N'})",
        failure_reason=(
            None
            if passed_gate
            else (
                f"E0 n-gram overlap {overlap:.1%} exceeds threshold {threshold:.0%}. "
                "Headline appears to reuse E0 example phrasing."
            )
        ),
        signals=["warn_mode"] if (warn_only and not passed_gate) else [],
    )


# ---------------------------------------------------------------------------
# Gate: base resume headline n-gram overlap (anti-hydration)
# ---------------------------------------------------------------------------


def check_headline_base_ngram_overlap(
    headline_line: str,
    base_headline_texts: list[str],
    *,
    threshold: float = BASE_NGRAM_THRESHOLD,
    warn_only: bool = True,
) -> HeadlineQualityResult:
    """Fail if headline has > threshold 4-gram overlap with the base resume headline."""
    if not base_headline_texts:
        return HeadlineQualityResult(
            gate_id="x2_headline_base_ngram_overlap",
            passed=True,
            observed_value=0.0,
            threshold=f"<={threshold:.0%} 4-gram overlap with base headline",
            failure_reason=None,
            signals=[],
        )
    overlap = compute_max_ngram_overlap_multi_reference(
        headline_line or "", base_headline_texts, n=NGRAM_SIZE
    )
    passed_gate = overlap <= threshold
    passed = passed_gate or warn_only
    return HeadlineQualityResult(
        gate_id="x2_headline_base_ngram_overlap",
        passed=passed,
        observed_value=round(overlap, 4),
        threshold=f"<={threshold:.0%} 4-gram overlap with base resume headline (WARN={'Y' if warn_only else 'N'})",
        failure_reason=(
            None
            if passed_gate
            else (
                f"Base resume n-gram overlap {overlap:.1%} exceeds threshold {threshold:.0%}. "
                "Headline must be organically generated, not rewritten from base resume."
            )
        ),
        signals=["warn_mode"] if (warn_only and not passed_gate) else [],
    )


__all__ = [
    "BASE_NGRAM_THRESHOLD",
    "E0_NGRAM_THRESHOLD",
    "HEADLINE_E0_REFERENCE_TEXTS",
    "HeadlineQualityResult",
    "NARROWING_IT_LABELS",
    "NGRAM_SIZE",
    "POSITIONING_FAMILIES",
    "check_headline_base_ngram_overlap",
    "check_headline_compact_four_segment_format",
    "check_headline_e0_ngram_overlap",
    "check_headline_no_narrowing_it_labels",
    "check_headline_positioning_families",
    "check_headline_seniority_floor",
]
