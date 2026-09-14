#!/usr/bin/env python3
"""Run Comprehensive Agentic Architecture Anti-Pattern Audit on gpt-5.6-luna (high)."""

import os
import sys
from pathlib import Path

# Load env_agents
env_file = Path("env_agents")
if not env_file.exists():
    raise FileNotFoundError("env_agents not found")

for line in env_file.read_text().splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from openai import OpenAI

client = OpenAI()

audit_prompt = """You are the Principal AI Systems & Sovereign Agentic Platform Architect reviewing this entire repository: /Users/amitayer/Git/agents.

REPOSITORY CONTEXT & ACTIVE RUNTIME TOPOLOGY:
1. Unified Entrypoint (`agents/cli.py`):
   - Commands: `python -m agents resume [run|eval|show]`, `outreach [run|eval|show]`, `e2e [--company ... --role ...]`.
   - Invariant check: In `run_e2e`, Stage 1 runs `apps_rg.__main__.main`, Stage 2 runs `apps_lic.__main__.main`. The advertised "Research" stage (`apps_research`) is completely bypassed/omitted from the unified lifecycle.
   - Dynamic path hacking (`sys.path.insert(0, ...)`) in multiple entrypoints.
2. Resume Graph Engine (`resume_graph_engine/src/apps_rg/`):
   - Recipe & Execution: `l2_recipe/modular_resume_generation.py` (1,548 lines). Orchestrates modular sections (headline, executive_summary, unify_bullets, ibm_bullets, competencies), self-consistency pools, proof judge evaluation (`REQUIRED_JUDGE_PROVIDER_KEYS`, `JudgePanelRunner`), and locked copy assembly.
   - Dual pipeline duality: Legacy/canonical dispatch (`run_canonical_apps_rg_from_cli_primitives`) vs modular R4 execution.
   - Prompt Assembly (`apps_rg/prompt_assembly/compiler.py`): Assembles prompt slots S0 through M0 (`PromptSlotPayload`, `CompiledPrompt`).
   - Judges & Gates (`apps_rg/runtime/judges/`, `apps_rg/runtime/exit/`): X1D proof judges, advisory selectors, release qualification. Notice: Gate-dependent feedback loop where X1/X1D serves as first and only sufficiency check rather than an iterative L1 -> L2 -> L1 reasoning loop.
   - Provider Layer (`apps_rg/runtime/providers/`): Multi-provider adapters (OpenAI, Anthropic, Gemini, local) with custom prompt caching and limit handling.
3. Research Engine (`apps_research/`):
   - Extensive architectural scaffolding (airlocks, reasoning, integration, domain contract, 90KB+ markdown review documents) but largely decoupled from the unified CLI lifecycle.
4. Executive Outreach Engine (`outreach_engine/src/apps_lic/`):
   - Dedicated pipeline (`pipeline/`), domain models, and custom judge system separate from `apps_rg`.
5. Governance & Configuration:
   - `config/provider_profiles.json` SSOT vs localized environment overrides (`APPS_RG_ROUTE_HMAC_SECRET`).
   - Structural AST linters in `scripts/governance/`.

TASK & SECTIONS TO AUDIT:

# 1. Full Agentic Architecture Anti-Pattern Audit
Review this entire repository as an agentic-system architect.
Identify architectural anti-patterns, hidden coupling, misplaced responsibilities, unnecessary complexity, missing feedback loops, and deviations between the intended architecture and the code that actually executes.
Do not infer architecture from README files, comments, names, or diagrams. Trace the executable runtime.
Inspect:
* user/event intake
* routing
* reasoning and planning
* prompt assembly
* retrieval/context
* tool selection
* tool execution
* orchestration
* state/memory
* policy/safety
* runtime gates
* human-in-the-loop
* multi-agent coordination
* observability
* evaluation
* final response/release

For every major runtime path:
ENTRY -> Reason -> Plan -> Retrieve -> Orchestrate -> Execute -> Observe -> Review -> Gate -> EXIT
Determine where the actual implementation differs.

Search for anti-patterns:
* reasoning mixed with execution
* policy embedded inside business logic
* tools directly calling unrelated tools
* orchestration distributed across layers
* duplicated routing logic
* implicit control flow
* bypassed runtime gates
* missing agentic feedback loops
* excessive LLM calls
* LLM calls where deterministic logic would suffice
* deterministic logic where semantic reasoning is required
* unbounded retries
* circular dependencies
* global mutable state
* duplicated abstractions
* dead frameworks
* premature abstractions
* god classes/modules
* hidden side effects
* unreachable code
* configuration drift

For every finding provide exact evidence:
| Anti-pattern | Severity | File | Symbol | Evidence | Runtime Impact | Recommended Fix |

Then produce:
### Current Architecture (ASCII)
### Target Architecture (ASCII)
### Wave-Based Refactor Plan:
Wave 0 — Characterize + protect existing behavior
Wave 1 — P0 correctness / safety defects
Wave 2 — Restore architectural boundaries
Wave 3 — Repair agentic feedback + orchestration
Wave 4 — Simplify / consolidate
Wave 5 — Performance + reliability
Wave 6 — Cleanup / deletion / documentation

Specify for each wave: files affected, symbols affected, dependencies, exact implementation objective, tests required, acceptance criteria, rollback boundary, what must NOT change.
Do not write code yet. Prioritize deletion and simplification.
Conclude Section 1 with:
Architecture Health: X/10
Agentic Integrity: X/10
Complexity Debt: X/10
Refactor Risk: X/10

---

# 2. Layer Responsibility and Boundary Audit
Audit for violations of architectural responsibility:
Reasoning = decide what should happen
Execution = perform the requested action
Orchestration = coordinate work
State = retain system/world state
Policy = constrain behavior
Evaluation = assess behavior

Trace: Who THINKS? Who ACTS? Who COORDINATES? Who REMEMBERS? Who GOVERNS? Who JUDGES?
Find: execution doing autonomous planning, reasoning doing side effects, orchestrator doing domain reasoning, state doing workflow decisions, policy executing actions, evaluation in business logic, direct cross-layer shortcuts, circular layer calls, duplicated responsibility, nominal bypassed layers.
Show CURRENT (A -> B -> C) vs TARGET (A -> X -> B -> C).
Produce Responsibility Matrix:
| Capability | Correct Owner | Current Owner | Violation? | Evidence | Severity |
Wave plan: Wave 1 (Stop dangerous boundary violations) to Wave 5 (Harden boundaries with tests).

---

# 3. Tooling + L1<->L2 Agentic Feedback Audit
Trace complete lifecycle:
Reason/Plan -> Tool proposal -> Pre-Commit -> Validate -> Execute -> Heal -> Seal -> Post-tool review -> continue/re-plan/exit
Distinguish: Execution correctness vs Semantic sufficiency vs Release readiness.
Find anti-patterns: tool output directly to exit gates, no semantic review after tool execution, tool success treated as task success, execution changing plan, reasoning bypassing execution controls, retries without re-planning, retry/heal conflated, final LLM judge used as first sufficiency check, duplicated validation, uncontrolled tool calling, unnecessary model round trips, PTC bypassing policy.
Draw actual feedback loop. Classify as A (True agentic feedback), B (Partial), C (Gate dependent), or D (Linear).
Remediation plan: Waves 1 to 5.

---

# 4. Orchestration and Control-Flow Anti-Pattern Audit
Trace sequential steps, branches, loops, retries, parallel execution, joins, dependencies, cancellation, timeout, failure propagation, re-planning, HITL, completion.
Find: orchestration in prompts, uncontrolled agent spawning, tool code coordinating workflows, business logic in DAG infra, duplicated state machines, implicit retries, unlimited loops, race conditions, nested orchestrators.
Draw real control flow in ASCII. Identify minimum orchestration primitive set required (SEQUENCE, BRANCH, PARALLEL, JOIN, RETRY, REPLAN, PAUSE, RESUME, FAIL, COMPLETE).
Wave plan: Waves 1 to 5.

---

# 5. State, Memory, and Context Anti-Pattern Audit
Inventory state types: Request, Workflow, Agent, Conversation, Working memory, Long-term memory, Retrieved context, World state, Tool observations, Caches, Persistent storage, Checkpoints.
Determine: owner, mutators, readers, lifetime, authority, conflict resolution, LLM context inclusion, retry/resume survival.
Find: global mutable state, multiple sources of truth, memory confused with workflow state, retrieved context written to long-term memory, agent-local vs orchestrator state conflicts, stale state reused, unrestricted state mutation, oversized prompts.
State ownership table:
| State | Owner | Writer(s) | Reader(s) | Lifetime | Authority | Problem |
Draw CURRENT vs TARGET STATE FLOW.
Wave plan: Waves 1 to 6.

---

# 6. Retrieval, RAG, Ranking, and Context Anti-Pattern Audit
Trace: Query understanding -> Query construction -> Candidate retrieval -> Filtering -> Ranking/reranking -> Context budgeting -> Prompt assembly -> Generation -> Grounding/citation verification.
Inventory retrievers, indexes, ranking, rerankers, embeddings, caches, context building.
Find: retrieval without clear info need, retrieval/assembly conflation, unjustified top-K, redundant passes, unbudgeted context injection, duplicate chunks, stale caches, ungrounded generation, ranking in multiple layers.
Wave plan: Waves 1 to 6.

---

# 7. Runtime Safety, Governance, Gates, and HITL Audit
Inventory input gates, policy checks, authorization, tool permissions, data-access controls, pre-execution gates, runtime validation, LLM judges, deterministic validators, HITL, exit gates, safety filters, audit logging.
Answer for each gate: What does it protect? When does it execute? Is it deterministic or semantic? Can anything bypass it? What happens on failure? Who owns remediation?
Find: policy only in prompts, advisory gates, bypasses, duplicated policy, LLM judge for deterministic rules, fail-open behavior, side effects before approval.
Wave plan: Waves 1 to 6.

---

# 8. Multi-Agent / A2A Anti-Pattern Audit
For every agent identify: Role, Goal, Inputs, Outputs, Tools, Authority, State, Dependencies, Termination condition.
Classify each agent: KEEP, MERGE, CONVERT TO FUNCTION, CONVERT TO TOOL, CONVERT TO WORKFLOW STEP, DELETE.
Draw current and proposed agent graphs.
Wave plan: Waves 1 to 6.

---

# 9. Reliability, Observability, and Evaluation Anti-Pattern Audit
Trace telemetry for request, plan, model call, prompt, retrieval, tool call/result, state transition, retry, re-plan, agent delegation, gate/judge decision, HITL, final output, failure.
Find: print/log vs structured telemetry, missing run IDs, logs with secrets, retry storms hidden, no distinction between tool failure and semantic failure, offline evals disconnected from traces, uncalibrated judges.
Wave plan: Waves 1 to 6.

---

# 10. Simplification + Final Refactor Convergence Audit
Identify everything that can be: DELETE, MERGE, INLINE, STANDARDIZE, REPLACE, SIMPLIFY.
Dependency-safe deletion map:
| Candidate | Action | Evidence | Dependents | Risk | Validation Required |

Combine all findings into FINAL IMPLEMENTATION ROADMAP:
WAVE 0: Baseline behavior + characterization tests
WAVE 1: P0 correctness / safety
WAVE 2: Core architectural boundaries
WAVE 3: Agentic feedback + orchestration
WAVE 4: State / retrieval / tool simplification
WAVE 5: Reliability + observability + evals
WAVE 6: Performance / cost
WAVE 7: Delete legacy architecture
WAVE 8: Documentation + final architecture lock

Specify for every wave:
OBJECTIVE, FILES, SYMBOLS, CHANGES, DEPENDENCIES, TESTS, ACCEPTANCE CRITERIA, ROLLBACK POINT, DELETIONS ENABLED, NEXT-WAVE PREREQUISITES.

Conclude with:
CURRENT vs TARGET (Files, Core abstractions, Agents, Tool paths, State systems, Orchestration systems, Policy systems)
and NET CHANGE (Code removed, Abstractions removed, Duplicate paths removed, Risk reduced, Complexity reduced).
"""

out_path = Path("artifacts/agentic_architecture_anti_pattern_audit_luna.md")
out_path.parent.mkdir(parents=True, exist_ok=True)

print("Dispatching comprehensive 10-part audit prompt to gpt-5.6-luna (high)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {
            "role": "system",
            "content": (
                "You are the world-class Principal AI Systems Architect and Sovereign Agentic Platform Auditor. "
                "Deliver a rigorous, exhaustive, code-grounded forensic architectural audit and wave-based refactoring plan."
            ),
        },
        {"role": "user", "content": audit_prompt},
    ],
    reasoning_effort="high",
    max_completion_tokens=40000,
)

review_text = response.choices[0].message.content
out_path.write_text(review_text, encoding="utf-8")
print(f"Audit completed successfully! Written to {out_path} ({len(review_text)} chars)")
print("Usage:", response.usage)
