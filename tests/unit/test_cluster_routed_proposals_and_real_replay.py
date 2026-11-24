"""Wave 4 tests: Cluster-routed calibration proposal synthesizer, priors.yaml SSOT, and domain shadow replay."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agents.learning.flywheel_hitl_dispatcher import build_domain_calibration_replay_runner
from agents.learning.proposal_generator import (
    synthesize_proposals_from_clusters,
    validate_no_prose_splicing,
)
from apps_eval.contracts.schemas import EvalCase, FailureCluster
from apps_eval.holdout_replay import evaluate_proposal_in_shadow


def _make_cluster(cid: str, _gate_sig: str, bucket: str) -> FailureCluster:
    return FailureCluster(
        cluster_id=cid,
        root_cause_bucket=bucket,
        owner_subsystem="agents",
        member_finding_ids=[f"find-{cid}"],
        unique_run_ids=["r1", "r2", "r3", "r4"],
        unique_session_count=2,
        max_priority="P1",
        aggregate_impact_score=32.0,
        conflict_detected=False,
        eligible_for_golden_promotion=True,
        eligible_for_proposal_synthesis=True,
        recommended_track="TRACK_1_CALIBRATION",
    )


def test_cluster_routed_synthesizer_maps_all_six_bounded_parameters_and_tier_b_priors() -> None:
    repo_root = Path(".").resolve()
    priors_file = repo_root / "config" / "prompt_governance" / "priors.yaml"
    assert priors_file.is_file()
    priors_doc = yaml.safe_load(priors_file.read_text(encoding="utf-8"))
    assert priors_doc["schema_version"] == "1.0.0"

    clusters = [
        _make_cluster("c-lat", "latency_sla", "apps_rg_latency_sla_defect"),
        _make_cluster("c-cache", "semantic_cache_miss", "gptcache_similarity_defect"),
        _make_cluster("c-abs", "abstain_floor", "safe_abstain_threshold_defect"),
        _make_cluster("c-casc", "r_casc_escalation", "cascade_escalation_defect"),
        _make_cluster("c-r1b", "r1b_semantic_match", "post_gate_match_defect"),
        _make_cluster("c-surf", "classifier_surface", "v12_surface_defect"),
        _make_cluster("c-corr", "correction:terminology", "correction_terminology_role"),
    ]

    proposals = synthesize_proposals_from_clusters(
        clusters,
        repo_root=repo_root,
        graduation_state_path=repo_root / "nonexistent_grad.json",
    )
    by_cluster = {p.cluster_id: p for p in proposals}
    assert len(by_cluster) == 7

    assert by_cluster["c-lat"].target_key == "v12_routing.loop_guard_efficiency_threshold"
    assert by_cluster["c-lat"].autonomy_tier == "TIER_A_AUTO_APPLY"

    assert by_cluster["c-cache"].target_key == "semantic_cache.similarity_threshold"
    assert by_cluster["c-cache"].proposed_value_or_patch < by_cluster["c-cache"].expected_current_value

    assert by_cluster["c-abs"].target_key == "abstain.default_threshold"
    assert by_cluster["c-casc"].target_key == "v12_routing.r_casc_escalation_threshold"
    assert by_cluster["c-r1b"].target_key == "v12_routing.r1b_semantic_match_threshold"
    assert by_cluster["c-surf"].target_key == "v12_routing.classifier_surface_threshold"

    corr_prop = by_cluster["c-corr"]
    assert corr_prop.target_path == "config/prompt_governance/priors.yaml"
    assert corr_prop.artifact_class == "prompt_prior"
    assert corr_prop.autonomy_tier == "TIER_B_HITL_GATED"
    assert corr_prop.target_key == "flywheel_priors.correction_terminology_role"


def test_prose_splicing_prior_rejected_fail_closed() -> None:
    with pytest.raises(ValueError, match="PROSE_SPLICING_HINT_REJECTED"):
        validate_no_prose_splicing("Always start with literal prefix 'In parallel, I led'")


def test_domain_calibration_replay_runner_executes_unlabeled_view_with_measured_latency() -> None:
    repo_root = Path(".").resolve()
    cl = _make_cluster("c-lat-replay", "latency_sla", "loop_guard_efficiency_defect")
    prop = synthesize_proposals_from_clusters(
        [cl],
        repo_root=repo_root,
        graduation_state_path=repo_root / "nonexistent_grad.json",
    )[0]
    assert prop.expected_current_value == 0.40
    assert prop.proposed_value_or_patch > 0.40

    dev_case = EvalCase(
        case_id="dev-1",
        suite_id="agents.routing.v1",
        app_id="apps_rg",
        split="development",
        execution_mode="snapshot",
        grounding_tier="LIVE_CORPUS_GROUNDED",
        source_kind="online_eval_failure",
        source_trace_id="t-dev-1",
        unlabeled_input={"payload": {"efficiency_score": 0.41}, "pii_redacted": True},
        expected_contract={"reference_label": "PASS"},
    )
    hold_case = EvalCase(
        case_id="hold-1",
        suite_id="agents.routing.v1",
        app_id="apps_rg",
        split="holdout",
        execution_mode="snapshot",
        grounding_tier="LIVE_CORPUS_GROUNDED",
        source_kind="curated_holdout_seed",
        source_trace_id="t-hold-1",
        unlabeled_input={"payload": {"efficiency_score": 0.92}, "pii_redacted": True},
        expected_contract={"reference_label": "PASS"},
    )

    runner = build_domain_calibration_replay_runner(prop)
    out_sample = runner(dev_case.unlabeled_view, prop.proposed_value_or_patch)
    assert "measured_wallclock_ms" in out_sample
    assert out_sample["measured_wallclock_ms"] > 0.0

    verdict = evaluate_proposal_in_shadow(
        proposal=prop,
        target_cluster_cases=[dev_case],
        holdout_cases=[hold_case],
        dataset_digest="a" * 64,
        candidate_runner=runner,
    )
    assert verdict.verdict == "PASS"
    assert verdict.target_metric_before == 0.0
    assert verdict.target_metric_after == 1.0
    assert verdict.holdout_accuracy_after == 1.0
