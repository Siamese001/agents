"""Declarative Named Repair Rules for Executive Summary Voice.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Replaces unbounded manual regex patching with explicit, deterministic, and auditable rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Pattern


@dataclass(frozen=True, slots=True)
class RepairRule:
    """Declarative, named rule for text repair and normalization."""

    rule_id: str
    description: str
    pattern: Pattern[str]
    replacement: str
    priority: int = 100

    def apply(self, text: str) -> tuple[str, int]:
        """Apply rule to text, returning new text and substitution count."""
        new_text, count = self.pattern.subn(self.replacement, text)
        return new_text, count


DEFAULT_REPAIR_RULES: tuple[RepairRule, ...] = (
    RepairRule(
        rule_id="normalize_whitespace",
        description="Collapse excessive horizontal whitespace",
        pattern=re.compile(r"[ \t]{2,}"),
        replacement=" ",
        priority=10,
    ),
    RepairRule(
        rule_id="remove_passive_hedging",
        description="Replace passive introductory phrases",
        pattern=re.compile(r"\b(?:it should be noted that|as a matter of fact|in order to)\b", re.IGNORECASE),
        replacement="to",
        priority=20,
    ),
    RepairRule(
        rule_id="strip_redundant_qualifiers",
        description="Remove filler adverbs like 'very', 'extremely', 'basically'",
        pattern=re.compile(r"\b(?:very|extremely|basically|virtually|actually)\s+", re.IGNORECASE),
        replacement="",
        priority=30,
    ),
    RepairRule(
        rule_id="standardize_bullet_prefix",
        description="Ensure consistent bullet formatting with dash",
        pattern=re.compile(r"^\s*[\*\u2022]\s+", re.MULTILINE),
        replacement="- ",
        priority=40,
    ),
    RepairRule(
        rule_id="fix_dangling_commas",
        description="Remove dangling commas before sentence end",
        pattern=re.compile(r",\s*\."),
        replacement=".",
        priority=50,
    ),
)
