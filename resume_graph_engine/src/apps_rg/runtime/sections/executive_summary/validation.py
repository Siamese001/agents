"""Executive Summary Validation Engine.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from apps_rg.runtime.sections.executive_summary.parsing import count_words, tokenize_sentences
from apps_rg.runtime.sections.executive_summary.policy import VoiceRepairPolicy


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    """Validation report for an executive summary text."""

    is_valid: bool
    word_count: int
    sentence_count: int
    violations: tuple[str, ...]


class ExecutiveSummaryValidator:
    """Validates executive summary text against voice policy."""

    def __init__(self, policy: VoiceRepairPolicy | None = None) -> None:
        self.policy = policy or VoiceRepairPolicy()

    def validate(self, text: str) -> ValidationOutcome:
        """Validate text against policy constraints."""
        violations: list[str] = []
        words = count_words(text)
        sentences = tokenize_sentences(text)

        if words > self.policy.max_word_count:
            violations.append(f"Word count {words} exceeds maximum allowed {self.policy.max_word_count}.")
        elif words < self.policy.min_word_count:
            violations.append(f"Word count {words} is below minimum required {self.policy.min_word_count}.")

        for idx, sentence in enumerate(sentences):
            sent_words = count_words(sentence)
            if sent_words > self.policy.max_sentence_length:
                violations.append(
                    f"Sentence {idx + 1} exceeds max length ({sent_words} > {self.policy.max_sentence_length})."
                )

        return ValidationOutcome(
            is_valid=len(violations) == 0,
            word_count=words,
            sentence_count=len(sentences),
            violations=tuple(violations),
        )
