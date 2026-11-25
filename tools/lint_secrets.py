#!/usr/bin/env python3
"""Deterministic secrets and credentials scanner delegating to core-governance with standalone CI fallback."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
from pathlib import Path
import re
import sys
from types import ModuleType
from typing import Sequence

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_PLUGIN_FILE = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp" / "security_purity_linters.py"
_CACHED_PLUGIN_MOD: ModuleType | None = None


def _load_backend() -> ModuleType:
    """Resolve core-governance security_purity_linters unless standalone mode is forced or plugin is absent."""
    global _CACHED_PLUGIN_MOD
    if os.environ.get("CORE_GOVERNANCE_FORCE_STANDALONE") != "1" and _PLUGIN_FILE.is_file():
        if _CACHED_PLUGIN_MOD is None:
            mod_name = "_core_governance_security_purity_linters"
            spec = importlib.util.spec_from_file_location(mod_name, _PLUGIN_FILE)
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                _CACHED_PLUGIN_MOD = mod
        if _CACHED_PLUGIN_MOD is not None:
            return _CACHED_PLUGIN_MOD
    from tools import _standalone_security_purity

    return _standalone_security_purity


_BACKEND = _load_backend()
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = _BACKEND.SECRET_PATTERNS

STAGED_FORBIDDEN_ENV_FILES: tuple[str, ...] = (
    ".env",
    ".env.local",
    "env_agents",
)

EXCLUDED_FILENAMES: tuple[str, ...] = (
    ".env.example",
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
)

EXCLUDED_DIR_PARTS: tuple[str, ...] = (
    ".git",
    ".venv",
    ".worktrees",
    "artifacts",
    "docs/archive",
    "fixtures",
)

SCANNABLE_TEXT_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".sh",
    ".ps1",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".mdc",
    ".txt",
    ".jinja",
    ".j2",
    ".csv",
    ".jsonl",
    ".sql",
)

DUMMY_SECRET_MARKERS: tuple[str, ...] = (
    "example",
    "dummy",
    "placeholder",
    "mock",
    "fake",
    "xxx",
    "<your_",
    "your-api-key",
    "redacted",
)

EXPLICIT_TEST_TOKEN_MARKERS: tuple[str, ...] = (
    "sk-test-",
    "sk_test_",
    "sk-ant-test",
    "-test-",
    "_test_",
    "test_key",
    "test-key",
    "test_token",
    "test-token",
    "testsecret",
    "testapikey",
)

FAST_SECRET_TRIGGERS: tuple[str, ...] = _BACKEND.FAST_TRIGGERS


def is_shannon_entropy_high(s: str, threshold: float = 3.5) -> bool:
    """Calculate Shannon entropy to filter low-entropy strings."""
    return bool(_load_backend().is_shannon_entropy_high(s, threshold=threshold))


_SYNTHETIC_SEQ_TEST_MARKERS: tuple[str, ...] = (
    "1234567890",
    "9876543210",
    "abcdefghijklmnop",
)


def check_file_for_secrets(
    file_path: Path,
    repo_root: Path,
    *,
    explicitly_targeted: bool = False,
) -> list[tuple[int, str, str]]:
    """Scan a single file for exposed secrets via core-governance or standalone fallback."""
    hits = list(
        _load_backend().check_file_for_secrets(
            file_path,
            repo_root,
            explicitly_targeted=explicitly_targeted,
            forbidden_env_files=STAGED_FORBIDDEN_ENV_FILES,
            excluded_dir_parts=EXCLUDED_DIR_PARTS,
            excluded_filenames=EXCLUDED_FILENAMES,
        )
    )
    if hits and (file_path.name.startswith("test_") or file_path.name.endswith("_test.py")):
        try:
            src_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            hits = [
                (ln, stype, msg)
                for ln, stype, msg in hits
                if not (
                    1 <= ln <= len(src_lines)
                    and any(seq in src_lines[ln - 1].lower() for seq in _SYNTHETIC_SEQ_TEST_MARKERS)
                )
            ]
        except OSError:
            pass
    return hits


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic secrets and credentials scanner.")
    parser.add_argument("--files", nargs="*", help="Specific files to scan")
    parser.add_argument("--all", action="store_true", help="Scan repository files")
    parser.add_argument("--repo-root", default=".", help="Root of repository")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    violations: list[tuple[str, int, str, str]] = []
    explicitly_targeted = bool(args.files)

    if args.files:
        files_to_scan = [Path(f) if Path(f).is_absolute() else repo_root / f for f in args.files]
    else:
        files_to_scan = []
        excluded_parts_set = set(EXCLUDED_DIR_PARTS) | {"__pycache__", ".pytest_cache", ".ruff_cache"}
        for root, dirs, files_in_dir in os.walk(repo_root):
            rel_root = os.path.relpath(root, repo_root).replace("\\", "/")
            if rel_root == "docs/archive" or rel_root.startswith("docs/archive/"):
                dirs.clear()
                continue
            dirs[:] = [
                d
                for d in dirs
                if d not in excluded_parts_set and not (rel_root == "docs" and d == "archive")
            ]
            for f in files_in_dir:
                if Path(f).suffix.lower() in SCANNABLE_TEXT_EXTENSIONS:
                    files_to_scan.append(Path(root) / f)

    def scan_one(f: Path) -> list[tuple[str, int, str, str]]:
        if not explicitly_targeted and not f.is_file():
            return []
        hits = check_file_for_secrets(f, repo_root, explicitly_targeted=explicitly_targeted)
        try:
            rel = str(f.relative_to(repo_root))
        except ValueError:
            rel = str(f)
        return [(rel, lineno, stype, msg) for lineno, stype, msg in hits]

    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as executor:
        for res in executor.map(scan_one, files_to_scan):
            violations.extend(res)

    if violations:
        print(f"[FAIL] Secrets detected ({len(violations)} occurrences):", file=sys.stderr)
        for rel, lineno, _stype, msg in violations:
            print(f"  - {rel}:{lineno}: {msg}", file=sys.stderr)
        return 1

    print("[PASS] Secrets scan clean (no unredacted credentials or keys detected).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
