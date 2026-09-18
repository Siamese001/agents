"""Canonical human-facing labels for résumé sections (export, manifest, run summaries).

JSON/schema keys stay ``skills`` / ``competencies`` where required; operator surfaces use
``ENGINEERING & PLATFORM COMPETENCIES`` for the same bucket.
"""

from __future__ import annotations

ENGINEERING_PLATFORM_COMPETENCIES_HEADING: str = "ENGINEERING & PLATFORM COMPETENCIES"
EXECUTIVE_TRANSFORMATION_COMPETENCIES_HEADING: str = "EXECUTIVE & TRANSFORMATION COMPETENCIES"
CORE_COMPETENCIES_HEADING: str = "CORE COMPETENCIES"

ALLOWED_COMPETENCIES_HEADINGS: tuple[str, ...] = (
    ENGINEERING_PLATFORM_COMPETENCIES_HEADING,
    EXECUTIVE_TRANSFORMATION_COMPETENCIES_HEADING,
    CORE_COMPETENCIES_HEADING,
)

CERTIFICATIONS_AND_CREDENTIALS_HEADING: str = "CERTIFICATIONS & CREDENTIALS"

_SECTION_HEADING_BY_ID: dict[str, str] = {
    "certifications": CERTIFICATIONS_AND_CREDENTIALS_HEADING,
    "competencies": ENGINEERING_PLATFORM_COMPETENCIES_HEADING,
    "skills": ENGINEERING_PLATFORM_COMPETENCIES_HEADING,
    "skills_block": ENGINEERING_PLATFORM_COMPETENCIES_HEADING,
}


def summary_section_label(section_id: str) -> str:
    """Résumé section label for narrative verdicts, gate failures, and operator logs."""
    sid = str(section_id or "").strip()
    return _SECTION_HEADING_BY_ID.get(sid, sid)


def resolve_competencies_heading(target_role_profile: str | None = None) -> str:
    """Resolve human-facing competencies heading based on target role profile."""
    prof = str(target_role_profile or "").strip()
    if prof in ("executive_agentic_transformation", "advisory_transformation"):
        return EXECUTIVE_TRANSFORMATION_COMPETENCIES_HEADING
    return ENGINEERING_PLATFORM_COMPETENCIES_HEADING


__all__ = [
    "ALLOWED_COMPETENCIES_HEADINGS",
    "CERTIFICATIONS_AND_CREDENTIALS_HEADING",
    "CORE_COMPETENCIES_HEADING",
    "ENGINEERING_PLATFORM_COMPETENCIES_HEADING",
    "EXECUTIVE_TRANSFORMATION_COMPETENCIES_HEADING",
    "resolve_competencies_heading",
    "summary_section_label",
]
