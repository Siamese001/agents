#!/usr/bin/env python3
"""Authoritative Tier 2 Local Main Readiness Gate: Does the structurally legal system actually work?

Orchestrates deep validation before merging local feature branches into local main:
1. Tier 1 Structural Governance Gate (verify_commit.py --all)
2. Unit & Architectural Boundary Tests
3. Adversarial Purity & Derivation Integrity Suite (Cases A-F)
4. Runtime Pipeline Contracts & Provenance Verification
5. Governed PR Merge Queue & Trunk Lock Suite
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def run_cmd(argv: list[str], cwd: Path, desc: str, timeout: int = 180, dry_run: bool = False) -> tuple[bool, str]:
    """Run subprocess command with bounded execution."""
    print(f"--> [RUNNING] {desc}...")
    if dry_run:
        print(f"    [DRY-RUN PASS] {desc} (0.00s)")
        return True, "dry-run"
    start_t = time.time()
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        elapsed = time.time() - start_t
        out = (proc.stdout + "\n" + proc.stderr).strip()
        if proc.returncode == 0:
            print(f"    [PASS] {desc} ({elapsed:.2f}s)")
            return True, out
        else:
            print(f"    [FAIL] {desc} ({elapsed:.2f}s, exit code {proc.returncode})")
            return False, out
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_t
        msg = f"Command timed out after {timeout}s"
        print(f"    [FAIL] {desc} ({msg})")
        return False, msg
    except Exception as e:
        elapsed = time.time() - start_t
        msg = f"Failed to execute command: {e}"
        print(f"    [FAIL] {desc} ({msg})")
        return False, msg


def _resolve_branch_and_sha(repo_root: Path, explicit_branch: str | None) -> tuple[str, str]:
    branch = explicit_branch or ""
    if not branch:
        with contextlib.suppress(Exception):
            res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if res.returncode == 0:
                branch = res.stdout.strip()
    branch = branch or "HEAD"
    head_sha = ""
    with contextlib.suppress(Exception):
        res = subprocess.run(
            ["git", "rev-parse", branch],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if res.returncode == 0:
            head_sha = res.stdout.strip()
    return branch, head_sha


def _load_prior_passing_stages(receipt_path: Path, expected_head_sha: str | None = None) -> set[str]:
    if not receipt_path.is_file():
        return set()
    try:
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        if expected_head_sha and data.get("head_commit_sha") != expected_head_sha:
            return set()
        stages = data.get("stages", [])
        return {
            str(s.get("stage_name"))
            for s in stages
            if isinstance(s, dict) and s.get("status") in ("PASS", "REUSED_PASS")
        }
    except Exception:
        return set()


def verify_main_readiness(
    repo_root: Path,
    branch: str | None = None,
    fail_fast: bool = False,
    recheck_failed_only: bool = False,
    dry_run: bool = False,
    full: bool = False,
) -> int:
    python_bin = repo_root / ".venv" / "bin" / "python"
    if not python_bin.exists():
        python_bin = Path(sys.executable)

    eff_branch, head_sha = _resolve_branch_and_sha(repo_root, branch)
    try:
        from tools.pr_governance_core.common import slugify_branch

        slug = slugify_branch(eff_branch)
    except Exception:
        slug = eff_branch.replace("/", "_")

    # Classify effective risk lane (Lane 0 / Lane 1 / Lane 2, fail-closed).
    effective_lane = 2
    lane_name = "Lane 2 (High / Critical Risk)"
    required_stage_set: set[str] | None = None
    batch_advisories: list[dict[str, Any]] = []
    changed_paths: list[str] = []
    try:
        from tools.change_lane_classifier import classify_paths, collect_git_changed_paths

        changed_paths, churn_loc = collect_git_changed_paths(repo_root, staged=False, base_ref="main")
        if changed_paths:
            lane_report = classify_paths(changed_paths, repo_root=repo_root, churn_loc=churn_loc)
            effective_lane = int(lane_report.get("effective_lane", 2))
            lane_name = str(lane_report.get("lane_name") or lane_name)
            batch_advisories = list(lane_report.get("advisories") or [])
            req_list = list(lane_report.get("required_readiness_stages") or [])
            if not full and effective_lane < 2 and req_list:
                required_stage_set = set(req_list)
    except (ImportError, OSError, ValueError, KeyError):
        effective_lane = 2

    receipt_dir = repo_root / "reports" / "readiness"
    receipt_path = receipt_dir / f"local_main_readiness_{slug}_receipt.json"
    prior_passed = (
        _load_prior_passing_stages(receipt_path, expected_head_sha=head_sha)
        if recheck_failed_only
        else set()
    )

    categories: dict[str, tuple[bool, str]] = {}
    stage_records: list[dict[str, Any]] = []

    print("=" * 76)
    print("  LOCAL PR / MAIN READINESS GATE (Tier 2)")
    print("  Invariant: Does the structurally legal system actually work?")
    print(f"  Risk Lane: {lane_name} (Lane {effective_lane}, full={full}, paths={len(changed_paths)})")
    for adv in batch_advisories:
        print(f"  [ADVISORY:{adv.get('code')}] {adv.get('message')}")
    print("=" * 76 + "\n")

    shield_cmd = [str(python_bin), "tools/run_diff_scoped_eval_shield.py"]
    if full or effective_lane >= 2 or not changed_paths:
        shield_cmd.append("--all")

    stage_defs: list[tuple[str, list[str] | None, str, int]] = [
        (
            "1. Tier 1 Structural Governance",
            [str(python_bin), "tools/verify_commit.py", "--all"],
            "Tier 1 Structural Governance (All 5 Categories)",
            180,
        ),
        (
            "2. Architecture & Service Boundaries",
            [str(python_bin), "-m", "pytest", "tests/unit/test_architecture_wave2_boundaries.py", "--timeout=60", "-q"],
            "Architectural Boundary & Decomposed Services Tests",
            120,
        ),
        (
            "3. Adversarial Purity & Derivation Integrity",
            [str(python_bin), "-m", "pytest", "tests/unit/test_adversarial_governance.py", "--timeout=60", "-q"]
            if (repo_root / "tests" / "unit" / "test_adversarial_governance.py").exists()
            else None,
            "Adversarial Quality & Purity Suite (Cases A-F)",
            120,
        ),
        (
            "4. Declarative Contracts & Schemas",
            [str(python_bin), "tools/lint_contract_schemas.py", "--all"],
            "Declarative Schema & Contract Validation",
            30,
        ),
        (
            "5. PR Merge Queue & Trunk Lock Governance",
            [str(python_bin), "-m", "pytest", "tests/test_pr_merge_queue_governance.py", "--timeout=60", "-q"]
            if (repo_root / "tests" / "test_pr_merge_queue_governance.py").exists()
            else None,
            "Governed PR Merge Queue & Trunk Lock Suite",
            120,
        ),
        (
            "6. Resume & Outreach Eval Harness & Promotion Gate",
            [
                str(python_bin),
                "ops_scripts/ci/check_eval_harness_promotion_evidence.py",
                "--run-offline",
                "--out",
                "artifacts/eval_harness/readiness/final_gate_report.json",
            ]
            if (repo_root / "ops_scripts" / "ci" / "check_eval_harness_promotion_evidence.py").exists()
            else None,
            "Resume & Outreach Eval Harness & Promotion Gate",
            180,
        ),
        (
            "7. Eval Construct Validity & Unmocked E2E Pinning",
            [str(python_bin), "tools/audit_eval_construct_validity.py", "--verify-strict", "--include-e2e-pin"]
            if (repo_root / "tools" / "audit_eval_construct_validity.py").exists()
            else None,
            "Eval Construct Validity & Unmocked E2E Pinning Gate",
            60,
        ),
        (
            "8. Diff-Scoped Unmocked Domain Eval Shield",
            shield_cmd
            if (repo_root / "tools" / "run_diff_scoped_eval_shield.py").exists()
            else None,
            "Diff-Scoped Unmocked Domain Eval Shield",
            120,
        ),
        (
            "9. Governance Harmonization & SSOT Drift Audit",
            [str(python_bin), "tools/audit_governance_harmonization.py", "--strict"]
            if (repo_root / "tools" / "audit_governance_harmonization.py").exists()
            else None,
            "Governance Harmonization & SSOT Drift Audit",
            60,
        ),
    ]

    for stage_name, argv, desc, timeout_s in stage_defs:
        if required_stage_set is not None and stage_name not in required_stage_set:
            print(f"--> [LANE_EXEMPT] {desc} (Lane {effective_lane} exemption)")
            categories[stage_name] = (True, f"Exempt under Lane {effective_lane}")
            stage_records.append({"stage_name": stage_name, "status": "LANE_EXEMPT"})
            continue

        if stage_name in prior_passed:
            print(f"--> [REUSED_PASS] {desc} (skipped via --recheck-failed-only)")
            categories[stage_name] = (True, "Reused prior PASS stage receipt")
            stage_records.append({"stage_name": stage_name, "status": "REUSED_PASS"})
            continue

        if argv is None:
            categories[stage_name] = (True, "Optional suite not present")
            stage_records.append({"stage_name": stage_name, "status": "PASS"})
            continue

        ok, out = run_cmd(argv, cwd=repo_root, desc=desc, timeout=timeout_s, dry_run=dry_run)
        categories[stage_name] = (ok, out)
        stage_records.append({"stage_name": stage_name, "status": "PASS" if ok else "FAIL"})
        if not ok and fail_fast:
            print("    [FAIL-FAST] Halting readiness run on first stage failure.")
            break

    all_passed = all(passed for passed, _ in categories.values()) and len(categories) == len(stage_defs)

    with contextlib.suppress(Exception):
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_payload = {
            "branch": eff_branch,
            "head_commit_sha": head_sha,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "effective_lane": effective_lane,
            "lane_name": lane_name,
            "batch_advisories": batch_advisories,
            "total_stages": len(stage_defs),
            "stages_evaluated": len(stage_records),
            "stages": stage_records,
            "terminal_outcome": "PASS" if all_passed else "FAIL",
        }
        receipt_path.write_text(json.dumps(receipt_payload, indent=2) + "\n", encoding="utf-8")

    # Summary report
    print("\n" + "=" * 76)
    print("  MAIN READINESS GATE SUMMARY")
    print("=" * 76)
    for cat_name, (passed, details) in categories.items():
        st = "[PASS]" if passed else "[FAIL]"
        print(f"  {cat_name:<46} {st}")
        if not passed:
            lines = details.splitlines()
            for l in lines[-6:]:
                print(f"      | {l}")

    print("-" * 76)
    if all_passed:
        print("  RESULT: LOCAL MAIN READINESS GATE PASSED")
        print("  Feature branch is verified and READY for local-main merge.")
        print("=" * 76 + "\n")
        return 0
    else:
        print("  RESULT: LOCAL MAIN READINESS GATE FAILED", file=sys.stderr)
        print("  Feature branch is NOT READY for merge into local-main.", file=sys.stderr)
        print("=" * 76 + "\n", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authoritative Tier 2 Local Main Readiness Gate.")
    parser.add_argument("--repo-root", default=".", help="Root of repository")
    parser.add_argument("--branch", default=None, help="Branch name being qualified")
    parser.add_argument("--fail-fast", action="store_true", help="Halt on first stage failure")
    parser.add_argument(
        "--recheck-failed-only",
        action="store_true",
        help="Only re-execute stages that failed in prior run",
    )
    parser.add_argument("--full", action="store_true", help="Run full readiness suite")
    parser.add_argument("--dry-run", action="store_true", help="Simulate readiness verification")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    return verify_main_readiness(
        repo_root,
        branch=args.branch,
        fail_fast=args.fail_fast,
        recheck_failed_only=args.recheck_failed_only,
        dry_run=args.dry_run,
        full=args.full,
    )


if __name__ == "__main__":
    sys.exit(main())
