"""
Worktree lifecycle commands for PR governance: start, dehydrate, finish, and list.

Enforces isolated worktree development under .worktrees/<slug>/ to prevent
parallel workspace collisions and uncommitted file pollution in the repository root.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .common import (
    CONVENTIONAL_BRANCH_RE,
    GENERATED_ARTIFACT_PATTERNS,
    ROOT,
    kill_ghost_processes,
    run_git,
    sanitized_git_env,
    slugify_branch,
)

logger = logging.getLogger("tools.pr_governance_core.worktree")

VALUABLE_IGNORED_EXTENSIONS = (".sqlite-wal", ".sqlite", ".db")
VALUABLE_IGNORED_PREFIXES = ("output/", "output\\", "artifacts/")
BENIGN_IGNORED_SUBSTRINGS = (
    "__pycache__",
    ".pytest_cache",
    ".venv",
    ".local",
    ".git",
    ".DS_Store",
    ".pyc",
    ".sqlite-shm",
)


@dataclass
class WorktreeDirtyResult:
    dirty: bool
    summary: str
    dirty_files_count: int
    authored_files_count: int
    authored_code_files: List[str] = field(default_factory=list)
    deliverable_files: List[str] = field(default_factory=list)
    ephemeral_attempt_files: List[str] = field(default_factory=list)


@contextlib.contextmanager
def worktree_provisioning_lock(timeout_seconds: float = 120.0, root: Path = ROOT):
    """Acquires an advisory provisioning lock powered by filelock.FileLock."""
    from filelock import FileLock, Timeout

    lock_file = root / ".worktrees" / ".provisioning.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    flock = FileLock(str(lock_file), timeout=timeout_seconds)
    try:
        flock.acquire(timeout=timeout_seconds, poll_interval=0.05)
    except Timeout as exc:
        raise TimeoutError(
            f"Could not acquire worktree provisioning lock within {timeout_seconds}s at {lock_file}"
        ) from exc
    try:
        yield lock_file
    finally:
        with contextlib.suppress(Exception):
            flock.release()


def link_worktree_dependencies(root: Path, worktree_dir: Path) -> list[str]:
    """
    Symlinks runtime dependencies, editor configs, and agent governance
    into the isolated worktree using robust relative symlinks.
    """
    linked: list[str] = []
    candidates = (".venv", ".local", ".vscode", ".agents", ".antigravity")
    for link_name in candidates:
        src = root / link_name
        dst = worktree_dir / link_name
        if (src.exists() or src.is_symlink()) and not (dst.exists() or dst.is_symlink()):
            try:
                rel_target = os.path.relpath(src, worktree_dir)
                os.symlink(rel_target, dst)
                linked.append(link_name)
            except Exception as e:
                print(f"  ⚠️ Could not symlink {link_name}: {e}")
    return linked


def safely_unlink_worktree_dependencies(worktree_dir: Path) -> list[str]:
    """
    Safely unlinks all symlinks inside worktree_dir before rmtree/git remove.
    Prevents recursive traversal into target directories (e.g. root .venv).
    """
    unlinked: list[str] = []
    if not worktree_dir.exists() or not worktree_dir.is_dir():
        return unlinked

    for item in list(worktree_dir.iterdir()):
        if item.is_symlink():
            try:
                item.unlink()
                unlinked.append(item.name)
            except Exception as e:
                print(f"  ⚠️ Could not unlink symlink {item.name}: {e}")
    return unlinked


def provision_isolated_worktree(
    root: Path,
    worktree_dir: Path,
    branch: str,
    base_branch: str = "main",
) -> Path:
    """
    Provisions a new git worktree with relative dependency symlinks.
    """
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        branches = run_git(
            ["branch", "--format=%(refname:short)"], cwd=root, check=True
        ).splitlines()
    except Exception:
        branches = []
    branch_exists = branch in branches

    if branch_exists:
        cmd = ["worktree", "add", str(worktree_dir), branch]
    else:
        cmd = ["worktree", "add", str(worktree_dir), "-b", branch, base_branch]

    try:
        run_git(cmd, cwd=root, check=True)
    except Exception as e:
        raise RuntimeError(
            f"Failed to create worktree at '{worktree_dir}' for branch '{branch}': {e}"
        ) from e

    link_worktree_dependencies(root, worktree_dir)
    return worktree_dir


def is_ephemeral_worktree_path(rel_path: str) -> bool:
    """Checks if a relative path corresponds to an ephemeral receipt or cache."""
    norm = rel_path.replace("\\", "/")
    if any(norm.startswith(pat) for pat in GENERATED_ARTIFACT_PATTERNS):
        return True
    if any(b in norm for b in BENIGN_IGNORED_SUBSTRINGS):
        return True
    if norm.endswith(".pyc") or norm.endswith(".lock"):
        return True
    return False


def is_mid_rebase(wt_path: Path) -> bool:
    """Returns True if the worktree is currently halted mid-rebase or mid-merge."""
    git_dir = wt_path / ".git"
    if git_dir.is_file():
        try:
            content = git_dir.read_text(encoding="utf-8").strip()
            if content.startswith("gitdir:"):
                git_dir = Path(content.split("gitdir:", 1)[1].strip())
                if not git_dir.is_absolute():
                    git_dir = (wt_path / git_dir).resolve()
        except Exception:
            pass
    return (
        (git_dir / "rebase-apply").exists()
        or (git_dir / "rebase-merge").exists()
        or (git_dir / "MERGE_HEAD").exists()
    )


def _inspect_worktree_dirty(wt_path: Path, ignore_review_artifacts: bool) -> WorktreeDirtyResult:
    """Audits whether a given worktree path has uncommitted modifications."""
    if not wt_path.exists():
        return WorktreeDirtyResult(False, "UNKNOWN (missing directory)", 0, 0)
    if is_mid_rebase(wt_path):
        return WorktreeDirtyResult(True, "UNKNOWN (mid-rebase in progress)", 0, 0)

    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=wt_path,
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=15.0,
        )
        lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
    except Exception:
        return WorktreeDirtyResult(True, "status-check-failed", 0, 0)

    dirty_files: list[str] = []
    authored_code: list[str] = []
    deliverables: list[str] = []
    ephemeral: list[str] = []

    for line in lines:
        if len(line) < 3:
            continue
        rel_path = line[3:].strip()
        if ignore_review_artifacts and is_ephemeral_worktree_path(rel_path):
            ephemeral.append(rel_path)
            continue
        dirty_files.append(rel_path)
        if rel_path.endswith((".py", ".sh", ".json", ".yaml", ".yml", ".md")):
            authored_code.append(rel_path)

    dirty = len(dirty_files) > 0
    summary = f"dirty ({len(dirty_files)} files)" if dirty else "clean"
    return WorktreeDirtyResult(
        dirty=dirty,
        summary=summary,
        dirty_files_count=len(dirty_files),
        authored_files_count=len(authored_code),
        authored_code_files=authored_code,
        deliverable_files=deliverables,
        ephemeral_attempt_files=ephemeral,
    )


def _inspect_single_worktree_entry(
    wt_path: Path,
    branch_ref: str,
    head_sha: str,
    is_bare: bool,
    is_detached: bool,
    root: Path,
    ignore_review_artifacts: bool,
) -> dict[str, Any]:
    if not wt_path.exists():
        return {
            "path": str(wt_path),
            "branch": branch_ref or "unknown",
            "head": head_sha,
            "dirty": False,
            "summary": "UNKNOWN (missing directory)",
            "status": "UNKNOWN",
            "dirty_files_count": 0,
            "authored_files_count": 0,
            "is_root": False,
        }

    mid_reb = is_mid_rebase(wt_path)
    dirty = False
    summary = "clean"
    dirty_count = 0
    authored_count = 0

    if not is_bare:
        res = _inspect_worktree_dirty(wt_path, ignore_review_artifacts)
        dirty = res.dirty
        summary = res.summary
        dirty_count = res.dirty_files_count
        authored_count = res.authored_files_count

    return {
        "path": str(wt_path),
        "branch": branch_ref or ("detached" if is_detached else ("bare" if is_bare else "unknown")),
        "head": head_sha,
        "dirty": dirty,
        "summary": summary,
        "status": "UNKNOWN" if mid_reb else ("dirty" if dirty else "clean"),
        "mid_rebase": mid_reb,
        "dirty_files_count": dirty_count,
        "authored_files_count": authored_count,
        "is_root": str(wt_path.resolve()) == str(root.resolve()),
    }


def list_active_worktrees(
    root: Path, ignore_review_artifacts: bool = False, include_orphans: bool = False
) -> list[dict[str, Any]]:
    """Discovers all registered git worktrees and audits their branch and dirty state."""
    entries: list[dict[str, Any]] = []
    try:
        wt_list = run_git(["worktree", "list", "--porcelain"], cwd=root, check=True)
    except Exception:
        return entries

    for block in wt_list.split("\n\n"):
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        wt_path: Optional[Path] = None
        branch_ref = ""
        head_sha = ""
        is_bare = False
        is_detached = False

        for line in lines:
            if line.startswith("worktree "):
                wt_path = Path(line.split(" ", 1)[1].strip())
            elif line.startswith("HEAD "):
                head_sha = line.split(" ", 1)[1].strip()[:8]
            elif line.startswith("branch "):
                branch_ref = line.split(" ", 1)[1].strip().replace("refs/heads/", "")
            elif line.strip() == "bare":
                is_bare = True
            elif line.strip() == "detached":
                is_detached = True

        if wt_path:
            entry = _inspect_single_worktree_entry(
                wt_path, branch_ref, head_sha, is_bare, is_detached, root, ignore_review_artifacts
            )
            entries.append(entry)

    return entries


_BRANCH_WORKTREE_CACHE: Dict[Tuple[str, str, bool], Optional[dict[str, Any]]] = {}


def clear_branch_worktree_cache() -> None:
    _BRANCH_WORKTREE_CACHE.clear()


def resolve_branch_worktree(
    root: Path, branch: str, ignore_review_artifacts: bool = True
) -> Optional[dict[str, Any]]:
    """O(1) worktree resolver targeting .worktrees/<slug> before full registry scan."""
    cache_key = (str(root.resolve()), branch, ignore_review_artifacts)
    if cache_key in _BRANCH_WORKTREE_CACHE:
        return _BRANCH_WORKTREE_CACHE[cache_key]

    slug = slugify_branch(branch)
    candidate_path = root / ".worktrees" / slug

    if candidate_path.is_dir() and (candidate_path / ".git").is_file():
        try:
            head_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=candidate_path, check=True).strip()
            if head_branch == branch:
                head_sha = run_git(["rev-parse", "HEAD"], cwd=candidate_path, check=True).strip()[:8]
                entry = _inspect_single_worktree_entry(
                    candidate_path,
                    branch,
                    head_sha,
                    is_bare=False,
                    is_detached=False,
                    root=root,
                    ignore_review_artifacts=ignore_review_artifacts,
                )
                _BRANCH_WORKTREE_CACHE[cache_key] = entry
                return entry
        except Exception:
            pass

    try:
        root_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root, check=True).strip()
        if root_branch == branch:
            root_sha = run_git(["rev-parse", "HEAD"], cwd=root, check=True).strip()[:8]
            entry = _inspect_single_worktree_entry(
                root,
                branch,
                root_sha,
                is_bare=False,
                is_detached=False,
                root=root,
                ignore_review_artifacts=ignore_review_artifacts,
            )
            _BRANCH_WORKTREE_CACHE[cache_key] = entry
            return entry
    except Exception:
        pass

    for wt in list_active_worktrees(root, ignore_review_artifacts=ignore_review_artifacts):
        if wt.get("branch") == branch:
            _BRANCH_WORKTREE_CACHE[cache_key] = wt
            return wt

    _BRANCH_WORKTREE_CACHE[cache_key] = None
    return None


def _find_worktree_dir(branch: str, slug: str, root: Path = ROOT) -> Path:
    """Finds worktree directory checking registered worktrees first."""
    with contextlib.suppress(Exception):
        wt_list = run_git(["worktree", "list", "--porcelain"], cwd=root, check=True)
        for block in wt_list.split("\n\n"):
            lines = block.strip().splitlines()
            wt_path, wt_branch = None, None
            for line in lines:
                if line.startswith("worktree "):
                    wt_path = Path(line.split(" ", 1)[1].strip())
                elif line.startswith("branch "):
                    wt_branch = line.split(" ", 1)[1].strip().replace("refs/heads/", "")
            if wt_branch == branch and wt_path:
                return wt_path
    return root / ".worktrees" / slug


def _is_branch_merged(branch: str, root: Path = ROOT) -> bool:
    """Checks if a branch is fully merged into main."""
    try:
        res = subprocess.run(
            ["git", "merge-base", "--is-ancestor", branch, "main"],
            cwd=root,
            env=sanitized_git_env(),
            capture_output=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def _remove_worktree_files(worktree_dir: Path, force: bool, root: Path = ROOT) -> bool:
    """Removes git worktree files cleanly without following directory symlinks."""
    kill_ghost_processes(worktree_dir, terminate_ghosts=True)
    safely_unlink_worktree_dependencies(worktree_dir)

    rm_args = ["worktree", "remove", str(worktree_dir)]
    if force:
        rm_args.append("--force")
    try:
        run_git(rm_args, cwd=root, check=True)
        return True
    except Exception as e:
        print(f"❌ git worktree remove {'--force ' if force else ''}failed: {e}")
        return False


def cmd_start(args: argparse.Namespace) -> int:
    """Creates a new conventional branch inside an isolated worktree."""
    with worktree_provisioning_lock():
        branch = args.branch
        slug = slugify_branch(branch)
        print(f"  LOCAL PR GOVERNANCE: START WORKTREE FOR {branch}")
        print(f"  Target Worktree Path: .worktrees/{slug}")

        if branch in ("main", "master") or "main_merge" in branch:
            print(f"❌ Error: Branch '{branch}' is strictly prohibited for isolated worktrees.")
            return 1

        if not CONVENTIONAL_BRANCH_RE.match(branch):
            print(f"❌ Error: Branch name '{branch}' does not conform to conventional branch format.")
            print("   Allowed patterns: feat/*, feature/*, fix/*, chore/*, docs/*, refactor/*, test/*, ci/*")
            return 1

        worktree_dir = ROOT / ".worktrees" / slug
        if worktree_dir.exists():
            print(f"❌ Error: Worktree directory already exists at: {worktree_dir}")
            return 1

        print(f"Provisioning isolated worktree at '.worktrees/{slug}'...")
        try:
            provision_isolated_worktree(ROOT, worktree_dir, branch, "main")
        except Exception as e:
            print(f"❌ Failed to create worktree: {e}")
            return 1

        print("\n" + "=" * 80)
        print("✅ Isolated worktree created successfully!")
        print("   To begin development, run:")
        print(f"     cd .worktrees/{slug}")
        print("=" * 80)
        return 0


def cmd_dehydrate(args: argparse.Namespace) -> int:
    """Dehydrates a worktree by removing its folder while preserving the branch."""
    with worktree_provisioning_lock():
        branch = args.branch
        slug = slugify_branch(branch)
        worktree_dir = _find_worktree_dir(branch, slug, root=ROOT)
        if not worktree_dir.exists():
            print(f"ℹ️ Worktree directory does not exist: {worktree_dir}")
            return 0

        res = _inspect_worktree_dirty(worktree_dir, ignore_review_artifacts=True)
        if res.dirty:
            print(f"❌ Error: Worktree '{worktree_dir}' has uncommitted changes ({res.dirty_files_count} files).")
            print("   Commit or stash changes before dehydrating.")
            return 1

        print(f"Dehydrating worktree '{worktree_dir}' (preserving branch '{branch}')...")
        if not _remove_worktree_files(worktree_dir, force=False, root=ROOT):
            return 1

        print(f"✅ Worktree for '{branch}' dehydrated successfully.")
        return 0


def cmd_finish(args: argparse.Namespace) -> int:
    """Removes a finished worktree after merge to main."""
    with worktree_provisioning_lock():
        branch = args.branch
        slug = slugify_branch(branch)
        force = getattr(args, "force", False)
        delete_branch = getattr(args, "delete_branch", True)

        print(f"  LOCAL PR GOVERNANCE: FINISH WORKTREE FOR {branch}")
        print(f"  Target Worktree Path: .worktrees/{slug}")

        worktree_dir = _find_worktree_dir(branch, slug, root=ROOT)
        if not worktree_dir.exists():
            print(f"ℹ️ Worktree directory does not exist: {worktree_dir}")
            if delete_branch:
                try:
                    recorded_sha = run_git(["rev-parse", f"refs/heads/{branch}"], cwd=ROOT, check=False).strip()
                    if recorded_sha:
                        run_git(["update-ref", "-d", f"refs/heads/{branch}", recorded_sha], cwd=ROOT, check=True)
                        print(f"✅ Branch '{branch}' deleted.")
                except Exception as e:
                    print(f"⚠️ Could not delete branch ref: {e}")
            return 0

        recorded_sha = ""
        with contextlib.suppress(Exception):
            recorded_sha = run_git(["rev-parse", f"refs/heads/{branch}"], cwd=ROOT, check=True).strip()

        if not force:
            is_merged = _is_branch_merged(branch, root=ROOT)
            is_clean = not _inspect_worktree_dirty(worktree_dir, ignore_review_artifacts=True).dirty
            if not is_merged:
                print(f"❌ Error: Branch '{branch}' is not fully merged into main. Use --force to remove anyway.")
                return 1
            if not is_clean:
                print(f"❌ Error: Worktree '{worktree_dir}' has uncommitted changes. Use --force to remove anyway.")
                return 1

        print(f"Removing worktree '{worktree_dir}'...")
        if not _remove_worktree_files(worktree_dir, force=force, root=ROOT):
            return 1

        if delete_branch and recorded_sha:
            print(f"Deleting branch '{branch}'...")
            try:
                run_git(["update-ref", "-d", f"refs/heads/{branch}", recorded_sha], cwd=ROOT, check=True)
                print(f"✅ Branch '{branch}' deleted.")
            except Exception as e:
                print(f"⚠️ Failed to delete branch ref: {e}")
                return 1

        print("✅ Worktree teardown complete.")
        return 0


def cmd_worktree_list(args: argparse.Namespace) -> int:
    """Lists all active worktrees and their status."""
    entries = list_active_worktrees(ROOT, ignore_review_artifacts=True)
    if not entries:
        print("No active worktrees found.")
        return 0

    print("=" * 80)
    print(f"  ACTIVE WORKTREES ({len(entries)})")
    print("=" * 80)
    header = f"{'Branch':<30} {'Status':<10} {'Head':<10} {'Path'}"
    print(header)
    print("-" * len(header))
    for e in entries:
        st = "DIRTY" if e["dirty"] else "CLEAN"
        print(f"{e['branch']:<30} {st:<10} {e['head']:<10} {e['path']}")
    print("=" * 80)
    return 0
