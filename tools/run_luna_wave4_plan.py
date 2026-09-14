#!/usr/bin/env python3
"""Consult gpt-5.6-luna (medium) using env_agents to formulate Wave 4 Execution Plan."""

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
Current Stage: Wave 4 (Wave 1, Wave 2, and Wave 3 are fully completed, committed, and verified).

OPERATOR INSTRUCTION:
"W4
Gpt-5.6-luna (medium)
env_agents"

CONTEXT & EXISTING FOUNDATIONS:
- Wave 1 committed: Eliminated duplicate subtrees, normalized packaging, unified configuration SSOT.
- Wave 2 committed: Formalized typed state contracts (`ResumeRunState`, `RunPhase`, `RunCheckpoint`), `FailureKind`, `RevisionRequest`, independent `RecoveryBudget`.
- Wave 3 committed: Canonical pipeline routing (`canonical_dispatch.py`), structured agentic feedback controller (`FeedbackController`, `FeedbackDecision`, `ControllerAction`), deterministic schema repair vs. semantic revision.
- Current Telemetry in `agents/telemetry/`:
  * `events.py` (`TelemetryEventType`, `TelemetryEvent`, `TelemetryEmitter`)
  * `correlation.py` (`CorrelationContext`)
  * `calibration.py` (`EvaluationTelemetry`, `JudgeCalibrator`)
- Anti-Pattern Review Roadmap for Wave 4 (from `artifacts/codebase_antipatterns_luna_review.md`):
  * "Wave 4 — Observability, Replay, and Persistence Boundaries"
  * Objectives: Make every run explainable and replayable; separate domain logic from SQLite, telemetry, and external persistence adapters.
  * Activities:
    1. Introduce canonical agent event types & envelopes (e.g. `PHASE_TRANSITION`, `FEEDBACK_DECISION`, `ARTIFACT_MANIFEST`, `CHECKPOINT_SAVED`).
    2. Model request/response provenance & metadata without logging secrets.
    3. Input/output SHA-256 digests and tamper-evident artifact manifests (`ArtifactManifest`, `ArtifactDigest`).
    4. Define clean repository/store ports/interfaces (`IStateRepository`, `IEventStore`, `IArtifactStore`) and SQLite/JSONL implementations, isolating persistence from domain orchestrators.
    5. Deterministic replay contract from recorded run context/checkpoints.

YOUR TASK:
Formulate the authoritative implementation plan for **Wave 4**:
1. Problem Statement & Invariants.
2. Concrete Scope & Target Files (What gets created/modified).
3. Data Contracts & Architecture:
   - Event types (`PHASE_TRANSITION`, `FEEDBACK_DECISION`, `ARTIFACT_COMMITTED`, `CHECKPOINT_STORED`).
   - Artifact provenance manifest (`ArtifactManifest` with SHA-256 digests).
   - Clean persistence ports and storage backends (`StateRepository`, `EventStore`).
   - Deterministic replay verification mechanism.
4. Step-by-Step Implementation Waves.
5. Invariant & Unit Tests (`tests/unit/test_antipattern_wave4_observability_persistence.py`).
6. Exit Gates & Acceptance Criteria.

Provide the response in crisp, clean GitHub Flavored Markdown ready to be saved as the official plan and implementation plan.
"""

response = client.chat.completions.create(
    model="gpt-5.6-luna",
    reasoning_effort="medium",
    messages=[
        {"role": "system", "content": "You are the Principal AI Systems Architect creating the official Wave 4 execution plan."},
        {"role": "user", "content": prompt},
    ],
)

content = response.choices[0].message.content
print(content[:500])

plan_file = Path("plans/antipattern-remediation-wave4-d5e1f8.md")
plan_file.write_text(content, encoding="utf-8")
print(f"\nPlan written to {plan_file}")
