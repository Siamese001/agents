---
trigger: always_on
---

# Work-Item Classification — Zero Bug-Deferral & Unbounded Root-Cause Refactoring

> Bugs discovered anywhere in the repository — whether single-file, cross-layer, `apps_rg` pipeline, `/boost`, or `/swarm` — are traced to their root cause and fixed immediately with zero file-count, line-count, wave-count, or blast-radius limits. Directional inter-subsystem and storage import boundaries (`tools/ssot_boundary_auditor.py`, `tools/lint_architecture_boundaries.py`) remain strictly enforced with zero file-size or line-ratchet caps (`INV-BUDGET-FILE-LINES = 0`).

## Classification Matrix

| Class | Condition | Action |
|---|---|---|
| `BUG_ROOT_CAUSE` | Any bug (1 file or 50+ files, single-layer or cross-layer, `/boost` or `/swarm`, including `apps_rg`) | Trace to owning producer/contract/consumer/validator and fix end-to-end immediately; never defer bugs due to file count or blast radius |
| `REFACTOR_COHESIVE` | Cohesive package decomposition behind a facade or cross-spine contract alignment (`INV-HOLISTIC-PIPELINE-PLANNING`) | Execute across all coupled files, tests, and ratchets without artificial file-count or wave-count caps |
| `ENHANCEMENT_IN_SCOPE` | Requested feature or improvement | Implement across all impacted layers and verify end-to-end |
| `UNCONNECTED_IDEA` | Speculative future feature unrelated to any bug or requested task | Note briefly without introducing unrelated cosmetic drift |
| `PLAN_WAVE` | Multi-wave architectural design (`plans/<slug>-<6hex>.md`) | Disk-only wave plan (`INV-WAVE-PLAN-MAX-WORDS = 0`, unbounded word and wave count) |

## Cohesive Package Decomposition & Spine Refactoring (`INV-HOLISTIC-PIPELINE-PLANNING`)

Decomposing oversized files into cohesive submodules behind an intact facade and extracting or aligning shared domain contracts across traced upstream/downstream spine dependencies is explicitly authorized across any number of modules. Keep coupled producer+contract+consumer+validator updates unified rather than fragmenting them into symptom-only local patches.

## Core Operating Rules

1. **Found a bug -> fix its root cause now.** Never defer a multi-file or cross-layer bug to `spawn_task` or a backlog row regardless of file count or line count.
2. **Scale `/boost` and `/swarm` freely.** Spawn parallel investigation, implementation, and verification workers as needed without artificial fan-out, file-count, or disjoint-scope blocks.
3. **Preserve directional architectural boundaries.** Respect unidirectional layer, storage-interface, and inter-subsystem import boundaries across all touched modules.
4. **Delete and Replace Before Slicing Spaghetti (`INV-DELETE-BEFORE-DECOMPOSE`).** Never slice bloated, fighting legacy code into dozens of micro-files behind facades just to satisfy line budgets (which preserves complexity and creates state-sync/closure bugs). When a single bounded output (such as a 70-word summary section) accumulates disproportionate private complexity (`> 1,500` LOC or `> 10` private modules), replace it cleanly behind its external boundary contract and delete all verified zero-caller private legacy files.

## References

- `.agents/rules/apps-rg-execution-bias.md` · `.agents/rules/plan-location.md` · `.agents/rules/scope-containment.md`
