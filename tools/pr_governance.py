#!/usr/bin/env python3
"""
Local PR & Git Governance CLI Tool (Solo-Developer Workflow).

Target Pipeline:
  Feature Branch → Pre-Commit → Pre-Merge Review → Local Main → Origin Main

Enforces the repository's governed PR process for local main:
- `start`: Provision an isolated feature worktree (.worktrees/<slug>).
- `dehydrate`: Dehydrate a worktree directory while preserving branch.
- `finish`: Tear down a worktree and optionally delete branch after merge.
- `doctor`: Audit git hooks, runtime, permissions, and gate tools.
- `list`: Show candidate feature branches with ahead/behind stats and mergeability.
- `worktrees`: List all active worktrees and dirty status.
- `sync`: Synchronize branch with main (rebase + readiness qualification).
- `rebase`: Rebase branch onto main under lock.
- `review`: Run pre-merge validation (clean merge, readiness, review receipt).
- `merge`: Governed --no-ff merge into local main under trunk reservation lock.
- `promote` / `submit`: End-to-end promotion to local main under lock.
- `queue`: Inspect, enqueue, drop, drain, or break merge queue lock.

Usage:
  python tools/pr_governance.py start feat/<name>
  python tools/pr_governance.py sync <branch-name>
  python tools/pr_governance.py review <branch-name>
  python tools/pr_governance.py merge <branch-name> --title "feat(scope): <Description>"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.prefix == sys.base_prefix:
    venv_py = (
        (ROOT / ".venv" / "bin" / "python")
        if os.name != "nt"
        else (ROOT / ".venv" / "Scripts" / "python.exe")
    )
    if venv_py.exists():
        os.execv(str(venv_py), [str(venv_py)] + sys.argv)

from tools.pr_governance_core import (  # noqa: E402
    CONVENTIONAL_BRANCH_RE,
    CONVENTIONAL_COMMIT_RE,
    REQUIRED_HOOKS,
    ROOT,
    check_merge_conflict,
    cmd_dehydrate,
    cmd_doctor,
    cmd_finish,
    cmd_list,
    cmd_merge,
    cmd_promote,
    cmd_queue,
    cmd_rebase,
    cmd_review,
    cmd_start,
    cmd_submit,
    cmd_sync,
    cmd_worktree_list,
    compute_first_parent_sync,
    get_feature_branches,
    inspect_branch_status,
    resolve_python,
    run_git,
    slugify_branch,
)

__all__ = [
    "CONVENTIONAL_BRANCH_RE",
    "CONVENTIONAL_COMMIT_RE",
    "REQUIRED_HOOKS",
    "ROOT",
    "build_parser",
    "check_merge_conflict",
    "cmd_dehydrate",
    "cmd_doctor",
    "cmd_finish",
    "cmd_list",
    "cmd_merge",
    "cmd_promote",
    "cmd_queue",
    "cmd_rebase",
    "cmd_review",
    "cmd_start",
    "cmd_submit",
    "cmd_sync",
    "cmd_worktree_list",
    "compute_first_parent_sync",
    "get_feature_branches",
    "inspect_branch_status",
    "main",
    "resolve_python",
    "run_git",
    "slugify_branch",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local PR & Git Governance Tool.")
    sub = parser.add_subparsers(dest="command", required=True)

    # start (worktree provisioning)
    p_start = sub.add_parser("start", help="Provision an isolated worktree for a feature branch.")
    p_start.add_argument("branch", help="Name of feature branch (e.g. feat/my-feature).")

    # dehydrate (worktree folder removal while keeping branch)
    p_dehyd = sub.add_parser("dehydrate", help="Dehydrate an isolated worktree while preserving branch.")
    p_dehyd.add_argument("branch", help="Name of feature branch to dehydrate.")

    # finish (worktree teardown)
    p_finish = sub.add_parser("finish", help="Tear down an isolated worktree after merge.")
    p_finish.add_argument("branch", help="Name of feature branch.")
    p_finish.add_argument("--force", action="store_true", help="Force removal even if not merged.")
    p_finish.add_argument(
        "--delete-branch",
        dest="delete_branch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delete branch after worktree removal (default: True).",
    )

    # sync (Stage A: Rebase + Readiness)
    p_sync = sub.add_parser("sync", help="Synchronize branch with main (rebase + readiness).")
    p_sync.add_argument("branch", help="Name of feature branch to synchronize.")
    p_sync.add_argument("--lock-rebase", action="store_true", help="Hold trunk lock during rebase.")
    p_sync.add_argument("--skip-readiness", action="store_true", help="Skip readiness (prohibited).")
    p_sync.add_argument("--fail-fast", action="store_true", help="Halt readiness on first stage failure.")
    p_sync.add_argument(
        "--recheck-failed-only",
        action="store_true",
        help="Only re-execute stages that failed in prior run.",
    )
    p_sync.add_argument("--full", action="store_true", help="Run full readiness suite.")
    p_sync.add_argument("--dry-run", action="store_true", help="Simulate readiness verification.")

    # rebase
    p_reb = sub.add_parser("rebase", help="Rebase feature branch onto main.")
    p_reb.add_argument("branch", help="Name of feature branch to rebase.")
    p_reb.add_argument("--lock", action="store_true", help="Acquire trunk lock during rebase.")

    # review
    p_rev = sub.add_parser("review", help="Run pre-merge validation.")
    p_rev.add_argument("branch", help="Name of feature branch to review.")
    p_rev.add_argument("--skip-readiness-run", action="store_true", help="Skip running tests.")
    p_rev.add_argument("--fail-fast", action="store_true", help="Halt readiness on first stage failure.")
    p_rev.add_argument(
        "--recheck-failed-only",
        action="store_true",
        help="Only re-execute stages that failed in prior run.",
    )
    p_rev.add_argument("--full", action="store_true", help="Run full readiness suite.")

    # merge
    p_mrg = sub.add_parser("merge", help="Governed PR merge into local main.")
    p_mrg.add_argument("branch", help="Name of feature branch to merge.")
    p_mrg.add_argument("--title", required=True, help="Merge title (conventional format).")
    p_mrg.add_argument(
        "--delete-branch",
        dest="delete_branch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delete branch after merge (default: True).",
    )
    p_mrg.add_argument("--skip-readiness-run", action="store_true", help="Skip running tests.")
    p_mrg.add_argument("--fail-fast", action="store_true", help="Halt readiness on first stage failure.")
    p_mrg.add_argument(
        "--recheck-failed-only",
        action="store_true",
        help="Only re-execute stages that failed in prior run.",
    )
    p_mrg.add_argument("--full", action="store_true", help="Run full readiness suite.")

    # promote / submit
    for cmd_name, cmd_help in (
        ("promote", "Promote feature branch to main under lock."),
        ("submit", "Submit feature branch to main under lock."),
    ):
        p_ps = sub.add_parser(cmd_name, help=cmd_help)
        p_ps.add_argument("branch", help=f"Name of feature branch to {cmd_name}.")
        p_ps.add_argument("--title", required=True, help="Merge title.")
        p_ps.add_argument(
            "--delete-branch",
            dest="delete_branch",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Delete branch after merge (default: True).",
        )
        p_ps.add_argument("--skip-readiness-run", action="store_true", help="Skip running tests.")
        p_ps.add_argument("--fail-fast", action="store_true", help="Halt readiness on first stage failure.")
        p_ps.add_argument(
            "--recheck-failed-only",
            action="store_true",
            help="Only re-execute stages that failed in prior run.",
        )
        p_ps.add_argument("--full", action="store_true", help="Run full readiness suite.")

    # list
    p_lst = sub.add_parser("list", help="List candidate feature branches.")
    p_lst.add_argument("--remote", action="store_true", help="Include remote branches.")
    p_lst.add_argument("--fetch", action="store_true", help="Fetch remote branches first.")
    p_lst.add_argument("--json", action="store_true", help="Output JSON.")

    # worktrees
    sub.add_parser("worktrees", help="List all active worktrees.")

    # doctor
    sub.add_parser("doctor", help="Audit git hooks, runtime, permissions, and gate tools.")

    # queue
    p_q = sub.add_parser("queue", help="Inspect, enqueue, drop, drain, or break merge queue lock.")
    p_q.add_argument(
        "action",
        choices=["status", "enqueue", "drop", "run", "break", "break-lock"],
        default="status",
        nargs="?",
    )
    p_q.add_argument("--branch", default=None, help="Branch for enqueue/drop.")
    p_q.add_argument("--title", default=None, help="Title for enqueue.")
    p_q.add_argument("--json", action="store_true", help="Output JSON.")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    dispatch = {
        "start": cmd_start,
        "dehydrate": cmd_dehydrate,
        "finish": cmd_finish,
        "sync": cmd_sync,
        "rebase": cmd_rebase,
        "review": cmd_review,
        "merge": cmd_merge,
        "promote": cmd_promote,
        "submit": cmd_submit,
        "list": cmd_list,
        "worktrees": cmd_worktree_list,
        "doctor": cmd_doctor,
        "queue": cmd_queue,
    }
    if args.command in dispatch:
        return dispatch[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
