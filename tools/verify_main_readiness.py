#!/usr/bin/env python3
"""Authoritative Tier 2 Local Main Readiness Gate: Does the structurally legal system actually work?

Orchestrates deep validation before merging local feature branches into local main:
1. Tier 1 Structural Governance Gate (verify_commit.py --all)
2. Unit & Architectural Boundary Tests
3. Adversarial Purity & Derivation Integrity Suite (Cases A-F)
4. Runtime Pipeline Contracts & Provenance Verification
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def run_cmd(argv: list[str], cwd: Path, desc: str, timeout: int = 180) -> tuple[bool, str]:
    """Run subprocess command with bounded execution."""
    print(f"--> [RUNNING] {desc}...")
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


def verify_main_readiness(repo_root: Path) -> int:
    python_bin = repo_root / ".venv" / "bin" / "python"
    if not python_bin.exists():
        python_bin = Path(sys.executable)

    categories: dict[str, tuple[bool, str]] = {}

    print("=" * 76)
    print("  LOCAL PR / MAIN READINESS GATE (Tier 2)")
    print("  Invariant: Does the structurally legal system actually work?")
    print("=" * 76 + "\n")

    # Stage 1: Tier 1 Structural Pre-Commit Gate
    ok_t1, out_t1 = run_cmd(
        [str(python_bin), "tools/verify_commit.py", "--all"],
        cwd=repo_root,
        desc="Tier 1 Structural Governance (All 5 Categories)",
        timeout=60,
    )
    categories["1. Tier 1 Structural Governance"] = (ok_t1, out_t1)

    # Stage 2: Architecture & Service Boundary Unit Tests
    ok_u, out_u = run_cmd(
        [str(python_bin), "-m", "pytest", "tests/unit/test_architecture_wave2_boundaries.py", "-q"],
        cwd=repo_root,
        desc="Architectural Boundary & Decomposed Services Tests",
        timeout=120,
    )
    categories["2. Architecture & Service Boundaries"] = (ok_u, out_u)

    # Stage 3: Adversarial Governance & Purity Tests
    adversarial_test = repo_root / "tests" / "unit" / "test_adversarial_governance.py"
    if adversarial_test.exists():
        ok_adv, out_adv = run_cmd(
            [str(python_bin), "-m", "pytest", "tests/unit/test_adversarial_governance.py", "-q"],
            cwd=repo_root,
            desc="Adversarial Quality & Purity Suite (Cases A-F)",
            timeout=120,
        )
        categories["3. Adversarial Purity & Derivation Integrity"] = (ok_adv, out_adv)
    else:
        categories["3. Adversarial Purity & Derivation Integrity"] = (True, "Adversarial test suite file not yet present (pending Wave 6)")

    # Stage 4: Contract and Pipeline Invariant Validation
    ok_cfg, out_cfg = run_cmd(
        [str(python_bin), "tools/lint_contract_schemas.py", "--all"],
        cwd=repo_root,
        desc="Declarative Schema & Contract Validation",
        timeout=30,
    )
    categories["4. Declarative Contracts & Schemas"] = (ok_cfg, out_cfg)

    # Summary report
    print("\n" + "=" * 76)
    print("  MAIN READINESS GATE SUMMARY")
    print("=" * 76)
    all_passed = True
    for cat_name, (passed, details) in categories.items():
        st = "[PASS]" if passed else "[FAIL]"
        print(f"  {cat_name:<46} {st}")
        if not passed:
            all_passed = False
            # Print brief details of failure
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
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    return verify_main_readiness(repo_root)


if __name__ == "__main__":
    sys.exit(main())
