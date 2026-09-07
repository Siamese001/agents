"""Tier-1 Hermetic JD Context Briefing Engine.

Extracts company positioning, technical signals, and role context strictly from
the provided Job Description text. Operates 100% offline with zero network I/O,
providing a deterministic fallback when live web research (SearXNG) is unavailable
or disabled.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class JDContextBriefingResult:
    company_name: str
    target_role: str
    briefing_text: str
    digest: str
    provenance: str = "provenance.jd_derived_offline.v1"
    evidence_count: int = 0
    confidence_score: float = 0.85
    metadata: dict[str, Any] = field(default_factory=dict)


def _extract_key_phrases(text: str, max_items: int = 4) -> list[str]:
    """Heuristic extraction of key technical/domain requirements from JD text."""
    if not text:
        return []
    lines = [line.strip().lstrip("-*• ") for line in text.splitlines() if line.strip()]
    candidates: list[str] = []
    keywords = ("experience", "lead", "build", "design", "architect", "scale", "cloud", "ai", "platform", "senior")
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in keywords) and 15 <= len(line) <= 120:
            candidates.append(line)
            if len(candidates) >= max_items:
                break
    return candidates or lines[:max_items]


def extract_jd_briefing(
    *,
    company_name: str,
    target_role: str,
    jd_text: str,
    jd_ref: str = "",
) -> JDContextBriefingResult:
    """Generate a hermetic briefing substrate from JD context only."""
    resolved_company = (company_name or "").strip() or "Target Organization"
    resolved_role = (target_role or "").strip() or "Target Position"
    clean_jd = (jd_text or "").strip()

    extracted_signals = _extract_key_phrases(clean_jd, max_items=4)

    bullet_lines = []
    if extracted_signals:
        for signal in extracted_signals:
            bullet_lines.append(f"- Core Responsibility / Domain: {signal}")
    else:
        bullet_lines.append(f"- Focused on executive mandate and operational objectives for {resolved_role}.")

    findings_block = "\n".join(bullet_lines)

    briefing_content = (
        f"# Research Briefing: {resolved_company}\n\n"
        f"## Research Summary\n"
        f"- Target Entity: {resolved_company}\n"
        f"- Target Role: {resolved_role}\n"
        f"- Operating Context: Hermetic JD-derived targeting synthesis for resume tailoring.\n\n"
        f"## Key Findings\n"
        f"{findings_block}\n"
        f"- Technical & Leadership Focus: Synthesized directly from primary JD source specifications.\n\n"
        f"## Source Attributions\n"
        f"- S01: Primary Job Description ({jd_ref or 'inline_text'}) [DIRECT_EVIDENCE]\n\n"
        f"## Confidence Assessment\n"
        f"- Confidence Score: 0.85 (High confidence from direct employer specification).\n\n"
        f"## Reuse Policy\n"
        f"- Scope: Bounded to run-specific resume generation for {resolved_company} ({resolved_role}).\n"
    )

    content_bytes = briefing_content.encode("utf-8")
    content_digest = "sha256:" + hashlib.sha256(content_bytes).hexdigest()

    return JDContextBriefingResult(
        company_name=resolved_company,
        target_role=resolved_role,
        briefing_text=briefing_content,
        digest=content_digest,
        evidence_count=len(extracted_signals) + 1,
        confidence_score=0.85,
        metadata={
            "jd_ref": jd_ref,
            "char_length": len(briefing_content),
            "jd_length": len(clean_jd),
            "offline_hermetic": True,
        },
    )


__all__ = [
    "JDContextBriefingResult",
    "extract_jd_briefing",
]
