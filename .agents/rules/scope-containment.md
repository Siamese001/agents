---
trigger: always_on
---

# Scope Containment — Zero Blast-Radius Cap on Root-Cause Fixes, Zero Unrelated Drift

> **Scope of the current task = (a) what the user asked for + (b) files in any active plan + (c) every connected upstream producer, shared schema/config, sibling lane, consumer, downstream validator, ratchet, and test needed to resolve root-cause bugs or complete cohesive refactoring across the repository (`INV-HOLISTIC-PIPELINE-PLANNING`). There is ZERO ceiling on file count, layer span, wave count, `/boost` subagents, or `/swarm` workers. Only directional inter-subsystem and storage import boundaries plus unrequested cosmetic churn in completely unconnected code remain bounded.**

Operationalizes constitutional §18 (no hidden unrelated scope expansion) and `INV-HOLISTIC-PIPELINE-PLANNING`.

## Core Principles

1. **Mandatory Full-Ripple Inspection (Read Everything Connected)**:
   - When you make a change, you must inspect all connected upstream producers, sibling lanes, shared schemas/configs, and downstream validators/consumers by definition.
   - Reading, searching, and tracing connected files across the call graph or data flow is **NEVER capped**.
2. **Cohesive Ripple Edit Scope (Change Everything Connected)**:
   - Any upstream allocator/producer, shared contract, or downstream validator whose assumptions or thresholds are impacted by the change is part of the core change by definition and MUST be updated together.
   - Never use "scope containment" as an excuse to leave upstream producers or downstream validators out of sync with a modified lane.
3. **Block Unintentional Drift Only**:
   - **No unrelated gold-plating**: Do not touch subsystems or modules with zero call-graph or data-flow connection to the task.
   - **No unrequested cosmetic churn**: Do not reformat, rename, or refactor unconnected files just because they were viewed during investigation.
   - **One cohesive objective at a time**: Surface unrelated future ideas via `NEXT_STEP:` or backlog rather than bundling unconnected work.

## In-Scope vs Out-of-Scope

**In scope (by definition)**:
- Files the user named or that appear in the approved wave plan.
- Connected upstream producers/allocators, shared schemas/configs, sibling lanes, and downstream validators/aggregators whose contracts or thresholds are affected by the change.
- Files required for the cohesive change to compile, type-check, and pass end-to-end and unit tests.

**Out of scope (unintentional drift)**:
- Unconnected subsystems or modules with zero call-graph, schema, or data-flow coupling to the task.
- Unrequested formatting, lint, or doc touches in unconnected files.
- Mutating credentials, secrets, or canonical production state.

## Structural & Ripple Tracing Discipline

- Use **ADG (`adg_sqlite`)** and structural queries first to trace upstream/downstream dependencies, fan-in/fan-out, and layer boundaries, supplemented by unconstrained file reads and text searches as needed to verify every connected contract.
- See `.agents/skills/scope-containment/SKILL.md` for full-ripple inspection and verification procedure.

## Scope Markers

| Marker | When | Format |
|--------|------|--------|
| `SCOPE_RESET:` | Cross-turn topic shift | `SCOPE_RESET: from=<prior> to=<new> dropped=<files>` |
| `NEXT_STEP:` | Unconnected ideas (don't implement) | `NEXT_STEP:` + description |

## Forbidden Patterns

- ❌ Truncating a multi-stage pipeline change into a symptom-only local patch while ignoring coupled upstream producers or downstream validators.
- ❌ Artificially capping file reads or searches before tracing all connected callers, schemas, and validators.
- ❌ Touching unconnected subsystems or performing unrequested cosmetic cleanup in files with zero data-flow or call-graph relationship to the task.
- ❌ Renaming, moving, or deleting unconnected files outside the active ripple scope.
