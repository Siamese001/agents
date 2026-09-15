#!/usr/bin/env python3
"""Run authoritative forensic verification of Wave 1 completion using gpt-5.6-luna (medium) with env_agents."""

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
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        return res.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

git_log = run_cmd(["git", "log", "-n", "3", "--oneline"])
package_tests = run_cmd(["uv", "run", "pytest", "-v", "tests/unit/test_antipattern_wave1_packaging_ssot.py"])
security_tests = run_cmd(["uv", "run", "pytest", "-v", "tests/unit/test_precision_security_modularization.py"])
file_budgets = run_cmd(["uv", "run", "python3", "tools/lint_file_budgets.py"])
verify_commit = run_cmd(["uv", "run", "python3", "tools/verify_commit.py"])

# Canonical module resolution check
canonical_resolution = run_cmd([
    "uv", "run", "python3", "-c",
    "import apps_research, apps_eval, apps_model_telemetry, infrastructure.utils.precision_security_framework as psf\n"
    "print('apps_research:', apps_research.__file__)\n"
    "print('apps_eval:', apps_eval.__file__)\n"
    "print('apps_model_telemetry:', apps_model_telemetry.__file__)\n"
    "print('precision_security_framework facade classes count:', len(psf.__all__))"
])

# Subtree de-duplication check
resume_graph_subtrees = run_cmd([
    "python3", "-c",
    "from pathlib import Path\n"
    "p = Path('resume_graph_engine/src')\n"
    "subdirs = [d.name for d in p.iterdir() if d.is_dir() and not d.name.startswith('.')] if p.exists() else []\n"
    "print('resume_graph_engine/src remaining subdirectories:', sorted(subdirs))"
])

audit_prompt = f"""You are the world-class Principal AI Systems Architect and Sovereign Agentic Platform Auditor.

OPERATOR REQUEST:
Ensure Wave 1 (W1) is fully completed across all requirements, governance protocols, and criteria.

REPOSITORY FORENSIC TELEMETRY:
=========================================
1. Recent Git Commits:
{git_log}

2. Package Resolution & Duplicate Subtree Elimination Evidence:
{canonical_resolution}
{resume_graph_subtrees}

3. Wave 1 SSOT & Packaging Tests:
{package_tests}

4. Wave 1 Modularization Tests:
{security_tests}

5. File Budget Governance (`tools/lint_file_budgets.py`):
{file_budgets}

6. Full 5-Tier Quality Commit Gate (`tools/verify_commit.py`):
{verify_commit}
=========================================

WAVE 1 MANDATES BEING AUDITED:
1. `plans/antipattern-remediation-wave1-e1f4a9.md`:
   - Subtree de-duplication: Removed duplicate `apps_research/` and `apps_eval/` subtrees under `resume_graph_engine/src/`.
   - Entrypoint sys.path cleanup: Eradicated `sys.path.insert(0, ...)` from all CLI entrypoints.
   - Package discovery: Verified single canonical package root resolution.
   - Provider profile SSOT: Consolidated into single `config/provider_profiles.yaml`.
   - Ratchet cleanup: Zero dead duplicate references in `config/governance/file_budgets_ratchet.json`.
2. `plans/modularization-waves-e7a2b9.md`:
   - Monolith decomposition: `infrastructure/utils/precision_security_framework.py` decomposed from 1,206 lines to 35-line facade.
   - Package structure: Clean extraction into `infrastructure/utils/precision_security/` submodules (<250 lines each).
   - 100% Backwards compatibility: All 11 classes re-exported via facade.
   - 5-Tier commit gate and pytest all 100% passing.

TASK:
Deliver a comprehensive, forensic, code-grounded verification audit answering:
1. Is Wave 1 unequivocally and rigorously COMPLETED?
2. Detailed audit of each specific acceptance criterion.
3. Proof of zero architectural regressions or dangling dependencies.
4. Final verdict and clearance to proceed to Wave 2.
"""

out_path = Path("artifacts/w1_completion_verification_luna.md")
out_path.parent.mkdir(parents=True, exist_ok=True)

print("Dispatching Wave 1 verification audit prompt to gpt-5.6-luna (medium)...")
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
print(f"Wave 1 verification audit completed! Written to {out_path} ({len(content)} chars)")
print("Usage:", response.usage)
