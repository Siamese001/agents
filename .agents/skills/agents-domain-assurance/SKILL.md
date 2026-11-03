---
name: agents-domain-assurance
description: Consolidated E2E pipeline and hybrid retrieval assurance across outreach_engine, resume_engine, resume_graph_engine, and apps_research.
---

# Agents Domain, Retrieval & Rubric Surface Assurance (On-Demand)

Consolidates `agents-outreach-resume-functionality`, `agents-research-retrieval-surface`, and `agents-evals-judge-assurance` into a single preflight-gated on-demand workflow (zero daily background schedules).

## Execution Protocol

1. **Preflight Discovery & Domain Smoke / Retrieval / Rubric Sweep**:
   ```bash
   .venv/bin/python tools/verify_commit.py
   .venv/bin/python tools/validate_eval_rubrics.py --json
   .venv/bin/python ops_scripts/run_e2e_authoritative_smoke.py --skip-resume
   .venv/bin/python tools/verify_graph_integrity_and_embeddings.py
   .venv/bin/python tools/run_resume_graph_traversal_probe.py --max-paths 200
   .venv/bin/python tools/verify_pipeline_latency_caching.py
   .venv/bin/python tools/verify_release_gate.py --no-write --json
   ```
   If `0` defects are detected (`B_total == 0`), exit immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating empty branches or synthetic wave plans.

2. **Interactive Remediation Quota (`INV-REMEDIATION-QUOTA-FLOOR`)**:
   When `B_total > 0`, provision an isolated worktree via `.venv/bin/python tools/pr_governance.py start`, remediate at least `Q_min = min(B_total, max(3, ceil(0.02 * B_domain)))` production defects, and include the 7-column Before/After Defect Accounting Table.
