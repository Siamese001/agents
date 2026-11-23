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

# Ensure repo root is on sys.path and shared .venv packages are available in worktrees
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.pr_governance_core.common import bootstrap_shared_venv

bootstrap_shared_venv(_REPO_ROOT)

# Import sub-linters directly for high performance
from tools.lint_layer_imports import check_file_layer_imports
from tools.lint_model_neutral_naming import check_file_model_neutrality
from tools.lint_production_purity import check_file_production_purity
from tools.lint_contract_schemas import validate_file_against_schema
from tools.lint_secrets import SCANNABLE_TEXT_EXTENSIONS, check_file_for_secrets
from tools.lint_architecture_boundaries import check_layer_boundaries, run_architecture_linter
from tools.lint_model_pins import audit_model_pins
from tools.check_config_ssot_drift import analyze_drift
from tools.lint_prompt_validator_vocab_symmetry import audit_prompt_validator_vocab_symmetry
from tools.lint_apps_rg_domain_literals import audit_apps_rg_domain_literals
from tools.lint_no_jd_overfitting import scan_files as scan_no_jd_overfitting
from tools.change_lane_classifier import classify_paths as classify_change_paths
from tools.audit_mock_reachability import _MockReachabilityVisitor, _PRODUCTION_ROOTS
from tools._testing_gaps_helpers import (
    _inspect_decorators_and_calls_for_skip_xfail,
    _is_pytest_fixture,
    _test_fn_has_assertion,
)

# Model literal baseline for ratcheting legacy violations
_BASELINE_PATH = _REPO_ROOT / "artifacts" / "governance" / "model_literal_baseline.json"
_MODEL_BASELINE_COUNTS: dict[str, int] = {}
if _BASELINE_PATH.is_file():
    try:
        import json as _json

        _bdata = _json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        _MODEL_BASELINE_COUNTS = _bdata.get("file_counts", {})
    except (OSError, ValueError, TypeError):
        pass


def _resolve_model_baseline_bucket(rel: str) -> tuple[str, int]:
    """Map relative path to (bucket_key, ceiling), aggregating split <stem>/ and <stem>_pkg/ submodules."""
    norm = rel.replace("\\", "/")
    if norm in _MODEL_BASELINE_COUNTS:
        return f"owner:{norm}", _MODEL_BASELINE_COUNTS[norm]
    for owner_file, ceiling in sorted(_MODEL_BASELINE_COUNTS.items()):
        norm_owner = owner_file.replace("\\", "/")
        if norm_owner.endswith(".py") and (
            norm.startswith(f"{norm_owner[:-3]}/") or norm.startswith(f"{norm_owner[:-3]}_pkg/")
        ):
            return f"owner:{norm_owner}", ceiling
    return f"file:{norm}", 0


def _resolve_model_baseline_count(rel: str) -> int:
    """Resolve model literal baseline count, allowing submodules split from a ratcheted parent file."""
    return _resolve_model_baseline_bucket(rel)[1]


def _check_ratcheted_model_buckets(py_files: Sequence[Path], repo_root: Path) -> list[str]:
    """Enforce aggregate model-literal baseline ceilings across parent + split-package submodules."""
    if not _MODEL_BASELINE_COUNTS:
        return []
    touched_owners: dict[str, int] = {}
    for f in py_files:
        try:
            rel = f.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = str(f).replace("\\", "/")
        bucket_key, ceiling = _resolve_model_baseline_bucket(rel)
        if bucket_key.startswith("owner:") and ceiling > 0:
            touched_owners[bucket_key[6:]] = ceiling
    if not touched_owners:
        return []

    errs: list[str] = []
    for norm_owner, ceiling in sorted(touched_owners.items()):
        candidates: list[Path] = []
        owner_path = repo_root / norm_owner
        if owner_path.is_file():
            candidates.append(owner_path)
        if norm_owner.endswith(".py"):
            for pkg_dir in (repo_root / norm_owner[:-3], repo_root / f"{norm_owner[:-3]}_pkg"):
                if pkg_dir.is_dir():
                    candidates.extend(sorted(pkg_dir.rglob("*.py")))
        seen: set[Path] = set()
        bucket_hits: list[tuple[str, int, str]] = []
        for cand in candidates:
            resolved = cand.resolve()
            if resolved in seen or not cand.is_file():
                continue
            seen.add(resolved)
            cand_rel = resolved.relative_to(repo_root.resolve()).as_posix()
            for lineno, _val, msg in check_file_model_neutrality(cand, repo_root):
                bucket_hits.append((cand_rel, lineno, msg))
        bucket_hits.sort(key=lambda item: (item[0], item[1]))
        if len(bucket_hits) > ceiling:
            for cand_rel, lineno, msg in bucket_hits[ceiling:]:
                errs.append(
                    f"[Model Neutrality] {cand_rel}:{lineno}: {msg} "
                    f"(split-package bucket '{norm_owner}' total {len(bucket_hits)} exceeds baseline of {ceiling})"
                )
    return errs


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
    except (OSError, subprocess.SubprocessError):
        return []


