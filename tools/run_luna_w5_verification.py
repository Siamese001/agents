#!/usr/bin/env python3
"""Run authoritative forensic verification of Wave 5 completion using gpt-5.6-luna (medium) with env_agents."""

import glob
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

def run_cmd(cmd: list[str], timeout: int = 120) -> str:
    try:
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"resume_graph_engine/src:.{':' + existing_pythonpath if existing_pythonpath else ''}"
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env)
        return (res.stdout + "\n" + res.stderr).strip()
    except Exception as e:
        return f"Error: {e}"

git_log = run_cmd(["git", "log", "-n", "5", "--oneline"])
wave5_tests = run_cmd([".venv/bin/pytest", "-v", "tests/unit/test_antipattern_wave5_monolith_decomposition.py"])

# Expand all wave test files explicitly to prevent glob string failures in execve
wave_test_files = sorted(glob.glob("tests/unit/test_antipattern_wave*.py"))
all_wave_tests = run_cmd([".venv/bin/pytest", "-v"] + wave_test_files)
all_unit_tests = run_cmd([".venv/bin/pytest", "-q", "tests/unit/"])

# Verify file budgets
file_budgets = run_cmd([".venv/bin/python", "tools/lint_file_budgets.py"])

# Verify commit gate (Tier 1-5)
verify_commit = run_cmd([".venv/bin/python", "tools/verify_commit.py"])

# Verify exports, API contracts, domain boundary isolation
export_check = run_cmd([
    ".venv/bin/python", "-c",
    "import inspect\n"
    "from apps_rg.runtime.artifact_output import (\n"
    "    ArtifactOutputEmitter,\n"
    "    ArtifactPayloadBuilder,\n"
    "    DeterministicSerializer,\n"
    "    MandatoryOutputPolicy,\n"
    ")\n"
    "from apps_rg.runtime.pipeline import (\n"
    "    SectionGenerationService,\n"
    "    EvaluationService,\n"
    "    ArtifactAssembler,\n"
    "    ReleasePolicy,\n"
    "    ModularPipelineOrchestrator,\n"
    ")\n"
    "from apps_rg.runtime.sections.executive_summary import (\n"
    "    ExecutiveSummaryRepairEngine,\n"
    "    ExecutiveSummaryValidator,\n"
    "    VoiceRepairPolicy,\n"
    ")\n"
    "print('WAVE_5_EXPORTS: VERIFIED')\n"
    "import apps_rg.runtime.artifact_output as ao\n"
    "import apps_rg.runtime.pipeline as pl\n"
    "import apps_rg.runtime.sections.executive_summary as es\n"
    "for mod in (ao, pl, es):\n"
    "    src = inspect.getsource(mod)\n"
    "    assert 'sqlite3' not in src, f'Found sqlite3 in {mod.__name__}'\n"
    "    assert 'agents.persistence.sqlite' not in src, f'Found concrete sqlite in {mod.__name__}'\n"
    "print('DOMAIN_BOUNDARY_ISOLATION: VERIFIED (Zero concrete storage imports in decomposed services)')\n"
])

audit_prompt = f"""You are the world-class Principal AI Systems Architect and Sovereign Agentic Platform Auditor.

OPERATOR REQUEST:
Ensure Wave 5 (W5: Monolith Decomposition & Domain Boundary Enforcement) is fully completed across all requirements, governance protocols, and criteria.

### FORENSIC EVIDENCE GATHERED FROM REPOSITORY:

1. GIT LOG (recent commits on refactor/antipattern-remediation-waves):
{git_log}

2. WAVE 5 UNIT TEST SUITE:
{wave5_tests}

3. COMBINED WAVES 1–5 UNIT TESTS (All {len(wave_test_files)} wave test suites):
Files tested: {wave_test_files}
{all_wave_tests}

4. FULL REPOSITORY UNIT TEST SUMMARY:
{all_unit_tests}

5. FILE BUDGETS AUDIT (tools/lint_file_budgets.py):
{file_budgets}

6. TIER 1 PRE-COMMIT VERIFICATION GATE (tools/verify_commit.py):
{verify_commit}

7. EXPORT, API CONTRACT, AND DOMAIN BOUNDARY ISOLATION:
{export_check}

Evaluate whether Wave 5 successfully satisfies the refactoring wave protocol, anti-pattern remediation roadmap, and governance requirements.
Provide your evaluation in a clear forensic report:
1. Executive Verdict (PASSED / FAILED)
2. Evidence Verification:
   - Mandatory Run Outputs Decomposition (`apps_rg.runtime.artifact_output`)
   - Executive Summary Voice Repair Modularization (`apps_rg.runtime.sections.executive_summary`)
   - Modular Pipeline Services (`apps_rg.runtime.pipeline`)
   - Domain Boundary Isolation (clean decoupling between domain contracts and concrete storage)
3. Governance & Invariants (cross-wave regression, file budgets, pre-commit tiers)
4. Readiness for Wave 6 (Final Governance Convergence & Release Gate Lockdown).
"""

print("Dispatching prompt to gpt-5.6-luna (medium)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    reasoning_effort="medium",
    messages=[
        {"role": "system", "content": "You are the Principal AI Systems Architect evaluating Wave 5 refactoring completion."},
        {"role": "user", "content": audit_prompt},
    ],
)

verdict = response.choices[0].message.content
print("\n=== LUNA FORENSIC VERDICT ===\n")
print(verdict)

for out_path in ["artifacts/w5_completion_verification_luna.md", "artifacts/wave5_luna_verification_report.md"]:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(verdict)
    print(f"Written report to {out_path}")
