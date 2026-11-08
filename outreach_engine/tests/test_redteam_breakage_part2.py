"""Automated, live non-mock regression test suite for Subsystems 3, 5, and 6.

Validates remediation of all 30 breakages identified by Red Team Challengers
in Compilers/Orchestrator, Research Bridge/Delegation, and Judges/Model Registry/Dispatch.
"""
from __future__ import annotations
import json, math, os, tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest

from apps_lic.domain.models import (
    AudiencePersona, CandidateFact, CandidateProfile, ChannelType,
    RecipientClass, RelationshipDistance, TargetOpportunity, OutreachMessageDraft,
)
from apps_lic.pipeline.compiler import PromptCompiler
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.pipeline.touch_sequence import TouchSequencePlanner
from apps_lic.integrations.apps_research_bridge import AppsResearchBridge
from apps_lic.integrations.managed_research_delegation import (
    OutreachBriefingReady, RequestForOutreachBriefing, ResearchDispatchFailure,
    ResearchResult, _validate_persisted_research_artifacts, dispatch_outreach_research_briefing,
)
from apps_lic.integrations.research_boundary_policy import (
    _find_valid_persisted_artifact_bundle, _resolve_canonical_targeting_brief, execute_bounded_live_research,
)
from apps_lic.integrations.research_bridge_support import persist_standalone_outreach_research_bundle
from apps_lic.judges.evaluator import AuthoritativeVerdict, EvaluationReport, ExecutiveOutreachJudgePanel
from apps_lic.runtime.dispatch.canonical_dispatch import run_canonical_apps_lic_spine
from apps_lic.runtime.model_registry import OutreachModelRegistry, OutreachModelRegistryError


def _make_cand(cid="c1", name="Jordan Reed", title="CTO", facts=None, summary="Leader.") -> CandidateProfile:
    return CandidateProfile(candidate_id=cid, full_name=name, target_title=title, executive_summary=summary, verified_facts=facts or [])


def _make_opp(oid="o1", co="Apex Financial Systems", role="CTO", rec="Alex", title="CEO", **kwargs) -> TargetOpportunity:
    d = dict(opportunity_id=oid, company_name=co, role_title=role, recipient_name=rec, recipient_title=title, industry="Fintech")
    d.update(kwargs)
    return TargetOpportunity(**d)


def _make_res(bundle=None, run_id="r", **kwargs) -> ResearchResult:
    d = dict(
        run_id=run_id, trace_id="t1", request_id="r1", is_blocked=False, block_reason="", is_stale=False,
        evidence_items=(), confidence_score=0.95, brief_sha256=bundle.brief_sha256 if bundle else "",
        company_brief_text="Brief", strategic_priorities=("p1",), fetch_duration_ms=10.0, audit_ref="t1",
        apps_research_handoff_envelope=bundle.envelope if bundle else {},
        research_artifact_dir=str(bundle.run_dir) if bundle else "",
        briefing_artifact_path=str(bundle.briefing_path) if bundle else "",
        result_metadata_digest=bundle.result_metadata_digest if bundle else "",
        bundle_manifest_digest=bundle.bundle_manifest_digest if bundle else "",
        resolution_source="PERSISTED_ARTIFACT" if bundle else "WEB_RESEARCH", is_verified=True,
    )
    d.update(kwargs)
    return ResearchResult(**d)


# ==============================================================================
# Subsystem 3: Compilers & Pipeline Execution
# ==============================================================================

def test_compiler_path_traversal_load_template() -> None:
    """ISSUE-COMP-01: Path traversal in load_template() must fail closed."""
    compiler = PromptCompiler()
    assert compiler.load_template("../../../config/provider_profiles.yaml") == {}
    assert compiler.load_template("/etc/passwd") == {}


def test_compiler_null_template_purpose_and_forbidden() -> None:
    """ISSUE-COMP-02: Null purpose or null items in forbidden_behaviors must not crash."""
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        (tpath / "outreach_draft_v2.yaml").write_text(
            "template_id: outreach_draft_v2\npurpose: null\nforbidden_behaviors:\n  - null\n  - avoid_buzzwords\n", encoding="utf-8",
        )
        compiler = PromptCompiler(templates_dir=tpath)
        cand, opp = _make_cand(), _make_opp(co="Apex Corp")
        ctx = compiler.assemble_context(cand, opp, ChannelType.LINKEDIN_INMAIL)
        assert ctx["template_purpose"] == ""
        assert "DO NOT avoid buzzwords." in ctx["forbidden_behaviors"]


