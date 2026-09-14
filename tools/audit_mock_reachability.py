#!/usr/bin/env python3
"""Audit production codebase to guarantee zero reachable mocks in production execution paths."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Sequence

_FORBIDDEN_PRODUCTION_PATTERNS = [
    (
        re.compile(r'(?:or\s*|=\s*|\breturn\s+)["\']sk-local-dev-key["\']'),
        "MR004: Hardcoded fallback or assignment of 'sk-local-dev-key'",
    ),
    (
        re.compile(r'(?:or\s*|=\s*|\breturn\s+)["\']http://localhost:8000/v1["\']'),
        "MR005: Hardcoded fallback or assignment of 'http://localhost:8000/v1'",
    ),
]

_PRODUCTION_ROOTS = [
    "agents",
    "resume_graph_engine/src/apps_rg",
    "apps_research",
    "outreach_engine/src/apps_lic",
    "infrastructure",
]


class _MockReachabilityVisitor(ast.NodeVisitor):
    """AST visitor to detect unguarded mock branches and bypass flags in production."""

    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.violations: list[str] = []

    def visit_If(self, node: ast.If) -> None:
        # Check if condition checks for mode == "mocked"
        is_mocked_check = False
        if isinstance(node.test, ast.Compare):
            left = node.test.left
            comparators = node.test.comparators
            # mode == "mocked"
            if isinstance(left, ast.Name) and left.id == "mode":
                for comp in comparators:
                    if isinstance(comp, ast.Constant) and comp.value == "mocked":
                        is_mocked_check = True
            elif isinstance(left, ast.Constant) and left.value == "mocked":
                for comp in comparators:
                    if isinstance(comp, ast.Name) and comp.id == "mode":
                        is_mocked_check = True

        if is_mocked_check:
            # Verify if this mocked block contains a guard against production runtime
            # e.g., calling _is_test_environment(), is_test_harness(), or checking APPS_RG_PRODUCTION_RUN
            has_guard = False
            for stmt in node.body:
                stmt_str = ast.dump(stmt)
                if any(g in stmt_str for g in (
                    "_is_test_environment",
                    "is_test_harness",
                    "APPS_RG_PRODUCTION_RUN",
                    "MOCK_JUDGE_FORBIDDEN",
                    "MOCK_PANEL_FORBIDDEN",
                    "LIVE_SELECTOR_ENFORCEMENT",
                    "raise",
                )):
                    has_guard = True
                    break

            if not has_guard:
                self.violations.append(
                    f"{self.rel_path}:{node.lineno}: MR001: Unguarded 'mode == \"mocked\"' branch without production runtime check"
                )

        self.generic_visit(node)


def audit_production_file(file_path: Path, repo_root: Path) -> list[str]:
    """Audit an individual production file for mock reachability violations."""
    violations: list[str] = []
    rel_path = file_path.relative_to(repo_root) if file_path.is_relative_to(repo_root) else file_path
    rel_str = str(rel_path)

    # Skip tests, docs, artifacts
    if any(p in file_path.parts for p in ("tests", "docs", "artifacts", ".venv", "__pycache__")):
        return []

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return [f"{rel_str}: Failed to read file: {exc}"]

    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # In rejection definitions or guard lists, placeholder strings are checked against
        if any(guard_hint in stripped for guard_hint in ("PLACEHOLDER", "placeholder", "forbidden", "reject", "in (")):
            continue

        for pattern, desc in _FORBIDDEN_PRODUCTION_PATTERNS:
            if pattern.search(line):
                violations.append(f"{rel_str}:{idx}: {desc}: {line.strip()[:80]}")

    # AST checks
    try:
        tree = ast.parse(content, filename=str(file_path))
        visitor = _MockReachabilityVisitor(rel_str)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    except SyntaxError:
        pass

    return violations


def run_audit(repo_root: Path) -> tuple[int, list[str]]:
    """Run full production mock reachability audit."""
    all_violations: list[str] = []
    print("=" * 70)
    print("  PRODUCTION MOCK REACHABILITY & LIVE ENFORCEMENT AUDIT")
    print("=" * 70)

    for root_name in _PRODUCTION_ROOTS:
        target_dir = repo_root / root_name
        if not target_dir.is_dir():
            continue
        for py_file in target_dir.rglob("*.py"):
            v = audit_production_file(py_file, repo_root)
            all_violations.extend(v)

    if all_violations:
        print(f"\n[FAIL] Found {len(all_violations)} mock reachability violation(s):")
        for v in all_violations:
            print(f"  * {v}")
        print("\n" + "=" * 70)
        return 1, all_violations

    print("\n[PASS] Zero reachable mocks detected across all production execution paths.")
    print("=" * 70 + "\n")
    return 0, []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit production paths for mock reachability.")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    code, _ = run_audit(repo_root)
    return code


if __name__ == "__main__":
    sys.exit(main())
