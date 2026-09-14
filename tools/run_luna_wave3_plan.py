#!/usr/bin/env python3
"""Consult gpt-5.6-luna (medium) using env_agents to formulate Wave 3 Execution Plan."""

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
Current Stage: Wave 3 (Wave 1 and Wave 2 completed and verified).

OPERATOR INSTRUCTION:
"W3
Gpt-5.6-luna (medium)
env_agents"

CONTEXT & EXISTING FOUNDATIONS:
- Wave 1: Eliminated duplicate subtrees, normalized packaging, unified configuration SSOT.
- Wave 2: Formalized typed state contracts (`ResumeRunState`, `RunPhase`, `RunCheckpoint`), `FailureKind`, `RevisionRequest`, and independent `RecoveryBudget`.
- Existing Orchestration in `agents/orchestration/`:
  * `state_contracts.py`, `failure_taxonomy.py`, `primitives.py`, `state_machine.py`, `engine.py`.
- In `resume_graph_engine/src/apps_rg/`:
  * `bare_pipeline.py` (2,448 lines) vs `modular_resume_generation.py` (decoupled services: `ResumeWorkflowCoordinator`, `SectionGenerationService`, `EvaluationService`, `ReleasePolicy`, `ArtifactAssembler`) vs `canonical_dispatch.py`.
  * `executive_summary_voice_repair.py` (2,582 lines of manual regex patching).

WAVE 3 OBJECTIVES (from approved roadmap):
1. Single Canonical Pipeline Routing:
   - Designate `ResumeWorkflowCoordinator` / `modular_resume_generation` as the authoritative resume generation engine.
   - Establish explicit routing adapter ensuring CLI and downstream invocations converge on this canonical path.
2. Structured Agentic Feedback Controller:
   - Create `agents/orchestration/feedback_controller.py`:
     * Consumes validation results from `EvaluationService` or section validators.
     * Maps failures using `FailureKind` and `derive_recovery_action`.
     * Formulates typed `RevisionRequest` with constraint details and allowed actions.
     * Manages bounded revision turns respecting Wave 2 `RecoveryBudget` (rejecting unbounded retry loops).
     * Distinguishes deterministic normalization from semantic model re-prompting.
3. Unit & Invariant Tests:
   - `tests/unit/test_antipattern_wave3_pipeline_and_feedback.py`.
4. Zero Regressions:
   - Ensure 100% green pass on `pytest` and `tools/verify_commit.py`.

YOUR TASK:
Formulate the authoritative implementation plan for **Wave 3**:
1. Problem Statement & Invariants.
2. Exact files to create or modify:
   - New `agents/orchestration/feedback_controller.py`.
   - Wiring with `agents/orchestration/`.
   - Pipeline routing alignment in `resume_graph_engine/src/apps_rg/`.
3. Step-by-step implementation procedure.
4. Acceptance Criteria & Verification Plan.
5. Save the plan document to `plans/antipattern-remediation-wave3-c4e9b2.md`.
"""

print("Dispatching Wave 3 planning prompt to gpt-5.6-luna (medium)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {"role": "system", "content": "You are the Principal Architect formulating an authoritative, code-grounded Wave 3 refactoring plan under docs/refactoring-wave-protocol.md."},
        {"role": "user", "content": prompt}
    ],
    reasoning_effort="medium",
    max_completion_tokens=15000,
)

content = response.choices[0].message.content
out_path = Path("plans/antipattern-remediation-wave3-c4e9b2.md")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(content, encoding="utf-8")
print(f"Wave 3 plan written to {out_path} ({len(content)} chars)")
