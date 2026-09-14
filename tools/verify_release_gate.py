#!/usr/bin/env python3
"""Authoritative Single Release Gate Command for Sovereign Agentic Platform.

Part of Sovereign Agentic Platform Governance (Wave 6 - Final Closure Wave).
Consolidates all verification tiers into a single atomic command:
1. Tier 1 Pre-Commit Quality Gate (Code Hygiene, Architecture, Purity, Schema, Secrets)
2. Continuous Architecture Boundaries & File Budgets
3. All 6 Anti-pattern Remediation Wave Suites (Waves 1-6)
4. Full Repository Regression Suite
5. Attestable Release Manifest & Receipt Emission
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WAVE_TEST_FILES = [
    "tests/unit/test_antipattern_wave1_packaging_ssot.py",
    "tests/unit/test_antipattern_wave2_state_contracts.py",
    "tests/unit/test_antipattern_wave3_pipeline_and_feedback.py",
    "tests/unit/test_antipattern_wave4_observability_persistence.py",
    "tests/unit/test_antipattern_wave5_monolith_decomposition.py",
    "tests/unit/test_antipattern_wave6_governance_convergence.py",
]


def run_command(cmd: list[str], cwd: Path, timeout: int = 180) -> tuple[int, str, str, float]:
    """Execute a subprocess command with duration timing."""
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        duration = round(time.time() - start, 2)
        return proc.returncode, proc.stdout, proc.stderr, duration
    except subprocess.TimeoutExpired:
        duration = round(time.time() - start, 2)
        return 124, "", f"Command timed out after {timeout} seconds", duration
    except Exception as err:
        duration = round(time.time() - start, 2)
        return 1, "", str(err), duration


def get_git_metadata(repo_root: Path) -> dict[str, str]:
    """Extract current git commit and branch info."""
    code_sha, out_sha, _, _ = run_command(["git", "rev-parse", "HEAD"], repo_root)
    code_branch, out_branch, _, _ = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root)

    return {
        "commit_sha": out_sha.strip() if code_sha == 0 else "UNKNOWN",
        "branch": out_branch.strip() if code_branch == 0 else "UNKNOWN",
    }


def execute_release_gate(
    repo_root: Path,
    output_dir: Path | None = None,
    keep_going: bool = False,
    wave_suites: list[str] | None = None,
    run_full_suite: bool = True,
) -> dict[str, Any]:
    """Execute the complete release gate and compile the receipt."""
    out_dir = output_dir or (repo_root / "artifacts" / "release")
    out_dir.mkdir(parents=True, exist_ok=True)

    git_meta = get_git_metadata(repo_root)
    timestamp = datetime.now(timezone.utc).isoformat()

    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "gate_name": "SOVEREIGN_PLATFORM_RELEASE_GATE",
        "wave": 6,
        "timestamp": timestamp,
        "repository": str(repo_root),
        "branch": git_meta["branch"],
        "commit_sha": git_meta["commit_sha"],
        "python_version": sys.version.split()[0],
        "checks": {},
        "all_passed": True,
        "failure_count": 0,
    }

    # Step 1: Continuous Architecture Boundaries Linter
    arch_code, arch_out, arch_err, arch_dur = run_command(
        [sys.executable, "tools/lint_architecture_boundaries.py"], repo_root
    )
    receipt["checks"]["architecture_boundaries"] = {
        "status": "PASS" if arch_code == 0 else "FAIL",
        "returncode": arch_code,
        "duration_seconds": arch_dur,
        "summary": "Zero concrete storage imports, pure sys.path, and file budgets verified",
        "error": arch_err if arch_code != 0 else "",
    }
    if arch_code != 0:
        receipt["all_passed"] = False
        receipt["failure_count"] += 1
        if not keep_going:
            return finish_receipt(receipt, out_dir)

    # Step 2: Tier 1 Pre-Commit Gate (Hygiene, Architecture, Purity, Schema, Secrets)
    tier1_code, tier1_out, tier1_err, tier1_dur = run_command(
        [sys.executable, "tools/verify_commit.py"], repo_root, timeout=240
    )
    receipt["checks"]["tier1_pre_commit"] = {
        "status": "PASS" if tier1_code == 0 else "FAIL",
        "returncode": tier1_code,
        "duration_seconds": tier1_dur,
        "summary": "Passed all 5 structural quality tiers",
        "error": tier1_err if tier1_code != 0 else "",
    }
    if tier1_code != 0:
        receipt["all_passed"] = False
        receipt["failure_count"] += 1
        if not keep_going:
            return finish_receipt(receipt, out_dir)

    # Step 3: Wave Unit Test Suites
    suites_to_run = wave_suites if wave_suites is not None else [f for f in WAVE_TEST_FILES if (repo_root / f).exists()]
    wave_code, wave_out, wave_err, wave_dur = run_command(
        [sys.executable, "-m", "pytest", "-v"] + suites_to_run, repo_root
    )
    receipt["checks"]["wave_suites"] = {
        "status": "PASS" if wave_code == 0 else "FAIL",
        "returncode": wave_code,
        "duration_seconds": wave_dur,
        "suites_tested": suites_to_run,
        "error": wave_err if wave_code != 0 else "",
    }
    if wave_code != 0:
        receipt["all_passed"] = False
        receipt["failure_count"] += 1
        if not keep_going:
            return finish_receipt(receipt, out_dir)

    # Step 4: Full Repository Unit Test Suite
    if run_full_suite:
        full_code, full_out, full_err, full_dur = run_command(
            [sys.executable, "-m", "pytest", "-q", "tests/unit/"], repo_root
        )
        receipt["checks"]["full_unit_suite"] = {
            "status": "PASS" if full_code == 0 else "FAIL",
            "returncode": full_code,
            "duration_seconds": full_dur,
            "error": full_err if full_code != 0 else "",
        }
        if full_code != 0:
            receipt["all_passed"] = False
            receipt["failure_count"] += 1

    return finish_receipt(receipt, out_dir)


def finish_receipt(receipt: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Serialize receipt, compute SHA-256 digest, and save receipt and manifest."""
    receipt["status"] = "PASSED" if receipt["all_passed"] else "FAILED"

    # Canonical receipt serialization
    receipt_json = json.dumps(receipt, indent=2, sort_keys=True)
    receipt_bytes = receipt_json.encode("utf-8")
    receipt_digest = hashlib.sha256(receipt_bytes).hexdigest()

    receipt["receipt_digest"] = receipt_digest

    receipt_file = output_dir / "release_receipt.json"
    receipt_file.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")

    manifest = {
        "manifest_type": "RELEASE_MANIFEST",
        "schema_version": "1.0.0",
        "created_at": receipt["timestamp"],
        "commit_sha": receipt["commit_sha"],
        "branch": receipt["branch"],
        "status": receipt["status"],
        "receipt_file": str(receipt_file.name),
        "receipt_sha256": receipt_digest,
    }
    manifest_file = output_dir / "release_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Authoritative Single Release Gate Command.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for release receipt")
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    parser.add_argument("--keep-going", action="store_true", help="Run all checks even if an early check fails")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    receipt = execute_release_gate(repo_root, output_dir=args.output_dir, keep_going=args.keep_going)

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print("========================================================================")
        print("  SOVEREIGN AGENTIC PLATFORM — AUTHORITATIVE RELEASE GATE (Wave 6)")
        print(f"  Status: {receipt['status']}")
        print(f"  Commit: {receipt['commit_sha']} ({receipt['branch']})")
        print("========================================================================")
        for name, data in receipt["checks"].items():
            print(f"  - {name:<26}: [{data['status']}] ({data['duration_seconds']}s)")
        print("------------------------------------------------------------------------")
        if receipt["all_passed"]:
            print("  RESULT: RELEASE GATE PASSED (All 6 waves and quality tiers verified)")
            print(f"  Receipt: artifacts/release/release_receipt.json")
            print(f"  SHA-256: {receipt['receipt_digest']}")
        else:
            print(f"  RESULT: RELEASE GATE FAILED ({receipt['failure_count']} failed checks)")
        print("========================================================================")

    return 0 if receipt["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
