"""Unit and concurrency tests for Governed PR Merge Queue and Trunk Reservation Lock (Waves 1 & 2).

Verifies:
1. GovernedMergeQueueLock acquisition, metadata serialization, re-entrancy, and release.
2. Dead-process stale lock breaking and heartbeat timeout recovery.
3. FIFO queue registration, unregistration, and live waiter pruning.
4. Starvation-bounded disjoint bypass (up to MAX_BYPASS_COUNT = 3).
5. Overlapping waiter bypass rejection.
6. Ephemeral merge-tree dry-run conflict check.
7. Worktree provisioning, relative dependency linking, and safe unlinking.
8. Serialized rebase establishing linear history onto main.
9. Automatic branch catch-up under lock when main advances.
10. Governed --no-ff merge under trunk lock with merge receipt.
11. Atomic main rollback upon verification failure.
12. Merged worktree and branch teardown.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pr_governance_core.common import check_merge_conflict, slugify_branch
from tools.pr_governance_core.lifecycle import (
    _catch_up_queued_branch_under_lock,
    _execute_merge_under_lock,
    atomic_rollback_main_to_sha,
    cmd_merge,
    cmd_review,
    verify_ephemeral_merge_tree,
)
from tools.pr_governance_core.merge_lock import (
    GovernedMergeQueueLock,
    LockContentionError,
    force_break_queue_lock,
    inspect_queue_lock,
    resolve_git_common_dir,
)
from tools.pr_governance_core.merge_queue import (
    MAX_BYPASS_COUNT,
    QueueItem,
    _read_waiters,
    _write_waiters,
    dequeue_pr,
    enqueue_pr,
    get_queue_status,
    is_first_live_waiter,
    register_fifo_waiter,
    unregister_fifo_waiter,
)
from tools.pr_governance_core.sync import rebase_branch_onto_main
from tools.pr_governance_core.worktree import (
    _remove_worktree_files,
    cmd_finish,
    link_worktree_dependencies,
    list_active_worktrees,
    provision_isolated_worktree,
    resolve_branch_worktree,
    safely_unlink_worktree_dependencies,
)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    clean_env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        env=clean_env,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )


class TestPRMergeQueueGovernance(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="agents_mq_test_")
        self.repo_root = Path(self.tmp_dir) / "repo"
        self.repo_root.mkdir(parents=True)

        _git(["init", "-b", "main"], self.repo_root)
        _git(["config", "user.name", "Agents Tester"], self.repo_root)
        _git(["config", "user.email", "agents@example.com"], self.repo_root)
        _git(["config", "commit.gpgsign", "false"], self.repo_root)

        (self.repo_root / "README.md").write_text("# Agents Repo\n", encoding="utf-8")
        _git(["add", "README.md"], self.repo_root)
        _git(["commit", "-m", "chore: initial commit"], self.repo_root)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_lock_acquire_inspect_and_release(self) -> None:
        """Lock creates metadata in git common dir and releases cleanly."""
        lock = GovernedMergeQueueLock("feat/branch-a", repo_root=self.repo_root, timeout_sec=5.0)
        self.assertTrue(lock.acquire())
        self.assertTrue(lock.is_acquired())

        info = inspect_queue_lock(self.repo_root)
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info.branch, "feat/branch-a")
        self.assertEqual(info.holder_pid, os.getpid())

        # Re-entrant acquire on same branch succeeds
        lock2 = GovernedMergeQueueLock("feat/branch-a", repo_root=self.repo_root)
        self.assertTrue(lock2.acquire())
        lock2.release()

        lock.release()
        self.assertFalse(lock.is_acquired())
        self.assertIsNone(inspect_queue_lock(self.repo_root))

    def test_02_lock_contention_non_blocking_fails(self) -> None:
        """Contending branch raises LockContentionError in non-blocking mode."""
        lock1 = GovernedMergeQueueLock("feat/branch-a", repo_root=self.repo_root)
        self.assertTrue(lock1.acquire())
        try:
            lock2 = GovernedMergeQueueLock(
                "feat/branch-b",
                repo_root=self.repo_root,
                non_blocking=True,
            )
            with self.assertRaises(LockContentionError):
                lock2.acquire()
        finally:
            lock1.release()

    def test_03_stale_lock_recovery_dead_pid(self) -> None:
        """Lock held by dead PID is automatically broken upon next acquire."""
        git_dir = resolve_git_common_dir(self.repo_root)
        meta_file = git_dir / "governed_merge_queue.json"
        lock_file = git_dir / "governed_merge_queue.lock"

        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        dead_pid = 999999
        meta_data = {
            "branch": "feat/dead-process",
            "holder_pid": dead_pid,
            "holder_host": "localhost",
            "acquired_at": now_iso,
            "heartbeat_at": now_iso,
            "timeout_sec": 300.0,
            "worktree_path": str(self.repo_root),
        }
        meta_file.write_text(json.dumps(meta_data), encoding="utf-8")
        lock_file.write_text("locked\n", encoding="utf-8")

        with patch("tools.pr_governance_core.merge_lock._is_pid_alive", return_value=False):
            lock = GovernedMergeQueueLock("feat/new-acquirer", repo_root=self.repo_root, timeout_sec=2.0)
            self.assertTrue(lock.acquire())
            self.assertTrue(lock.is_acquired())
            lock.release()

    def test_04_force_break_lock(self) -> None:
        """Manual force-break clears metadata and lock file."""
        lock = GovernedMergeQueueLock("feat/stuck-branch", repo_root=self.repo_root)
        self.assertTrue(lock.acquire())

        broken = force_break_queue_lock(self.repo_root)
        self.assertTrue(broken)
        self.assertIsNone(inspect_queue_lock(self.repo_root))

    def test_05_fifo_waiter_registration_and_unregistration(self) -> None:
        """Waiters are registered in FIFO sequence and unregistered accurately."""
        git_dir = resolve_git_common_dir(self.repo_root)
        pid1 = 10001
        pid2 = 10002

        with patch("tools.pr_governance_core.merge_queue._is_pid_alive", return_value=True):
            pos1 = register_fifo_waiter(git_dir, "feat/branch-1", pid1, ["file1.py"], False)
            pos2 = register_fifo_waiter(git_dir, "feat/branch-2", pid2, ["file2.py"], True)

            self.assertEqual(pos1, 1)
            self.assertEqual(pos2, 2)

            waiters = _read_waiters(git_dir)
            self.assertEqual(len(waiters), 2)
            self.assertEqual(waiters[0].branch, "feat/branch-1")
            self.assertEqual(waiters[1].branch, "feat/branch-2")

            unregister_fifo_waiter(git_dir, "feat/branch-1", pid1)
            waiters_after = _read_waiters(git_dir)
            self.assertEqual(len(waiters_after), 1)
            self.assertEqual(waiters_after[0].branch, "feat/branch-2")

    def test_06_starvation_bounded_disjoint_bypass(self) -> None:
        """Disjoint waiter bypasses unverified head up to 3 times, then halts."""
        git_dir = resolve_git_common_dir(self.repo_root)
        head_pid = 20001
        cand_pid = 20002

        with patch("tools.pr_governance_core.merge_queue._is_pid_alive", return_value=True):
            register_fifo_waiter(git_dir, "feat/slow-head", head_pid, ["slow.py"], False)
            register_fifo_waiter(git_dir, "feat/fast-disjoint", cand_pid, ["fast.py"], True)

            for expected_bypass_count in (1, 2, 3):
                can_run = is_first_live_waiter(
                    git_dir, "feat/fast-disjoint", cand_pid, ["fast.py"], True
                )
                self.assertTrue(can_run)
                head = [w for w in _read_waiters(git_dir) if w.branch == "feat/slow-head"][0]
                self.assertEqual(head.bypass_count, expected_bypass_count)

            can_run_4 = is_first_live_waiter(
                git_dir, "feat/fast-disjoint", cand_pid, ["fast.py"], True
            )
            self.assertFalse(can_run_4, "Candidate must not exceed MAX_BYPASS_COUNT (3)")

    def test_07_overlapping_waiter_cannot_bypass(self) -> None:
        """Candidate sharing modified files with head cannot bypass."""
        git_dir = resolve_git_common_dir(self.repo_root)
        head_pid = 30001
        cand_pid = 30002

        with patch("tools.pr_governance_core.merge_queue._is_pid_alive", return_value=True):
            register_fifo_waiter(git_dir, "feat/head", head_pid, ["shared.py", "a.py"], False)
            register_fifo_waiter(git_dir, "feat/cand", cand_pid, ["shared.py", "b.py"], True)

            can_bypass = is_first_live_waiter(
                git_dir, "feat/cand", cand_pid, ["shared.py", "b.py"], True
            )
            self.assertFalse(can_bypass, "Overlapping waiter must not bypass head")

    def test_08_queue_status_and_enqueue_dequeue(self) -> None:
        """Enqueue, status inspection, and dequeue operate cleanly."""
        item = enqueue_pr("feat/feature-x", "Feature X title", repo_root=self.repo_root)
        self.assertEqual(item.branch, "feat/feature-x")

        status = get_queue_status(repo_root=self.repo_root)
        self.assertEqual(status["total_queued"], 1)
        self.assertEqual(len(status["pending_waiters"]), 1)

        dropped = dequeue_pr("feat/feature-x", repo_root=self.repo_root)
        self.assertTrue(dropped)
        status_after = get_queue_status(repo_root=self.repo_root)
        self.assertEqual(status_after["total_queued"], 0)

    def test_09_check_merge_conflict_clean_and_dirty(self) -> None:
        """Ephemeral merge tree detects clean branches and conflicting branches in memory."""
        _git(["checkout", "-b", "feat/clean"], self.repo_root)
        (self.repo_root / "clean.txt").write_text("clean\n", encoding="utf-8")
        _git(["add", "clean.txt"], self.repo_root)
        _git(["commit", "-m", "feat: clean file"], self.repo_root)

        _git(["checkout", "main"], self.repo_root)
        is_clean, _ = check_merge_conflict("main", "feat/clean", cwd=self.repo_root)
        self.assertTrue(is_clean)

        _git(["checkout", "-b", "feat/conflict"], self.repo_root)
        (self.repo_root / "README.md").write_text("Branch version\n", encoding="utf-8")
        _git(["add", "README.md"], self.repo_root)
        _git(["commit", "-m", "feat: branch conflict"], self.repo_root)

        _git(["checkout", "main"], self.repo_root)
        (self.repo_root / "README.md").write_text("Main version\n", encoding="utf-8")
        _git(["add", "README.md"], self.repo_root)
        _git(["commit", "-m", "feat: main conflict"], self.repo_root)

        is_conf, details = check_merge_conflict("main", "feat/conflict", cwd=self.repo_root)
        self.assertFalse(is_conf)
        self.assertIn("README.md", details)

    def test_10_worktree_provision_and_unlink_dependencies(self) -> None:
        """Provisions an isolated worktree, creates symlinks, and safely unlinks them."""
        # Create mock .venv and .agents in root
        (self.repo_root / ".venv").mkdir()
        (self.repo_root / ".agents").mkdir()

        wt_dir = self.repo_root / ".worktrees" / "test-wt"
        provision_isolated_worktree(self.repo_root, wt_dir, "feat/test-worktree", "main")

        self.assertTrue(wt_dir.is_dir())
        self.assertTrue((wt_dir / ".venv").is_symlink())
        self.assertTrue((wt_dir / ".agents").is_symlink())

        # Resolve worktree
        wt_info = resolve_branch_worktree(self.repo_root, "feat/test-worktree")
        self.assertIsNotNone(wt_info)
        assert wt_info is not None
        self.assertEqual(wt_info["branch"], "feat/test-worktree")

        # Safely unlink
        unlinked = safely_unlink_worktree_dependencies(wt_dir)
        self.assertIn(".venv", unlinked)
        self.assertIn(".agents", unlinked)
        self.assertFalse((wt_dir / ".venv").exists())
        self.assertTrue((self.repo_root / ".venv").exists(), "Root .venv must not be destroyed!")

        # Clean teardown
        removed = _remove_worktree_files(wt_dir, force=True, root=self.repo_root)
        self.assertTrue(removed)
        self.assertFalse(wt_dir.exists())

    def test_11_rebase_branch_onto_main_linear(self) -> None:
        """Branch is rebased onto main, creating a linear history."""
        # Main commits a file
        (self.repo_root / "main_file.txt").write_text("main\n", encoding="utf-8")
        _git(["add", "main_file.txt"], self.repo_root)
        _git(["commit", "-m", "feat: main file"], self.repo_root)

        # Create branch from initial commit
        initial_sha = _git(["rev-parse", "HEAD~1"], self.repo_root).stdout.strip()
        _git(["branch", "feat/rebase-me", initial_sha], self.repo_root)

        # Worktree for branch
        wt_dir = self.repo_root / ".worktrees" / "rebase-me"
        provision_isolated_worktree(self.repo_root, wt_dir, "feat/rebase-me")
        (wt_dir / "feature_file.txt").write_text("feature\n", encoding="utf-8")
        _git(["add", "feature_file.txt"], wt_dir)
        _git(["commit", "-m", "feat: feature file"], wt_dir)

        # Rebase onto main
        outcome = rebase_branch_onto_main("feat/rebase-me", "main", repo_root=self.repo_root, work_dir=wt_dir)
        self.assertEqual(outcome.status, "SUCCESS")
        self.assertEqual(outcome.commits_rebased, 1)

        # Verify ancestor
        main_sha = _git(["rev-parse", "main"], self.repo_root).stdout.strip()
        branch_head = _git(["rev-parse", "feat/rebase-me"], self.repo_root).stdout.strip()
        base = _git(["merge-base", main_sha, branch_head], self.repo_root).stdout.strip()
        self.assertEqual(base, main_sha, "Rebased branch must have main as immediate ancestor")

        # Cleanup
        _remove_worktree_files(wt_dir, force=True, root=self.repo_root)

    def test_12_catch_up_queued_branch_under_lock_when_main_moves(self) -> None:
        """When main advances, catch-up under lock re-aligns branch and checks disjointness."""
        _git(["checkout", "-b", "feat/queued-branch"], self.repo_root)
        (self.repo_root / "feature.py").write_text("feature\n", encoding="utf-8")
        _git(["add", "feature.py"], self.repo_root)
        _git(["commit", "-m", "feat: feature file"], self.repo_root)

        # Main moves forward with disjoint commit
        _git(["checkout", "main"], self.repo_root)
        (self.repo_root / "other.py").write_text("other\n", encoding="utf-8")
        _git(["add", "other.py"], self.repo_root)
        _git(["commit", "-m", "chore: other file on main"], self.repo_root)

        # Catch up under lock
        slug = slugify_branch("feat/queued-branch")
        success, is_disjoint = _catch_up_queued_branch_under_lock("feat/queued-branch", slug, self.repo_root)
        self.assertTrue(success)
        self.assertTrue(is_disjoint)

        main_sha = _git(["rev-parse", "main"], self.repo_root).stdout.strip()
        branch_base = _git(["merge-base", "main", "feat/queued-branch"], self.repo_root).stdout.strip()
        self.assertEqual(main_sha, branch_base)

    def test_13_governed_merge_under_lock_and_post_merge_verification(self) -> None:
        """Branch is merged into main with --no-ff under lock and writes merge receipt."""
        _git(["checkout", "-b", "feat/merge-target"], self.repo_root)
        (self.repo_root / "target.py").write_text("target\n", encoding="utf-8")
        _git(["add", "target.py"], self.repo_root)
        _git(["commit", "-m", "feat: target code"], self.repo_root)
        branch_head = _git(["rev-parse", "HEAD"], self.repo_root).stdout.strip()

        _git(["checkout", "main"], self.repo_root)

        # Write passing PR review receipt
        slug = slugify_branch("feat/merge-target")
        reports_dir = self.repo_root / "reports"
        reports_dir.mkdir(parents=True)
        review_receipt = {
            "pr_type": "LOCAL_FEATURE_BRANCH_REVIEW",
            "branch": "feat/merge-target",
            "head_sha": branch_head,
            "base": "main",
            "clean_merge": True,
            "readiness_verified": True,
            "terminal_outcome": "PASS",
        }
        (reports_dir / f"pr_review_{slug}_receipt.json").write_text(
            json.dumps(review_receipt, indent=2), encoding="utf-8"
        )

        # Verify ephemeral merge tree
        clean, detail = verify_ephemeral_merge_tree(self.repo_root, "main", "feat/merge-target")
        self.assertTrue(clean)

        # Execute merge under lock
        rc = _execute_merge_under_lock("feat/merge-target", "feat: target code", slug, repo_root=self.repo_root)
        self.assertEqual(rc, 0)

        # Verify 2-parent merge commit on main
        parents = _git(["rev-list", "--parents", "-n", "1", "HEAD"], self.repo_root).stdout.strip().split()
        self.assertEqual(len(parents), 3)  # commit, parent1, parent2
        self.assertEqual(parents[2], branch_head)

        # Verify merge receipt file
        merge_receipt_file = reports_dir / f"pr_merge_{slug}_receipt.json"
        self.assertTrue(merge_receipt_file.is_file())
        receipt_data = json.loads(merge_receipt_file.read_text(encoding="utf-8"))
        self.assertEqual(receipt_data["terminal_outcome"], "PASS")

    def test_14_atomic_rollback_on_failed_verification(self) -> None:
        """Atomic rollback restores main to pre-merge commit cleanly."""
        pre_sha = _git(["rev-parse", "HEAD"], self.repo_root).stdout.strip()

        # Simulate bad commit on main
        (self.repo_root / "bad.txt").write_text("bad\n", encoding="utf-8")
        _git(["add", "bad.txt"], self.repo_root)
        _git(["commit", "-m", "bad commit"], self.repo_root)

        post_sha = _git(["rev-parse", "HEAD"], self.repo_root).stdout.strip()
        self.assertNotEqual(pre_sha, post_sha)

        rolled_back = atomic_rollback_main_to_sha(self.repo_root, pre_sha)
        self.assertTrue(rolled_back)

        current_sha = _git(["rev-parse", "HEAD"], self.repo_root).stdout.strip()
        self.assertEqual(current_sha, pre_sha)
        self.assertFalse((self.repo_root / "bad.txt").exists())

    def test_15_cmd_finish_teardown(self) -> None:
        """Merged worktree and branch are torn down by cmd_finish."""
        wt_dir = self.repo_root / ".worktrees" / "finished-wt"
        provision_isolated_worktree(self.repo_root, wt_dir, "feat/finished-wt", "main")
        self.assertTrue(wt_dir.is_dir())

        # Branch has no commits ahead, so it is ancestor/merged into main
        args = argparse.Namespace(
            branch="feat/finished-wt",
            force=False,
            delete_branch=True,
        )
        with patch("tools.pr_governance_core.worktree.ROOT", self.repo_root):
            rc = cmd_finish(args)
            self.assertEqual(rc, 0)

        self.assertFalse(wt_dir.exists())
        # Check branch deleted
        branches = _git(["branch", "--list", "feat/finished-wt"], self.repo_root).stdout.strip()
        self.assertEqual(branches, "")

    def test_16_cmd_merge_end_to_end_with_moving_main_disjoint_rebind(self) -> None:
        """Full cmd_merge succeeds when main moves forward with a disjoint commit after review receipt was sealed."""
        initial_main_sha = _git(["rev-parse", "main"], self.repo_root).stdout.strip()

        # Create branch B and commit a feature file
        _git(["checkout", "-b", "feat/branch-b"], self.repo_root)
        (self.repo_root / "feature_b.py").write_text("b = 1\n", encoding="utf-8")
        _git(["add", "feature_b.py"], self.repo_root)
        _git(["commit", "-m", "feat: add feature b"], self.repo_root)
        old_b_head = _git(["rev-parse", "HEAD"], self.repo_root).stdout.strip()

        # Write passing review receipt for branch B at initial_main_sha
        slug_b = slugify_branch("feat/branch-b")
        reports_dir = self.repo_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        review_receipt = {
            "pr_type": "LOCAL_FEATURE_BRANCH_REVIEW",
            "branch": "feat/branch-b",
            "head_sha": old_b_head,
            "base": "main",
            "base_commit_sha": initial_main_sha,
            "clean_merge": True,
            "readiness_verified": True,
            "terminal_outcome": "PASS",
        }
        (reports_dir / f"pr_review_{slug_b}_receipt.json").write_text(
            json.dumps(review_receipt, indent=2), encoding="utf-8"
        )

        # Now main moves forward (simulating branch A merging while branch B waited in FIFO queue)
        _git(["checkout", "main"], self.repo_root)
        (self.repo_root / "feature_a.py").write_text("a = 1\n", encoding="utf-8")
        _git(["add", "feature_a.py"], self.repo_root)
        _git(["commit", "-m", "feat: land feature a on main"], self.repo_root)
        advanced_main_sha = _git(["rev-parse", "main"], self.repo_root).stdout.strip()
        self.assertNotEqual(initial_main_sha, advanced_main_sha)

        # Run full cmd_merge for branch B
        merge_args = argparse.Namespace(
            branch="feat/branch-b",
            title="feat: add feature b",
            repo_root=self.repo_root,
            skip_readiness_run=True,
            delete_branch=True,
        )
        rc = cmd_merge(merge_args)
        self.assertEqual(rc, 0, "cmd_merge must catch up under lock, rebind disjoint receipt, and land cleanly")

        # Verify both feature_a.py and feature_b.py are on main and branch-b is deleted
        self.assertTrue((self.repo_root / "feature_a.py").is_file())
        self.assertTrue((self.repo_root / "feature_b.py").is_file())
        branches = _git(["branch", "--list", "feat/branch-b"], self.repo_root).stdout.strip()
        self.assertEqual(branches, "")

    def test_17_cmd_merge_overlapping_main_triggers_revalidation(self) -> None:
        """When main advances with overlapping file changes, catch-up releases lock and re-runs review."""
        (self.repo_root / "shared.py").write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        _git(["add", "shared.py"], self.repo_root)
        _git(["commit", "-m", "chore: add shared file"], self.repo_root)
        base_sha = _git(["rev-parse", "main"], self.repo_root).stdout.strip()

        # Branch modifies bottom of shared.py
        _git(["checkout", "-b", "feat/overlap-branch"], self.repo_root)
        (self.repo_root / "shared.py").write_text("line1\nline2\nline3\nline4\nline5_branch\n", encoding="utf-8")
        _git(["add", "shared.py"], self.repo_root)
        _git(["commit", "-m", "feat: modify bottom of shared"], self.repo_root)
        old_head = _git(["rev-parse", "HEAD"], self.repo_root).stdout.strip()

        slug = slugify_branch("feat/overlap-branch")
        reports_dir = self.repo_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / f"pr_review_{slug}_receipt.json").write_text(
            json.dumps(
                {
                    "pr_type": "LOCAL_FEATURE_BRANCH_REVIEW",
                    "branch": "feat/overlap-branch",
                    "head_sha": old_head,
                    "base": "main",
                    "base_commit_sha": base_sha,
                    "clean_merge": True,
                    "readiness_verified": True,
                    "terminal_outcome": "PASS",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        # Main modifies top of shared.py (overlapping file, non-conflicting lines)
        _git(["checkout", "main"], self.repo_root)
        (self.repo_root / "shared.py").write_text("line1_main\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        _git(["add", "shared.py"], self.repo_root)
        _git(["commit", "-m", "feat: modify top of shared on main"], self.repo_root)

        merge_args = argparse.Namespace(
            branch="feat/overlap-branch",
            title="feat: modify bottom of shared",
            repo_root=self.repo_root,
            skip_readiness_run=True,
            delete_branch=True,
        )
        rc = cmd_merge(merge_args)
        self.assertEqual(rc, 0, "Overlapping non-conflicting change must re-run review and land on cycle 2")
        final_text = (self.repo_root / "shared.py").read_text(encoding="utf-8")
        self.assertIn("line1_main", final_text)
        self.assertIn("line5_branch", final_text)

    def test_18_verify_merge_receipt_and_forgery_guard(self) -> None:
        """verify_merge_receipt rejects missing, stale, or forged receipts and accepts valid ones."""
        from tools.verify_merge_receipt import verify_merge_receipt

        _git(["checkout", "-b", "feat/check-rcpt"], self.repo_root)
        (self.repo_root / "r.txt").write_text("r\n", encoding="utf-8")
        _git(["add", "r.txt"], self.repo_root)
        _git(["commit", "-m", "feat: add r"], self.repo_root)
        head_sha = _git(["rev-parse", "HEAD"], self.repo_root).stdout.strip()
        _git(["checkout", "main"], self.repo_root)

        # 1. Missing receipt
        with patch.dict(os.environ, {"GOVERNED_PR_MERGE": "0"}):
            ok, msg = verify_merge_receipt(branch="feat/check-rcpt", repo_root=self.repo_root)
            self.assertFalse(ok)
            self.assertIn("Missing required PR Review Receipt", msg)

        # 2. Forged GOVERNED_PR_MERGE=1 without lock or receipt
        with patch.dict(os.environ, {"GOVERNED_PR_MERGE": "1"}):
            ok_f, msg_f = verify_merge_receipt(branch="feat/check-rcpt", repo_root=self.repo_root)
            self.assertFalse(ok_f)
            self.assertIn("FORGED_GOVERNED_MERGE_REJECTED", msg_f)

        # 3. Stale receipt
        slug = slugify_branch("feat/check-rcpt")
        reports_dir = self.repo_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = reports_dir / f"pr_review_{slug}_receipt.json"
        receipt_path.write_text(
            json.dumps(
                {
                    "branch": "feat/check-rcpt",
                    "head_sha": "0000000000000000000000000000000000000000",
                    "terminal_outcome": "PASS",
                }
            ),
            encoding="utf-8",
        )
        ok_s, msg_s = verify_merge_receipt(branch="feat/check-rcpt", repo_root=self.repo_root)
        self.assertFalse(ok_s)
        self.assertIn("stale", msg_s)

        # 4. Valid receipt
        receipt_path.write_text(
            json.dumps(
                {
                    "branch": "feat/check-rcpt",
                    "head_sha": head_sha,
                    "terminal_outcome": "PASS",
                }
            ),
            encoding="utf-8",
        )
        ok_v, msg_v = verify_merge_receipt(branch="feat/check-rcpt", repo_root=self.repo_root)
        self.assertTrue(ok_v)
        self.assertIn("Verified valid PR Review Receipt", msg_v)

    def test_19_verify_post_merge_certification(self) -> None:
        """verify_latest_merge rejects single-parent commits and certifies 2-parent governed merges."""
        from tools.verify_post_merge import verify_latest_merge

        # Single-parent commit on main fails certification
        ok_single, msg_single = verify_latest_merge(self.repo_root)
        self.assertFalse(ok_single)
        self.assertIn("not a two-parent merge commit", msg_single)

        # Perform governed merge and verify certification passes
        _git(["checkout", "-b", "feat/cert-branch"], self.repo_root)
        (self.repo_root / "cert.txt").write_text("cert\n", encoding="utf-8")
        _git(["add", "cert.txt"], self.repo_root)
        _git(["commit", "-m", "feat: cert"], self.repo_root)
        b_sha = _git(["rev-parse", "HEAD"], self.repo_root).stdout.strip()
        _git(["checkout", "main"], self.repo_root)

        slug = slugify_branch("feat/cert-branch")
        reports_dir = self.repo_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / f"pr_review_{slug}_receipt.json").write_text(
            json.dumps(
                {
                    "branch": "feat/cert-branch",
                    "head_sha": b_sha,
                    "clean_merge": True,
                    "readiness_verified": True,
                    "terminal_outcome": "PASS",
                }
            ),
            encoding="utf-8",
        )
        rc = _execute_merge_under_lock("feat/cert-branch", "feat: cert", slug, repo_root=self.repo_root)
        self.assertEqual(rc, 0)

        ok_merge, msg_merge = verify_latest_merge(self.repo_root)
        self.assertTrue(ok_merge)
        self.assertIn("certified against reviewed branch", msg_merge)

    def test_20_recheck_failed_only_stage_reuse(self) -> None:
        """verify_main_readiness --recheck-failed-only reuses prior PASS stages and only runs failed ones."""
        from tools.verify_main_readiness import _load_prior_passing_stages

        receipt_dir = self.repo_root / "reports" / "readiness"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        rcpt_file = receipt_dir / "local_main_readiness_feat_test_receipt.json"
        rcpt_file.write_text(
            json.dumps(
                {
                    "branch": "feat/test",
                    "stages": [
                        {"stage_name": "1. Tier 1 Structural Governance", "status": "PASS"},
                        {"stage_name": "2. Architecture & Service Boundaries", "status": "FAIL"},
                    ],
                    "terminal_outcome": "FAIL",
                }
            ),
            encoding="utf-8",
        )
        passed = _load_prior_passing_stages(rcpt_file)
        self.assertIn("1. Tier 1 Structural Governance", passed)
        self.assertNotIn("2. Architecture & Service Boundaries", passed)


if __name__ == "__main__":
    unittest.main()
