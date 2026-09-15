#!/usr/bin/env python3
"""Deterministic layer import linter enforcing architectural layer boundaries and isolation.

Governance Rules:
    1. Production code cannot import from tests/, fixtures/, archives/, or docs/.
    2. Testing frameworks (pytest, unittest.mock) must not be imported in production code.
    3. Cross-layer violations require explicit guardian exemption:
       `# guardian: allow-layer-violation -- <specific justification>`
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Sequence

PRODUCTION_DIRECTORIES: tuple[str, ...] = (
    "scripts",
    "dual_pipeline",
    "storage",
    "resume_graph_engine/src",
    "apps_research",
    "outreach_engine/src",
    "agents",
)

NON_PRODUCTION_DIRECTORIES: tuple[str, ...] = (
    "tests",
    "fixtures",
    "docs",
    "artifacts",
    "scratch",
    ".git",
    ".venv",
)

FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "tests",
    "fixtures",
    "archive",
    "archives",
    "docs",
    "pytest",
    "unittest.mock",
)

GUARDIAN_PATTERN = re.compile(
    r"#\s*guardian:\s*allow-layer-violation\s*--\s*(.+)",
    re.IGNORECASE,
)


def is_production_path(path: Path | str, repo_root: Path) -> bool:
    """Check whether a path falls within a production-executable scope."""
    p = Path(path).resolve()
    try:
        rel = str(p.relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return False

    # Exclude non-production paths explicitly
    for non_prod in NON_PRODUCTION_DIRECTORIES:
        if rel == non_prod or rel.startswith(f"{non_prod}/") or f"/{non_prod}/" in rel:
            return False

    # Skip files with test_ in name
    if "/tests/" in rel or rel.endswith("_test.py") or Path(rel).name.startswith("test_"):
        return False

    for prod in PRODUCTION_DIRECTORIES:
        if rel == prod or rel.startswith(f"{prod}/"):
            return True

    return False


def check_file_layer_imports(
    file_path: Path,
    repo_root: Path,
) -> list[tuple[int, str, str]]:
    """Inspect Python file AST for layer boundary violations.

    Returns:
        List of (line_number, imported_module, reason)
    """
    if not file_path.exists() or not is_production_path(file_path, repo_root):
        return []

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    violations: list[tuple[int, str, str]] = []

    try:
        tree = ast.parse("\n".join(lines), filename=str(file_path))
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        imported_names = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.append((node.module, node.lineno))

        for name, lineno in imported_names:
            first_part = name.split(".")[0]
            if first_part in FORBIDDEN_IMPORT_PREFIXES or any(name.startswith(f"{p}.") for p in FORBIDDEN_IMPORT_PREFIXES):
                # Check line for guardian exemption
                line_content = lines[lineno - 1] if 1 <= lineno <= len(lines) else ""
                if GUARDIAN_PATTERN.search(line_content):
                    continue
                violations.append(
                    (
                        lineno,
                        name,
                        f"Forbidden production import '{name}' (cannot import tests/fixtures/archives/pytest in production)",
                    )
                )

    return violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic layer import linter.")
    parser.add_argument("--files", nargs="*", help="Specific files to check")
    parser.add_argument("--all", action="store_true", help="Scan all production Python files")
    parser.add_argument("--repo-root", default=".", help="Root of repository")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    all_violations: list[tuple[str, int, str, str]] = []

    if args.files:
        files_to_check = [Path(f) if Path(f).is_absolute() else repo_root / f for f in args.files]
    else:
        files_to_check = []
        for prod_dir in PRODUCTION_DIRECTORIES:
            d = repo_root / prod_dir
            if d.exists():
                files_to_check.extend(d.rglob("*.py"))

    for f in files_to_check:
        if f.suffix == ".py":
            v = check_file_layer_imports(f, repo_root)
            for lineno, mod, msg in v:
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                all_violations.append((rel, lineno, mod, msg))

    if all_violations:
        print(f"[FAIL] Layer import violations found ({len(all_violations)} violations):", file=sys.stderr)
        for rel, lineno, mod, msg in all_violations:
            print(f"  - {rel}:{lineno}: {msg}", file=sys.stderr)
        return 1

    print(f"[PASS] Layer imports clean (no illegal cross-layer or test/fixture imports in production).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
