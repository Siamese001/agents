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


def check_standard_code_hygiene(files: Sequence[Path], repo_root: Path) -> tuple[bool, list[str]]:
    """Category 1: Fast deterministic syntax & compilation checks."""
    errors = []
    py_files = [f for f in files if f.suffix == ".py"]
    for f in py_files:
        rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
        # Skip gitignored / venv / docs/archive
        if ".venv" in rel or ".git" in rel or "docs/archive" in rel:
            continue
        # 1. Compile test
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{rel}: Syntax compilation error: {e}")
            continue

        # 2. AST parsing test
        try:
            ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
        except SyntaxError as se:
            errors.append(f"{rel}:{se.lineno}: AST syntax error: {se.msg}")

    return len(errors) == 0, errors


def check_architectural_governance(files: Sequence[Path] | None, repo_root: Path) -> tuple[bool, list[str]]:
    """Category 2: Architectural Governance (Budgets, Layer Imports, Model Neutrality)."""
    errors = []

    # A. File budgets
    if files is not None:
        for f in files:
            if f.suffix == ".py":
                ok, lines, msg = check_file_budget(f, repo_root)
                if not ok:
                    errors.append(f"[File Budget] {msg}")
    else:
        v_budgets = scan_all_production_files(repo_root)
        for path, lines, msg in v_budgets:
            errors.append(f"[File Budget] {msg}")

    # B. Layer imports
    files_to_check = files if files is not None else [p for p in repo_root.rglob("*.py") if ".venv" not in p.parts and ".git" not in p.parts]
    for f in files_to_check:
        if f.suffix == ".py":
            v_layers = check_file_layer_imports(f, repo_root)
            for lineno, mod, msg in v_layers:
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                errors.append(f"[Layer Import] {rel}:{lineno}: {msg}")

    # C. Model neutral naming
    for f in files_to_check:
        if f.suffix == ".py":
            v_models = check_file_model_neutrality(f, repo_root)
            for lineno, val, msg in v_models:
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                errors.append(f"[Model Neutrality] {rel}:{lineno}: {msg}")

    return len(errors) == 0, errors


def check_production_purity(files: Sequence[Path] | None, repo_root: Path) -> tuple[bool, list[str]]:
    """Category 3: Production Purity & Fixture Isolation."""
    errors = []
    files_to_check = files if files is not None else [p for p in repo_root.rglob("*.py") if ".venv" not in p.parts and ".git" not in p.parts]
    for f in files_to_check:
        if f.suffix == ".py":
            v_purity = check_file_production_purity(f, repo_root)
            for lineno, symbol, msg in v_purity:
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                errors.append(f"[Production Purity] {rel}:{lineno} [{symbol}]: {msg}")
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
        files_to_check = []
        for ext in ("*.py", "*.json", "*.yaml", "*.yml", "*.sh"):
            for f in repo_root.rglob(ext):
                if ".venv" not in f.parts and ".git" not in f.parts and "artifacts" not in f.parts:
                    files_to_check.append(f)

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
    """Execute all five categories and report individual statuses."""
    results: dict[str, tuple[bool, list[str]]] = {}

    print("=" * 72)
    print(f"  PRE-COMMIT QUALITY GATE (Tier 1) — Mode: {mode_name}")
    print("  Invariant: Is this change structurally legal?")
    print("=" * 72)

    # 1. Standard Code Hygiene
    hygiene_files = target_files if target_files is not None else [p for p in repo_root.rglob("*.py") if ".venv" not in p.parts and ".git" not in p.parts]
    ok_h, err_h = check_standard_code_hygiene(hygiene_files, repo_root)
    results["1. Standard Code Hygiene"] = (ok_h, err_h)

    # 2. Architectural Governance
    ok_a, err_a = check_architectural_governance(target_files, repo_root)
    results["2. Architectural Governance"] = (ok_a, err_a)

    # 3. Production Purity
    ok_p, err_p = check_production_purity(target_files, repo_root)
    results["3. Production Purity"] = (ok_p, err_p)

    # 4. Contract / Schema Validation
    ok_c, err_c = check_contract_schemas(target_files, repo_root)
    results["4. Contract / Schema Validation"] = (ok_c, err_c)

    # 5. Secrets / Credential Protection
    ok_s, err_s = check_secrets_protection(target_files, repo_root)
    results["5. Secrets / Credential Protection"] = (ok_s, err_s)

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
