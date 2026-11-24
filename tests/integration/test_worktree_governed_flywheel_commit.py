"""Wave 5 tests: Ephemeral worktree governed auto-commit engine for git-tracked Tier A and approved Tier B updates."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

from agents.learning.rollback_manager import execute_bidirectional_rollback
from agents.learning.worktree_promoter import (
    apply_and_verify_with_worktree_isolation,
    is_git_tracked_target,
)
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.schemas import HoldoutReplayVerdict, ImprovementProposal


def _init_temp_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    src_root = Path(".").resolve()

    (repo / "config" / "governance").mkdir(parents=True, exist_ok=True)
    (repo / "config" / "prompt_governance").mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_root / "config" / "governance" / "auto_apply_policy.yaml", repo / "config" / "governance" / "auto_apply_policy.yaml")
    shutil.copy2(src_root / "config" / "routing_calibration.yaml", repo / "config" / "routing_calibration.yaml")
    shutil.copy2(src_root / "config" / "prompt_governance" / "priors.yaml", repo / "config" / "prompt_governance" / "priors.yaml")
    (repo / ".gitignore").write_text(".worktrees/\nartifacts/\n", encoding="utf-8")

    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, shell=False, timeout=10)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test Operator"], check=True, shell=False, timeout=5)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@agents.local"], check=True, shell=False, timeout=5)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, shell=False, timeout=10)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "initial commit"], check=True, shell=False, timeout=10)
    return repo


def _make_tier_a_proposal() -> tuple[ImprovementProposal, HoldoutReplayVerdict]:
    prop = ImprovementProposal(
        proposal_id="prop-wt-tier-a-001",
        cluster_id="clst-wt-1",
        artifact_class="bounded_threshold",
        autonomy_tier="TIER_A_AUTO_APPLY",
        risk_lane="LANE_1",
        target_path="config/routing_calibration.yaml",
        target_key="v12_routing.loop_guard_efficiency_threshold",
        expected_current_value=0.40,
        proposed_value_or_patch=0.44,
        step_delta_magnitude=0.04,
        evidence_trace_ids=["t-1", "t-2", "t-3"],
        source_receipt_digests=[],
        provenance_digest="a" * 64,
        evaluation_plan=["target_cluster_replay", "locked_holdout_replay"],
        status="PROPOSED",
        expires_at_utc="2026-12-31T00:00:00Z",
    )
    verdict = HoldoutReplayVerdict(
        verdict_id="hrv-wt-001",
        proposal_id=prop.proposal_id,
        proposal_digest=prop.canonical_digest,
        dataset_digest="b" * 64,
        zero_mutation_verified=True,
        unlabeled_view_enforced=True,
        target_cluster_cases=3,
        target_metric_before=0.33,
        target_metric_after=1.0,
        holdout_cases_evaluated=5,
        holdout_accuracy_before=1.0,
        holdout_accuracy_after=1.0,
        holdout_accuracy_delta=0.0,
        veto_regressions_count=0,
        latency_delta_pct=0.0,
        cost_delta_pct=0.0,
        pareto_regression=False,
        pinned_regressions_passed=True,
        verdict="PASS",
        rejection_reasons=[],
    )
    return prop, verdict


def test_worktree_promoter_commits_tracked_tier_a_cleanly_and_supports_clean_rollback(tmp_path: Path) -> None:
    repo = _init_temp_git_repo(tmp_path)
    assert is_git_tracked_target(repo, "config/routing_calibration.yaml") is True

    initial_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, shell=False, timeout=5,
    ).stdout.strip()

    prop, verdict = _make_tier_a_proposal()
    rt_dir = repo / "artifacts" / "learning"
    ledger = SqliteLearningLedgerStore(rt_dir / "learning_ledger.sqlite")
    try:
        applied, canary = apply_and_verify_with_worktree_isolation(
            proposal=prop,
            holdout_verdict=verdict,
            repo_root=repo,
            ledger_store=ledger,
            rollback_dir=rt_dir / "rollbacks",
            seals_dir=rt_dir / "seals",
            canary_metrics={
                "quality_score": 1.0,
                "veto_defects": 0,
                "latency_ms": 10.0,
                "pinned_regressions_passed": True,
            },
            baseline_metrics={"quality_score": 1.0},
            confidence_margin=0.35,
        )
        assert canary["canary_passed"] is True
        assert canary["status"] == "APPLIED_AND_SEALED"

        # 1. Working tree on main is 100% clean (zero dirty tracked files)
        status_out = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, check=True, shell=False, timeout=5,
        ).stdout.strip()
        assert status_out == ""

        # 2. HEAD advanced with a governed commit and value is 0.44 on main
        promoted_sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, shell=False, timeout=5,
        ).stdout.strip()
        assert promoted_sha != initial_sha
        doc = yaml.safe_load((repo / "config" / "routing_calibration.yaml").read_text(encoding="utf-8"))
        assert float(doc["v12_routing"]["loop_guard_efficiency_threshold"]) == 0.44

        # 3. Ephemeral worktree was pruned cleanly
        wt_list = [p for p in (repo / ".worktrees").glob("flywheel_*")] if (repo / ".worktrees").is_dir() else []
        assert wt_list == []

        # 4. Subsequent rollback also lands via ephemeral worktree leaving main clean and exact SHA-256 restored
        rb = execute_bidirectional_rollback(
            receipt=applied,
            ledger_store=ledger,
            reason="manual_operator_revert_test",
        )
        assert rb["status"] == "ROLLED_BACK"
        assert rb["exact_pre_apply_sha_match"] is True
        status_after_rb = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, check=True, shell=False, timeout=5,
        ).stdout.strip()
        assert status_after_rb == ""
        doc_rb = yaml.safe_load((repo / "config" / "routing_calibration.yaml").read_text(encoding="utf-8"))
        assert float(doc_rb["v12_routing"]["loop_guard_efficiency_threshold"]) == 0.40
    finally:
        ledger.close()


def test_worktree_promoter_aborts_on_failed_canary_leaving_main_untouched(tmp_path: Path) -> None:
    repo = _init_temp_git_repo(tmp_path)
    initial_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, shell=False, timeout=5,
    ).stdout.strip()

    prop, verdict = _make_tier_a_proposal()
    rt_dir = repo / "artifacts" / "learning"
    ledger = SqliteLearningLedgerStore(rt_dir / "learning_ledger.sqlite")
    try:
        _applied, canary = apply_and_verify_with_worktree_isolation(
            proposal=prop,
            holdout_verdict=verdict,
            repo_root=repo,
            ledger_store=ledger,
            rollback_dir=rt_dir / "rollbacks",
            seals_dir=rt_dir / "seals",
            canary_metrics={
                "quality_score": 0.70,
                "veto_defects": 1,
                "latency_ms": 10.0,
                "pinned_regressions_passed": False,
            },
            baseline_metrics={"quality_score": 1.0},
            confidence_margin=0.35,
        )
        assert canary["canary_passed"] is False
        assert canary["status"] == "ROLLED_BACK"

        # Main HEAD SHA and file contents were never mutated
        after_sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, shell=False, timeout=5,
        ).stdout.strip()
        assert after_sha == initial_sha
        status_out = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, check=True, shell=False, timeout=5,
        ).stdout.strip()
        assert status_out == ""
        doc = yaml.safe_load((repo / "config" / "routing_calibration.yaml").read_text(encoding="utf-8"))
        assert float(doc["v12_routing"]["loop_guard_efficiency_threshold"]) == 0.40

        # 7-day anti-oscillation rollback lock is active
        lock = ledger.get_active_rollback_lock(
            target_path="config/routing_calibration.yaml",
            target_key="v12_routing.loop_guard_efficiency_threshold",
        )
        assert lock is not None
    finally:
        ledger.close()
