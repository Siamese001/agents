# apps_rg - App Agent Contract

> `apps_rg` owns the resume-generation app surface. Its active contract, architecture, and runtime details live in this app package.

## Scope

`apps_rg` owns app-specific prompt assembly, runtime sections, contracts, profiles, tests, and evidence artifacts under `apps_rg/`. Root-cause bug fixes and cohesive cross-spine refactors across `apps_rg/` and its upstream/downstream contracts execute freely with zero file-count, file-size, line-count, or blast-radius caps (`INV-REFACTOR-EXTENT-UNBOUNDED`) while keeping directional inter-subsystem and storage import boundaries intact.

## Core invariants

- Graph IDs are the only claim authority.
- Runtime selection narrows evidence, but cannot add evidence.
- Whole-run caches stay separate from per-section C0 semantic payloads.
- Shared lanes such as `executive_summary`, `headline`, and `competencies` may only claim from their section-specific evidence plan.
- Deterministic copy and section templates remain grounded in canonical graph claims, and may be updated freely when resolving root-cause bugs or aligning section contracts.

## Working rules

- Build and verify section seams before broad integration.
- Keep whole-run `R1A`/`R1B` state separate from per-section payloads.
- Show exact section output, prompt/profile, provider or model status, artifact path, judge result, X2 gate result, and X3 disposition when making implementation claims.

## References

- Root [`AGENTS.md`](../AGENTS.md)
