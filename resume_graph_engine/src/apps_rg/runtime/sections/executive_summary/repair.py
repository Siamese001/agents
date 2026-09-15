"""Deterministic Executive Summary Repair Engine.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Executes ordered declarative repair rules with audit logging, without arbitrary regex mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from apps_rg.runtime.sections.executive_summary.policy import VoiceRepairPolicy
from apps_rg.runtime.sections.executive_summary.rules import DEFAULT_REPAIR_RULES, RepairRule


@dataclass(frozen=True, slots=True)
class RepairAuditEntry:
    """Record of an applied repair rule."""

    rule_id: str
    description: str
    substitutions: int


@dataclass(frozen=True, slots=True)
class RepairResult:
    """Outcome of an executive summary voice repair run."""

    original_text: str
    repaired_text: str
    total_modifications: int
    applied_rules: tuple[RepairAuditEntry, ...]
    is_modified: bool


class ExecutiveSummaryRepairEngine:
    """Applies declarative repair rules in strict deterministic priority order."""

    def __init__(
        self,
        rules: Sequence[RepairRule] | None = None,
        policy: VoiceRepairPolicy | None = None,
    ) -> None:
        self.rules = tuple(sorted(rules or DEFAULT_REPAIR_RULES, key=lambda r: r.priority))
        self.policy = policy or VoiceRepairPolicy()

    def repair_text(self, text: str) -> RepairResult:
        """Apply repair rules deterministically."""
        current = text
        applied: list[RepairAuditEntry] = []
        total_subs = 0

        for rule in self.rules:
            new_text, count = rule.apply(current)
            if count > 0:
                applied.append(
                    RepairAuditEntry(
                        rule_id=rule.rule_id,
                        description=rule.description,
                        substitutions=count,
                    )
                )
                total_subs += count
                current = new_text

        return RepairResult(
            original_text=text,
            repaired_text=current.strip(),
            total_modifications=total_subs,
            applied_rules=tuple(applied),
            is_modified=total_subs > 0,
        )
