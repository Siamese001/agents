# Wave Refactoring & Subtraction-First Protocol

## Role

Operate as a convergence-driven, **subtraction-first** engineering system in which:

- Every root-cause bug discovered before or during refactoring is traced across coupled upstream producers, shared domain contracts, consumers, validators, and tests without artificial file-count, subsystem-span, or blast-radius caps (`INV-REFACTOR-EXTENT-UNBOUNDED`).
- Refactoring must **reduce net complexity** rather than slicing bloated spaghetti into dozens of micro-files behind facades (`INV-DELETE-BEFORE-DECOMPOSE`).
- Directional inter-subsystem, storage-interface, and unidirectional layer boundaries (`tools/ssot_boundary_auditor.py`, `tools/lint_architecture_boundaries.py`, `tools/lint_layer_imports.py`) remain strictly enforced, with zero artificial file-size or line-ratchet ceilings (`INV-BUDGET-FILE-LINES = 0`).

---

## 1. Primary Objective & Multi-Case Generalization

Before proposing any refactoring work, define:

1. The specific problem being solved and its measurable failure evidence.
2. The observable end-state and real unmocked verification criteria (including pinned human-rejected negative controls).
3. The external caller contract that must remain stable (public interfaces used by sibling subsystems/lanes).
4. The dead internal layers, mutators, or duplicate rules to be **deleted** (not wrapped).

Never alter global pipeline structures based on a single target case/JD without validating across a multi-domain benchmark (`INV-MULTI-JD-NO-WHIPLASH`). Never fabricate or backfill source-of-truth data to clear a failing gate (`INV-FACT-GRAPH-NO-AGENT-SYNTHESIS`).

---

## 2. Subtraction-First & Complexity Proportionality (`INV-DELETE-BEFORE-DECOMPOSE`)

- **Prefer deletion and clean replacement over additive patching**: When a bounded component (such as a 70-word summary generator) accumulates disproportionate private complexity (`> 1,500` LOC or `> 10` private modules), replace it cleanly behind its external boundary facade and delete all verified zero-caller private legacy files.
- **No regex-on-regex / post-LLM mutator stacking (`INV-NO-POST-LLM-PROSE-MUTATORS`)**: Fix LLM output defects upstream (verified facts, concise prompt, or a single bounded fresh-turn judge-guided rewrite loop), never by stacking post-hoc text mutators.
- **Cohesive factoring vs. spaghetti slicing**: Cohesive module separation behind a stable facade and shared domain contracts (`INV-HOLISTIC-PIPELINE-PLANNING`) are authorized ONLY when they simplify ownership and preserve clear boundaries, never as mechanical splitting of tangled state into micro-files; avoid unrelated drift in uncoupled modules.

---

## 3. Sequential & Parallel Sharded Execution (`/boost` & `/swarm`)

Waves may execute sequentially (`Wave 1`, `Wave 2`, ...) or as parallel fork-join `/boost` and `/swarm` shards (`Wave 2A`, `Wave 2B`, ... with `Depends On:` and optional `shard-manifest` blocks):

- Align coupled upstream producers, shared domain contracts, and downstream validators cohesively across any number of files while preserving external caller contracts and excluding unrelated drift.
- Sharded `/swarm` workers qualify branches via `tools/pr_governance.py shard-ready` and assemble via `tools/pr_governance.py train --wave <N> --shards ...`.
- Every wave must clear real unmocked verification (`tools/audit_eval_construct_validity.py --verify-strict --include-e2e-pin`, `tools/run_diff_scoped_eval_shield.py`) before marking complete.

---

## 4. Wave Completion Gate (Outcome Truth Over Process Ceremony)

A wave is complete ONLY when:

1. Declared acceptance criteria pass against real unmocked behavior (not mocked unit tests alone).
2. Both positive recall and negative-control precision (`INV-BILATERAL-RECALL-PRECISION-GATE`, `INV-JUDGE-NEGATIVE-CONTROL-GOLDEN`) are independently observed.
3. Dead legacy files targeted for retirement are actually deleted with zero broken imports.
4. All required Tier 1 (`tools/verify_commit.py`) and Tier 2 AI-SDLC (`tools/verify_main_readiness.py`) stages pass cleanly.
