"""Executive Summary Package.

Decomposes monolithic voice repair into declarative rules, tokenization,
deterministic repair engine, and policy validation.
"""

from apps_rg.runtime.sections.executive_summary.parsing import (
    count_words,
    extract_bullets,
    tokenize_sentences,
)
from apps_rg.runtime.sections.executive_summary.policy import VoiceRepairPolicy
from apps_rg.runtime.sections.executive_summary.repair import (
    ExecutiveSummaryRepairEngine,
    RepairAuditEntry,
    RepairResult,
)
from apps_rg.runtime.sections.executive_summary.rules import (
    DEFAULT_REPAIR_RULES,
    RepairRule,
)
from apps_rg.runtime.sections.executive_summary.validation import (
    ExecutiveSummaryValidator,
    ValidationOutcome,
)

__all__ = [
    "DEFAULT_REPAIR_RULES",
    "ExecutiveSummaryRepairEngine",
    "ExecutiveSummaryValidator",
    "RepairAuditEntry",
    "RepairResult",
    "RepairRule",
    "ValidationOutcome",
    "VoiceRepairPolicy",
    "count_words",
    "extract_bullets",
    "tokenize_sentences",
]
