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


# =============================================================================
# Wave 3: Regression Tests (Tampering, Fallback, Successful-Handoff)
# =============================================================================


def test_tampered_u0_receipt_fails_closed(tmp_path: Path):
    """Tampering with U0 receipt status, schema, or authority proof must fail closed."""
    producer_runs = tmp_path / "tamper_u0_runs"
    bridge = MockAppsResearchBridge(artifact_runs_root=producer_runs)

    res = bridge.fetch(
        company_name="U0TamperCorp",
        job_title="VP Engineering",
        run_id="run-u0-tamper-1",
        trace_id="trace-u0-tamper-1",
    )
    valid_pre, _, _ = _validate_persisted_research_artifacts(res)
    assert valid_pre

    u0_file = Path(res.research_artifact_dir) / "apps_research_u0_receipt.json"

    # 1. Tamper status: change from PASS to SYNTHETIC_PASS
    original_u0 = json.loads(u0_file.read_text(encoding="utf-8"))
    tampered_u0 = dict(original_u0)
    tampered_u0["status"] = "SYNTHETIC_PASS"
    u0_file.write_text(json.dumps(tampered_u0, indent=2), encoding="utf-8")

    valid_post, reason, _ = _validate_persisted_research_artifacts(res)
    assert not valid_post
    assert "status is not PASS" in reason

    # 2. Tamper authority contract id
    tampered_u0 = dict(original_u0)
    tampered_u0["authority_contract_id"] = "forged_contract_id"
    u0_file.write_text(json.dumps(tampered_u0, indent=2), encoding="utf-8")

    valid_post, reason, _ = _validate_persisted_research_artifacts(res)
    assert not valid_post
    assert "authority_contract_id invalid" in reason

    # 3. Tamper authority validation receipt
    tampered_u0 = dict(original_u0)
    tampered_u0["authority_validation_receipt"] = {"passed": False, "allowed": False}
    u0_file.write_text(json.dumps(tampered_u0, indent=2), encoding="utf-8")

    valid_post, reason, _ = _validate_persisted_research_artifacts(res)
    assert not valid_post
    assert "authority_validation_receipt" in reason


def test_tampered_commit_manifest_fails_closed(tmp_path: Path):
    """Tampering with bundle_commit_manifest status or authority must fail closed."""
    producer_runs = tmp_path / "tamper_manifest_runs"
    bridge = MockAppsResearchBridge(artifact_runs_root=producer_runs)

    res = bridge.fetch(
        company_name="ManifestTamperCorp",
        job_title="VP AI",
        run_id="run-manifest-tamper-1",
        trace_id="trace-manifest-tamper-1",
    )
    valid_pre, _, _ = _validate_persisted_research_artifacts(res)
    assert valid_pre

    manifest_file = Path(res.research_artifact_dir) / "bundle_commit_manifest.json"
    original_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    # 1. Tamper status: UNCOMMITTED instead of COMMITTED
    tampered = dict(original_manifest)
    tampered["status"] = "UNCOMMITTED"
    manifest_file.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

    valid_post, reason, _ = _validate_persisted_research_artifacts(res)
    assert not valid_post
    assert "bundle_commit_manifest status is not COMMITTED" in reason

    # 2. Tamper authority contract id
    tampered = dict(original_manifest)
    tampered["authority_contract_id"] = "forged_authority"
    manifest_file.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

    valid_post, reason, _ = _validate_persisted_research_artifacts(res)
    assert not valid_post
    assert "bundle_commit_manifest authority_contract_id invalid" in reason


