"""Extended AST construct-validity scanners and 3-tier substantive grounding classifier.

Detects anti-gaming patterns in evaluator, judge, and test files:
1. CLAMPED_REGRESSION_DELTA (max(0.0, a - b) or max(score, threshold))
2. VACUOUS_ZERO_CASE_PASS (returning True/1.0/PASS on empty inputs)
3. IGNORED_EVAL_PARAM (unused parameters in evaluate_*/grade_*)
4. VACUOUS_EVALUATE_STUB (single-return hardcoded PASS/True)
5. TAUTOLOGICAL_SELF_COMPARE (assert x == x)
6. TAUTOLOGICAL_CONSTANT_COMPARE (assert True / assert 1 == 1)
7. VACUOUS_EXIT_CODE_ASSERTION (assert returncode in [0, 1])
8. SILENT_SCANNER_EXCEPT_PASS (bare except ...: pass without guardian comment)
9. UNWIRED_JUDGE_VACUOUS_PASS (fail-open pass tokens like PASS_WITHOUT_JUDGE)
10. FAKE_JUDGE_SCORE_QUALIFICATION (synthetic model IDs without negative assertion)
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from apps_eval.contracts.schemas import GroundingTier

_IGNORED_PARAM_ALLOWLIST = frozenset({"self", "cls", "sandbox", "timeout_seconds", "_"})
_FAIL_OPEN_JUDGE_TOKENS = frozenset(
    {
        "PASS_WITHOUT_JUDGE",
        "PASS_READY_FOR_JUDGE",
        "PASS_STAGE1_READY_FOR_BLIND_JUDGE",
    }
)
_SYNTHETIC_JUDGE_TOKENS = ("model_family_a", "model_family_b", "fake_model", "stub_model")


def _is_docstring_expr(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_hardcoded_pass_expr(expr: ast.expr | None) -> bool:
    if expr is None:
        return False
    if isinstance(expr, ast.Constant) and (
        expr.value is True or expr.value == 1.0 or str(expr.value).upper() == "PASS"
    ):
        return True
    if isinstance(expr, ast.Dict):
        for k, v in zip(expr.keys, expr.values):
            if (
                isinstance(k, ast.Constant)
                and str(k.value).lower() in {"status", "pass", "passed", "verdict"}
                and isinstance(v, ast.Constant)
                and (v.value is True or str(v.value).upper() == "PASS")
            ):
                if all(isinstance(val, (ast.Constant, ast.List, ast.Dict, ast.Tuple)) for val in expr.values):
                    return True
    return False


def classify_evaluator_grounding_tier(file_path: Path) -> GroundingTier:
    """Classify an evaluator module into LIVE_CORPUS_GROUNDED, OFFLINE_BENCHMARK_GROUNDED, or SYNTHETIC_SANDBOX_SMOKE_ONLY."""
    text = file_path.read_text(encoding="utf-8", errors="ignore").lower()
    if any(tok in text for tok in ("online_eval_ledger", "run_traces.jsonl", "live_adapter", "live_corpus")):
        return "LIVE_CORPUS_GROUNDED"
    if any(tok in text for tok in ("holdout", "cassette", "pinned_fix_regressions", "golden_eval_cases", "benchmark")):
        return "OFFLINE_BENCHMARK_GROUNDED"
    return "SYNTHETIC_SANDBOX_SMOKE_ONLY"


def scan_extended_construct_validity(
    file_path: Path,
    *,
    is_scanner_file: bool = False,
    is_judge_test: bool = False,
) -> list[dict[str, Any]]:
    """Run all extended AST construct-validity checks on a Python file."""
    violations: list[dict[str, Any]] = []
    try:
        src = file_path.read_text(encoding="utf-8")
        lines = src.splitlines()
        tree = ast.parse(src, filename=str(file_path))
    except (OSError, SyntaxError) as exc:
        return [{"code": "AST_PARSE_ERROR", "file": str(file_path), "line": 1, "message": str(exc)}]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name_l = node.name.lower()
            is_eval_fn = name_l.startswith(("evaluate", "eval_", "grade_", "compute_"))
            body = [stmt for stmt in node.body if not _is_docstring_expr(stmt)]

            # 1. VACUOUS_EVALUATE_STUB
            if is_eval_fn and len(body) == 1 and isinstance(body[0], ast.Return) and _is_hardcoded_pass_expr(body[0].value):
                violations.append(
                    {
                        "code": "VACUOUS_EVALUATE_STUB",
                        "file": str(file_path),
                        "line": node.lineno,
                        "message": f"Function '{node.name}' returns hardcoded passing literal.",
                    }
                )

            # 2. IGNORED_EVAL_PARAM
            if name_l.startswith(("evaluate_", "grade_")):
                used_names = {
                    n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                }
                for arg in (*node.args.args, *node.args.kwonlyargs):
                    if arg.arg in _IGNORED_PARAM_ALLOWLIST or arg.arg.startswith("_"):
                        continue
                    if arg.arg not in used_names:
                        violations.append(
                            {
                                "code": "IGNORED_EVAL_PARAM",
                                "file": str(file_path),
                                "line": node.lineno,
                                "message": f"Parameter '{arg.arg}' in '{node.name}' is never referenced.",
                            }
                        )

            # 3. VACUOUS_ZERO_CASE_PASS (if not items: return True / 1.0 / 'PASS')
            if is_eval_fn:
                for stmt in body:
                    if (
                        isinstance(stmt, ast.If)
                        and isinstance(stmt.test, ast.UnaryOp)
                        and isinstance(stmt.test.op, ast.Not)
                        and len(stmt.body) == 1
                        and isinstance(stmt.body[0], ast.Return)
                        and _is_hardcoded_pass_expr(stmt.body[0].value)
                    ):
                        violations.append(
                            {
                                "code": "VACUOUS_ZERO_CASE_PASS",
                                "file": str(file_path),
                                "line": stmt.lineno,
                                "message": f"Function '{node.name}' returns passing value on empty input.",
                            }
                        )

            # 4. CLAMPED_REGRESSION_DELTA: max(0.0, a - b) in regression/delta/diff functions
            if any(tok in name_l for tok in ("regress", "delta", "diff", "evaluate", "judge")):
                for sub in ast.walk(node):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Name)
                        and sub.func.id == "max"
                        and len(sub.args) == 2
                    ):
                        a0, a1 = sub.args
                        is_zero_sub = (
                            isinstance(a0, ast.Constant)
                            and a0.value in (0, 0.0)
                            and isinstance(a1, ast.BinOp)
                            and isinstance(a1.op, ast.Sub)
                            and not (isinstance(a1.left, ast.Constant) and a1.left.value in (1, 1.0))
                        )
                        if is_zero_sub:
                            violations.append(
                                {
                                    "code": "CLAMPED_REGRESSION_DELTA",
                                    "file": str(file_path),
                                    "line": sub.lineno,
                                    "message": "max(0.0, a - b) masks negative regression deltas.",
                                }
                            )

        # 5 & 6. Tautological asserts & vacuous exit code checks
        elif isinstance(node, ast.Assert):
            test = node.test
            if isinstance(test, ast.Constant) and test.value is True:
                violations.append(
                    {
                        "code": "TAUTOLOGICAL_CONSTANT_COMPARE",
                        "file": str(file_path),
                        "line": node.lineno,
                        "message": "Tautological 'assert True' provides zero verification.",
                    }
                )
            elif isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
                op = test.ops[0]
                right = test.comparators[0]
                if isinstance(op, ast.Eq):
                    if ast.dump(test.left) == ast.dump(right):
                        code = (
                            "TAUTOLOGICAL_CONSTANT_COMPARE"
                            if isinstance(test.left, ast.Constant)
                            else "TAUTOLOGICAL_SELF_COMPARE"
                        )
                        violations.append(
                            {
                                "code": code,
                                "file": str(file_path),
                                "line": node.lineno,
                                "message": "Tautological equality assertion comparing expression to itself.",
                            }
                        )
                elif isinstance(op, ast.In) and isinstance(right, (ast.List, ast.Tuple, ast.Set)):
                    left_src = ast.dump(test.left).lower()
                    vals = {c.value for c in right.elts if isinstance(c, ast.Constant)}
                    if ("returncode" in left_src or "exit_code" in left_src) and {0, 1}.issubset(vals):
                        violations.append(
                            {
                                "code": "VACUOUS_EXIT_CODE_ASSERTION",
                                "file": str(file_path),
                                "line": node.lineno,
                                "message": "Exit code assertion accepts both 0 (pass) and 1 (fail).",
                            }
                        )

        # 7. SILENT_SCANNER_EXCEPT_PASS
        elif is_scanner_file and isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                line_txt = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
                if "guardian:" not in line_txt:
                    violations.append(
                        {
                            "code": "SILENT_SCANNER_EXCEPT_PASS",
                            "file": str(file_path),
                            "line": node.lineno,
                            "message": "Silent 'except: pass' in scanner/auditor without guardian justification.",
                        }
                    )

        # 8. UNWIRED_JUDGE_VACUOUS_PASS
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in _FAIL_OPEN_JUDGE_TOKENS and "construct_validity" not in file_path.name:
                violations.append(
                    {
                        "code": "UNWIRED_JUDGE_VACUOUS_PASS",
                        "file": str(file_path),
                        "line": node.lineno,
                        "message": f"Fail-open judge pass token '{node.value}' detected.",
                    }
                )
            if is_judge_test and any(tok == node.value.lower() for tok in _SYNTHETIC_JUDGE_TOKENS):
                if "reject" not in src.lower() and "assert not" not in src.lower():
                    violations.append(
                        {
                            "code": "FAKE_JUDGE_SCORE_QUALIFICATION",
                            "file": str(file_path),
                            "line": node.lineno,
                            "message": f"Synthetic judge model '{node.value}' used without asserting fail-closed rejection.",
                        }
                    )

    return violations
