---
trigger: glob
globs: "resume_graph_engine/**"
---

# Resume Graph Engine (`apps_rg`) Governance

Applies to all work inside `resume_graph_engine/`.

## Core Runtime Invariants

- **Verified Candidate Fact Provenance (`INV-FACT-GRAPH-NO-AGENT-SYNTHESIS`)**: Verified candidate base resume and explicit operator confirmations are the sole source of truth. Graph JSON files (`resume_graph_engine/src/apps_rg/fact_inventory/*.json`) are derived indices; never invent, extrapolate, or backfill candidate facts, metrics, or vendor names to clear a gate.
- **Zero Post-LLM Prose Mutators (`INV-NO-POST-LLM-PROSE-MUTATORS`)**: Fix prose defects upstream via verified facts, clean prompt contracts, or a bounded judge-guided rewrite loop rather than stacking post-hoc regex mutators.
- **Multi-JD Generalization (`INV-MULTI-JD-NO-WHIPLASH`)**: Never hardcode target company names, employer slot locks, or single-JD conditional branches into runtime code or global rules (`tools/lint_no_jd_overfitting.py`).
- **Acronym Clarity (`INV-RESUME-NO-UNDEFINED-ACRONYMS`)**: Specialized industry acronyms (such as `MGA`/`MGAs` for Managing General Agents) must be defined on first use in executive-facing resume outputs (`resume_graph_engine/src/apps_rg/runtime/aggregation/cross_section_x2.py`).
- **Graph Allocation & SQLite Integrity**: Preserve C0.3 unique IDs (`resume_graph_engine/src/apps_rg/runtime/c0/resume_graph_allocation.py`) and read-only SQLite skills graph projections (`resume_graph_engine/src/apps_rg/fact_inventory/skills_graph/`). Keep whole-run `R1A`/`R1B` caches separate from per-section C0 payloads.
- **Cross-Family Judge Orthogonality**: Section generators and exit judges must resolve orthogonal provider families from `config/provider_profiles.yaml`.
- **Unbounded Root-Cause Fixes**: Trace and fix defects across all coupled producers, contracts, validators, and tests under `resume_graph_engine/` without file-count or line-count caps (`INV-REFACTOR-EXTENT-UNBOUNDED`).
