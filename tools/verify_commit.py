#!/usr/bin/env python3
"""Canonical Tier 1 Pre-Commit Gate: Is this change structurally legal?

Orchestrates the five mandatory pre-commit categories:
1. Standard Code Hygiene (syntax & static compile checks)
2. Architectural Governance (file budgets with closed script loopholes, layer imports, model neutrality)
3. Production Purity (no predetermined domain answers or golden/fixture imports in production paths)
4. Contract / Schema Validation (declarative configurations, manifests, and JSON schemas)
5. Secrets / Credential Protection (deterministic secrets and credentials scan)
"""

from __future__ import annotations

import argparse
import ast
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Sequence

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import sub-linters directly for high performance
from tools.lint_file_budgets import check_file_budget, scan_all_production_files
from tools.lint_layer_imports import check_file_layer_imports
from tools.lint_model_neutral_naming import check_file_model_neutrality
from tools.lint_production_purity import check_file_production_purity
from tools.lint_contract_schemas import validate_file_against_schema
from tools.lint_secrets import check_file_for_secrets


def get_staged_files(repo_root: Path) -> list[Path]:
    """Retrieve list of staged files from git."""
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        files = [repo_root / f.strip() for f in res.stdout.splitlines() if f.strip()]
        return [f for f in files if f.exists()]
    except Exception:
        return []


import os
from concurrent.futures import ThreadPoolExecutor

