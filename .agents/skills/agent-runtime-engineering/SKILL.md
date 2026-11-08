---
name: agent-runtime-engineering
description: Design production agent runtimes, decision loops, planners, retries, and termination policies. Use for executable runtime behavior, supervisor loops, or control-flow diagnostics.
---

# Agent Runtime Engineering

Design runtime behavior explicitly. An agent is not production-ready because it can call an LLM and tools.

## Required workflow

1. Define the agent goal, authority, boundaries, inputs, outputs, and accountable owner.
2. Decide what is deterministic workflow logic and what genuinely requires agentic decision-making.
3. Choose the runtime pattern from `references/runtime-patterns.md`.
4. Define state ownership, action selection, tool/delegation contracts, observation, evaluation, and termination.
5. Define budgets for time, tokens/model calls, tool calls, cost, and delegation depth where relevant.
6. Define retries, backoff, idempotency, cancellation, timeout, partial completion, and compensation.
7. Define human approval/intervention points for material risk.
8. Produce `runtime-design.json` using `references/design-contract.md`.
9. Validate with `scripts/validate_runtime_design.py`.
10. Only then generate framework-specific code. Keep core runtime semantics independent of any one agent SDK.

## Core loop

Model the runtime as:

Goal -> Observe -> Decide -> Act/Delegate -> Observe result -> Evaluate -> Continue, Escalate, or Stop

Do not force every task through a free-running loop. Use bounded workflows when the process is known.

## Pattern selection

Prefer deterministic orchestration when sequence and decisions are known.

Use supervisor/worker when one dynamic coordinator should decompose and assign work.

Use planner/executor when plan quality and execution can be separated and evaluated.

Use peer collaboration when multiple independently useful agents need dynamic delegation or negotiation.

Use parallel specialists only when outputs are truly parallelizable and merge semantics are defined.

## Delegation contract

Every delegation must define:
- goal and expected deliverable;
- allowed context and data;
- authority and tool scope;
- completion criteria;
- timeout/budget;
- error and escalation behavior;
- correlation/task identity;
- whether sub-delegation is allowed.

## Prompt Caching & Stable Prefix Pattern

When constructing agent loops or delegating to sub-agents, always use the **Stable Prefix Pattern** to maximize OpenAI prefix caching:
1. System instructions, schemas, and static context must be placed at the beginning of the prompt array and remain absolutely immutable across turns.
2. Dynamic or volatile context (like timestamps or variable memory) must be appended at the end of the array.
3. Tool schemas must remain stable during execution; dynamically hot-swapping tools between turns breaks the prefix cache.

## Termination and loop safety

Define success, failure, escalation, and maximum-effort termination. Prevent unbounded reflection or delegation loops.

Require a stop condition based on observable state, not "until satisfied" alone.

## Output contract

Produce:
- `runtime-design.json`;
- runtime state machine or sequence diagram;
- pseudocode or implementation skeleton;
- failure/resilience table;
- framework-specific code only after semantics are locked.

## Blocking failures

- No explicit termination condition.
- Agent can delegate recursively without depth/budget control.
- Non-idempotent actions can be retried blindly.
- Human approval is described but no enforcement point exists.
- Deterministic workflow steps are mislabeled as autonomous agents.
- Shared mutable state has no owner or concurrency policy.
- Failure handling depends on generic "try again" behavior.
