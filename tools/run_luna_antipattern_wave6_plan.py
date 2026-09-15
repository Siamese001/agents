#!/usr/bin/env python3
"""Consult gpt-5.6-luna (medium) using env_agents to formulate Anti-pattern Remediation Wave 6 Plan."""

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
Protocol: docs/refactoring-wave-protocol.md (Maximum 6 waves; this is Wave 6: Cutover, Cleanup, and Continuous Architecture Governance).
Catalog: artifacts/codebase_antipatterns_luna_review.md

PROGRESS TO DATE:
- Wave 1 (Committed `cfbb3c180e`): Packaging SSOT, Subtree de-duplication (355 duplicate files removed), sys.path cleanup, config SSOT in `config/provider_profiles.yaml`.
- Wave 2 (Committed `066ec8ab99`): Typed state contracts (`ResumeRunState`, `RunPhase`, `RunCheckpoint`), `FailureKind`, `RevisionRequest`, `RecoveryBudget`.
- Wave 3 (Committed `638e7aa2f2`): Canonical pipeline routing (`canonical_dispatch.py`), structured feedback controller (`FeedbackController`, `FeedbackDecision`, `ControllerAction`).
- Wave 4 (Committed `07ba1a7902` + `20f07306ac` + `98c22ee7cf`): Canonical event envelopes (`AgentEventEnvelope`), byte-level artifact manifests (`ArtifactManifest`), storage-independent persistence ports (`StateRepository`, `EventStore`, `ArtifactStore`), SQLite/JSONL/FS adapters, replay verifier (`ReplayVerifier`). Certified PASSED by Luna.
- Wave 5 (Committed `96676793a5`): Monolith decomposition: `artifact_output` (`Emitter`, `PayloadBuilder`, `Serializer`), `sections/executive_summary` (`RepairEngine`, `Validator`, `Policy`), modular pipeline services (`SectionGenerationService`, `EvaluationService`, `ArtifactAssembler`, `ReleasePolicy`, `ModularPipelineOrchestrator`), zero concrete storage dependencies in domain services. Certified PASSED by Luna.

WAVE 6 OBJECTIVE (Final Wave of the Anti-pattern Remediation Roadmap):
Wave 6 is the final closure wave: Cutover, Cleanup, and Continuous Architecture Governance.
Its goals are:
1. Single Authoritative Release Gate Command:
   - Provide `tools/verify_release_gate.py` that consolidates Tier 1-5 checks, all 6 wave unit suites, file budgets, domain boundary linters, and emits an attestable release manifest/receipt.
2. Resolve Remaining Technical Debt & Warnings:
   - Fix Pydantic deprecation warning in `apps_research/types/research_types.py` (replace class `Config` with `ConfigDict`).
   - Reconcile `pytest.ini` vs `pyproject.toml` configuration to eliminate warning.
3. Continuous Architecture & Anti-Pattern Prevention:
   - Automated boundary and monolith prevention linter (`tools/lint_architecture_boundaries.py`):
     - Assert zero concrete storage imports (`sqlite3`, `agents.persistence.sqlite`) in domain services.
     - Enforce file budget ceilings (no production file exceeding budget, e.g. 600 lines).
     - Enforce no `sys.path.insert` or `sys.path.append` in production runtime.
     - Enforce canonical dispatch usage.
4. Comprehensive Wave 6 Test Suite:
   - `tests/unit/test_antipattern_wave6_governance_convergence.py` covering all Wave 6 invariants, release gate execution, deprecation fixes, and architectural assertions.
5. Final Attestable Seal & Closeout:
   - Forensic certification from `gpt-5.6-luna (medium)` certifying the entire 6-wave roadmap complete and production ready.

YOUR TASK:
Provide an authoritative architectural specification and implementation plan for Wave 6:
1. Exact components and files to create, modify, or verify.
2. Step-by-step implementation tasks.
3. Complete Wave 6 test specifications.
4. Acceptance criteria and verification commands under `docs/refactoring-wave-protocol.md`.
5. Output format: A complete plan document suitable for `plans/antipattern-remediation-wave6-b9e4a2.md`.
"""

print("Dispatching Wave 6 planning prompt to gpt-5.6-luna (medium)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {
            "role": "system",
            "content": "You are the Principal Architect formulating an authoritative, code-grounded Wave 6 refactoring plan under docs/refactoring-wave-protocol.md.",
        },
        {"role": "user", "content": prompt},
    ],
    reasoning_effort="medium",
    max_completion_tokens=15000,
)

content = response.choices[0].message.content
out_path = Path("plans/antipattern-remediation-wave6-b9e4a2.md")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(content, encoding="utf-8")
print(f"Wave 6 architectural plan written to {out_path} ({len(content)} chars)")
