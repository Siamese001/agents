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
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.audit_mock_reachability import _PRODUCTION_ROOTS, audit_production_file

PRODUCTION_PACKAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("agents", ("agents",)),
    ("outreach_engine", ("outreach_engine/src",)),
    ("resume_engine", ("resume_engine",)),
    ("resume_graph_engine", ("resume_graph_engine/src", "resume_graph_engine/tools")),
    ("apps_research", ("apps_research",)),
    ("apps_eval", ("apps_eval",)),
    ("apps_model_telemetry", ("apps_model_telemetry",)),
    ("infrastructure", ("infrastructure",)),
    ("ops_scripts", ("ops_scripts",)),
    ("scripts", ("scripts",)),
    ("tools", ("tools",)),
)
TEST_ROOTS: tuple[str, ...] = (
    "tests",
    "resume_graph_engine/tests",
    "outreach_engine/tests",
    "apps_eval/tests",
    "scripts/local_llm",
    "resume_graph_engine/src/apps_rg/evals",
)
PYTEST_INI_PATHS: tuple[str, ...] = (
    "pytest.ini",
    "outreach_engine/pytest.ini",
    "resume_graph_engine/pytest.ini",
)
PROTECTED_TEST_ROOTS: frozenset[str] = frozenset(
    {"tests", "outreach_engine/tests", "resume_graph_engine/tests", "apps_eval/tests", "scripts/local_llm"}
)
MAX_QUARANTINED_IGNORES: int = 2
MIN_SYMBOL_COVERAGE_RATIO: float = 0.65
MIN_MODULE_COVERAGE_RATIO: float = 0.90
MIN_SYMBOLS_FOR_RATIO_GATE: int = 10

REQUIRED_GITHOOKS: tuple[str, ...] = (
    "pre-commit",
    "pre-merge-commit",
    "pre-push",
    "post-merge",
)


def _is_pytest_fixture(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn_node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name) and target.id == "fixture":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "fixture":
            return True
    return False


def _node_has_direct_assertion(fn_node: ast.AST) -> bool:
    assertion_call_prefixes = ("assert", "_assert", "require_", "_check_")
    assertion_call_exact = {"raises", "warns", "fail", "deprecated_call", "check_schema"}
    for sub in ast.walk(fn_node):
        if isinstance(sub, ast.Assert):
            return True
        if isinstance(sub, ast.Raise) and sub.exc is not None:
            return True
        if isinstance(sub, ast.Call):
            fn = sub.func
            name = ""
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name in assertion_call_exact or name.startswith(assertion_call_prefixes):
                return True
    return False


def _test_fn_has_assertion(
    fn_node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    module_fns: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    class_methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    is_method: bool,
    depth: int = 0,
) -> bool:
    if _node_has_direct_assertion(fn_node):
        return True
    if depth >= 3:
        return False
    for sub in ast.walk(fn_node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        if isinstance(fn, ast.Name) and fn.id in module_fns:
            target = module_fns[fn.id]
            if target is not fn_node and _test_fn_has_assertion(
                target,
                module_fns=module_fns,
                class_methods=class_methods,
                is_method=False,
                depth=depth + 1,
            ):
                return True
        elif (
            is_method
            and isinstance(fn, ast.Attribute)
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "self"
            and fn.attr in class_methods
        ):
            target_m = class_methods[fn.attr]
            if target_m is not fn_node and _test_fn_has_assertion(
                target_m,
                module_fns=module_fns,
                class_methods=class_methods,
                is_method=True,
                depth=depth + 1,
            ):
                return True
    return False


def _inspect_decorators_and_calls_for_skip_xfail(
    tree: ast.Module,
    rel_path: str,
) -> tuple[list[str], list[str]]:
    unreasoned_skips: list[str] = []
    non_strict_xfails: list[str] = []

    def _is_mark_attr(expr: ast.AST, attr_name: str) -> bool:
        return (
            isinstance(expr, ast.Attribute)
            and expr.attr == attr_name
            and isinstance(expr.value, ast.Attribute)
            and expr.value.attr == "mark"
        )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                if _is_mark_attr(dec, "skip"):
                    unreasoned_skips.append(f"{rel_path}:{dec.lineno}: bare @pytest.mark.skip without reason=")
                elif _is_mark_attr(dec, "xfail"):
                    non_strict_xfails.append(f"{rel_path}:{dec.lineno}: bare @pytest.mark.xfail without strict=True")
        if isinstance(node, ast.Call):
            if _is_mark_attr(node.func, "skip") or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "skip"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "pytest"
            ):
                has_pos = bool(node.args) and not (
                    isinstance(node.args[0], ast.Constant) and not str(node.args[0].value or "").strip()
                )
                has_kw = any(
                    kw.arg == "reason"
                    and not (isinstance(kw.value, ast.Constant) and not str(kw.value.value or "").strip())
                    for kw in node.keywords
                )
                if not (has_pos or has_kw):
                    unreasoned_skips.append(f"{rel_path}:{node.lineno}: skip missing non-empty reason=")
            elif _is_mark_attr(node.func, "xfail"):
                has_strict = any(
                    kw.arg == "strict" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in node.keywords
                )
                if not has_strict:
                    non_strict_xfails.append(f"{rel_path}:{node.lineno}: mark.xfail missing strict=True")
    return unreasoned_skips, non_strict_xfails


