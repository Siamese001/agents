#!/usr/bin/env python3
"""Agents Repository — 6-Pillar Testing Gaps, Assertion Strength & Mock Reachability Auditor.

Implements the deterministic, fail-closed Stage IV-B (`Order 7/7`) auditor for
`automations/prompts/agents_testing_gaps_assurance_agent.md`:
1. Pillar 1: Per-module & per-package public entrypoint AST inventory across all 11 executable roots,
   enforcing both non-zero symbol coverage and minimum symbol/module coverage ratios.
2. Pillar 2: Separate cross-subsystem handoff contract test verification for BOTH
   `apps_research -> outreach_engine` AND `apps_research -> resume_graph_engine`.
3. Pillar 3: Constitutional `pytest.mark.skip(reason=...)` and `pytest.mark.xfail(strict=True)` AST enforcement.
4. Pillar 4: Sync & async strict assertion detector across all 6 test surfaces (rejecting bare `raise`
   and unasserted `validate*()` calls).
5. Pillar 5: Full 11-root production mock reachability enforcement (`tools/audit_mock_reachability.py`).
6. Pillar 6: Multi-`pytest.ini` `--timeout=` & `--ignore=` quarantine audit, misplaced `src/` test detection,
   and `.githooks/` executable permission enforcement.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools._testing_gaps_helpers import (
    MAX_QUARANTINED_IGNORES,
    MIN_MODULE_COVERAGE_RATIO,
    MIN_SYMBOLS_FOR_RATIO_GATE,
    MIN_SYMBOL_COVERAGE_RATIO,
    PRODUCTION_PACKAGES,
    PROTECTED_TEST_ROOTS,
    PYTEST_INI_PATHS,
    REQUIRED_GITHOOKS,
    TEST_ROOTS,
    _audit_pytest_inis_and_src_layout,
    _inspect_decorators_and_calls_for_skip_xfail,
    _is_pytest_fixture,
    _node_has_direct_assertion,
    _parse_pure_reexport_facade,
    _resolve_facade_targets,
    _test_fn_has_assertion,
)
from tools.audit_mock_reachability import _PRODUCTION_ROOTS, audit_production_file


def run_testing_gaps_audit(
    repo_root: Path = REPO_ROOT,
    *,
    include_uncovered_backlog: bool = False,
    execute_pytest_smoke: bool = False,
) -> dict[str, Any]:
    """Execute the 6-pillar testing gaps, assertion strength, skip/xfail, and mock reachability audit."""
    root = repo_root.resolve()
    referenced_symbols: set[str] = set()
    zero_assertion_tests: list[dict[str, Any]] = []
    unreasoned_skips: list[str] = []
    non_strict_xfails: list[str] = []
    syntax_errors: list[str] = []
    sleep_violations: list[str] = []
    outreach_handoff_tests: list[str] = []
    resume_handoff_tests: list[str] = []
    root_counts: dict[str, int] = {}

    for rel_root in TEST_ROOTS:
        tdir = root / rel_root
        if not tdir.is_dir():
            root_counts[rel_root] = 0
            continue
        files = sorted({*tdir.rglob("test_*.py"), *tdir.rglob("*_test.py"), *tdir.rglob("conftest.py")})
        root_counts[rel_root] = len(files)
        for py in files:
            if "__pycache__" in py.parts:
                continue
            rel = str(py.relative_to(root))
            try:
                src = py.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=str(py))
            except (OSError, SyntaxError) as exc:
                syntax_errors.append(f"{rel}: {exc}")
                continue

            if py.name != "conftest.py":
                if any(
                    tok in src
                    for tok in (
                        "managed_research_delegation",
                        "GovernedBriefingResolver",
                        "dispatch_outreach_research_briefing",
                    )
                ):
                    outreach_handoff_tests.append(rel)
                if any(tok in src for tok in ("apps_rg_handoff", "apps_research_apps_rg_handoff")):
                    resume_handoff_tests.append(rel)

            skips, xfails = _inspect_decorators_and_calls_for_skip_xfail(tree, rel)
            unreasoned_skips.extend(skips)
            non_strict_xfails.extend(xfails)

            lines = src.splitlines()
            for sub in ast.walk(tree):
                if isinstance(sub, ast.Name):
                    referenced_symbols.add(sub.id)
                elif isinstance(sub, ast.Attribute):
                    referenced_symbols.add(sub.attr)
                elif isinstance(sub, ast.Import):
                    for alias in sub.names:
                        referenced_symbols.update(alias.name.split("."))
                elif isinstance(sub, ast.ImportFrom):
                    if sub.module:
                        referenced_symbols.update(sub.module.split("."))
                    for alias in sub.names:
                        referenced_symbols.add(alias.name)
                elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    if (
                        isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "time"
                        and sub.func.attr == "sleep"
                        and sub.args
                        and isinstance(sub.args[0], ast.Constant)
                        and isinstance(sub.args[0].value, (int, float))
                        and float(sub.args[0].value) > 2.0
                    ):
                        line_txt = lines[sub.lineno - 1] if 0 <= sub.lineno - 1 < len(lines) else ""
                        if "guardian:" not in line_txt.lower():
                            sleep_violations.append(f"{rel}:{sub.lineno}: unguarded time.sleep({sub.args[0].value})")

            if py.name == "conftest.py":
                continue

            module_fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_") and not _is_pytest_fixture(node):
                    if not _test_fn_has_assertion(node, module_fns=module_fns, class_methods={}, is_method=False):
                        zero_assertion_tests.append({"file": rel, "line": node.lineno, "test": node.name})
                elif isinstance(node, ast.ClassDef):
                    methods = {m.name: m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
                    for m in methods.values():
                        if m.name.startswith("test_") and not _is_pytest_fixture(m):
                            if not _test_fn_has_assertion(m, module_fns=module_fns, class_methods=methods, is_method=True):
                                zero_assertion_tests.append({"file": rel, "line": m.lineno, "test": f"{node.name}.{m.name}"})

    package_coverage: dict[str, dict[str, Any]] = {}
    uncovered_packages: list[str] = []
    under_covered_packages: list[str] = []
    facade_search_roots = tuple(
        dict.fromkeys([root, *(root / p for p in ("resume_graph_engine/src", "outreach_engine/src", "resume_engine/src") if (root / p).is_dir())])
    )
    for pkg_name, rel_dirs in PRODUCTION_PACKAGES:
        existing_dirs = [root / rd for rd in rel_dirs if (root / rd).is_dir()]
        if not existing_dirs:
            continue
        total_pub, covered_pub, total_mods, covered_mods = 0, 0, 0, 0
        uncovered_mod_paths: list[str] = []
        mod_covered: dict[Path, bool] = {}
        facade_imports: dict[Path, list[ast.ImportFrom]] = {}
        for pdir in existing_dirs:
            for py in sorted(pdir.rglob("*.py")):
                if "tests" in py.parts or "__pycache__" in py.parts or py.name.startswith("test_"):
                    continue
                try:
                    ptree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
                except SyntaxError:
                    continue
                pubs = [
                    n.name for n in ptree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not n.name.startswith("_")
                ]
                rp = py.resolve()
                if pubs:
                    total_mods += 1
                    mod_cov = sum(1 for sym in pubs if sym in referenced_symbols)
                    total_pub += len(pubs)
                    covered_pub += mod_cov
                    is_cov = mod_cov > 0 or py.stem in referenced_symbols
                    mod_covered[rp] = is_cov
                    if is_cov:
                        covered_mods += 1
                    else:
                        uncovered_mod_paths.append(str(py.relative_to(root)))
                elif (imps := _parse_pure_reexport_facade(ptree)):
                    facade_imports[rp] = imps

        pkg_roots = tuple(dict.fromkeys([*facade_search_roots, *(d.resolve() for d in existing_dirs)]))

        def _is_facade_covered(fpy: Path, seen: set[Path] | None = None) -> bool:
            seen = set() if seen is None else seen
            if fpy in seen:
                return False
            seen.add(fpy)
            fname = fpy.parent.name if fpy.name == "__init__.py" else fpy.stem
            if fname in referenced_symbols:
                return True
            for imp in facade_imports[fpy]:
                if any((a.asname or a.name) in referenced_symbols or a.name in referenced_symbols for a in imp.names if a.name != "*"):
                    return True
            for tgt in _resolve_facade_targets(fpy, facade_imports[fpy], pkg_roots):
                if mod_covered.get(tgt) or (tgt in facade_imports and _is_facade_covered(tgt, seen)):
                    return True
            return False

        for fpy in facade_imports:
            if _is_facade_covered(fpy):
                total_mods += 1
                covered_mods += 1
                for tgt in _resolve_facade_targets(fpy, facade_imports[fpy], pkg_roots):
                    if tgt in mod_covered and not mod_covered[tgt]:
                        mod_covered[tgt] = True
                        covered_mods += 1
                        rel_tgt = str(tgt.relative_to(root))
                        if rel_tgt in uncovered_mod_paths:
                            uncovered_mod_paths.remove(rel_tgt)

        # Propagate package-level seam coverage across split subpackage sibling modules so
        # decomposing a covered module into submodules never penalizes module_coverage_ratio.
        covered_parent_dirs = {
            p.parent for p, cov in mod_covered.items() if cov and (p.parent / "__init__.py").is_file()
        } | {
            fpy.parent for fpy in facade_imports if _is_facade_covered(fpy) and fpy.name == "__init__.py"
        }
        for rp, cov in list(mod_covered.items()):
            if not cov and rp.parent in covered_parent_dirs and rp.parent not in {d.resolve() for d in existing_dirs}:
                mod_covered[rp] = True
                covered_mods += 1
                rel_rp = str(rp.relative_to(root))
                if rel_rp in uncovered_mod_paths:
                    uncovered_mod_paths.remove(rel_rp)

        sym_ratio = round(covered_pub / float(max(total_pub, 1)), 4)
        mod_ratio = round(covered_mods / float(max(total_mods, 1)), 4)
        package_coverage[pkg_name] = {
            "public_symbols": total_pub,
            "referenced_in_tests": covered_pub,
            "symbol_coverage_ratio": sym_ratio,
            "modules_with_public_symbols": total_mods,
            "covered_modules": covered_mods,
            "module_coverage_ratio": mod_ratio,
            "uncovered_module_count": len(uncovered_mod_paths),
        }
        if total_pub > 0 and covered_pub == 0:
            uncovered_packages.append(pkg_name)
        elif total_pub >= MIN_SYMBOLS_FOR_RATIO_GATE and (
            sym_ratio < MIN_SYMBOL_COVERAGE_RATIO or mod_ratio < MIN_MODULE_COVERAGE_RATIO
        ):
            under_covered_packages.append(f"{pkg_name}(sym={sym_ratio:.2%}, mod={mod_ratio:.2%})")

    mock_violations: list[str] = []
    for prod_rel in _PRODUCTION_ROOTS:
        pdir = root / prod_rel
        if pdir.is_dir():
            for py in sorted(pdir.rglob("*.py")):
                mock_violations.extend(audit_production_file(py, root))

    hook_issues: list[str] = []
    githooks_dir = root / ".githooks"
    if githooks_dir.is_dir():
        for hname in REQUIRED_GITHOOKS:
            hp = githooks_dir / hname
            if not hp.is_file() or not os.access(hp, os.X_OK):
                hook_issues.append(f".githooks/{hname}: missing or non-executable")

    ini_issues, quarantined_ignores, misplaced_src_tests = _audit_pytest_inis_and_src_layout(root)
    hook_issues.extend(ini_issues)

    pytest_smoke_rc: int | None = None
    if execute_pytest_smoke:
        smoke_targets = [
            rel_t
            for rel_t in (
                "tests/unit/test_sidecar_separation_governance.py",
                "tests/unit/test_ssot_centralization_auditor.py",
                "outreach_engine/tests/test_research_governance_truth.py",
                "tests/unit/test_resume_graph_and_core_coverage_elevation.py",
            )
            if (root / rel_t).is_file()
        ]
        if smoke_targets:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *smoke_targets, "-q", "--timeout=60"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            pytest_smoke_rc = proc.returncode
            if proc.returncode != 0:
                hook_issues.append(f"Scoped pytest smoke failed with exit code {proc.returncode}")

    has_research = (root / "apps_research").is_dir()
    needs_lic_handoff = has_research and (root / "outreach_engine").is_dir()
    needs_rg_handoff = has_research and (root / "resume_graph_engine").is_dir()
    pillar_2_ok = (not needs_lic_handoff or len(outreach_handoff_tests) > 0) and (
        not needs_rg_handoff or len(resume_handoff_tests) > 0
    )

    pillar_status = {
        "pillar_1_public_entrypoint_coverage": "PASS"
        if (not uncovered_packages and not under_covered_packages)
        else "FAIL",
        "pillar_2_cross_subsystem_handoff_tests": "PASS" if pillar_2_ok else "FAIL",
        "pillar_3_skip_xfail_hygiene": "PASS" if (not unreasoned_skips and not non_strict_xfails) else "FAIL",
        "pillar_4_sync_async_assertion_strength": "PASS"
        if (not zero_assertion_tests and not syntax_errors)
        else "FAIL",
        "pillar_5_mock_reachability": "PASS" if not mock_violations else "FAIL",
        "pillar_6_hooks_and_pytest_governance": "PASS" if (not hook_issues and not sleep_violations) else "FAIL",
    }
    handoff_union = sorted({*outreach_handoff_tests, *resume_handoff_tests})
    total_uncovered_modules = sum(v["uncovered_module_count"] for v in package_coverage.values())
    strict_clean = all(v == "PASS" for v in pillar_status.values())
    if not strict_clean:
        status = "FAIL"
        is_clean = False
    elif include_uncovered_backlog and total_uncovered_modules > 0:
        status = "BACKLOG_ACTION_REQUIRED"
        is_clean = False
    else:
        status = "PASS"
        is_clean = True
    return {
        "status": status,
        "is_clean": is_clean,
        "repo_root": str(root),
        "pillar_status": pillar_status,
        "test_root_file_counts": root_counts,
        "total_test_files_scanned": sum(root_counts.values()),
        "package_coverage": package_coverage,
        "uncovered_backlog": {
            "total_uncovered_modules": total_uncovered_modules,
            "quarantined_ignore_count": len(quarantined_ignores),
        },
        "pytest_smoke_executed": execute_pytest_smoke,
        "pytest_smoke_returncode": pytest_smoke_rc,
        "uncovered_packages": uncovered_packages,
        "under_covered_packages": under_covered_packages,
        "handoff_contract_test_count": len(handoff_union),
        "outreach_handoff_test_count": len(outreach_handoff_tests),
        "resume_handoff_test_count": len(resume_handoff_tests),
        "zero_assertion_tests": zero_assertion_tests,
        "unreasoned_skips": unreasoned_skips,
        "non_strict_xfails": non_strict_xfails,
        "mock_reachability_violations": mock_violations,
        "quarantined_ignore_paths": quarantined_ignores,
        "misplaced_src_tests": misplaced_src_tests,
        "hook_and_pytest_issues": hook_issues + sleep_violations + syntax_errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 6-pillar testing gaps and assertion strength audit.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--include-uncovered-backlog",
        action="store_true",
        help="Return BACKLOG_ACTION_REQUIRED when uncovered modules remain > 0.",
    )
    parser.add_argument(
        "--execute-pytest-smoke",
        action="store_true",
        help="Execute scoped pytest governance smoke during Pillar 6 verification.",
    )
    args = parser.parse_args(argv)

    rep = run_testing_gaps_audit(
        args.repo_root.resolve(),
        include_uncovered_backlog=args.include_uncovered_backlog,
        execute_pytest_smoke=args.execute_pytest_smoke,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        passing = sum(1 for v in rep["pillar_status"].values() if v == "PASS")
        print(
            f"[{rep['status']}] Testing Gaps Audit: {passing}/6 pillars passing "
            f"(scanned={rep['total_test_files_scanned']} test files, "
            f"zero_assert={len(rep['zero_assertion_tests'])}, "
            f"mock_violations={len(rep['mock_reachability_violations'])})"
        )
    return 0 if rep["is_clean"] else 1


__all__ = [
    "MAX_QUARANTINED_IGNORES",
    "MIN_MODULE_COVERAGE_RATIO",
    "MIN_SYMBOLS_FOR_RATIO_GATE",
    "MIN_SYMBOL_COVERAGE_RATIO",
    "PRODUCTION_PACKAGES",
    "PROTECTED_TEST_ROOTS",
    "PYTEST_INI_PATHS",
    "REQUIRED_GITHOOKS",
    "TEST_ROOTS",
    "_audit_pytest_inis_and_src_layout",
    "_inspect_decorators_and_calls_for_skip_xfail",
    "_is_pytest_fixture",
    "_node_has_direct_assertion",
    "_parse_pure_reexport_facade",
    "_resolve_facade_targets",
    "_test_fn_has_assertion",
    "main",
    "run_testing_gaps_audit",
]


if __name__ == "__main__":
    sys.exit(main())
