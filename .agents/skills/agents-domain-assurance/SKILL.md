---
name: agents-domain-assurance
description: Consolidated E2E pipeline and hybrid retrieval assurance across outreach_engine, resume_engine, resume_graph_engine, and apps_research.
---

# Agents Domain & Retrieval Surface Assurance

Consolidates `agents-outreach-resume-functionality` and `agents-research-retrieval-surface` into a single preflight-gated workflow.

## Execution Protocol

1. **Preflight Discovery First**:
   ```bash
   .venv/bin/python tools/verify_commit.py
   ```
   If `0` defects are detected (`B_total == 0`), exit immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating empty branches or synthetic wave plans.

2. **Interactive Remediation Quota (`INV-REMEDIATION-QUOTA-FLOOR`)**:
   When `B_total > 0`, provision an isolated worktree via `.venv/bin/python tools/pr_governance.py start`, remediate at least `Q_min = min(B_total, max(3, ceil(0.02 * B_domain)))` production defects, and include the 7-column Before/After Defect Accounting Table.
