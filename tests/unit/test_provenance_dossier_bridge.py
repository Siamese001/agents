"""Unit tests for Cross-Engine Provenance Dossier Bridge (Wave 3).

Tests end-to-end integration between ResumeSwarmChallenger, ProvenanceDossierBridge,
and OutreachSwarmCoordinator, verifying fail-closed gating on unverified claims and cryptographic integrity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from apps_rg.runtime.resume_swarm_challenger import (
    ResumeSwarmDisposition,
    ResumeSwarmReceipt,
)
from apps_lic.pipeline.coordinator import OutreachSwarmCoordinator
from infrastructure.runtime.provenance_dossier_bridge import (
    CrossEngineDossierReceipt,
    DossierDisposition,
    ProvenanceDossierBridge,
    compute_dossier_digest,
    verify_dossier_integrity,
)


@pytest.fixture
def sample_approved_resume_receipt() -> ResumeSwarmReceipt:
    """Fixture providing an approved ResumeSwarmReceipt."""
    return ResumeSwarmReceipt(
        run_id="run_test_resume_001",
        turns_executed=2,
        final_disposition=ResumeSwarmDisposition.APPROVED,
        certified_bullets=(
            "Architected distributed real-time data streaming pipeline achieving 40% latency reduction.",
            "Spearheaded cloud migration across 14 services maintaining 99.99% system availability.",
            "Led cross-functional engineering team of 18 delivering flagship enterprise platform.",
        ),
        uncorroborated_claims_detected=0,
        factual_score=0.95,
        voice_score=0.92,
        calibrated_confidence=0.94,
        margin=0.25,
    )


@pytest.fixture
def sample_rejected_resume_receipt() -> ResumeSwarmReceipt:
    """Fixture providing a rejected ResumeSwarmReceipt."""
    return ResumeSwarmReceipt(
        run_id="run_test_resume_rej_002",
        turns_executed=3,
        final_disposition=ResumeSwarmDisposition.REJECTED,
        certified_bullets=(),
        uncorroborated_claims_detected=4,
        factual_score=0.35,
        voice_score=0.50,
        calibrated_confidence=0.40,
        margin=0.10,
        escalation_reason="Multiple uncorroborated metric inflations detected.",
    )


def test_end_to_end_cross_engine_dossier_bridge(sample_approved_resume_receipt: ResumeSwarmReceipt) -> None:
    """Verify clean handoff from approved resume receipt to outreach message."""
    bridge = ProvenanceDossierBridge()
    receipt = bridge.bridge_and_dispatch(
        resume_receipt=sample_approved_resume_receipt,
        campaign_id="camp_fintech_lead_01",
        recipient_name="Sarah",
        role_title="Head of Platform Engineering",
        company_name="Apex Financial",
    )

    assert receipt.outreach_deliverable is True
    assert receipt.disposition == DossierDisposition.DELIVERABLE
    assert receipt.campaign_id == "camp_fintech_lead_01"
    assert receipt.recipient_name == "Sarah"
    assert len(receipt.certified_claims) > 0
    assert len(receipt.rejected_claims) == 0
    assert "Sarah" in receipt.certified_outreach_message
    assert receipt.outreach_word_count <= 80
    assert len(receipt.provenance_digest) == 64
    assert verify_dossier_integrity(receipt) is True


def test_dossier_bridge_rejects_unverified_claims(sample_approved_resume_receipt: ResumeSwarmReceipt) -> None:
    """Verify that uncorroborated claims are filtered and rejected before outreach generation."""
    bridge = ProvenanceDossierBridge()

    candidate_claims = [
        "Architected distributed real-time data streaming pipeline achieving 40% latency reduction.",
        "Personally invented quantum computing algorithms for cryptographic breakthroughs in 2026.",
    ]

    receipt = bridge.bridge_and_dispatch(
        resume_receipt=sample_approved_resume_receipt,
        campaign_id="camp_cloud_infra_02",
        recipient_name="David",
        candidate_claims=candidate_claims,
    )

    assert receipt.outreach_deliverable is True
    assert len(receipt.certified_claims) == 1
    assert "latency reduction" in receipt.certified_claims[0]
    assert len(receipt.rejected_claims) == 1
    assert "quantum" in receipt.rejected_claims[0]
    assert "quantum" not in receipt.certified_outreach_message.lower()
    assert verify_dossier_integrity(receipt) is True


def test_dossier_bridge_fails_closed_on_unapproved_resume(sample_rejected_resume_receipt: ResumeSwarmReceipt) -> None:
    """Verify that unapproved or escalated resume results fail closed with zero outreach copy."""
    bridge = ProvenanceDossierBridge()
    receipt = bridge.bridge_and_dispatch(
        resume_receipt=sample_rejected_resume_receipt,
        campaign_id="camp_blocked_03",
        recipient_name="Alex",
    )

    assert receipt.outreach_deliverable is False
    assert receipt.disposition == DossierDisposition.REJECTED_RESUME_DISPOSITION
    assert receipt.certified_outreach_message == ""
    assert receipt.outreach_word_count == 0
    assert verify_dossier_integrity(receipt) is True


def test_dossier_bridge_fails_closed_when_all_claims_rejected(
    sample_approved_resume_receipt: ResumeSwarmReceipt,
) -> None:
    """Verify that if all candidate claims are hallucinated or unverified, the bridge fails closed."""
    bridge = ProvenanceDossierBridge()
    hallucinated_claims = [
        "Won three Olympic gold medals in downhill skiing.",
        "Discovered faster-than-light warp propulsion drive.",
    ]

    receipt = bridge.bridge_and_dispatch(
        resume_receipt=sample_approved_resume_receipt,
        campaign_id="camp_hallucinated_04",
        recipient_name="Jordan",
        candidate_claims=hallucinated_claims,
    )

    assert receipt.outreach_deliverable is False
    assert receipt.disposition == DossierDisposition.NO_CERTIFIED_CLAIMS
    assert receipt.certified_outreach_message == ""
    assert len(receipt.rejected_claims) == 2
    assert verify_dossier_integrity(receipt) is True


def test_dossier_receipt_serialization_and_persistence(
    sample_approved_resume_receipt: ResumeSwarmReceipt,
    tmp_path: Path,
) -> None:
    """Verify JSON serialization and atomic file persistence of CrossEngineDossierReceipt."""
    bridge = ProvenanceDossierBridge()
    receipt = bridge.bridge_and_dispatch(
        resume_receipt=sample_approved_resume_receipt,
        campaign_id="camp_persist_05",
        recipient_name="Elena",
    )

    data = receipt.to_dict()
    assert data["dossier_id"] == receipt.dossier_id
    assert data["campaign_id"] == "camp_persist_05"
    assert data["outreach_deliverable"] is True
    assert data["disposition"] == DossierDisposition.DELIVERABLE.value

    out_file = tmp_path / "cross_engine_dossier.json"
    written_path = receipt.write_to_path(out_file)
    assert written_path.exists()

    loaded = json.loads(written_path.read_text(encoding="utf-8"))
    assert loaded["dossier_id"] == receipt.dossier_id
    assert loaded["provenance_digest"] == receipt.provenance_digest


def test_tampered_digest_fails_integrity_check(sample_approved_resume_receipt: ResumeSwarmReceipt) -> None:
    """Verify that tampering with any field invalidates cryptographic integrity verification."""
    bridge = ProvenanceDossierBridge()
    receipt = bridge.bridge_and_dispatch(
        resume_receipt=sample_approved_resume_receipt,
        campaign_id="camp_tamper_06",
        recipient_name="Marcus",
    )

    assert verify_dossier_integrity(receipt) is True

    # Tampered message
    tampered_msg_receipt = CrossEngineDossierReceipt(
        dossier_id=receipt.dossier_id,
        resume_run_id=receipt.resume_run_id,
        campaign_id=receipt.campaign_id,
        recipient_name=receipt.recipient_name,
        certified_claims=receipt.certified_claims,
        rejected_claims=receipt.rejected_claims,
        outreach_deliverable=receipt.outreach_deliverable,
        certified_outreach_message="Tampered message with unauthorized content.",
        outreach_word_count=receipt.outreach_word_count,
        provenance_digest=receipt.provenance_digest,
        disposition=receipt.disposition,
    )
    assert verify_dossier_integrity(tampered_msg_receipt) is False
