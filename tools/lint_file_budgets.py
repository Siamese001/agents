#!/usr/bin/env python3
"""Deterministic file budget linter enforcing line limits across production-executable directories.

Governance Rule:
    Any directory capable of participating in production execution (including scripts/,
    dual_pipeline/, storage/, resume_graph_engine/, apps_research/, outreach_engine/)
    is subject to file budget governance.
    Non-production exclusions must be narrow, explicit, and justified.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_MAX_LINES = 600

# Production-executable directories subject to architectural governance
PRODUCTION_DIRECTORIES: tuple[str, ...] = (
    "scripts",
    "dual_pipeline",
    "storage",
    "resume_graph_engine",
    "apps_research",
    "outreach_engine",
    "agents",
)

# Explicitly excluded non-production directories
NON_PRODUCTION_DIRECTORIES: tuple[str, ...] = (
    "tests",
    "fixtures",
    "docs",
    "artifacts",
    "scratch",
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
)

RATCHET_REL_PATH = "config/governance/file_budgets_ratchet.json"


def load_ratchet(repo_root: Path) -> dict[str, dict]:
    """Load baseline file budget ratchet exemptions."""
    ratchet_file = repo_root / RATCHET_REL_PATH
    if ratchet_file.is_file():
        try:
            return json.loads(ratchet_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def is_production_path(path: Path | str, repo_root: Path) -> bool:
    """Check whether a path falls within a production-executable scope."""
    p = Path(path).resolve()
    try:
        rel = str(p.relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return False

    # Exclude non-production paths explicitly
    for non_prod in NON_PRODUCTION_DIRECTORIES:
        if rel == non_prod or rel.startswith(f"{non_prod}/"):
            return False

    # Check production directory roots
    for prod in PRODUCTION_DIRECTORIES:
        if rel == prod or rel.startswith(f"{prod}/"):
            return True

    return False


def check_file_budget(
    file_path: Path,
    repo_root: Path,
    max_lines: int = DEFAULT_MAX_LINES,
    ratchet: dict[str, dict] | None = None,
) -> tuple[bool, int, str]:
    """Check a single file against the budget.

    Returns:
        (passed, line_count, message)
    """
    if not file_path.exists():
        return True, 0, "File does not exist"

    try:
        rel_str = str(file_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        rel_str = str(file_path)

    if not is_production_path(file_path, repo_root):
        return True, 0, f"Skipped (non-production path: {rel_str})"

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    line_count = len(lines)

    if ratchet is None:
        ratchet = load_ratchet(repo_root)

    # If file is in ratchet: ensure it does not grow past baseline
    if rel_str in ratchet:
        entry = ratchet[rel_str]
        ceiling = entry.get("line_limit", max_lines)
        if line_count > ceiling:
            return (
                False,
                line_count,
                f"REGRESSION: {rel_str} has grown to {line_count} lines (ratchet ceiling: {ceiling}). Reason: {entry.get('justification', 'None')}",
            )
        return True, line_count, f"Ratchet OK ({line_count}/{ceiling} lines): {entry.get('justification', '')}"

    # For files in scripts/: strict enforcement unless explicit non-production classification
    if rel_str.startswith("scripts/"):
        # If script exceeds budget, fail immediately
        if line_count > max_lines:
            return (
                False,
                line_count,
                f"VIOLATION: Production script {rel_str} has {line_count} lines (budget limit: {max_lines}). No production script may evade governance. Either decompose or classify as explicit non_production in ratchet.",
            )

    if line_count > max_lines:
        return (
            False,
            line_count,
            f"VIOLATION: {rel_str} has {line_count} lines (budget limit: {max_lines}). Exceeds architectural file budget limit.",
        )

    return True, line_count, f"OK ({line_count}/{max_lines} lines)"


def scan_all_production_files(repo_root: Path, max_lines: int = DEFAULT_MAX_LINES) -> list[tuple[str, int, str]]:
    """Scan all production Python files in the repository."""
    ratchet = load_ratchet(repo_root)
    violations = []
    for prod_dir in PRODUCTION_DIRECTORIES:
        dir_path = repo_root / prod_dir
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            passed, lines, msg = check_file_budget(py_file, repo_root, max_lines=max_lines, ratchet=ratchet)
            if not passed:
                violations.append((str(py_file.relative_to(repo_root)), lines, msg))
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic file budget linter.")
    parser.add_argument("--files", nargs="*", help="Specific files to check (e.g. from staged changes)")
    parser.add_argument("--all", action="store_true", help="Scan all production Python files in the repository")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES, help=f"Max lines budget (default {DEFAULT_MAX_LINES})")
    parser.add_argument("--repo-root", default=".", help="Root of repository")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    ratchet = load_ratchet(repo_root)

    violations = []
    checked_count = 0

    if args.files:
        for f in args.files:
            p = Path(f)
            if not p.is_absolute():
                p = repo_root / p
            if p.suffix == ".py":
                checked_count += 1
                passed, lines, msg = check_file_budget(p, repo_root, max_lines=args.max_lines, ratchet=ratchet)
                if not passed:
                    violations.append((f, lines, msg))
    else:
        # Default / --all: scan production directories
        violations = scan_all_production_files(repo_root, max_lines=args.max_lines)
        checked_count = len(violations)

    if violations:
        print(f"[FAIL] File budget violations found ({len(violations)} files):", file=sys.stderr)
        for path, lines, msg in violations:
            print(f"  - {msg}", file=sys.stderr)
        return 1

    print(f"[PASS] File budgets clean (checked production files within limit of {args.max_lines} lines).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
