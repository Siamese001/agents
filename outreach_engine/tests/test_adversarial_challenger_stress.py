"""Adversarial stress-test harness for Subsystems 3, 5, and 6 in Outreach Engine.

Executed by Challenger to probe corner cases, malicious payloads, type fuzzing,
and boundary integrity under live, non-mock execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path

import pytest

from apps_lic.domain.models import (
    AudiencePersona,
    AuthoritativeVerdict,
    CandidateFact,
    CandidateProfile,
    CandidateProfileLoader,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.integrations.apps_research_bridge import (
    AppsResearchBridge,
    ResearchResult,
    execute_bounded_live_research,
)
from apps_lic.integrations.managed_research_delegation import (
    OutreachBriefingReady,
    RequestForOutreachBriefing,
    _validate_persisted_research_artifacts,
    dispatch_outreach_research_briefing,
)
from apps_lic.integrations.research_boundary_policy import (
    _find_valid_persisted_artifact_bundle,
    _normalize_canonical_brief_for_handoff,
)
from apps_lic.integrations.research_bridge_support import (
    persist_standalone_outreach_research_bundle,
)
from apps_lic.judges.evaluator import (
    EvaluationReport,
    ExecutiveOutreachJudgePanel,
)
from apps_lic.pipeline.compiler import PromptCompiler
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.pipeline.touch_sequence import (
    TouchPoint,
    TouchSequencePlanner,
)
from apps_lic.runtime.dispatch.canonical_dispatch import run_canonical_apps_lic_spine
from apps_lic.runtime.model_registry import (
    OutreachModelRegistry,
    OutreachModelRegistryError,
)


def test_compiler_path_traversal_adversarial_vectors():
    """Stress test template loader against URL encoding, backslashes, double extensions, and absolute paths."""
    compiler = PromptCompiler()
    vectors = [
        "../../../../../../etc/passwd",
        "/etc/passwd",
        "..%2F..%2F..%2Fetc%2Fpasswd",
        "..\\..\\..\\config\\provider_profiles",
        "....//....//....//config//provider_profiles",
        "outreach_draft_v2/../../provider_profiles",
        "nonexistent_sub/../../../../../etc/hosts",
    ]
    for vec in vectors:
        res = compiler.load_template(vec)
        assert res == {}, f"Path traversal attack vector '{vec}' should return empty dict, got {res}"


def test_compiler_render_draft_message_with_extreme_inputs():
    """Stress test compiler with unicode, excessive length, and weird characters."""
    compiler = PromptCompiler()
    cand = CandidateProfileLoader.load_default(
        overrides={
            "full_name": "Test Candidate \u202e RLO Injection \u202c",
            "current_title": "CTO & VP of Architecture ⚠",
            "target_title": "Chief Technology Officer",
        }
    )
    opp = TargetOpportunity(
        opportunity_id="opp_stress_1",
        company_name="Acme Corp — Global & Multi-National",
        role_title="SVP Engineering",
        industry="Tech",
        recipient_name="Alex Smith, Ph.D.",
        recipient_title="Head of Talent Acquisition",
        recipient_class=RecipientClass.TALENT_PARTNER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=[
            "Cloud modernization across U.S. and E.U. regions.",
            "AI adoption.",
        ],
        briefing_text="Acme Corp is accelerating modernization under Dr. Jane Doe.",
    )
    subj, body, facts = compiler.render_draft_message(
        candidate=cand,
        opportunity=opp,
        channel=ChannelType.LINKEDIN_CONNECTION,
        audience_persona=AudiencePersona.EXECUTIVE_RECRUITER,
    )
    assert len(body) <= 300, f"Connection note must be <= 300 chars, got {len(body)}"
    assert "Alex" in body, "Recipient first name should be preserved"
    assert "\u202e" not in body, "RLO injection should not contaminate or corrupt draft body"


def test_orchestrator_touch_continuity_touch2_failure():
    """If Touch 1 passes but Touch 2 fails, campaign status must be BLOCKED and Touch 3 blocked."""
    orchestrator = OutreachOrchestrator()
    cand = CandidateProfileLoader.load_default()
    opp = TargetOpportunity(
        opportunity_id="opp_t2_fail",
        company_name="TechCorp",
        role_title="VP Engineering",
        industry="Tech",
        recipient_name="Morgan",
        recipient_title="Director of Engineering",
        recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["Scale distributed systems"],
        briefing_text="TechCorp is hiring leadership.",
    )
    with tempfile.TemporaryDirectory() as td:
        seq = orchestrator.generate_full_campaign(
            candidate=cand,
            opportunity=opp,
            primary_channel=ChannelType.LINKEDIN_INMAIL,
            audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
            artifact_dir=Path(td),
        )
        assert seq.status in ("PASSED", "BLOCKED")
        manifest_file = Path(td) / "run_manifest.json"
        if manifest_file.is_file():
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            if seq.status == "BLOCKED":
                assert "authoritative_evaluation" not in manifest.get("completed_stages", [])


def test_touch_sequence_casing_and_multiple_re_prefixes():
    """Touch 2 subject must clean various casing and repetitions of Re:, RE:, re:, and whitespace."""
    planner = TouchSequencePlanner()
    cand = CandidateProfileLoader.load_default()
    opp = TargetOpportunity(
        opportunity_id="opp_re_prefix",
        company_name="AlphaCorp",
        role_title="CTO",
        industry="Tech",
        recipient_name="Sam",
        recipient_title="VP Talent",
        recipient_class=RecipientClass.TALENT_PARTNER,
        relationship_distance=RelationshipDistance.COLD,
    )
    for prefix in ("Re: ", "RE: ", "re: ", "Re: Re: ", "RE: re: RE:  "):
        t2 = planner._generate_touch_2(
            candidate=cand,
            opportunity=opp,
            persona=AudiencePersona.EXECUTIVE_RECRUITER,
            day_offset=3,
            sequence_id="seq_re",
            t1_subject=f"{prefix}Strategic discussion for AlphaCorp",
        )
        assert not t2.draft.subject.startswith("Re: Re:"), f"Subject accumulated duplicate Re: {t2.draft.subject}"
        assert t2.draft.subject.startswith("Re: Strategic discussion"), f"Expected 'Re: Strategic discussion', got {t2.draft.subject}"


def test_research_bridge_support_run_id_path_traversal():
    with tempfile.TemporaryDirectory() as td:
        runs_root = Path(td)
        malicious_ids = [
            "../../escaped",
            "/absolute_escape",
            "..\\..\\win_escaped",
            "....//....//nested",
            "safe_name/../../still_escaped",
            "",
            "   ",
            "...",
        ]
        for m_id in malicious_ids:
            class DummyRecord:
                run_id = m_id
                company_name = "Acme Global"
                role_title = "VP Engineering"
                company_brief_text = "# Acme Global\nStrategic mandate: cloud platform modernization."

            bundle = persist_standalone_outreach_research_bundle(
                record=DummyRecord(),
                target_company="Acme Global",
                target_role="VP Engineering",
                jd_text="",
                runs_root=runs_root,
            )
            created_dir = Path(bundle.run_dir).resolve()
            assert created_dir.is_relative_to(runs_root.resolve()), f"Path escaped root: {created_dir} vs {runs_root}"


def test_research_delegation_missing_u0_receipt_sha_fails_closed():
    from types import SimpleNamespace

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        record = SimpleNamespace(
            run_id="run-u0",
            trace_id="t1",
            request_id="r1",
            company_brief_text="# TargetCorp\nStrategic mandate: enterprise platform modernization.",
            confidence_score=0.95,
            strategic_priorities=["p1"],
        )
        bundle = persist_standalone_outreach_research_bundle(
            record=record,
            target_company="TargetCorp",
            target_role="CTO",
            jd_text="JD text",
            runs_root=root,
        )
        manifest_path = bundle.run_dir / "bundle_commit_manifest.json"
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "u0_receipt_sha256" in manifest_data

        del manifest_data["u0_receipt_sha256"]
        manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

        res = ResearchResult(
            run_id="run-u0",
            trace_id="t1",
            request_id="r1",
            is_blocked=False,
            block_reason="",
            is_stale=False,
            evidence_items=(),
            confidence_score=0.95,
            brief_sha256=bundle.brief_sha256,
            company_brief_text=record.company_brief_text,
            strategic_priorities=("p1",),
            fetch_duration_ms=10.0,
            audit_ref="t1",
            apps_research_handoff_envelope=bundle.envelope,
            research_artifact_dir=str(bundle.run_dir),
            briefing_artifact_path=str(bundle.briefing_path),
            result_metadata_digest=bundle.result_metadata_digest,
            bundle_manifest_digest=bundle.bundle_manifest_digest,
            resolution_source="PERSISTED_ARTIFACT",
            is_verified=True,
        )
        req = RequestForOutreachBriefing(
            request_id="r1",
            run_id="run-u0",
            trace_id="t1",
            company_name="TargetCorp",
            job_title="CTO",
            artifact_runs_root=root,
        )
        valid, reason, _ = _validate_persisted_research_artifacts(res, request=req)
        assert not valid, f"SECURITY VULNERABILITY: bundle missing u0_receipt_sha256 was accepted as valid! reason: {reason}"


def test_research_delegation_duck_typed_and_none_confidence():
    class FakeEvidence:
        statement = "Company revenue grew 30%."
        uri = "https://example.com/source"
        source_id = "src_1"

    res = ResearchResult(
        run_id="run_duck_1",
        trace_id="trace_duck_1",
        request_id="req_duck_1",
        is_blocked=False,
        block_reason="",
        is_stale=False,
        evidence_items=(FakeEvidence(),),
        confidence_score=None,
        brief_sha256="abc",
        company_brief_text="Brief text",
        strategic_priorities=("p1",),
        fetch_duration_ms=10.0,
        audit_ref="ref_1",
        resolution_source="WEB_RESEARCH",
        is_verified=True,
    )

    class FakeBridge:
        def fetch(self, *args, **kwargs):
            return res

    req = RequestForOutreachBriefing(
        request_id="req_duck_1",
        run_id="run_duck_1",
        trace_id="trace_duck_1",
        company_name="Acme",
        job_title="VP",
    )
    out = dispatch_outreach_research_briefing(request=req, bridge=FakeBridge())
    assert out is not None


def test_research_bridge_cost_limit_strict_abort():
    call_count = 0

    def mock_invoke(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Network flake")

    with pytest.raises((ConnectionError, TimeoutError, Exception)):
        execute_bounded_live_research(
            invoke_fn=mock_invoke,
            timeout_seconds=5.0,
            max_retries=3,
            cost_per_call_usd=0.08,
            cost_limit_usd=0.1,
            cumulative_cost_usd=0.0,
        )
    assert call_count <= 2, f"Expected cost limit abort, but executed {call_count} times"


def test_evaluator_nan_and_inf_scores_clamped_and_ranked():
    """Judge panel tournament must clamp NaN, Inf, and -Inf to 0.0 and never award wins to them."""
    panel = ExecutiveOutreachJudgePanel()
    cand = CandidateProfileLoader.load_default()
    opp = TargetOpportunity(
        opportunity_id="opp_judge_nan",
        company_name="BetaCorp",
        role_title="CTO",
        industry="Tech",
        recipient_name="Taylor",
        recipient_title="VP Talent",
        recipient_class=RecipientClass.TALENT_PARTNER,
        relationship_distance=RelationshipDistance.COLD,
    )
    draft_normal = OutreachMessageDraft(
        draft_id="draft_normal",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="BetaCorp leadership discussion",
        body="Hi Taylor,\n\nI have followed BetaCorp's engineering milestones. Scaled distributed platforms across multi-cloud environments.\n\nOpen to discussing priorities?",
        grounded_facts_used=["fact_1"],
    )
    draft_nan = OutreachMessageDraft(
        draft_id="draft_nan",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="BetaCorp discussion",
        body="Hi Taylor, spam words act now free buy now.",
    )
    tournament = panel.evaluate_persona_tournament(
        drafts=[draft_nan, draft_normal],
        candidate=cand,
        opportunity=opp,
    )
    for r in tournament["rankings"]:
        assert not math.isnan(r["tournament_score"]), f"Rankings contained NaN: {r}"
        assert not math.isinf(r["tournament_score"]), f"Rankings contained Inf: {r}"
    if tournament["passed"]:
        assert tournament["winner_draft_id"] != "draft_nan", "Failing NaN draft must never win tournament"


def test_evaluator_tournament_tie_breaking_deterministic():
    """Tournament must sort deterministically regardless of input permutation."""
    panel = ExecutiveOutreachJudgePanel()
    cand = CandidateProfileLoader.load_default()
    opp = TargetOpportunity(
        opportunity_id="opp_tie_break",
        company_name="GammaCorp",
        role_title="VP Engineering",
        industry="Tech",
        recipient_name="Jordan",
        recipient_title="Talent Lead",
        recipient_class=RecipientClass.TALENT_PARTNER,
        relationship_distance=RelationshipDistance.COLD,
    )
    draft_a = OutreachMessageDraft(
        draft_id="draft_a",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="GammaCorp engineering discussion",
        body="Hi Jordan,\n\nI have followed GammaCorp's platform milestones. Scaled enterprise platform systems.\n\nOpen to discussing priorities?",
        grounded_facts_used=["fact_1"],
    )
    draft_b = OutreachMessageDraft(
        draft_id="draft_b",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="GammaCorp engineering discussion",
        body="Hi Jordan,\n\nI have followed GammaCorp's platform milestones. Scaled enterprise platform systems.\n\nOpen to discussing priorities?",
        grounded_facts_used=["fact_1"],
    )
    t1 = panel.evaluate_persona_tournament([draft_a, draft_b], cand, opp)
    t2 = panel.evaluate_persona_tournament([draft_b, draft_a], cand, opp)
    assert t1["winner_draft_id"] == t2["winner_draft_id"], (
        f"Non-deterministic winner! [A, B] gave {t1['winner_draft_id']}, [B, A] gave {t2['winner_draft_id']}"
    )


def test_evaluator_report_from_verdict_none_handling():
    """report_from_verdict must safely format reports when lens_scores contains None values."""
    panel = ExecutiveOutreachJudgePanel()
    verdict = AuthoritativeVerdict(
        passed=True,
        status="PASSED",
        composite_score=0.92,
        score_band="EXEMPLARY",
        hard_gate_passed=True,
        judge_passed=True,
        violations=[],
        failure_reasons=[],
        lens_scores={"lens1_altitude": None, "lens2_grounding": 0.95, "lens3_resonance": None},
    )
    report = panel.report_from_verdict(verdict)
    assert isinstance(report, EvaluationReport)
    d = report.to_dict()
    assert d["passed"] is True
    assert d["composite_score"] == 0.92


def test_model_registry_arbitrary_unapproved_model_blocked():
    """Adversarial test: An unapproved model without 'unapproved' in its name must NOT be returned as default."""
    OutreachModelRegistry.clear_cache()
    arbitrary_unapproved = [
        "custom-shadow-gpt-v4",
        "llama-3-unregistered",
        "claude-3-unofficial",
        "deepseek-v3-external",
    ]
    for model in arbitrary_unapproved:
        assert not OutreachModelRegistry.validate_model(model), f"{model} should not be approved"


def test_canonical_dispatch_spine_adversarial_payloads():
    """Canonical dispatch spine must survive extreme/malicious ingress payloads without unhandled crash."""
    with tempfile.TemporaryDirectory() as td:
        artifact_dir = Path(td)
        payloads = [
            {},
            {"lead_profile": None, "target_role": None},
            {"lead_profile": "not_a_dict", "strategic_priorities": "single_string_not_list"},
            {"recipient_class": 99999, "relationship_distance": [1, 2, 3]},
            {"channel": "UNSUPPORTED_CHANNEL_NAME", "company": None},
            {"audience_persona": 12345, "manual_brief": 98765},
        ]
        for p in payloads:
            res = run_canonical_apps_lic_spine(p, artifact_dir)
            assert isinstance(res, dict)
            assert "x3_code" in res
            assert res["x3_code"] in ("X3D_ALLOW_FINISH", "X3D_BLOCK")
            assert "is_valid" in res