EXEMPT_DIR_NAMES: set[str] = {
    ".venv",
    ".git",
    "artifacts",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def _collect_repository_files(repo_root: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """Single-pass filesystem traversal with directory pruning."""
    py_files: list[Path] = []
    schema_files: list[Path] = []
    secret_files: list[Path] = []

    for root, dirs, files in os.walk(repo_root):
        rel_root = os.path.relpath(root, repo_root).replace("\\", "/")
        if rel_root == "docs/archive" or rel_root.startswith("docs/archive/"):
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in EXEMPT_DIR_NAMES and not (rel_root == "docs" and d == "archive")]
        for f in files:
            full_p = Path(root) / f
            suffix = full_p.suffix.lower()
            if suffix == ".py":
                py_files.append(full_p)
                secret_files.append(full_p)
            elif suffix in (".json", ".yaml", ".yml"):
                secret_files.append(full_p)
                if "config" in full_p.parts:
                    schema_files.append(full_p)
            elif suffix == ".sh":
                secret_files.append(full_p)

    return py_files, schema_files, secret_files


def _analyze_single_python_file(
    f: Path,
    repo_root: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Single-pass analysis of one Python file for hygiene, governance, and purity."""
    hygiene_errs: list[str] = []
    gov_errs: list[str] = []
    purity_errs: list[str] = []

    try:
        rel = str(f.relative_to(repo_root))
    except ValueError:
        rel = str(f)

    if ".venv" in rel or ".git" in rel or "docs/archive" in rel:
        return hygiene_errs, gov_errs, purity_errs

    # 1. Read file content once
    try:
        content = f.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
    except Exception as e:
        hygiene_errs.append(f"{rel}: Read error: {e}")
        return hygiene_errs, gov_errs, purity_errs

    # 2. Syntax compilation check (in-memory, zero disk write overhead)
    try:
        compile(content, str(f), "exec")
    except SyntaxError as se:
        hygiene_errs.append(f"{rel}:{se.lineno}: Syntax compilation error: {se.msg}")
        return hygiene_errs, gov_errs, purity_errs
    except Exception as e:
        hygiene_errs.append(f"{rel}: Compilation error: {e}")
        return hygiene_errs, gov_errs, purity_errs

    # 3. Parse AST once for all downstream linters
    try:
        tree = ast.parse(content, filename=str(f))
    except SyntaxError as se:
        hygiene_errs.append(f"{rel}:{se.lineno}: AST syntax error: {se.msg}")
        return hygiene_errs, gov_errs, purity_errs

    # 3. File budgets
    ok_b, _, msg_b = check_file_budget(f, repo_root)
    if not ok_b:
        gov_errs.append(f"[File Budget] {msg_b}")

    # 4. Layer imports (shared AST)
    v_layers = check_file_layer_imports(f, repo_root, tree=tree, lines=lines)
    for lineno, mod, msg in v_layers:
        gov_errs.append(f"[Layer Import] {rel}:{lineno}: {msg}")

    # 5. Model neutrality (shared AST)
    v_models = check_file_model_neutrality(f, repo_root, tree=tree, lines=lines)
    for lineno, val, msg in v_models:
        gov_errs.append(f"[Model Neutrality] {rel}:{lineno}: {msg}")

    # 6. Production purity (shared AST)
    v_purity = check_file_production_purity(f, repo_root, tree=tree, lines=lines)
    for lineno, symbol, msg in v_purity:
        purity_errs.append(f"[Production Purity] {rel}:{lineno} [{symbol}]: {msg}")

    return hygiene_errs, gov_errs, purity_errs


def check_standard_code_hygiene(files: Sequence[Path], repo_root: Path) -> tuple[bool, list[str]]:
    """Category 1: Fast deterministic syntax & compilation checks."""
    errors: list[str] = []
    py_files = [f for f in files if f.suffix == ".py"]
    for f in py_files:
        h_errs, _, _ = _analyze_single_python_file(f, repo_root)
        errors.extend(h_errs)
    return len(errors) == 0, errors


def check_architectural_governance(files: Sequence[Path] | None, repo_root: Path) -> tuple[bool, list[str]]:
    """Category 2: Architectural Governance (Budgets, Layer Imports, Model Neutrality)."""
    errors: list[str] = []
    if files is not None:
        target_py = [f for f in files if f.suffix == ".py"]
    else:
        target_py, _, _ = _collect_repository_files(repo_root)

    for f in target_py:
        _, g_errs, _ = _analyze_single_python_file(f, repo_root)
        errors.extend(g_errs)
    return len(errors) == 0, errors


def check_production_purity(files: Sequence[Path] | None, repo_root: Path) -> tuple[bool, list[str]]:
    """Category 3: Production Purity & Fixture Isolation."""
    errors: list[str] = []
    if files is not None:
        target_py = [f for f in files if f.suffix == ".py"]
    else:
        target_py, _, _ = _collect_repository_files(repo_root)

    for f in target_py:
        _, _, p_errs = _analyze_single_python_file(f, repo_root)
        errors.extend(p_errs)
    return len(errors) == 0, errors


def check_contract_schemas(files: Sequence[Path] | None, repo_root: Path) -> tuple[bool, list[str]]:
    """Category 4: Contract / Schema Validation."""
    errors = []
    if files is not None:
        decl_files = [f for f in files if f.suffix.lower() in (".json", ".yaml", ".yml")]
    else:
        decl_files = list((repo_root / "config").rglob("*.json")) + list((repo_root / "config").rglob("*.yaml"))

    for f in decl_files:
        ok, msg = validate_file_against_schema(f, repo_root)
        if not ok:
            rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
            errors.append(f"[Schema/Contract] {rel}: {msg}")

    return len(errors) == 0, errors


def check_secrets_protection(files: Sequence[Path] | None, repo_root: Path) -> tuple[bool, list[str]]:
    """Category 5: Secrets / Credential Protection."""
    errors = []
    if files is not None:
        files_to_check = files
    else:
        _, _, files_to_check = _collect_repository_files(repo_root)

    for f in files_to_check:
        if f.is_file():
            v_secrets = check_file_for_secrets(f, repo_root)
            for lineno, stype, msg in v_secrets:
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                errors.append(f"[Secret] {rel}:{lineno}: {msg}")
    return len(errors) == 0, errors


def run_precommit_gate(
    target_files: list[Path] | None,
    repo_root: Path,
    mode_name: str = "staged",
) -> tuple[int, dict[str, tuple[bool, list[str]]]]:
    """Execute all five categories and report individual statuses with parallel acceleration."""
    results: dict[str, tuple[bool, list[str]]] = {}

    print("=" * 72)
    print(f"  PRE-COMMIT QUALITY GATE (Tier 1) — Mode: {mode_name}")
    print("  Invariant: Is this change structurally legal?")
    print("=" * 72)

    # 1. File collection
    if target_files is not None:
        py_files = [f for f in target_files if f.suffix == ".py"]
        schema_files = [f for f in target_files if f.suffix.lower() in (".json", ".yaml", ".yml")]
        secret_files = list(target_files)
    else:
        py_files, schema_files, secret_files = _collect_repository_files(repo_root)

    # 2. Parallel single-pass Python analysis (Hygiene + Governance + Purity)
    max_workers = min(8, os.cpu_count() or 4)
    err_h: list[str] = []
    err_a: list[str] = []
    err_p: list[str] = []

    def _worker(f: Path) -> tuple[list[str], list[str], list[str]]:
        return _analyze_single_python_file(f, repo_root)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        py_results = executor.map(_worker, py_files)
        for h, g, p in py_results:
            err_h.extend(h)
            err_a.extend(g)
            err_p.extend(p)

    results["1. Standard Code Hygiene"] = (len(err_h) == 0, err_h)
    results["2. Architectural Governance"] = (len(err_a) == 0, err_a)
    results["3. Production Purity"] = (len(err_p) == 0, err_p)

    # 3. Contract / Schema Validation
    err_c: list[str] = []
    for f in schema_files:
        ok, msg = validate_file_against_schema(f, repo_root)
        if not ok:
            try:
                rel = str(f.relative_to(repo_root))
            except ValueError:
                rel = str(f)
            err_c.append(f"[Schema/Contract] {rel}: {msg}")
    results["4. Contract / Schema Validation"] = (len(err_c) == 0, err_c)

    # 4. Secrets / Credential Protection (Parallel)
    err_s: list[str] = []
    def scan_secret(f: Path) -> list[str]:
        if not f.is_file():
            return []
        v_sec = check_file_for_secrets(f, repo_root)
        try:
            rel = str(f.relative_to(repo_root))
        except ValueError:
            rel = str(f)
        return [f"[Secret] {rel}:{lineno}: {msg}" for lineno, stype, msg in v_sec]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        sec_results = executor.map(scan_secret, secret_files)
        for res in sec_results:
            err_s.extend(res)
    results["5. Secrets / Credential Protection"] = (len(err_s) == 0, err_s)

    all_passed = True
    print("\nPre-Commit Gate Summary:")
    for category, (passed, errs) in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {category:<38} {status}")
        if not passed:
            all_passed = False
            for e in errs[:5]:
                print(f"      * {e}")
            if len(errs) > 5:
                print(f"      * ... and {len(errs) - 5} more issues")

    print("-" * 72)
    if all_passed:
        print("  RESULT: PRE-COMMIT QUALITY GATE PASSED (Change is structurally legal)")
        print("=" * 72 + "\n")
        return 0, results
    else:
        print("  RESULT: PRE-COMMIT QUALITY GATE FAILED (Structural violations found)", file=sys.stderr)
        print("=" * 72 + "\n", file=sys.stderr)
        return 1, results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic Tier 1 Pre-Commit Quality Gate.")
    parser.add_argument("--files", nargs="*", help="Specific files to check")
    parser.add_argument("--all", action="store_true", help="Scan full repository")
    parser.add_argument("--staged", action="store_true", help="Scan only git staged files (pre-commit default)")
    parser.add_argument("--repo-root", default=".", help="Root of repository")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    if args.files:
        files = [Path(f) if Path(f).is_absolute() else repo_root / f for f in args.files]
        code, _ = run_precommit_gate(files, repo_root, mode_name=f"explicit ({len(files)} files)")
    elif args.all:
        code, _ = run_precommit_gate(None, repo_root, mode_name="all repository files")
    else:
        staged = get_staged_files(repo_root)
        if staged:
            code, _ = run_precommit_gate(staged, repo_root, mode_name=f"staged ({len(staged)} files)")
        else:
            code, _ = run_precommit_gate(None, repo_root, mode_name="all repository files (no staged files)")

    return code


if __name__ == "__main__":
    sys.exit(main())
