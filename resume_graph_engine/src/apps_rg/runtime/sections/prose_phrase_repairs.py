"""Deterministic prose phrase repair helpers for bullet and narrative lanes."""
from __future__ import annotations

from apps_rg.runtime.sections.cross_section_signal_guards import (
    apply_bullet_consulting_clean,
    apply_narrative_consulting_clean,
    rewrite_generic_consulting_phrases,
)


def apply_deterministic_prose_repairs(text: str) -> str:
    """Deterministically repair banned generic consulting phrases in prose text."""
    return rewrite_generic_consulting_phrases(text)


__all__ = [
    "apply_bullet_consulting_clean",
    "apply_deterministic_prose_repairs",
    "apply_narrative_consulting_clean",
    "rewrite_generic_consulting_phrases",
]
