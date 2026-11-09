"""Unit tests for Autonomous Governance Swarm Council.

Part of Monorepo-Wide Swarm Integration (Wave 3).
Verifies multi-member council dispatch, automated finding synthesis,
learning proposal generation, and durable receipt persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from tools.governance_swarm_council import (
    ArchitectureAuditor,
    ConfigSSOTAuditor,
    CouncilFinding,
    CouncilLearningProposal,
    CouncilMember,
    CouncilStatus,
    GovernanceCouncilReceipt,
    GovernanceSwarmCouncil,
    TestCoverageAuditor,
)


def test_governance_swarm_council_convenes_healthy(tmp_path: Path) -> None:
    """Council should convene all specialized members and report healthy status on clean tree."""
    # Create clean mock repo layout
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "provider_profiles.yaml").write_text("profiles: {}\n", encoding="utf-8")

    pytest_file = tmp_path / "pytest.ini"
    pytest_file.write_text("[pytest]\naddopts = --timeout=60\n", encoding="utf-8")

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "service.py").write_text("# Clean small module\n", encoding="utf-8")

    council = GovernanceSwarmCouncil()
    receipt = council.convene(repo_root=tmp_path, council_id="test_healthy_session")

    assert receipt.council_id == "test_healthy_session"
    assert receipt.status == CouncilStatus.HEALTHY
    assert len(receipt.members_reporting) == 4
    assert CouncilMember.ARCHITECTURE_AUDITOR.value in receipt.members_reporting
    assert CouncilMember.CONFIG_SSOT_AUDITOR.value in receipt.members_reporting
    assert CouncilMember.TEST_COVERAGE_AUDITOR.value in receipt.members_reporting
    assert CouncilMember.COUNCIL_SYNTHESIZER.value in receipt.members_reporting
    assert receipt.calibrated_confidence >= 0.85
    assert len(receipt.findings) == 0
    assert len(receipt.learning_proposals) == 0


def test_governance_swarm_council_detects_violations_and_generates_proposals(tmp_path: Path) -> None:
    """Council must detect configuration and test gaps and synthesize actionable proposals."""
    # Missing provider_profiles.yaml and pytest.ini missing --timeout
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    pytest_file = tmp_path / "pytest.ini"
    pytest_file.write_text("[pytest]\naddopts = -v\n", encoding="utf-8")

    council = GovernanceSwarmCouncil()
    receipt = council.convene(repo_root=tmp_path, council_id="test_violations_session")

    assert receipt.status == CouncilStatus.VIOLATIONS_FOUND
    assert len(receipt.findings) >= 2
    assert len(receipt.learning_proposals) >= 2

    # Check that learning proposals have calibrated confidence
    for proposal in receipt.learning_proposals:
        assert isinstance(proposal.proposal_id, str)
        assert proposal.calibrated_confidence >= 0.70
        assert proposal.suggested_addition != ""


def test_governance_swarm_council_receipt_serialization(tmp_path: Path) -> None:
    """Council receipt must serialize cleanly to disk with all provenance fields."""
    receipt = GovernanceCouncilReceipt(
        council_id="test_receipt_session",
        status=CouncilStatus.HEALTHY,
        members_reporting=(
            CouncilMember.ARCHITECTURE_AUDITOR.value,
            CouncilMember.COUNCIL_SYNTHESIZER.value,
        ),
        total_checks_evaluated=20,
        findings=(),
        learning_proposals=(),
        calibrated_confidence=0.95,
        margin=0.90,
    )

    receipt_dict = receipt.to_dict()
    assert receipt_dict["council_id"] == "test_receipt_session"
    assert receipt_dict["status"] == "HEALTHY"

    target_file = tmp_path / "wave3_council_receipt_test.json"
    written_path = receipt.write_to_path(target_file)
    assert written_path.is_file()

    loaded = json.loads(written_path.read_text(encoding="utf-8"))
    assert loaded["council_id"] == "test_receipt_session"
    assert loaded["status"] == "HEALTHY"
