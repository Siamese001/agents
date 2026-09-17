"""Multi-lens rubric judge evaluator for executive outreach, adapted from apps_rg Rubric v3."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    TargetOpportunity,
)
from apps_lic.domain.validators import (
    ChannelLengthValidator,
    EmDashValidator,
    GroundingValidator,
    MarkdownLinkValidator,
    QuestionEndingValidator,
    SpamTriggerValidator,
    SubordinateToneValidator,
)


@dataclass
class EvaluationReport:
    """Consolidated multi-lens rubric evaluation report."""
    passed: bool
    lens1_altitude_score: float = 1.0
    lens2_grounding_score: float = 1.0
    lens3_resonance_score: float = 1.0
    lens4_cta_score: float = 1.0
    lens5_anti_spam_score: float = 1.0
    lens6_constraints_score: float = 1.0
    # Backward compatibility fields for legacy callers
    hop1_classifier_score: float = 1.0
    hop2_grounding_score: float = 1.0
    hop6_alignment_score: float = 1.0
    hop8_narrative_score: float = 1.0
    feedback: List[str] = field(default_factory=list)
    remediation_hints: List[str] = field(default_factory=list)
    lens_scores: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.lens_scores:
            self.lens_scores = {
                "lens1_altitude": self.lens1_altitude_score,
                "lens2_grounding": self.lens2_grounding_score,
                "lens3_resonance": self.lens3_resonance_score,
                "lens4_cta": self.lens4_cta_score,
                "lens5_anti_spam": self.lens5_anti_spam_score,
                "lens6_constraints": self.lens6_constraints_score,
            }

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "lens1_altitude_score": self.lens1_altitude_score,
            "lens2_grounding_score": self.lens2_grounding_score,
            "lens3_resonance_score": self.lens3_resonance_score,
            "lens4_cta_score": self.lens4_cta_score,
            "lens5_anti_spam_score": self.lens5_anti_spam_score,
            "lens6_constraints_score": self.lens6_constraints_score,
            "hop1_classifier_score": self.hop1_classifier_score,
            "hop2_grounding_score": self.hop2_grounding_score,
            "hop6_alignment_score": self.hop6_alignment_score,
            "hop8_narrative_score": self.hop8_narrative_score,
            "feedback": list(self.feedback),
            "remediation_hints": list(self.remediation_hints),
            "lens_scores": dict(self.lens_scores),
        }


class ExecutiveOutreachJudgePanel:
    """Authoritative 6-lens judge panel adapting apps_rg Rubric v3 to executive outreach."""

    def __init__(self, rubrics_dir: Path | str | None = None) -> None:
        if rubrics_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            self.rubrics_dir = repo_root / "config" / "rubrics"
        else:
            self.rubrics_dir = Path(rubrics_dir)
        self._rubrics = self._load_rubrics()
        self._spam_validator = SpamTriggerValidator()
        self._length_validator = ChannelLengthValidator()
        self._question_validator = QuestionEndingValidator()
        self._grounding_validator = GroundingValidator()
        self._dash_validator = EmDashValidator()
        self._link_validator = MarkdownLinkValidator()
        self._tone_validator = SubordinateToneValidator()

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

        # =====================================================================
        # Lens 1: Altitude, Persona & Peer Framing (adapted from Rubric v3 Lens 5)
        # =====================================================================
        lens1_score = 1.0
        tone_valid, tone_viols = self._tone_validator.validate(draft.body)
        if not tone_valid:
            lens1_score = 0.3
            feedback.append(f"Lens 1 (Altitude) Failure: {', '.join(tone_viols)}")
            hints.append("Adopt peer-to-peer executive framing; eliminate subordinate job-seeking phrases.")

        if opportunity.recipient_class == RecipientClass.BOARD_MEMBER and draft.channel == ChannelType.LINKEDIN_CONNECTION:
            lens1_score = min(lens1_score, 0.5)
            feedback.append("Lens 1 (Altitude) Warning: Board member outreach should prefer InMail or Executive Email.")
            hints.append("Upgrade channel to InMail or Executive Email for Board Member tier.")

        # =====================================================================
        # Lens 2: Zero-Hallucination Grounding & Fact Binding (Rubric v3 Lens 2)
        # =====================================================================
        lens2_score = 1.0
        allowed_facts = {f.fact_id for f in candidate.verified_facts}
        g_valid, g_viols = self._grounding_validator.validate(draft.grounded_facts_used, allowed_facts)
        if not g_valid:
            lens2_score = 0.0
            feedback.append(f"Lens 2 (Grounding) Failure: {', '.join(g_viols)}")
            hints.append("All claims must map directly to verified candidate facts.")

        # =====================================================================
        # Lens 3: Strategic Briefing Resonance (Rubric v3 Lens 3)
        # =====================================================================
        lens3_score = 1.0
        company_lower = opportunity.company_name.lower()
        body_lower = draft.body.lower()
        subject_lower = draft.subject.lower()

        has_company_ref = company_lower in body_lower or company_lower in subject_lower
        has_priority_ref = False
        for p in opportunity.strategic_priorities:
            tokens = [t.lower() for t in re.findall(r"\b[A-Za-z]{4,}\b", p)]
            if any(tok in body_lower for tok in tokens[:4]):
                has_priority_ref = True
                break

        if not has_company_ref and not has_priority_ref:
            lens3_score = 0.4
            feedback.append("Lens 3 (Resonance) Failure: Outreach lacks reference to company priorities or mandate.")
            hints.append("Anchor message to verified strategic priorities from company briefing.")

        # =====================================================================
        # Lens 4: Friction & CTA Calibration (Rubric v3 Lens 4)
        # =====================================================================
        lens4_score = 1.0
        q_valid, q_err = self._question_validator.validate(draft.body)
        if not q_valid and q_err:
            lens4_score = 0.4
            feedback.append(f"Lens 4 (CTA) Failure: {q_err}")
            hints.append("Conclude message with a low-friction inquiry ending with a question mark.")

        if any(w in body_lower for w in ("you must", "my demands", "give me a job", "need a response today")):
            lens4_score = min(lens4_score, 0.2)
            feedback.append("Lens 4 (CTA) Failure: High-friction or demanding call-to-action detected.")
            hints.append("Reframe call to action as a low-friction value exchange.")

        # =====================================================================
        # Lens 5: Anti-Spam, Anti-Cliche & Tone Guardrails (Rubric v3 Lens 1)
        # =====================================================================
        lens5_score = 1.0
        spam_valid, spam_viols, spam_warns = self._spam_validator.validate(draft.body)
        if not spam_valid:
            lens5_score = 0.2
            feedback.append(f"Lens 5 (Anti-Spam) Failure: {', '.join(spam_viols)}")
            hints.append("Eliminate sales urgency and aggressive pitching language.")
        elif spam_warns:
            lens5_score = 0.8
            feedback.append(f"Lens 5 (Anti-Spam) Warning: {', '.join(spam_warns)}")
            hints.append("Avoid corporate cliches and formulaic generic openers.")

        dash_valid, dash_err = self._dash_validator.validate(draft.body)
        if not dash_valid and dash_err:
            lens5_score = min(lens5_score, 0.6)
            feedback.append(f"Lens 5 (Style) Warning: {dash_err}")
            hints.append("Replace em dashes with commas or hyphens per writing preferences.")

        # =====================================================================
        # Lens 6: Channel & Constraint Compliance (Rubric v3 Lens 6)
        # =====================================================================
        lens6_score = 1.0
        len_valid, len_err = self._length_validator.validate(draft.channel, draft.body)
        if not len_valid and len_err:
            lens6_score = 0.0
            feedback.append(f"Lens 6 (Constraints) Failure: {len_err}")
            hints.append("Trim message to stay within strict channel character ceilings.")

        link_valid, link_err = self._link_validator.validate(draft.body)
        if not link_valid and link_err:
            lens6_score = min(lens6_score, 0.5)
            feedback.append(f"Lens 6 (Constraints) Failure: {link_err}")
            hints.append("Use plain-text URLs instead of markdown link syntax.")

        passed = (
            lens1_score >= 0.70
            and lens2_score >= 0.99
            and lens3_score >= 0.70
            and lens4_score >= 0.70
            and lens5_score >= 0.70
            and lens6_score >= 0.70
        )

        hop1 = min(lens1_score, lens6_score)
        hop2 = lens2_score
        hop6 = min(lens3_score, lens5_score)
        hop8 = lens4_score

        return EvaluationReport(
            passed=passed,
            lens1_altitude_score=lens1_score,
            lens2_grounding_score=lens2_score,
            lens3_resonance_score=lens3_score,
            lens4_cta_score=lens4_score,
            lens5_anti_spam_score=lens5_score,
            lens6_constraints_score=lens6_score,
            hop1_classifier_score=hop1,
            hop2_grounding_score=hop2,
            hop6_alignment_score=hop6,
            hop8_narrative_score=hop8,
            feedback=feedback,
            remediation_hints=hints,
        )


# Backward-compatible alias
RubricJudgeEvaluator = ExecutiveOutreachJudgePanel

__all__ = [
    "EvaluationReport",
    "ExecutiveOutreachJudgePanel",
    "RubricJudgeEvaluator",
]
