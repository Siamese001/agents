#!/usr/bin/env python3
"""Consult gpt-5.6-luna (medium) using env_agents to formulate Wave 5 Execution Plan."""

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
Current Stage: Wave 5 (Wave 1, 2, 3, 4 are fully completed, committed, and verified as PASSED).

OPERATOR INSTRUCTION:
"W5
Gpt-5.6-luna (medium)
env_agents"

CONTEXT & EXISTING FOUNDATIONS:
- Wave 1 committed: Eliminated duplicate subtrees, normalized packaging, unified configuration SSOT.
- Wave 2 committed: Formalized typed state contracts (`ResumeRunState`, `RunPhase`, `RunCheckpoint`), `FailureKind`, `RevisionRequest`, independent `RecoveryBudget`.
- Wave 3 committed: Canonical pipeline routing (`canonical_dispatch.py`), structured agentic feedback controller (`FeedbackController`, `FeedbackDecision`, `ControllerAction`), deterministic schema repair vs. semantic revision.
- Wave 4 committed: Canonical event envelopes (`AgentEventEnvelope`), artifact manifests with SHA-256 digests (`ArtifactManifest`), decoupled persistence ports (`StateRepository`, `EventStore`, `ArtifactStore`), reference SQLite and JSONL adapters, deterministic replay verifier (`ReplayVerifier`).
- Anti-Pattern Review Roadmap for Wave 5 (from `artifacts/codebase_antipatterns_luna_review.md`):
  * "Wave 5 — Monolith Decomposition and Domain Boundary Enforcement"
  * Objectives:
    - Reduce large modules incrementally.
    - Establish durable code-health constraints.
    - Target highest priority oversized modules identified in the review:
      1. `mandatory_run_outputs.py` (500+ lines of monolithic artifact emission)
      2. `bare_pipeline.py` (2,448 lines of legacy monolithic generation)
      3. `executive_summary_voice_repair.py` (2,582 lines of manual regex patching)
      4. Decouple domain orchestration from concrete lane monoliths into cleanly separated modular stages (`SectionGenerationService`, `EvaluationService`, `ArtifactAssembler`, `ReleasePolicy`).
    - Enforce file budget ratchets and layer boundary linters.

YOUR TASK:
Formulate the authoritative implementation plan for **Wave 5**:
1. Problem Statement & Invariants.
2. Concrete Scope & Target Files (What gets decomposed, extracted, or modified).
3. Decomposition Architecture & Modular Service Boundaries.
4. Step-by-Step Implementation Waves.
5. Invariant & Unit Tests (`tests/unit/test_antipattern_wave5_monolith_decomposition.py`).
6. Exit Gates & Acceptance Criteria.

Provide the response in crisp, clean GitHub Flavored Markdown ready to be saved as the official plan and implementation plan.
"""

response = client.chat.completions.create(
    model="gpt-5.6-luna",
    reasoning_effort="medium",
    messages=[
        {"role": "system", "content": "You are the Principal AI Systems Architect creating the official Wave 5 execution plan."},
        {"role": "user", "content": prompt},
    ],
)

content = response.choices[0].message.content
print(content[:500])

plan_file = Path("plans/antipattern-remediation-wave5-e8f2a1.md")
plan_file.write_text(content, encoding="utf-8")
print(f"\nPlan written to {plan_file}")