def _audit_pytest_inis_and_src_layout(root: Path) -> tuple[list[str], list[str], list[str]]:
    issues: list[str] = []
    quarantined_ignores: list[str] = []
    misplaced_src_tests: list[str] = []

    for ini_rel in PYTEST_INI_PATHS:
        ini_path = root / ini_rel
        if not ini_path.is_file():
            continue
        txt = ini_path.read_text(encoding="utf-8")
        if "--timeout=" not in txt:
            issues.append(f"{ini_rel}: missing mandatory --timeout= in addopts")
        for match in re.finditer(r"--ignore=([^\s]+)", txt):
            target = match.group(1).strip().rstrip("/")
            quarantined_ignores.append(f"{ini_rel}:{target}")
            if target in PROTECTED_TEST_ROOTS:
                issues.append(f"{ini_rel}: forbidden --ignore={target} disabling primary test root")

    if len(quarantined_ignores) > MAX_QUARANTINED_IGNORES:
        issues.append(
            f"Quarantined --ignore= count {len(quarantined_ignores)} exceeds ratchet ceiling {MAX_QUARANTINED_IGNORES}"
        )

    for src_rel in ("outreach_engine/src", "resume_graph_engine/src"):
        sdir = root / src_rel
        if not sdir.is_dir():
            continue
        for py in sorted({*sdir.rglob("test_*.py"), *sdir.rglob("*_test.py")}):
            if "__pycache__" in py.parts:
                continue
            rel_parts = py.relative_to(root).parts
            if "tests" not in rel_parts:
                rel_str = str(py.relative_to(root))
                misplaced_src_tests.append(rel_str)
                issues.append(f"{rel_str}: misplaced test module inside production src/ outside tests/ directory")

    return issues, quarantined_ignores, misplaced_src_tests


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

            module_fns = {
                n.name: n
                for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    if _is_pytest_fixture(node):
                        continue
                    if not _test_fn_has_assertion(
                        node, module_fns=module_fns, class_methods={}, is_method=False
                    ):
                        zero_assertion_tests.append({"file": rel, "line": node.lineno, "test": node.name})
                elif isinstance(node, ast.ClassDef):
                    methods = {
                        m.name: m
                        for m in node.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                    }
                    for m in methods.values():
                        if m.name.startswith("test_") and not _is_pytest_fixture(m):
                            if not _test_fn_has_assertion(
                                m, module_fns=module_fns, class_methods=methods, is_method=True
                            ):
                                zero_assertion_tests.append(
                                    {"file": rel, "line": m.lineno, "test": f"{node.name}.{m.name}"}
                                )

    package_coverage: dict[str, dict[str, Any]] = {}
    uncovered_packages: list[str] = []
    under_covered_packages: list[str] = []
    for pkg_name, rel_dirs in PRODUCTION_PACKAGES:
        existing_dirs = [root / rd for rd in rel_dirs if (root / rd).is_dir()]
        if not existing_dirs:
            continue
        total_pub = 0
        covered_pub = 0
        total_mods = 0
        covered_mods = 0
        uncovered_mod_paths: list[str] = []
        for pdir in existing_dirs:
            for py in sorted(pdir.rglob("*.py")):
                if "tests" in py.parts or "__pycache__" in py.parts or py.name.startswith("test_"):
                    continue
                try:
                    ptree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
                except SyntaxError:
                    continue
                pubs = [
                    n.name
                    for n in ptree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and not n.name.startswith("_")
                ]
                if not pubs:
                    continue
                total_mods += 1
                mod_cov = sum(1 for sym in pubs if sym in referenced_symbols)
                total_pub += len(pubs)
                covered_pub += mod_cov
                if mod_cov > 0 or py.stem in referenced_symbols:
                    covered_mods += 1
                else:
                    uncovered_mod_paths.append(str(py.relative_to(root)))

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
            under_covered_packages.append(
                f"{pkg_name}(sym={sym_ratio:.2%}, mod={mod_ratio:.2%})"
            )

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


if __name__ == "__main__":
    sys.exit(main())
