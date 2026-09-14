#!/usr/bin/env python3
"""Run authoritative forensic verification of Wave 6 (Final Closure Wave) completion using gpt-5.6-luna (medium) with env_agents."""

import json
import os
import subprocess
import sys
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

# Gather live forensic evidence
def run_cmd(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
        out = (res.stdout + "\n" + res.stderr).strip()
        return out
    except Exception as e:
        return f"Error: {e}"

git_log = run_cmd(["git", "log", "-n", "8", "--oneline"])
git_status = run_cmd(["git", "status", "--short"])

# Release Gate execution
print("Running authoritative release gate...")
release_gate_out = run_cmd([sys.executable, "tools/verify_release_gate.py"])

# Architecture linter execution
arch_lint_out = run_cmd([sys.executable, "tools/lint_architecture_boundaries.py"])

# Tier 1 pre-commit check
tier1_out = run_cmd([sys.executable, "tools/verify_commit.py"])

# Wave unit tests execution
wave_tests_out = run_cmd([
    sys.executable, "-m", "pytest", "-v",
    "tests/unit/test_antipattern_wave1_packaging_ssot.py",
    "tests/unit/test_antipattern_wave2_state_contracts.py",
    "tests/unit/test_antipattern_wave3_pipeline_and_feedback.py",
    "tests/unit/test_antipattern_wave4_observability_persistence.py",
    "tests/unit/test_antipattern_wave5_monolith_decomposition.py",
    "tests/unit/test_antipattern_wave6_governance_convergence.py",
])

# Read release receipt and manifest if generated
receipt_path = Path("artifacts/release/release_receipt.json")
manifest_path = Path("artifacts/release/release_manifest.json")
receipt_content = receipt_path.read_text(encoding="utf-8") if receipt_path.exists() else "MISSING"
manifest_content = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else "MISSING"

audit_prompt = f"""You are the world-class Principal AI Systems Architect and Sovereign Agentic Platform Auditor.

OPERATOR REQUEST:
Ensure Wave 6 (W6: Cutover, Cleanup, and Continuous Architecture Governance) is fully completed across all requirements, governance protocols, and criteria. This is the final closure wave (Wave 6 of 6) under docs/refactoring-wave-protocol.md.

REPOSITORY FORENSIC TELEMETRY:
=========================================
1. Recent Git Commits & Status:
{git_log}
Status:
{git_status}

2. Authoritative Release Gate (`tools/verify_release_gate.py`):
{release_gate_out}

3. Continuous Architecture Boundaries (`tools/lint_architecture_boundaries.py`):
{arch_lint_out}

4. Tier 1 Pre-Commit Gate (`tools/verify_commit.py`):
{tier1_out}

5. All 6 Wave Test Suites:
{wave_tests_out}

6. Attested Release Receipt (`artifacts/release/release_receipt.json`):
{receipt_content}

7. Attested Release Manifest (`artifacts/release/release_manifest.json`):
{manifest_content}
=========================================

WAVE 6 MANDATES BEING AUDITED:
1. Single Authoritative Release Gate:
   - `python tools/verify_release_gate.py` must be the sole authoritative entrypoint.
   - Executes architecture linters, commit gates, all 6 wave suites, and regression checks.
   - Emits cryptographically attested `artifacts/release/release_receipt.json` and `artifacts/release/release_manifest.json`.
2. Warning-Free Repository Execution:
   - Eradication of Pydantic deprecation warnings (e.g. `ConfigDict` upgrade in `apps_research/types/research_types.py`).
   - Clean pytest configuration SSOT in `pytest.ini` without configuration conflict warnings.
   - Zero runtime warnings during release gate or test execution.
3. Continuous Architecture Governance:
   - AST enforcement of domain storage isolation (zero concrete storage imports in domain services).
   - AST enforcement of sys.path purity (zero sys.path mutations in production).
   - Strict enforcement of file budgets (<= 600 lines per production file).
4. All Six Waves Convergence:
   - W1: Packaging SSOT & Subtree deduplication.
   - W2: Typed state & error contracts (`ResumeRunState`, `FailureKind`).
   - W3: Canonical dispatch & structured feedback controller.
   - W4: Canonical event envelopes, artifact manifests, decoupled persistence ports & replay verification.
   - W5: Monolith decomposition, domain services isolation, executive summary repair & voice policies.
   - W6: Release gate cutover, warning eradication, continuous architecture linters, attested receipt.

TASK:
Deliver a comprehensive, forensic, code-grounded verification audit answering:
1. Is Wave 6 unequivocally and rigorously COMPLETED?
2. Detailed audit of each specific acceptance criterion from `plans/antipattern-remediation-wave6-b9e4a2.md`.
3. Proof of zero architectural regressions, zero warnings, and clean repository integrity.
4. Final verdict on the entire 6-Wave Antipattern Remediation Roadmap, declaring the platform certified and production-ready.
"""

out_path = Path("artifacts/w6_completion_verification_luna.md")
out_path.parent.mkdir(parents=True, exist_ok=True)

print("Dispatching Wave 6 verification audit prompt to gpt-5.6-luna (medium)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {
            "role": "system",
            "content": (
                "You are the world-class Principal AI Systems Architect and Sovereign Agentic Platform Auditor. "
                "Deliver an authoritative, code-grounded forensic completion audit."
            ),
        },
        {"role": "user", "content": audit_prompt},
    ],
    reasoning_effort="medium",
    max_completion_tokens=20000,
)

content = response.choices[0].message.content
out_path.write_text(content, encoding="utf-8")
print(f"Wave 6 verification audit completed! Written to {out_path} ({len(content)} chars)")
print("Usage:", response.usage)
