"""apps-test-model: APP CONTRACT.

apps_rg bridge fail-closed contract gate + delegation tests.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps_rg.integrations.apps_research_bridge import (
    AppsResearchBridge,
    EvidenceItem,
    MockAppsResearchBridge,
    ResearchResult,
)
from apps_rg.integrations.managed_research_delegation import (
    RequestForResumeBriefing,
    ResearchDispatchFailure,
    ResumeBriefingReady,
    dispatch_resume_research_briefing,
)
from apps_research.integrations.apps_rg_handoff import (
    persist_apps_rg_targeting_brief_artifacts,
)
from tests.unit.apps_research.test_apps_rg_handoff_canonical_exit import (
    _record,
    _record_for_identity,
)


def _fetch(bridge: AppsResearchBridge):
    return bridge.fetch(
        company_name="Acme Co",
        job_title="SVP IT Strategy",
        capability_ref="apps_research.v1",
        request_id="req-1",
        run_id="run-1",
        trace_id="trace-1",
    )


def test_mock_bridge_default_brief_cannot_pass_contract_gate(tmp_path: Path) -> None:
    result = _fetch(
        MockAppsResearchBridge(
            confidence_score=0.9,
            artifact_runs_root=tmp_path / "apps_research",
        )
    )
    assert result.is_blocked
    # The mock has no canonical X3 allow receipt, so persistence may fail at
    # the canonical exit before the legacy G26 eligibility label is emitted.
    assert "apps_research_artifact_persistence_failed" in result.block_reason
    assert "X3D_BLOCKED" in result.block_reason
    assert result.briefing_artifact_path == ""
    assert result.apps_research_handoff_envelope is None


def test_bridge_rejects_missing_brief_text() -> None:
    bridge = MockAppsResearchBridge(confidence_score=0.9, company_brief_text=" ")
    # company_brief_text=" " is whitespace → falls back to default valid brief;
    # force genuinely empty by overriding the mock raw output.
    bridge._mock_brief = ""
    result = _fetch(bridge)
    assert result.is_blocked
    assert "missing_company_brief_text" in result.block_reason
    assert result.company_brief_text == ""


def test_bridge_persists_inner_dag_failure_forensics_for_missing_brief(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "apps_research" / "runs"
    raw = SimpleNamespace(
        run_id="research-run-1",
        is_blocked=False,
        block_reason="",
        company_brief_text="",
        hop_terminal_error="required stage company_brief failed",
        hop_checkpoints=(
            {
                "stage_id": 1,
                "stage_name": "research_retrieval",
                "status": "COMPLETED",
                "duration_ms": 12.5,
                "error": "",
            },
            {
                "stage_id": 2,
                "stage_name": "company_brief",
                "status": "FAILED",
                "duration_ms": 24.5,
                "error": "CompanyBriefUnavailableError: X2 judge failed",
            },
        ),
        fec_run_context={},
        evidence_items=(),
        confidence_score=0.0,
        support_coverage=0.0,
        is_stale=False,
        age_days=0.0,
    )
    bridge = AppsResearchBridge(artifact_runs_root=runs_root)

    result = bridge._translate(
        raw=raw,
        run_id="parent-run",
        trace_id="trace-1",
        request_id="request-1",
        t_start=0.0,
        company_name="Anthropic",
        job_title="Manager of Applied AI Architecture, Partnerships",
    )

    assert result.is_blocked is True
    assert "required stage company_brief failed" in result.block_reason
    assert "forensic_ref=" in result.block_reason
    forensic_path = tmp_path / "apps_research" / "apps_research_blocked_run_forensics.json"
    forensic = json.loads(forensic_path.read_text(encoding="utf-8"))
    assert forensic["handoff_authorized"] is False
    assert forensic["hop_terminal_error"] == "required stage company_brief failed"
    assert forensic["hop_checkpoints"][1]["status"] == "FAILED"
    assert forensic["hop_checkpoints"][1]["error"].endswith("X2 judge failed")


def test_bridge_rejects_contract_invalid_brief() -> None:
    bridge = MockAppsResearchBridge(confidence_score=0.9)
    bridge._mock_brief = '{"company": "Acme", "brief": "not markdown"}'
    result = _fetch(bridge)
    assert result.is_blocked
    assert "contract_invalid_company_brief_text" in result.block_reason
    assert result.company_brief_text == ""


class _StaticBridge:
    def __init__(self, result: ResearchResult) -> None:
        self._result = result

    def fetch(self, **_kwargs) -> ResearchResult:
        return self._result


def _persist_observed_result(tmp_path: Path) -> ResearchResult:
    base = _record("run-1")
    producer_record = _record_for_identity(
        run_id="run-1",
        trace_id="trace-1",
        request_id="req-1",
    )
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=producer_record,
        target_company="Acme Co",
        target_role="SVP IT Strategy",
        jd_text="Lead enterprise technology strategy.",
        runs_root=tmp_path / "apps_research",
    )
    return ResearchResult(
        run_id="run-1",
        trace_id="trace-1",
        request_id="req-1",
        is_blocked=False,
        block_reason="",
        is_stale=False,
        age_days=0.0,
        evidence_items=(
            EvidenceItem(
                source_id="observed-fixture",
                label="Observed provider fixture",
                uri="test://observed-provider-fixture",
                source_type="provider_response",
                field_ref="company_brief",
                confidence=0.91,
            ),
        ),
        confidence_score=base.confidence_score,
        result_hash=bundle.bundle_manifest_digest,
        company_brief_hash=bundle.brief_sha256,
        fetch_duration_ms=0.0,
        audit_ref=str(bundle.run_dir),
        research_artifact_dir=str(bundle.run_dir),
        briefing_artifact_path=str(bundle.briefing_path),
        company_brief_text=base.company_brief_text,
        apps_research_handoff_envelope=bundle.envelope,
        brief_sha256=bundle.brief_sha256,
        result_metadata_digest=bundle.result_metadata_digest,
        bundle_manifest_digest=bundle.bundle_manifest_digest,
        apps_research_u0_receipt=json.loads(bundle.u0_receipt_path.read_text(encoding="utf-8")),
    )


def test_delegation_fails_closed_without_persisted_briefing(tmp_path: Path) -> None:
    req = RequestForResumeBriefing(
        request_id="req-1",
        run_id="run-1",
        trace_id="trace-1",
        company_name="Acme Co",
        job_title="SVP IT Strategy",
        research_authorized=True,
    )
    in_memory_only = replace(
        _persist_observed_result(tmp_path),
        research_artifact_dir="",
        briefing_artifact_path="",
    )
    outcome = dispatch_resume_research_briefing(req, bridge=_StaticBridge(in_memory_only))
    assert isinstance(outcome, ResearchDispatchFailure)
    assert outcome.r5_reason_code == "APPS_RESEARCH_ARTIFACT_MISSING"
    assert "research_artifact_dir" in outcome.detail


def test_delegation_returns_ready_with_persisted_brief(tmp_path: Path) -> None:
    req = RequestForResumeBriefing(
        request_id="req-1",
        run_id="run-1",
        trace_id="trace-1",
        company_name="Acme Co",
        job_title="SVP IT Strategy",
        research_authorized=True,
    )
    persisted = _persist_observed_result(tmp_path)

    outcome = dispatch_resume_research_briefing(req, bridge=_StaticBridge(persisted))

    assert isinstance(outcome, ResumeBriefingReady)
    assert outcome.briefing_text.strip()
    assert Path(outcome.research_briefing_path).is_file()
    assert Path(outcome.research_artifact_dir).is_dir()
    assert outcome.apps_research_handoff_envelope["schema_version"] == (
        "apps_research.apps_rg_handoff.v2"
    )
    assert set(outcome.apps_research_handoff_envelope["mandatory_gate_receipts"]) == {
        "G5",
        "G6",
        "G7",
        "G21",
        "G24",
        "G26",
    }


@pytest.mark.parametrize(
    "tamper",
    (
        "missing_company_brief",
        "changed_briefing_text",
        "escaped_envelope_path",
        "malformed_envelope",
    ),
)
def test_delegation_rejects_tampered_producer_bundle(
    tmp_path: Path,
    tamper: str,
) -> None:
    persisted = _persist_observed_result(tmp_path)
    run_dir = Path(persisted.research_artifact_dir)
    envelope_path = run_dir / "apps_research_apps_rg_handoff_v2.json"
    if tamper == "missing_company_brief":
        (run_dir / "company_brief.json").unlink()
    elif tamper == "changed_briefing_text":
        Path(persisted.briefing_artifact_path).write_text(
            "Tampered briefing text.\n", encoding="utf-8"
        )
    elif tamper == "escaped_envelope_path":
        envelope = dict(persisted.apps_research_handoff_envelope or {})
        envelope["artifact_manifest"]["artifacts"][0]["artifact_ref"] = str(
            (tmp_path / "outside.md").resolve()
        )
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        persisted = replace(persisted, apps_research_handoff_envelope=envelope)
    else:
        envelope_path.write_text("{not-json", encoding="utf-8")
    req = RequestForResumeBriefing(
        request_id="req-tamper",
        run_id="run-tamper",
        trace_id="trace-tamper",
        company_name="Acme Co",
        job_title="SVP IT Strategy",
        research_authorized=True,
    )

    outcome = dispatch_resume_research_briefing(req, bridge=_StaticBridge(persisted))

    assert isinstance(outcome, ResearchDispatchFailure)
    assert outcome.r5_reason_code == "APPS_RESEARCH_ARTIFACT_MISSING"


def test_delegation_fails_closed_without_handoff_envelope() -> None:
    bridge = MockAppsResearchBridge(confidence_score=0.9)
    bridge._mock_sidecar = lambda _brief: {}  # type: ignore[method-assign]
    req = RequestForResumeBriefing(
        request_id="req-1",
        run_id="run-1",
        trace_id="trace-1",
        company_name="Acme Co",
        job_title="SVP IT Strategy",
        research_authorized=True,
    )
    outcome = dispatch_resume_research_briefing(req, bridge=bridge)
    assert isinstance(outcome, ResearchDispatchFailure)
    assert outcome.r5_reason_code == "APPS_RESEARCH_BLOCKED"
    assert "missing_apps_research_handoff_v2" in outcome.detail


def test_delegation_fails_closed_on_blocked_brief() -> None:
    bridge = MockAppsResearchBridge(confidence_score=0.9)
    bridge._mock_brief = ""
    req = RequestForResumeBriefing(
        request_id="req-1",
        run_id="run-1",
        trace_id="trace-1",
        company_name="Acme Co",
        job_title="SVP IT Strategy",
        research_authorized=True,
    )
    outcome = dispatch_resume_research_briefing(req, bridge=bridge)
    assert isinstance(outcome, ResearchDispatchFailure)
    assert outcome.r5_reason_code in {"APPS_RESEARCH_BLOCKED", "APPS_RESEARCH_EMPTY"}
