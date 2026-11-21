"""Wave 3 tests for proposal synthesis, unlabeled_view holdout replay, eligibility firewall, hysteresis, and Tier A/B/C routing."""

from __future__ import annotations

from pathlib import Path

from agents.learning.eligibility import (
    evaluate_effort_hysteresis,
    filter_frozen_priors,
    record_learning_weight,
    validate_learning_approval_origin,
)
from agents.learning.policy_router import evaluate_auto_apply_policy
from agents.learning.proposal_generator import (
    build_signed_provenance,
    synthesize_proposals_from_clusters,
)
from apps_eval.contracts.schemas import EvalCase, FailureCluster, ImprovementProposal
from apps_eval.holdout_replay import evaluate_proposal_in_shadow
from tools.verify_fix_eval_pinning import evaluate_non_mock_e2e_branch_requirement

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_cases(split: str, count: int) -> list[EvalCase]:
    return [
        EvalCase(
            case_id=f"{split}-case-{i}",
            suite_id="agents_core.golden.v1",
            app_id="agents_core",
            split=split,  # type: ignore[arg-type]
            execution_mode="snapshot",
            source_kind="curated",
            grounding_tier="OFFLINE_BENCHMARK_GROUNDED",
            unlabeled_input={"confidence": 0.74, "idx": i},
            expected_contract={"reference_label": "ROUTE_A", "veto_dimensions": ["safety_breach"]},
        )
        for i in range(count)
    ]


def test_learning_eligibility_firewall_and_hysteresis() -> None:
    assert record_learning_weight({"run_id": "pytest_run_1", "decision_origin": "HUMAN_OPERATOR"}) == 0.0
    assert record_learning_weight({"run_id": "prod-1", "decision_origin": "AUTONOMOUS", "independent_outcome_verified": False}) == 0.0
    assert record_learning_weight({"run_id": "prod-1", "decision_origin": "AUTONOMOUS", "independent_outcome_verified": True}) == 0.5
    assert record_learning_weight({"run_id": "prod-1", "decision_origin": "HUMAN_HITL_APPROVED"}) == 1.0

    frozen = filter_frozen_priors(
        [
            {"decision_id": "d-self", "decision_origin": "HUMAN_OPERATOR"},
            {"decision_id": "d-child", "parent_decision_id": "d-self", "decision_origin": "HUMAN_OPERATOR"},
            {"decision_id": "d-test", "run_id": "pytest_1", "decision_origin": "HUMAN_OPERATOR"},
            {"decision_id": "d-valid", "run_id": "prod-9", "decision_origin": "HUMAN_OPERATOR"},
        ],
        current_decision_id="d-self",
    )
    assert [r["decision_id"] for r in frozen] == ["d-valid"]

    ok_syn, msg_syn = validate_learning_approval_origin(
        {"approval_origin": "human_hitl_approved", "approved_by": "autonomous_policy_supervisor"}
    )
    assert not ok_syn and "SYNTHETIC_APPROVAL_ORIGIN_REJECTED" in msg_syn

    # Hysteresis escalates immediately on FAILED, holds on 2 clean runs, steps down on 3 clean high-margin runs.
    eff1, _ = evaluate_effort_hysteresis(current_effort="MEDIUM", recent_runs=[{"status": "FAILED", "steps": 1}])
    assert eff1 == "HIGH"
    eff2, _ = evaluate_effort_hysteresis(
        current_effort="HIGH",
        recent_runs=[
            {"status": "COMPLETED", "steps": 1, "confidence_margin": 0.35},
            {"status": "COMPLETED", "steps": 1, "confidence_margin": 0.35},
        ],
    )
    assert eff2 == "HIGH"
    eff3, _ = evaluate_effort_hysteresis(
        current_effort="HIGH",
        recent_runs=[
            {"status": "COMPLETED", "steps": 1, "confidence_margin": 0.35},
            {"status": "COMPLETED", "steps": 1, "confidence_margin": 0.30},
            {"status": "COMPLETED", "steps": 1, "confidence_margin": 0.25},
        ],
    )
    assert eff3 == "MEDIUM"


