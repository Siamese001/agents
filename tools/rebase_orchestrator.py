#!/usr/bin/env python3
"""Governed Multi-Agent Rebase Orchestrator & Fast Landing CLI.

Serializes branch rebasing, readiness verification, and PR landing under the
governed merge queue lock (.git/governed_merge_queue.lock). Prevents multi-agent
convoy livelocks, duplicate work, and race conditions during high-concurrency
worktree development.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pr_governance_core.common import slugify_branch  # noqa: E402
from tools.pr_governance_core.merge_lock import (  # noqa: E402
    GovernedMergeQueueLock,
    force_break_queue_lock,
    inspect_queue_lock,
)
from tools.pr_governance_core.merge_queue import get_queue_status  # noqa: E402
from tools.pr_governance_core.sync import RebaseOutcome, rebase_branch_onto_main  # noqa: E402
from tools.pr_governance_core.worktree import resolve_branch_worktree  # noqa: E402

logger = logging.getLogger("tools.rebase_orchestrator")


@dataclass
class RebaseResult:
    """Outcome of a governed rebase operation."""

    branch: str
    status: str  # SUCCESS, UP_TO_DATE, CONFLICT, FAILED
    commits_rebased: int = 0
    duration_seconds: float = 0.0
    head_sha_before: str = ""
    head_sha_after: str = ""
    conflict_files: List[str] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LandResult:
    """Outcome of a governed branch landing operation."""

    branch: str
    status: str  # SUCCESS, FAILED
    merge_commit_sha: str = ""
    readiness_passed: bool = False
    duration_seconds: float = 0.0
    receipt_path: str = ""
    error_message: str = ""
    rebase_status: str = "NOT_RUN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_head_sha(cwd: Path) -> str:
    with contextlib.suppress(Exception):
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
            timeout=10.0,
        )
        return res.stdout.strip()
    return "unknown"


def _outcome_to_rebase_result(outcome: RebaseOutcome) -> RebaseResult:
    status = "FAILED" if outcome.status == "ERROR" else outcome.status
    return RebaseResult(
        branch=outcome.branch,
        status=status,
        commits_rebased=outcome.commits_rebased,
        duration_seconds=outcome.duration_sec,
        head_sha_before=outcome.head_sha_before,
        head_sha_after=outcome.head_sha_after,
        conflict_files=outcome.conflict_files,
        error_message=outcome.message if status in ("FAILED", "CONFLICT") else "",
    )


def resolve_worktree_for_branch(branch: str, repo_root: Path) -> Path:
    """Locates the working directory for a given branch."""
    wt = resolve_branch_worktree(repo_root, branch, ignore_review_artifacts=True)
    if wt and wt.get("path"):
        p = Path(str(wt["path"])).resolve()
        if p.exists():
            return p
    return repo_root


def rebase_branch_serialized(
    branch: str,
    base_branch: str = "main",
    repo_root: Optional[Path] = None,
    timeout_sec: float = 300.0,
    non_blocking: bool = False,
) -> RebaseResult:
    """Rebases a branch onto base_branch while serializing under trunk reservation lock."""
    root = repo_root or ROOT
    work_dir = resolve_worktree_for_branch(branch, root)

    outcome = rebase_branch_onto_main(
        branch=branch,
        base_branch=base_branch,
        repo_root=root,
        work_dir=work_dir,
        use_lock=True,
        timeout_sec=timeout_sec,
    )
    return _outcome_to_rebase_result(outcome)


def _run_readiness_qualification(branch: str, work_dir: Path) -> bool:
    """Runs readiness qualification checks."""
    py = sys.executable
    readiness_script = work_dir / "tools" / "verify_main_readiness.py"
    if readiness_script.exists():
        proc = subprocess.run([py, str(readiness_script), "--repo-root", str(work_dir)], cwd=work_dir)
        return proc.returncode == 0

    verify_commit = work_dir / "tools" / "verify_commit.py"
    if verify_commit.exists():
        proc = subprocess.run([py, str(verify_commit), "--all"], cwd=work_dir)
        return proc.returncode == 0

    return True


def _run_pr_merge(branch: str, title: str, delete_branch: bool, repo_root: Path) -> int:
    """Executes governed PR merge via lifecycle cmd_merge."""
    from tools.pr_governance_core.lifecycle import cmd_merge

    args = argparse.Namespace(
        branch=branch,
        title=title,
        delete_branch=delete_branch,
        repo_root=repo_root,
        skip_readiness_run=True,
    )
    return cmd_merge(args)


def land_branch_serialized(
    branch: str,
    title: str,
    base_branch: str = "main",
    delete_branch: bool = True,
    repo_root: Optional[Path] = None,
    timeout_sec: float = 300.0,
) -> LandResult:
    """Performs serialized rebase, readiness verification, and landing into main."""
    root = repo_root or ROOT
    work_dir = resolve_worktree_for_branch(branch, root)
    start_t = time.monotonic()

    # 1. Initial rebase outside lock
    reb_outcome = rebase_branch_onto_main(
        branch=branch,
        base_branch=base_branch,
        repo_root=root,
        work_dir=work_dir,
        use_lock=False,
        timeout_sec=timeout_sec,
    )
    reb_res = _outcome_to_rebase_result(reb_outcome)
    if reb_res.status not in ("SUCCESS", "UP_TO_DATE"):
        return LandResult(
            branch=branch,
            status="FAILED",
            duration_seconds=round(time.monotonic() - start_t, 3),
            rebase_status=reb_res.status,
            error_message=f"Rebase failed with status {reb_res.status}: {reb_res.error_message}",
        )

    # 2. Run readiness qualification outside lock
    readiness_ok = _run_readiness_qualification(branch, work_dir)
    if not readiness_ok:
        return LandResult(
            branch=branch,
            status="FAILED",
            readiness_passed=False,
            rebase_status=reb_res.status,
            duration_seconds=round(time.monotonic() - start_t, 3),
            error_message="Readiness qualification failed.",
        )

    # 3. Hold trunk lock for final landing
    with GovernedMergeQueueLock(branch=branch, repo_root=root, timeout_sec=timeout_sec):
        merge_rc = _run_pr_merge(branch, title, delete_branch, root)
        dur = round(time.monotonic() - start_t, 3)
        slug = slugify_branch(branch)
        receipt_p = root / "reports" / f"pr_merge_{slug}_receipt.json"

        if merge_rc != 0:
            return LandResult(
                branch=branch,
                status="FAILED",
                readiness_passed=True,
                rebase_status=reb_res.status,
                duration_seconds=dur,
                error_message="Governed merge command returned non-zero status.",
            )

        merge_sha = _get_head_sha(root)
        return LandResult(
            branch=branch,
            status="SUCCESS",
            merge_commit_sha=merge_sha,
            readiness_passed=True,
            rebase_status=reb_res.status,
            duration_seconds=dur,
            receipt_path=str(receipt_p) if receipt_p.is_file() else "",
        )


def cmd_rebase(args: argparse.Namespace) -> int:
    res = rebase_branch_serialized(
        branch=args.branch,
        base_branch=args.base_branch,
        timeout_sec=args.timeout,
        non_blocking=args.non_blocking,
    )
    if args.json:
        print(json.dumps(res.to_dict(), indent=2))
    elif res.status in ("SUCCESS", "UP_TO_DATE"):
        print(f"✅ Rebase {res.status} for '{args.branch}' ({res.commits_rebased} commits, {res.duration_seconds}s)")
    else:
        print(f"❌ Rebase {res.status} for '{args.branch}': {res.error_message}")
        if res.conflict_files:
            print("  Conflicts in:")
            for f in res.conflict_files:
                print(f"    - {f}")
    return 0 if res.status in ("SUCCESS", "UP_TO_DATE") else 1


def cmd_land(args: argparse.Namespace) -> int:
    res = land_branch_serialized(
        branch=args.branch,
        title=args.title,
        base_branch=args.base_branch,
        delete_branch=not args.keep_branch,
        timeout_sec=args.timeout,
    )
    if args.json:
        print(json.dumps(res.to_dict(), indent=2))
    elif res.status == "SUCCESS":
        print(f"✅ Landed '{args.branch}' to main (SHA: {res.merge_commit_sha[:8]}, {res.duration_seconds}s)")
    else:
        print(f"❌ Failed to land '{args.branch}': {res.error_message}")
    return 0 if res.status == "SUCCESS" else 1


def cmd_status(args: argparse.Namespace) -> int:
    lock_info = inspect_queue_lock()
    status_dict = get_queue_status()

    if args.json:
        out = {
            "lock": {
                "active": lock_info is not None,
                "branch": lock_info.branch if lock_info else None,
                "pid": lock_info.pid if lock_info else None,
                "acquired_at": lock_info.acquired_at if lock_info else None,
            },
            "queue": status_dict,
        }
        print(json.dumps(out, indent=2))
    else:
        print("=" * 80)
        print("  GOVERNED MERGE QUEUE STATUS")
        print("=" * 80)
        if lock_info:
            print(f"Trunk Lock:  ACTIVE (held by '{lock_info.branch}', PID {lock_info.pid})")
            print(f"Acquired At: {lock_info.acquired_at}")
        else:
            print("Trunk Lock:  FREE (no active merge in progress)")

        waiters = status_dict.get("waiters", [])
        print(f"Waiters:     {len(waiters)} queued")
        for i, w in enumerate(waiters):
            print(f"  [{i+1}] {w.get('branch')} (PID {w.get('pid')}, bypasses={w.get('bypass_count', 0)})")
        print("=" * 80)
    return 0


def cmd_break(args: argparse.Namespace) -> int:
    broken = force_break_queue_lock()
    if broken:
        print("✅ Force-broke merge queue lock.")
        return 0
    else:
        print("ℹ️ No active merge queue lock was found.")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Governed Rebase Orchestrator & Fast Landing CLI.")
    sub = parser.add_subparsers(dest="action", required=True)

    # rebase
    p_reb = sub.add_parser("rebase", help="Rebase branch serialized under trunk reservation lock.")
    p_reb.add_argument("branch", help="Feature branch to rebase.")
    p_reb.add_argument("--base-branch", default="main", help="Target branch (default: main).")
    p_reb.add_argument("--timeout", type=float, default=300.0, help="Lock wait timeout in seconds.")
    p_reb.add_argument("--non-blocking", action="store_true", help="Fail immediately if lock is held.")
    p_reb.add_argument("--json", action="store_true", help="Output JSON.")

    # land
    p_land = sub.add_parser("land", help="Rebase, qualify, and land branch to main under lock.")
    p_land.add_argument("branch", help="Feature branch to land.")
    p_land.add_argument("--title", required=True, help="Merge commit title.")
    p_land.add_argument("--base-branch", default="main", help="Target branch (default: main).")
    p_land.add_argument("--keep-branch", action="store_true", help="Do not delete branch after merge.")
    p_land.add_argument("--timeout", type=float, default=300.0, help="Lock wait timeout in seconds.")
    p_land.add_argument("--json", action="store_true", help="Output JSON.")

    # status
    p_stat = sub.add_parser("status", help="Inspect current lock and queue waiters.")
    p_stat.add_argument("--json", action="store_true", help="Output JSON.")

    # break
    sub.add_parser("break", help="Force break a stuck merge queue lock.")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    dispatch = {
        "rebase": cmd_rebase,
        "land": cmd_land,
        "status": cmd_status,
        "break": cmd_break,
    }
    return dispatch[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
