"""Unit tests for Resume Engine Runtime Swarm Challenger.

Part of Monorepo-Wide Swarm Integration (Wave 1).
Verifies qualification matching, factual graph cross-examination,
executive voice scoring, 3-turn bounds, and receipt serialization.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from apps_rg.runtime.resume_swarm_challenger import (
    BulletAudit,
    FactualCritic,
    QualificationMatcher,
    ResumeSwarmChallenger,
    ResumeSwarmCritique,
    ResumeSwarmDisposition,
    ResumeSwarmReceipt,
    VoiceArbiter,
    verify_with_swarm,
)


def test_resume_swarm_approves_grounded_bullets() -> None:
    """Clean bullets matching canonical facts should approve on Turn 1."""
    challenger = ResumeSwarmChallenger()
    bullets = (
        "Architected distributed data platform processing multi-terabyte analytical workloads.",
        "Spearheaded cloud governance framework reducing operational infrastructure spend by 25%.",
    )
    canonical_facts = (
        "Spearheaded cloud governance framework reducing operational infrastructure spend by 25%.",
        "Built high-throughput distributed data platform.",
    )

    receipt = challenger.execute(
        bullets=bullets,
        run_id="test_grounded_approval",
        canonical_assertions=canonical_facts,
    )

    assert receipt.final_disposition == ResumeSwarmDisposition.APPROVED
    assert receipt.turns_executed == 1
    assert receipt.factual_score == 1.0
    assert receipt.voice_score >= 0.80
    assert receipt.calibrated_confidence >= 0.80
    assert receipt.uncorroborated_claims_detected == 0


def test_resume_swarm_repairs_first_person_and_unverified_metrics() -> None:
    """Bullets with first person or uncorroborated metrics should be flagged and repaired."""
    challenger = ResumeSwarmChallenger()
    messy_bullets = (
        "I led engineering operations and delivered 85% revenue growth across business lines.",
    )
    canonical_facts = (
        "Led engineering operations across enterprise business units.",
    )

    receipt = challenger.execute(
        bullets=messy_bullets,
        run_id="test_metric_and_voice_repair",
        canonical_assertions=canonical_facts,
    )

    assert receipt.uncorroborated_claims_detected >= 1
    assert "I led" not in receipt.certified_bullets[0]
    assert "85% revenue growth" not in receipt.certified_bullets[0]
    assert "measurable growth" in receipt.certified_bullets[0]


def test_resume_swarm_escalates_on_stubborn_unverified_claims() -> None:
    """Stubborn issues persisting across 3 turns must trigger escalation."""
    class StrictCritic(FactualCritic):
        def evaluate_bullet(self, bullet: str, canonical_assertions=None):
            return BulletAudit(
                original=bullet,
                repaired=bullet,
                is_verified=False,
                uncorroborated_claims=("Fictitious achievement",),
                issues=("Persistent hallucination",),
            )

    challenger = ResumeSwarmChallenger(critic=StrictCritic())
    receipt = challenger.execute(
        bullets=("Fabricated executive achievement.",),
        run_id="test_escalation",
        max_turns=3,
    )

    assert receipt.final_disposition == ResumeSwarmDisposition.ESCALATED
    assert receipt.turns_executed == 3
    assert receipt.escalation_reason is not None
    assert "exhausted" in receipt.escalation_reason.lower()


def test_resume_swarm_receipt_serialization(tmp_path: Path) -> None:
    """Resume swarm receipt must serialize cleanly to disk with all provenance fields."""
    challenger = ResumeSwarmChallenger()
    receipt = challenger.execute(
        bullets=("Orchestrated enterprise cloud transformation.",),
        run_id="serialization_test",
    )

    receipt_dict = receipt.to_dict()
    assert receipt_dict["run_id"] == "serialization_test"
    assert "certified_bullets" in receipt_dict
    assert isinstance(receipt_dict["created_at_ms"], int)

    target_file = tmp_path / "resume_receipt.json"
    written_path = receipt.write_to_path(target_file)
    assert written_path.is_file()

    loaded = json.loads(written_path.read_text(encoding="utf-8"))
    assert loaded["run_id"] == "serialization_test"


def test_final_resume_outputs_verify_with_swarm_integration() -> None:
    """verify_with_swarm helper must integrate cleanly with final resume outputs."""
    bullets = ["Architected enterprise platform with high availability."]
    receipt = verify_with_swarm(
        bullets=bullets,
        run_id="integration_test",
    )

    assert receipt.run_id == "integration_test"
    assert receipt.final_disposition == ResumeSwarmDisposition.APPROVED
    assert len(receipt.certified_bullets) == 1
