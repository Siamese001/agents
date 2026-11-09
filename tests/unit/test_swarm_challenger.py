"""Unit tests for Multi-Agent Swarm Challenger Service and Executive Summary Repair Integration.

Verifies bounded 3-turn Socratic convergence, calibrated confidence calculations,
critic anti-hallucination verification, and receipt durability.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from agents.orchestration.services.swarm_challenger import (
    ArbiterAgent,
    ChallengerCritique,
    CriticAgent,
    ProponentAgent,
    SwarmChallenger,
    SwarmDisposition,
    SwarmExecutionReceipt,
    SwarmRole,
)
from agents.orchestration.services.executive_summary_repair import (
    ExecutiveSummaryRepairService,
)


def test_swarm_challenger_approves_clean_text() -> None:
    """Clean text adhering to voice and facts should approve on Turn 1."""
    challenger = SwarmChallenger()
    clean_text = "Accomplished engineering executive with proven track record leading global teams."
    receipt = challenger.execute(
        text=clean_text,
        workflow_id="test_clean_approval",
    )

    assert receipt.final_disposition == SwarmDisposition.APPROVED
    assert receipt.turns_executed == 1
    assert receipt.calibrated_confidence >= 0.85
    assert receipt.unverified_claims_detected == 0
    assert len(receipt.turns) == 1
    assert receipt.turns[0].critique.is_passing is True


def test_swarm_challenger_repairs_and_converges_within_three_turns() -> None:
    """Text with voice violations should be repaired by Proponent and approved within 3 turns."""
    challenger = SwarmChallenger()
    messy_text = "I am an enterprise architect and was responsible for large system migrations."
    receipt = challenger.execute(
        text=messy_text,
        workflow_id="test_repair_convergence",
        max_turns=3,
    )

    assert receipt.final_disposition == SwarmDisposition.APPROVED
    assert 1 < receipt.turns_executed <= 3
    assert "I am" not in receipt.final_text
    assert "was responsible for" not in receipt.final_text
    assert receipt.calibrated_confidence >= 0.80


def test_swarm_challenger_detects_uncorroborated_metrics() -> None:
    """Critic must detect metrics not present in canonical assertions and report unverified claims."""
    challenger = SwarmChallenger()
    unverified_text = "Directed transformation delivering 45% revenue growth across business units."
    canonical_facts = (
        "Led modernization of cloud data platform across 12 distributed regions.",
        "Reduced infrastructure spend by 22% annual run rate.",
    )

    receipt = challenger.execute(
        text=unverified_text,
        workflow_id="test_uncorroborated_metric",
        canonical_assertions=canonical_facts,
    )

    assert receipt.unverified_claims_detected >= 1
    # Check that the unverified claim was flagged during critique
    critique_issues = [issue for t in receipt.turns for issue in t.critique.issues]
    assert any("Uncorroborated metric claim detected" in issue for issue in critique_issues)


def test_swarm_challenger_escalates_when_issues_persist_beyond_max_turns() -> None:
    """When issues cannot be resolved within 3 turns, arbiter must escalate with reasons."""
    # Critic that always flags a stubborn domain error with low score (margin > 20%)
    class StubbornCritic(CriticAgent):
        def evaluate(self, text: str, turn: int, canonical_assertions=None, disallowed_patterns=None):
            return ChallengerCritique(
                turn=turn,
                critic_score=0.15,
                issues=("Persistent compliance violation",),
                repair_directives=("attempt manual fix",),
                is_passing=False,
            )

    challenger = SwarmChallenger(critic=StubbornCritic())
    receipt = challenger.execute(
        text="Sample text requiring compliance signoff.",
        workflow_id="test_escalation_budget",
        max_turns=3,
    )

    assert receipt.final_disposition == SwarmDisposition.ESCALATED
    assert receipt.turns_executed == 3
    assert receipt.escalation_reason is not None
    assert "exhausted" in receipt.escalation_reason.lower()


def test_swarm_challenger_escalates_on_ambiguity_margin() -> None:
    """When confidence spread is within the 20% margin threshold, arbiter must escalate immediately."""
    class AmbiguousCritic(CriticAgent):
        def evaluate(self, text: str, turn: int, canonical_assertions=None, disallowed_patterns=None):
            return ChallengerCritique(
                turn=turn,
                critic_score=0.45,  # conf 0.45 vs 0.55 -> margin 0.10 <= 0.20
                issues=("Borderline ambiguity detected",),
                repair_directives=("clarify statement",),
                is_passing=False,
            )

    challenger = SwarmChallenger(critic=AmbiguousCritic())
    receipt = challenger.execute(
        text="Borderline ambiguous statement.",
        workflow_id="test_ambiguity_margin",
        max_turns=3,
    )

    assert receipt.final_disposition == SwarmDisposition.ESCALATED
    assert receipt.turns_executed == 2  # Escalates early on turn 2 due to margin <= 20%
    assert receipt.escalation_reason is not None
    assert "ambiguity margin" in receipt.escalation_reason.lower()


def test_swarm_challenger_receipt_serialization(tmp_path: Path) -> None:
    """Swarm receipt should serialize cleanly to dictionary and disk."""
    challenger = SwarmChallenger()
    receipt = challenger.execute(
        text="Accomplished technology leader with experience delivering scalable platforms.",
        workflow_id="receipt_test",
    )

    receipt_dict = receipt.to_dict()
    assert receipt_dict["workflow_id"] == "receipt_test"
    assert receipt_dict["final_disposition"] == "APPROVED"
    assert "turns" in receipt_dict
    assert isinstance(receipt_dict["created_at_ms"], int)

    target_file = tmp_path / "test_receipt.json"
    written_path = receipt.write_to_path(target_file)
    assert written_path.is_file()

    loaded = json.loads(written_path.read_text(encoding="utf-8"))
    assert loaded["workflow_id"] == "receipt_test"
    assert loaded["final_disposition"] == "APPROVED"


def test_executive_summary_repair_service_integration() -> None:
    """ExecutiveSummaryRepairService must seamlessly execute challenger verification when requested."""
    repair_service = ExecutiveSummaryRepairService()
    input_text = "I am a principal architect who was responsible for platform security."
    
    # Run with challenger enabled
    result = repair_service.repair(
        text=input_text,
        enable_challenger=True,
    )

    assert result.is_successful is True
    assert result.was_modified is True
    assert result.swarm_receipt is not None
    assert result.swarm_receipt.final_disposition == SwarmDisposition.APPROVED
    assert "I am" not in result.repaired_text
