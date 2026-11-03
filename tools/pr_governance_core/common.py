"""Common constants, regexes, and utility functions for PR governance."""

from __future__ import annotations

import functools
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple


def _find_repo_root() -> Path:
    script_repo = Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(script_repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            common_dir = Path(proc.stdout.strip()).resolve()
            return common_dir.parent if common_dir.name == ".git" else common_dir
    except Exception:  # guardian: allow-silent-swallow -- fallback to script directory layout
        pass
    return script_repo.parents[1] if script_repo.parent.name == ".worktrees" else script_repo


ROOT = _find_repo_root()
CHECKOUT_ROOT = Path(__file__).resolve().parents[2]

CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([a-zA-Z0-9_\-./]+\))?:\s+.+$|"
    r"^Merge\s+.+$"
)

CONVENTIONAL_BRANCH_RE = re.compile(
    r"^(feat|feature|enhance|fix|ingest|audio|transcript|docs|style|refactor|perf|test|build|ci|chore|revert)/[a-zA-Z0-9_\-\.]+$"
)

GENERATED_ARTIFACT_PATTERNS = (
    "reports/pr_review_",
    "reports/pr_merge_",
    "reports/pr_queue_detail.json",
    "reports/readiness/",
    "reports/local_main_readiness_",
    "reports/testing_gaps_audit_report",
    "reports/qa_gates_report",
    "reports/test_timing_db",
    "reports/final_release_decision",
)

PLAN_DOC_FILES = frozenset({"implementation_plan.md", "walkthrough.md"})


def is_plan_doc_file(path: str | Path) -> bool:
    """Checks whether a path refers to an implementation plan or walkthrough doc."""
    s = str(path).replace("\\", "/")
    if s in PLAN_DOC_FILES:
        return True
    p = Path(s)
    parts = p.parts
    if not parts or p.suffix != ".md":
        return False
    if parts[0] == "plans":
        return True
    return len(parts) >= 3 and parts[0] == "docs" and parts[1] == "plans"


def resolve_branch_plan_path(branch: str, repo_root: Path | None = None) -> Path:
    """Resolves the canonical plan path for a branch."""
    root = repo_root or ROOT
    slug = slugify_branch(branch)
    for candidate in (
        root / "plans" / f"{slug}.md",
        root / "docs" / "plans" / f"{slug}.md",
        root / "plans" / slug / "implementation_plan.md",
        root / "implementation_plan.md",
    ):
        if candidate.is_file():
            return candidate
    return root / "plans" / f"{slug}.md"


REQUIRED_HOOKS = [
    ".githooks/pre-commit",
    ".githooks/commit-msg",
    ".githooks/pre-merge-commit",
    ".githooks/pre-push",
    ".githooks/post-checkout",
    ".githooks/post-merge",
]


_RESOLVED_PR_PYTHON: Optional[str] = None


