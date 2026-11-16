---
trigger: model_decision
---

# Agent, `/boost`, & `/swarm` Fan-Out — Unconstrained Root-Cause & Parallel Execution

> **Parallel `/boost` and `/swarm` fan-out has zero artificial ceiling.** Spin up as many investigation, implementation, refactoring, and verification workers as the task benefits from across any number of files, packages, or waves.

## Core Principles

1. **Zero Fan-Out or Scope Throttle on `/boost` and `/swarm`**:
   - Parallel workers may investigate, trace root causes, decompose cohesive modules behind facades, align shared contracts, and run impacted test suites concurrently without mandatory 10-field contract blocks, file-size ceilings (`INV-BUDGET-FILE-LINES = 0`), or disjoint-file write lockouts.
2. **Spend Fan-Out on Real Leverage**:
   - Use parallel workers freely for multi-root bug hunting, cross-subsystem contract alignment, large monolith decomposition, adversarial verification, and independent test execution.
   - Avoid wasting turns re-running identical read-only inventory queries whose exact output is already in context.
3. **Preserve Directional Architectural Boundaries**:
   - Every worker must respect unidirectional layer, storage-interface, and inter-subsystem import boundaries (`tools/lint_architecture_boundaries.py`, `tools/ssot_boundary_auditor.py`).

## References

- `.agents/rules/001-runtime-seam-execution.md`
- `.agents/rules/scope-containment.md`
- `.agents/rules/work-item-classification.md`
