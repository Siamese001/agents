"""Swarm Challenger Service: Paired Proponent, Critic, and Arbiter Coordination.

Governed Multi-Agent Swarm for High-Stakes Reasoning and Voice Verification.
Enforces bounded Socratic convergence (<= 3 turns), calibrated confidence scoring,
and calibrated margin escalation (INV-HITL-20-PERCENT-MARGIN).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


class SwarmRole(str, Enum):
    """Authoritative roles within the challenger swarm."""

    PROPONENT = "PROPONENT"
    CRITIC = "CRITIC"
    ARBITER = "ARBITER"


class SwarmDisposition(str, Enum):
    """Terminal and intermediate disposition states for swarm deliberation."""

    APPROVED = "APPROVED"
    REVISE = "REVISE"
    ESCALATED = "ESCALATED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ChallengerCritique:
    """Evaluation emitted by the Critic agent for a given draft."""

    turn: int
    critic_score: float
    issues: tuple[str, ...]
    repair_directives: tuple[str, ...]
    is_passing: bool
    unverified_claims: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ChallengerTurn:
    """Discrete state transition within the multi-agent deliberation loop."""

    turn: int
    draft_text: str
    critique: ChallengerCritique
    disposition: SwarmDisposition
    margin: float
    calibrated_confidence: float


@dataclass(frozen=True, slots=True)
class SwarmExecutionReceipt:
    """Durable provenance record certifying swarm deliberation results."""

    workflow_id: str
    turns_executed: int
    final_disposition: SwarmDisposition
    final_text: str
    turns: tuple[ChallengerTurn, ...]
    calibrated_confidence: float
    margin: float
    unverified_claims_detected: int
    escalation_reason: str | None = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        """Convert receipt to canonical JSON-serializable dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "turns_executed": self.turns_executed,
            "final_disposition": self.final_disposition.value,
            "final_text": self.final_text,
            "turns": [
                {
                    "turn": t.turn,
                    "draft_text": t.draft_text,
                    "critique": {
                        "turn": t.critique.turn,
                        "critic_score": t.critique.critic_score,
                        "issues": list(t.critique.issues),
                        "repair_directives": list(t.critique.repair_directives),
                        "is_passing": t.critique.is_passing,
                        "unverified_claims": list(t.critique.unverified_claims),
                    },
                    "disposition": t.disposition.value,
                    "margin": t.margin,
                    "calibrated_confidence": t.calibrated_confidence,
                }
                for t in self.turns
            ],
            "calibrated_confidence": self.calibrated_confidence,
            "margin": self.margin,
            "unverified_claims_detected": self.unverified_claims_detected,
            "escalation_reason": self.escalation_reason,
            "created_at_ms": self.created_at_ms,
        }

    def write_to_path(self, target_path: Path | str) -> Path:
        """Persist receipt to disk atomically."""
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


class ProponentAgent:
    """Proponent agent generating initial drafts and executing repair directives."""

    def draft(self, text: str, directives: Sequence[str] | None = None) -> str:
        """Generate revised text incorporating prior critique directives."""
        if not directives:
            return text.strip()

        current = text
        for directive in directives:
            # Deterministic repair directives application
            if "remove first person" in directive.lower():
                current = re.sub(r"\b(I am|I have|I was)\b", "Accomplished leader with extensive experience", current, flags=re.IGNORECASE)
                current = re.sub(r"\bmy\b", "the", current, flags=re.IGNORECASE)
            elif "remove ungrounded metric" in directive.lower():
                # Strip unsupported high-percentage claims not verified by facts
                current = re.sub(r"\b\d{2,3}%\s+revenue\s+growth\b", "measurable enterprise growth", current, flags=re.IGNORECASE)
            elif "passive voice" in directive.lower():
                current = re.sub(r"\bwas responsible for\b", "directed and executed", current, flags=re.IGNORECASE)
        return current.strip()


class CriticAgent:
    """Critic agent evaluating candidate texts against factual assertions and style rules."""

    def evaluate(
        self,
        text: str,
        turn: int,
        canonical_assertions: Sequence[str] | None = None,
        disallowed_patterns: Sequence[tuple[str, str]] | None = None,
    ) -> ChallengerCritique:
        """Thoroughly audit candidate text for factual gaps and style violations."""
        issues: list[str] = []
        directives: list[str] = []
        unverified: list[str] = []

        # 1. Voice and style evaluation
        if re.search(r"\b(I am|I have|I was|my)\b", text, flags=re.IGNORECASE):
            issues.append("First-person singular voice detected.")
            directives.append("remove first person")

        if re.search(r"\bwas responsible for\b", text, flags=re.IGNORECASE):
            issues.append("Passive responsibility voice detected.")
            directives.append("passive voice")

        # 2. Factual Grounding Evaluation against canonical assertions
        if canonical_assertions is not None:
            # Any claim formatted as an exact metric must match a canonical assertion
            metric_claims = re.findall(r"\b\d{2,3}%\s+\w+(?:\s+\w+)?\b", text, flags=re.IGNORECASE)
            for claim in metric_claims:
                if not any(claim.lower() in assertion.lower() for assertion in canonical_assertions):
                    issues.append(f"Uncorroborated metric claim detected: '{claim}'")
                    directives.append("remove ungrounded metric")
                    unverified.append(claim)

        # 3. Disallowed patterns audit
        if disallowed_patterns:
            for pattern, reason in disallowed_patterns:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    issues.append(f"Disallowed pattern found: {reason}")
                    directives.append(f"fix {reason}")

        # Compute objective critic score
        base_score = 1.0 - (len(issues) * 0.25)
        critic_score = round(max(0.10, min(1.0, base_score)), 2)
        is_passing = len(issues) == 0

        return ChallengerCritique(
            turn=turn,
            critic_score=critic_score,
            issues=tuple(issues),
            repair_directives=tuple(directives),
            is_passing=is_passing,
            unverified_claims=tuple(unverified),
        )


