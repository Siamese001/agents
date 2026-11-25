---
trigger: glob
globs: "{config/contracts/**,config/governance/**,resume_graph_engine/src/apps_rg/config/domain_contract/**}"
---

# Contract Enforcement Rules (`agents` Overrides)

Inherits shared schema-first, fail-closed, and versioned evolution invariants from `~/.gemini/config/plugins/core-governance/rules/contract-enforcement.md`.

## Repository Contract Surfaces & Enforcers

- **Governance Contracts**: `config/governance/policy_registry.yaml`, `config/governance/risk_lanes_policy.json`, `config/governance/linter_profile.json`, `.agents/hooks.json`.
- **Domain Contracts**: `resume_graph_engine/src/apps_rg/config/domain_contract/*`, `resume_graph_engine/src/apps_rg/config/provider_profiles.yaml`, `config/model_catalog.json`.
- **Canonical Digest & Receipt Parity**: Allocation plans, evidence contracts, and readiness receipts bind deterministic SHA-256 digests (sorted keys, compact separators) with zero raw credential logging and strict `PASS`/`FAIL` gate parity.
- **Validation**: `.venv/bin/python tools/lint_contract_schemas.py --all` (Tier 1 Category 4 and Tier 2 Stage 4).
