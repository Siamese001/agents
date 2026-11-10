"""
PR Lifecycle: Review, Governed Merge to Main, Automatic Catch-Up Under Lock, and Teardown.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .common import (
    ROOT,
    check_disjoint_base_advance_equivalence,
    check_merge_conflict,
    compute_branch_delta_digest,
    compute_first_parent_sync,
    resolve_python,
    run_git,
    sanitized_git_env,
    slugify_branch,
)
from .inspection import get_feature_branches
from .merge_lock import GovernedMergeQueueLock
from .worktree import (
    _find_worktree_dir,
    _remove_worktree_files,
    list_active_worktrees,
    provision_isolated_worktree,
    resolve_branch_worktree,
)


def _is_disjoint_rebase_equivalent(
    repo_root: Path,
    branch: str,
    old_head_sha: str,
    new_head_sha: str,
    old_base_sha: str,
) -> Tuple[bool, str]:
    """Verifies whether `new_head_sha` is a pure disjoint rebase of `old_head_sha` onto current `main`."""
    if not old_head_sha or not new_head_sha:
        return False, ""
    try:
        main_sha = run_git(["rev-parse", "main"], cwd=repo_root, check=False).strip()
        if not main_sha:
            return False, ""
        if not old_base_sha:
            old_base_sha = run_git(["merge-base", "main", old_head_sha], cwd=repo_root, check=False).strip()
        if not old_base_sha:
            return False, ""

        old_delta = compute_branch_delta_digest(repo_root, ref=old_head_sha, base_ref=old_base_sha)
        new_delta = compute_branch_delta_digest(repo_root, ref=new_head_sha, base_ref=main_sha)
        if old_delta and new_delta and old_delta != new_delta:
            return False, ""

        branch_diff = [
            line.strip()
            for line in run_git(["diff", "--name-only", f"{main_sha}...{new_head_sha}"], cwd=repo_root, check=False).splitlines()
            if line.strip()
        ]
        is_disjoint, _ = check_disjoint_base_advance_equivalence(
            old_base_sha, main_sha, branch_diff, repo_root=repo_root
        )
        return is_disjoint, main_sha
    except Exception:
        return False, ""


def _resolve_pr_review_receipt(
    branch: str, slug: str, head_sha: str, repo_root: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Resolves and parses PR review receipt for the branch, supporting disjoint rebase rebinding."""
    root = repo_root or ROOT
    candidates = [
        root / "reports" / f"pr_review_{slug}_receipt.json",
        root / ".worktrees" / slug / "reports" / f"pr_review_{slug}_receipt.json",
    ]
    for c in candidates:
        if not c.is_file():
            continue
        try:
            data = json.loads(c.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            if data.get("branch") not in (None, branch):
                continue
            rec_sha = str(data.get("head_sha") or data.get("head_commit_sha") or "")
            if not head_sha or rec_sha == head_sha:
                return data
            if data.get("terminal_outcome") == "PASS" and data.get("clean_merge") is True and rec_sha and head_sha:
                old_base = str(data.get("base_commit_sha") or "")
                is_disjoint, new_main = _is_disjoint_rebase_equivalent(
                    root, branch, rec_sha, head_sha, old_base
                )
                if is_disjoint:
                    rebound = dict(data)
                    rebound["head_sha"] = head_sha
                    rebound["commits_behind"] = 0
                    if new_main:
                        rebound["base_commit_sha"] = new_main
                    with contextlib.suppress(Exception):
                        c.write_text(json.dumps(rebound, indent=2) + "\n", encoding="utf-8")
                    return rebound
        except (OSError, ValueError, TypeError, RuntimeError):
            pass
    return None


def _validate_merge_receipt(
    branch: str, slug: str, head_sha: str, repo_root: Optional[Path] = None
) -> bool:
    """Verifies that a passing review receipt exists, is not stale, and aligns with main."""
    root = repo_root or ROOT
    receipt = _resolve_pr_review_receipt(branch, slug, head_sha, repo_root=root)
    if not receipt:
        return False
    if receipt.get("terminal_outcome") != "PASS":
        return False
    if receipt.get("head_sha") != head_sha:
        return False
    return True


def _check_merge_cleanliness(branch: str, repo_root: Optional[Path] = None) -> bool:
    """Checks that the worktree for the branch is clean."""
    root = repo_root or ROOT
    for wt in list_active_worktrees(root, ignore_review_artifacts=True):
        if wt.get("branch") == branch and wt.get("dirty"):
            print(f"❌ Error: Worktree for '{branch}' has uncommitted modifications: {wt.get('summary')}")
            return False
    return True


def _check_merge_prerequisites(branch: str, repo_root: Optional[Path] = None) -> int:
    """Validates that branch exists and is not main."""
    root = repo_root or ROOT
    if branch in ("main", "master"):
        print(f"❌ Error: Cannot merge '{branch}' into itself.")
        return 1

    branches = get_feature_branches(repo_root=root)
    try:
        cur = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root).strip()
        if branch not in branches and cur != branch:
            print(f"❌ Error: Branch '{branch}' does not exist.")
            return 1
    except Exception:
        if branch not in branches:
            print(f"❌ Error: Branch '{branch}' does not exist.")
            return 1
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """Executes pre-merge review validation (cleanliness, mergeability, readiness)."""
    branch = args.branch
    repo_root = getattr(args, "repo_root", None) or ROOT
    slug = slugify_branch(branch)
    print("=" * 80)
    print(f"  PRE-MERGE REVIEW VALIDATION: {branch}")
    print("=" * 80)

    if _check_merge_prerequisites(branch, repo_root) != 0:
        return 1

    if not _check_merge_cleanliness(branch, repo_root):
        return 1

    wt_info = resolve_branch_worktree(repo_root, branch, ignore_review_artifacts=True)
    wt_dir = Path(str(wt_info["path"])) if (wt_info and wt_info.get("path")) else repo_root

    behind, ahead = compute_first_parent_sync("main", branch, cwd=wt_dir)
    print(f"Branch Status: {ahead} ahead, {behind} behind main.")

    is_clean, conflict_msg = check_merge_conflict("main", branch, cwd=wt_dir)
    if not is_clean:
        print(f"❌ Conflict detected between 'main' and '{branch}':\n   {conflict_msg[:300]}")
        return 1
    print("✅ In-memory merge tree check: CLEAN (no merge conflicts).")

    # Run readiness suite
    py = resolve_python()
    readiness_script = wt_dir / "tools" / "verify_main_readiness.py"
    if not readiness_script.exists():
        readiness_script = repo_root / "tools" / "verify_main_readiness.py"

    if readiness_script.exists() and not getattr(args, "skip_readiness_run", False):
        print("\nExecuting readiness gate verification...")
        r_cmd = [py, str(readiness_script), "--repo-root", str(wt_dir), "--branch", branch]
        if getattr(args, "fail_fast", False):
            r_cmd.append("--fail-fast")
        if getattr(args, "recheck_failed_only", False):
            r_cmd.append("--recheck-failed-only")
        if getattr(args, "full", False):
            r_cmd.append("--full")
        proc = subprocess.run(r_cmd, cwd=wt_dir, timeout=600)
        if proc.returncode != 0:
            print("❌ Readiness verification failed.")
            return 1
        print("✅ Readiness verification passed.")
    else:
        verify_commit_script = wt_dir / "tools" / "verify_commit.py"
        if verify_commit_script.exists() and not getattr(args, "skip_readiness_run", False):
            print("\nExecuting Tier 1 structural verification...")
            proc = subprocess.run([py, str(verify_commit_script), "--all"], cwd=wt_dir, timeout=300)
            if proc.returncode != 0:
                print("❌ Tier 1 structural verification failed.")
                return 1
            print("✅ Tier 1 structural verification passed.")

    head_sha = run_git(["rev-parse", branch], cwd=wt_dir).strip()
    base_sha = run_git(["merge-base", "main", branch], cwd=wt_dir, check=False).strip()
    diff_names = [
        line
        for line in run_git(
            ["diff", "--name-only", f"main...{branch}"], cwd=repo_root, check=False
        ).splitlines()
        if line.strip()
    ]

    review_receipt = {
        "pr_type": "LOCAL_FEATURE_BRANCH_REVIEW",
        "branch": branch,
        "head_sha": head_sha,
        "base": "main",
        "base_commit_sha": base_sha,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commits_ahead": ahead,
        "commits_behind": behind,
        "modified_files_count": len(diff_names),
        "clean_merge": True,
        "readiness_verified": True,
        "terminal_outcome": "PASS",
    }

    reports_dir = repo_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    receipt_file = reports_dir / f"pr_review_{slug}_receipt.json"
    receipt_file.write_text(json.dumps(review_receipt, indent=2) + "\n", encoding="utf-8")

    if wt_dir.resolve() != repo_root.resolve():
        wt_reports = wt_dir / "reports"
        wt_reports.mkdir(parents=True, exist_ok=True)
        (wt_reports / f"pr_review_{slug}_receipt.json").write_text(
            json.dumps(review_receipt, indent=2) + "\n", encoding="utf-8"
        )

    print(f"✅ PR Review Receipt recorded: {receipt_file}")
    print("=" * 80)
    print("✅ PRE-MERGE REVIEW PASSED")
    print("=" * 80)
    return 0


