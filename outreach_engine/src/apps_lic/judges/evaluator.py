"""Standalone judge evaluator executing the 4 core apps_lic rubrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

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
    feedback: List[str] = field(default_factory=list)
    remediation_hints: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "hop1_classifier_score": self.hop1_classifier_score,
            "hop2_grounding_score": self.hop2_grounding_score,
            "hop6_alignment_score": self.hop6_alignment_score,
            "hop8_narrative_score": self.hop8_narrative_score,
            "feedback": list(self.feedback),
            "remediation_hints": list(self.remediation_hints),
        }


class RubricJudgeEvaluator:
    """Automated judge applying the 4 canonical evaluation rubrics."""

    def __init__(self, rubrics_dir: Path | str | None = None) -> None:
        if rubrics_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            self.rubrics_dir = repo_root / "config" / "rubrics"
        else:
            self.rubrics_dir = Path(rubrics_dir)
        self._rubrics = self._load_rubrics()

    def _load_rubrics(self) -> dict[str, dict[str, Any]]:
        rubrics: dict[str, dict[str, Any]] = {}
        if not self.rubrics_dir.is_dir():
            return rubrics
        for f in self.rubrics_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "rubric_id" in data:
                    rubrics[data["rubric_id"]] = data
            except Exception:
                pass
        return rubrics

    def evaluate(
        self,
        draft: OutreachMessageDraft,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
    ) -> EvaluationReport:
        feedback: List[str] = []
        hints: List[str] = []

        # Hop 1: Classifier & Channel Suitability
        hop1_score = 1.0
        if opportunity.recipient_class == RecipientClass.BOARD_MEMBER and draft.channel.value == "connection_note":
            hop1_score = 0.5
            feedback.append("Hop 1: Board member outreach should prefer InMail or Executive Email over brief connection note.")
            hints.append("Upgrade channel to InMail or Executive Email for Board Member tier.")

        # Hop 2: Grounding (Zero Hallucination)
        allowed_facts = {f.fact_id for f in candidate.verified_facts}
        ungrounded = [f for f in draft.grounded_facts_used if f not in allowed_facts]
        if ungrounded:
            hop2_score = 0.0
            feedback.append(f"Hop 2 Grounding Failure: Found ungrounded claims {ungrounded}.")
            hints.append("Remove or verify claims not present in candidate profile.")
        else:
            hop2_score = 1.0

        # Hop 6: Alignment & Tone
        hop6_score = 1.0
        body_lower = draft.body.lower()
        if any(w in body_lower for w in ("you must", "hire me", "my demands", "give me a job")):
            hop6_score = 0.2
            feedback.append("Hop 6 Alignment Failure: Aggressive or entitled tone detected.")
            hints.append("Frame outreach with reciprocity and peer-to-peer alignment.")

        # Hop 8: Narrative & CTA Friction
        hop8_score = 1.0
        if not draft.body.strip().endswith("?"):
            hop8_score = 0.4
            feedback.append("Hop 8 Narrative Warning: Missing conversational closing question.")
            hints.append("End message with a low-friction question mark.")

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
            remediation_hints=hints,
        )


__all__ = ["RubricJudgeEvaluator", "EvaluationReport"]
