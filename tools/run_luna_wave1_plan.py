#!/usr/bin/env python3
"""Consult gpt-5.6-luna (medium) using env_agents to formulate Wave 1 Execution Plan."""

import os
import sys
from pathlib import Path

# Load credentials from env_agents
env_file = Path("env_agents")
if not env_file.exists():
    raise FileNotFoundError("env_agents not found")

for line in env_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from openai import OpenAI

client = OpenAI()

prompt = """You are the Principal AI Systems & Sovereign Agentic Platform Architect.
Repository: /Users/amitayer/Git/agents on branch `refactor/antipattern-remediation-waves`.
Protocol: docs/refactoring-wave-protocol.md (One wave at a time, max 6 waves).

CONTEXT:
We have just completed the architectural anti-pattern audit (artifacts/codebase_antipatterns_luna_review.md).
The operator gave the instruction:
"run plan wave by wave on new branch using env_agents gpt-5.6-luna (medium)"

Wave 1 Focus: Packaging, Subtree De-duplication & Configuration SSOT Stabilization.
Confirmed facts:
1. Subtree Duplication:
   - `resume_graph_engine/src/apps_research/` is an exact duplicate of `apps_research/`
   - `resume_graph_engine/src/apps_eval/` is an exact duplicate of `apps_eval/`
   - `resume_graph_engine/src/apps_model_telemetry/` is an exact duplicate of `apps_model_telemetry/`
2. Packaging & Path Hacking:
   - Root `pyproject.toml` defines `where = ["."]`, including `agents*`, `resume_graph_engine*`, `outreach_engine*`, `apps_eval*`, `apps_research*`, `apps_model_telemetry*`.
   - Entrypoints use `sys.path.insert(0, ...)` to point to `resume_graph_engine/src`, causing dual import resolution.
3. Configuration SSOT:
   - Provider profiles in `config/provider_profiles.yaml` vs `resume_graph_engine/src/apps_rg/config/provider_profiles.yaml`.

YOUR TASK:
Formulate the authoritative implementation plan for **Wave 1**:
1. Problem Statement & Invariants.
2. Exact files to modify, delete, or create:
   - How to safely de-duplicate the subtrees under `resume_graph_engine/src/` (e.g. converting `resume_graph_engine/src/apps_research` to proxy re-export packages or removing them while updating references, ensuring zero broken imports).
   - How to normalize package paths and remove `sys.path.insert` from key entrypoints (`resume_engine/__main__.py`, `outreach_engine/__main__.py`, `resume_graph_engine/__main__.py`).
   - Configuration unification.
3. Acceptance Criteria & Verification Strategy:
   - Unit tests to verify package resolution.
   - Preserving 100% green pass on `tools/verify_commit.py` and pytest.
4. Output format: A complete plan document suitable for saving to `plans/antipattern-remediation-wave1-<hex>.md`.
"""

print("Dispatching Wave 1 planning prompt to gpt-5.6-luna (medium)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {"role": "system", "content": "You are the Principal Architect formulating an authoritative, code-grounded Wave 1 refactoring plan under docs/refactoring-wave-protocol.md."},
        {"role": "user", "content": prompt}
    ],
    reasoning_effort="medium",
    max_completion_tokens=15000,
)

content = response.choices[0].message.content
out_path = Path("plans/antipattern-remediation-wave1-e1f4a9.md")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(content, encoding="utf-8")
print(f"Wave 1 plan written to {out_path} ({len(content)} chars)")
