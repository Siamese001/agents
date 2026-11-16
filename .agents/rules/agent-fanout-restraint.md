<!-- Trigger: model_decision (load when orchestrating sub-agents / workflows). -->

# Agent, `/boost`, & `/swarm` Fan-Out — Unconstrained Root-Cause & Parallel Execution

> **Parallel `/boost` and `/swarm` fan-out has zero artificial ceiling.** Spin up as many investigation, implementation, refactoring, and verification workers as the task benefits from across any number of files, packages, or waves.

## Core Principles

1. **Zero Fan-Out or Scope Throttle on `/boost` and `/swarm`**:
   - Parallel workers may investigate, trace root causes, decompose `<= 600`-line modules behind facades, align shared contracts, and run impacted test suites concurrently without mandatory 10-field contract blocks or disjoint-file write lockouts.
2. **Spend Fan-Out on Real Leverage**:
   - Use parallel workers freely for multi-root bug hunting, cross-subsystem contract alignment, large monolith decomposition, adversarial verification, and independent test execution.
   - Avoid wasting turns re-running identical read-only inventory queries whose exact output is already in context.
3. **Preserve Modular Size & Architectural Boundaries**:
   - Every worker must keep production `.py` files `<= 600` lines (`<= 150` lines for pure re-export facades) and respect unidirectional layer and inter-subsystem import boundaries (`tools/lint_file_budgets.py`, `tools/ssot_boundary_auditor.py`).

## References

- `.agents/rules/001-runtime-seam-execution.md`
- `.agents/rules/scope-containment.md`
- `.agents/rules/work-item-classification.md`
