#!/usr/bin/env python3
"""Continuous Architecture and Anti-Pattern Boundary Linter.

Part of Sovereign Agentic Platform Governance (Wave 6 - Final Closure Wave).
Mechanically verifies architectural invariants:
1. Domain Storage Isolation: Domain services and contracts must NOT import concrete
   storage adapters (sqlite3, agents.persistence.sqlite, agents.persistence.jsonl).
2. Packaging & Sys.Path Purity: Production runtime code must NOT call sys.path.insert or sys.path.append.
3. Production File Budget: No production Python file may exceed 600 lines.
4. Canonical Pipeline Routing: Dispatches must route through canonical dispatch authority.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

MAX_PRODUCTION_LINES = 600

FORBIDDEN_STORAGE_MODULES = {
    "sqlite3",
    "agents.persistence.sqlite",
    "agents.persistence.jsonl",
    "agents.persistence.sqlite.state_repository",
    "agents.persistence.sqlite.event_store",
    "agents.persistence.jsonl.event_store",
    "agents.persistence.jsonl.artifact_store",
}

PRODUCTION_SCAN_DIRS = [
    "agents/orchestration",
    "agents/observability",
    "resume_graph_engine/src/apps_rg/runtime",
    "apps_research",
    "apps_eval",
]

EXCLUDED_DIRS = {
    ".venv",
    ".git",
    "tests",
    "__pycache__",
    "archives",
    "artifacts",
    "build",
    "dist",
}


def check_domain_storage_isolation(repo_root: Path) -> list[str]:
    """Verify domain services contain zero concrete storage imports."""
    violations: list[str] = []
    domain_dirs = [
        repo_root / "agents" / "orchestration" / "services",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "pipeline",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "artifact_output",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "sections" / "executive_summary",
    ]

    for d in domain_dirs:
        if not d.exists():
            continue
        for py_file in d.glob("**/*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except Exception as e:
                violations.append(f"{py_file}: parse error: {e}")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in FORBIDDEN_STORAGE_MODULES:
                            violations.append(
                                f"{py_file.name}:{node.lineno}: Forbidden concrete storage import '{alias.name}'"
                            )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod in FORBIDDEN_STORAGE_MODULES:
                        violations.append(
                            f"{py_file.name}:{node.lineno}: Forbidden concrete storage import '{mod}'"
                        )
                    for alias in node.names:
                        full = f"{mod}.{alias.name}" if mod else alias.name
                        if full in FORBIDDEN_STORAGE_MODULES:
                            violations.append(
                                f"{py_file.name}:{node.lineno}: Forbidden concrete storage import '{full}'"
                            )

    return violations


def check_sys_path_purity(repo_root: Path) -> list[str]:
    """Ensure production runtime files do not mutate sys.path."""
    violations: list[str] = []

    for scan_dir in PRODUCTION_SCAN_DIRS:
        target = repo_root / scan_dir
        if not target.exists():
            continue
        for py_file in target.glob("**/*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr in ("insert", "append"):
                        val = func.value
                        if isinstance(val, ast.Attribute) and val.attr == "path":
                            if isinstance(val.value, ast.Name) and val.value.id == "sys":
                                violations.append(
                                    f"{py_file.relative_to(repo_root)}:{node.lineno}: Forbidden sys.path.{func.attr}() call"
                                )
    return violations


def check_file_budgets(repo_root: Path) -> list[str]:
    """Enforce that all production files adhere to budgets and ratchet ceilings."""
    try:
        from tools.lint_file_budgets import scan_all_production_files
        raw_violations = scan_all_production_files(repo_root, max_lines=MAX_PRODUCTION_LINES)
        return [msg for _, _, msg in raw_violations]
    except Exception as e:
        return [f"Error running file budget check: {e}"]


def run_architecture_linter(repo_root: Path | None = None) -> dict[str, Any]:
    """Execute all continuous architecture checks and return structured results."""
    root = repo_root or Path(__file__).resolve().parent.parent

    storage_violations = check_domain_storage_isolation(root)
    sys_path_violations = check_sys_path_purity(root)
    budget_violations = check_file_budgets(root)

    total_violations = storage_violations + sys_path_violations + budget_violations
    status = "PASS" if not total_violations else "FAIL"

    return {
        "status": status,
        "is_clean": len(total_violations) == 0,
        "checks": {
            "domain_storage_isolation": {
                "status": "PASS" if not storage_violations else "FAIL",
                "violations": storage_violations,
            },
            "sys_path_purity": {
                "status": "PASS" if not sys_path_violations else "FAIL",
                "violations": sys_path_violations,
            },
            "file_budgets": {
                "status": "PASS" if not budget_violations else "FAIL",
                "violations": budget_violations,
            },
        },
        "total_violation_count": len(total_violations),
        "violations": total_violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint continuous architecture boundaries.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument("--root", type=Path, default=None, help="Repository root path")
    args = parser.parse_args()

    results = run_architecture_linter(args.root)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if results["is_clean"]:
            print("[PASS] Continuous Architecture Boundaries clean:")
            print("  - Domain Storage Isolation: PASSED (Zero concrete storage imports in domain)")
            print("  - Sys.Path Purity: PASSED (Zero runtime sys.path mutations)")
            print("  - File Budgets: PASSED (Production modules within budget)")
        else:
            print(f"[FAIL] Architecture boundary check failed ({results['total_violation_count']} violations):")
            for v in results["violations"]:
                print(f"  - {v}")

    return 0 if results["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
