# apps_rg - App Agent Contract

> `apps_rg` owns the resume-generation app surface. Its active contract, architecture, and runtime details live in this app package.

## Scope

`apps_rg` owns app-specific prompt assembly, runtime sections, contracts, profiles, tests, and evidence artifacts under `apps_rg/`. Root-cause bug fixes and cohesive cross-spine refactors across `apps_rg/` and its upstream/downstream contracts execute freely with zero file-count, file-size, line-count, or blast-radius caps (`INV-REFACTOR-EXTENT-UNBOUNDED`) while keeping directional inter-subsystem and storage import boundaries intact.

## Core invariants

- Verified candidate base resume and explicit operator confirmations are the only source of truth; graph JSON files (`fact_inventory/*.json`) are derived indices, never self-certifying (`approved_by_graph_presence` without source provenance is forbidden).
- Agents must NEVER invent, extrapolate, or backfill candidate facts, vendor names, or metrics into `fact_inventory/*.json` to pass a coverage gate (`INV-FACT-GRAPH-NO-AGENT-SYNTHESIS`); surface source-data gaps to the operator instead.
- Runtime selection narrows verified evidence and strictly enforces per-item `section_eligibility`; it can never add evidence or bypass eligibility locks.
- Zero post-LLM regex prose mutators (`INV-NO-POST-LLM-PROSE-MUTATORS`): fix prose quality upstream via clean facts, concise prompts, or a single bounded judge-guided fresh rewrite loop.
- Whole-run caches stay separate from per-section C0 semantic payloads.
- Shared lanes such as `executive_summary`, `headline`, and `competencies` may only claim from their section-specific verified evidence plan.
- Global structural changes must generalize across the multi-JD benchmark (`INV-MULTI-JD-NO-WHIPLASH`), never overfit to one company.

## Working rules

- Build and verify section seams before broad integration.
- Keep whole-run `R1A`/`R1B` state separate from per-section payloads.
- Show exact section output, prompt/profile, provider or model status, artifact path, judge result, X2 gate result, and X3 disposition when making implementation claims.

## References

- Root [`AGENTS.md`](../../../AGENTS.md)