def _candidate_venv_roots(extra_root: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    for cand in (extra_root, CHECKOUT_ROOT, ROOT):
        if cand is not None:
            resolved = cand.resolve()
            if resolved not in roots:
                roots.append(resolved)
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=extra_root or CHECKOUT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            common_root = Path(proc.stdout.strip()).parent.resolve()
            if common_root not in roots:
                roots.append(common_root)
    except Exception:  # guardian: allow-silent-swallow -- best-effort git common dir lookup
        pass
    return roots


def bootstrap_shared_venv(repo_root: Path | None = None) -> Optional[Path]:
    """Attach the shared repository .venv site-packages to sys.path when running in an isolated worktree."""
    import site

    for candidate_root in _candidate_venv_roots(repo_root):
        venv_dir = candidate_root / ".venv"
        if not venv_dir.is_dir():
            continue
        site_dirs = list((venv_dir / "lib").glob("python*/site-packages"))
        win_site = venv_dir / "Lib" / "site-packages"
        if win_site.is_dir():
            site_dirs.append(win_site)
        for sdir in site_dirs:
            sdir_str = str(sdir.resolve())
            if sdir_str not in sys.path:
                site.addsitedir(sdir_str)
        return venv_dir
    return None


def resolve_python(repo_root: Path | None = None) -> str:
    global _RESOLVED_PR_PYTHON
    if _RESOLVED_PR_PYTHON is not None and repo_root is None:
        return _RESOLVED_PR_PYTHON

    if sys.prefix != sys.base_prefix and Path(sys.executable).is_file():
        _RESOLVED_PR_PYTHON = sys.executable
        return sys.executable

    for candidate_root in _candidate_venv_roots(repo_root):
        venv_py = candidate_root / ".venv" / "bin" / "python"
        if venv_py.exists() and os.access(venv_py, os.X_OK):
            if repo_root is None:
                _RESOLVED_PR_PYTHON = str(venv_py)
            return str(venv_py)
        win_py = candidate_root / ".venv" / "Scripts" / "python.exe"
        if win_py.exists() and os.access(win_py, os.X_OK):
            if repo_root is None:
                _RESOLVED_PR_PYTHON = str(win_py)
            return str(win_py)
    if repo_root is None:
        _RESOLVED_PR_PYTHON = sys.executable
    return sys.executable


def resolve_pytest(repo_root: Path | None = None) -> list[str]:
    """Resolve pytest executable across local worktree, shared main repository .venv, and system PATH."""
    for candidate_root in _candidate_venv_roots(repo_root):
        venv_pytest = candidate_root / ".venv" / "bin" / "pytest"
        if venv_pytest.is_file() and os.access(venv_pytest, os.X_OK):
            return [str(venv_pytest)]
        win_pytest = candidate_root / ".venv" / "Scripts" / "pytest.exe"
        if win_pytest.is_file() and os.access(win_pytest, os.X_OK):
            return [str(win_pytest)]
    return [resolve_python(repo_root), "-m", "pytest"]


_BANNED_GIT_ENV_VARS = frozenset(
    {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX"}
)


def sanitized_git_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Returns a copy of os.environ with worktree-polluting GIT_* variables removed."""
    env = {k: v for k, v in os.environ.items() if k not in _BANNED_GIT_ENV_VARS}
    env["GIT_TERMINAL_PROMPT"] = "0"
    if extra:
        env.update(extra)
    return env


def run_git(args: List[str], check: bool = True, cwd: Path | None = None, timeout: float = 30.0) -> str:
    res = subprocess.run(
        ["git"] + args,
        cwd=cwd or ROOT,
        env=sanitized_git_env(),
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
    )
    return res.stdout.rstrip("\r\n")


def slugify_branch(branch: str) -> str:
    """Produces a clean filesystem slug, sanitizing prohibited model naming tokens."""
    tokens = re.split(r"[^a-zA-Z0-9]+", branch)
    prohibited = {"gpt", "astra", "luna", "sol", "terra", "claude", "gemini", "llama", "sonnet", "haiku", "opus", "o1", "o3"}
    filtered = [
        t for t in tokens
        if t and t.lower() not in prohibited and not any(t.lower().startswith(p) for p in ("gpt", "claude", "gemini", "llama"))
    ]
    return "_".join(filtered) or "feature"


def check_diff_syntax(diff_names: list[str], target_cwd: Path) -> Tuple[bool, Optional[str]]:
    """Performs early deterministic syntax prechecks on modified Python and JSON files."""
    import ast
    import json

    for name in diff_names:
        file_path = target_cwd / name
        if not file_path.is_file():
            continue
        if name.endswith(".py"):
            try:
                ast.parse(file_path.read_bytes(), filename=str(file_path))
            except SyntaxError as e:
                return False, f"Python syntax error in {name}:{e.lineno}: {e.msg}"
        elif name.endswith(".json"):
            try:
                json.loads(file_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                return False, f"JSON syntax error in {name}:{e.lineno}: {e.msg}"
    return True, None


_MERGE_TREE_CACHE: dict[tuple[str, str, str], Tuple[bool, str]] = {}


def _resolve_ref_sha(ref: str, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=cwd,
        env=sanitized_git_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=15.0,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return ref


def check_merge_conflict(base: str, target: str, cwd: Optional[Path] = None) -> Tuple[bool, str]:
    """Dry-run merge using git merge-tree --write-tree. Returns (is_clean, details)."""
    run_cwd = cwd or ROOT
    try:
        resolved_base = _resolve_ref_sha(base, run_cwd)
        resolved_target = _resolve_ref_sha(target, run_cwd)

        cache_key = (str(run_cwd), resolved_base, resolved_target)
        if cache_key in _MERGE_TREE_CACHE:
            return _MERGE_TREE_CACHE[cache_key]

        res = subprocess.run(
            ["git", "merge-tree", "--write-tree", resolved_base, resolved_target],
            cwd=run_cwd,
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=30.0,
        )
        if res.returncode == 0:
            out = (True, "")
        elif res.returncode == 1 and res.stdout.strip() and "not something we can merge" not in res.stderr:
            out = (False, res.stdout + ("\n" + res.stderr if res.stderr else ""))
        else:
            out = (False, f"UNKNOWN: git merge-tree exited with code {res.returncode}\n{res.stderr.strip()}")

        _MERGE_TREE_CACHE[cache_key] = out
        return out
    except Exception as e:
        return False, f"UNKNOWN: {e}"


def compute_branch_delta_digest(repo_root: Path, ref: str, base_ref: str = "main") -> str:
    """Computes a deterministic SHA-256 digest of the diff between base_ref and ref."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--binary", f"{base_ref}...{ref}"],
            cwd=repo_root,
            env=sanitized_git_env(),
            capture_output=True,
            check=False,
            timeout=30.0,
        )
        if proc.returncode != 0:
            return ""
        return hashlib.sha256(proc.stdout).hexdigest()
    except (OSError, subprocess.SubprocessError):
        return ""


