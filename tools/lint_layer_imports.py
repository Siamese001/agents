#!/usr/bin/env python3
"""Deterministic layer import linter delegating to core-governance with standalone CI fallback."""

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

_PLUGIN_FILE = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp" / "boundary_naming_linters.py"
_CACHED_PLUGIN_MOD: ModuleType | None = None


def _load_backend() -> ModuleType:
    """Resolve core-governance boundary_naming_linters unless standalone mode is forced or plugin is absent."""
    global _CACHED_PLUGIN_MOD
    if os.environ.get("CORE_GOVERNANCE_FORCE_STANDALONE") != "1" and _PLUGIN_FILE.is_file():
        if _CACHED_PLUGIN_MOD is None:
            mod_name = "_core_governance_boundary_naming_linters"
            spec = importlib.util.spec_from_file_location(mod_name, _PLUGIN_FILE)
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                _CACHED_PLUGIN_MOD = mod
        if _CACHED_PLUGIN_MOD is not None:
            return _CACHED_PLUGIN_MOD
    from tools import _standalone_boundary_naming

    return _standalone_boundary_naming


_BACKEND = _load_backend()

PRODUCTION_DIRECTORIES: tuple[str, ...] = (
    "scripts",
    "tools",
    "resume_graph_engine",
    "resume_engine",
    "apps_research",
    "apps_eval",
    "apps_model_telemetry",
    "infrastructure",
    "ops_scripts",
    "outreach_engine",
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

FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = _BACKEND.DEFAULT_FORBIDDEN_IMPORTS
GUARDIAN_PATTERN = _BACKEND.LAYER_GUARDIAN_RE


def is_production_path(path: Path | str, repo_root: Path) -> bool:
    """Check whether a path falls within a production-executable scope."""
    p = Path(path).resolve()
    try:
        rel = str(p.relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return False

    for non_prod in NON_PRODUCTION_DIRECTORIES:
        if rel == non_prod or rel.startswith(f"{non_prod}/") or f"/{non_prod}/" in rel:
            return False

    if "/tests/" in rel or rel.endswith("_test.py") or Path(rel).name.startswith("test_"):
        return False

    return any(rel == prod or rel.startswith(f"{prod}/") for prod in PRODUCTION_DIRECTORIES)


def check_file_layer_imports(
    file_path: Path,
    repo_root: Path,
    tree: ast.AST | None = None,
    lines: list[str] | None = None,
) -> list[tuple[int, str, str]]:
    """Inspect Python file AST for layer boundary violations via core-governance or standalone fallback."""
    return list(
        _load_backend().check_forbidden_production_imports(
            file_path,
            repo_root,
            production_dirs=PRODUCTION_DIRECTORIES,
            non_production_dirs=NON_PRODUCTION_DIRECTORIES,
            forbidden_prefixes=FORBIDDEN_IMPORT_PREFIXES,
            tree=tree,
            lines=lines,
        )
    )


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
            for lineno, mod, msg in check_file_layer_imports(f, repo_root):
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                all_violations.append((rel, lineno, mod, msg))

    if all_violations:
        print(f"[FAIL] Layer import violations found ({len(all_violations)} violations):", file=sys.stderr)
        for rel, lineno, _mod, msg in all_violations:
            print(f"  - {rel}:{lineno}: {msg}", file=sys.stderr)
        return 1

    print("[PASS] Layer imports clean (no illegal cross-layer or test/fixture imports in production).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