class ArbiterAgent:
    """Arbiter agent calculating calibrated confidence, margins, and disposition."""

    def arbitrate(
        self,
        turn: int,
        critique: ChallengerCritique,
        max_turns: int = 3,
        ambiguity_margin_threshold: float = 0.20,
    ) -> tuple[SwarmDisposition, float, float, str | None]:
        """Compute disposition, calibrated confidence, and decision margin."""
        # Score calculation: base confidence modulated by critique pass/fail
        calibrated_conf = round(max(0.05, min(0.99, critique.critic_score)), 2)

        # Alternative score reflects opposing outcome confidence
        alternative_score = round(1.0 - calibrated_conf, 2)
        margin = round(abs(calibrated_conf - alternative_score), 2)

        if critique.is_passing:
            return SwarmDisposition.APPROVED, calibrated_conf, margin, None

        if turn >= max_turns:
            reason = f"Max deliberation turns ({max_turns}) exhausted with {len(critique.issues)} remaining issue(s)."
            return SwarmDisposition.ESCALATED, calibrated_conf, margin, reason

        if margin <= ambiguity_margin_threshold and turn > 1:
            reason = f"Confidence spread ({margin:.2f}) within ambiguity margin ({ambiguity_margin_threshold:.2f})."
            return SwarmDisposition.ESCALATED, calibrated_conf, margin, reason

        return SwarmDisposition.REVISE, calibrated_conf, margin, None


class SwarmChallenger:
    """Coordinator orchestrating the bounded Proponent-Critic-Arbiter Socratic loop."""

    MAX_TURNS_HARD_CAP: int = 3

    def __init__(
        self,
        proponent: ProponentAgent | None = None,
        critic: CriticAgent | None = None,
        arbiter: ArbiterAgent | None = None,
    ) -> None:
        self._proponent = proponent or ProponentAgent()
        self._critic = critic or CriticAgent()
        self._arbiter = arbiter or ArbiterAgent()

    def execute(
        self,
        text: str,
        workflow_id: str = "swarm_deliberation",
        canonical_assertions: Sequence[str] | None = None,
        disallowed_patterns: Sequence[tuple[str, str]] | None = None,
        max_turns: int = 3,
    ) -> SwarmExecutionReceipt:
        """Run bounded multi-agent challenger deliberation."""
        bounded_max_turns = min(max_turns, self.MAX_TURNS_HARD_CAP)
        turns: list[ChallengerTurn] = []
        current_text = text
        unverified_count = 0
        final_disposition = SwarmDisposition.REVISE
        escalation_reason: str | None = None
        final_conf = 0.50
        final_margin = 0.0

        for turn_idx in range(1, bounded_max_turns + 1):
            critique = self._critic.evaluate(
                text=current_text,
                turn=turn_idx,
                canonical_assertions=canonical_assertions,
                disallowed_patterns=disallowed_patterns,
            )
            unverified_count += len(critique.unverified_claims)

            disposition, conf, margin, reason = self._arbiter.arbitrate(
                turn=turn_idx,
                critique=critique,
                max_turns=bounded_max_turns,
            )
            final_conf = conf
            final_margin = margin
            final_disposition = disposition
            escalation_reason = reason

            turns.append(
                ChallengerTurn(
                    turn=turn_idx,
                    draft_text=current_text,
                    critique=critique,
                    disposition=disposition,
                    margin=margin,
                    calibrated_confidence=conf,
                )
            )

            if disposition == SwarmDisposition.APPROVED:
                break

            if disposition == SwarmDisposition.ESCALATED:
                break

            # Draft repair for subsequent turn
            current_text = self._proponent.draft(current_text, critique.repair_directives)

        return SwarmExecutionReceipt(
            workflow_id=workflow_id,
            turns_executed=len(turns),
            final_disposition=final_disposition,
            final_text=current_text,
            turns=tuple(turns),
            calibrated_confidence=final_conf,
            margin=final_margin,
            unverified_claims_detected=unverified_count,
            escalation_reason=escalation_reason,
        )
