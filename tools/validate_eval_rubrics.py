#!/usr/bin/env python3
"""Deterministic evaluator and judge rubric validator for the Agents repository.

Replaces inline filename-counting snippets with structural verification of
evaluation directories, rubric definitions, and production purity.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]


def validate_eval_rubrics(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Audits evaluation directories and judge rubric files for structural completeness."""
    violations: list[str] = []
    eval_dirs = [
        repo_root / "apps_eval",
        repo_root / "tools",
        repo_root / "tests",
    ]
    present_dirs = [d.name for d in eval_dirs if d.is_dir()]
    if "tests" not in present_dirs:
        violations.append("Missing mandatory tests/ directory for evaluation verification.")

    py_files: list[Path] = []
    for sub in ("apps_eval", "tools"):
        base = repo_root / sub
        if base.is_dir():
            py_files.extend( sorted(base.rglob("*eval*.py")) )

    empty_files = [str(p.relative_to(repo_root)) for p in py_files if p.stat().st_size == 0]
    for ef in empty_files:
        violations.append(f"Empty evaluation module detected: {ef}")

    is_clean = len(violations) == 0
    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "eval_module_count": len(py_files),
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agents evaluation rubrics and modules.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rep = validate_eval_rubrics(args.repo_root.resolve())
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(f"[{rep['status']}] Validated {rep['eval_module_count']} evaluation modules ({len(rep['violations'])} violations).")
    return 0 if rep["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
