"""Tests for managed research delegation, cryptographic validation, and test doubles."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from apps_lic.integrations.apps_research_bridge import (
    AppsResearchBridge,
    EvidenceItem,
    MockAppsResearchBridge,
    _resolve_canonical_targeting_brief,
)
from apps_lic.integrations.managed_research_delegation import (
    OutreachBriefingReady,
    RequestForOutreachBriefing,
    ResearchDispatchFailure,
    ResearchFailureReason,
    _validate_persisted_research_artifacts,
    dispatch_outreach_research_briefing,
)


def test_delegation_happy_path_with_persisted_artifacts(tmp_path: Path):
    producer_runs = tmp_path / "producer_runs"
    consumer_dir = tmp_path / "outreach_run_01"

    bridge = MockAppsResearchBridge(
        artifact_runs_root=producer_runs,
        confidence_score=0.92,
        strategic_priorities=(
            "Platform consolidation across business units",
            "Frontline agent assist with human-in-the-loop oversight",
        ),
    )

    req = RequestForOutreachBriefing(
        request_id="req-test-1",
        run_id="run-test-1",
        trace_id="trace-test-1",
        company_name="Truist",
        job_title="Head of AI Enablement",
        artifact_runs_root=producer_runs,
    )

    outcome = dispatch_outreach_research_briefing(
        req,
        bridge=bridge,
        consumer_artifact_dir=consumer_dir,
    )

    assert isinstance(outcome, OutreachBriefingReady)
    assert outcome.confidence_score == 0.92
    assert len(outcome.strategic_priorities) == 2
    assert outcome.resolution_source == "WEB_RESEARCH"

    # Verify producer artifacts
    run_dir = Path(outcome.research_artifact_dir)
    assert run_dir.is_dir()
    assert (run_dir / "company_brief.md").is_file()
    assert (run_dir / "company_brief.json").is_file()
    assert (run_dir / "apps_research_apps_rg_handoff_v2.json").is_file()
    assert (run_dir / "bundle_commit_manifest.json").is_file()
    assert (run_dir / "apps_research_u0_receipt.json").is_file()
    assert (run_dir / "run_metadata.json").is_file()

    # Verify consumer artifacts
    assert (consumer_dir / "research_bridge_request.json").is_file()
    assert (consumer_dir / "research_bridge_response.json").is_file()
    assert (consumer_dir / "delegated_briefing.md").is_file()


def test_delegation_blocked_fails_closed():
    bridge = MockAppsResearchBridge(
        is_blocked=True,
        block_reason="X2_RESEARCH_GATE_REJECTED",
    )

    req = RequestForOutreachBriefing(
        request_id="req-test-blocked",
        run_id="run-test-blocked",
        trace_id="trace-test-blocked",
        company_name="Blocked Corp",
        job_title="VP Engineering",
    )

    outcome = dispatch_outreach_research_briefing(req, bridge=bridge)
    assert isinstance(outcome, ResearchDispatchFailure)
    assert outcome.r5_reason_code == ResearchFailureReason.APPS_RESEARCH_BLOCKED.value
    assert "X2_RESEARCH_GATE_REJECTED" in outcome.detail


def test_tampered_artifact_digest_fails_closed(tmp_path: Path):
    producer_runs = tmp_path / "tamper_runs"
    bridge = MockAppsResearchBridge(artifact_runs_root=producer_runs)

    res = bridge.fetch(
        company_name="Tamper Corp",
        job_title="Director",
        run_id="run-tamper-1",
    )

    # Validate before tampering
    valid_pre, _, _ = _validate_persisted_research_artifacts(res)
    assert valid_pre

    # Tamper with the briefing file on disk
    brief_file = Path(res.briefing_artifact_path)
    brief_file.write_text("TAMPERED ADVERSARIAL CONTENT\n", encoding="utf-8")

    # Validate after tampering - must fail closed
    valid_post, reason, _ = _validate_persisted_research_artifacts(res)
    assert not valid_post
    assert "digest mismatch" in reason or "does not match bridge result" in reason


def test_canonical_brief_resolution():
    content, path = _resolve_canonical_targeting_brief(
        company_name="Truist",
        job_title="Head of AI Enablement",
    )
    assert content != ""
    assert path != ""
    assert "truist" in path.lower()
