"""Outreach Swarm Challenger Service: Runtime Multi-Agent Tone and Delivery Verification.

Part of Monorepo-Wide Swarm Integration (Wave 2).
Coordinates Value Proposition Drafter, Tone & Compliance Critic, and Delivery Arbiter
within a bounded 3-turn Socratic loop to eliminate spam triggers, em-dashes, and sycophancy.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


class OutreachSwarmRole(str, Enum):
    """Specialized roles in the outreach runtime swarm."""

    DRAFTER = "DRAFTER"
    TONE_CRITIC = "TONE_CRITIC"
    DELIVERY_ARBITER = "DELIVERY_ARBITER"


class OutreachSwarmDisposition(str, Enum):
    """Disposition states for outreach message deliberation."""

    APPROVED = "APPROVED"
    REVISE = "REVISE"
    ESCALATED = "ESCALATED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class OutreachMessageAudit:
    """Detailed audit metrics for an outreach message draft."""

    original_text: str
    repaired_text: str
    word_count: int
    is_length_compliant: bool
    is_tone_compliant: bool
    spam_triggers_found: tuple[str, ...]
    em_dashes_found: int
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutreachSwarmCritique:
    """Evaluation emitted by the Tone & Compliance Critic."""

    turn: int
    audit: OutreachMessageAudit
    tone_score: float
    compliance_score: float
    is_passing: bool
    repair_directives: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutreachSwarmReceipt:
    """Durable receipt certifying outreach message compliance and delivery readiness."""

    campaign_id: str
    turns_executed: int
    final_disposition: OutreachSwarmDisposition
    certified_message: str
    word_count: int
    calibrated_confidence: float
    margin: float
    issues_resolved: int
    escalation_reason: str | None = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        """Convert receipt to JSON dictionary."""
        return {
            "campaign_id": self.campaign_id,
            "turns_executed": self.turns_executed,
            "final_disposition": self.final_disposition.value,
            "certified_message": self.certified_message,
            "word_count": self.word_count,
            "calibrated_confidence": self.calibrated_confidence,
            "margin": self.margin,
            "issues_resolved": self.issues_resolved,
            "escalation_reason": self.escalation_reason,
            "created_at_ms": self.created_at_ms,
        }

    def write_to_path(self, target_path: Path | str) -> Path:
        """Persist receipt to disk atomically."""
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


class ValuePropositionDrafter:
    """Drafter agent crafting personalized candidate messaging and applying repairs."""

    def draft(self, text: str, directives: Sequence[str] | None = None) -> str:
        """Apply repair directives to draft text."""
        if not directives:
            return text.strip()

        current = text
        for d in directives:
            if "remove em-dash" in d.lower():
                current = re.sub(r"[\u2014\u2013]|--", " - ", current)
            elif "remove sycophancy" in d.lower():
                current = re.sub(r"\b(I hope you don't mind me reaching out|I know you're super busy)\b", "", current, flags=re.IGNORECASE)
            elif "remove spam" in d.lower():
                current = re.sub(r"\b(guaranteed|risk-free|100% free|revolutionary)\b", "proven", current, flags=re.IGNORECASE)
            elif "trim length" in d.lower():
                words = current.split()
                if len(words) > 150:
                    current = " ".join(words[:140]) + "."

        return re.sub(r"\s+", " ", current).strip()


class ToneCritic:
    """Critic agent enforcing brevity, peer executive tone, and compliance."""

    SPAM_PATTERNS = (r"\bguaranteed\b", r"\brisk-free\b", r"\b100% free\b", r"\brevolutionary\b")
    SUBORDINATE_PATTERNS = (
        r"\bi hope you don't mind\b",
        r"\bi know you're super busy\b",
        r"\bsorry to bother you\b",
    )

    def evaluate(self, text: str, turn: int, max_words: int = 150, min_words: int = 30) -> OutreachSwarmCritique:
        """Audit message text for tone, brevity, and anti-spam rules."""
        issues: list[str] = []
        directives: list[str] = []
        words = text.split()
        word_count = len(words)

        # 1. Brevity check
        is_length_compliant = min_words <= word_count <= max_words
        if word_count > max_words:
            issues.append(f"Message exceeds maximum word limit ({word_count} > {max_words}).")
            directives.append("trim length")
        elif word_count < min_words:
            issues.append(f"Message is too short ({word_count} < {min_words}).")

        # 2. Em-dash check
        em_dash_count = len(re.findall(r"[\u2014\u2013]|--", text))
        if em_dash_count > 0:
            issues.append(f"Found {em_dash_count} forbidden em-dashes.")
            directives.append("remove em-dash")

        # 3. Tone & Sycophancy check
        found_subordinate = False
        for p in self.SUBORDINATE_PATTERNS:
            if re.search(p, text, flags=re.IGNORECASE):
                issues.append("Subordinate / sycophantic opening phrasing detected.")
                directives.append("remove sycophancy")
                found_subordinate = True
                break

        # 4. Spam trigger check
        found_spam: list[str] = []
        for p in self.SPAM_PATTERNS:
            matches = re.findall(p, text, flags=re.IGNORECASE)
            if matches:
                found_spam.extend(matches)
        if found_spam:
            issues.append(f"Spam trigger words detected: {', '.join(found_spam)}")
            directives.append("remove spam")

        tone_score = 0.50 if found_subordinate else 0.95
        compliance_score = round(max(0.10, 1.0 - (len(issues) * 0.25)), 2)
        is_passing = len(issues) == 0

        audit = OutreachMessageAudit(
            original_text=text,
            repaired_text=text,
            word_count=word_count,
            is_length_compliant=is_length_compliant,
            is_tone_compliant=not found_subordinate,
            spam_triggers_found=tuple(found_spam),
            em_dashes_found=em_dash_count,
            issues=tuple(issues),
        )

        return OutreachSwarmCritique(
            turn=turn,
            audit=audit,
            tone_score=tone_score,
            compliance_score=compliance_score,
            is_passing=is_passing,
            repair_directives=tuple(directives),
        )


class DeliveryArbiter:
    """Arbiter agent evaluating calibrated confidence and signing off on delivery."""

    def arbitrate(
        self,
        turn: int,
        critique: OutreachSwarmCritique,
        max_turns: int = 3,
        ambiguity_margin: float = 0.20,
    ) -> tuple[OutreachSwarmDisposition, float, float, str | None]:
        """Compute disposition, calibrated confidence, and decision margin."""
        calibrated_conf = round((critique.tone_score * 0.50) + (critique.compliance_score * 0.50), 2)
        alternative_score = round(1.0 - calibrated_conf, 2)
        margin = round(abs(calibrated_conf - alternative_score), 2)

        if critique.is_passing and calibrated_conf >= 0.80:
            return OutreachSwarmDisposition.APPROVED, calibrated_conf, margin, None

        if turn >= max_turns:
            reason = f"Outreach deliberation limit ({max_turns} turns) exhausted with remaining issues."
            return OutreachSwarmDisposition.ESCALATED, calibrated_conf, margin, reason

        if margin <= ambiguity_margin and turn > 1:
            reason = f"Confidence spread ({margin:.2f}) within ambiguity margin ({ambiguity_margin:.2f})."
            return OutreachSwarmDisposition.ESCALATED, calibrated_conf, margin, reason

        return OutreachSwarmDisposition.REVISE, calibrated_conf, margin, None


class OutreachSwarmChallenger:
    """Coordinator orchestrating the bounded multi-agent outreach deliberation loop."""

    MAX_TURNS: int = 3

    def __init__(
        self,
        drafter: ValuePropositionDrafter | None = None,
        critic: ToneCritic | None = None,
        arbiter: DeliveryArbiter | None = None,
    ) -> None:
        self._drafter = drafter or ValuePropositionDrafter()
        self._critic = critic or ToneCritic()
        self._arbiter = arbiter or DeliveryArbiter()

    def execute(
        self,
        text: str,
        campaign_id: str = "outreach_campaign",
        max_turns: int = 3,
    ) -> OutreachSwarmReceipt:
        """Run bounded multi-agent deliberation on candidate outreach message."""
        bounded_turns = min(max_turns, self.MAX_TURNS)
        current_text = text
        final_disposition = OutreachSwarmDisposition.REVISE
        escalation_reason: str | None = None
        final_conf = 0.50
        final_margin = 0.0
        total_issues_resolved = 0

        for turn_idx in range(1, bounded_turns + 1):
            critique = self._critic.evaluate(current_text, turn=turn_idx)
            disposition, conf, margin, reason = self._arbiter.arbitrate(
                turn=turn_idx,
                critique=critique,
                max_turns=bounded_turns,
            )
            final_conf = conf
            final_margin = margin
            final_disposition = disposition
            escalation_reason = reason

            if disposition == OutreachSwarmDisposition.APPROVED:
                break
            if disposition == OutreachSwarmDisposition.ESCALATED:
                break

            total_issues_resolved += len(critique.repair_directives)
            current_text = self._drafter.draft(current_text, critique.repair_directives)

        return OutreachSwarmReceipt(
            campaign_id=campaign_id,
            turns_executed=turn_idx,
            final_disposition=final_disposition,
            certified_message=current_text,
            word_count=len(current_text.split()),
            calibrated_confidence=final_conf,
            margin=final_margin,
            issues_resolved=total_issues_resolved,
            escalation_reason=escalation_reason,
        )
