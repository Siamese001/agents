# DEPRECATION NOTICE: `apps_rg` has moved to `apps_rg_v2`

> [!WARNING]
> **This package is DEPRECATED and FROZEN.**
> As of August 2026, all active development, standalone runtime execution, graph skill qualification, and evaluation suites for Apps RG have graduated from this monorepo into an independent, purpose-built repository:
>
> ➡️ **[Siamese001/apps_rg_v2](https://github.com/Siamese001/apps_rg_v2)** (Local: `C:\Git\apps_rg_v2`)

---

## Migration Summary

1. **Why `apps_rg` was extracted**:
   - Apps RG was previously bound to `agentic_core` in this monorepo. To enable independent deployment, isolated dependency management, offline BGE-M3 qualification, and zero-monorepo runtime boundaries, it was extracted as a standalone repository.
2. **Current State in `Agentic-Workflow`**:
   - The code in this directory (`apps_rg/`) was frozen following commit `38796dc6cb` and merge commit `d200a03cfc`.
   - All feature branches (`agent/apps-rg-l6-semantic-closure*`, `codex/apps-rg-*`) have been fully merged and retired.
   - All high-value domain guardrails (`forbidden_claims`), architectural decision records (ADRs), golden senior role fixtures, and run diagnostic tools have been audited and extracted into `apps_rg_v2`.
3. **What is New in `apps_rg_v2`**:
   - Fully standalone packaging (zero `agentic_core` coupling).
   - Slalom activated as the primary executive role across the graph, DAG, and modular pipeline (pruning legacy InsurTech/EY roles).
   - 5 bounded Agent-to-Agent (A2A) runtime reasoning loops with dedicated repair agents (`ExecutiveVoiceRepairAgent`, `ResumeRunRecoveryAgent`, `CareerThesisAlignmentAgent`).
   - Hardened 4-plane decision engine, post-X3 completion gates, and resolver path integrity.
   - Built-in stdlib OOXML DOCX renderer eliminating legacy exporter dependencies.
   - Offline candidate requalification against pinned BGE-M3 embeddings.

## Developer Instructions

- **Do NOT commit changes to `Agentic-Workflow/apps_rg`**.
- For all resume generation, evaluation runs, and code contributions, clone and use:
  ```bash
  git clone https://github.com/Siamese001/apps_rg_v2.git
  ```