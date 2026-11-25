#!/usr/bin/env python3
"""AST-based Eval Construct Validity & Zero-Tautology Auditor (INV-EVALS-CONSTRUCT-VALIDITY-GATE).

Enforces three fail-closed construct-validity invariants:
1. FORBIDDEN_MOCK_IN_SMOKE_HARNESS: Smoke harnesses and unmocked eval shields must never
   import or invoke unittest.mock, MagicMock, patch, or monkeypatch.
2. VACUOUS_EVALUATE_STUB: Evaluator/check functions must not return hardcoded passing
   constants without inspecting inputs.
3. CLAMPED_REGRESSION_DELTA: Judge/evaluator modules must not clamp failing scores upward
   to a passing threshold (e.g. max(score, 4.7) / max(raw_score, threshold)).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_MOCK_MODULES: frozenset[str] = frozenset({"unittest.mock", "mock"})
FORBIDDEN_MOCK_NAMES: frozenset[str] = frozenset(
    {"MagicMock", "AsyncMock", "Mock", "patch", "monkeypatch"}
)

DEFAULT_SMOKE_HARNESS_PATHS: tuple[str, ...] = (
    "tools/run_diff_scoped_eval_shield.py",
    "tools/eval_shield_core/domain_eval_checks.py",
    "ops_scripts/ci/check_eval_harness_promotion_evidence.py",
)

DEFAULT_EVALUATOR_GLOBS: tuple[str, ...] = (
    "tools/eval_shield_core/*.py",
    "tools/run_diff_scoped_eval_shield.py",
    "apps_eval/graders/trajectory.py",
    "apps_eval/graders/judge/*.py",
    "apps_eval/online_grader.py",
    "apps_eval/holdout_replay.py",
    "apps_eval/pareto.py",
    "apps_eval/longitudinal.py",
    "resume_graph_engine/src/apps_rg/runtime/judges/executive_summary_judge_packet.py",
    "resume_graph_engine/src/apps_rg/runtime/judges/executive_summary_x1d_dimension_verdicts.py",
)


def _is_docstring_expr(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_hardcoded_pass_return(expr: ast.expr | None) -> bool:
    if expr is None:
        return False
    if isinstance(expr, ast.Constant) and expr.value is True:
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


def scan_file_for_forbidden_mocks(file_path: Path, *, code: str = "FORBIDDEN_MOCK_IN_SMOKE_HARNESS") -> list[dict[str, Any]]:
    """Parse AST of file_path and return violations for any forbidden mock usage."""
    violations: list[dict[str, Any]] = []
    try:
        src = file_path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(file_path))
    except (OSError, SyntaxError) as exc:
        return [{"code": "AST_PARSE_ERROR", "file": str(file_path), "line": 1, "message": str(exc)}]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_MOCK_MODULES or alias.name.startswith("unittest.mock"):
                    violations.append(
                        {
                            "code": code,
                            "file": str(file_path),
                            "line": node.lineno,
                            "message": f"Forbidden mock import '{alias.name}' in unmocked harness.",
                        }
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = str(node.module or "")
            if mod in FORBIDDEN_MOCK_MODULES or mod.startswith("unittest.mock"):
                violations.append(
                    {
                        "code": code,
                        "file": str(file_path),
                        "line": node.lineno,
                        "message": f"Forbidden mock import from '{mod}' in unmocked harness.",
                    }
                )
            for alias in node.names:
                if alias.name in FORBIDDEN_MOCK_NAMES:
                    violations.append(
                        {
                            "code": code,
                            "file": str(file_path),
                            "line": node.lineno,
                            "message": f"Forbidden mock symbol '{alias.name}' imported in unmocked harness.",
                        }
                    )
        elif isinstance(node, ast.FunctionDef):
            for arg in (*node.args.args, *node.args.kwonlyargs):
                if arg.arg == "monkeypatch":
                    violations.append(
                        {
                            "code": code,
                            "file": str(file_path),
                            "line": node.lineno,
                            "message": f"Forbidden 'monkeypatch' fixture parameter in '{node.name}'.",
                        }
                    )
        elif isinstance(node, ast.Call):
            fn = node.func
            fn_name = ""
            if isinstance(fn, ast.Name):
                fn_name = fn.id
            elif isinstance(fn, ast.Attribute):
                fn_name = fn.attr
            if fn_name in FORBIDDEN_MOCK_NAMES:
                violations.append(
                    {
                        "code": code,
                        "file": str(file_path),
                        "line": node.lineno,
                        "message": f"Forbidden mock call '{fn_name}()' in unmocked harness.",
                    }
                )
    return violations


def scan_file_for_vacuous_eval_and_score_clamping(file_path: Path) -> list[dict[str, Any]]:
    """Scan evaluator/judge file for VACUOUS_EVALUATE_STUB and CLAMPED_REGRESSION_DELTA."""
    violations: list[dict[str, Any]] = []
    try:
        src = file_path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(file_path))
    except (OSError, SyntaxError) as exc:
        return [{"code": "AST_PARSE_ERROR", "file": str(file_path), "line": 1, "message": str(exc)}]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name_l = node.name.lower()
            if name_l.startswith(("evaluate", "eval_", "check_", "verify_", "grade_")):
                body = [stmt for stmt in node.body if not _is_docstring_expr(stmt)]
                if len(body) == 1 and isinstance(body[0], ast.Return) and _is_hardcoded_pass_return(body[0].value):
                    violations.append(
                        {
                            "code": "VACUOUS_EVALUATE_STUB",
                            "file": str(file_path),
                            "line": node.lineno,
                            "message": f"Evaluator '{node.name}' returns a hardcoded passing constant without inspecting inputs.",
                        }
                    )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "max":
            if len(node.args) == 2:
                arg0, arg1 = node.args
                arg0_names = {n.id.lower() for n in ast.walk(arg0) if isinstance(n, ast.Name)}
                arg1_names = {n.id.lower() for n in ast.walk(arg1) if isinstance(n, ast.Name)}
                score_hit = any("score" in n for n in arg0_names | arg1_names)
                floor_hit = any(
                    k in n for n in arg0_names | arg1_names for k in ("threshold", "pass_floor", "min_pass")
                ) or any(
                    isinstance(a, ast.Constant) and isinstance(a.value, (int, float)) and 4.0 <= float(a.value) <= 5.0
                    for a in (arg0, arg1)
                )
                if score_hit and floor_hit:
                    violations.append(
                        {
                            "code": "CLAMPED_REGRESSION_DELTA",
                            "file": str(file_path),
                            "line": node.lineno,
                            "message": "Upward score clamping via max(score, threshold/4.x) masks judge regressions.",
                        }
                    )
    return violations


def scan_fact_inventory_graph_presence_ratchet(repo_root: Path) -> tuple[int, int, list[dict[str, Any]]]:
    """Enforce INV-FACT-GRAPH-NO-AGENT-SYNTHESIS ratchet on approved_by_graph_presence entries."""
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from tools.validate_turn_gates import load_policy_registry

    policies = load_policy_registry(repo_root)
    ceiling = int((policies.get("INV-FACT-GRAPH-NO-AGENT-SYNTHESIS") or {}).get("threshold", 0))
    inv_dir = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "fact_inventory"
    total_count = 0
    if inv_dir.is_dir():
        for bundle_path in sorted(inv_dir.glob("*_role_episode_bundles.json")):
            total_count += bundle_path.read_text(encoding="utf-8", errors="ignore").count("approved_by_graph_presence")
    violations: list[dict[str, Any]] = []
    if total_count > ceiling:
        violations.append(
            {
                "code": "AGENT_SYNTHESIZED_GRAPH_PRESENCE_EXCEEDS_RATCHET",
                "file": "resume_graph_engine/src/apps_rg/fact_inventory/*_role_episode_bundles.json",
                "line": 1,
                "message": (
                    f"approved_by_graph_presence count ({total_count}) exceeds INV-FACT-GRAPH-NO-AGENT-SYNTHESIS "
                    f"ratchet ceiling ({ceiling}). Agents must never invent or backfill unverified candidate facts."
                ),
            }
        )
    return total_count, ceiling, violations


def audit_repository(
    repo_root: Path,
    *,
    extra_smoke_files: Sequence[Path] = (),
    extra_eval_files: Sequence[Path] = (),
) -> dict[str, Any]:
    root = repo_root.resolve()
    violations: list[dict[str, Any]] = []
    scanned_smoke: list[str] = []
    scanned_eval: list[str] = []

    smoke_targets: list[Path] = [root / rel for rel in DEFAULT_SMOKE_HARNESS_PATHS]
    smoke_targets.extend(extra_smoke_files)
    for path in smoke_targets:
        if path.is_file():
            rel = path.resolve().relative_to(root).as_posix() if path.resolve().is_relative_to(root) else str(path)
            scanned_smoke.append(rel)
            violations.extend(scan_file_for_forbidden_mocks(path, code="FORBIDDEN_MOCK_IN_SMOKE_HARNESS"))

    eval_targets: list[Path] = []
    for pattern in DEFAULT_EVALUATOR_GLOBS:
        if "*" in pattern:
            eval_targets.extend(sorted(root.glob(pattern)))
        else:
            p = root / pattern
            if p.is_file():
                eval_targets.append(p)
    eval_targets.extend(extra_eval_files)

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from apps_eval.construct_validity import (
        classify_evaluator_grounding_tier,
        scan_extended_construct_validity,
    )

    seen_eval: set[Path] = set()
    grounding_tiers: dict[str, str] = {}
    authoritative_grounded_floors = {
        "tools/eval_shield_core/domain_eval_checks.py": ("LIVE_CORPUS_GROUNDED",),
        "apps_eval/graders/judge/blind_pool_deduplicator.py": ("OFFLINE_BENCHMARK_GROUNDED", "LIVE_CORPUS_GROUNDED"),
    }
    for path in eval_targets:
        resolved = path.resolve()
        if resolved in seen_eval or not path.is_file():
            continue
        seen_eval.add(resolved)
        rel = resolved.relative_to(root).as_posix() if resolved.is_relative_to(root) else str(path)
        scanned_eval.append(rel)
        tier = classify_evaluator_grounding_tier(path)
        grounding_tiers[rel] = tier
        allowed_tiers = authoritative_grounded_floors.get(rel)
        if allowed_tiers and tier not in allowed_tiers:
            violations.append(
                {
                    "code": "GROUNDING_TIER_REGRESSION",
                    "file": rel,
                    "line": 1,
                    "message": f"Authoritative evaluator '{rel}' regressed to grounding tier '{tier}' (expected one of {allowed_tiers}).",
                }
            )
        violations.extend(scan_file_for_vacuous_eval_and_score_clamping(path))
        if rel.startswith("apps_eval/"):
            violations.extend(scan_extended_construct_validity(path))

    gp_count, gp_ceiling, gp_violations = scan_fact_inventory_graph_presence_ratchet(root)
    violations.extend(gp_violations)

    return {
        "schema_version": "agents.eval_construct_validity_audit.v2",
        "status": "PASS" if not violations else "FAIL",
        "scanned_smoke_files": sorted(set(scanned_smoke)),
        "scanned_eval_files": sorted(set(scanned_eval)),
        "grounding_tiers": grounding_tiers,
        "graph_presence_count": gp_count,
        "graph_presence_ceiling": gp_ceiling,
        "violation_count": len(violations),
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit eval construct validity and anti-mock invariants.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--verify-strict", action="store_true", help="Fail closed (exit 1) on any violation.")
    parser.add_argument("--include-e2e-pin", action="store_true", help="Also execute branch-diff unmocked E2E pinning gate.")
    parser.add_argument("--smoke-files", nargs="*", default=(), help="Additional smoke/shield files to scan.")
    parser.add_argument("--eval-files", nargs="*", default=(), help="Additional evaluator files to scan.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    report = audit_repository(
        repo_root,
        extra_smoke_files=[Path(p) for p in args.smoke_files],
        extra_eval_files=[Path(p) for p in args.eval_files],
    )
    if args.include_e2e_pin:
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from tools.audit_multi_ssot_judge_gate_drift import audit_multi_ssot_judge_gate_drift
        from tools.verify_fix_eval_pinning import evaluate_non_mock_e2e_branch_requirement

        pin_report = evaluate_non_mock_e2e_branch_requirement(repo_root)
        report["e2e_pin_report"] = pin_report
        if pin_report.get("violations"):
            report["violations"].extend(pin_report["violations"])
            report["violation_count"] = len(report["violations"])
            report["status"] = "FAIL"

        drift_report = audit_multi_ssot_judge_gate_drift(repo_root)
        report["multi_ssot_judge_drift_report"] = drift_report
        if drift_report.get("violations"):
            for dv in drift_report["violations"]:
                report["violations"].append(
                    {
                        "code": f"MULTI_SSOT_DRIFT_{dv.get('vector', 'UNKNOWN')}",
                        "file": "tools/audit_multi_ssot_judge_gate_drift.py",
                        "line": 1,
                        "message": str(dv.get("message") or ""),
                    }
                )
            report["violation_count"] = len(report["violations"])
            report["status"] = "FAIL"
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[eval-construct-validity] status={report['status']} "
            f"smoke={len(report['scanned_smoke_files'])} eval={len(report['scanned_eval_files'])} "
            f"violations={report['violation_count']}"
        )
        for v in report["violations"]:
            print(f"  - [{v['code']}] {v['file']}:{v['line']}: {v['message']}")
    if args.verify_strict and report["violation_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