def test_tampered_mandatory_gates_and_exit_auth_fails_closed(tmp_path: Path):
    """Tampering with gate verdicts or canonical exit dispositions must fail closed."""
    producer_runs = tmp_path / "tamper_gates_runs"
    bridge = MockAppsResearchBridge(artifact_runs_root=producer_runs)

    res = bridge.fetch(
        company_name="GatesTamperCorp",
        job_title="Director of Engineering",
        run_id="run-gates-tamper-1",
        trace_id="trace-gates-tamper-1",
    )
    valid_pre, _, _ = _validate_persisted_research_artifacts(res)
    assert valid_pre

    handoff_file = Path(res.research_artifact_dir) / "apps_research_apps_rg_handoff_v2.json"
    original_handoff = json.loads(handoff_file.read_text(encoding="utf-8"))

    # 1. Tamper gate receipt status: G21 set to FAIL
    tampered = dict(original_handoff)
    gates = dict(tampered.get("mandatory_gate_receipts", {}))
    gates["G21"] = {**gates.get("G21", {}), "status": "FAIL"}
    tampered["mandatory_gate_receipts"] = gates
    handoff_file.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

    valid_post, reason, _ = _validate_persisted_research_artifacts(res)
    assert not valid_post
    assert (
        "mandatory gate G21 status is not PASS" in reason
        or "differs from committed bytes" in reason
        or "differs from persisted producer manifest" in reason
    )

    # 2. Tamper exit authorization: x3_code set to X3D_BLOCKED
    tampered = dict(original_handoff)
    tampered["exit_authorization"] = {"x3_code": "X3D_BLOCKED"}
    handoff_file.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

    valid_post, reason, _ = _validate_persisted_research_artifacts(res)
    assert not valid_post
    assert (
        "exit authorization x3_code is not X3D_ALLOW_FINISH" in reason
        or "differs from committed bytes" in reason
        or "differs from persisted producer manifest" in reason
    )

    # 3. Tamper producer app id
    tampered = dict(original_handoff)
    tampered["producer"] = {"producer_app_id": "impostor_app", "attestation_sha256": "fake"}
    handoff_file.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

    valid_post, reason, _ = _validate_persisted_research_artifacts(res)
    assert not valid_post
    assert (
        "valid producer attestation" in reason
        or "differs from committed bytes" in reason
        or "differs from persisted producer manifest" in reason
    )


def test_execution_identity_mismatch_fails_closed(tmp_path: Path):
    """Execution identity mismatches (company, role, run_id, trace_id) must fail closed."""
    producer_runs = tmp_path / "identity_mismatch_runs"
    bridge = MockAppsResearchBridge(artifact_runs_root=producer_runs)

    res = bridge.fetch(
        company_name="TargetCorp",
        job_title="Lead Architect",
        run_id="run-ident-1",
        trace_id="trace-ident-1",
        request_id="req-ident-1",
    )
    valid_pre, _, _ = _validate_persisted_research_artifacts(res)
    assert valid_pre

    # 1. Company mismatch
    mismatch_req_co = RequestForOutreachBriefing(
        request_id="req-ident-1",
        run_id="run-ident-1",
        trace_id="trace-ident-1",
        company_name="AttackerCorp",
        job_title="Lead Architect",
    )
    valid_co, reason_co, _ = _validate_persisted_research_artifacts(res, request=mismatch_req_co)
    assert not valid_co
    assert "company mismatch" in reason_co

    # 2. Role mismatch
    mismatch_req_role = RequestForOutreachBriefing(
        request_id="req-ident-1",
        run_id="run-ident-1",
        trace_id="trace-ident-1",
        company_name="TargetCorp",
        job_title="Junior Intern",
    )
    valid_role, reason_role, _ = _validate_persisted_research_artifacts(res, request=mismatch_req_role)
    assert not valid_role
    assert "role mismatch" in reason_role

    # 3. Run ID mismatch
    mismatch_req_run = RequestForOutreachBriefing(
        request_id="req-ident-1",
        run_id="run-mismatch-id",
        trace_id="trace-ident-1",
        company_name="TargetCorp",
        job_title="Lead Architect",
    )
    valid_run, reason_run, _ = _validate_persisted_research_artifacts(res, request=mismatch_req_run)
    assert not valid_run
    assert "run_id mismatch" in reason_run

    # 4. Trace ID mismatch
    mismatch_req_trace = RequestForOutreachBriefing(
        request_id="req-ident-1",
        run_id="run-ident-1",
        trace_id="trace-mismatch-id",
        company_name="TargetCorp",
        job_title="Lead Architect",
    )
    valid_trace, reason_trace, _ = _validate_persisted_research_artifacts(res, request=mismatch_req_trace)
    assert not valid_trace
    assert "trace mismatch" in reason_trace


