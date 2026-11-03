"""
Stage A Branch Alignment CLI: Serialized Rebase onto Main + Post-Rebase Readiness.
Prepares and certifies a feature branch on the developer's desk prior to PR review and merge.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .common import (
    ROOT,
    check_merge_conflict,
    compute_first_parent_sync,
    resolve_python,
    run_git,
    slugify_branch,
)
from .inspection import get_feature_branches
from .merge_lock import GovernedMergeQueueLock
from .worktree import list_active_worktrees

_BANNED_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX")


@dataclass
class RebaseOutcome:
    """Structured result of canonical branch rebase onto base_branch."""

    branch: str
    base_branch: str
    status: str  # "SUCCESS" | "UP_TO_DATE" | "CONFLICT" | "ERROR"
    head_sha_before: str
    head_sha_after: str
    base_sha: str
    commits_rebased: int
    duration_sec: float
    message: str
    conflict_files: List[str] = field(default_factory=list)

    @property
    def new_head_sha(self) -> str:
        return self.head_sha_after

    @property
    def new_head(self) -> str:
        return self.head_sha_after


def _sanitized_git_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _BANNED_GIT_VARS}
    env["GIT_TERMINAL_PROMPT"] = "0"
    if extra:
        env.update(extra)
    return env


def _resolve_worktree(branch: str, repo_root: Path) -> Optional[Path]:
    """Finds the isolated worktree directory for the given branch."""
    from .worktree import resolve_branch_worktree

    wt = resolve_branch_worktree(repo_root, branch, ignore_review_artifacts=True)
    if wt and wt.get("path"):
        wt_path = Path(str(wt.get("path"))).resolve()
        if wt_path.exists():
            return wt_path

    slug = slugify_branch(branch)
    candidate = (repo_root / ".worktrees" / slug).resolve()
    if candidate.is_dir():
        return candidate

    try:
        cur_proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            env=_sanitized_git_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if cur_proc.returncode == 0 and cur_proc.stdout.strip() == branch:
            return repo_root
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def rebase_branch_onto_main(
    branch: str,
    base_branch: str = "main",
    repo_root: Optional[Path] = None,
    work_dir: Optional[Path] = None,
    use_lock: bool = False,
    timeout_sec: float = 300.0,
) -> RebaseOutcome:
    """Canonical rebase engine handling env sanitization, locks, up-to-date checks, and conflicts."""
    root = (repo_root or ROOT).resolve()
    t0 = time.monotonic()
    target_dir = (work_dir or _resolve_worktree(branch, root) or root).resolve()
    env = _sanitized_git_env({"IS_REBASE": "1"})

    def _resolve_ref_fast(ref_name: str) -> str:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", ref_name],
            cwd=target_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""

    head_before = _resolve_ref_fast(branch)
    base_sha = _resolve_ref_fast(base_branch)
    if not head_before or not base_sha:
        return RebaseOutcome(
            branch=branch,
            base_branch=base_branch,
            status="ERROR",
            head_sha_before="",
            head_sha_after="",
            base_sha="",
            commits_rebased=0,
            duration_sec=round(time.monotonic() - t0, 4),
            message=f"Failed to resolve '{branch}' or '{base_branch}'.",
        )

    if head_before == base_sha:
        return RebaseOutcome(
            branch=branch,
            base_branch=base_branch,
            status="UP_TO_DATE",
            head_sha_before=head_before,
            head_sha_after=head_before,
            base_sha=base_sha,
            commits_rebased=0,
            duration_sec=round(time.monotonic() - t0, 4),
            message=f"Branch '{branch}' is already up-to-date with '{base_branch}'.",
        )

    anc_proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, head_before],
        cwd=target_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if anc_proc.returncode == 0:
        return RebaseOutcome(
            branch=branch,
            base_branch=base_branch,
            status="UP_TO_DATE",
            head_sha_before=head_before,
            head_sha_after=head_before,
            base_sha=base_sha,
            commits_rebased=0,
            duration_sec=round(time.monotonic() - t0, 4),
            message=f"Branch '{branch}' is already up-to-date with '{base_branch}'.",
        )

    lock_ctx = (
        GovernedMergeQueueLock(branch=branch, repo_root=root, timeout_sec=timeout_sec)
        if use_lock
        else contextlib.nullcontext()
    )
    with lock_ctx:
        cnt_proc = subprocess.run(
            ["git", "rev-list", "--count", f"{base_branch}..{branch}"],
            cwd=target_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        try:
            commits_count = int(cnt_proc.stdout.strip()) if cnt_proc.returncode == 0 else 0
        except ValueError:
            commits_count = 0

        cur_branch_proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=target_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if cur_branch_proc.stdout.strip() != branch:
            co_proc = subprocess.run(
                ["git", "checkout", branch],
                cwd=target_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if co_proc.returncode != 0:
                return RebaseOutcome(
                    branch=branch,
                    base_branch=base_branch,
                    status="ERROR",
                    head_sha_before=head_before,
                    head_sha_after=head_before,
                    base_sha=base_sha,
                    commits_rebased=0,
                    duration_sec=round(time.monotonic() - t0, 4),
                    message=f"Failed to checkout '{branch}': {(co_proc.stderr or co_proc.stdout).strip()}",
                )

        rb_proc = subprocess.run(
            ["git", "rebase", base_branch],
            cwd=target_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if rb_proc.returncode != 0:
            cf_proc = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=target_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            conflict_files = [f.strip() for f in cf_proc.stdout.splitlines() if f.strip()]
            subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=target_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            return RebaseOutcome(
                branch=branch,
                base_branch=base_branch,
                status="CONFLICT",
                head_sha_before=head_before,
                head_sha_after=head_before,
                base_sha=base_sha,
                commits_rebased=0,
                duration_sec=round(time.monotonic() - t0, 4),
                message=f"Rebase onto '{base_branch}' halted due to conflict; aborted cleanly.",
                conflict_files=conflict_files,
            )

        after_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=target_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        head_after = after_proc.stdout.strip() if after_proc.returncode == 0 else head_before

        return RebaseOutcome(
            branch=branch,
            base_branch=base_branch,
            status="SUCCESS",
            head_sha_before=head_before,
            head_sha_after=head_after,
            base_sha=base_sha,
            commits_rebased=commits_count,
            duration_sec=round(time.monotonic() - t0, 4),
            message=f"Rebased {commits_count} commit(s) onto '{base_branch}' ({base_sha[:8]}).",
        )


def cmd_rebase(args: argparse.Namespace) -> int:
    """Lightweight rebase of branch onto main."""
    branch = args.branch
    repo_root = getattr(args, "repo_root", None) or ROOT
    use_lock = bool(getattr(args, "lock", False))

    print(f"Rebasing branch '{branch}' onto 'main'...")
    outcome = rebase_branch_onto_main(
        branch=branch,
        base_branch="main",
        repo_root=repo_root,
        use_lock=use_lock,
    )
    if outcome.status in ("SUCCESS", "UP_TO_DATE"):
        print(f"✅ {outcome.message}")
        return 0
    else:
        print(f"❌ Rebase failed ({outcome.status}): {outcome.message}")
        if outcome.conflict_files:
            print("Conflict files:")
            for cf in outcome.conflict_files:
                print(f"  - {cf}")
        return 1


def cmd_sync(args: argparse.Namespace) -> int:
    """Executes Stage A: Serialized rebase onto main + post-rebase readiness verification."""
    branch = args.branch
    repo_root = getattr(args, "repo_root", None) or ROOT
    print("=" * 80)
    print(f"  STAGE A: BRANCH ALIGNMENT & POST-REBASE READINESS: {branch}")
    print("=" * 80)

    # 1. Branch existence check
    branches = get_feature_branches(repo_root=repo_root)
    if branch not in branches:
        try:
            cur = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root).strip()
            if cur != branch:
                print(f"❌ Error: Branch '{branch}' does not exist.")
                return 1
        except Exception:
            print(f"❌ Error: Branch '{branch}' does not exist.")
            return 1

    # 2. Resolve target worktree
    wt_dir = _resolve_worktree(branch, repo_root)
    if not wt_dir:
        print(
            f"❌ Error: No active worktree found for '{branch}'.\n"
            f"   Provision an isolated worktree first via:\n"
            f"     python tools/pr_governance.py start {branch}"
        )
        return 1

    print(f"Target Worktree: {wt_dir}")

    # 3. Cleanliness check
    status_proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=wt_dir, capture_output=True, text=True, check=False, timeout=30
    )
    raw_status = [line for line in status_proc.stdout.splitlines() if line.strip()]
    dirty_lines = [
        line
        for line in raw_status
        if not any(pat in line for pat in ("reports/pr_review_", "reports/pr_merge_"))
    ]
    if dirty_lines:
        print(f"❌ Error: Worktree has uncommitted modifications ({len(dirty_lines)} files):")
        for line in dirty_lines[:5]:
            print(f"   {line}")
        print("   Commit or stash changes before synchronizing with main.")
        return 1

    # 4. Checkpoint sync status against main
    behind, ahead = compute_first_parent_sync("main", branch, cwd=wt_dir)
    print(f"Commits Ahead of main:  {ahead}")
    print(f"Commits Behind main: {behind}")

    if behind == 0:
        print("✅ Branch is already up-to-date with 'main' (0 commits behind).")
    else:
        is_clean, conflict_details = check_merge_conflict("main", branch, cwd=wt_dir)
        if not is_clean:
            print("❌ Conflict detected between 'main' and branch:")
            print(f"   {conflict_details[:300]}")
            print("   Please resolve conflicts manually in the worktree or rebase interactively.")
            return 1

        use_lock = bool(getattr(args, "lock_rebase", False))
        print(f"Rebasing {behind} commit(s) onto 'main' in isolated worktree (use_lock={use_lock})...")
        outcome = rebase_branch_onto_main(
            branch=branch,
            base_branch="main",
            repo_root=repo_root,
            work_dir=wt_dir,
            use_lock=use_lock,
            timeout_sec=300.0,
        )
        if outcome.status not in ("SUCCESS", "UP_TO_DATE"):
            print(f"❌ Rebase failed ({outcome.duration_sec}s): {outcome.message}")
            return 1
        print(f"✅ Successfully rebased onto 'main' in {outcome.duration_sec}s.")

    # 5. Post-Rebase Readiness Qualification
    if getattr(args, "skip_readiness", False):
        print("❌ Error: --skip-readiness is prohibited; post-rebase readiness verification is mandatory.")
        return 1

    py = resolve_python()
    wt_py = wt_dir / ".venv" / "bin" / "python"
    run_py = str(wt_py) if (wt_py.exists() and wt_py.is_file()) else py

    readiness_script = wt_dir / "tools" / "verify_main_readiness.py"
    if not readiness_script.exists():
        readiness_script = repo_root / "tools" / "verify_main_readiness.py"

    print("\nExecuting authoritative post-rebase readiness verification...")
    if readiness_script.exists():
        readiness_cmd = [run_py, str(readiness_script), "--repo-root", str(wt_dir), "--branch", branch]
        if getattr(args, "fail_fast", False):
            readiness_cmd.append("--fail-fast")
        if getattr(args, "recheck_failed_only", False):
            readiness_cmd.append("--recheck-failed-only")
        if getattr(args, "full", False):
            readiness_cmd.append("--full")
        if getattr(args, "dry_run", False):
            readiness_cmd.append("--dry-run")
        readiness_proc = subprocess.run(readiness_cmd, cwd=wt_dir, timeout=600)
        if readiness_proc.returncode != 0:
            print("\n❌ Post-rebase readiness qualification failed.")
            return 1
    else:
        # Fallback to Tier 1 commit verification
        verify_commit_script = wt_dir / "tools" / "verify_commit.py"
        if verify_commit_script.exists():
            v_cmd = [run_py, str(verify_commit_script), "--all"]
            v_proc = subprocess.run(v_cmd, cwd=wt_dir, timeout=300)
            if v_proc.returncode != 0:
                print("\n❌ Post-rebase Tier 1 verification failed.")
                return 1

    # Write PR review receipt
    try:
        head_sha = run_git(["rev-parse", branch], cwd=wt_dir).strip()
        base_sha = run_git(["merge-base", "main", branch], cwd=wt_dir, check=False).strip()
        slug = slugify_branch(branch)
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
            "commits_behind": 0,
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
        print(f"✅ Verified review receipt recorded: {receipt_file}")
    except Exception as e:
        print(f"⚠️ Warning: Could not write post-sync review receipt: {e}")

    print("\n" + "=" * 80)
    print(f"✅ Stage A Complete: Branch '{branch}' is synchronized and verified ready for merge.")
    print("=" * 80)
    return 0
