#!/usr/bin/env python3
"""
Local PR & Git Governance CLI Tool (Solo-Developer Workflow).

Target Pipeline:
  Feature Branch → Pre-Commit → Pre-Merge Review → Local Main → Origin Main

Enforces the repository's governed PR process for local main:
- `start`: Provision an isolated feature worktree (.worktrees/<slug>).
- `consolidate-host`: Deduplicate clean external host worktrees and optionally start branch.
- `dehydrate`: Dehydrate a worktree directory while preserving branch.
- `finish`: Tear down a worktree and optionally delete branch after merge.
- `doctor`: Audit git hooks, runtime, permissions, and gate tools.
- `list`: Show candidate feature branches with ahead/behind stats and mergeability.
- `worktrees`: List all active worktrees and dirty status.
- `sync`: Synchronize branch with main (rebase + readiness qualification).
- `rebase`: Rebase branch onto main under lock.
- `review`: Run pre-merge validation (clean merge, readiness, review receipt).
- `merge`: Governed --no-ff merge into local main under trunk reservation lock.
- `promote` / `submit`: End-to-end promotion or `--stage-only` overnight staging.
- `queue`: Inspect, enqueue, drop, drain, or break merge queue lock.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))


def _bootstrap_primary_venv() -> None:
    if sys.prefix != sys.base_prefix or os.environ.get("AGENTS_PR_GOV_BOOTSTRAPPED") == "1":
        return
    candidates = [_SCRIPT_ROOT]
    try:
        proc = subprocess.run(
            ["git", "-C", str(_SCRIPT_ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            common_dir = Path(proc.stdout.strip()).resolve()
            primary_root = common_dir.parent if common_dir.name == ".git" else common_dir
            if primary_root not in candidates:
                candidates.append(primary_root)
    except (OSError, subprocess.SubprocessError):  # guardian: allow-silent-swallow -- best-effort venv lookup
        pass

    for root in candidates:
        venv_py = (
            (root / ".venv" / "bin" / "python")
            if os.name != "nt"
            else (root / ".venv" / "Scripts" / "python.exe")
        )
        if venv_py.is_file() and os.access(venv_py, os.X_OK):
            env = dict(os.environ, AGENTS_PR_GOV_BOOTSTRAPPED="1")
            os.execve(str(venv_py), [str(venv_py), __file__, *sys.argv[1:]], env)


_bootstrap_primary_venv()

from tools.pr_governance_core import (  # noqa: E402
    CONVENTIONAL_BRANCH_RE,
    CONVENTIONAL_COMMIT_RE,
    REQUIRED_HOOKS,
    ROOT,
    check_merge_conflict,
    cmd_consolidate_host,
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
    derive_branch_merge_title,
    get_feature_branches,
    inspect_branch_status,
    resolve_effective_repo_root,
    resolve_python,
    run_git,
    slugify_branch,
    stage_overnight_branch,
)

__all__ = [
    "CONVENTIONAL_BRANCH_RE",
    "CONVENTIONAL_COMMIT_RE",
    "REQUIRED_HOOKS",
    "ROOT",
    "build_parser",
    "check_merge_conflict",
    "cmd_consolidate_host",
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
    "derive_branch_merge_title",
    "get_feature_branches",
    "inspect_branch_status",
    "main",
    "resolve_effective_repo_root",
    "resolve_python",
    "run_git",
    "slugify_branch",
    "stage_overnight_branch",
]


def _add_workspace_flags(target: argparse.ArgumentParser) -> None:
    target.add_argument(
        "-C",
        "--worktree",
        default=argparse.SUPPRESS,
        help="Stateless target worktree or repository directory.",
    )
    target.add_argument(
        "--repo-root",
        default=argparse.SUPPRESS,
        help="Explicit primary repository root override.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local PR & Git Governance Tool.")
    _add_workspace_flags(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Provision an isolated worktree for a feature branch.")
    _add_workspace_flags(p_start)
    p_start.add_argument("branch", help="Name of feature branch (e.g. feat/my-feature).")
    p_start.add_argument(
        "--consolidate-host",
        action="store_true",
        help="Deduplicate clean merged external chat worktrees before provisioning.",
    )

    p_cons = sub.add_parser("consolidate-host", help="Deduplicate clean external chat worktrees.")
    _add_workspace_flags(p_cons)
    p_cons.add_argument("branch", nargs="?", default=None, help="Optional feature branch to provision.")

    p_dehyd = sub.add_parser("dehydrate", help="Dehydrate an isolated worktree while preserving branch.")
    _add_workspace_flags(p_dehyd)
    p_dehyd.add_argument("branch", help="Name of feature branch to dehydrate.")

    p_finish = sub.add_parser("finish", help="Tear down an isolated worktree after merge.")
    _add_workspace_flags(p_finish)
    p_finish.add_argument("branch", help="Name of feature branch.")
    p_finish.add_argument("--force", action="store_true", help="Force removal even if not merged.")
    p_finish.add_argument(
        "--delete-branch",
        dest="delete_branch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delete branch after worktree removal (default: True).",
    )

    p_sync = sub.add_parser("sync", help="Synchronize branch with main (rebase + readiness).")
    _add_workspace_flags(p_sync)
    p_sync.add_argument("branch", help="Name of feature branch to synchronize.")
    p_sync.add_argument("--lock-rebase", action="store_true", help="Hold trunk lock during rebase.")
    p_sync.add_argument("--skip-readiness", action="store_true", help="Skip readiness (prohibited).")
    p_sync.add_argument("--fail-fast", action="store_true", help="Halt readiness on first stage failure.")
    p_sync.add_argument("--recheck-failed-only", action="store_true", help="Re-execute failed stages only.")
    p_sync.add_argument("--full", action="store_true", help="Run full readiness suite.")
    p_sync.add_argument("--dry-run", action="store_true", help="Simulate readiness verification.")

    p_reb = sub.add_parser("rebase", help="Rebase feature branch onto main.")
    _add_workspace_flags(p_reb)
    p_reb.add_argument("branch", help="Name of feature branch to rebase.")
    p_reb.add_argument("--lock", action="store_true", help="Acquire trunk lock during rebase.")

    p_rev = sub.add_parser("review", help="Run pre-merge validation.")
    _add_workspace_flags(p_rev)
    p_rev.add_argument("branch", help="Name of feature branch to review.")
    p_rev.add_argument("--skip-readiness-run", action="store_true", help="Skip running tests.")
    p_rev.add_argument("--fail-fast", action="store_true", help="Halt readiness on first stage failure.")
    p_rev.add_argument("--recheck-failed-only", action="store_true", help="Re-execute failed stages only.")
    p_rev.add_argument("--full", action="store_true", help="Run full readiness suite.")

    p_mrg = sub.add_parser("merge", help="Governed PR merge into local main.")
    _add_workspace_flags(p_mrg)
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
    p_mrg.add_argument("--recheck-failed-only", action="store_true", help="Re-execute failed stages only.")
    p_mrg.add_argument("--full", action="store_true", help="Run full readiness suite.")

    for cmd_name, cmd_help in (
        ("promote", "Promote feature branch to main under lock."),
        ("submit", "Submit feature branch to main (or --stage-only overnight)."),
    ):
        p_ps = sub.add_parser(cmd_name, help=cmd_help)
        _add_workspace_flags(p_ps)
        p_ps.add_argument("branch", help=f"Name of feature branch to {cmd_name}.")
        p_ps.add_argument("--title", default=None, help="Optional merge title (auto-derived if omitted).")
        p_ps.add_argument(
            "--stage-only",
            action="store_true",
            help="Rebase, review, and stage branch for morning approval without mutating main.",
        )
        p_ps.add_argument(
            "--delete-branch",
            dest="delete_branch",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Delete branch after merge (default: True).",
        )
        p_ps.add_argument("--skip-readiness-run", action="store_true", help="Skip running tests.")
        p_ps.add_argument("--fail-fast", action="store_true", help="Halt readiness on first stage failure.")
        p_ps.add_argument("--recheck-failed-only", action="store_true", help="Re-execute failed stages only.")
        p_ps.add_argument("--full", action="store_true", help="Run full readiness suite.")

    p_lst = sub.add_parser("list", help="List candidate feature branches.")
    _add_workspace_flags(p_lst)
    p_lst.add_argument("--remote", action="store_true", help="Include remote branches.")
    p_lst.add_argument("--fetch", action="store_true", help="Fetch remote branches first.")
    p_lst.add_argument("--json", action="store_true", help="Output JSON.")

    p_wt = sub.add_parser("worktrees", help="List all active worktrees.")
    _add_workspace_flags(p_wt)

    p_doc = sub.add_parser("doctor", help="Audit git hooks, runtime, permissions, and gate tools.")
    _add_workspace_flags(p_doc)

    p_q = sub.add_parser("queue", help="Inspect, enqueue, drop, drain, or break merge queue lock.")
    _add_workspace_flags(p_q)
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "worktree", None) or getattr(args, "repo_root", None):
        args.repo_root = resolve_effective_repo_root(args)
    dispatch = {
        "start": cmd_start,
        "consolidate-host": cmd_consolidate_host,
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
