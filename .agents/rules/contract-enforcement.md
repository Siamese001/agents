---
trigger: glob
globs: "{config/contracts/**,config/governance/**,resume_graph_engine/src/apps_rg/config/domain_contract/**}"
---
# Contract Enforcement & Schema Integrity Rules

Governs declarative JSON/YAML schemas, canonical digests, and contract-bound receipts across `agents`.

## 1. Compatibility & Canonical Digest Integrity

- **Fail Closed**: Governed contract artifacts and config files fail closed on malformed structure or unknown critical fields (`tools/lint_contract_schemas.py --all`).
- **Versioning**: Breaking schema changes require a major version bump; backward-compatible optional fields require a minor bump; documentation updates require a patch bump.
- **Canonical Digest**: Deterministic SHA-256 over UTF-8 JSON with sorted keys and compact separators (excluding the digest field itself) for allocation plans, evidence contracts, and readiness receipts.

## 2. Governed Contract Surfaces

- **Governance Policies**: `config/governance/policy_registry.yaml`, `config/governance/risk_lanes_policy.json`, `.agents/hooks.json`.
- **Domain Contracts**: `resume_graph_engine/src/apps_rg/config/domain_contract/*`, `resume_graph_engine/src/apps_rg/config/provider_profiles.yaml`, `config/model_catalog.json`.
- **Validation**: `.venv/bin/python tools/lint_contract_schemas.py --all` (Tier 1 Category 4 and Tier 2 Stage 4).

## 3. Telemetry & Receipt Boundaries

- Never log raw private credentials, bearer tokens, or API keys in receipts or telemetry streams.
- Receipts must preserve exact pass/fail parity with underlying stage dispositions (`PASS` only when all required gates and admissions pass).
