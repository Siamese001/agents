#!/usr/bin/env python3
"""Consult gpt-5.6-luna (medium) using env_agents to formulate Wave 2 Execution Plan."""

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
Current Stage: Wave 2 (Wave 1 completed and verified).

OPERATOR INSTRUCTION:
"W2
Gpt-5.6-luna (medium)
env_agents"

CONTEXT & EXISTING FOUNDATIONS:
- In `agents/orchestration/`:
  * `primitives.py`: `OrchestrationPrimitive`, `WorkflowStatus`, `ExecutionRetry`, `SemanticRepair`, `Replan`.
  * `state_machine.py`: `WorkflowStateMachine`, transition checks.
  * `engine.py`: `WorkflowExecutionEngine`.
- In `agents/context/`:
  * `provenance.py`: `ContextItem`, `ContextSnapshot`, SHA-256 digests.
  * `budgeting.py`: `TokenBudget`, priority allocations.
- In `agents/gateway/`:
  * `model_gateway.py`: `ModelCapabilityGateway`.

WAVE 2 OBJECTIVES (from approved roadmap):
1. Formalize Typed State Contracts (`ResumeRunState`, `RunPhase`, transition validations, immutable checkpoints).
2. Establish Authoritative Failure Taxonomy & Error Classes:
   `FailureKind` (`TRANSPORT`, `PROVIDER`, `SCHEMA`, `DETERMINISTIC_QUALITY`, `FACTUAL_CONFLICT`, `PLANNING`, `POLICY`).
3. Define Structured Revision & Diagnostic Contracts:
   `RevisionRequest` (failure_kind, failed_constraints, evidence, allowed_actions, attempt_count, max_revisions).
4. Unify Bounded Recovery Budgets:
   Distinguish and enforce:
   - Technical Transport Retry (transient 5xx/rate-limit, exponential backoff).
   - Schema / Deterministic Repair (format correction, missing field fill).
   - Semantic Revision Turn (model self-correction via RevisionRequest).
   - Cognitive Replan (strategy shift).
5. Contract & Invariant Tests:
   Add comprehensive unit test suite in `tests/unit/test_antipattern_wave2_state_contracts.py`.
6. Zero Regressions: Ensure 100% green on `tools/verify_commit.py` and `pytest`.

YOUR TASK:
Formulate the authoritative implementation plan for **Wave 2**:
1. Problem Statement & Invariants.
2. Exact files to create or modify:
   - New contracts module (e.g. `agents/orchestration/state_contracts.py` or `agents/orchestration/taxonomy.py`).
   - Integration into `agents/orchestration/` and public exports.
3. Step-by-step implementation procedure.
4. Acceptance Criteria & Verification Plan.
5. Save the plan document to `plans/antipattern-remediation-wave2-7f3a1b.md`.
"""

print("Dispatching Wave 2 planning prompt to gpt-5.6-luna (medium)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {"role": "system", "content": "You are the Principal Architect formulating an authoritative, code-grounded Wave 2 refactoring plan under docs/refactoring-wave-protocol.md."},
        {"role": "user", "content": prompt}
    ],
    reasoning_effort="medium",
    max_completion_tokens=15000,
)

content = response.choices[0].message.content
out_path = Path("plans/antipattern-remediation-wave2-7f3a1b.md")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(content, encoding="utf-8")
print(f"Wave 2 plan written to {out_path} ({len(content)} chars)")
