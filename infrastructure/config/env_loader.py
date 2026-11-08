"""Centralized, typed environment lookup and main-repository root helpers."""

from __future__ import annotations

import os
import re
import sqlite3
import struct
import subprocess
from pathlib import Path

_LOCAL_BGE_M3_CORPUS_CACHE: list[tuple[frozenset[str], tuple[float, ...]]] | None = None


def load_local_bge_m3_corpus_vectors(caller_root: Path | None = None) -> list[tuple[frozenset[str], tuple[float, ...]]]:
    """Load and cache the canonical 1024-d BGE-M3 unit_vectors from the local augmented skills graph SQLite."""
    global _LOCAL_BGE_M3_CORPUS_CACHE
    if _LOCAL_BGE_M3_CORPUS_CACHE is not None:
        return _LOCAL_BGE_M3_CORPUS_CACHE

    base_root = (caller_root or Path(__file__).resolve().parents[2]).resolve()
    roots = [base_root]
    main_root = get_main_repo_root(base_root)
    if main_root.is_dir() and main_root not in roots:
        roots.append(main_root)

    corpus: list[tuple[frozenset[str], tuple[float, ...]]] = []
    for base in roots:
        db_path = base / "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
        if not db_path.is_file():
            continue
        try:
            conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=10)
            try:
                rows = conn.execute(
                    "SELECT su.text, uv.vector FROM semantic_unit su JOIN unit_vectors uv ON su.unit_id = uv.unit_id"
                ).fetchall()
            finally:
                conn.close()
            for unit_text, blob in rows:
                if isinstance(blob, bytes) and len(blob) == 1024 * 4:
                    toks = frozenset(re.findall(r"[a-z0-9]{3,}", str(unit_text or "").lower()))
                    if toks:
                        corpus.append((toks, struct.unpack("1024f", blob)))
            if corpus:
                break
        except (OSError, sqlite3.Error, struct.error):
            continue

    _LOCAL_BGE_M3_CORPUS_CACHE = corpus
    return corpus



def get_env_str(name: str, default: str = "") -> str:
    """Return environment variable value as string, or default when unset."""
    value = os.environ.get(name)
    return value if value is not None else default


def set_env_default(name: str, default: str) -> str:
    """Set environment variable default when unset and return the active value."""
    return os.environ.setdefault(name, default)


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
