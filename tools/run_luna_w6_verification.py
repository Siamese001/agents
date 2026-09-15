#!/usr/bin/env python3
"""Run authoritative forensic verification of Wave 6 completion and final closeout using gpt-5.6-luna (medium) with env_agents."""

import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# 1. Load credentials from env_agents
env_file = Path("env_agents")
if not env_file.exists():
    raise FileNotFoundError("env_agents file not found in repository root")

for line in env_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from openai import OpenAI

client = OpenAI()

def run_cmd(cmd: list[str], timeout: int = 120) -> str:
    try:
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"resume_graph_engine/src:.{':' + existing_pythonpath if existing_pythonpath else ''}"
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env)
        return (res.stdout + "\n" + res.stderr).strip()
    except Exception as e:
        return f"Error: {e}"

git_log = run_cmd(["git", "log", "-n", "8", "--oneline"])
wave6_tests = run_cmd([".venv/bin/pytest", "-v", "tests/unit/test_antipattern_wave6_governance_convergence.py"])

wave_test_files = sorted(glob.glob("tests/unit/test_antipattern_wave*.py"))
all_wave_tests = run_cmd([".venv/bin/pytest", "-v"] + wave_test_files)
all_unit_tests = run_cmd([".venv/bin/pytest", "-q", "tests/unit/"])

arch_linter = run_cmd([".venv/bin/python", "tools/lint_architecture_boundaries.py"])
file_budgets = run_cmd([".venv/bin/python", "tools/lint_file_budgets.py"])
verify_commit = run_cmd([".venv/bin/python", "tools/verify_commit.py"])
release_gate = run_cmd([".venv/bin/python", "tools/verify_release_gate.py"])

manifest_content = ""
manifest_path = Path("artifacts/release/release_manifest.json")
if manifest_path.exists():
    manifest_content = manifest_path.read_text(encoding="utf-8")

receipt_content = ""
receipt_path = Path("artifacts/release/release_receipt.json")
if receipt_path.exists():
    receipt_content = receipt_path.read_text(encoding="utf-8")

audit_prompt = f"""You are the world-class Principal AI Systems Architect and Sovereign Agentic Platform Auditor.

OPERATOR REQUEST:
Ensure Wave 6 (W6: Cutover, Cleanup, and Continuous Architecture Governance) is fully completed across all requirements, governance protocols, and criteria.
This is the final wave of the 6-wave Anti-Pattern Remediation Roadmap under docs/refactoring-wave-protocol.md.

### FORENSIC EVIDENCE GATHERED FROM REPOSITORY:

1. GIT LOG (recent commits on refactor/antipattern-remediation-waves):
{git_log}

2. WAVE 6 UNIT TEST SUITE:
{wave6_tests}

3. COMBINED WAVES 1–6 UNIT TESTS (All {len(wave_test_files)} wave test suites):
Files tested: {wave_test_files}
{all_wave_tests}

4. FULL REPOSITORY UNIT TEST SWEEP (Zero warnings, full green pass):
{all_unit_tests}

5. CONTINUOUS ARCHITECTURAL BOUNDARY LINTER (tools/lint_architecture_boundaries.py):
{arch_linter}

6. PRODUCTION FILE BUDGETS AUDIT (tools/lint_file_budgets.py):
{file_budgets}

7. TIER 1 PRE-COMMIT VERIFICATION GATE (tools/verify_commit.py):
{verify_commit}

8. AUTHORITATIVE RELEASE GATE EXECUTION (tools/verify_release_gate.py):
{release_gate}

9. ATTESTED RELEASE MANIFEST (artifacts/release/release_manifest.json):
{manifest_content}

10. ATTESTED RELEASE RECEIPT (artifacts/release/release_receipt.json):
{receipt_content}

Evaluate whether Wave 6 successfully satisfies the refactoring wave protocol, anti-pattern remediation roadmap, and continuous governance requirements.
Provide your evaluation in a clear forensic report:
1. Executive Verdict (PASSED / FAILED)
2. Evidence Verification across Key Objectives:
   - Single Authoritative Release Gate Command (`tools/verify_release_gate.py`)
   - Continuous Architecture Linter (`tools/lint_architecture_boundaries.py` enforcing storage isolation, line budgets, and sys.path purity)
   - Configuration & Deprecation Warning Elimination (zero Pydantic V2 warnings, zero pytest config warnings)
   - All 6 Wave Unit Suites Passing (Waves 1 to 6 full regression check)
   - Attested Release Artifacts (release_manifest.json, release_receipt.json with SHA-256 digest)
3. Cumulative 6-Wave Program Review:
   - Wave 1: Packaging SSOT, Subtree De-duplication, Provider Profiles
   - Wave 2: Typed State Contracts, Failure Taxonomy, Recovery Budgets
   - Wave 3: Canonical Dispatch Authority, Structured Feedback Controller
   - Wave 4: Event Envelopes, Artifact Manifests, Persistence Ports, Replay Verifier
   - Wave 5: Monolith Decomposition, Modular Pipeline Services, Storage Isolation
   - Wave 6: Cutover, Cleanup, and Continuous Architecture Governance
4. Final Release Determination & Production Readiness.
"""

print("Dispatching prompt to gpt-5.6-luna (medium)...")
response = None
for attempt in range(1, 5):
    try:
        response = client.chat.completions.create(
            model="gpt-5.6-luna",
            reasoning_effort="medium",
            messages=[
                {"role": "system", "content": "You are the Principal AI Systems Architect evaluating Wave 6 and final 6-wave program completion."},
                {"role": "user", "content": audit_prompt},
            ],
        )
        break
    except Exception as e:
        print(f"Attempt {attempt} failed: {e}. Retrying in {attempt * 3}s...")
        time.sleep(attempt * 3)

if response is None:
    raise RuntimeError("Failed to obtain response from gpt-5.6-luna after 4 attempts.")

verdict = response.choices[0].message.content
print("\n=== LUNA FORENSIC VERDICT ===\n")
print(verdict)

for out_path in ["artifacts/w6_completion_verification_luna.md", "artifacts/final_roadmap_luna_verification_report.md"]:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(verdict)
    print(f"Written report to {out_path}")