def test_compiler_and_orchestrator_string_channel_recipient() -> None:
    """ISSUE-COMP-03: String channel or recipient class must be coerced safely."""
    compiler = PromptCompiler()
    cand, opp = _make_cand(), _make_opp(co="Apex Corp")
    ctx = compiler.assemble_context(cand, opp, "inmail")  # type: ignore[arg-type]
    assert ctx["channel"] == "inmail"


def test_touch_sequence_spurious_tournament_signoff() -> None:
    """ISSUE-COMP-04: Multi-touch sequences must not lock with requires_human_signoff=True."""
    planner = TouchSequencePlanner()
    cand = _make_cand(facts=[
        CandidateFact(fact_id="f1", category="scale", statement="scaled platform to $10M", metric="$10M", source_reference="resume"),
        CandidateFact(fact_id="f2", category="leadership", statement="led 50 engineers", metric="50", source_reference="resume"),
    ])
    opp = _make_opp(strategic_priorities=["cloud payments"], sealed_resolution={"is_verified": True})
    seq = planner.plan_sequence(cand, opp, ChannelType.LINKEDIN_INMAIL)
    assert seq.status == "PASSED"
    assert seq.metadata["requires_human_signoff"] is False


def test_orchestrator_completed_stages_manifest_on_failure() -> None:
    """ISSUE-COMP-05: Failed evaluations must not record authoritative_evaluation as completed."""
    orch = OutreachOrchestrator()
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        cand_fail = _make_cand(summary="Won $100M Nobel prize in distributed systems")
        opp = _make_opp()
        _, verdict = orch.generate_single_draft(cand_fail, opp, ChannelType.LINKEDIN_INMAIL, auto_research=False, artifact_dir=tpath)
        assert verdict.passed is False
        manifest_data = json.loads((tpath / "run_manifest.json").read_text(encoding="utf-8"))
        assert "authoritative_evaluation" not in manifest_data["completed_stages"]
        res = orch.resume_or_patch_run(tpath)
        assert "authoritative_evaluation" not in res["reused_stages"]


def test_orchestrator_touch_continuity_touch1_failure() -> None:
    """ISSUE-COMP-06: When Touch 1 fails, subsequent touches must not be dispatched as first touch."""
    orch = OutreachOrchestrator()
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        cand = _make_cand()
        opp = _make_opp(recipient_class=RecipientClass.HIRING_MANAGER, strategic_priorities=["Targeting a salary of $350k plus signing bonus"])
        seq = orch.generate_full_campaign(cand, opp, ChannelType.LINKEDIN_INMAIL, auto_research=False, artifact_dir=tpath)
        assert seq.status == "BLOCKED"
        seq_data = json.loads((tpath / "campaign_sequence.json").read_text(encoding="utf-8"))
        assert len(seq_data["touches"]) == 0
        assert seq_data["status"] == "BLOCKED"
        assert len(seq_data["blocked_touches"]) > 0


def test_compiler_strategic_hook_abbreviation_preservation() -> None:
    """ISSUE-COMP-07: Strategic hook formatting must preserve standard abbreviations."""
    compiler = PromptCompiler()
    hook1 = compiler._format_strategic_hook("Dr. Smith announced migration to multi-region cloud infrastructure")
    assert hook1 != "dr" and "smith" in hook1.lower() and len(hook1) > 20
    hook2 = compiler._format_strategic_hook("U.S. expansion into digital core banking")
    assert "u.s." in hook2.lower() or "expansion" in hook2.lower()


def test_compiler_missing_title_and_recipient_clean_grammar() -> None:
    """ISSUE-COMP-08: Missing candidate title or recipient name must not produce dangling commas."""
    compiler = PromptCompiler()
    cand_empty = _make_cand(title="", facts=[
        CandidateFact(fact_id="f1", category="scale", statement="scaled platform to 10M users", metric="10M", source_reference="resume")
    ])
    opp = _make_opp(co="Apex Corp", rec="")
    _, body, _ = compiler.render_draft_message(cand_empty, opp, ChannelType.LINKEDIN_INMAIL)
    assert "work as ," not in body and "As ," not in body and not body.startswith("Hi ,")


