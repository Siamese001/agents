---
name: agents-governance-hygiene
description: Consolidated 6-pillar storage, worktree, SQLite WAL hygiene, and SSOT architectural boundary governance for the Agents repository.
---

# Agents Governance & Storage Hygiene

Consolidates `agents-storage-worktree-hygiene` and `agents-ssot-boundary-governance` into deterministic CLI execution and interactive boundary remediation.

## Execution Protocol

1. **Deterministic 6-Pillar Storage & Worktree Remediation**:
   ```bash
   .venv/bin/python tools/storage_worktree_hygiene.py --remediate
   ```

2. **SSOT Architectural Boundary Audit**:
   ```bash
   .venv/bin/python tools/ssot_boundary_auditor.py
   .venv/bin/python tools/validate_sidecar_separation.py
   ```
