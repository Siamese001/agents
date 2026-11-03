#!/usr/bin/env python3
"""Continuous Architectural Boundary & Anti-Pattern Linter (Wave 6).

Enforces repository-wide architectural constraints across:
- Domain Storage Isolation: Zero concrete persistence imports in domain services.
- Sys.Path Purity: Zero runtime `sys.path.insert()` or `sys.path.append()` mutations in production.
- Production File Budgets: Ceiling compliance for all production modules (<= 600 lines).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.lint_file_budgets import scan_all_production_files

FORBIDDEN_STORAGE_MODULES = {
    "sqlite3",
    "agents.persistence.sqlite",
    "agents.persistence.jsonl",
    "agents.persistence.sqlite.state_repository",
    "agents.persistence.sqlite.event_store",
    "agents.persistence.jsonl.event_store",
    "agents.persistence.jsonl.artifact_store",
}

FORBIDDEN_STORAGE_CLASSES = {
    "SqliteStateRepository",
    "SqliteEventStore",
    "JsonlEventStore",
    "FilesystemArtifactStore",
}

DOMAIN_SERVICE_DIRS = [
    "resume_graph_engine/src/apps_rg/runtime/artifact_output",
    "resume_graph_engine/src/apps_rg/runtime/pipeline",
    "resume_graph_engine/src/apps_rg/runtime/sections",
    "resume_engine",
    "outreach_engine/src/apps_lic",
    "apps_research",
    "apps_eval",
    "apps_model_telemetry",
    "agents/orchestration/services",
]

LINE_BUDGET_CEILING = 600


def check_domain_storage_isolation(
    repo_root: Path,
    *,
    ast_cache: dict[Path, ast.AST | None] | None = None,
) -> list[str]:
    """Scan domain services for concrete persistence imports."""
    violations: list[str] = []

    for rel_dir in DOMAIN_SERVICE_DIRS:
        abs_dir = repo_root / rel_dir
        if not abs_dir.exists():
            continue

        for py_file in abs_dir.glob("**/*.py"):
            tree = ast_cache.get(py_file) if ast_cache is not None and py_file in ast_cache else None
            if tree is None:
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"), filename=str(py_file))
                    if ast_cache is not None:
                        ast_cache[py_file] = tree
                except Exception as e:
                    violations.append(f"{py_file.name}: AST parse error: {e}")
                    continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in FORBIDDEN_STORAGE_MODULES:
                            violations.append(
                                f"{py_file.name}:{node.lineno}: Forbidden concrete persistence import: '{alias.name}'"
                            )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod in FORBIDDEN_STORAGE_MODULES:
                        violations.append(
                            f"{py_file.name}:{node.lineno}: Forbidden concrete persistence import: '{mod}'"
                        )
                    for alias in node.names:
                        full = f"{mod}.{alias.name}" if mod else alias.name
                        if full in FORBIDDEN_STORAGE_MODULES or alias.name in FORBIDDEN_STORAGE_CLASSES:
                            violations.append(
                                f"{py_file.name}:{node.lineno}: Forbidden concrete persistence symbol: '{alias.name}'"
                            )

    return violations


# Legacy sys.path mutations removed in Wave 2 packaging SSOT
LEGACY_SYS_PATH_ALLOWLIST: set[str] = set()


def check_sys_path_purity(
    repo_root: Path,
    *,
    ast_cache: dict[Path, ast.AST | None] | None = None,
) -> list[str]:
    """Verify zero sys.path mutations in domain modules and package entrypoints."""
    violations: list[str] = []

    target_files_and_dirs = [
        repo_root / "agents/orchestration",
        repo_root / "agents/persistence",
        repo_root / "agents/observability",
        repo_root / "resume_engine",
        repo_root / "outreach_engine/__init__.py",
        repo_root / "outreach_engine/__main__.py",
        repo_root / "outreach_engine/src/apps_lic",
        repo_root / "resume_graph_engine/__init__.py",
        repo_root / "resume_graph_engine/__main__.py",
        repo_root / "resume_graph_engine/src/apps_rg",
        repo_root / "apps_research",
        repo_root / "apps_eval",
        repo_root / "apps_model_telemetry",
        repo_root / "infrastructure",
    ]

    seen: set[Path] = set()
    for item in target_files_and_dirs:
        if not item.exists():
            continue
        py_files = [item] if item.is_file() else list(item.glob("**/*.py"))

        for py_file in py_files:
            if py_file in seen:
                continue
            seen.add(py_file)
            if "test_" in py_file.name or "tests" in str(py_file):
                continue
            try:
                rel = py_file.relative_to(repo_root).as_posix()
            except ValueError:
                rel = py_file.name
            if rel in LEGACY_SYS_PATH_ALLOWLIST:
                continue
            tree = ast_cache.get(py_file) if ast_cache is not None and py_file in ast_cache else None
            if tree is None:
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"), filename=str(py_file))
                    if ast_cache is not None:
                        ast_cache[py_file] = tree
                except (OSError, SyntaxError, ValueError):
                    continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr in ("insert", "append"):
                        val = func.value
                        if isinstance(val, ast.Attribute) and val.attr == "path":
                            if isinstance(val.value, ast.Name) and val.value.id == "sys":
                                violations.append(
                                    f"{py_file.name}:{node.lineno}: Forbidden sys.path.{func.attr}() call in {rel}"
                                )

    return violations


def check_file_budgets(repo_root: Path) -> list[str]:
    """Enforce production file ceilings across all 11 executable roots with ratchet governance."""
    violations: list[str] = []
    for _rel_path, _lines, msg in scan_all_production_files(repo_root, max_lines=LINE_BUDGET_CEILING):
        violations.append(msg)
    return violations


def run_architecture_linter(
    repo_root: Path,
    *,
    ast_cache: dict[Path, ast.AST | None] | None = None,
) -> dict[str, Any]:
    """Run all continuous architecture checks and return structured diagnostic results."""
    storage_violations = check_domain_storage_isolation(repo_root, ast_cache=ast_cache)
    syspath_violations = check_sys_path_purity(repo_root, ast_cache=ast_cache)
    budget_violations = check_file_budgets(repo_root)

    total_violations = len(storage_violations) + len(syspath_violations) + len(budget_violations)
    is_clean = total_violations == 0

    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "total_violation_count": total_violations,
        "checks": {
            "domain_storage_isolation": {
                "status": "PASS" if not storage_violations else "FAIL",
                "violation_count": len(storage_violations),
                "violations": storage_violations,
            },
            "sys_path_purity": {
                "status": "PASS" if not syspath_violations else "FAIL",
                "violation_count": len(syspath_violations),
                "violations": syspath_violations,
            },
            "file_budgets": {
                "status": "PASS" if not budget_violations else "FAIL",
                "violation_count": len(budget_violations),
                "violations": budget_violations,
            },
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Architectural Boundary & Anti-Pattern Linter")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root path")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    results = run_architecture_linter(repo_root)

    if args.json:
        print(json.dumps(results, indent=2))
        return 0 if results["is_clean"] else 1

    if not results["is_clean"]:
        print(f"[FAIL] Found {results['total_violation_count']} architectural boundary violation(s):", file=sys.stderr)
        for check_name, data in results["checks"].items():
            if data["violations"]:
                print(f"  [{check_name}]:", file=sys.stderr)
                for v in data["violations"]:
                    print(f"    - {v}", file=sys.stderr)
        return 1

    print("[PASS] Architectural boundaries clean (Zero concrete storage imports, sys.path clean, line budgets respected).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
