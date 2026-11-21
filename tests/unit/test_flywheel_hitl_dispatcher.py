"""Unmocked unit tests for agents.learning.flywheel_hitl_dispatcher (Wave 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.learning.eligibility import validate_learning_approval_origin
from agents.learning.flywheel_hitl_dispatcher import (
    dispatch_cycle_remediation,
    build_atomic_remediation_question,
    execute_approved_tier_b_commit,
    record_remediation_decision,
)
from agents.learning.merkle_seal import verify_merkle_seal
from agents.learning.proposal_generator import build_signed_provenance
from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.digests import sha256_file
from apps_eval.contracts.schemas import EvalCase, FailureCluster, HoldoutReplayVerdict, ImprovementProposal
from apps_eval.triage_promoter import promote_golden_cases
from tools.hitl_governance import (
    MAX_OPTION_LENGTH,
    MAX_QUESTION_LENGTH,
    HITLDecisionStore,
    evaluate_hitl_surfacing_gate,
    scan_question_jargon,
    validate_hitl_presentation,
)
from tools.hook_dispatch import _is_mandatory_hitl_question, handle_pre_ask_question

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_tier_b_proposal(target_path: str = "config/prompt_governance/priors.yaml") -> ImprovementProposal:
    pid = "prop-tier-b-001"
    return ImprovementProposal(
        proposal_id=pid,
        cluster_id="clst-tier-b-1",
        artifact_class="prompt_prior",
        autonomy_tier="TIER_B_HITL_GATED",
        risk_lane="LANE_1",
        target_path=target_path,
        target_key="outreach.tone_prior",
        expected_current_value="concise",
        proposed_value_or_patch="executive_concise",
        step_delta_magnitude=0.0,
        evidence_trace_ids=["trace-b1", "trace-b2", "trace-b3"],
        source_receipt_digests=["r" * 64],
        provenance_digest=build_signed_provenance(
            proposal_id=pid,
            evidence_trace_ids=["trace-b1", "trace-b2", "trace-b3"],
            source_receipt_digests=["r" * 64],
            proposed_change={"key": "outreach.tone_prior", "value": "executive_concise"},
            evaluation_plan=["locked_holdout_replay", "lp5_canary"],
        ),
        evaluation_plan=["locked_holdout_replay", "lp5_canary"],
        status="PROPOSED",
        expires_at_utc="2026-12-31T00:00:00Z",
    )


def _make_tier_c_proposal() -> ImprovementProposal:
    pid = "prop-tier-c-001"
    patch = {"action": "open_pr_for_root_cause_fix", "owner_subsystem": "resume_graph_engine"}
    return ImprovementProposal(
        proposal_id=pid,
        cluster_id="clst-tier-c-1",
        artifact_class="validator_or_code",
        autonomy_tier="TIER_C_PR_ONLY",
        risk_lane="LANE_2",
        target_path="resume_graph_engine/src/apps_rg/runtime/validators/x2.py",
        target_key=None,
        expected_current_value=None,
        proposed_value_or_patch=patch,
        step_delta_magnitude=0.0,
        evidence_trace_ids=["trace-c1", "trace-c2"],
        source_receipt_digests=["c" * 64],
        provenance_digest=build_signed_provenance(
            proposal_id=pid,
            evidence_trace_ids=["trace-c1", "trace-c2"],
            source_receipt_digests=["c" * 64],
            proposed_change=patch,
            evaluation_plan=["isolated_worktree_fix", "pr_governance_readiness"],
        ),
        evaluation_plan=["isolated_worktree_fix", "pr_governance_readiness"],
        status="PROPOSED",
        expires_at_utc="2026-12-31T00:00:00Z",
    )


def _make_tier_a_proposal(proposed_val: float = 0.75) -> ImprovementProposal:
    pid = "prop-tier-a-001"
    return ImprovementProposal(
        proposal_id=pid,
        cluster_id="clst-tier-a-1",
        artifact_class="bounded_threshold",
        autonomy_tier="TIER_A_AUTO_APPLY",
        risk_lane="LANE_1",
        target_path="config/routing_calibration.yaml",
        target_key="v12_routing.classifier_surface_threshold",
        expected_current_value=0.72,
        proposed_value_or_patch=proposed_val,
        step_delta_magnitude=round(abs(proposed_val - 0.72), 4),
        evidence_trace_ids=["trace-a1", "trace-a2", "trace-a3"],
        source_receipt_digests=["a" * 64],
        provenance_digest=build_signed_provenance(
            proposal_id=pid,
            evidence_trace_ids=["trace-a1", "trace-a2", "trace-a3"],
            source_receipt_digests=["a" * 64],
            proposed_change={"key": "v12_routing.classifier_surface_threshold", "value": proposed_val},
            evaluation_plan=["target_cluster_replay", "locked_holdout_replay"],
        ),
        evaluation_plan=["target_cluster_replay", "locked_holdout_replay"],
        status="PROPOSED",
        expires_at_utc="2026-12-31T00:00:00Z",
    )


def _make_pass_verdict(prop: ImprovementProposal) -> HoldoutReplayVerdict:
    return HoldoutReplayVerdict(
        verdict_id=f"hrv-{prop.proposal_id}",
        proposal_id=prop.proposal_id,
        proposal_digest=prop.canonical_digest,
        dataset_digest="d" * 64,
        zero_mutation_verified=True,
        unlabeled_view_enforced=True,
        target_cluster_cases=4,
        target_metric_before=0.50,
        target_metric_after=1.00,
        holdout_cases_evaluated=5,
        holdout_accuracy_before=0.80,
        holdout_accuracy_after=0.95,
        holdout_accuracy_delta=0.15,
        pinned_regressions_passed=True,
        veto_regressions_count=0,
        pareto_regression=False,
        latency_delta_pct=0.0,
        cost_delta_pct=0.0,
        verdict="PASS",
    )


def test_build_atomic_remediation_question_strips_jargon_and_enforces_caps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    q_store = SqliteFindingsQueueStore(tmp_path / "queue.sqlite")
    try:
        jargon_finding = q_store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_rg",
            failed_gate_signature="x2_gates_passed,trajectory_healthy",
            root_cause_bucket="apps_rg_snake_case_defect",
            owner_subsystem="resume_graph_engine",
            track="TRACK_2_CODE_FIX",
            priority="P0",
            title="HITL O2 SQL SELECT * FROM eval_findings in resume_graph_engine/x2.py --no-verify Candidate ID: c1... ExecutiveVoiceRepairAgent?",
            summary="WAL SSOT telemetry schema payload ratchet invariant failed.",
            recommended_action="Fix snake_case_symbol in tools/foo.py",
            occurrence_count=6,
            target_files=["resume_graph_engine/src/apps_rg/runtime/validators/x2.py"],
        )
        for prop, margin in (
            (_make_tier_c_proposal(), 0.35),
            (_make_tier_b_proposal(), 0.35),
            (_make_tier_a_proposal(), 0.14),
        ):
            payload = build_atomic_remediation_question(
                jargon_finding,
                prop,
                _make_pass_verdict(prop),
                confidence_margin=margin,
            )
            assert len(payload["questions"]) == 1
            q_obj = payload["questions"][0]
            assert len(q_obj["question"]) <= MAX_QUESTION_LENGTH
            assert len(q_obj["options"]) == 3
            assert all(len(opt) <= MAX_OPTION_LENGTH for opt in q_obj["options"])
            assert scan_question_jargon(q_obj["question"]) == []
            assert validate_hitl_presentation(payload, enforce_visibility_and_jargon=True) == []
            assert payload["metadata"]["finding_digest"] == jargon_finding.finding_digest
            assert payload["metadata"]["proposal_digest"] == prop.canonical_digest
            if prop.autonomy_tier in ("TIER_B_HITL_GATED", "TIER_C_PR_ONLY"):
                assert _is_mandatory_hitl_question(q_obj["question"], q_obj, payload) is True
            if prop.autonomy_tier == "TIER_A_AUTO_APPLY":
                gate = evaluate_hitl_surfacing_gate(q_obj["options"])
                assert gate["should_surface"] is True
                assert gate["margin"] <= 0.20
            rc = handle_pre_ask_question({"toolCall": {"args": {"questions": payload["questions"]}}}, REPO_ROOT)
            assert rc == 0
            hook_out = capsys.readouterr().out
            assert '"allow"' in hook_out, hook_out
    finally:
        q_store.close()


def test_tier_b_approval_emits_commit_engine_receipt_and_executes_canary(tmp_path: Path) -> None:
    q_store = SqliteFindingsQueueStore(tmp_path / "queue.sqlite")
    h_store = HITLDecisionStore(tmp_path / "hitl.sqlite")
    ledger = SqliteLearningLedgerStore(tmp_path / "ledger.sqlite")
    prior_file = tmp_path / "priors.yaml"
    prior_file.write_text("outreach:\n  tone_prior: concise\n", encoding="utf-8")
    try:
        finding = q_store.upsert_finding(
            source_surface="hitl_override",
            app_id="apps_lic",
            failed_gate_signature="hitl_override:tone",
            root_cause_bucket="outreach_tone_prior",
            owner_subsystem="outreach_engine",
            track="TRACK_1_CALIBRATION",
            priority="P1",
            title="Recurring tone override in outreach writer",
            summary="3 operator overrides recorded.",
            recommended_action="Update tone_prior to executive_concise.",
            occurrence_count=3,
        )
        prop_b = _make_tier_b_proposal()
        verdict_b = _make_pass_verdict(prop_b)
        q_payload = build_atomic_remediation_question(finding, prop_b, verdict_b)

        action = record_remediation_decision(
            finding.finding_id,
            prop_b,
            q_payload["questions"][0]["options"][0],
            q_store,
            h_store,
            approved_by="amit",
            expected_finding_digest=finding.finding_digest,
            expected_proposal_digest=prop_b.canonical_digest,
            question_payload=q_payload,
            repo_root=REPO_ROOT,
        )
        assert action.action == "EXECUTE_TIER_B_COMMIT"
        assert action.finding_status == "APPROVED"
        assert action.approval_receipt is not None
        ok_orig, msg_orig = validate_learning_approval_origin(action.approval_receipt)
        assert ok_orig, msg_orig

        res = execute_approved_tier_b_commit(
            action=action,
            proposal=prop_b,
            holdout_verdict=verdict_b,
            repo_root=REPO_ROOT,
            ledger_store=ledger,
            queue_store=q_store,
            hitl_store=h_store,
            rollback_dir=tmp_path / "rollbacks",
            seals_dir=tmp_path / "seals",
            canary_metrics={"quality_score": 0.96, "veto_defects": 0, "latency_ms": 50.0, "pinned_regressions_passed": True},
            baseline_metrics={"quality_score": 0.80},
            target_file_override=prior_file,
        )
        assert res["canary"]["status"] == "APPLIED_AND_SEALED"
        assert verify_merkle_seal(res["canary"]["merkle_seal"]) is True
        assert "executive_concise" in prior_file.read_text(encoding="utf-8")
        assert q_store.get_finding(finding.finding_id).status == "VERIFIED"
        assert h_store.get_calibration_metrics()["outcomes"].get("SUCCESS") == 1
    finally:
        ledger.close()
        h_store.close()
        q_store.close()


def test_tier_c_approval_transitions_open_approved_in_progress_and_emits_worktree_packet(tmp_path: Path) -> None:
    q_store = SqliteFindingsQueueStore(tmp_path / "queue.sqlite")
    h_store = HITLDecisionStore(tmp_path / "hitl.sqlite")
    try:
        finding = q_store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_rg",
            failed_gate_signature="x2_gates_passed",
            root_cause_bucket="apps_rg_x2_grounding",
            owner_subsystem="resume_graph_engine",
            track="TRACK_2_CODE_FIX",
            priority="P0",
            title="Ungrounded claim passed validation",
            summary="X2 grounding check missed an ungrounded bullet.",
            recommended_action="Fix grounding check in x2.py.",
            occurrence_count=4,
            target_files=["resume_graph_engine/src/apps_rg/runtime/validators/x2.py"],
        )
        prop_c = _make_tier_c_proposal()
        q_payload = build_atomic_remediation_question(finding, prop_c)

        action = record_remediation_decision(
            finding.finding_id,
            prop_c,
            q_payload["questions"][0]["options"][0],
            q_store,
            h_store,
            approved_by="amit",
            expected_finding_digest=finding.finding_digest,
            expected_proposal_digest=prop_c.canonical_digest,
            question_payload=q_payload,
            repo_root=REPO_ROOT,
        )
        assert action.action == "EXECUTE_TIER_C_FIX_AND_PROMOTE"
        assert action.finding_status == "IN_PROGRESS"
        assert action.worktree_execution_packet is not None
        assert "resume_graph_engine/src/apps_rg/runtime/validators/x2.py" in action.worktree_execution_packet["target_files"]
        assert "apps_eval/suites/pinned_fix_regressions.json" in action.worktree_execution_packet["required_regression_pins"]

        events = q_store.list_events(finding.finding_id)
        transitions = [(e["from_status"], e["to_status"]) for e in events]
        assert (None, "OPEN") in transitions
        assert ("OPEN", "APPROVED") in transitions
        assert ("APPROVED", "IN_PROGRESS") in transitions
    finally:
        h_store.close()
        q_store.close()


def test_snooze_reject_and_cryptographic_or_synthetic_rejections(tmp_path: Path) -> None:
    q_store = SqliteFindingsQueueStore(tmp_path / "queue.sqlite")
    h_store = HITLDecisionStore(tmp_path / "hitl.sqlite")
    try:
        f_snooze = q_store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_rg",
            failed_gate_signature="x2_gates_passed",
            root_cause_bucket="bucket_snooze",
            owner_subsystem="resume_graph_engine",
            track="TRACK_2_CODE_FIX",
            priority="P1",
            title="Snoozeable defect",
            summary="Test snooze",
            recommended_action="Fix later",
            occurrence_count=2,
        )
        f_reject = q_store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_lic",
            failed_gate_signature="x2_gates_passed",
            root_cause_bucket="bucket_reject",
            owner_subsystem="outreach_engine",
            track="TRACK_2_CODE_FIX",
            priority="P2",
            title="Rejectable defect",
            summary="Test reject",
            recommended_action="Ignore",
            occurrence_count=2,
        )
        prop_c = _make_tier_c_proposal()

        res_snooze = record_remediation_decision(
            f_snooze.finding_id,
            prop_c,
            "Snooze for 7 days",
            q_store,
            h_store,
            approved_by="amit",
            repo_root=REPO_ROOT,
        )
        assert res_snooze.action == "SNOOZED"
        assert res_snooze.finding_status == "SNOOZED"
        assert res_snooze.snoozed_until_utc is not None

        res_reject = record_remediation_decision(
            f_reject.finding_id,
            prop_c,
            "Reject and archive",
            q_store,
            h_store,
            approved_by="amit",
            repo_root=REPO_ROOT,
        )
        assert res_reject.action == "REJECTED"
        assert res_reject.finding_status == "REJECTED"
        assert h_store.get_calibration_metrics()["total_decisions"] == 2

        with pytest.raises(ValueError, match="FINDING_DIGEST_MISMATCH"):
            record_remediation_decision(
                f_snooze.finding_id,
                prop_c,
                "Approve and fix now",
                q_store,
                h_store,
                expected_finding_digest="0" * 64,
                repo_root=REPO_ROOT,
            )

        with pytest.raises(ValueError, match="SYNTHETIC_"):
            record_remediation_decision(
                f_snooze.finding_id,
                prop_c,
                "Approve and fix now",
                q_store,
                h_store,
                approved_by="autonomous_policy_supervisor",
                repo_root=REPO_ROOT,
            )
    finally:
        h_store.close()
        q_store.close()


def test_dispatch_cycle_remediation_auto_applies_tier_a_and_emits_single_tier_c_question(tmp_path: Path) -> None:
    q_store = SqliteFindingsQueueStore(tmp_path / "queue.sqlite")
    out_dir = tmp_path / "sandbox_out"
    out_dir.mkdir()
    try:
        f_tier_a = q_store.upsert_finding(
            source_surface="online_eval",
            app_id="agents_core",
            failed_gate_signature="latency_sla",
            root_cause_bucket="agents_core_latency_sla_defect",
            owner_subsystem="agents",
            track="TRACK_1_CALIBRATION",
            priority="P1",
            title="Agents routing latency borderline threshold",
            summary="4 traces exceeded threshold.",
            recommended_action="Raise classifier threshold to 0.75.",
            occurrence_count=4,
            sample_trace_ids=["t1", "t2", "t3", "t4"],
        )
        f_tier_c_high = q_store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_rg",
            failed_gate_signature="x2_gates_passed",
            root_cause_bucket="apps_rg_grounding_defect",
            owner_subsystem="resume_graph_engine",
            track="TRACK_2_CODE_FIX",
            priority="P0",
            title="Resume grounding defect",
            summary="5 traces failed grounding.",
            recommended_action="Fix grounding validator.",
            occurrence_count=5,
            target_files=["resume_graph_engine/src/apps_rg/runtime/validators/x2.py"],
        )
        f_tier_c_low = q_store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_lic",
            failed_gate_signature="x2_gates_passed",
            root_cause_bucket="apps_lic_minor_defect",
            owner_subsystem="outreach_engine",
            track="TRACK_2_CODE_FIX",
            priority="P2",
            title="Minor outreach spacing issue",
            summary="2 traces failed formatting.",
            recommended_action="Fix formatter.",
            occurrence_count=2,
        )

        cl_a = FailureCluster(
            cluster_id="clst-tier-a-1",
            root_cause_bucket=f_tier_a.root_cause_bucket,
            owner_subsystem="agents",
            member_finding_ids=[f_tier_a.finding_id],
            unique_run_ids=["r1", "r2", "r3", "r4"],
            unique_session_count=4,
            max_priority="P1",
            aggregate_impact_score=f_tier_a.impact_score,
            conflict_detected=False,
            eligible_for_golden_promotion=True,
            eligible_for_proposal_synthesis=True,
            recommended_track="TRACK_1_CALIBRATION",
        )
        cl_c = FailureCluster(
            cluster_id="clst-tier-c-1",
            root_cause_bucket=f_tier_c_high.root_cause_bucket,
            owner_subsystem="resume_graph_engine",
            member_finding_ids=[f_tier_c_high.finding_id],
            unique_run_ids=["r5", "r6", "r7", "r8", "r9"],
            unique_session_count=5,
            max_priority="P0",
            aggregate_impact_score=f_tier_c_high.impact_score,
            conflict_detected=False,
            eligible_for_golden_promotion=True,
            eligible_for_proposal_synthesis=True,
            recommended_track="TRACK_2_CODE_FIX",
        )

        seeds = [
            {
                "case_id": f"seed-dev-{i}",
                "app_id": "agents_core",
                "split": "development",
                "unlabeled_input": {"score": 0.73},
                "expected_contract": {"reference_label": "PASS"},
            }
            for i in range(3)
        ] + [
            {
                "case_id": f"seed-hold-{i}",
                "app_id": "agents_core",
                "split": "holdout",
                "unlabeled_input": {"score": 0.73 if i < 2 else 0.85},
                "expected_contract": {"reference_label": "PASS"},
            }
            for i in range(5)
        ]
        golden_path = out_dir / "golden_eval_cases.json"
        promote_golden_cases(output_dataset_path=golden_path, curated_holdout_seeds=seeds)

        prop_a = _make_tier_a_proposal(0.75)
        prop_c = _make_tier_c_proposal()

        live_sha_before = sha256_file(REPO_ROOT / "config" / "routing_calibration.yaml")
        res = dispatch_cycle_remediation(
            repo_root=REPO_ROOT,
            output_root=out_dir,
            queue_store=q_store,
            clusters=[cl_a, cl_c],
            proposals=[prop_a, prop_c],
            golden_dataset_path=golden_path,
            sandbox=True,
            confidence_margin=0.35,
        )
        assert sha256_file(REPO_ROOT / "config" / "routing_calibration.yaml") == live_sha_before
        assert res["auto_applied_count"] == 1
        assert q_store.get_finding(f_tier_a.finding_id).status == "VERIFIED"
        assert Path(res["auto_applied"][0]["seal_path"]).is_file()
        assert res["pending_hitl_count"] == 2
        q_payload = res["next_ask_question_payload"]
        assert q_payload is not None
        assert len(q_payload["questions"]) == 1
        assert q_payload["metadata"]["finding_id"] == f_tier_c_high.finding_id
        assert q_payload["metadata"]["finding_id"] != f_tier_c_low.finding_id
        assert validate_hitl_presentation(q_payload, enforce_visibility_and_jargon=True) == []
    finally:
        q_store.close()
