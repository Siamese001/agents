"""Wave 3 tests for atomic CAS commits, absent-key cleanup, post-apply LP5 canary auto-rollback, 7d lock, and LP0..LP5 Merkle seal."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.learning.commit_engine import CommitPreconditionError, apply_proposal_atomically
from agents.learning.merkle_seal import verify_merkle_seal
from agents.learning.policy_router import evaluate_auto_apply_policy
from agents.learning.proposal_generator import build_signed_provenance
from agents.learning.rollback_manager import evaluate_post_apply_canary_and_seal
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.digests import sha256_file
from apps_eval.contracts.schemas import HoldoutReplayVerdict, ImprovementProposal

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_tier_a_proposal(
    *,
    proposal_id: str,
    expected_val: float | None,
    proposed_val: float,
    target_key: str = "v12_routing.classifier_surface_threshold",
) -> tuple[ImprovementProposal, HoldoutReplayVerdict]:
    prop = ImprovementProposal(
        proposal_id=proposal_id,
        cluster_id="clst-routing-1",
        artifact_class="bounded_threshold",
        autonomy_tier="TIER_A_AUTO_APPLY",
        risk_lane="LANE_1",
        target_path="config/routing_calibration.yaml",
        target_key=target_key,
        expected_current_value=expected_val,
        proposed_value_or_patch=proposed_val,
        step_delta_magnitude=round(abs(proposed_val - (expected_val or 0.72)), 4),
        evidence_trace_ids=["trace-1", "trace-2", "trace-3"],
        source_receipt_digests=["r" * 64],
        provenance_digest=build_signed_provenance(
            proposal_id=proposal_id,
            evidence_trace_ids=["trace-1", "trace-2", "trace-3"],
            source_receipt_digests=["r" * 64],
            proposed_change={"key": target_key, "value": proposed_val},
            evaluation_plan=["target_cluster_replay", "locked_holdout_replay"],
        ),
        evaluation_plan=["target_cluster_replay", "locked_holdout_replay"],
        status="PROPOSED",
        expires_at_utc="2026-12-01T00:00:00Z",
    )
    verdict = HoldoutReplayVerdict(
        verdict_id=f"hrv-{proposal_id}",
        proposal_id=prop.proposal_id,
        proposal_digest=prop.canonical_digest,
        dataset_digest="d" * 64,
        zero_mutation_verified=True,
        unlabeled_view_enforced=True,
        target_cluster_cases=5,
        target_metric_before=0.70,
        target_metric_after=0.95,
        holdout_cases_evaluated=10,
        holdout_accuracy_before=0.90,
        holdout_accuracy_after=0.95,
        holdout_accuracy_delta=0.05,
        pinned_regressions_passed=True,
        veto_regressions_count=0,
        pareto_regression=False,
        latency_delta_pct=1.0,
        cost_delta_pct=0.0,
        verdict="PASS",
    )
    return prop, verdict


def test_tier_a_commit_cas_conflict_and_merkle_seal_pass(tmp_path: Path) -> None:
    cfg = tmp_path / "routing_calibration.yaml"
    cfg.write_text("# Header comment\nv12_routing:\n  classifier_surface_threshold: 0.72\n", encoding="utf-8")
    ledger = SqliteLearningLedgerStore(tmp_path / "learning_ledger.sqlite")
    try:
        # 1. Drifted expected value triggers CAS_CONFLICT without mutating file.
        drifted_prop, drifted_v = _make_tier_a_proposal(
            proposal_id="prop-cas-drift",
            expected_val=0.60,
            proposed_val=0.75,
        )
        with pytest.raises(CommitPreconditionError, match="CAS_CONFLICT"):
            apply_proposal_atomically(
                proposal=drifted_prop,
                holdout_verdict=drifted_v,
                repo_root=REPO_ROOT,
                ledger_store=ledger,
                rollback_dir=tmp_path / "rollbacks",
                target_file_override=cfg,
            )

        # 2. Matching CAS applies atomically and seals LP0..LP5 on healthy LP5 canary.
        prop, verdict = _make_tier_a_proposal(
            proposal_id="prop-good-1",
            expected_val=0.72,
            proposed_val=0.76,
        )
        rcpt = apply_proposal_atomically(
            proposal=prop,
            holdout_verdict=verdict,
            repo_root=REPO_ROOT,
            ledger_store=ledger,
            rollback_dir=tmp_path / "rollbacks",
            target_file_override=cfg,
        )
        assert rcpt.status == "APPLIED"
        assert rcpt.pre_apply_file_sha256 != rcpt.post_apply_file_sha256
        assert "0.76" in cfg.read_text(encoding="utf-8")

        # Duplicate apply is blocked.
        with pytest.raises(CommitPreconditionError, match="DUPLICATE_APPLY_BLOCKED"):
            apply_proposal_atomically(
                proposal=prop,
                holdout_verdict=verdict,
                repo_root=REPO_ROOT,
                ledger_store=ledger,
                rollback_dir=tmp_path / "rollbacks",
                target_file_override=cfg,
            )

        canary = evaluate_post_apply_canary_and_seal(
            receipt=rcpt,
            canary_metrics={"quality_score": 0.96, "veto_defects": 0, "latency_ms": 120.0, "pinned_regressions_passed": True},
            baseline_metrics={"quality_score": 0.90},
            ledger_store=ledger,
            seals_dir=tmp_path / "seals",
        )
        assert canary["status"] == "APPLIED_AND_SEALED"
        assert canary["canary_passed"] is True
        assert verify_merkle_seal(canary["merkle_seal"]) is True
    finally:
        ledger.close()


def test_canary_regression_triggers_exact_sha_rollback_and_7day_lock(tmp_path: Path) -> None:
    cfg = tmp_path / "routing_calibration.yaml"
    cfg.write_text("# Preserved comment\nv12_routing:\n  classifier_surface_threshold: 0.72\n", encoding="utf-8")
    pre_sha = sha256_file(cfg)
    ledger = SqliteLearningLedgerStore(tmp_path / "learning_ledger.sqlite")
    try:
        prop, verdict = _make_tier_a_proposal(
            proposal_id="prop-canary-fail",
            expected_val=0.72,
            proposed_val=0.78,
        )
        rcpt = apply_proposal_atomically(
            proposal=prop,
            holdout_verdict=verdict,
            repo_root=REPO_ROOT,
            ledger_store=ledger,
            rollback_dir=tmp_path / "rollbacks",
            target_file_override=cfg,
        )
        assert sha256_file(cfg) != pre_sha

        # Degraded LP5 canary immediately rolls back to exact pre-apply SHA-256 and locks key for 7 days.
        canary = evaluate_post_apply_canary_and_seal(
            receipt=rcpt,
            canary_metrics={"quality_score": 0.70, "veto_defects": 1, "latency_ms": 150.0, "pinned_regressions_passed": True},
            baseline_metrics={"quality_score": 0.92},
            ledger_store=ledger,
            seals_dir=tmp_path / "seals",
        )
        assert canary["status"] == "ROLLED_BACK"
        assert canary["canary_passed"] is False
        assert canary["rollback"]["exact_pre_apply_sha_match"] is True
        assert sha256_file(cfg) == pre_sha
        assert verify_merkle_seal(canary["merkle_seal"]) is True

        # Subsequent Tier A attempt on the same key is blocked by the 7-day post-rollback lock and escalated to HITL.
        prop2, verdict2 = _make_tier_a_proposal(
            proposal_id="prop-after-rollback",
            expected_val=0.72,
            proposed_val=0.75,
        )
        dec = evaluate_auto_apply_policy(
            proposal=prop2,
            holdout_verdict=verdict2,
            repo_root=REPO_ROOT,
            ledger_store=ledger,
        )
        assert dec.auto_apply_permitted is False
        assert dec.requires_hitl is True
        assert any("POST_ROLLBACK_LOCK_ACTIVE" in r for r in dec.blocking_reasons)
    finally:
        ledger.close()
