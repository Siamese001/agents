---
name: scope-containment
description: Restrain task scope, enforce edit vs read-only evidence boundaries, and apply retrieval caps using structural dependency analysis.
---

# Scope Containment

Keep investigation broad enough to establish empirical evidence while strictly limiting edits to the approved outcome. The always-on scope rule (`.agents/rules/scope-containment.md`) remains authoritative.

## 1. Scope Triaging & Separation

Separate touched files into three distinct categories before making any edits:
- **Edit Scope**: Explicitly approved in the wave plan, or strictly required for build/test correctness.
- **Read-Only Evidence**: Consulted to understand contracts, interfaces, or system behavior without mutation.
- **Deferred Backlog**: Tangential cleanups or future enhancements placed in backlog rather than expanding active scope.

## 2. Structural Retrieval Discipline

- Use ADG SQLite structural queries (`adg_sqlite` MCP or direct queries) for dependencies, callers, fan-in/fan-out, and layer boundaries before resorting to broad text searches.
- **Per-Turn Retrieval Caps**:
  - `grep_search` + `code_search` <= 3 per response.
  - File reads <= 10 per response.
- Retain exact paths and symbol extracts; discard large raw retrieval blocks after extracting required evidence.
- Halt retrieval broadening as soon as options converge or sufficient proof is gathered.

## 3. Boundary & Layer Linters

Verify that proposed or completed edits preserve architectural boundaries:
```bash
.venv/bin/python tools/lint_layer_imports.py
.venv/bin/python tools/lint_architecture_boundaries.py
.venv/bin/python tools/ssot_boundary_auditor.py --json
```

## 4. Scope Verification

```bash
git diff --name-only
```

Every changed file must have a direct outcome, build, test, or graph-backed justification for being in scope.
