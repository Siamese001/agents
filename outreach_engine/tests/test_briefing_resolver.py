"""Non-mock Wave 1 tests for GovernedBriefingResolver, canonical fixture persistence, and shared disk cache."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfile,
    ChannelType,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.integrations.apps_research_bridge import AppsResearchBridge
from apps_lic.integrations.managed_research_delegation import (
    OutreachBriefingReady,
    RequestForOutreachBriefing,
    execute_managed_research,
)
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver
from apps_lic.pipeline.orchestrator import OutreachOrchestrator


@pytest.fixture(autouse=True)
def _reset_resolver_cache() -> None:
    GovernedBriefingResolver.clear_cache()
    GovernedBriefingResolver.SHARED_DISK_CACHE_DIR = None
    yield
    GovernedBriefingResolver.clear_cache()
    GovernedBriefingResolver.SHARED_DISK_CACHE_DIR = None


@pytest.mark.parametrize("company", ["Truist", "Citi", "Anthropic"])
def test_resolver_canonical_fixture_with_artifact_runs_root(tmp_path: Path, company: str) -> None:
    """Defect 1A: Canonical fixture resolution with artifact_runs_root set must pass X2/X3 and persist receipts."""
    runs_root = tmp_path / "apps_research" / "runs"
    res = GovernedBriefingResolver.resolve(
        company_name=company,
        target_role="Chief Technology Officer",
        artifact_runs_root=runs_root,
        trace_id=f"trace-{company.lower()}-01",
        force_fresh=True,
    )

    assert res.resolution_source == "CANONICAL_FIXTURE"
    assert res.is_verified is True
    assert res.confidence_score > 0.0
    assert res.evidence_count > 0
    assert len(res.strategic_priorities) > 0
    assert res.research_artifact_dir != ""

    run_dir = Path(res.research_artifact_dir)
    assert run_dir.is_dir()
    u0_path = run_dir / "apps_research_u0_receipt.json"
    handoff_path = run_dir / "apps_research_apps_rg_handoff_v2.json"
    assert u0_path.is_file()
    assert handoff_path.is_file()

    u0 = json.loads(u0_path.read_text(encoding="utf-8"))
    assert u0.get("status") == "PASS" or u0.get("gate_status") == "PASS"
    assert u0["trace_root"] == f"trace-{company.lower()}-01"

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff["exit_authorization"]["x3_code"] == "X3D_ALLOW_FINISH"
    assert (run_dir / "exit_disposition_receipt.json").is_file()


def test_execute_managed_research_persists_valid_bundle(tmp_path: Path) -> None:
    """Defect 1B: execute_managed_research with real AppsResearchBridge must pass strict artifact validation."""
    runs_root = tmp_path / "runs"
    bridge = AppsResearchBridge(artifact_runs_root=runs_root)
    req = RequestForOutreachBriefing(
        request_id="req-mrd-01",
        run_id="run-mrd-01",
        trace_id="trace-mrd-01",
        company_name="Truist",
        job_title="Head of Enterprise AI",
        artifact_runs_root=runs_root,
        force_fresh=True,
    )

    outcome = execute_managed_research(req, bridge=bridge, consumer_artifact_dir=tmp_path / "consumer")
    assert isinstance(outcome, OutreachBriefingReady), f"Expected OutreachBriefingReady, got {outcome}"
    assert outcome.resolution_source == "CANONICAL_FIXTURE"
    assert outcome.confidence_score >= 0.90
    assert outcome.research_evidence_count >= 1
    assert (tmp_path / "consumer" / "research_bridge_response.json").is_file()


def test_orchestrator_resolve_opportunity_briefing_raw_text_extraction_and_evidence_count() -> None:
    """Defect 1C & Defect 2: Opportunity briefing_text extracts priorities and propagates evidence_count."""
    orchestrator = OutreachOrchestrator()
    candidate = CandidateProfile(
        candidate_id="cand_w1",
        full_name="Alex Rivera",
        target_title="VP of Platform Engineering",
        current_title="VP of Platform Engineering",
        executive_summary="Platform engineering executive scaling resilient cloud infrastructure.",
        key_competencies=["Cloud Architecture", "AI Governance"],
        verified_facts=[
            CandidateFact(
                fact_id="f1",
                category="scale",
                statement="Scaled cloud platform availability to 99.99% while reducing annual compute spend by 28%.",
                metric="99.99%",
            )
        ],
    )
    raw_brief = (
        "# Executive Briefing: Acme Cloud\n\n"
        "## Strategic Priorities\n"
        "- Accelerate multi-region Kubernetes control plane modernization across core banking workloads\n"
        "- Establish zero-trust runtime governance and automated reliability guardrails\n"
        "- Reduce cloud infrastructure unit cost through workload telemetry and FinOps automation\n"
    )
    opp = TargetOpportunity(
        opportunity_id="opp_raw_text",
        company_name="Acme Cloud",
        role_title="VP of Platform Engineering",
        industry="Enterprise Technology",
        recipient_name="Jordan Lee",
        recipient_title="Chief Information Officer",
        recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=[],
        briefing_text=raw_brief,
    )

    resolved = orchestrator.resolve_opportunity_briefing(opp, auto_research=False)
    assert len(resolved.strategic_priorities) == 3
    assert resolved.sealed_resolution["metadata"]["extraction_mode"] == "RAW_TEXT_EXTRACTION"
    assert len(resolved.evidence_items) == 3

    draft, verdict = orchestrator.generate_single_draft(
        candidate,
        opp,
        ChannelType.LINKEDIN_INMAIL,
        auto_research=False,
    )
    assert verdict.passed is True
    assert draft.research_metadata["evidence_count"] == 3


def test_shared_disk_cache_rejects_unverified_and_tampered_payloads(tmp_path: Path) -> None:
    """Defect 3: _load_from_shared_disk must reject unverified, missing-digest, or tampered cache files."""
    GovernedBriefingResolver.SHARED_DISK_CACHE_DIR = tmp_path

    # 1. Valid save and reload
    res1 = GovernedBriefingResolver.resolve(
        company_name="Truist",
        target_role="CTO",
        auto_research=True,
        force_fresh=True,
    )
    assert res1.is_verified is True

    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
    cache_file = cache_files[0]

    GovernedBriefingResolver.clear_cache()
    res_hit = GovernedBriefingResolver.resolve(
        company_name="Truist",
        target_role="CTO",
        auto_research=False,
    )
    assert res_hit.resolution_source == "CACHE_HIT"
    assert res_hit.is_verified is True

    # 2. Tamper with briefing_text so digest no longer matches
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    payload["briefing_text"] = "# Tampered brief with mismatched sha256 digest"
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    GovernedBriefingResolver.clear_cache()
    res_tampered = GovernedBriefingResolver.resolve(
        company_name="Truist",
        target_role="CTO",
        auto_research=False,
    )
    assert res_tampered.resolution_source == "HERMETIC_FALLBACK"
    assert res_tampered.is_verified is False

    # 3. Missing is_verified in metadata must be rejected
    payload["briefing_text"] = res1.briefing_text
    payload["metadata"].pop("is_verified", None)
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    GovernedBriefingResolver.clear_cache()
    res_unverified = GovernedBriefingResolver.resolve(
        company_name="Truist",
        target_role="CTO",
        auto_research=False,
    )
    assert res_unverified.resolution_source == "HERMETIC_FALLBACK"
    assert res_unverified.is_verified is False

    # 4. Expired TTL must unlink file and reject
    payload["metadata"]["is_verified"] = True
    payload["created_at"] = time.time() - (40 * 86400.0)
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    GovernedBriefingResolver.clear_cache()
    res_expired = GovernedBriefingResolver.resolve(
        company_name="Truist",
        target_role="CTO",
        auto_research=False,
    )
    assert res_expired.resolution_source == "HERMETIC_FALLBACK"
    assert not cache_file.exists()
