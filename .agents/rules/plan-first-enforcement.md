---
trigger: model_decision
---

# Plan-First Enforcement (native plan mode)

> **Renamed W2.** Formerly `sequential-thinking-enforcement.md`
> — that name is a historical reference; the rule
> was goal-seeked to reimplement its *intent*. The real scope is **plan-first reasoning**: on T2/T3
> work, decompose and gather evidence, and make **no edits before the plan is approved** (native plan
> mode). Renamed to match scope.

> Superseded W2 (ADR-094): the `SR_INTAKE / SR_PLAN /
> SR_APPROVAL / SR_EXECUTE / SR_VERIFY` marker packet is retired. Native **plan mode** is the
> "no edits before approval" contract it emulated.

## When plan mode applies vs. immediate root-cause execution

- **Root-Cause Bug Fixes, `/boost`, & `/swarm` (Execute Directly Without File-Count Limits)**: Whenever a bug is discovered or `/boost` / `/swarm` is invoked, trace the defect across all connected layers and fix every impacted producer, shared contract, consumer, validator, and test immediately with zero file-count, line-count, or blast-radius barriers (preserving directional inter-subsystem and storage import boundaries).
- **Open-Ended Architecture & Design**: When the operator requests `/plan` or open-ended architectural design with genuine ambiguity ($\Delta \le 20\%$), gather evidence, structure the wave plan, and resolve ambiguity before editing.

## Contract

- Direct user instructions (`implement`, `fix`, `/boost`, `/swarm`, `/learn`, `refactor`, `commit`, `promote`) authorize full end-to-end execution across all connected files, contracts, ratchets, and tests needed to solve the root cause cleanly.
- Do **not** ask for separate "design approval", "implementation approval", "refactor approval", or ">10-file blast-radius approval" once execution is authorized, unless genuine high-level product ambiguity ($\Delta \le 20\%$) or a destructive external action arises.

## Wave-Based Implementation Plan Standard (Supersedes Status Table)

The legacy mandatory 4-column Status Table in markdown plan files is retired. Implementation plans (`implementation_plan.md` or `plans/*.md`) are governed by [.agents/rules/wave-progression.md](wave-progression.md).

- **Structure**: Plans must be decomposed into sequential numbered waves (`## Wave 1: <Title>`, `## Wave 2: <Title>`) with 4 mandatory subsections per wave:
  1. `### Objective & Scope`
  2. `### Milestones & Deliverables` (`[NEW]`, `[MODIFY]`, `[DELETE]`)
  3. `### Acceptance Criteria`
  4. `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`)
- **Word & Wave Budget**: Unbounded (`INV-WAVE-PLAN-MAX-WORDS = 0`); scale waves and `/boost` / `/swarm` shards freely to match the full architectural scope.
- **Status Tracking & Reporting**: Wave status is tracked durably within repository artifacts and persistent ledgers. Ordinary conversational chat outputs must NOT dump all-wave status tables into chat (target ~150-250 words, max 450 words).
- **Canonical Template**: See [docs/templates/wave_plan_template.md](../../docs/templates/wave_plan_template.md).

## Retrieval & full-ripple inspection discipline at T2/T3

Before synthesis, pull evidence in this order: local repo guidance + nearby docs → exact files /
symbols / commands / config values → ADG / structured MCP for dependency, blast-radius, runtime
questions → semantic retrieval only when exact lookup leaves gaps → external research only when local
evidence is insufficient. Facts first, synthesis second. Reading and searching connected files across
upstream producers, shared schemas, sibling lanes, and downstream validators is **never capped**—when
making a change, inspect every connected component by definition.

## Holistic End-to-End Pipeline Contract Trace (`INV-HOLISTIC-PIPELINE-PLANNING`)

When a plan or refactor modifies any intermediate domain pipeline stage (e.g., `runtime/sections/`, `prompt_assembly/`, or `runtime/reasoning/` in `resume_graph_engine`, `outreach_engine`, or `apps_research`), the plan MUST trace and verify the full end-to-end data contract across all four coupled spine stages before finalizing `implementation_plan.md`:

1. **Stage-1 Upstream Retrieval & Candidate Ranking** (`quad_graph_retriever.py`, `graph_role_episode_selector.py`, `c0_perf_sync_helpers.py`): Verify whether query terms, entity boosts, or candidate admission quotas must realign with the new downstream structure or explicitly defend why Stage-1 stays unchanged.
2. **Stage-2 Upstream Graph Allocation & Schema Projection** (`runtime/c0/resume_graph_allocation.py`, `c0_fact_anchor.py`, `fact_inventory/`): Verify whether the upstream producer supplies the structured fields (`FactAnchor`, `resolved_raw_chunk`, `numeric_tokens`, `content_word_stems`, disjoint `root_id`/`fact_id` partitions) required so downstream lanes do not rely on local fallback templates or hardcoded string repairs.
3. **Stage-3 Section Generation, Prompt Assembly & Pool Selection** (`runtime/sections/`, `prompt_assembly/`, `runtime/reasoning/`, `runtime/judges/`): Consume the upstream contract directly rather than masking upstream schema omissions with post-LLM prose overrides.
4. **Stage-4 Downstream Cross-Section & Quality Floor Validation** (`runtime/aggregation/cross_section_x2.py`, `runtime/validators/bullet_quality_floor_x2.py`, `narrative_quality_x2.py`, `bullet_fact_entailment.py`): Unify word floors, sentence caps, stem-entailment ratios, cadence rules, and cosine similarity ceilings with the updated generation contract.

Focused single-module bug-fix plans pass `tools/validate_implementation_plan.py` without artificial pipeline-bundling blocks (`INV-REFACTOR-EXTENT-UNBOUNDED`), while cross-stage changes should align coupled upstream/downstream contracts cohesively.

## Anti-patterns (forbidden)

Plan-mode theatre for trivial T0/T1 work; stalling before a simple question; retrying a hung tool in a
loop; symptom-only section plans that ignore upstream C0 allocation or downstream X2 validation contracts. If an MCP hangs: STOP, note `[MCP UNAVAILABLE]`, proceed without it.
