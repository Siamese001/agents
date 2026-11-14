---
name: scope-containment
description: Restrain task scope, enforce edit vs read-only evidence boundaries, and apply retrieval caps using structural dependency analysis.
---

# Scope Containment

Keep investigation broad enough to establish empirical evidence while strictly limiting edits to the approved outcome. The always-on scope rule (`.agents/rules/scope-containment.md`) remains authoritative.

## 1. Scope Triaging & Separation

Separate touched files into three distinct categories before making any edits:
- **Edit Scope**: Explicitly approved in the wave plan, or strictly required for build/test correctness **and end-to-end Producer-Consumer-Validator pipeline contract alignment**.
- **Read-Only Evidence**: Consulted to understand contracts, interfaces, or system behavior without mutation (only after verifying the upstream producer and downstream validator contracts already satisfy the target behavior).
- **Deferred Backlog**: Tangential cleanups or future enhancements placed in backlog rather than expanding active scope.

### Producer-Consumer-Validator Coupling Exception (`INV-HOLISTIC-PIPELINE-PLANNING`)

Scope containment prohibits *unrelated* gold-plating; it must **never** be used to truncate a multi-stage pipeline refactor into a symptom-only local patch:
- When a task modifies a domain pipeline lane (e.g., `runtime/sections/`, `prompt_assembly/`, or `runtime/reasoning/`), you MUST trace one hop upstream to the **Data Producer / Allocator** (e.g., Stage-1 retrieval / Stage-2 `runtime/c0/` graph allocation & `FactAnchor` projection) and one hop downstream to the **Quality Gate / Cross-Section Validator** (e.g., Stage-4 `runtime/validators/` & `runtime/aggregation/cross_section_x2.py`).
- If a downstream lane relies on hardcoded fallback dictionaries, regex scrubs, or prose overrides because the upstream allocator projected an incomplete schema (or cloned shared facts across overview and bullet lanes), fixing the upstream allocator and unifying the downstream X2 validator thresholds are **mandatory transitive Edit Scope**, never "out-of-scope gold-plating".
- Every pipeline implementation plan must either include the coupled upstream producer and downstream validator files in `Milestones & Deliverables` or document an explicit architectural defense proving why those stages require zero changes.

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
