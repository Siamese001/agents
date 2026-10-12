# Plan-First Enforcement (native plan mode)

> **Renamed W2.** Formerly `sequential-thinking-enforcement.md`
> — that name is a historical reference; the rule
> was goal-seeked to reimplement its *intent*. The real scope is **plan-first reasoning**: on T2/T3
> work, decompose and gather evidence, and make **no edits before the plan is approved** (native plan
> mode). Renamed to match scope.

> Superseded W2 (ADR-094): the `SR_INTAKE / SR_PLAN /
> SR_APPROVAL / SR_EXECUTE / SR_VERIFY` marker packet is retired. Native **plan mode** is the
> "no edits before approval" contract it emulated.

## When plan mode is required

MANDATORY for **T2/T3** tasks: planning / decomposition, architecture decisions, multi-file debugging,
refactors spanning files, ADG / dependency analysis, test-strategy design. NOT required for T0/T1
(question, typo, single config value, single import).

## Contract

- T2/T3 ⇒ `EnterPlanMode`, gather evidence (reads only), present the plan via `ExitPlanMode`, and make
  **no edits until the plan is approved**.
- One explicit approval for the presented plan authorizes execution of that unchanged scope through
  implementation, verification, and requested local git closeout. Do **not** ask for separate
  "design approval", "implementation approval", "refactor approval", or "commit/merge approval" unless
  the user limited the approval, the scope materially changes, a new Author-Gate-class decision appears,
  or the next action is destructive, external publication, or credential/security sensitive.
- A direct user instruction such as "implement", "fix it", "remove it", "commit", "merge to local main",
  or "execute PR" counts as approval for that named action when it stays inside the current approved
  scope. Ask again only when the requested action would exceed that scope.
- T0/T1 ⇒ proceed directly.

## Wave-Based Implementation Plan Standard (Supersedes Status Table)

The legacy mandatory 4-column Status Table in markdown plan files is retired. Implementation plans (`implementation_plan.md` or `plans/*.md`) are governed by [.agents/rules/wave-progression.md](wave-progression.md).

- **Structure**: Plans must be decomposed into sequential numbered waves (`## Wave 1: <Title>`, `## Wave 2: <Title>`) with 4 mandatory subsections per wave:
  1. `### Objective & Scope`
  2. `### Milestones & Deliverables` (`[NEW]`, `[MODIFY]`, `[DELETE]`)
  3. `### Acceptance Criteria`
  4. `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`)
- **Word Budget**: Target 500–800 words, hard limit 1,000 words (`INV-WAVE-PLAN-MAX-WORDS`).
- **Status Tracking & Reporting**: Wave status is tracked durably within repository artifacts and persistent ledgers. Ordinary conversational chat outputs must NOT dump all-wave status tables into chat (target ~120 words, max 300 words).
- **Canonical Template**: See [docs/templates/wave_plan_template.md](../../docs/templates/wave_plan_template.md).

## Retrieval discipline at T2/T3 (unchanged)

Before synthesis, pull evidence in this order: local repo guidance + nearby docs → exact files /
symbols / commands / config values → ADG / structured MCP for dependency, blast-radius, runtime
questions → semantic retrieval only when exact lookup leaves gaps → external research only when local
evidence is insufficient. Facts first, synthesis second.

## Anti-patterns (forbidden)

Plan-mode theatre for trivial T0/T1 work; stalling before a simple question; retrying a hung tool in a
loop. If an MCP hangs: STOP, note `[MCP UNAVAILABLE]`, proceed without it.
