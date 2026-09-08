"""Standalone judge evaluator executing the 4 core apps_lic rubrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from apps_lic.domain.models import (
    CandidateProfile,
    OutreachMessageDraft,
    RecipientClass,
    TargetOpportunity,
)


@dataclass
class EvaluationReport:
    """Consolidated rubric evaluation report."""
    passed: bool
    hop1_classifier_score: float
    hop2_grounding_score: float
    hop6_alignment_score: float
    hop8_narrative_score: float
    feedback: List[str]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "hop1_classifier_score": self.hop1_classifier_score,
            "hop2_grounding_score": self.hop2_grounding_score,
            "hop6_alignment_score": self.hop6_alignment_score,
            "hop8_narrative_score": self.hop8_narrative_score,
            "feedback": list(self.feedback),
        }


class RubricJudgeEvaluator:
    """Automated judge applying the 4 canonical evaluation rubrics."""

    def evaluate(
        self,
        draft: OutreachMessageDraft,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
    ) -> EvaluationReport:
        feedback: List[str] = []

        # Hop 1: Classifier & Channel Suitability
        hop1_score = 1.0
        if opportunity.recipient_class == RecipientClass.BOARD_MEMBER and draft.channel.value == "connection_note":
            hop1_score = 0.5
            feedback.append("Hop 1: Board member outreach should prefer InMail or Executive Email over brief connection note.")

        # Hop 2: Grounding (Zero Hallucination)
        allowed_facts = {f.fact_id for f in candidate.verified_facts}
        ungrounded = [f for f in draft.grounded_facts_used if f not in allowed_facts]
        if ungrounded:
            hop2_score = 0.0
            feedback.append(f"Hop 2 Grounding Failure: Found ungrounded claims {ungrounded}.")
        else:
            hop2_score = 1.0

        # Hop 6: Alignment & Tone
        hop6_score = 1.0
        body_lower = draft.body.lower()
        if "you must" in body_lower or "hire me" in body_lower:
            hop6_score = 0.2
            feedback.append("Hop 6 Alignment Failure: Aggressive or entitled tone detected.")

        # Hop 8: Narrative & CTA Friction
        hop8_score = 1.0
        if not draft.body.strip().endswith("?"):
            hop8_score = 0.4
            feedback.append("Hop 8 Narrative Warning: Missing conversational closing question.")

        passed = (
            hop1_score >= 0.7
            and hop2_score >= 0.99
            and hop6_score >= 0.7
            and hop8_score >= 0.7
        )

        return EvaluationReport(
            passed=passed,
            hop1_classifier_score=hop1_score,
            hop2_grounding_score=hop2_score,
            hop6_alignment_score=hop6_score,
            hop8_narrative_score=hop8_score,
            feedback=feedback,
        )


__all__ = ["RubricJudgeEvaluator", "EvaluationReport"]
