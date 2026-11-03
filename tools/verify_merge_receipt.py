#!/usr/bin/env python3
"""
Pre-Merge Receipt Gatekeeper for Agents Repository.

Enforces Git Lifecycle Invariant:
  Before Git is allowed to create a merge commit, verifies that
  `reports/pr_review_<slug>_receipt.json` exists on the merging branch
  or locally in `reports/` and has `terminal_outcome: "PASS"`.

Usage:
  python tools/verify_merge_receipt.py [--branch <branch>] [--root <path>]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pr_governance_core.common import sanitized_git_env, slugify_branch


def run_git(args: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        env=sanitized_git_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def extract_merging_branch(git_dir: Path) -> Optional[str]:
    """Extracts the branch name being merged from MERGE_MSG or git status."""
    merge_msg_file = git_dir / "MERGE_MSG"
    if merge_msg_file.exists():
        first_line = merge_msg_file.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        m = re.search(r"Merge (?:remote-tracking )?branch ['\"]([^'\"]+)['\"]", first_line)
        if m:
            return m.group(1).strip()

    res = run_git(["name-rev", "--name-only", "MERGE_HEAD"])
    if res.returncode == 0:
        candidate = res.stdout.strip()
        if candidate and candidate != "undefined":
            candidate = re.sub(r"^(remotes/)?origin/", "", candidate)
            candidate = re.sub(r"[\^~].*$", "", candidate)
            return candidate

    return None


def _check_governed_merge_forgery(branch: str, repo_root: Path, local_receipt: Path) -> Optional[str]:
    from tools.pr_governance_core.merge_lock import inspect_queue_lock

    if os.environ.get("GOVERNED_PR_MERGE") == "1":
        lock_info = inspect_queue_lock(repo_root)
        if not lock_info or lock_info.branch != branch:
            if not local_receipt.exists():
                return (
                    f"[FORGED_GOVERNED_MERGE_REJECTED] GOVERNED_PR_MERGE=1 asserted without active merge queue "
                    f"reservation or valid review receipt for branch '{branch}'."
                )
    return None


def _load_receipt_data(
    branch: str, receipt_filename: str, repo_root: Path, local_receipt: Path
) -> tuple[Optional[dict], Optional[str]]:
    if local_receipt.exists():
        try:
            return json.loads(local_receipt.read_text(encoding="utf-8")), None
        except Exception as e:
            return None, f"Failed to parse local receipt {local_receipt}: {e}"

    for rev in [branch, f"origin/{branch}", "MERGE_HEAD"]:
        git_show = run_git(["show", f"{rev}:reports/{receipt_filename}"], cwd=repo_root)
        if git_show.returncode == 0 and git_show.stdout.strip():
            try:
                return json.loads(git_show.stdout), None
            except (ValueError, TypeError):
                pass

    return None, None


def verify_merge_receipt(
    branch: Optional[str] = None,
    repo_root: Path = ROOT,
) -> tuple[bool, str]:
    """Verifies that a valid passing PR review receipt exists for the branch."""
    res = run_git(["rev-parse", "--git-dir"], cwd=repo_root)
    if res.returncode != 0:
        return False, f"Not a git repository: {repo_root}"
    raw_git_dir = res.stdout.strip()
    git_dir = Path(raw_git_dir)
    if not git_dir.is_absolute():
        git_dir = (repo_root / git_dir).resolve()

    if not branch:
        branch = extract_merging_branch(git_dir)

    if not branch:
        merge_head = git_dir / "MERGE_HEAD"
        if not merge_head.exists():
            return True, "No active merge in progress (MERGE_HEAD not present)."
        return False, "Could not determine branch being merged from MERGE_MSG or MERGE_HEAD."

    slug = slugify_branch(branch)
    receipt_filename = f"pr_review_{slug}_receipt.json"
    local_receipt = repo_root / "reports" / receipt_filename

    forgery_err = _check_governed_merge_forgery(branch, repo_root, local_receipt)
    if forgery_err:
        return False, forgery_err

    rev_res = run_git(["rev-parse", branch], cwd=repo_root)
    if rev_res.returncode != 0:
        rev_res = run_git(["rev-parse", "MERGE_HEAD"], cwd=repo_root)
    actual_head = rev_res.stdout.strip() if rev_res.returncode == 0 else ""

    receipt_data, parse_err = _load_receipt_data(branch, receipt_filename, repo_root, local_receipt)
    if parse_err:
        return False, parse_err

    if receipt_data is None:
        return (
            False,
            f"Missing required PR Review Receipt for '{branch}'.\n"
            f"Expected: reports/{receipt_filename}\n"
            f"Run 'python tools/pr_governance.py review {branch}' before merging.",
        )

    terminal_outcome = receipt_data.get("terminal_outcome")
    if terminal_outcome != "PASS":
        return (
            False,
            f"PR Review Receipt for '{branch}' did not pass.\n"
            f"Terminal outcome: '{terminal_outcome}' (must be 'PASS').\n"
            f"Resolve blockers and re-run 'python tools/pr_governance.py review {branch}'.",
        )

    if actual_head:
        receipt_head = receipt_data.get("head_sha")
        if receipt_head and receipt_head != actual_head:
            return (
                False,
                f"PR Review Receipt for '{branch}' is stale!\n"
                f"Receipt was for commit {receipt_head[:8]}, but branch is at {actual_head[:8]}.\n"
                f"Re-run 'python tools/pr_governance.py review {branch}' before merging.",
            )

    return True, f"Verified valid PR Review Receipt for '{branch}' (outcome: PASS)."


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-Merge Receipt Gatekeeper.")
    parser.add_argument("--branch", default=None, help="Explicit branch name being merged.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root.")
    args = parser.parse_args(argv)

    passed, message = verify_merge_receipt(branch=args.branch, repo_root=args.root)
    if passed:
        print(f"✅ {message}")
        return 0
    else:
        print(f"❌ MERGE REJECTED:\n{message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