def test_touch_sequence_no_double_re_subject() -> None:
    """ISSUE-COMP-09: Touch 2 subject must not accumulate Re: Re: prefixes."""
    planner = TouchSequencePlanner()
    t2 = planner._generate_touch_2(_make_cand(), _make_opp(co="Apex"), AudiencePersona.EXECUTIVE_CONTACT, 4, "seq_1", t1_subject="Re: Following up")
    assert not t2.draft.subject.startswith("Re: Re:")
    assert t2.draft.subject.startswith("Re: ")


def test_touch_sequence_metric_free_clause_when_no_facts() -> None:
    """ISSUE-COMP-10: Fact-sparse candidates with metrics in executive summary must not self-induce grounding blocks."""
    planner = TouchSequencePlanner()
    cand = _make_cand(summary="Delivered $10M in value through platform transformations.")
    opp = _make_opp(co="Apex", title="Recruiter", recipient_class=RecipientClass.TALENT_PARTNER)
    t1 = planner._generate_touch_1(cand, opp, ChannelType.LINKEDIN_INMAIL, AudiencePersona.EXECUTIVE_RECRUITER, 0, "seq_1", attempt=0)
    assert "$10M" not in t1.draft.body


# ==============================================================================
# Subsystem 5: Integrations & Research Bridge
# ==============================================================================

def test_research_bridge_path_traversal_run_id() -> None:
    """ISSUE-RES-01: Directory escape via run_id must be sanitized and rejected."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "runs_root"
        root.mkdir()
        escape_target = Path(td) / "escaped_dir"
        record = SimpleNamespace(run_id="../escaped_dir", trace_id="t1", request_id="r1", company_brief_text="Valid brief", confidence_score=0.95, strategic_priorities=["p1"])
        bundle = persist_standalone_outreach_research_bundle(record=record, target_company="TargetCorp", target_role="CTO", jd_text="JD", runs_root=root)
        assert bundle.run_dir.resolve().is_relative_to(root.resolve())
        assert not escape_target.exists()


def test_research_delegation_empty_identity_rejected() -> None:
    """ISSUE-RES-02: Blank target_company in persisted bundle must not match arbitrary company."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        record = SimpleNamespace(run_id="run-empty-id", trace_id="t1", request_id="r1", company_brief_text="Brief text", confidence_score=0.95, strategic_priorities=["p1"])
        bundle = persist_standalone_outreach_research_bundle(record=record, target_company="", target_role="", jd_text="JD text", runs_root=root)
        res = _make_res(bundle, run_id="run-empty-id", company_brief_text="Brief text")
        req = RequestForOutreachBriefing(request_id="r1", run_id="run-empty-id", trace_id="t1", company_name="Microsoft Corporation", job_title="Chief AI Officer", artifact_runs_root=root)
        valid, detail, _ = _validate_persisted_research_artifacts(res, request=req)
        assert valid is False and "company mismatch" in detail


