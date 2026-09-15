#!/usr/bin/env python3
"""Deterministic model-neutral naming and path linter.

Governance Rules:
1. Production code must not contain hardcoded proprietary model IDs
   (e.g., 'gpt-4', 'claude-3-5-sonnet', 'gemini-1.5-pro', 'gpt-5.6-luna')
   outside of canonical configuration SSOT and catalog files.
2. File paths and filenames across reports, plans, docs, and production paths
   must not embed LLM model tags, provider names, or reasoning tier tags.
   Model identity belongs exclusively in JSON metadata fields or execution scratchpads.
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

PROHIBITED_TOKEN_PATTERNS = [
    re.compile(r"(?i)\bgpt[0-9_\-a-z]*\b"),
    re.compile(r"(?i)\bastra\b"),
    re.compile(r"(?i)\bluna\b"),
    re.compile(r"(?i)\bterra\b"),
    re.compile(r"(?i)\bsol(?:_medium|_high|-medium|-high)?\b"),
    re.compile(r"(?i)\bclaude[0-9_\-a-z]*\b"),
    re.compile(r"(?i)\bgemini[0-9_\-a-z]*\b"),
    re.compile(r"(?i)\bllama[0-9_\-a-z]*\b"),
    re.compile(r"(?i)\b(?:sonnet|haiku|opus)\b"),
    re.compile(r"\b(?:o1|o3)(?:-[a-z0-9]+)?\b"),
]

EXEMPT_PATH_PATTERNS = [
    re.compile(r"^\.git/"),
    re.compile(r"^\.venv/"),
    re.compile(r"^__pycache__/"),
    re.compile(r"^\.pytest_cache/"),
    re.compile(r"^\.agents/"),
    re.compile(r"^archive/"),
    re.compile(r"^artifacts/"),
    re.compile(r"^docs/archive/"),
    re.compile(r"^tools/run_luna_.*\.py$"),
    re.compile(r"^plans/live-llm-enforcement-wave1-b7d14e\.md$"),
    re.compile(r"(?:^|/)tests/"),
    re.compile(r"^scratch/"),
    re.compile(r"^resume_graph_engine/src/apps_rg/runtime/judges/bullet_pool_claude_selector\.py$"),
]

GUARDIAN_PATTERN = re.compile(
    r"#\s*(?:guardian|ssot):\s*allow-(?:model-literal|model-id|model)\s*--\s*(.+)",
    re.IGNORECASE,
)


def is_path_exempt(rel_path: str) -> bool:
    """Check if the given relative path is exempt from model-naming constraints."""
    normalized = rel_path.replace("\\", "/")
    for pattern in EXEMPT_PATH_PATTERNS:
        if pattern.search(normalized):
            return True
    return False


def check_path_model_neutrality(
    path: Path,
    repo_root: Path,
) -> list[str]:
    """Scan a file path and its filename for forbidden model naming tokens."""
    try:
        rel = str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        rel = str(path).replace("\\", "/")

    if is_path_exempt(rel):
        return []

    tokens = [t for t in re.split(r"[/\\._\-]+", rel) if t]
    violations: list[str] = []

    for pattern in PROHIBITED_TOKEN_PATTERNS:
        for token in tokens:
            if pattern.fullmatch(token) or pattern.search(token):
                violations.append(
                    f"Path '{rel}' contains prohibited model identifier '{token}' matching '{pattern.pattern}'."
                )
                break

    return violations


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
    """Scan a Python file for hardcoded model literals and filename branding."""
    if not file_path.exists() or not is_production_file(file_path, repo_root):
        return []

    # Check if this is a bootstrap/catalog file
    if any(file_path.name == b or file_path.name.endswith(b) for b in CANONICAL_MODEL_CATALOG_FILES):
        return []

    violations: list[tuple[int, str, str]] = []

    # 1. Check path naming for production files
    path_issues = check_path_model_neutrality(file_path, repo_root)
    for issue in path_issues:
        violations.append((1, file_path.name, issue))

    # Check if this is a bootstrap/catalog file
    if any(file_path.name == b or file_path.name.endswith(b) for b in CANONICAL_MODEL_CATALOG_FILES):
        return violations

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()

    try:
        tree = ast.parse("\n".join(lines), filename=str(file_path))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.strip()
            if MODEL_PATTERN.match(val):
                line_idx = node.lineno - 1
                line_str = lines[line_idx] if line_idx < len(lines) else ""
                guardian_match = GUARDIAN_PATTERN.search(line_str)
                if not guardian_match:
                    violations.append((
                        node.lineno,
                        val,
                        f"Hardcoded model literal '{val}' found. Model IDs must be resolved via model_capabilities/env_bootstrap.",
                    ))

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
        v = check_file_model_neutrality(f, repo_root)
        for lineno, val, msg in v:
            rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
            violations.append((rel, lineno, val, msg))

    if violations:
        print(f"[FAIL] Model-neutral naming violations found ({len(violations)} violations):", file=sys.stderr)
        for rel, lineno, val, msg in violations:
            print(f"  - {rel}:{lineno}: {msg}", file=sys.stderr)
        return 1

    print("[PASS] Model-neutral naming clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
