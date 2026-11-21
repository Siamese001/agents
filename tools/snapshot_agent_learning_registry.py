#!/usr/bin/env python3
"""AST-verified learning instrumentation coverage snapshot for `agents` runtime exit seams."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps_eval.contracts.schemas import utc_now_iso

LEARNING_INSTRUMENTATION_SYMBOLS: frozenset[str] = frozenset(
    {
        "emit_post_run_trace_safe",
        "RunTraceCollector",
        "EvalFlywheelEngine",
        "FeedbackLearningStore",
        "HITLDecisionStore",
        "TrajectoryLearningEngine",
    }
)

WATCHED_RUNTIME_SEAMS: tuple[str, ...] = (
    "tools/hook_dispatch.py",
    "agents/cli.py",
    "agents/orchestration/services/pipeline_coordinator.py",
    "resume_engine/cli.py",
    "outreach_engine/src/apps_lic/runtime/whole_run_exit.py",
    "apps_research/integrations/governed_research_run.py",
)


def scan_module_learning_hooks(file_path: Path) -> list[str]:
    """Return sorted learning instrumentation symbols referenced via AST in file_path."""
    if not file_path.is_file():
        return []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, SyntaxError):
        return []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in LEARNING_INSTRUMENTATION_SYMBOLS:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in LEARNING_INSTRUMENTATION_SYMBOLS:
            found.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in LEARNING_INSTRUMENTATION_SYMBOLS:
                    found.add(alias.name)
    return sorted(found)


def build_learning_registry_snapshot(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    seam_rows: list[dict[str, Any]] = []
    instrumented = 0
    for rel in WATCHED_RUNTIME_SEAMS:
        hooks = scan_module_learning_hooks(root / rel)
        is_inst = len(hooks) > 0
        if is_inst:
            instrumented += 1
        seam_rows.append(
            {
                "seam_path": rel,
                "instrumented": is_inst,
                "symbols": hooks,
            }
        )
    return {
        "schema_version": "agents.learning_role_registry.v1",
        "generated_at_utc": utc_now_iso(),
        "watched_seams_count": len(WATCHED_RUNTIME_SEAMS),
        "instrumented_seams_count": instrumented,
        "coverage_ratio": round(instrumented / max(1, len(WATCHED_RUNTIME_SEAMS)), 4),
        "seams": seam_rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot AST-verified learning instrumentation coverage.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--out",
        default="reports/agent_learning_role_registry_baseline.json",
        help="Optional output JSON path (omit --write to print only).",
    )
    parser.add_argument("--write", action="store_true", help="Write snapshot JSON to --out.")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    snap = build_learning_registry_snapshot(root)
    if args.write:
        out_path = (root / args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snap, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(snap, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
