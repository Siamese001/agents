"""Unit tests for Outreach Engine Runtime Swarm Challenger.

Part of Monorepo-Wide Swarm Integration (Wave 2).
Verifies value proposition drafting, tone and brevity screening,
em-dash and anti-spam detection, 3-turn bounds, and receipt durability.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from apps_lic.runtime.outreach_swarm_challenger import (
    DeliveryArbiter,
    OutreachMessageAudit,
    OutreachSwarmChallenger,
    OutreachSwarmCritique,
    OutreachSwarmDisposition,
    OutreachSwarmReceipt,
    ToneCritic,
    ValuePropositionDrafter,
)
from apps_lic.pipeline.coordinator import (
    CertifiedOutreachPackage,
    OutreachSwarmCoordinator,
)


def test_outreach_swarm_approves_clean_message() -> None:
    """Clean, concise executive message should approve on Turn 1."""
    challenger = OutreachSwarmChallenger()
    clean_text = (
        "Hi Alex, reaching out regarding the Principal Systems Architect opportunity. "
        "With a background architecting distributed cloud systems and leading high-throughput data platforms, "
        "I believe my background aligns strongly with your current expansion. "
        "Would welcome thirty minutes next week to discuss mutual alignment and technical goals."
    )

    receipt = challenger.execute(
        text=clean_text,
        campaign_id="test_clean_outreach",
    )

    assert receipt.final_disposition == OutreachSwarmDisposition.APPROVED
    assert receipt.turns_executed == 1
    assert receipt.calibrated_confidence >= 0.85
    assert 30 <= receipt.word_count <= 150


def test_outreach_swarm_repairs_em_dashes_and_sycophancy() -> None:
    """Messages with sycophancy and em-dashes should be repaired and approved within 3 turns."""
    challenger = OutreachSwarmChallenger()
    messy_text = (
        "Hi Jordan, I hope you don't mind me reaching out—I saw the platform opening. "
        "Over the past decade—leading large cloud initiatives—I delivered high availability platforms. "
        "Would appreciate thirty minutes to share thoughts on your data roadmap."
    )

    receipt = challenger.execute(
        text=messy_text,
        campaign_id="test_repair_sycophancy",
        max_turns=3,
    )

    assert receipt.final_disposition == OutreachSwarmDisposition.APPROVED
    assert "\u2014" not in receipt.certified_message
    assert "I hope you don't mind" not in receipt.certified_message
    assert receipt.issues_resolved >= 1


def test_outreach_swarm_escalates_on_stubborn_issues() -> None:
    """Stubborn issues persisting beyond 3 turns must trigger escalation."""
    class StrictCritic(ToneCritic):
        def evaluate(self, text: str, turn: int, max_words=150, min_words=30):
            audit = OutreachMessageAudit(
                original_text=text,
                repaired_text=text,
                word_count=len(text.split()),
                is_length_compliant=False,
                is_tone_compliant=False,
                spam_triggers_found=(),
                em_dashes_found=0,
                issues=("Persistent regulatory restriction",),
            )
            return OutreachSwarmCritique(
                turn=turn,
                audit=audit,
                tone_score=0.40,
                compliance_score=0.30,
                is_passing=False,
                repair_directives=("attempt manual override",),
            )

    challenger = OutreachSwarmChallenger(critic=StrictCritic())
    receipt = challenger.execute(
        text="Sample candidate outreach message for review.",
        campaign_id="test_escalation",
        max_turns=3,
    )

    assert receipt.final_disposition == OutreachSwarmDisposition.ESCALATED
    assert receipt.turns_executed == 3
    assert receipt.escalation_reason is not None
    assert "exhausted" in receipt.escalation_reason.lower()


def test_outreach_swarm_receipt_serialization(tmp_path: Path) -> None:
    """Outreach swarm receipt must serialize cleanly to disk with all provenance fields."""
    challenger = OutreachSwarmChallenger()
    receipt = challenger.execute(
        text="Hi Taylor, reaching out regarding the engineering leadership role. Would welcome thirty minutes to connect.",
        campaign_id="outreach_serialization_test",
    )

    receipt_dict = receipt.to_dict()
    assert receipt_dict["campaign_id"] == "outreach_serialization_test"
    assert "certified_message" in receipt_dict
    assert isinstance(receipt_dict["created_at_ms"], int)

    target_file = tmp_path / "outreach_receipt.json"
    written_path = receipt.write_to_path(target_file)
    assert written_path.is_file()

    loaded = json.loads(written_path.read_text(encoding="utf-8"))
    assert loaded["campaign_id"] == "outreach_serialization_test"


def test_outreach_swarm_coordinator_end_to_end() -> None:
    """OutreachSwarmCoordinator must assemble, deliberate, and produce certified packages."""
    coordinator = OutreachSwarmCoordinator()
    value_props = (
        "Architected distributed cloud platforms across multi-region deployments.",
        "Led engineering organizations delivering high-availability infrastructure.",
    )

    package = coordinator.compile_and_certify(
        campaign_id="exec_hiring_outreach",
        recipient_name="Morgan",
        value_props=value_props,
        role_title="Head of Cloud Infrastructure",
        company_name="Acme Corp",
    )

    assert package.campaign_id == "exec_hiring_outreach"
    assert package.recipient_name == "Morgan"
    assert package.is_deliverable is True
    assert "Head of Cloud Infrastructure" in package.certified_body
    assert package.receipt.final_disposition == OutreachSwarmDisposition.APPROVED
