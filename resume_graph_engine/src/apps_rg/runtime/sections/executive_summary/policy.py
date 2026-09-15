"""Policy and Guardrails for Executive Summary Voice Repair.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceRepairPolicy:
    """Policy bounds governing permissible voice repair transformations."""

    max_word_count: int = 150
    min_word_count: int = 30
    max_sentence_length: int = 35
    prohibit_passive_hedging: bool = True
    max_repair_passes: int = 3
