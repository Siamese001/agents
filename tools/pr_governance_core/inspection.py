"""
Branch inspection, listing, and doctor health audit for PR governance.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import (
    CHECKOUT_ROOT,
    REQUIRED_HOOKS,
    ROOT,
    check_merge_conflict,
    compute_first_parent_sync,
    resolve_python,
    run_git,
    slugify_branch,
)
from .worktree import list_active_worktrees


def is_remote_tracking_branch(branch: str) -> bool:
    """Determines whether a branch ref represents a remote tracking branch."""
    return (
        branch.startswith("origin/")
        or branch.startswith("remotes/")
        or branch.startswith("upstream/")
    )


def get_feature_branches(
    include_remote: bool = False,
    fetch_first: bool = False,
    repo_root: Optional[Path] = None,
) -> List[str]:
    """Returns local (and optionally remote) feature branches, excluding main."""
    root = repo_root or ROOT
    if fetch_first:
        try:
            run_git(["fetch", "--prune", "origin"], check=False, cwd=root, timeout=30.0)
        except Exception as e:
            print(f"⚠️ Warning: git fetch failed: {e}", file=sys.stderr)

    try:
        out = run_git(["branch", "--format=%(refname:short)"], check=True, cwd=root)
    except Exception:
        out = ""

    branches = []
    for line in out.splitlines():
        b = line.strip()
        if b and b not in ("main", "master") and not b.startswith("backup-"):
            branches.append(b)

    if include_remote:
        try:
            remote_out = run_git(
                ["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/"],
                check=False,
                cwd=root,
                timeout=15.0,
            )
        except Exception:
            remote_out = ""

        local_set = set(branches)
        for line in remote_out.splitlines():
            r = line.strip()
            if not r or r in ("origin", "origin/HEAD", "origin/main", "origin/master"):
                continue
            local_counterpart = r[len("origin/"):] if r.startswith("origin/") else r
            if local_counterpart not in local_set and r not in branches:
                branches.append(r)

    return sorted(branches)


def _check_readiness_receipt_pass(
    branch: str, head_sha: str, slug: str, repo_root: Path = ROOT
) -> bool:
    """Checks whether a valid PASS PR review receipt exists for the branch."""
    candidates = [
        repo_root / "reports" / f"pr_review_{slug}_receipt.json",
        repo_root / ".worktrees" / slug / "reports" / f"pr_review_{slug}_receipt.json",
    ]
    for c in candidates:
        if c.is_file():
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
                if data.get("terminal_outcome") == "PASS":
                    rec_sha = data.get("head_sha") or data.get("head_commit_sha")
                    if not head_sha or rec_sha == head_sha:
                        return True
            except Exception:
                pass
    return False


def inspect_branch_status(branch: str, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Inspects a feature branch for ahead/behind count, clean mergeability, and review receipts."""
    root = repo_root or ROOT
    head_sha = (run_git(["rev-parse", branch], cwd=root, check=False) or "").strip()
    eff_branch = branch
    if branch == "HEAD":
        try:
            eff_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root).strip()
        except Exception:
            eff_branch = "HEAD"

    behind, ahead = compute_first_parent_sync("main", eff_branch, cwd=root)
    if behind == -1 or ahead == -1:
        clean_merge = False
    elif ahead > 0:
        clean_merge, _ = check_merge_conflict("main", eff_branch, cwd=root)
    else:
        clean_merge = True

    slug = slugify_branch(eff_branch)
    receipt_pass = _check_readiness_receipt_pass(eff_branch, head_sha, slug, repo_root=root)

    changed_files: list[str] = []
    try:
        raw_diff = run_git(["diff", "--name-only", f"main...{eff_branch}"], cwd=root, check=False)
        changed_files = [f for f in raw_diff.splitlines() if f.strip()]
    except Exception:
        pass

    merge_base = run_git(["merge-base", "main", eff_branch], cwd=root, check=False).strip()[:8]

    return {
        "branch": eff_branch,
        "ahead": ahead,
        "behind": behind,
        "clean_merge": clean_merge,
        "readiness_receipt_pass": receipt_pass,
        "changed_files_count": len(changed_files),
        "changed_files": changed_files,
        "tip_sha": head_sha[:8],
        "merge_base_sha": merge_base,
    }


