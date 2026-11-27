#!/usr/bin/env python3
"""Branch-diff Unmocked E2E Pinning Gate (FORBIDDEN_MOCK_IN_E2E_PIN).

Ensures that:
1. All unmocked E2E test suites under tests/end_to_end/*_e2e.py contain zero
   unittest.mock, MagicMock, patch, or monkeypatch usage.
2. Feature branches modifying production pipeline or governance code include
   regression/E2E test coverage (enforced fail-closed when --require-branch-test is set).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.audit_eval_construct_validity import scan_file_for_forbidden_mocks
from tools.change_lane_classifier import collect_git_changed_paths

PRODUCTION_ROOT_PREFIXES: tuple[str, ...] = (
    "resume_graph_engine/src/",
    "outreach_engine/",
    "apps_research/",
    "agents/",
    "apps_eval/",
    "apps_model_telemetry/",
    "infrastructure/",
    "ops_scripts/",
    "resume_engine/",
    "scripts/",
    "tools/",
)

_HIGH_ASSURANCE_TEST_ROOTS: tuple[str, ...] = (
    "tests",
    "resume_graph_engine/tests",
    "outreach_engine/tests",
    "apps_eval/tests",
)

_CODE_BRANCH_PREFIXES: tuple[str, ...] = (
    "fix/",
    "feat/",
    "chore/",
    "refactor/",
    "perf/",
)


def _current_branch_name(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _head_commit_has_e2e_exempt(repo_root: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%B"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return "e2e-exempt" in proc.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def _discover_high_assurance_e2e_and_live_files(root: Path) -> list[Path]:
    """Discover all unmocked E2E suites across subsystems plus *live_llm* and non-unit *_e2e* suites."""
    seen: set[Path] = set()
    discovered: list[Path] = []
    for rel_root in _HIGH_ASSURANCE_TEST_ROOTS:
        base = root / rel_root
        if not base.is_dir():
            continue
        for py in sorted({*base.rglob("test_*.py"), *base.rglob("*_test.py")}):
            if "__pycache__" in py.parts:
                continue
            rel_low = py.relative_to(root).as_posix().lower()
            fname_low = py.name.lower()
            in_e2e_dir = "/end_to_end/" in f"/{rel_low}"
            is_live_llm = "live_llm" in fname_low
            is_non_unit_e2e = "/unit/" not in f"/{rel_low}" and (
                fname_low.endswith("_e2e.py") or "_e2e_" in fname_low
            )
            if in_e2e_dir or is_live_llm or is_non_unit_e2e:
                rp = py.resolve()
                if rp not in seen:
                    seen.add(rp)
                    discovered.append(py)
    return discovered


def scan_e2e_file_for_forbidden_mocks(file_path: Path) -> list[dict[str, Any]]:
    """Scan a single E2E test file for forbidden mocks (FORBIDDEN_MOCK_IN_E2E_PIN)."""
    return scan_file_for_forbidden_mocks(file_path, code="FORBIDDEN_MOCK_IN_E2E_PIN")


def evaluate_non_mock_e2e_branch_requirement(
    repo_root: Path,
    *,
    changed_paths: Sequence[str] | None = None,
    e2e_files: Sequence[Path] | None = None,
    require_branch_test: bool = False,
    branch_name: str | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    violations: list[dict[str, Any]] = []

    if e2e_files is not None:
        targets = [Path(p) for p in e2e_files]
    else:
        targets = _discover_high_assurance_e2e_and_live_files(root)

    scanned_e2e: list[str] = []
    for path in targets:
        if not path.is_file():
            continue
        rel = path.resolve().relative_to(root).as_posix() if path.resolve().is_relative_to(root) else str(path)
        scanned_e2e.append(rel)
        violations.extend(scan_e2e_file_for_forbidden_mocks(path))

    paths = list(changed_paths) if changed_paths is not None else collect_git_changed_paths(root)[0]
    branch = branch_name if branch_name is not None else _current_branch_name(root)
    low_branch = branch.lower()
    is_code_branch = any(low_branch.startswith(pref) for pref in _CODE_BRANCH_PREFIXES)
    e2e_exempt = changed_paths is None and _head_commit_has_e2e_exempt(root)
    effective_require = bool((require_branch_test or is_code_branch) and not e2e_exempt)

    prod_touched = [
        p for p in paths if any(p.startswith(pref) for pref in PRODUCTION_ROOT_PREFIXES) and "/tests/" not in p
    ]
    tests_touched = [
        p
        for p in paths
        if p.startswith("tests/")
        or "/tests/" in p
        or p.startswith("apps_eval/suites/")
    ]

    branch_test_warning = ""
    if prod_touched and not tests_touched:
        branch_test_warning = (
            f"Branch '{branch or 'HEAD'}' modifies {len(prod_touched)} production file(s) "
            "without adding a pinned regression case (apps_eval/suites/) or test file."
        )
        if effective_require:
            violations.append(
                {
                    "code": "MISSING_BRANCH_REGRESSION_TEST",
                    "file": prod_touched[0],
                    "line": 1,
                    "message": branch_test_warning,
                }
            )

    return {
        "schema_version": "agents.fix_eval_pinning.v2",
        "status": "PASS" if not violations else "FAIL",
        "branch": branch,
        "fail_closed_fix_pinning_active": effective_require,
        "scanned_e2e_files": scanned_e2e,
        "prod_touched_count": len(prod_touched),
        "tests_touched_count": len(tests_touched),
        "branch_test_warning": branch_test_warning,
        "violation_count": len(violations),
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify unmocked E2E pinning invariants.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--e2e-files", nargs="*", default=None, help="Explicit E2E test files to verify.")
    parser.add_argument("--require-branch-test", action="store_true", help="Fail if prod files changed with zero tests.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    report = evaluate_non_mock_e2e_branch_requirement(
        repo_root,
        e2e_files=[Path(p) for p in args.e2e_files] if args.e2e_files is not None else None,
        require_branch_test=args.require_branch_test,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[fix-eval-pinning] status={report['status']} e2e_scanned={len(report['scanned_e2e_files'])} "
            f"violations={report['violation_count']}"
        )
        if report["branch_test_warning"]:
            print(f"  [ADVISORY] {report['branch_test_warning']}")
        for v in report["violations"]:
            print(f"  - [{v['code']}] {v['file']}:{v['line']}: {v['message']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
