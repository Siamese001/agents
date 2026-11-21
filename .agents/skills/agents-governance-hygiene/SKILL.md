---
name: agents-governance-hygiene
description: Consolidated 6-pillar storage, worktree, SQLite WAL hygiene, and SSOT architectural boundary governance for the Agents repository.
---

# Agents Architecture, Storage & Tokenomics Governance (On-Demand)

Consolidates SSOT centralization, unidirectional subsystem boundaries (`L0–L6`), multi-tier prompt/semantic/briefing caching, model profile right-sizing, and storage/SQLite hygiene into preflight-first, fail-closed execution alongside `.githooks/pre-commit` and `.githooks/post-merge` (zero daily background schedules).

## Execution Protocol

0. **Full Multi-Extension Search Mandate (`INV-FULL-EXTENSION-SSOT-SEARCH`)**:
   Every deduplication, redundancy, sprawl, secret, and SSOT audit searches `.md`, `.mdc`, `.txt`, `.jinja`, `.j2`, `.csv`, `.jsonl`, `.toml`, `.ini`, `.cfg`, `.sql`, `.yaml`, `.yml`, `.json`, `.py`, `.sh`, and `.ps1` across the repository without restricting scans to `.json`, `.yaml`, or `.py`.

1. **8-Pillar Cost, Caching & SSOT Architecture Checklist**:
   - **Boundaries & Centralization**: Zero cross-subsystem direct imports (`ssot_boundary_auditor.py`, `lint_architecture_boundaries.py`, `lint_layer_imports.py`), zero shadow-config drift (`ssot_sprawl_scanner.py`), zero unowned threshold literals (`ssot_hardcoding_scanner.py` vs `config/governance/centralization_registry.yaml`), and passing declarative schemas (`lint_contract_schemas.py`).
   - **Model Pins & Keyless IDE Routing**: Resolve all active pins strictly against `config/provider_profiles.yaml` and `config/model_catalog.json` (`lint_model_pins.py --strict`), keeping interactive sessions keyless (`$0.00` marginal API spend) and locking compact selectors/auditors to `low` reasoning effort.
   - **Multi-Tier Caching & $\text{ROI} \ge 2.5\times$ Gate**: Preserve Anthropic 3-breakpoint prefix caching (`TIER1_SLOTS`, `TIER2_SLOTS`, `VOLATILE_SLOTS`), BGE-M3 semantic fact-digest caching (`>= 0.985` cosine + matching `CacheIdentity`), 30-day atomic briefing persistence, and `48,000` / `300,000` token spend governors (`cost_token_budget_auditor.py --strict`).
   - **Automated Hygiene Gates**: Post-merge worktree/branch pruning and bloated WAL checkpointing run automatically in `.githooks/post-merge` (`storage_worktree_hygiene.py --post-merge-quick`); run full 6-pillar storage remediation manually via `tools/storage_worktree_hygiene.py --remediate --json` when needed.

2. **Preflight Read-Only Behavioral Audits (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`)**:
   Always execute read-only behavioral auditors first before provisioning any branch or mutating repository state:
   ```bash
   .venv/bin/python tools/ssot_boundary_auditor.py --include-ratchet-backlog --json
   .venv/bin/python tools/cost_token_budget_auditor.py --json --strict
   .venv/bin/python tools/lint_contract_schemas.py --all
   .venv/bin/python tools/storage_worktree_hygiene.py --json
   .venv/bin/python tools/validate_sidecar_separation.py --json
   .venv/bin/pytest tests/unit/test_ssot_centralization_auditor.py tests/unit/test_evals_and_budget_full_parity.py outreach_engine/tests/test_research_cost_optimization.py -q --timeout=60
   ```
   If all behavioral gates exit `0` (`is_clean == true`), fast-exit cleanly (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating empty worktrees or synthetic wave plans.

3. **Governed Remediation on Active Findings (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
   Whenever `>= 1` actionable findings exist (`is_clean == false`), provision an isolated `.worktrees/` branch via `prune_merged_chat_worktrees.py --consolidate-sidecar --write-manifest` (or `pr_governance.py start`), author and validate a wave plan in `plans/<slug>-<6hex>.md`, execute bounded remediation with 5-point counterfactual proofs, and obtain `PR_MERGE_AUTHORIZATION` before promoting to `main`.
