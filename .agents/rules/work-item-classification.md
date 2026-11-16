# Work-Item Classification — Zero Bug-Deferral & Unbounded Root-Cause Refactoring

> Bugs discovered anywhere in the repository — whether single-file, cross-layer, `apps_rg` pipeline, `/boost`, or `/swarm` — are traced to their root cause and fixed immediately with zero file-count, line-count, wave-count, or blast-radius limits. Modular `<= 600`-line file budgets (`tools/lint_file_budgets.py`) and inter-subsystem import boundaries (`tools/ssot_boundary_auditor.py`) remain strictly enforced.

## Classification Matrix

| Class | Condition | Action |
|---|---|---|
| `BUG_ROOT_CAUSE` | Any bug (1 file or 50+ files, single-layer or cross-layer, `/boost` or `/swarm`, including `apps_rg`) | Trace to owning producer/contract/consumer/validator and fix end-to-end immediately; never defer bugs due to file count or blast radius |
| `REFACTOR_COHESIVE` | Cohesive `<= 600`-line package decomposition behind a facade or cross-spine contract alignment (`INV-HOLISTIC-PIPELINE-PLANNING`) | Execute across all coupled files, tests, and ratchets without artificial file-count or wave-count caps |
| `ENHANCEMENT_IN_SCOPE` | Requested feature or improvement | Implement across all impacted layers and verify end-to-end |
| `UNCONNECTED_IDEA` | Speculative future feature unrelated to any bug or requested task | Note briefly without introducing unrelated cosmetic drift |
| `PLAN_WAVE` | Multi-wave architectural design (`plans/<slug>-<6hex>.md`) | Disk-only wave plan (`INV-WAVE-PLAN-MAX-WORDS = 0`, unbounded word and wave count) |

## Cohesive Package Decomposition & Spine Refactoring (`INV-HOLISTIC-PIPELINE-PLANNING`)

Decomposing oversized files into cohesive `<= 600`-line submodules behind an intact facade (`<= 150` lines) and extracting or aligning shared domain contracts across traced upstream/downstream spine dependencies is explicitly authorized across any number of modules. Keep coupled producer+contract+consumer+validator updates unified rather than fragmenting them into symptom-only local patches.

## Core Operating Rules

1. **Found a bug -> fix its root cause now.** Never downgrade a multi-file or cross-layer bug to `BUG_DEFERRED`, `spawn_task`, or a backlog row because it touches `> 3` files or `> 20` lines.
2. **Scale `/boost` and `/swarm` freely.** Spawn parallel investigation, implementation, and verification workers as needed without artificial fan-out, file-count, or disjoint-scope blocks.
3. **Preserve modular size & architectural boundaries.** Every production `.py` module stays `<= 600` lines (outside ratcheted legacy ceilings, which only clamp downward) and respects unidirectional layer and inter-subsystem import boundaries.

## References

- `.agents/rules/apps-rg-execution-bias.md` · `.agents/rules/plan-location.md` · `.agents/rules/scope-containment.md`
