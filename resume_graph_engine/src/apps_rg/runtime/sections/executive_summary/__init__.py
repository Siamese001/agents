"""Executive Summary Modular Sub-Package.

Modularized stage handlers, context assembler, prompt builders, and repair engines.
"""
from __future__ import annotations

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .synthesis_repair import *
from .word_budget_repair import *
from .lane_runner import run_executive_summary_execution
from .parsing import count_words, extract_bullets, tokenize_sentences
from .policy import VoiceRepairPolicy
from .repair import ExecutiveSummaryRepairEngine, RepairAuditEntry, RepairResult
from .rules import DEFAULT_REPAIR_RULES, RepairRule
from .validation import ExecutiveSummaryValidator, ValidationOutcome

__all__ = [
    "run_executive_summary_execution",
    "VoiceRepairPolicy",
    "RepairRule",
    "DEFAULT_REPAIR_RULES",
    "ExecutiveSummaryRepairEngine",
    "RepairAuditEntry",
    "RepairResult",
    "ExecutiveSummaryValidator",
    "ValidationOutcome",
    "tokenize_sentences",
    "extract_bullets",
    "count_words",
]