def test_cryptographic_digest_mismatch_fails_closed(tmp_path: Path):
    """Cryptographic digest mismatches in ResearchResult must fail closed."""
    import dataclasses

    producer_runs = tmp_path / "digest_mismatch_runs"
    bridge = MockAppsResearchBridge(artifact_runs_root=producer_runs)

    res = bridge.fetch(
        company_name="DigestCorp",
        job_title="Head of Engineering",
        run_id="run-digest-1",
    )

    # 1. Briefing digest mismatch
    res_tampered_brief = dataclasses.replace(
        res, brief_sha256="sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )
    valid, reason, _ = _validate_persisted_research_artifacts(res_tampered_brief)
    assert not valid
    assert "bridge brief_sha256 differs from committed bytes" in reason

    # 2. Result metadata digest mismatch
    res_tampered_meta = dataclasses.replace(
        res, result_metadata_digest="sha256:1111111111111111111111111111111111111111111111111111111111111111"
    )
    valid, reason, _ = _validate_persisted_research_artifacts(res_tampered_meta)
    assert not valid
    assert "bridge result_metadata_digest differs from committed bytes" in reason

    # 3. Bundle manifest digest mismatch
    res_tampered_manifest = dataclasses.replace(
        res, bundle_manifest_digest="sha256:2222222222222222222222222222222222222222222222222222222222222222"
    )
    valid, reason, _ = _validate_persisted_research_artifacts(res_tampered_manifest)
    assert not valid
    assert "bridge bundle_manifest_digest differs from committed bytes" in reason


def test_unverified_hermetic_fallback_rejected_by_delegation(tmp_path: Path):
    """An unverified hermetic fallback bridge result must be rejected by delegation."""
    bridge = AppsResearchBridge(artifact_runs_root=tmp_path / "fallback_runs")

    fallback_res = bridge._hermetic_fallback(
        company_name="FallbackCorp",
        job_title="CTO",
        job_description_text="",
        req_id="req-fallback-1",
        r_id="run-fallback-1",
        bridge_trace_id="trace-fallback-1",
        t_start=0.0,
    )
    assert fallback_res.is_verified is False

    # Dispatch via delegation must fail closed
    valid, reason, _ = _validate_persisted_research_artifacts(fallback_res)
    assert not valid
    assert (
        "schema_version is not apps_research.u0_receipt.v1" in reason
        or "status is not PASS" in reason
        or "UNVERIFIED" in reason
        or "bundle_commit_manifest" in reason
    )


def test_freshness_ttl_enforcement(tmp_path: Path):
    """Stale research artifacts beyond freshness_ttl_days must be rejected."""
    import os
    import time

    producer_runs = tmp_path / "ttl_runs"

    class StaleMockBridge(MockAppsResearchBridge):
        def fetch(self, **kwargs):
            res = super().fetch(**kwargs)
            meta_path = Path(res.research_artifact_dir) / "run_metadata.json"
            old_time = time.time() - (10 * 86400.0)
            os.utime(meta_path, (old_time, old_time))
            return res

    bridge = StaleMockBridge(artifact_runs_root=producer_runs)
    req = RequestForOutreachBriefing(
        request_id="req-ttl-1",
        run_id="run-ttl-1",
        trace_id="trace-ttl-1",
        company_name="OldCorp",
        job_title="Lead Architect",
        freshness_ttl_days=7,
        artifact_runs_root=producer_runs,
    )

    outcome = dispatch_outreach_research_briefing(req, bridge=bridge)
    assert isinstance(outcome, ResearchDispatchFailure)
    assert outcome.r5_reason_code == ResearchFailureReason.APPS_RESEARCH_STALE.value
    assert "stale" in outcome.detail.lower()


def test_empty_evidence_or_invalid_uri_rejected(tmp_path: Path):
    """Empty evidence items or missing source URIs must fail closed."""
    # 1. Empty evidence items
    bridge_empty = MockAppsResearchBridge(evidence_items=[], artifact_runs_root=tmp_path / "empty_runs")
    req = RequestForOutreachBriefing(
        request_id="req-empty-1",
        run_id="run-empty-1",
        trace_id="trace-empty-1",
        company_name="EmptyCorp",
        job_title="VP AI",
        require_evidence=True,
    )
    outcome = dispatch_outreach_research_briefing(req, bridge=bridge_empty)
    assert isinstance(outcome, ResearchDispatchFailure)
    assert outcome.r5_reason_code == ResearchFailureReason.APPS_RESEARCH_EMPTY.value

    # 2. Missing source URI on evidence item
    invalid_item = EvidenceItem(
        source_id="ev-no-uri",
        label="Invalid Evidence",
        uri="",  # Empty URI is prohibited
        source_type="web",
        field_ref="brief",
        confidence=0.9,
    )
    bridge_no_uri = MockAppsResearchBridge(evidence_items=[invalid_item], artifact_runs_root=tmp_path / "no_uri_runs")
    outcome_uri = dispatch_outreach_research_briefing(req, bridge=bridge_no_uri)
    assert isinstance(outcome_uri, ResearchDispatchFailure)
    assert outcome_uri.r5_reason_code == ResearchFailureReason.APPS_RESEARCH_FAILED.value
    assert "lacks source URI" in outcome_uri.detail


def test_successful_handoff_with_full_evidence_and_receipts(tmp_path: Path):
    """A fully verified authentic producer handoff succeeds with complete receipts."""
    producer_runs = tmp_path / "success_producer"
    consumer_dir = tmp_path / "success_consumer"

    bridge = MockAppsResearchBridge(
        artifact_runs_root=producer_runs,
        confidence_score=0.95,
        strategic_priorities=("Priority Alpha", "Priority Beta"),
    )

    req = RequestForOutreachBriefing(
        request_id="req-full-success-1",
        run_id="run-full-success-1",
        trace_id="trace-full-success-1",
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
    assert outcome.confidence_score == 0.95
    assert outcome.resolution_source == "WEB_RESEARCH"
    assert outcome.strategic_priorities == ("Priority Alpha", "Priority Beta")
    assert outcome.brief_sha256.startswith("sha256:")
    assert outcome.result_metadata_digest.startswith("sha256:")
    assert outcome.bundle_manifest_digest.startswith("sha256:")

    # Consumer artifacts exist and match
    assert (consumer_dir / "research_bridge_request.json").is_file()
    assert (consumer_dir / "research_bridge_response.json").is_file()
    assert (consumer_dir / "delegated_briefing.md").is_file()

    # Exact bytes match between delegated briefing and producer briefing
    producer_briefing = Path(outcome.research_briefing_path)
    delegated_briefing = consumer_dir / "delegated_briefing.md"
    assert producer_briefing.read_bytes() == delegated_briefing.read_bytes()

    # Evidence lineage bound
    assert len(outcome.evidence_lineage) >= 1
    assert all(bool(item.get("uri")) for item in outcome.evidence_lineage)


def test_outreach_architecture_boundaries_and_file_budgets():
    """Verify outreach_engine passes all architectural boundary, sys.path purity, and 600-line ceiling checks."""
    from tools.lint_architecture_boundaries import run_architecture_linter

    repo_root = Path(__file__).resolve().parents[2]
    results = run_architecture_linter(repo_root)
    assert results["is_clean"] is True, f"Architectural violations found: {results}"
    assert results["total_violation_count"] == 0


