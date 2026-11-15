"""Helper routines for tools/testing_gaps_auditor.py."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Sequence

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
                target, module_fns=module_fns, class_methods=class_methods, is_method=False, depth=depth + 1
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
                target_m, module_fns=module_fns, class_methods=class_methods, is_method=True, depth=depth + 1
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


def _parse_pure_reexport_facade(tree: ast.Module) -> list[ast.ImportFrom] | None:
    """Return non-future ImportFrom nodes when body holds only docstrings, __all__, Import/ImportFrom, or TYPE_CHECKING."""
    imports: list[ast.ImportFrom] = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.ImportFrom):
            if node.module != "__future__":
                imports.append(node)
            continue
        if isinstance(node, ast.Import):
            continue
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__all__"
        ):
            continue
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "__all__":
            continue
        if (
            isinstance(node, ast.If)
            and not node.orelse
            and (
                (isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING")
                or (isinstance(node.test, ast.Attribute) and node.test.attr == "TYPE_CHECKING")
            )
            and all(isinstance(inner, (ast.Import, ast.ImportFrom, ast.Pass)) for inner in node.body)
        ):
            continue
        return None
    return imports or None


def _resolve_facade_targets(
    facade_py: Path, imports: Sequence[ast.ImportFrom], search_roots: Sequence[Path]
) -> list[Path]:
    """Resolve ImportFrom statements in a pure re-export facade to target module files."""
    targets: list[Path] = []
    for imp in imports:
        if imp.level > 0:
            if imp.level - 1 >= len(facade_py.parents):
                continue
            bases: Sequence[Path] = (facade_py.parents[imp.level - 1],)
        else:
            bases = search_roots
        for base in bases:
            mod_base = base.joinpath(*imp.module.split(".")) if imp.module else base
            if imp.module:
                for cand in (mod_base.with_suffix(".py"), mod_base / "__init__.py"):
                    if cand.is_file():
                        targets.append(cand.resolve())
            for alias in imp.names:
                if alias.name == "*":
                    continue
                sub_base = mod_base / alias.name
                for cand in (sub_base.with_suffix(".py"), sub_base / "__init__.py"):
                    if cand.is_file():
                        targets.append(cand.resolve())
    return targets


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
]
