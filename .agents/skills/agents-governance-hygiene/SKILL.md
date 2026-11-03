---
name: agents-governance-hygiene
description: Consolidated 6-pillar storage, worktree, SQLite WAL hygiene, and SSOT architectural boundary governance for the Agents repository.
---

# Agents Governance, Storage & Cost Hygiene (On-Demand)

Consolidates `agents-storage-worktree-hygiene`, `agents-ssot-boundary-governance`, `agents-cost-token-budget`, and `agents-testing-gaps-assurance` into deterministic on-demand CLI execution alongside `.githooks/pre-commit` (zero daily background schedules).

## Execution Protocol

1. **Deterministic 6-Pillar Storage, 6-DB WAL & Worktree Remediation**:
   ```bash
   .venv/bin/python tools/storage_worktree_hygiene.py --remediate --json
   ```

2. **6-Dimension SSOT, Package Boundary & Schedule Retirement Audit**:
   ```bash
   .venv/bin/python tools/ssot_boundary_auditor.py --json
   .venv/bin/python tools/validate_sidecar_separation.py --json
   ```

3. **8-Pillar Tokenomics, Dynamic ROI, Secrets & 9-Package Mock Reachability Audit**:
   ```bash
   .venv/bin/python tools/cost_token_budget_auditor.py --json --strict
   .venv/bin/python tools/lint_secrets.py --all
   .venv/bin/python tools/audit_mock_reachability.py
   ```
