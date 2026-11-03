"""Policy and Guardrails for Executive Summary Voice Repair.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
"""

from __future__ import annotations

from dataclasses import dataclass

from apps_rg.runtime.validators.executive_summary_x2 import (
    EXEC_SUMMARY_MAX_WORDS,
    EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE,
)


@dataclass(frozen=True, slots=True)
class VoiceRepairPolicy:
    """Policy bounds governing permissible voice repair transformations."""

    max_word_count: int = EXEC_SUMMARY_MAX_WORDS
    min_word_count: int = 30
    max_sentence_length: int = EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE
    prohibit_passive_hedging: bool = True
    max_repair_passes: int = 3