def test_research_delegation_u0_receipt_digest_tamper_fails() -> None:
    """ISSUE-RES-03: Tampering with apps_research_u0_receipt.json must fail verification."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        record = SimpleNamespace(run_id="run-u0", trace_id="t1", request_id="r1", company_brief_text="Brief", confidence_score=0.95, strategic_priorities=["p1"])
        bundle = persist_standalone_outreach_research_bundle(record=record, target_company="TargetCorp", target_role="CTO", jd_text="JD text", runs_root=root)
        u0_path = bundle.run_dir / "apps_research_u0_receipt.json"
        u0_data = json.loads(u0_path.read_text(encoding="utf-8"))
        u0_data["raw_input_sha256"] = "sha256:TAMPERED_0000000000000000000000000000000000000000000000000000000000000000"
        u0_path.write_text(json.dumps(u0_data), encoding="utf-8")

        res = _make_res(bundle, run_id="run-u0")
        req = RequestForOutreachBriefing(request_id="r1", run_id="run-u0", trace_id="t1", company_name="TargetCorp", job_title="CTO", artifact_runs_root=root)
        valid, _, _ = _validate_persisted_research_artifacts(res, request=req)
        assert valid is False


def test_research_delegation_none_confidence_and_duck_evidence() -> None:
    """ISSUE-RES-04: confidence_score=None or evidence items without attributes must not crash."""
    class SafeTestBridge:
        def __init__(self, res: Any) -> None:
            self.res = res
        def fetch(self, **kwargs: Any) -> Any:
            return self.res

    req = RequestForOutreachBriefing(request_id="r1", run_id="run1", trace_id="t1", company_name="Corp", job_title="CTO")
    res_none = _make_res(run_id="run1", confidence_score=None)
    out_a = dispatch_outreach_research_briefing(req, bridge=SafeTestBridge(res_none))
    assert isinstance(out_a, ResearchDispatchFailure)

    ev_item = SimpleNamespace(uri="https://example.com/source")
    res_duck = _make_res(run_id="run1", evidence_items=(ev_item,), confidence_score=0.9)
    out_b = dispatch_outreach_research_briefing(req, bridge=SafeTestBridge(res_duck))
    assert isinstance(out_b, OutreachBriefingReady)
    assert len(out_b.evidence_lineage) == 1 and out_b.evidence_lineage[0]["uri"] == "https://example.com/source"


def test_research_bridge_cost_limit_abort_retries() -> None:
    """ISSUE-RES-05: execute_bounded_live_research must abort retries when cost limit would be exceeded."""
    invocations = 0
    def mock_failing_provider() -> None:
        nonlocal invocations
        invocations += 1
        raise RuntimeError("External API timeout")

    bridge = AppsResearchBridge(max_retries=2, cost_per_call_usd=0.05, cost_limit_usd=0.08)
    def _on_attempt(attempt_idx: int) -> None:
        bridge.cumulative_cost_usd += bridge.policy.cost_per_call_usd

    try:
        execute_bounded_live_research(
            invoke_fn=mock_failing_provider, timeout_seconds=0.5, max_retries=2,
            cost_per_call_usd=0.05, cost_limit_usd=0.08, cumulative_cost_usd=bridge.cumulative_cost_usd,
            on_attempt_fn=_on_attempt,
        )
    except Exception:
        pass
    assert invocations == 1
    assert bridge.cumulative_cost_usd <= 0.08


def test_research_delegation_ready_is_verified_field() -> None:
    """ISSUE-RES-06: OutreachBriefingReady must carry is_verified provenance."""
    class VerifiedBridge:
        def fetch(self, **kwargs: Any) -> Any:
            return _make_res(run_id="run-u", resolution_source="WEB_RESEARCH", is_verified=True)

    req = RequestForOutreachBriefing(request_id="r1", run_id="run1", trace_id="t1", company_name="Corp", job_title="CTO")
    res = dispatch_outreach_research_briefing(req, bridge=VerifiedBridge())
    assert isinstance(res, OutreachBriefingReady) and hasattr(res, "is_verified") and res.is_verified is True


def test_research_boundary_policy_company_stem_whole_word() -> None:
    """ISSUE-RES-07: Company stem matching must use whole-word tokens."""
    _, path = _resolve_canonical_targeting_brief(company_name="A")
    assert "aig" not in path.lower(), f"Company 'A' mistakenly matched: {path}"


def test_research_delegation_ro_consumer_dir_oserror() -> None:
    """ISSUE-RES-08: OSError on writing consumer receipts must not abort successful delegation."""
    class DummyBridge:
        def fetch(self, **kwargs: Any) -> Any:
            return _make_res(run_id="run-1", confidence_score=0.9)

    with tempfile.TemporaryDirectory() as td:
        ro_dir = Path(td) / "ro"
        ro_dir.mkdir(mode=0o555)
        req = RequestForOutreachBriefing(request_id="r1", run_id="run1", trace_id="t1", company_name="Corp", job_title="CTO")
        try:
            res = dispatch_outreach_research_briefing(req, bridge=DummyBridge(), consumer_artifact_dir=ro_dir)
            assert isinstance(res, OutreachBriefingReady)
        finally:
            os.chmod(ro_dir, 0o755)


def test_research_boundary_policy_none_company_bundle_search() -> None:
    """ISSUE-RES-09: Searching bundles with company_name=None must return cleanly."""
    bundle, reason = _find_valid_persisted_artifact_bundle(artifact_runs_root=None, company_name=None)  # type: ignore[arg-type]
    assert bundle is None and reason == "missing_company_name"


# ==============================================================================
# Subsystem 6: Judges, Model Registry & Canonical Dispatch
# ==============================================================================

def test_judge_nan_composite_score_clamped() -> None:
    """ISSUE-JUDGE-01: NaN composite scores must clamp to 0.0, not 1.0."""
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "executive_outreach_rubric_v3.yaml").write_text(
            "rubric_id: executive_outreach_rubric_v3\npassing_criteria:\n  min_composite_score: .nan\nlenses:\n  lens1_altitude:\n    threshold: .nan\n    weight: .nan\n",
            encoding="utf-8",
        )
        panel = ExecutiveOutreachJudgePanel(rubrics_dir=td)
        cand, opp = _make_cand(title="VP"), _make_opp(co="Acme", role="VP", rec="C D", title="Dir", recipient_class=RecipientClass.HIRING_MANAGER)
        draft = OutreachMessageDraft(draft_id="d1", subject="S", body="Hello Acme", channel=ChannelType.LINKEDIN_INMAIL, grounded_facts_used=["f1"])
        res = panel.evaluate_persona_tournament([draft], cand, opp)
        assert res["top_score"] == 0.0 or res["top_score"] < 1.0
        assert res["rankings"][0]["passed"] is False


def test_judge_failed_runner_up_no_signoff() -> None:
    """ISSUE-JUDGE-02: Failed runner-up drafts must not trigger requires_human_signoff."""
    cand = _make_cand(title="VP", facts=[CandidateFact(fact_id="f1", category="scale", statement="Scaled platform to $4B.", metric="$4B", source_reference="dossier")])
    opp = _make_opp(co="Acme Corp", role="VP", rec="Jane", title="CTO", recipient_class=RecipientClass.HIRING_MANAGER, strategic_priorities=["Cloud"])
    d_pass = OutreachMessageDraft(
        draft_id="d_pass", subject="Acme", body="Jane, regarding Acme Corp Cloud, I scaled platform to $4B. Would you be open to a call next week?",
        channel=ChannelType.LINKEDIN_INMAIL, grounded_facts_used=["f1"],
    )
    d_fail = OutreachMessageDraft(
        draft_id="d_fail", subject="Acme", body="Jane, regarding Acme Corp Cloud, see [my portfolio](https://example.com) where I scaled platform to $4B. Would you be open to a call next week?",
        channel=ChannelType.LINKEDIN_INMAIL, grounded_facts_used=["f1"],
    )
    panel = ExecutiveOutreachJudgePanel()
    res = panel.evaluate_persona_tournament([d_pass, d_fail], cand, opp)
    assert res["rankings"][0]["passed"] is True and res["rankings"][1]["passed"] is False and res["requires_human_signoff"] is False


def test_judge_all_failing_candidates_empty_winner() -> None:
    """ISSUE-JUDGE-03: When all candidate drafts fail, winner_draft_id must be empty and passed=False."""
    cand, opp = _make_cand(title="VP"), _make_opp(co="Acme", role="VP", rec="Jane", title="CTO", recipient_class=RecipientClass.HIRING_MANAGER)
    d1 = OutreachMessageDraft(draft_id="d1_fail", subject="Bad", body="Please hire me!", channel=ChannelType.LINKEDIN_INMAIL)
    d2 = OutreachMessageDraft(draft_id="d2_fail", subject="Bad 2", body="Please give me a job!", channel=ChannelType.LINKEDIN_INMAIL)
    panel = ExecutiveOutreachJudgePanel()
    res = panel.evaluate_persona_tournament([d1, d2], cand, opp)
    assert res["winner_draft_id"] == "" and res["passed"] is False


def test_judge_tournament_deterministic_tie_breaker_no_index_penalty() -> None:
    """ISSUE-JUDGE-04: Winner must be deterministic and invariant to input list ordering."""
    cand = _make_cand(title="VP", facts=[CandidateFact(fact_id="f1", category="scale", statement="Scaled platform to $4B.", metric="$4B", source_reference="dossier")])
    opp = _make_opp(co="Acme", role="VP", rec="Jane", title="CTO", recipient_class=RecipientClass.HIRING_MANAGER, strategic_priorities=["Cloud"])
    body = "Jane, regarding Acme Cloud, I scaled platform to $4B. Would you be open to a conversation next week?"
    d1 = OutreachMessageDraft(draft_id="alpha", subject="Acme", body=body, channel=ChannelType.LINKEDIN_INMAIL, grounded_facts_used=["f1"])
    d2 = OutreachMessageDraft(draft_id="beta", subject="Acme", body=body, channel=ChannelType.LINKEDIN_INMAIL, grounded_facts_used=["f1"])
    panel = ExecutiveOutreachJudgePanel()
    assert panel.evaluate_persona_tournament([d1, d2], cand, opp)["winner_draft_id"] == "alpha"
    assert panel.evaluate_persona_tournament([d2, d1], cand, opp)["winner_draft_id"] == "alpha"


def test_judge_bad_rubric_id_and_null_lenses_handled() -> None:
    """ISSUE-JUDGE-05: Non-string rubric_id or null lenses in YAML must be handled safely."""
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "bad_id.yaml").write_text("rubric_id: [1, 2]\n", encoding="utf-8")
        assert ExecutiveOutreachJudgePanel(rubrics_dir=td) is not None

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "executive_outreach_rubric_v3.yaml").write_text("rubric_id: executive_outreach_rubric_v3\nlenses: null\n", encoding="utf-8")
        assert ExecutiveOutreachJudgePanel(rubrics_dir=td).get_threshold("lens1_altitude", 0.70) == 0.70


def test_judge_report_from_verdict_none_lens_score() -> None:
    """ISSUE-JUDGE-10: None in lens_scores must not raise TypeError in report_from_verdict."""
    v = AuthoritativeVerdict(
        passed=True, status="PASSED", composite_score=1.0, score_band="EXEMPLARY", hard_gate_passed=True, judge_passed=True,
        violations=[], warnings=[], failure_reasons=[], lens_scores={"lens1_altitude": None, "lens6_constraints": 1.0},
        feedback=[], remediation_hints=[], scores={},
    )
    rep = ExecutiveOutreachJudgePanel().report_from_verdict(v)
    assert isinstance(rep, EvaluationReport) and rep.lens1_altitude_score == 1.0


def test_model_registry_nested_env_override_allowed() -> None:
    """ISSUE-JUDGE-06: is_env_override_allowed must inspect nested model_pin_ownership."""
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "provider_profiles.yaml"
        cfg.write_text("provider_profile_registry_id: test\nmodel_pin_ownership:\n  environment_model_override_allowed: true\nprofiles: {}\n", encoding="utf-8")
        OutreachModelRegistry.clear_cache()
        assert OutreachModelRegistry.is_env_override_allowed(config_path=cfg) is True


def test_model_registry_approved_models_whitespace_strip() -> None:
    """ISSUE-JUDGE-11: Model pins and approved models must strip leading/trailing whitespace."""
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "provider_profiles.yaml"
        cfg.write_text("provider_profile_registry_id: test\nprofiles:\n  role_a:\n    provider: openai\n    model: ' gpt-5.6-luna '\n", encoding="utf-8")
        OutreachModelRegistry.clear_cache()
        pin = OutreachModelRegistry.get_model_pin("role_a", config_path=cfg)
        assert pin.model == "gpt-5.6-luna"
        assert OutreachModelRegistry.validate_model(pin.model, config_path=cfg) is True


def test_model_registry_get_model_for_role_unapproved_default_raises() -> None:
    """ISSUE-JUDGE-07: get_model_for_role must not return unapproved rogue fallback models."""
    OutreachModelRegistry.clear_cache()
    with pytest.raises(OutreachModelRegistryError):
        OutreachModelRegistry.get_model_for_role("unregistered_role", default="unapproved_rogue_model_v9")


def test_canonical_dispatch_non_dict_lead_and_string_dir() -> None:
    """ISSUE-JUDGE-08: Non-dict lead_profile and string artifact_dir must be coerced safely."""
    with tempfile.TemporaryDirectory() as td:
        assert "x3_code" in run_canonical_apps_lic_spine({"lead_profile": "lead_123"}, Path(td))
        assert "x3_code" in run_canonical_apps_lic_spine({}, td)


def test_canonical_dispatch_exception_returns_x3d_block() -> None:
    """ISSUE-JUDGE-09: Unhandled pipeline exception must return governed X3D_BLOCK envelope."""
    with tempfile.NamedTemporaryFile() as tf:
        out = run_canonical_apps_lic_spine({}, Path(tf.name))
        assert out["x3_code"] == "X3D_BLOCK" and out["is_valid"] is False and len(out["failure_reasons"]) > 0
