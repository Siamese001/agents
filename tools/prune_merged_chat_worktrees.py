#!/usr/bin/env python3
"""Post-Merge Worktree & Branch Cleanup Tool.

Enforces the Post-PR to Local Main Cleanup invariant declared in AGENTS.md and
.agents/rules/git-branch-per-chat.md:
- Following a merge into local main (exact branch-tip ancestry in main),
  removes the associated secondary worktree (`git worktree remove <path>`)
  and deletes the merged local feature branch (`git branch -d <branch>`).
- Never removes the primary repository checkout (`main` / `master`), active
  unmerged worktrees, worktrees with uncommitted changes, or the caller's own
  current working directory unless explicitly detached/safe.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master", "HEAD"})


def _clean_git_env() -> dict[str, str]:
    """Return environment with git hook override variables stripped so cwd governs."""
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_") or k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")
    }


def _run_git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run a bounded git command with shell=False and explicit timeout."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=_clean_git_env(),
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def get_main_repo_root(repo_root: Path) -> Path:
    """Resolve the primary checkout root from any worktree or repository path."""
    res = _run_git(["rev-parse", "--git-common-dir"], cwd=repo_root)
    if res.returncode == 0 and res.stdout.strip():
        common_dir = Path(res.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = (repo_root / common_dir).resolve()
        else:
            common_dir = common_dir.resolve()
        if common_dir.name == ".git":
            return common_dir.parent
    return repo_root.resolve()


def list_worktrees(repo_root: Path) -> list[dict[str, Any]]:
    """Parse `git worktree list --porcelain` into structured records."""
    res = _run_git(["worktree", "list", "--porcelain"], cwd=repo_root)
    if res.returncode != 0:
        return []

    worktrees: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw_line in res.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            if current.get("path"):
                worktrees.append(current)
            current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = Path(line[len("worktree ") :].strip()).resolve()
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD ") :].strip()
        elif line.startswith("branch "):
            ref = line[len("branch ") :].strip()
            branch_name = ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else ref
            current["branch"] = branch_name
        elif line == "detached":
            current["detached"] = True
        elif line.startswith("locked"):
            current["locked"] = True
        elif line.startswith("prunable"):
            current["prunable"] = True

    if current.get("path"):
        worktrees.append(current)
    return worktrees


def get_merged_branches(repo_root: Path, target_ref: str = "main") -> set[str]:
    """Return local branches whose tip is an ancestor of `target_ref`."""
    res = _run_git(["branch", "--merged", target_ref, "--format=%(refname:short)"], cwd=repo_root)
    if res.returncode != 0:
        return set()
    return {
        b.strip()
        for b in res.stdout.splitlines()
        if b.strip() and b.strip() not in PROTECTED_BRANCHES
    }


def is_in_repo_worktree(main_root: Path, wt_path: Path) -> bool:
    """Return True if wt_path is inside <main_root>/.worktrees/."""
    allowed_dir = (main_root.resolve() / ".worktrees").resolve()
    return allowed_dir in wt_path.resolve().parents


def is_worktree_clean(wt_path: Path) -> bool:
    """Return True if the worktree exists and has no uncommitted or untracked changes."""
    if not wt_path.is_dir():
        return True
    res = _run_git(["status", "--porcelain"], cwd=wt_path)
    return res.returncode == 0 and not res.stdout.strip()


def prune_merged_worktrees(
    repo_root: Path,
    target_ref: str = "main",
    delete_merged: bool = False,
    active_cwd: Path | None = None,
) -> dict[str, Any]:
    """Identify and optionally remove merged secondary worktrees and local branches."""
    if os.environ.get("WORKTREE_PER_CHAT_BYPASS") == "1":
        return {
            "status": "BYPASSED",
            "removed_worktrees": [],
            "deleted_branches": [],
            "skipped": [],
        }

    main_root = get_main_repo_root(repo_root)
    caller_cwd = (active_cwd or Path.cwd()).resolve()

    # Prune stale administrative worktree entries first
    if delete_merged:
        _run_git(["worktree", "prune"], cwd=main_root)

    worktrees = list_worktrees(main_root)
    merged_branches = get_merged_branches(main_root, target_ref=target_ref)

    removed_worktrees: list[str] = []
    deleted_branches: list[str] = []
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    worktree_by_branch: dict[str, dict[str, Any]] = {}
    for idx, wt in enumerate(worktrees):
        wt_path: Path = wt["path"]
        branch = wt.get("branch")
        # Never touch the primary repository checkout (entry 0 or matching main_root)
        if idx == 0 or wt_path == main_root:
            continue
        if branch:
            worktree_by_branch[branch] = wt

        if not branch or branch in PROTECTED_BRANCHES:
            continue
        if branch not in merged_branches:
            continue

        # Protect caller's active working directory from self-deletion while running inside it
        if caller_cwd == wt_path or wt_path in caller_cwd.parents:
            skipped.append({"branch": branch, "path": str(wt_path), "reason": "active_cwd"})
            continue

        if wt.get("locked"):
            skipped.append({"branch": branch, "path": str(wt_path), "reason": "locked"})
            continue

        if not is_worktree_clean(wt_path):
            skipped.append({"branch": branch, "path": str(wt_path), "reason": "dirty_worktree"})
            continue

        candidates.append({"branch": branch, "path": str(wt_path)})
        if delete_merged:
            rm_res = _run_git(["worktree", "remove", str(wt_path)], cwd=main_root)
            if rm_res.returncode == 0:
                removed_worktrees.append(str(wt_path))
                # Safe to use -D here because `branch in merged_branches` already proved
                # exact branch-tip ancestry in target_ref (`main`), whereas `-d` fails if
                # a branch has an unpushed upstream tracking ref on origin.
                br_res = _run_git(["branch", "-D", branch], cwd=main_root)
                if br_res.returncode == 0:
                    deleted_branches.append(branch)
                else:
                    skipped.append(
                        {"branch": branch, "path": str(wt_path), "reason": f"branch_delete_failed: {br_res.stderr.strip()}"}
                    )
            else:
                skipped.append(
                    {"branch": branch, "path": str(wt_path), "reason": f"worktree_remove_failed: {rm_res.stderr.strip()}"}
                )

    # Also clean up merged local branches that have no checked-out worktree
    for branch in sorted(merged_branches):
        if branch in PROTECTED_BRANCHES or branch in deleted_branches:
            continue
        if branch in worktree_by_branch:
            continue
        # Ensure primary checkout is not currently on this branch
        primary_branch = worktrees[0].get("branch") if worktrees else None
        if branch == primary_branch:
            continue
        candidates.append({"branch": branch, "path": None})
        if delete_merged:
            br_res = _run_git(["branch", "-D", branch], cwd=main_root)
            if br_res.returncode == 0:
                deleted_branches.append(branch)
            else:
                skipped.append({"branch": branch, "path": "", "reason": f"branch_delete_failed: {br_res.stderr.strip()}"})

    return {
        "status": "CLEANED" if delete_merged else "DRY_RUN",
        "target_ref": target_ref,
        "candidates": candidates,
        "removed_worktrees": removed_worktrees,
        "deleted_branches": deleted_branches,
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prune merged secondary git worktrees and feature branches.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository or worktree root path.")
    parser.add_argument("--target-ref", default="main", help="Target branch to check ancestry against (default: main).")
    parser.add_argument("--active-cwd", type=Path, default=None, help="Explicit active working directory to protect.")
    parser.add_argument("--dry-run", action="store_true", help="Report merged worktrees/branches without deleting.")
    parser.add_argument("--delete-merged", action="store_true", help="Remove merged worktrees and delete merged branches.")
    args = parser.parse_args(argv)

    delete_flag = bool(args.delete_merged and not args.dry_run)
    result = prune_merged_worktrees(
        repo_root=args.repo_root.resolve(),
        target_ref=args.target_ref,
        delete_merged=delete_flag,
        active_cwd=args.active_cwd.resolve() if args.active_cwd else None,
    )

    if delete_flag:
        for wt in result["removed_worktrees"]:
            print(f"[post-merge cleanup] Removed merged worktree: {wt}")
        for br in result["deleted_branches"]:
            print(f"[post-merge cleanup] Deleted merged branch: {br}")
    else:
        print(f"[post-merge dry-run] Candidates: {len(result['candidates'])}, Skipped: {len(result['skipped'])}")
        for cand in result["candidates"]:
            print(f"  candidate: branch={cand['branch']} worktree={cand['path']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
