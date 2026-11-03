#!/usr/bin/env python3
"""Agents Repository — 6-Pillar Testing Gaps, Assertion Strength & Mock Reachability Auditor.

Implements the deterministic, fail-closed Stage IV-B (`Order 7/7`) auditor for
`automations/prompts/agents_testing_gaps_assurance_agent.md`:
1. Pillar 1: Public entrypoint AST inventory & test-reference cross-check across 8 packages.
2. Pillar 2: Cross-subsystem handoff contract test verification (`apps_research` -> `outreach_engine` / `apps_rg`).
3. Pillar 3: Constitutional `pytest.mark.skip(reason=...)` and `pytest.mark.xfail(strict=True)` AST enforcement.
4. Pillar 4: Sync & async zero-assertion `test_*` function detector across all 4 test roots.
5. Pillar 5: Production mock reachability enforcement (`tools/audit_mock_reachability.py`).
6. Pillar 6: Pytest `--timeout=` configuration & `.githooks/` executable permission enforcement.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.audit_mock_reachability import audit_production_file, _PRODUCTION_ROOTS

PRODUCTION_PACKAGES: tuple[tuple[str, str], ...] = (
    ("agents", "agents"),
    ("outreach_engine", "outreach_engine/src"),
    ("resume_engine", "resume_engine"),
    ("resume_graph_engine", "resume_graph_engine/src"),
    ("apps_research", "apps_research"),
    ("apps_eval", "apps_eval"),
    ("apps_model_telemetry", "apps_model_telemetry"),
    ("infrastructure", "infrastructure"),
)
TEST_ROOTS: tuple[str, ...] = (
    "tests",
    "resume_graph_engine/tests",
    "outreach_engine/tests",
    "apps_eval/tests",
)
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
    assertion_call_prefixes = ("assert", "_assert", "validate", "require_", "_check_")
    assertion_call_exact = {"raises", "warns", "fail", "deprecated_call", "check_schema"}
    for sub in ast.walk(fn_node):
        if isinstance(sub, (ast.Assert, ast.Raise)):
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


def run_testing_gaps_audit(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Execute the 6-pillar testing gaps, assertion strength, skip/xfail, and mock reachability audit."""
    root = repo_root.resolve()
    referenced_symbols: set[str] = set()
    zero_assertion_tests: list[dict[str, Any]] = []
    unreasoned_skips: list[str] = []
    non_strict_xfails: list[str] = []
    syntax_errors: list[str] = []
    sleep_violations: list[str] = []
    handoff_test_files: list[str] = []
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

            if any(
                tok in src
                for tok in ("apps_rg_handoff", "managed_research_delegation", "GovernedBriefingResolver", "research_packet")
            ) and py.name != "conftest.py":
                handoff_test_files.append(rel)

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

    package_coverage: dict[str, dict[str, int]] = {}
    uncovered_packages: list[str] = []
    for pkg_name, rel_dir in PRODUCTION_PACKAGES:
        pdir = root / rel_dir
        if not pdir.is_dir():
            continue
        total_pub = 0
        covered_pub = 0
        for py in sorted(pdir.rglob("*.py")):
            if "tests" in py.parts or "__pycache__" in py.parts:
                continue
            try:
                ptree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for n in ptree.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not n.name.startswith("_"):
                    total_pub += 1
                    if n.name in referenced_symbols:
                        covered_pub += 1
        package_coverage[pkg_name] = {"public_symbols": total_pub, "referenced_in_tests": covered_pub}
        if total_pub > 0 and covered_pub == 0:
            uncovered_packages.append(pkg_name)

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

    pytest_ini = root / "pytest.ini"
    if pytest_ini.is_file() and "--timeout=" not in pytest_ini.read_text(encoding="utf-8"):
        hook_issues.append("pytest.ini: missing mandatory --timeout= in addopts")

    needs_handoff_tests = (root / "apps_research").is_dir() and (
        (root / "outreach_engine").is_dir() or (root / "resume_graph_engine").is_dir()
    )
    pillar_2_ok = (len(handoff_test_files) > 0) if needs_handoff_tests else True

    pillar_status = {
        "pillar_1_public_entrypoint_coverage": "PASS" if not uncovered_packages else "FAIL",
        "pillar_2_cross_subsystem_handoff_tests": "PASS" if pillar_2_ok else "FAIL",
        "pillar_3_skip_xfail_hygiene": "PASS" if (not unreasoned_skips and not non_strict_xfails) else "FAIL",
        "pillar_4_sync_async_assertion_strength": "PASS"
        if (not zero_assertion_tests and not syntax_errors)
        else "FAIL",
        "pillar_5_mock_reachability": "PASS" if not mock_violations else "FAIL",
        "pillar_6_hooks_and_pytest_governance": "PASS" if (not hook_issues and not sleep_violations) else "FAIL",
    }
    is_clean = all(v == "PASS" for v in pillar_status.values())
    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "repo_root": str(root),
        "pillar_status": pillar_status,
        "test_root_file_counts": root_counts,
        "total_test_files_scanned": sum(root_counts.values()),
        "package_coverage": package_coverage,
        "uncovered_packages": uncovered_packages,
        "handoff_contract_test_count": len(handoff_test_files),
        "zero_assertion_tests": zero_assertion_tests,
        "unreasoned_skips": unreasoned_skips,
        "non_strict_xfails": non_strict_xfails,
        "mock_reachability_violations": mock_violations,
        "hook_and_pytest_issues": hook_issues + sleep_violations + syntax_errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 6-pillar testing gaps and assertion strength audit.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rep = run_testing_gaps_audit(args.repo_root.resolve())
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
