#!/usr/bin/env python3
"""Deterministic production purity linter.

Invariant:
    Production code may not contain, import, load, inject, or otherwise consume
    predetermined domain answers as substitutes for runtime generation or evaluation.
    Production execution must not depend directly or transitively on directories/artifacts
    classified as tests/, fixtures/, golden/, expected outputs, or benchmark references.

Constitutional Doctrine:
    runtime source + approved config -> actual pipeline execution -> generated domain output
    must NEVER become:
    prewritten answer / reference artifact -> production output
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
    "resume_graph_engine/src/apps_rg",
    "apps_research",
    "outreach_engine/src",
    "agents",
)

EXCLUDED_DIRECTORIES: tuple[str, ...] = (
    "tests",
    "fixtures",
    "apps_eval",
    "docs",
    "artifacts",
    "scratch",
    ".git",
    ".venv",
)

# Paths classified as fixtures / goldens / test references
FORBIDDEN_FIXTURE_PATH_PATTERNS: tuple[str, ...] = (
    "fixtures/",
    "/fixtures/",
    "golden/",
    "/golden/",
    "expected_outputs/",
    "/expected_outputs/",
    "benchmark_references/",
    "tests/fixtures",
    "data/eval/golden",
)

# Modules / prefixes forbidden from being imported in production execution
FORBIDDEN_FIXTURE_MODULES: tuple[str, ...] = (
    "fixtures",
    "tests",
    "golden",
    "expected_outputs",
)

# Semantic indicators of precomputed domain synthesis substitution
PREDETERMINED_SYNTHESIS_KEYS: tuple[str, ...] = (
    "executive_summary",
    "final_summary",
    "synthesis",
    "extracted_insights",
    "pinned_eval",
    "pinned_evals",
    "golden_answer",
    "expected_output",
    "result_payload",
    "summary_payload",
    "f2_text",
    "f3_data",
)

GUARDIAN_PATTERN = re.compile(
    r"#\s*guardian:\s*allow-(?:purity|fixture|golden|layer-violation)\s*--\s*(.+)",
    re.IGNORECASE,
)


def is_production_file(path: Path, repo_root: Path) -> bool:
    try:
        rel = str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return False

    for exc in EXCLUDED_DIRECTORIES:
        if exc in rel.split("/") or rel.startswith(f"{exc}/"):
            return False

    if "/tests/" in rel or rel.endswith("_test.py") or Path(rel).name.startswith("test_"):
        return False

    for prod in PRODUCTION_DIRECTORIES:
        if rel == prod or rel.startswith(f"{prod}/"):
            return True

    return False


class ProductionPurityVisitor(ast.NodeVisitor):
    """AST visitor detecting predetermined domain answers and fixture dependencies."""

    def __init__(self, file_path: Path, lines: list[str], rel_path: str):
        self.file_path = file_path
        self.lines = lines
        self.rel_path = rel_path
        self.violations: list[tuple[int, str, str]] = []
        self._docstring_nodes: set[int] = set()

    def _is_exempt(self, lineno: int) -> bool:
        if 1 <= lineno <= len(self.lines):
            line = self.lines[lineno - 1]
            return bool(GUARDIAN_PATTERN.search(line))
        return False

    def visit_Module(self, node: ast.Module) -> None:
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            self._docstring_nodes.add(node.body[0].value.lineno)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            self._docstring_nodes.add(node.body[0].value.lineno)

        func_name_lower = node.name.lower()
        if any(func_name_lower.startswith(prefix) for prefix in ("generate_", "synthesize_", "extract_", "evaluate_")):
            for stmt in node.body:
                if isinstance(stmt, ast.Return) and stmt.value:
                    val = stmt.value
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        s = val.value.strip()
                        if len(s) > 80 and not self._is_prompt_template(s):
                            if not self._is_exempt(stmt.lineno):
                                self.violations.append(
                                    (
                                        stmt.lineno,
                                        node.name,
                                        f"Function '{node.name}' directly returns predetermined multiline domain answer instead of runtime generation.",
                                    )
                                )
                    elif isinstance(val, ast.Dict):
                        if self._is_predetermined_dict(val):
                            if not self._is_exempt(stmt.lineno):
                                self.violations.append(
                                    (
                                        stmt.lineno,
                                        node.name,
                                        f"Function '{node.name}' returns predetermined domain dictionary payload substituting for runtime pipeline execution.",
                                    )
                                )

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            self._docstring_nodes.add(node.body[0].value.lineno)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            self._docstring_nodes.add(node.body[0].value.lineno)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            first_part = alias.name.split(".")[0]
            if first_part in FORBIDDEN_FIXTURE_MODULES:
                if not self._is_exempt(node.lineno):
                    self.violations.append(
                        (
                            node.lineno,
                            alias.name,
                            f"Production code cannot import test/fixture artifact '{alias.name}'. Fixtures may only be consumed in test/eval contexts.",
                        )
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            first_part = node.module.split(".")[0]
            if first_part in FORBIDDEN_FIXTURE_MODULES:
                if not self._is_exempt(node.lineno):
                    self.violations.append(
                        (
                            node.lineno,
                            node.module,
                            f"Production code cannot import test/fixture artifact '{node.module}'. Fixtures may only be consumed in test/eval contexts.",
                        )
                    )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        target_names = []
        for t in node.targets:
            if isinstance(t, ast.Name):
                target_names.append(t.id)

        for target_name in target_names:
            name_lower = target_name.lower()
            if any(k in name_lower for k in PREDETERMINED_SYNTHESIS_KEYS):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    s = node.value.value.strip()
                    if len(s) > 80 and not self._is_prompt_template(s):
                        if not self._is_exempt(node.lineno):
                            self.violations.append(
                                (
                                    node.lineno,
                                    target_name,
                                    f"Variable '{target_name}' contains hardcoded predetermined domain text ({len(s)} chars) substituting for runtime synthesis.",
                                )
                            )
                elif isinstance(node.value, ast.Dict):
                    if self._is_predetermined_dict(node.value):
                        if not self._is_exempt(node.lineno):
                            self.violations.append(
                                (
                                    node.lineno,
                                    target_name,
                                    f"Variable '{target_name}' contains precomputed domain payload substituting for runtime generation.",
                                )
                            )

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                s = arg.value
                if any(fp in s for fp in FORBIDDEN_FIXTURE_PATH_PATTERNS):
                    if not self._is_exempt(node.lineno):
                        self.violations.append(
                            (
                                node.lineno,
                                s,
                                f"Production code attempts to load fixture/golden artifact '{s}'. Goldens and fixtures are strictly forbidden from production execution paths.",
                            )
                        )
        self.generic_visit(node)

    @staticmethod
    def _is_prompt_template(s: str) -> bool:
        if "{" in s and "}" in s:
            return True
        if re.search(r"\$\{[A-Za-z0-9_]+\}|\$[A-Za-z_][A-Za-z0-9_]*", s):
            return True
        lower = s.lower()
        if any(
            kw in lower
            for kw in (
                "you are",
                "instructions:",
                "prompt:",
                "guidelines:",
                "system:",
                "assistant:",
                "do not",
                "proof_boundary",
                "proof_gap",
                "remediation",
                "never introduce",
            )
        ):
            return True
        return False

    def _is_predetermined_dict(self, node: ast.Dict) -> bool:
        """Check if a dictionary literal represents a precomputed final graph or synthesis payload."""
        string_keys = []
        constant_values_count = 0
        multiline_domain_count = 0

        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                string_keys.append(k.value.lower())
                if isinstance(v, ast.Constant):
                    constant_values_count += 1
                    if isinstance(v.value, str) and len(v.value) > 60 and not self._is_prompt_template(v.value):
                        multiline_domain_count += 1
                elif isinstance(v, (ast.List, ast.Dict)):
                    # Check if inner structure contains static constants
                    if all(isinstance(elt, ast.Constant) for elt in getattr(v, "elts", [])):
                        constant_values_count += 1

        # Must be mostly static constant values (not dynamic expressions like call/get)
        if constant_values_count >= 2 and any(
            k in string_keys for k in ("nodes", "edges", "executive_summary", "synthesis", "verdict", "final_summary", "result_payload")
        ):
            if multiline_domain_count >= 1 or constant_values_count >= 3:
                return True

        return False


def check_file_production_purity(
    file_path: Path,
    repo_root: Path,
) -> list[tuple[int, str, str]]:
    """Scan a production file for production purity violations."""
    if not file_path.exists() or not is_production_file(file_path, repo_root):
        return []

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        tree = ast.parse("\n".join(lines), filename=str(file_path))
    except SyntaxError:
        return []

    try:
        rel = str(file_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        rel = str(file_path)

    visitor = ProductionPurityVisitor(file_path, lines, rel)
    visitor.visit(tree)
    return visitor.violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic production purity linter.")
    parser.add_argument("--files", nargs="*", help="Specific files to check")
    parser.add_argument("--all", action="store_true", help="Scan all production Python files")
    parser.add_argument("--repo-root", default=".", help="Root of repository")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    violations: list[tuple[str, int, str, str]] = []

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
            v = check_file_production_purity(f, repo_root)
            for lineno, symbol, msg in v:
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                violations.append((rel, lineno, symbol, msg))

    if violations:
        print(f"[FAIL] Production purity violations found ({len(violations)} violations):", file=sys.stderr)
        for rel, lineno, symbol, msg in violations:
            print(f"  - {rel}:{lineno} [{symbol}]: {msg}", file=sys.stderr)
        return 1

    print(f"[PASS] Production purity clean (no predetermined answers or fixture dependencies in production paths).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
