#!/usr/bin/env python3
"""Audit production codebase to guarantee zero reachable mocks in production execution paths."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Sequence

_FORBIDDEN_MOCK_LITERALS: dict[str, tuple[str, str]] = {
    "sk-local-dev-key": (
        "MR004",
        "Hardcoded fallback, default, or assignment of 'sk-local-dev-key'",
    ),
    "http://localhost:8000/v1": (
        "MR005",
        "Hardcoded fallback, default, or assignment of 'http://localhost:8000/v1'",
    ),
}

_PRODUCTION_ROOTS = [
    "agents",
    "apps_eval",
    "apps_model_telemetry",
    "apps_research",
    "infrastructure",
    "ops_scripts",
    "outreach_engine",
    "resume_engine",
    "resume_graph_engine",
    "scripts",
    "tools",
]


def _check_forbidden_literal(expr: ast.AST | None) -> tuple[str, str, str] | None:
    """Return (code, desc, literal) if expr is a direct forbidden mock constant."""
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        val = expr.value.strip()
        if val in _FORBIDDEN_MOCK_LITERALS:
            code, desc = _FORBIDDEN_MOCK_LITERALS[val]
            return code, desc, val
    return None


def _is_mocked_mode_comparison(test: ast.AST) -> bool:
    """Return True when condition tests `mode == 'mocked'` (directly or inside boolean ops)."""
    for sub in ast.walk(test):
        if isinstance(sub, ast.Compare) and any(isinstance(op, (ast.Eq, ast.Is)) for op in sub.ops):
            left = sub.left
            comparators = sub.comparators
            if isinstance(left, ast.Name) and left.id == "mode":
                for comp in comparators:
                    if isinstance(comp, ast.Constant) and comp.value == "mocked":
                        return True
            elif isinstance(left, ast.Constant) and left.value == "mocked":
                for comp in comparators:
                    if isinstance(comp, ast.Name) and comp.id == "mode":
                        return True
    return False


def _has_runtime_guard_ast(stmts: Sequence[ast.stmt]) -> bool:
    """Verify via AST (not stringified dump) that branch raises or invokes a test-harness guard."""
    guard_fn_names = {"_is_test_environment", "is_test_harness"}
    for stmt in stmts:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Raise):
                return True
            if isinstance(sub, ast.Call):
                fn = sub.func
                if isinstance(fn, ast.Name) and fn.id in guard_fn_names:
                    return True
                if isinstance(fn, ast.Attribute) and fn.attr in guard_fn_names:
                    return True
    return False


class _MockReachabilityVisitor(ast.NodeVisitor):
    """AST visitor to detect unguarded mock branches and forbidden credential/endpoint fallbacks."""

    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.violations: list[str] = []
        self._if_stack: list[ast.If] = []

    def _record_literal(self, lineno: int, hit: tuple[str, str, str]) -> None:
        code, desc, val = hit
        self.violations.append(f"{self.rel_path}:{lineno}: {code}: {desc} ('{val}')")

    def visit_Assign(self, node: ast.Assign) -> None:
        hit = _check_forbidden_literal(node.value)
        if hit is not None:
            self._record_literal(node.lineno, hit)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        hit = _check_forbidden_literal(node.value)
        if hit is not None:
            self._record_literal(node.lineno, hit)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        hit = _check_forbidden_literal(node.value)
        if hit is not None:
            self._record_literal(node.lineno, hit)
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, ast.Or):
            for val in node.values[1:]:
                hit = _check_forbidden_literal(val)
                if hit is not None:
                    self._record_literal(getattr(val, "lineno", node.lineno), hit)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_fn_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_fn_defaults(node)
        self.generic_visit(node)

    def _check_fn_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
        for default_expr in defaults:
            hit = _check_forbidden_literal(default_expr)
            if hit is not None:
                self._record_literal(getattr(default_expr, "lineno", node.lineno), hit)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in ("get", "setdefault"):
            if len(node.args) >= 2:
                hit = _check_forbidden_literal(node.args[1])
                if hit is not None:
                    self._record_literal(node.lineno, hit)
        for kw in node.keywords:
            if kw.arg in ("api_key", "base_url", "endpoint", "default"):
                hit = _check_forbidden_literal(kw.value)
                if hit is not None:
                    self._record_literal(node.lineno, hit)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        # Check direct `if mode == "mocked":` branches (excluding nested checks already inside a guarded parent If)
        is_direct_mock_if = False
        if isinstance(node.test, ast.Compare):
            is_direct_mock_if = _is_mocked_mode_comparison(node.test)
        elif isinstance(node.test, ast.BoolOp) and isinstance(node.test.op, ast.And):
            is_direct_mock_if = any(
                isinstance(v, ast.Compare) and _is_mocked_mode_comparison(v) for v in node.test.values
            )

        if is_direct_mock_if and not _has_runtime_guard_ast(node.body):
            parent_guarded = any(_has_runtime_guard_ast(parent.body) for parent in self._if_stack)
            if not parent_guarded:
                self.violations.append(
                    f"{self.rel_path}:{node.lineno}: MR001: Unguarded 'mode == \"mocked\"' branch without production runtime check"
                )

        self._if_stack.append(node)
        self.generic_visit(node)
        self._if_stack.pop()


def audit_production_file(file_path: Path, repo_root: Path) -> list[str]:
    """Audit an individual production file for mock reachability violations via AST."""
    rel_path = file_path.relative_to(repo_root) if file_path.is_relative_to(repo_root) else file_path
    rel_str = str(rel_path)

    if any(p in file_path.parts for p in ("tests", "docs", "artifacts", ".venv", "__pycache__")):
        return []

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"{rel_str}: Failed to read file: {exc}"]

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as exc:
        return [f"{rel_str}:{exc.lineno or 1}: MR000: SyntaxError in production module: {exc.msg}"]

    visitor = _MockReachabilityVisitor(rel_str)
    visitor.visit(tree)
    return visitor.violations


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
        for py_file in sorted(target_dir.rglob("*.py")):
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
