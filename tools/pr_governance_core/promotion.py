"""
Unified PR promotion, overnight staging, and host consolidation workflow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Optional

from .common import (
    CONVENTIONAL_COMMIT_RE,
    ROOT,
    compute_first_parent_sync,
    run_git,
    sanitized_git_env,
    slugify_branch,
)


def resolve_effective_repo_root(args: argparse.Namespace) -> Path:
    """Resolve the primary repository root from --repo-root, -C/--worktree, or ROOT."""
    hint = getattr(args, "repo_root", None) or getattr(args, "worktree", None)
    if hint is None:
        return ROOT
    hint_path = Path(hint).resolve()
    probe_dir = hint_path if hint_path.is_dir() else hint_path.parent
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(probe_dir),
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            common_dir = Path(proc.stdout.strip()).resolve()
            return common_dir.parent if common_dir.name == ".git" else common_dir
    except Exception:  # guardian: allow-silent-swallow -- fallback to hint path
        pass
    return hint_path


def derive_branch_merge_title(branch: str, repo_root: Path) -> str:
    """Derive a conventional merge commit title from the latest branch commit subject."""
    prefix_raw = branch.split("/", 1)[0].lower() if "/" in branch else "chore"
    prefix_map = {"feature": "feat", "enhance": "feat", "ingest": "feat", "audio": "feat", "transcript": "feat"}
    conv_type = prefix_map.get(prefix_raw, prefix_raw)
    if conv_type not in {"feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"}:
        conv_type = "chore"

    subject = ""
    try:
        subject = run_git(["log", "-1", "--format=%s", branch], cwd=repo_root, check=False).strip()
    except Exception:  # guardian: allow-silent-swallow -- fallback to synthesized title
        subject = ""

    if subject and CONVENTIONAL_COMMIT_RE.match(subject) and not subject.startswith("Merge "):
        return subject
    clean_desc = subject if len(subject) >= 5 else f"promote {branch} changes"
    return f"{conv_type}(companion): {clean_desc}"


def _prune_zero_commit_noop_branch(branch: str, repo_root: Path) -> Optional[int]:
    """Automatically tear down clean worktrees that made zero commits ahead of main."""
    import contextlib

    from .common import sanitized_git_env
    from .lifecycle import _check_merge_cleanliness, _teardown_merged_worktree
    from .worktree import clear_branch_worktree_cache, resolve_branch_worktree

    _, ahead = compute_first_parent_sync("main", branch, cwd=repo_root)
    if ahead != 0:
        return None

    clear_branch_worktree_cache()
    wt_info = resolve_branch_worktree(repo_root, branch, ignore_review_artifacts=True)
    if wt_info and wt_info.get("path"):
        wt_dir = Path(str(wt_info["path"]))
        with contextlib.suppress(OSError):
            (wt_dir / ".sidecar_active_run.lock").unlink()
        # Clean uncommitted synthetic plans/*.md on 0-commit no-op runs when no other dirty files exist
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=wt_dir,
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=15.0,
        )
        raw_lines = [ln.strip() for ln in status_proc.stdout.splitlines() if ln.strip()]
        if raw_lines and all(ln.startswith("?? plans/") and ln.endswith(".md") for ln in raw_lines):
            for ln in raw_lines:
                rel_plan = ln[3:].strip()
                with contextlib.suppress(OSError):
                    (wt_dir / rel_plan).unlink()
        clear_branch_worktree_cache()

    if not _check_merge_cleanliness(branch, repo_root):
        return 1
    print(f"ℹ️ Branch '{branch}' has 0 commits ahead of 'main' and is clean; pruning no-op worktree.")
    _teardown_merged_worktree(branch, delete_branch=True, repo_root=repo_root)
    return 0


def _align_branch_onto_main(branch: str, repo_root: Path) -> int:
    """Rebase branch onto local main when behind main prior to review or staging."""
    from .sync import rebase_branch_onto_main
    from .worktree import clear_branch_worktree_cache, resolve_branch_worktree

    behind, _ = compute_first_parent_sync("main", branch, cwd=repo_root)
    if behind <= 0:
        return 0
    clear_branch_worktree_cache()
    wt_info = resolve_branch_worktree(repo_root, branch, ignore_review_artifacts=True)
    wt_dir = Path(str(wt_info["path"])) if (wt_info and wt_info.get("path")) else repo_root
    print(f"🔄 Branch '{branch}' is {behind} commit(s) behind 'main'; rebasing onto 'main'...")
    outcome = rebase_branch_onto_main(
        branch=branch,
        base_branch="main",
        repo_root=repo_root,
        work_dir=wt_dir,
        use_lock=False,
        timeout_sec=120.0,
    )
    if outcome.status not in ("SUCCESS", "UP_TO_DATE"):
        print(f"❌ Automatic rebase of '{branch}' onto 'main' failed: {outcome.message}")
        return 1
    clear_branch_worktree_cache()
    return 0


def stage_overnight_branch(args: argparse.Namespace, repo_root: Path, title: str) -> int:
    """Qualify branch via pre-merge review and stage manifest for morning approval without mutating main."""
    from .lifecycle import _validate_merge_receipt, cmd_review

    branch = args.branch
    slug = slugify_branch(branch)
    review_args = argparse.Namespace(
        branch=branch,
        repo_root=repo_root,
        skip_readiness_run=getattr(args, "skip_readiness_run", False),
        fail_fast=getattr(args, "fail_fast", False),
        recheck_failed_only=getattr(args, "recheck_failed_only", False),
        full=getattr(args, "full", False),
    )
    rev_rc = cmd_review(review_args)
    if rev_rc != 0:
        return rev_rc

    head_sha = run_git(["rev-parse", branch], cwd=repo_root).strip()
    main_sha = run_git(["rev-parse", "main"], cwd=repo_root).strip()
    if not _validate_merge_receipt(branch, slug, head_sha, repo_root=repo_root):
        print(f"❌ Overnight staging failed: review receipt invalid for '{branch}'.")
        return 1

    stage_dir = repo_root / ".local" / "merge_queue" / "staged_morning_approvals"
    stage_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = stage_dir / f"{slug}.json"
    manifest = {
        "schema_version": "1.0.0",
        "status": "STAGED_FOR_MORNING_APPROVAL",
        "branch": branch,
        "slug": slug,
        "title": title,
        "head_sha": head_sha,
        "base_commit_sha": main_sha,
        "review_receipt": str(repo_root / "reports" / f"pr_review_{slug}_receipt.json"),
        "staged_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"✅ Staged verified branch '{branch}' for morning approval: {manifest_path}")
    return 0


def cmd_consolidate_host(args: argparse.Namespace) -> int:
    """Deduplicate clean merged external chat worktrees and optionally provision a feature branch."""
    from .worktree import cmd_start, deduplicate_external_chat_worktrees

    repo_root = resolve_effective_repo_root(args)
    removed = deduplicate_external_chat_worktrees(repo_root, base_branch="main")
    for br in removed:
        print(f"[host-consolidation] Deduplicated clean external branch: {br}")
    branch = getattr(args, "branch", None)
    if branch:
        args.repo_root = repo_root
        return cmd_start(args)
    print(f"[host-consolidation] Completed on {repo_root} (removed={len(removed)})")
    return 0


def _run_submit_or_promote(args: argparse.Namespace) -> int:
    from .lifecycle import _check_merge_cleanliness, _check_merge_prerequisites, cmd_merge

    repo_root = resolve_effective_repo_root(args)
    branch = args.branch
    if _check_merge_prerequisites(branch, repo_root) != 0:
        return 1

    noop_rc = _prune_zero_commit_noop_branch(branch, repo_root)
    if noop_rc is not None:
        return noop_rc

    if not _check_merge_cleanliness(branch, repo_root):
        return 1

    if _align_branch_onto_main(branch, repo_root) != 0:
        return 1

    resolved_title = getattr(args, "title", None)
    if not resolved_title or len(str(resolved_title).strip()) < 5:
        resolved_title = derive_branch_merge_title(branch, repo_root)
    args.title = resolved_title
    args.repo_root = repo_root

    if getattr(args, "stage_only", False):
        return stage_overnight_branch(args, repo_root=repo_root, title=resolved_title)
    return cmd_merge(args)


def cmd_promote(args: argparse.Namespace) -> int:
    """CLI handler for `pr_governance.py promote <branch>`."""
    return _run_submit_or_promote(args)


def cmd_submit(args: argparse.Namespace) -> int:
    """CLI handler for `pr_governance.py submit <branch>`."""
    return _run_submit_or_promote(args)
