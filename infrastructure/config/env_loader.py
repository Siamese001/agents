"""Centralized, typed environment lookup and main-repository root helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def get_env_str(name: str, default: str = "") -> str:
    """Return environment variable value as string, or default when unset."""
    value = os.environ.get(name)
    return value if value is not None else default


def get_env_bool(name: str, default: bool = False) -> bool:
    """Return boolean environment variable value using canonical truthy tokens."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def get_env_optional_path(name: str) -> Path | None:
    """Return resolved Path when environment variable is set and non-empty."""
    raw = os.environ.get(name)
    if not raw or not raw.strip():
        return None
    return Path(raw.strip()).resolve()


def snapshot_process_env() -> dict[str, str]:
    """Return a mutable copy of the current process environment dictionary."""
    return dict(os.environ)


def get_main_repo_root(repo_root: Path | None = None) -> Path:
    """Resolve the primary Git checkout root even when called from a linked worktree."""
    root = (repo_root or Path.cwd()).resolve()
    dot_git = root / ".git"
    if dot_git.is_dir():
        return root
    if dot_git.is_file():
        try:
            content = dot_git.read_text(encoding="utf-8", errors="replace").strip()
            if content.startswith("gitdir:"):
                target = Path(content.split(":", 1)[1].strip())
                if not target.is_absolute():
                    target = (root / target).resolve()
                if "worktrees" in target.parts:
                    common_git = target.parents[1].resolve()
                    if common_git.name == ".git" and common_git.parent.is_dir():
                        return common_git.parent.resolve()
        except (OSError, ValueError, IndexError):
            pass
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            common_dir = Path(proc.stdout.strip()).resolve()
            if common_dir.name == ".git" and common_dir.parent.is_dir():
                return common_dir.parent.resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return root
