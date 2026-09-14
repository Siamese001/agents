"""Executive Summary Voice Repair Service.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Replaces unconstrained regex patching with declarative, ordered repair rules,
scoped matching, and mandatory post-repair validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True, slots=True)
class RepairRule:
    """Declarative, deterministic voice repair rule."""

    name: str
    pattern: str
    replacement: str
    description: str
    is_regex: bool = False
    is_safe: bool = True


DEFAULT_VOICE_RULES: tuple[RepairRule, ...] = (
    RepairRule(
        name="remove_first_person_singular",
        pattern=r"\bI am\b",
        replacement="Accomplished professional with experience in",
        description="Eliminate first-person phrasing from executive summary opening.",
        is_regex=True,
    ),
    RepairRule(
        name="remove_first_person_pronoun",
        pattern=r"\bmy\b",
        replacement="the",
        description="Replace subjective possessive pronouns with objective determiners.",
        is_regex=True,
    ),
    RepairRule(
        name="passive_voice_strengthening",
        pattern=r"\bwas responsible for\b",
        replacement="directed and executed",
        description="Replace passive responsibility wording with active verbs.",
        is_regex=True,
    ),
    RepairRule(
        name="trailing_whitespace_normalization",
        pattern=r"[ \t]+(?=\n|$)",
        replacement="",
        description="Strip trailing whitespace from lines.",
        is_regex=True,
    ),
)


@dataclass(frozen=True, slots=True)
class RepairResult:
    """Outcome of applying voice repair rules."""

    original_text: str
    repaired_text: str
    was_modified: bool
    applied_rules: tuple[str, ...]
    is_valid: bool
    errors: tuple[str, ...] = ()

    @property
    def is_successful(self) -> bool:
        return self.is_valid and len(self.errors) == 0


class ExecutiveSummaryRepairService:
    """Domain service executing deterministic, rule-based executive summary repairs."""

    def __init__(self, rules: Sequence[RepairRule] | None = None) -> None:
        self._rules = tuple(rules or DEFAULT_VOICE_RULES)

    def repair(self, text: str, max_rules_applied: int = 10) -> RepairResult:
        """Apply configured repair rules deterministically."""
        if not text.strip():
            return RepairResult(
                original_text=text,
                repaired_text=text,
                was_modified=False,
                applied_rules=(),
                is_valid=True,
                errors=(),
            )

        current = text
        applied: list[str] = []

        for rule in self._rules:
            if len(applied) >= max_rules_applied:
                break

            if rule.is_regex:
                if re.search(rule.pattern, current, flags=re.IGNORECASE):
                    current = re.sub(
                        rule.pattern,
                        rule.replacement,
                        current,
                        flags=re.IGNORECASE,
                    )
                    applied.append(rule.name)
            else:
                if rule.pattern in current:
                    current = current.replace(rule.pattern, rule.replacement)
                    applied.append(rule.name)

        # Post-repair safety validation
        errors: list[str] = []
        if len(current.strip()) == 0 and len(text.strip()) > 0:
            errors.append("Repair rule inadvertently stripped all content.")

        was_modified = current != text
        is_valid = len(errors) == 0

        return RepairResult(
            original_text=text,
            repaired_text=current if is_valid else text,
            was_modified=was_modified and is_valid,
            applied_rules=tuple(applied),
            is_valid=is_valid,
            errors=tuple(errors),
        )