def test_shadow_holdout_replay_enforces_unlabeled_view_zero_mutation_and_rejects_self_cert(tmp_path: Path) -> None:
    watched_dir = tmp_path / "prod_readonly"
    watched_dir.mkdir()
    (watched_dir / "state.json").write_text('{"immutable": true}', encoding="utf-8")

    cl_cal = FailureCluster(
        cluster_id="clst-cal-001",
        root_cause_bucket="routing_threshold_miss",
        owner_subsystem="agents",
        member_finding_ids=["find-1"],
        unique_run_ids=["run-1", "run-2", "run-3"],
        unique_session_count=3,
        max_priority="P1",
        aggregate_impact_score=90.0,
        conflict_detected=False,
        eligible_for_golden_promotion=True,
        eligible_for_proposal_synthesis=True,
        recommended_track="TRACK_1_CALIBRATION",
    )
    proposals = synthesize_proposals_from_clusters(
        [cl_cal],
        repo_root=REPO_ROOT,
        current_config_values={"config/routing_calibration.yaml::v12_routing.classifier_surface_threshold": 0.72},
    )
    assert len(proposals) == 1
    prop = proposals[0]
    assert prop.autonomy_tier == "TIER_A_AUTO_APPLY"
    assert prop.step_delta_magnitude <= 0.15

    target_cases = _make_cases("development", 4)
    holdout_cases = _make_cases("holdout", 6)

    seen_views: list[dict] = []

    def _runner(unlabeled_view: dict, threshold_val: float) -> dict:
        seen_views.append(unlabeled_view)
        assert "expected_contract" not in unlabeled_view
        # Proposed threshold (> 0.72) improves classification from ROUTE_B -> ROUTE_A.
        label = "ROUTE_A" if float(threshold_val) > 0.73 else "ROUTE_B"
        return {"label": label, "latency_ms": 50.0, "cost_usd": 0.001}

    verdict = evaluate_proposal_in_shadow(
        proposal=prop,
        target_cluster_cases=target_cases,
        holdout_cases=holdout_cases,
        dataset_digest="d" * 64,
        candidate_runner=_runner,
        watched_readonly_paths=[watched_dir],
    )
    assert verdict.verdict == "PASS", verdict.rejection_reasons
    assert verdict.zero_mutation_verified is True
    assert verdict.unlabeled_view_enforced is True
    assert verdict.holdout_accuracy_delta > 0.0
    assert len(seen_views) == (len(target_cases) + len(holdout_cases)) * 2

    # Empty holdout fails closed.
    empty_v = evaluate_proposal_in_shadow(
        proposal=prop,
        target_cluster_cases=target_cases,
        holdout_cases=[],
        dataset_digest="d" * 64,
        candidate_runner=_runner,
    )
    assert empty_v.verdict == "REJECT"
    assert "EMPTY_HOLDOUT_SET" in empty_v.rejection_reasons

    # Policy router routes Tier A pass, Tier B prompt_prior -> HITL, Tier C Python file -> PR-only.
    dec_a = evaluate_auto_apply_policy(proposal=prop, holdout_verdict=verdict, repo_root=REPO_ROOT)
    assert dec_a.effective_tier == "TIER_A_AUTO_APPLY"
    assert dec_a.auto_apply_permitted is True

    prop_b = ImprovementProposal(
        proposal_id="prop-tier-b",
        cluster_id="clst-b",
        artifact_class="prompt_prior",
        autonomy_tier="TIER_B_HITL_GATED",
        risk_lane="LANE_1",
        target_path="config/prompt_governance/priors.yaml",
        target_key="tone",
        expected_current_value="v1",
        proposed_value_or_patch="v2",
        step_delta_magnitude=0.0,
        evidence_trace_ids=["t1"],
        source_receipt_digests=[],
        provenance_digest=build_signed_provenance(
            proposal_id="prop-tier-b",
            evidence_trace_ids=["t1"],
            source_receipt_digests=[],
            proposed_change="v2",
            evaluation_plan=["holdout"],
        ),
        evaluation_plan=["holdout"],
        status="PROPOSED",
        expires_at_utc="2026-11-30T00:00:00Z",
    )
    dec_b = evaluate_auto_apply_policy(proposal=prop_b, holdout_verdict=None, repo_root=REPO_ROOT)
    assert dec_b.effective_tier == "TIER_B_HITL_GATED"
    assert dec_b.requires_hitl is True
    assert dec_b.auto_apply_permitted is False

    prop_c = ImprovementProposal(
        proposal_id="prop-tier-c",
        cluster_id="clst-c",
        artifact_class="bounded_threshold",  # Even if mislabeled, .py path unconditionally escalates to Tier C!
        autonomy_tier="TIER_A_AUTO_APPLY",
        risk_lane="LANE_1",
        target_path="agents/orchestration/engine.py",
        target_key="x",
        expected_current_value=1,
        proposed_value_or_patch=2,
        step_delta_magnitude=0.01,
        evidence_trace_ids=["t1"],
        source_receipt_digests=[],
        provenance_digest="a" * 64,
        evaluation_plan=["holdout"],
        status="PROPOSED",
        expires_at_utc="2026-11-30T00:00:00Z",
    )
    dec_c = evaluate_auto_apply_policy(proposal=prop_c, holdout_verdict=verdict, repo_root=REPO_ROOT)
    assert dec_c.effective_tier == "TIER_C_PR_ONLY"
    assert dec_c.requires_pr is True
    assert dec_c.auto_apply_permitted is False


def test_fix_branch_pinning_fails_closed_without_regression_case_or_test() -> None:
    bad = evaluate_non_mock_e2e_branch_requirement(
        REPO_ROOT,
        changed_paths=["apps_eval/online_grader.py"],
        e2e_files=[],
        branch_name="fix/unpinned-bug-123",
    )
    assert bad["status"] == "FAIL"
    assert bad["fail_closed_fix_pinning_active"] is True
    assert any(v["code"] == "MISSING_BRANCH_REGRESSION_TEST" for v in bad["violations"])

    good = evaluate_non_mock_e2e_branch_requirement(
        REPO_ROOT,
        changed_paths=["apps_eval/online_grader.py", "apps_eval/suites/pinned_fix_regressions.json"],
        e2e_files=[],
        branch_name="fix/pinned-bug-123",
    )
    assert good["status"] == "PASS"
