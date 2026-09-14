#!/usr/bin/env python3
"""Deterministic model-neutral naming linter.

Governance Rule:
    Production code must not contain hardcoded proprietary model IDs
    (e.g., 'gpt-4', 'claude-3-5-sonnet', 'gemini-1.5-pro', 'gpt-5.6-luna')
    outside of canonical configuration SSOT and catalog files.
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
    "env_bootstrap.py",
    "model_capabilities.py",
    "model_pin_ownership.py",
    "section_model_limits.py",
    "section_judge_policy.py",
    "credentials.py",
    "core_model_catalog.py",
    "embedding_settings.py",
    "single_run_rca_w2.py",
    "w5_end_to_end_pipeline.py",
    "zero_llm_qualification.py",
    "anthropic_cache_live_probe.py",
    "ExecutiveVoiceRepairAgent.py",
    "CareerThesisAlignmentAgent.py",
    "apps_research_bridge.py",
)

MODEL_PATTERN = re.compile(
    r"^(?:gpt-[456]\.[0-9](?:-[a-z0-9]+)?|claude-[a-z0-9-]+|gemini-[0-9]\.[0-9](?:-[a-z0-9]+)?|o[13](?:-[a-z0-9]+)?)$",
    re.IGNORECASE,
)

GUARDIAN_PATTERN = re.compile(
    r"#\s*(?:guardian|ssot):\s*allow-(?:model-literal|model-id|model)\s*--\s*(.+)",
    re.IGNORECASE,
)


def is_production_file(path: Path, repo_root: Path) -> bool:
    try:
        rel = str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return False

    for exc in EXCLUDED_DIRECTORIES:
        if exc in rel.split("/"):
            return False

    for prod in PRODUCTION_DIRECTORIES:
        if rel == prod or rel.startswith(f"{prod}/"):
            return True

    return False


def check_file_model_neutrality(
    file_path: Path,
    repo_root: Path,
) -> list[tuple[int, str, str]]:
    """Scan a Python file for hardcoded model literals."""
    if not file_path.exists() or not is_production_file(file_path, repo_root):
        return []

    # Check if this is a bootstrap/catalog file
    if any(file_path.name == b or file_path.name.endswith(b) for b in CANONICAL_MODEL_CATALOG_FILES):
        return []

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    violations: list[tuple[int, str, str]] = []

    try:
        tree = ast.parse("\n".join(lines), filename=str(file_path))
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.strip()
            if MODEL_PATTERN.match(val):
                line_no = node.lineno
                line_content = lines[line_no - 1] if 1 <= line_no <= len(lines) else ""
                if GUARDIAN_PATTERN.search(line_content):
                    continue
                violations.append(
                    (
                        line_no,
                        val,
                        f"Hardcoded model literal '{val}' found outside model catalog SSOT.",
                    )
                )

    return violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic model-neutral naming linter.")
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
            v = check_file_model_neutrality(f, repo_root)
            for lineno, val, msg in v:
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                violations.append((rel, lineno, val, msg))

    if violations:
        print(f"[FAIL] Model-neutral naming violations found ({len(violations)} violations):", file=sys.stderr)
        for rel, lineno, val, msg in violations:
            print(f"  - {rel}:{lineno}: {msg}", file=sys.stderr)
        return 1

    print(f"[PASS] Model-neutral naming clean (no hardcoded proprietary model IDs in production modules).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
