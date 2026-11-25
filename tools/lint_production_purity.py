#!/usr/bin/env python3
"""Deterministic production purity linter delegating to core-governance with standalone CI fallback."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
from pathlib import Path
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

PRODUCTION_DIRECTORIES: tuple[str, ...] = (
    "scripts",
    "tools",
    "resume_graph_engine",
    "resume_engine",
    "apps_research",
    "apps_model_telemetry",
    "infrastructure",
    "ops_scripts",
    "outreach_engine",
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

FORBIDDEN_FIXTURE_PATH_PATTERNS: tuple[str, ...] = _BACKEND.FORBIDDEN_FIXTURE_PATHS
FORBIDDEN_FIXTURE_MODULES: tuple[str, ...] = tuple(sorted(_BACKEND.FORBIDDEN_FIXTURE_MODULES))
PREDETERMINED_SYNTHESIS_KEYS: tuple[str, ...] = tuple(sorted(_BACKEND.PREDETERMINED_KEYS))
GUARDIAN_PATTERN = _BACKEND.PURITY_GUARDIAN_RE


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

    return any(rel == prod or rel.startswith(f"{prod}/") for prod in PRODUCTION_DIRECTORIES)


def _scan_agents_function_return_purity(
    tree: ast.AST,
    lines: list[str],
    backend: ModuleType,
) -> list[tuple[int, str, str]]:
    """Supplement shared purity visitor with direct-return checks on synthesis/generation functions."""
    extra: list[tuple[int, str, str]] = []
    is_prompt = backend._is_prompt_template
    is_static_dict = backend.ProductionPurityAstVisitor._is_static_domain_dict
    guardian_re = backend.PURITY_GUARDIAN_RE

    def _exempt(lineno: int) -> bool:
        return 1 <= lineno <= len(lines) and bool(guardian_re.search(lines[lineno - 1]))

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.lower().startswith(
            ("generate_", "synthesize_", "extract_", "evaluate_")
        ):
            for stmt in node.body:
                if isinstance(stmt, ast.Return) and stmt.value and not _exempt(stmt.lineno):
                    val = stmt.value
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        s = val.value.strip()
                        if len(s) > 80 and not is_prompt(s, node.name):
                            extra.append(
                                (
                                    stmt.lineno,
                                    node.name,
                                    f"Function '{node.name}' directly returns predetermined multiline domain answer instead of runtime generation.",
                                )
                            )
                    elif isinstance(val, ast.Dict) and is_static_dict(val):
                        extra.append(
                            (
                                stmt.lineno,
                                node.name,
                                f"Function '{node.name}' returns predetermined domain dictionary payload substituting for runtime pipeline execution.",
                            )
                        )
        elif isinstance(node, ast.Assign) and not _exempt(node.lineno):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    low = t.id.lower()
                    if (
                        low not in backend.PREDETERMINED_KEYS
                        and any(k in low for k in PREDETERMINED_SYNTHESIS_KEYS)
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)
                    ):
                        s = node.value.value.strip()
                        if len(s) > 80 and not is_prompt(s, t.id):
                            extra.append(
                                (
                                    node.lineno,
                                    t.id,
                                    f"Variable '{t.id}' contains hardcoded predetermined domain text ({len(s)} chars) substituting for runtime synthesis.",
                                )
                            )
    return extra


def check_file_production_purity(
    file_path: Path,
    repo_root: Path,
    tree: ast.AST | None = None,
    lines: list[str] | None = None,
) -> list[tuple[int, str, str]]:
    """Scan a production file for production purity violations via core-governance or standalone fallback."""
    if not file_path.exists() or not is_production_file(file_path, repo_root):
        return []

    src_lines = lines if lines is not None else file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    parsed = tree
    if parsed is None:
        try:
            parsed = ast.parse("\n".join(src_lines), filename=str(file_path))
        except SyntaxError:
            return []

    backend = _load_backend()
    visitor = backend.ProductionPurityAstVisitor(src_lines)
    visitor.visit(parsed)
    combined: list[tuple[int, str, str]] = []
    for ln, sym, msg in visitor.violations:
        if "precomputed domain payload" in msg and not any(k in sym.lower() for k in PREDETERMINED_SYNTHESIS_KEYS):
            continue
        if "binds forbidden fixture path" in msg and "config/fixtures/" in src_lines[ln - 1]:
            continue
        combined.append((ln, sym, msg))
    seen = {(ln, sym) for ln, sym, _ in combined}
    for ln, sym, msg in _scan_agents_function_return_purity(parsed, src_lines, backend):
        if (ln, sym) not in seen:
            seen.add((ln, sym))
            combined.append((ln, sym, msg))
    return combined


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
            for lineno, symbol, msg in check_file_production_purity(f, repo_root):
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                violations.append((rel, lineno, symbol, msg))

    if violations:
        print(f"[FAIL] Production purity violations found ({len(violations)} violations):", file=sys.stderr)
        for rel, lineno, symbol, msg in violations:
            print(f"  - {rel}:{lineno} [{symbol}]: {msg}", file=sys.stderr)
        return 1

    print("[PASS] Production purity clean (no predetermined answers or fixture dependencies in production paths).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