import os
from concurrent.futures import ThreadPoolExecutor

EXEMPT_DIR_NAMES: set[str] = {
    ".venv",
    ".git",
    ".worktrees",
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
            elif suffix in SCANNABLE_TEXT_EXTENSIONS:
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

    # 4. Layer imports (shared AST)
    v_layers = check_file_layer_imports(f, repo_root, tree=tree, lines=lines)
    for lineno, mod, msg in v_layers:
        gov_errs.append(f"[Layer Import] {rel}:{lineno}: {msg}")

    # 5. Model neutrality (shared AST)
    v_models = check_file_model_neutrality(f, repo_root, tree=tree, lines=lines)
    base_count = _resolve_model_baseline_count(rel)
    if len(v_models) > base_count:
        excess = len(v_models) - base_count
        for lineno, val, msg in v_models[:excess]:
            gov_errs.append(f"[Model Neutrality] {rel}:{lineno}: {msg} (exceeds baseline of {base_count})")

    # 6. Production purity & mock reachability (shared AST)
    v_purity = check_file_production_purity(f, repo_root, tree=tree, lines=lines)
    for lineno, symbol, msg in v_purity:
        purity_errs.append(f"[Production Purity] {rel}:{lineno} [{symbol}]: {msg}")

    norm_rel = rel.replace("\\", "/")
    top_part = norm_rel.split("/", 1)[0]
    is_test_module = (
        "tests" in f.parts
        or f.name.startswith("test_")
        or f.name.endswith("_test.py")
        or f.name == "conftest.py"
    )
    if top_part in _PRODUCTION_ROOTS and not is_test_module and "docs" not in f.parts:
        mock_visitor = _MockReachabilityVisitor(rel)
        mock_visitor.visit(tree)
        for mv in mock_visitor.violations:
            purity_errs.append(f"[Mock Reachability] {mv}")

    # 7. Fast AST test hygiene on touched pytest modules (skip/xfail & zero-assertion guard)
    if is_test_module and ("tests" in f.parts or "/evals/" in f"/{norm_rel}" or "scripts/local_llm" in norm_rel):
        skips, xfails = _inspect_decorators_and_calls_for_skip_xfail(tree, rel)
        for sv in skips:
            hygiene_errs.append(f"[Test Skip Hygiene] {sv}")
        for xv in xfails:
            hygiene_errs.append(f"[Test Xfail Hygiene] {xv}")
        if f.name != "conftest.py" and (f.name.startswith("test_") or f.name.endswith("_test.py")):
            mod_fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_") and not _is_pytest_fixture(node):
                    if not _test_fn_has_assertion(node, module_fns=mod_fns, class_methods={}, is_method=False):
                        hygiene_errs.append(f"[Zero-Assertion Test] {rel}:{node.lineno}: {node.name} has zero assertions")
                elif isinstance(node, ast.ClassDef):
                    cls_methods = {m.name: m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
                    for m in cls_methods.values():
                        if m.name.startswith("test_") and not _is_pytest_fixture(m):
                            if not _test_fn_has_assertion(m, module_fns=mod_fns, class_methods=cls_methods, is_method=True):
                                hygiene_errs.append(
                                    f"[Zero-Assertion Test] {rel}:{m.lineno}: {node.name}.{m.name} has zero assertions"
                                )

    return hygiene_errs, gov_errs, purity_errs


def check_standard_code_hygiene(files: Sequence[Path], repo_root: Path) -> tuple[bool, list[str]]:
    """Category 1: Fast deterministic syntax & compilation checks."""
    errors: list[str] = []
    py_files = [f for f in files if f.suffix == ".py"]
    for f in py_files:
        h_errs, _, _ = _analyze_single_python_file(f, repo_root)
        errors.extend(h_errs)
    return len(errors) == 0, errors


def _files_touch_repo_wide_governance(files: Sequence[Path] | None, repo_root: Path) -> bool:
    if files is None:
        return True
    triggers = ("config/", "data/", "judges/", "tools/", ".agents/", "agents/orchestration/services/")
    exact = {"pyproject.toml", "pytest.ini", ".mcp.json"}
    for f in files:
        try:
            rel = f.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = str(f).replace("\\", "/")
        if rel in exact or any(rel.startswith(p) or f"/{p}" in f"/{rel}" for p in triggers):
            return True
    return False


def _run_extended_architectural_checks(
    files: Sequence[Path] | None,
    repo_root: Path,
    mode_name: str = "all",
    shard_fast: bool = False,
) -> list[str]:
    """Run architectural boundary, layer boundary, and model pin integrity checks."""
    errs: list[str] = []
    if mode_name == "unit-test-explicit":
        return errs
    if shard_fast and not _files_touch_repo_wide_governance(files, repo_root):
        return errs

    arch_res = run_architecture_linter(repo_root)
    if not arch_res.get("is_clean", True):
        for check_name, data in arch_res.get("checks", {}).items():
            for v in data.get("violations", []):
                errs.append(f"[Arch Boundary:{check_name}] {v}")

    services_dir = repo_root / "agents" / "orchestration" / "services"
    if services_dir.is_dir():
        for v in check_layer_boundaries(services_dir):
            errs.append(f"[Layer Boundary] {v}")

    for finding in audit_model_pins(repo_root):
        errs.append(
            f"[Model Pin:{finding.get('category', 'VIOLATION')}] "
            f"{finding.get('file', '')} :: {finding.get('key', '')} — {finding.get('message', '')}"
        )

    return errs


def _run_ssot_drift_checks(
    files: Sequence[Path] | None,
    repo_root: Path,
    mode_name: str = "all",
    shard_fast: bool = False,
) -> list[str]:
    """Run strict configuration and data SSOT drift checks."""
    errs: list[str] = []
    if mode_name == "unit-test-explicit":
        return errs
    if shard_fast and not _files_touch_repo_wide_governance(files, repo_root):
        return errs
    if not (repo_root / "config").is_dir() or not (repo_root / "resume_graph_engine" / "config").is_dir():
        return errs

    report = analyze_drift(repo_root)
    cfg_items = report.get("unallowlisted_differing") or report.get("unallowlisted_drift_files") or []
    for item in cfg_items:
        if isinstance(item, dict):
            errs.append(f"[Config SSOT Drift] {item.get('relative_path')}: {item.get('status')}")
        else:
            errs.append(f"[Config SSOT Drift] {item}: UNALLOWLISTED")
    data_items = report.get("data_differing") or report.get("data_drift_files") or []
    for item in data_items:
        if isinstance(item, dict):
            errs.append(f"[Data SSOT Drift] {item.get('relative_path')}: {item.get('status')}")
        else:
            errs.append(f"[Data SSOT Drift] data/{item}: UNALLOWLISTED")

    errs.extend(audit_prompt_validator_vocab_symmetry(repo_root))
    errs.extend(audit_apps_rg_domain_literals(repo_root))
    return errs


def check_architectural_governance(files: Sequence[Path] | None, repo_root: Path) -> tuple[bool, list[str]]:
    """Category 2: Architectural Governance (Budgets, Layer Imports, Model Neutrality, Boundaries, Model Pins)."""
    errors: list[str] = []
    if files is not None:
        target_py = [f for f in files if f.suffix == ".py"]
    else:
        target_py, _, _ = _collect_repository_files(repo_root)

    for f in target_py:
        _, g_errs, _ = _analyze_single_python_file(f, repo_root)
        errors.extend(g_errs)
    for b_err in _check_ratcheted_model_buckets(target_py, repo_root):
        if b_err not in errors:
            errors.append(b_err)
    errors.extend(_run_extended_architectural_checks(files, repo_root))
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
    ov_report = scan_no_jd_overfitting(target_py, repo_root, use_baseline=True)
    for v in ov_report.get("violations", []):
        errors.append(f"[Anti-Overfitting] {v['file']}:{v['line']}: {v['message']}")
    return len(errors) == 0, errors


def check_contract_schemas(files: Sequence[Path] | None, repo_root: Path) -> tuple[bool, list[str]]:
    """Category 4: Contract / Schema Validation & SSOT Drift."""
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

    errors.extend(_run_ssot_drift_checks(files, repo_root))
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
    shard_fast: bool = False,
) -> tuple[int, dict[str, tuple[bool, list[str]]]]:
    """Execute all five categories and report individual statuses with parallel acceleration."""
    results: dict[str, tuple[bool, list[str]]] = {}

    print("=" * 72)
    print(f"  PRE-COMMIT QUALITY GATE (Tier 1) — Mode: {mode_name}")
    print("  Invariant: Is this change structurally legal?")
    if target_files:
        try:
            lane_report = classify_change_paths([str(f) for f in target_files], repo_root=repo_root)
            print(f"  Risk Classification: {lane_report['lane_name']} (Lane {lane_report['effective_lane']})")
            for adv in lane_report.get("advisories", []):
                print(f"    [ADVISORY:{adv['code']}] {adv['message']}")
        except (OSError, ValueError, KeyError):
            pass
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

    for b_err in _check_ratcheted_model_buckets(py_files, repo_root):
        if b_err not in err_a:
            err_a.append(b_err)
    err_a.extend(_run_extended_architectural_checks(target_files, repo_root, mode_name=mode_name, shard_fast=shard_fast))

    ov_report = scan_no_jd_overfitting(py_files, repo_root, use_baseline=True)
    for v in ov_report.get("violations", []):
        err_p.append(f"[Anti-Overfitting] {v['file']}:{v['line']}: {v['message']}")

    results["1. Standard Code Hygiene"] = (len(err_h) == 0, err_h)
    results["2. Architectural Governance"] = (len(err_a) == 0, err_a)
    results["3. Production Purity"] = (len(err_p) == 0, err_p)

    # 3. Contract / Schema Validation & SSOT Drift
    err_c: list[str] = []
    for f in schema_files:
        ok, msg = validate_file_against_schema(f, repo_root)
        if not ok:
            try:
                rel = str(f.relative_to(repo_root))
            except ValueError:
                rel = str(f)
            err_c.append(f"[Schema/Contract] {rel}: {msg}")
    err_c.extend(_run_ssot_drift_checks(target_files, repo_root, mode_name=mode_name, shard_fast=shard_fast))
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
    parser.add_argument("--shard-fast", action="store_true", help="Fast per-shard verification on target files")
    parser.add_argument("--repo-root", default=".", help="Root of repository")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    if args.files:
        files = [Path(f) if Path(f).is_absolute() else repo_root / f for f in args.files]
        code, _ = run_precommit_gate(files, repo_root, mode_name=f"explicit ({len(files)} files)", shard_fast=args.shard_fast)
    elif args.all:
        code, _ = run_precommit_gate(None, repo_root, mode_name="all repository files")
    else:
        staged = get_staged_files(repo_root)
        if staged:
            code, _ = run_precommit_gate(staged, repo_root, mode_name=f"staged ({len(staged)} files)", shard_fast=args.shard_fast)
        else:
            code, _ = run_precommit_gate(None, repo_root, mode_name="all repository files (no staged files)")

    return code


if __name__ == "__main__":
    sys.exit(main())