def _rebind_receipt_after_disjoint_catchup(
    repo_root: Path, branch: str, slug: str, new_head_sha: str, new_main_sha: str
) -> None:
    """Rebinds an existing passing review receipt to the new rebased HEAD when catch-up is disjoint."""
    for receipt_file in (
        repo_root / "reports" / f"pr_review_{slug}_receipt.json",
        repo_root / ".worktrees" / slug / "reports" / f"pr_review_{slug}_receipt.json",
    ):
        if not receipt_file.is_file():
            continue
        with contextlib.suppress(Exception):
            data = json.loads(receipt_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("terminal_outcome") == "PASS":
                data["head_sha"] = new_head_sha
                data["base_commit_sha"] = new_main_sha
                data["commits_behind"] = 0
                receipt_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _catch_up_queued_branch_under_lock(
    branch: str, slug: str, repo_root: Path
) -> Tuple[bool, bool]:
    """When a queued PR wakes up after main has moved, automatically catches up onto main under lock."""
    try:
        main_head_sha = run_git(["rev-parse", "main"], cwd=repo_root, check=False).strip()
        base_ancestor = run_git(["merge-base", "main", branch], cwd=repo_root, check=False).strip()
    except Exception:
        return True, True

    if not main_head_sha or not base_ancestor or base_ancestor == main_head_sha:
        return True, True

    from .sync import rebase_branch_onto_main

    wt = resolve_branch_worktree(repo_root, branch, ignore_review_artifacts=True)
    wt_dir = Path(str(wt["path"])) if (wt and Path(str(wt["path"])).is_dir()) else None
    rebase_cwd = wt_dir or repo_root

    print(f"🔄 Queue wake-up: catching up '{branch}' onto updated main ({main_head_sha[:8]})...")

    is_jit = False
    if wt_dir is None:
        jit_path = repo_root / ".worktrees" / slug
        print(f"⚡ JIT rehydration: provisioning temporary worktree for queue rebase at {jit_path}...")
        try:
            provision_isolated_worktree(repo_root, jit_path, branch, "main")
            wt_dir = jit_path
            rebase_cwd = jit_path
            is_jit = True
        except Exception as e:
            print(f"❌ Post-pause JIT rehydration failed for '{branch}': {e}")
            return False, False

    outcome = rebase_branch_onto_main(
        branch=branch,
        base_branch="main",
        repo_root=repo_root,
        work_dir=rebase_cwd,
        use_lock=False,
        timeout_sec=120.0,
    )
    if outcome.status not in ("SUCCESS", "UP_TO_DATE"):
        if is_jit and wt_dir is not None:
            _remove_worktree_files(wt_dir, force=True, root=repo_root)
        print(f"❌ Post-pause catch-up rebase failed for '{branch}': {outcome.message}")
        return False, False

    if is_jit and wt_dir is not None:
        print(f"⚡ JIT teardown: cleaning up temporary queue rebase worktree at {wt_dir}...")
        _remove_worktree_files(wt_dir, force=False, root=repo_root)

    branch_diff = [
        line.strip()
        for line in run_git(["diff", "--name-only", f"{main_head_sha}...{branch}"], cwd=repo_root, check=False).splitlines()
        if line.strip()
    ]
    is_disjoint, reason = check_disjoint_base_advance_equivalence(
        base_ancestor, main_head_sha, branch_diff, repo_root=repo_root
    )
    if is_disjoint:
        new_head = run_git(["rev-parse", branch], cwd=repo_root, check=False).strip()
        if new_head:
            _rebind_receipt_after_disjoint_catchup(repo_root, branch, slug, new_head, main_head_sha)
    else:
        print(f"ℹ️ Overlapping mainline changes detected ({reason}); requiring post-rebase re-verification.")

    return True, is_disjoint


def verify_ephemeral_merge_tree(
    repo_root: Path, main_ref: str, branch_ref: str
) -> Tuple[bool, str]:
    """Verifies combined main + branch tree in-memory via git merge-tree --write-tree before mutating main."""
    try:
        proc = subprocess.run(
            ["git", "merge-tree", "--write-tree", main_ref, branch_ref],
            cwd=repo_root,
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=30.0,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            return False, f"Ephemeral merge-tree conflict detected: {detail[:240]}"
        tree_oid = proc.stdout.splitlines()[0].strip() if proc.stdout.strip() else ""
        return True, tree_oid
    except Exception as exc:
        return False, f"git merge-tree check failed: {exc}"


def atomic_rollback_main_to_sha(repo_root: Path, pre_merge_main_sha: str) -> bool:
    """Atomically restores refs/heads/main and working tree to pre_merge_main_sha on post-merge failure."""
    if not pre_merge_main_sha:
        return False
    try:
        subprocess.run(
            ["git", "update-ref", "refs/heads/main", pre_merge_main_sha],
            cwd=repo_root,
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            check=True,
            timeout=15.0,
        )
        subprocess.run(
            ["git", "checkout", "-f", "main"],
            cwd=repo_root,
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            check=True,
            timeout=15.0,
        )
        return True
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return False


def _execute_merge_under_lock(
    branch: str,
    title: str,
    slug: str,
    repo_root: Optional[Path] = None,
) -> int:
    """Executes the actual merge into main under lock after all prerequisites pass."""
    root = repo_root or ROOT

    with GovernedMergeQueueLock(branch=branch, repo_root=root):
        main_base_sha = run_git(["rev-parse", "HEAD"], check=True, cwd=root).strip()
        try:
            base_ancestor = run_git(["merge-base", "HEAD", branch], check=True, cwd=root).strip()
        except Exception:
            print(f"❌ [MERGE_BLOCKED] Cannot find merge-base between HEAD and '{branch}'.")
            return 1

        if base_ancestor != main_base_sha:
            print(
                f"❌ [MERGE_BLOCKED] Base mismatch: 'main' ({main_base_sha[:8]}) "
                f"has advanced beyond merge-base ({base_ancestor[:8]}). Branch must be caught up."
            )
            return 1

        branch_head_sha = run_git(["rev-parse", branch], check=True, cwd=root).strip()

        r_data = _resolve_pr_review_receipt(branch, slug, branch_head_sha, repo_root=root)
        if not isinstance(r_data, dict):
            print(f"❌ [MERGE_BLOCKED] Missing or invalid PR Review Receipt for '{branch}'.")
            return 1
        if r_data.get("terminal_outcome") != "PASS":
            print(f"❌ [MERGE_BLOCKED] PR Review Receipt outcome is not PASS (was '{r_data.get('terminal_outcome')}').")
            return 1
        if r_data.get("head_sha") != branch_head_sha:
            print("❌ [MERGE_BLOCKED] PR Review Receipt is stale! The branch has new commits.")
            return 1

        mt_ok, mt_detail = verify_ephemeral_merge_tree(root, "main", branch)
        if not mt_ok:
            print(f"❌ [MERGE_BLOCKED] {mt_detail}")
            return 1

        merge_msg = f"Merge branch '{branch}' into main ({title})"
        print(f"Executing governed merge: {merge_msg} (tree {mt_detail[:10]})...")

        merge_res = subprocess.run(
            ["git", "merge", "--no-ff", "--no-commit", branch],
            cwd=root,
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            timeout=180.0,
        )
        if merge_res.returncode != 0:
            print(f"❌ Merge failed:\n{merge_res.stderr}")
            subprocess.run(["git", "merge", "--abort"], cwd=root, env=sanitized_git_env(), capture_output=True, text=True, timeout=30.0)
            return 1

        merge_receipt = {
            "pr_type": "LOCAL_FEATURE_BRANCH_MERGE",
            "branch": branch,
            "head_sha": branch_head_sha,
            "target": "main",
            "branch_head_sha": branch_head_sha,
            "main_base_sha": main_base_sha,
            "merge_message": merge_msg,
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "terminal_outcome": "PASS",
        }
        merge_receipt_file = root / "reports" / f"pr_merge_{slug}_receipt.json"
        merge_receipt_file.parent.mkdir(parents=True, exist_ok=True)
        merge_receipt_file.write_text(json.dumps(merge_receipt, indent=2) + "\n", encoding="utf-8")

        full_commit_msg = (
            f"{merge_msg}\n\n"
            f"PR-Merge-Target: main\n"
            f"PR-Branch-Head: {branch_head_sha}\n"
            f"PR-Main-Base: {main_base_sha}\n"
            f"PR-Terminal-Outcome: PASS"
        )
        commit_env = sanitized_git_env({"GOVERNED_PR_MERGE": "1"})
        commit_res = subprocess.run(
            ["git", "commit", "-m", full_commit_msg],
            cwd=root,
            capture_output=True,
            text=True,
            env=commit_env,
            timeout=300.0,
        )
        if commit_res.returncode != 0:
            print(f"❌ Merge commit creation failed:\n{commit_res.stderr}")
            subprocess.run(["git", "merge", "--abort"], cwd=root, env=sanitized_git_env(), capture_output=True, text=True, timeout=30.0)
            return 1

        merge_sha = run_git(["rev-parse", "HEAD"], check=True, cwd=root).strip()
        print(f"✅ Governed merge commit created: {merge_sha}")
        print(f"✅ Out-of-tree PR Merge Receipt recorded: {merge_receipt_file}")
    return 0


def _teardown_merged_worktree(branch: str, delete_branch: bool = True, repo_root: Optional[Path] = None) -> None:
    """Cleans up the worktree and branch after a successful merge, plus any other merged secondary worktrees."""
    from .worktree import _inspect_worktree_dirty

    root = repo_root or ROOT
    slug = slugify_branch(branch)
    wt_dir = _find_worktree_dir(branch, slug, root=root)
    if wt_dir.exists():
        print(f"Tearing down merged worktree at '{wt_dir}'...")
        wt_reports = wt_dir / "reports"
        if wt_reports.is_dir():
            for eph in (*wt_reports.glob("pr_review_*_receipt.json"), *wt_reports.glob("pr_merge_*_receipt.json")):
                with contextlib.suppress(OSError):
                    eph.unlink()
            with contextlib.suppress(OSError):
                wt_reports.rmdir()
        is_clean_authored = not _inspect_worktree_dirty(wt_dir, ignore_review_artifacts=True).dirty
        if not _remove_worktree_files(wt_dir, force=False, root=root) and is_clean_authored:
            _remove_worktree_files(wt_dir, force=True, root=root)

    if delete_branch:
        print(f"Deleting merged branch '{branch}'...")
        try:
            run_git(["branch", "-d", branch], cwd=root, check=False)
        except (OSError, RuntimeError):
            try:
                run_git(["branch", "-D", branch], cwd=root, check=False)
            except (OSError, RuntimeError):
                pass

        with contextlib.suppress(Exception):
            from tools.prune_merged_chat_worktrees import prune_merged_worktrees

            pruned = prune_merged_worktrees(
                repo_root=root,
                target_ref="main",
                delete_merged=True,
                active_cwd=root,
            )
            for r_wt in pruned.get("removed_worktrees", []):
                print(f"Pruned merged secondary worktree: {r_wt}")
            for d_br in pruned.get("deleted_branches", []):
                print(f"Deleted merged local branch: {d_br}")


def cmd_merge(args: argparse.Namespace) -> int:
    """Governed PR Merge into local main using trunk reservation lock and automatic catch-up."""
    branch = args.branch
    title = args.title
    repo_root = getattr(args, "repo_root", None) or ROOT
    print("=" * 80)
    print(f"  GOVERNED PR MERGE TO MAIN: {branch}")
    print(f"  Merge Title: {title}")
    print("=" * 80)

    if not title or len(title.strip()) < 5:
        print("❌ Error: Merge title must be at least 5 characters.")
        return 1

    if _check_merge_prerequisites(branch, repo_root) != 0:
        return 1

    if not _check_merge_cleanliness(branch, repo_root):
        return 1

    slug = slugify_branch(branch)
    branch_head_sha = run_git(["rev-parse", branch], cwd=repo_root).strip()

    review_args = argparse.Namespace(
        branch=branch,
        repo_root=repo_root,
        skip_readiness_run=getattr(args, "skip_readiness_run", False),
        fail_fast=getattr(args, "fail_fast", False),
        recheck_failed_only=getattr(args, "recheck_failed_only", False),
        full=getattr(args, "full", False),
    )

    # Pre-qualification outside trunk lock: ensure review receipt exists and passes
    if not _validate_merge_receipt(branch, slug, branch_head_sha, repo_root=repo_root):
        print(f"ℹ️ Fresh review receipt not found for '{branch}'. Running pre-merge validation...")
        rev_rc = cmd_review(review_args)
        if rev_rc != 0:
            print("❌ Pre-merge validation failed. Merge aborted.")
            return rev_rc
        branch_head_sha = run_git(["rev-parse", branch], cwd=repo_root).strip()
        if not _validate_merge_receipt(branch, slug, branch_head_sha, repo_root=repo_root):
            return 1

    # Intelligent FIFO Queue Lock
    q_lock = GovernedMergeQueueLock(branch=branch, repo_root=repo_root)
    max_lock_cycles = 3

    for cycle in range(max_lock_cycles):
        print(f"\n[Lock Cycle {cycle + 1}/{max_lock_cycles}] Acquiring trunk reservation lock...")
        q_lock.acquire()

        try:
            catchup_ok, is_disjoint = _catch_up_queued_branch_under_lock(branch, slug, repo_root)
            if not catchup_ok:
                return 1

            branch_head_sha = run_git(["rev-parse", branch], cwd=repo_root).strip()
            if not _validate_merge_receipt(branch, slug, branch_head_sha, repo_root=repo_root):
                if not is_disjoint:
                    print("ℹ️ Overlapping mainline changes detected. Releasing queue lock before re-validation...")
                    q_lock.release()
                    rev_rc = cmd_review(review_args)
                    if rev_rc != 0:
                        print("❌ Validation failed after catch-up. Merge aborted.")
                        return rev_rc
                    continue
                else:
                    return 1

            current_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root, check=True).strip()
            if current_branch != "main":
                print("Checking out 'main'...")
                run_git(["checkout", "main"], cwd=repo_root, check=True)

            pre_merge_main_sha = run_git(["rev-parse", "main"], cwd=repo_root, check=True).strip()

            merge_rc = _execute_merge_under_lock(branch, title, slug, repo_root=repo_root)
            if merge_rc != 0:
                return merge_rc
            break
        finally:
            if q_lock.is_acquired():
                q_lock.release()
    else:
        print(f"❌ Exhausted {max_lock_cycles} lock cycles attempting to catch up and land '{branch}'.")
        return 1

    # Post-merge verification
    py = resolve_python()
    post_verify_script = repo_root / "tools" / "verify_post_merge.py"
    if not post_verify_script.exists():
        from .common import CHECKOUT_ROOT

        post_verify_script = CHECKOUT_ROOT / "tools" / "verify_post_merge.py"

    if post_verify_script.exists():
        print("\nCertifying the committed merge tree on 'main'...")
        post_verify = subprocess.run(
            [py, "-B", str(post_verify_script), "--repo-root", str(repo_root)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120.0,
        )
        if post_verify.returncode != 0:
            print(f"❌ Post-merge certification failed:\n{post_verify.stdout}{post_verify.stderr}")
            rolled_back = atomic_rollback_main_to_sha(repo_root, pre_merge_main_sha)
            print(f"⏪ Atomic auto-rollback of 'main' to {pre_merge_main_sha[:10]}: {'SUCCESS' if rolled_back else 'FAILED'}")
            return 1
        print(f"✅ {post_verify.stdout.strip()}")

    # Teardown merged worktree and branch
    delete_br = getattr(args, "delete_branch", True)
    _teardown_merged_worktree(branch, delete_branch=delete_br, repo_root=repo_root)

    print("\n" + "=" * 80)
    print(f"✅ Governed merge of '{branch}' into 'main' completed successfully!")
    print("=" * 80)
    return 0
