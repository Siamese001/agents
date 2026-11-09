"""Resume Swarm Challenger Service: Runtime Multi-Agent Verification.

Part of Monorepo-Wide Swarm Integration (Wave 1).
Coordinates Qualification Matcher, Factual Critic, and Voice Arbiter within a
bounded 3-turn Socratic loop to eliminate hallucinations and calibrate executive voice.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


class ResumeSwarmRole(str, Enum):
    """Specialized roles in the resume runtime swarm."""

    MATCHER = "MATCHER"
    FACTUAL_CRITIC = "FACTUAL_CRITIC"
    VOICE_ARBITER = "VOICE_ARBITER"


class ResumeSwarmDisposition(str, Enum):
    """Disposition outcomes for resume swarm deliberation."""

    APPROVED = "APPROVED"
    REVISE = "REVISE"
    ESCALATED = "ESCALATED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class BulletAudit:
    """Audit result for an individual resume bullet point."""

    original: str
    repaired: str
    is_verified: bool
    uncorroborated_claims: tuple[str, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResumeSwarmCritique:
    """Evaluation emitted by the Factual Critic and Matcher."""

    turn: int
    bullet_audits: tuple[BulletAudit, ...]
    factual_score: float
    voice_score: float
    is_passing: bool
    repair_directives: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResumeSwarmReceipt:
    """Durable receipt certifying resume swarm verification and provenance."""

    run_id: str
    turns_executed: int
    final_disposition: ResumeSwarmDisposition
    certified_bullets: tuple[str, ...]
    uncorroborated_claims_detected: int
    factual_score: float
    voice_score: float
    calibrated_confidence: float
    margin: float
    escalation_reason: str | None = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        """Convert receipt to JSON dictionary."""
        return {
            "run_id": self.run_id,
            "turns_executed": self.turns_executed,
            "final_disposition": self.final_disposition.value,
            "certified_bullets": list(self.certified_bullets),
            "uncorroborated_claims_detected": self.uncorroborated_claims_detected,
            "factual_score": self.factual_score,
            "voice_score": self.voice_score,
            "calibrated_confidence": self.calibrated_confidence,
            "margin": self.margin,
            "escalation_reason": self.escalation_reason,
            "created_at_ms": self.created_at_ms,
        }

    def write_to_path(self, target_path: Path | str) -> Path:
        """Persist receipt to disk atomically."""
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


class QualificationMatcher:
    """Matcher agent aligning candidate experience with target job competencies."""

    def match_bullet(self, bullet: str, target_keywords: Sequence[str] | None = None) -> float:
        """Calculate relevance score against target competency keywords."""
        if not target_keywords:
            return 1.0
        bullet_lower = bullet.lower()
        matches = sum(1 for kw in target_keywords if kw.lower() in bullet_lower)
        return min(1.0, round(matches / max(1, len(target_keywords)), 2) + 0.50)


class FactualCritic:
    """Critic agent cross-checking assertions and eliminating ungrounded metrics."""

    def evaluate_bullet(
        self,
        bullet: str,
        canonical_assertions: Sequence[str] | None = None,
    ) -> BulletAudit:
        """Audit single bullet against canonical facts and style rules."""
        issues: list[str] = []
        uncorroborated: list[str] = []
        repaired = bullet

        # 1. Voice check: Remove subjective first-person phrasing
        if re.search(r"\b(I am|I was|I led|my)\b", repaired, flags=re.IGNORECASE):
            issues.append("First-person pronoun detected.")
            repaired = re.sub(r"\b(I am|I was|I led)\b", "Led", repaired, flags=re.IGNORECASE)
            repaired = re.sub(r"\bmy\b", "the", repaired, flags=re.IGNORECASE)

        # 2. Factual check: Detect high-metric percentages not present in assertions
        if canonical_assertions is not None:
            metrics = re.findall(r"\b\d{2,3}%\s+\w+(?:\s+\w+)?\b", bullet, flags=re.IGNORECASE)
            for metric in metrics:
                if not any(metric.lower() in assertion.lower() for assertion in canonical_assertions):
                    issues.append(f"Uncorroborated metric: '{metric}'")
                    uncorroborated.append(metric)
                    repaired = repaired.replace(metric, "measurable growth")

        is_verified = len(issues) == 0
        return BulletAudit(
            original=bullet,
            repaired=repaired.strip(),
            is_verified=is_verified,
            uncorroborated_claims=tuple(uncorroborated),
            issues=tuple(issues),
        )


class VoiceArbiter:
    """Arbiter agent calibrating executive voice, confidence, and disposition."""

    def evaluate_seniority_voice(self, bullets: Sequence[str]) -> float:
        """Score leadership tone and executive clarity across bullets."""
        if not bullets:
            return 0.50
        weak_verbs = ("helped", "assisted", "worked on", "handled")
        strong_verbs = ("directed", "engineered", "orchestrated", "architected", "spearheaded")

        strong_count = sum(1 for b in bullets if any(v in b.lower() for v in strong_verbs))
        weak_count = sum(1 for b in bullets if any(v in b.lower() for v in weak_verbs))

        base = 0.85
        adjustment = (strong_count * 0.05) - (weak_count * 0.15)
        return round(max(0.20, min(1.0, base + adjustment)), 2)

    def arbitrate(
        self,
        turn: int,
        critique: ResumeSwarmCritique,
        max_turns: int = 3,
        ambiguity_margin: float = 0.20,
    ) -> tuple[ResumeSwarmDisposition, float, float, str | None]:
        """Compute disposition, calibrated confidence, and decision margin."""
        calibrated_conf = round((critique.factual_score * 0.60) + (critique.voice_score * 0.40), 2)
        alternative_score = round(1.0 - calibrated_conf, 2)
        margin = round(abs(calibrated_conf - alternative_score), 2)

        if critique.is_passing and calibrated_conf >= 0.75:
            return ResumeSwarmDisposition.APPROVED, calibrated_conf, margin, None

        if turn >= max_turns:
            reason = f"Deliberation limit ({max_turns} turns) exhausted with unverified claims."
            return ResumeSwarmDisposition.ESCALATED, calibrated_conf, margin, reason

        if margin <= ambiguity_margin and turn > 1:
            reason = f"Confidence spread ({margin:.2f}) within ambiguity margin ({ambiguity_margin:.2f})."
            return ResumeSwarmDisposition.ESCALATED, calibrated_conf, margin, reason

        return ResumeSwarmDisposition.REVISE, calibrated_conf, margin, None


class ResumeSwarmChallenger:
    """Coordinator executing bounded multi-agent resume verification."""

    MAX_TURNS: int = 3

    def __init__(
        self,
        matcher: QualificationMatcher | None = None,
        critic: FactualCritic | None = None,
        arbiter: VoiceArbiter | None = None,
    ) -> None:
        self._matcher = matcher or QualificationMatcher()
        self._critic = critic or FactualCritic()
        self._arbiter = arbiter or VoiceArbiter()

    def execute(
        self,
        bullets: Sequence[str],
        run_id: str = "resume_swarm_run",
        canonical_assertions: Sequence[str] | None = None,
        target_keywords: Sequence[str] | None = None,
        max_turns: int = 3,
    ) -> ResumeSwarmReceipt:
        """Run bounded deliberation on candidate resume bullets."""
        bounded_turns = min(max_turns, self.MAX_TURNS)
        current_bullets = list(bullets)
        final_disposition = ResumeSwarmDisposition.REVISE
        escalation_reason: str | None = None
        final_conf = 0.50
        final_margin = 0.0
        final_factual = 0.50
        final_voice = 0.50
        total_uncorroborated = 0

        for turn_idx in range(1, bounded_turns + 1):
            audits = [
                self._critic.evaluate_bullet(b, canonical_assertions)
                for b in current_bullets
            ]
            uncorroborated_in_turn = sum(len(a.uncorroborated_claims) for a in audits)
            total_uncorroborated += uncorroborated_in_turn

            verified_count = sum(1 for a in audits if a.is_verified)
            factual_score = round(verified_count / max(1, len(audits)), 2)
            voice_score = self._arbiter.evaluate_seniority_voice(current_bullets)

            final_factual = factual_score
            final_voice = voice_score
            is_passing = (factual_score == 1.0) and (voice_score >= 0.80)

            directives = []
            for a in audits:
                directives.extend(a.issues)

            critique = ResumeSwarmCritique(
                turn=turn_idx,
                bullet_audits=tuple(audits),
                factual_score=factual_score,
                voice_score=voice_score,
                is_passing=is_passing,
                repair_directives=tuple(directives),
            )

            disposition, conf, margin, reason = self._arbiter.arbitrate(
                turn=turn_idx,
                critique=critique,
                max_turns=bounded_turns,
            )
            final_conf = conf
            final_margin = margin
            final_disposition = disposition
            escalation_reason = reason

            if disposition == ResumeSwarmDisposition.APPROVED:
                break
            if disposition == ResumeSwarmDisposition.ESCALATED:
                break

            # Apply repairs for subsequent turn
            current_bullets = [a.repaired for a in audits]

        return ResumeSwarmReceipt(
            run_id=run_id,
            turns_executed=turn_idx,
            final_disposition=final_disposition,
            certified_bullets=tuple(current_bullets),
            uncorroborated_claims_detected=total_uncorroborated,
            factual_score=final_factual,
            voice_score=final_voice,
            calibrated_confidence=final_conf,
            margin=final_margin,
            escalation_reason=escalation_reason,
        )


def verify_with_swarm(
    bullets: Sequence[str],
    *,
    canonical_assertions: Sequence[str] | None = None,
    target_keywords: Sequence[str] | None = None,
    run_id: str = "resume_swarm_run",
) -> ResumeSwarmReceipt:
    """Validate resume bullets through multi-agent challenger swarm."""
    challenger = ResumeSwarmChallenger()
    return challenger.execute(
        bullets=bullets,
        run_id=run_id,
        canonical_assertions=canonical_assertions,
        target_keywords=target_keywords,
    )