def _audit_git_hooks(audit_root: Optional[Path] = None) -> bool:
    """Verifies core.hooksPath and required hook scripts."""
    target_root = audit_root or (CHECKOUT_ROOT if (CHECKOUT_ROOT / ".githooks").is_dir() else ROOT)
    all_healthy = True
    try:
        hooks_path = run_git(["config", "core.hooksPath"], cwd=target_root, check=False).strip()
        if hooks_path == ".githooks":
            print("✅ Git core.hooksPath is correctly set to '.githooks'.")
        else:
            print(
                f"❌ Git core.hooksPath is '{hooks_path}' (expected '.githooks'). Fix with: git config core.hooksPath .githooks"
            )
            all_healthy = False
    except Exception as e:
        print(f"❌ Failed to check core.hooksPath: {e}")
        all_healthy = False

    for hook_rel in REQUIRED_HOOKS:
        rel_str = hook_rel if hook_rel.startswith(".githooks/") else f".githooks/{hook_rel}"
        hook_path = target_root / rel_str
        if not hook_path.exists():
            print(f"❌ Missing hook script: {rel_str}")
            all_healthy = False
        elif not os.access(hook_path, os.X_OK):
            print(f"❌ Hook is not executable: {rel_str}. Fix with: chmod +x {rel_str}")
            all_healthy = False
        else:
            print(f"✅ Hook exists and is executable: {rel_str}")
    return all_healthy


def cmd_doctor(args: argparse.Namespace) -> int:
    """Audits repository health, git hooks, runtime, and governance tools."""
    target_root = getattr(args, "repo_root", None) or (
        CHECKOUT_ROOT if (CHECKOUT_ROOT / "tools").is_dir() else ROOT
    )
    print("=" * 80)
    print("  LOCAL PR GOVERNANCE: DOCTOR HEALTH AUDIT")
    print("=" * 80)

    all_healthy = True

    # 1. Git hooks audit
    if not _audit_git_hooks(target_root):
        all_healthy = False

    # 2. Python runtime
    py = resolve_python()
    if not Path(py).exists():
        print(f"❌ Python executable not found at: {py}")
        all_healthy = False
    else:
        print(f"✅ Python runtime available: {py}")

    # 3. Critical Gatekeeper Tools
    critical_tools = [
        "tools/verify_commit.py",
        "tools/verify_main_readiness.py",
        "tools/verify_merge_receipt.py",
        "tools/verify_post_merge.py",
        "tools/validate_turn_gates.py",
        "tools/lint_production_purity.py",
        "tools/lint_secrets.py",
    ]
    for tool_rel in critical_tools:
        tool_path = target_root / tool_rel
        if tool_path.exists():
            print(f"✅ Gatekeeper tool present: {tool_rel}")
        else:
            print(f"❌ Missing gatekeeper tool: {tool_rel}")
            all_healthy = False

    # 4. Active worktrees
    active_wts = list_active_worktrees(target_root, ignore_review_artifacts=True)
    dirty_wts = [w for w in active_wts if w["dirty"]]
    if dirty_wts:
        print(f"⚠️ Warning: {len(dirty_wts)} worktree(s) have uncommitted modifications:")
        for dw in dirty_wts:
            print(f"   - {dw['branch']} at {dw['path']} ({dw['summary']})")
    else:
        print(f"✅ All active worktrees ({len(active_wts)}) are clean.")

    print("=" * 80)
    if all_healthy:
        print("✅ REPOSITORY HEALTH CHECK PASSED")
        return 0
    else:
        print("❌ REPOSITORY HEALTH ISSUES DETECTED")
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """Lists candidate feature branches with ahead/behind stats and mergeability."""
    branches = get_feature_branches(
        include_remote=getattr(args, "remote", False),
        fetch_first=getattr(args, "fetch", False),
        repo_root=ROOT,
    )
    if not branches:
        print("No active feature branches found.")
        return 0

    print("=" * 80)
    print(f"  FEATURE BRANCH QUEUE ({len(branches)} candidates)")
    print("=" * 80)
    header = f"{'Branch':<36} {'Ahead':<7} {'Behind':<8} {'Mergeable':<11} {'Review':<8}"
    print(header)
    print("-" * len(header))

    out_data = []
    for b in branches:
        info = inspect_branch_status(b, repo_root=ROOT)
        out_data.append(info)
        m_str = "YES" if info["clean_merge"] else "CONFLICT"
        r_str = "PASS" if info["readiness_receipt_pass"] else "PENDING"
        print(
            f"{info['branch']:<36} "
            f"{info['ahead']:<7} "
            f"{info['behind']:<8} "
            f"{m_str:<11} "
            f"{r_str:<8}"
        )

    print("=" * 80)
    if getattr(args, "json", False):
        print(json.dumps(out_data, indent=2))
    return 0
