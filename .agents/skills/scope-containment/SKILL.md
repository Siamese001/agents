---
name: scope-containment
description: Enforce full-ripple dependency inspection and cohesive upstream-to-downstream alignment while blocking unrelated cross-subsystem drift.
---

# Scope Containment: Full-Ripple Alignment vs. Unrelated Drift

When you make a change, you must inspect and align all connected changes across the call graph and data flow by definition. Scope containment exists solely to prevent unintentional drift into unrelated subsystems—never to cap reading, truncate impact analysis, or excuse local symptom-only patches. The always-on scope rule (`.agents/rules/scope-containment.md`) remains authoritative.

## 1. Full-Ripple Inspection & Cohesive Edit Scope

Separate touched files into three distinct categories based on call-graph and data-flow connectivity:

- **Mandatory Full-Ripple Inspection (Read Everything Connected)**:
  - Reading and tracing connected files is **NEVER capped** when analyzing impact.
  - When changing any behavior, data structure, prompt, or threshold, you MUST inspect all connected upstream producers, sibling lanes, shared schemas/configs, and downstream validators/consumers across the spine.
- **Cohesive Ripple Edit Scope (Change Everything Connected)**:
  - Any upstream producer, shared contract, sibling lane, or downstream validator whose assumptions, schemas, or thresholds are impacted by the change is part of the core change by definition and MUST be updated together in the same wave or plan (`INV-HOLISTIC-PIPELINE-PLANNING`).
  - Fixing an incomplete upstream allocator schema (`runtime/c0/`) or unifying downstream quality/cross-section validators (`runtime/validators/`, `runtime/aggregation/cross_section_x2.py`) alongside a section or prompt change (`runtime/sections/`, `prompt_assembly/`, `runtime/reasoning/`) is mandatory cohesive scope, never "out-of-scope gold-plating".
- **What Scope Containment Actually Blocks (Unintentional Drift Only)**:
  - Touching unrelated subsystems with zero call-graph or data-flow connection to the task.
  - Unrequested cosmetic, formatting, or refactor churn in unconnected files ("while I'm here" edits).
  - Mutating credentials, secrets, or canonical production state outside the approved workflow.
  - Tangential ideas with zero contract coupling to the active change (record in backlog rather than expanding scope).

## 2. Unbounded Structural & Ripple Tracing

- Use ADG SQLite structural queries (`adg_sqlite` MCP or direct queries) and targeted searches to trace full upstream/downstream fan-in, fan-out, callers, callees, and shared schema contracts.
- Never artificially cap `grep_search`, `code_search`, or file reads when tracing ripple impact across connected producers, consumers,validators, and tests.
- Follow every impacted data field, threshold, or contract edge until the full transitive boundary of the change is verified.

## 3. Boundary & Layer Linters

Verify that cohesive edits preserve unidirectional layer imports and subsystem boundaries:
```bash
.venv/bin/python tools/lint_layer_imports.py
.venv/bin/python tools/lint_architecture_boundaries.py
.venv/bin/python tools/ssot_boundary_auditor.py --json
```

## 4. Scope Verification

```bash
git diff --name-only
```

Every changed file must belong to the cohesive ripple graph of the requested outcome, its coupled producer-consumer-validator contracts, or its verification tests.
