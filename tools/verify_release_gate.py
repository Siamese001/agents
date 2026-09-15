#!/usr/bin/env python3
"""Authoritative Release Gate Verification (Wave 6).

Consolidates all verification tiers and governance invariants:
1. Pre-Commit Quality Gate (Tier 1 Code Hygiene, Architecture, Purity, Schemas, Secrets).
2. Anti-Pattern Remediation Wave Test Suites (Waves 1 through 6).
3. Continuous Architectural Boundary Linter (Domain isolation, Sys.path purity, File budgets).
4. Deterministic Release Manifest & Verification Receipt Generation with cryptographic SHA-256 digest.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

WAVE_TEST_FILES = [
    "tests/unit/test_antipattern_wave1_packaging_ssot.py",
    "tests/unit/test_antipattern_wave2_state_contracts.py",
    "tests/unit/test_antipattern_wave3_pipeline_and_feedback.py",
    "tests/unit/test_antipattern_wave4_observability_persistence.py",
    "tests/unit/test_antipattern_wave5_monolith_decomposition.py",
    "tests/unit/test_antipattern_wave6_governance_convergence.py",
]


@dataclass
class CheckResult:
    check_name: str
    status: str  # "PASSED" | "FAILED"
    duration_seconds: float
    details: str
    violations: list[str]


def run_command_buffered(cmd: list[str], cwd: Path, timeout: int = 180) -> tuple[int, str, str, float]:
    start = time.perf_counter()
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"resume_graph_engine/src:.{':' + existing_pythonpath if existing_pythonpath else ''}"
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        elapsed = time.perf_counter() - start
        return res.returncode, res.stdout, res.stderr, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        return 124, "", f"Command timed out after {timeout}s", elapsed
    except Exception as e:
        elapsed = time.perf_counter() - start
        return 1, "", str(e), elapsed


def get_git_metadata(repo_root: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    try:
        rc, out, _, _ = run_command_buffered(["git", "rev-parse", "HEAD"], repo_root, 10)
        meta["commit_sha"] = out.strip() if rc == 0 else "UNKNOWN"
        rc, out, _, _ = run_command_buffered(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root, 10)
        meta["branch"] = out.strip() if rc == 0 else "UNKNOWN"
    except Exception:
        meta["commit_sha"] = "UNKNOWN"
        meta["branch"] = "UNKNOWN"
    return meta


def run_tier1_precommit(repo_root: Path) -> CheckResult:
    py_bin = repo_root / ".venv" / "bin" / "python"
    python_cmd = str(py_bin) if py_bin.exists() else sys.executable
    code, stdout, stderr, dur = run_command_buffered(
        [python_cmd, "tools/verify_commit.py"],
        cwd=repo_root,
        timeout=120,
    )
    violations = []
    if code != 0:
        violations.append(f"Pre-commit gate failed with exit code {code}: {stderr or stdout}")
    return CheckResult(
        check_name="Tier 1 Pre-Commit Quality Gate",
        status="PASSED" if code == 0 else "FAILED",
        duration_seconds=round(dur, 3),
        details="Standard Code Hygiene, Architectural Governance, Production Purity, Contract Schemas, Secrets",
        violations=violations,
    )


def run_architecture_boundary_linter(repo_root: Path) -> CheckResult:
    py_bin = repo_root / ".venv" / "bin" / "python"
    python_cmd = str(py_bin) if py_bin.exists() else sys.executable
    code, stdout, stderr, dur = run_command_buffered(
        [python_cmd, "tools/lint_architecture_boundaries.py", "--json"],
        cwd=repo_root,
        timeout=60,
    )
    violations = []
    if code != 0:
        try:
            data = json.loads(stdout)
            for check_data in data.get("checks", {}).values():
                for v in check_data.get("violations", []):
                    violations.append(str(v))
        except Exception:
            violations.append(stderr or stdout)
    return CheckResult(
        check_name="Architectural Boundaries Linter (Domain Isolation, Sys.Path Purity, File Budgets)",
        status="PASSED" if code == 0 else "FAILED",
        duration_seconds=round(dur, 3),
        details="Domain/storage isolation, file budgets, sys.path prohibition",
        violations=violations,
    )


def run_antipattern_wave_suites(repo_root: Path, target_suites: list[str] | None = None) -> list[CheckResult]:
    pytest_bin = repo_root / ".venv" / "bin" / "pytest"
    pytest_cmd = str(pytest_bin) if pytest_bin.exists() else "pytest"

    results: list[CheckResult] = []
    suites_to_run = target_suites if target_suites is not None else WAVE_TEST_FILES

    for w_rel in suites_to_run:
        w_path = repo_root / w_rel
        if not w_path.exists():
            results.append(
                CheckResult(
                    check_name=f"Anti-Pattern Unit Suite: {Path(w_rel).stem}",
                    status="FAILED",
                    duration_seconds=0.0,
                    details=f"Test file missing: {w_rel}",
                    violations=[f"File not found: {w_rel}"],
                )
            )
            continue

        code, stdout, stderr, dur = run_command_buffered(
            [pytest_cmd, "-q", str(w_path)],
            cwd=repo_root,
            timeout=120,
        )
        violations = []
        if code != 0:
            violations.append(f"Suite {w_path.name} failed (exit {code}): {stderr or stdout}")
        results.append(
            CheckResult(
                check_name=f"Anti-Pattern Unit Suite: {w_path.stem}",
                status="PASSED" if code == 0 else "FAILED",
                duration_seconds=round(dur, 3),
                details=f"Test file: {w_path.name}",
                violations=violations,
            )
        )

    return results


def execute_release_gate(
    repo_root: Path,
    output_dir: Path | None = None,
    keep_going: bool = True,
    wave_suites: list[str] | None = None,
    run_full_suite: bool = False,
) -> dict[str, Any]:
    """Execute the full release gate and return the canonical receipt dictionary."""
    checks: list[CheckResult] = []

    # 1. Tier 1 Pre-Commit Gate
    checks.append(run_tier1_precommit(repo_root))

    # 2. Architecture boundary linter
    checks.append(run_architecture_boundary_linter(repo_root))

    # 3. Anti-pattern wave test suites
    wave_results = run_antipattern_wave_suites(repo_root, target_suites=wave_suites)
    checks.extend(wave_results)

    # 4. Optional full repository unit suite
    if run_full_suite:
        pytest_bin = repo_root / ".venv" / "bin" / "pytest"
        pytest_cmd = str(pytest_bin) if pytest_bin.exists() else "pytest"
        code, stdout, stderr, dur = run_command_buffered(
            [pytest_cmd, "-q", "tests/unit/"],
            cwd=repo_root,
            timeout=180,
        )
        checks.append(
            CheckResult(
                check_name="Full Repository Unit Suite",
                status="PASSED" if code == 0 else "FAILED",
                duration_seconds=round(dur, 3),
                details="Complete tests/unit/ test sweep",
                violations=[stderr or stdout] if code != 0 else [],
            )
        )

    git_meta = get_git_metadata(repo_root)
    all_passed = all(c.status == "PASSED" for c in checks)
    overall_status = "PASSED" if all_passed else "FAILED"
    now_iso = datetime.now(timezone.utc).isoformat()

    receipt_payload = {
        "gate_name": "SOVEREIGN_PLATFORM_RELEASE_GATE",
        "wave": 6,
        "status": overall_status,
        "all_passed": all_passed,
        "timestamp": now_iso,
        "metadata": git_meta,
        "checks": [asdict(c) for c in checks],
    }

    # Deterministic SHA-256 digest of normalized JSON string
    serialized_canonical = json.dumps(receipt_payload, sort_keys=True)
    receipt_digest = hashlib.sha256(serialized_canonical.encode("utf-8")).hexdigest()
    receipt_payload["receipt_digest"] = receipt_digest

    manifest_payload = {
        "manifest_type": "RELEASE_MANIFEST",
        "manifest_version": "1.0.0",
        "wave": 6,
        "status": overall_status,
        "timestamp": now_iso,
        "receipt_sha256": receipt_digest,
        "git_commit": git_meta.get("commit_sha"),
        "git_branch": git_meta.get("branch"),
        "waves_verified": [
            "Wave 1 (Packaging SSOT, Subtree De-duplication, Provider Profiles)",
            "Wave 2 (Typed State Contracts, Failure Taxonomy, Recovery Budgets)",
            "Wave 3 (Canonical Dispatch Authority, Structured Feedback Controller)",
            "Wave 4 (Event Envelopes, Artifact Manifests, Persistence Ports, Replay)",
            "Wave 5 (Monolith Decomposition, Modular Pipeline Services, Storage Isolation)",
            "Wave 6 (Cutover, Cleanup, Continuous Architecture Governance)",
        ],
        "checks_total": len(checks),
        "checks_passed": sum(1 for c in checks if c.status == "PASSED"),
        "checks_failed": sum(1 for c in checks if c.status == "FAILED"),
    }

    if output_dir is not None:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "release_receipt.json").write_text(json.dumps(receipt_payload, indent=2), encoding="utf-8")
        (out_path / "release_manifest.json").write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    return receipt_payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authoritative Release Gate Verifier")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root path")
    parser.add_argument("--receipt-dir", type=Path, default=Path("artifacts/release"), help="Receipt output directory")
    parser.add_argument("--no-write", action="store_true", help="Perform verification without writing artifacts")
    parser.add_argument("--json", action="store_true", help="Output verification result in JSON format to stdout")
    parser.add_argument("--full-suite", action="store_true", help="Run entire tests/unit/ directory as part of gate")
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    receipt_dir = None if args.no_write else (repo_root / args.receipt_dir).resolve()

    receipt = execute_release_gate(
        repo_root=repo_root,
        output_dir=receipt_dir,
        keep_going=True,
        run_full_suite=args.full_suite,
    )

    if args.json:
        print(json.dumps(receipt, indent=2))
        return 0 if receipt["all_passed"] else 1

    print("========================================================================")
    print("  AUTHORITATIVE RELEASE GATE VERIFICATION (Wave 6)")
    print("========================================================================")
    for c in receipt["checks"]:
        status_tag = f"[{c['status']}]"
        print(f"  {c['check_name']:<60} {status_tag:>10} ({c['duration_seconds']:.2f}s)")
        if c.get("violations"):
            for v in c["violations"]:
                print(f"    -> {v}")
    print("------------------------------------------------------------------------")
    print(f"  RESULT: RELEASE GATE {receipt['status']} (Digest: {receipt['receipt_digest'][:16]}...)")
    if receipt_dir:
        print(f"  Receipt written to:  {receipt_dir / 'release_receipt.json'}")
        print(f"  Manifest written to: {receipt_dir / 'release_manifest.json'}")
    print("========================================================================")

    return 0 if receipt["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