def check_disjoint_base_advance_equivalence(
    old_base_sha: str,
    new_base_sha: str,
    branch_diff_files: list[str],
    repo_root: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Checks whether mainline commits between old_base_sha and new_base_sha are disjoint from branch_diff_files."""
    root = repo_root or ROOT
    if not old_base_sha or not new_base_sha:
        return False, "missing_base_sha"
    if old_base_sha == new_base_sha:
        return True, "identical_base"
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{old_base_sha}..{new_base_sha}"],
            cwd=root,
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=15.0,
        )
        if proc.returncode != 0:
            return False, "git_diff_failed"
        main_changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
        branch_changed = {line.strip() for line in branch_diff_files if line.strip()}
        overlap = sorted(main_changed.intersection(branch_changed))
        if overlap:
            return False, f"overlapping_files:{','.join(overlap[:5])}"
        return True, "disjoint_files"
    except Exception as exc:
        return False, f"error:{exc}"


def get_immune_pids() -> set[int]:
    """Returns set of PIDs immune from ghost process reaping (current process, parent, process group)."""
    immune: set[int] = {os.getpid()}
    try:
        immune.add(os.getppid())
    except (OSError, AttributeError):
        pass
    try:
        immune.add(os.getpgid(0))
    except (OSError, AttributeError):
        pass
    return immune


def kill_ghost_processes(worktree_dir: Path, terminate_ghosts: bool = False) -> list[int]:
    """Safely audits and optionally terminates orphan processes holding descriptors in worktree_dir."""
    import signal

    proc = subprocess.run(["lsof", "-t", "+D", str(worktree_dir)], capture_output=True, text=True, check=False, timeout=10.0)
    if not proc.stdout.strip():
        return []

    immune = get_immune_pids()
    target_pids: list[int] = []
    for line in set(proc.stdout.strip().splitlines()):
        try:
            pid = int(line.strip())
            if pid > 0 and pid not in immune:
                target_pids.append(pid)
        except ValueError:
            continue

    if not target_pids:
        return []

    if terminate_ghosts:
        for pid in target_pids:
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"Terminated orphan worktree process (PID {pid}).")
            except OSError:
                pass
    else:
        pid_strs = [str(p) for p in target_pids]
        print(f"Detected background process(es) holding descriptors in {worktree_dir}: {', '.join(pid_strs)}.")

    return target_pids


@functools.lru_cache(maxsize=None)
def logic_digest(*module_files: str) -> str:
    """Short digest of rule/engine source files."""
    h = hashlib.sha256(b"prq-cache-schema-v2")
    for name in module_files:
        try:
            h.update(Path(name).read_bytes())
        except OSError:
            h.update(name.encode("utf-8"))
    return h.hexdigest()[:10]


def compute_first_parent_sync(
    base_branch: str, eff_branch: str, cwd: Path | None = None
) -> Tuple[int, int]:
    """Computes (behind, ahead) commit counts along the mainline first-parent spine."""
    root = cwd or ROOT
    try:
        base_res = run_git(["merge-base", base_branch, eff_branch], check=True, cwd=root).strip()
        if not base_res:
            return -1, -1
        behind_s = run_git(
            ["rev-list", "--first-parent", "--count", f"{base_res}..{base_branch}"],
            check=True,
            cwd=root,
        ).strip()
        ahead_s = run_git(
            ["rev-list", "--count", f"{base_res}..{eff_branch}"],
            check=True,
            cwd=root,
        ).strip()
        return int(behind_s), int(ahead_s)
    except Exception:
        return -1, -1
