#!/usr/bin/env python3
"""Deterministic model-neutral naming and literal linter delegating to core-governance with standalone fallback."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
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
    "resume_graph_engine/src",
    "resume_graph_engine/tools",
    "resume_engine",
    "apps_research",
    "apps_eval",
    "apps_model_telemetry",
    "infrastructure",
    "ops_scripts",
    "outreach_engine/src",
    "agents",
)

EXCLUDED_DIRECTORIES: tuple[str, ...] = (
    "tests",
    "fixtures",
    "docs",
    "artifacts",
    "scratch",
    ".git",
    ".venv",
)

CANONICAL_MODEL_CATALOG_FILES: tuple[str, ...] = (
    "core_model_catalog.py",
)

MODEL_PATTERN = _BACKEND.AST_MODEL_LITERAL_RE
PROHIBITED_TOKEN_PATTERNS = list(_BACKEND.PROHIBITED_PATH_MODEL_PATTERNS)
GUARDIAN_PATTERN = _BACKEND.MODEL_GUARDIAN_RE

EXEMPT_PATH_PATTERNS = [
    re.compile(r"^\.git/"),
    re.compile(r"^\.venv/"),
    re.compile(r"^__pycache__/"),
    re.compile(r"^\.pytest_cache/"),
    re.compile(r"^\.agents/"),
    re.compile(r"^archive/"),
    re.compile(r"^artifacts/"),
    re.compile(r"^docs/archive/"),
    re.compile(r"^plans/live-llm-enforcement-wave1-b7d14e\.md$"),
    re.compile(r"(?:^|/)tests/"),
    re.compile(r"^scratch/"),
]

EXEMPT_PACKAGE_PREFIX_PATTERNS = [
    r"^tools/run_luna_[^/]+",
    r"^infrastructure/sdks_mcps/gemini_client",
    r"^resume_graph_engine/src/apps_rg/runtime/judges/bullet_pool_claude_selector",
]


def is_path_exempt(rel_path: str) -> bool:
    """Check if the given relative path is exempt from model-naming constraints."""
    return bool(
        _load_backend().is_model_path_exempt(
            rel_path,
            exempt_patterns=EXEMPT_PATH_PATTERNS,
            exempt_package_prefixes=EXEMPT_PACKAGE_PREFIX_PATTERNS,
        )
    )


def check_path_model_neutrality(
    path: Path,
    repo_root: Path,
) -> list[str]:
    """Scan a file path and its filename for forbidden model naming tokens."""
    try:
        rel = str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        rel = str(path).replace("\\", "/")
        rel = re.sub(r"^.*?/\.gemini/(?:antigravity/brain/[^/]+|config/plugins)/", "", rel)

    hits = _load_backend().scan_path_for_model_tokens(
        rel,
        exempt_patterns=EXEMPT_PATH_PATTERNS,
        exempt_package_prefixes=EXEMPT_PACKAGE_PREFIX_PATTERNS,
    )
    return [v.detail for v in hits]


def is_production_file(path: Path, repo_root: Path) -> bool:
    try:
        rel = str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return False

    if any(exc in rel.split("/") for exc in EXCLUDED_DIRECTORIES):
        return False

    return any(rel == prod or rel.startswith(f"{prod}/") for prod in PRODUCTION_DIRECTORIES)


def check_file_model_neutrality(
    file_path: Path,
    repo_root: Path,
    tree: ast.AST | None = None,
    lines: list[str] | None = None,
) -> list[tuple[int, str, str]]:
    """Scan a Python file for hardcoded model literals and filename branding."""
    return list(
        _load_backend().check_file_model_neutrality(
            file_path,
            repo_root,
            production_dirs=PRODUCTION_DIRECTORIES,
            excluded_dirs=EXCLUDED_DIRECTORIES,
            exempt_patterns=EXEMPT_PATH_PATTERNS,
            exempt_package_prefixes=EXEMPT_PACKAGE_PREFIX_PATTERNS,
            catalog_files=CANONICAL_MODEL_CATALOG_FILES,
            tree=tree,
            lines=lines,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic model-neutral naming linter.")
    parser.add_argument("--files", nargs="*", help="Specific files to check")
    parser.add_argument("--all", action="store_true", help="Scan all production Python files")
    parser.add_argument("--repo-root", default=".", help="Root of repository")
    parser.add_argument("--baseline", help="Path to model literal baseline JSON file")
    parser.add_argument("--create-baseline", action="store_true", help="Create baseline JSON file from current scan")
    parser.add_argument("--ratchet", action="store_true", help="Enforce that violations do not exceed baseline")

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
        for lineno, val, msg in check_file_model_neutrality(f, repo_root):
            rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
            violations.append((rel, lineno, val, msg))

    if args.create_baseline and args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.is_absolute():
            baseline_path = repo_root / baseline_path
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        file_counts: dict[str, int] = {}
        for rel, *_ in violations:
            file_counts[rel] = file_counts.get(rel, 0) + 1
        payload = {
            "version": 1,
            "total_violations": len(violations),
            "file_counts": file_counts,
        }
        baseline_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[BASELINE] Saved baseline with {len(violations)} violations across {len(file_counts)} files to {baseline_path}")
        return 0

    if args.ratchet and args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.is_absolute():
            baseline_path = repo_root / baseline_path
        passed, regressions = _load_backend().evaluate_model_ratchet(violations, baseline_path)
        if not passed:
            print(f"[FAIL] Model-neutral naming ratchet failure ({len(regressions)} regressions):", file=sys.stderr)
            for r in regressions:
                print(f"  - {r}", file=sys.stderr)
            return 1
        cur_files = {rel for rel, *_ in violations}
        print(f"[PASS] Model-neutral naming ratchet passed: {len(violations)} violations within baseline across {len(cur_files)} files.")
        return 0

    if violations:
        print(f"[FAIL] Model-neutral naming violations found ({len(violations)} violations):", file=sys.stderr)
        for rel, lineno, _val, msg in violations:
            print(f"  - {rel}:{lineno}: {msg}", file=sys.stderr)
        return 1

    print("[PASS] Model-neutral naming clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
