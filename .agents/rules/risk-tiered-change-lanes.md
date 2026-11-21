---
trigger: model_decision
description: Path-classified 3-lane risk tiering policy (Lane 0/1/2), fail-closed escalation, and non-blocking batch advisories
---
# Risk-Tiered Change Lanes & Batch Advisory Governance Rules

Governs proportional AI-SDLC verification ceremony, path classification, fail-closed escalation, and non-blocking batch advisories (`config/governance/risk_lanes_policy.json`, `tools/change_lane_classifier.py`).

## 1. Three-Lane Risk Classification Architecture

Verification ceremony scales proportionally with the blast radius of changed paths:

- **Lane 0 (Low Risk)**:
  - *Scope*: Documentation (`docs/**`, `README.md`, `CHANGELOG.md`, `reports/**`, `plans/**`) and isolated test files (`tests/**`, `*/tests/**`) without production pipeline modifications.
  - *Ceremony*: Tier 1 structural checks, declarative contracts, eval construct validity, and governance harmonization.
- **Lane 1 (Medium Risk)**:
  - *Scope*: Standard application code (`agents/**`, `apps_eval/**`, `apps_model_telemetry/**`, `apps_research/**`, `outreach_engine/**`, `resume_engine/**`, `resume_graph_engine/src/**` outside Lane 2 critical paths, `infrastructure/**`, `scripts/**`, `ops_scripts/**`, `tools/**`).
  - *Ceremony*: Tier 1 pre-commit (including anti-overfitting linter), architectural boundaries, adversarial purity, contracts, eval harness, eval construct validity, unmocked diff-scoped eval shield, and governance harmonization.
- **Lane 2 (High / Critical Risk)**:
  - *Scope*: Candidate fact inventories (`resume_graph_engine/src/apps_rg/fact_inventory/**`), C0 allocation and graph projection (`resume_graph_engine/src/apps_rg/runtime/c0/**`), X2/X3 validators and LLM judges (`runtime/validators/**`, `runtime/judges/**`), provider routing (`provider_profiles.yaml`, `runtime/providers/**`), and governance controls themselves (`AGENTS.md`, `.agents/**`, `.githooks/**`, `config/governance/**`, `tools/verify_*`, `tools/pr_governance*`, `tools/change_lane_classifier.py`).
  - *Ceremony*: Strict 100% enforcement of all 9 registered Tier 2 readiness stages, PR merge queue qualification, unmocked domain eval shield across all domains, and governance harmonization.

## 2. Fail-Closed Escalation Invariants

1. **Unrecognized Path Escalation**: Any file path not explicitly mapped in `config/governance/risk_lanes_policy.json` strictly defaults to **Lane 2**.
2. **Mixed Change Escalation**: Any change set touching files across multiple lanes strictly escalates to the highest lane touched.
3. **Self-Referential Immutability**: `config/governance/risk_lanes_policy.json`, `tools/change_lane_classifier.py`, `tools/verify_commit.py`, `tools/verify_main_readiness.py`, and `tools/pr_governance.py` are locked to Lane 2 and can never downgrade themselves.

## 3. Non-Blocking Batch & Refactoring Advisories (`INV-REFACTOR-EXTENT-UNBOUNDED`)

- `max_non_generated_loc_per_merge` defaults to `0` (unbounded) so root-cause bug fixes and cohesive refactors never hit artificial file-count or LOC ceilings.
- `tools/change_lane_classifier.py` emits non-blocking advisories (`MIXED_RISK_LANES`, `LANE2_GOVERNANCE_ESCALATION`, `SOFT_BATCH_PROD_FILES`, `SOFT_BATCH_CHURN_LOC`, `UNRECOGNIZED_PATH_ESCALATED`) during `verify_commit.py`, `verify_main_readiness.py`, and `pr_governance.py` review.
- Active feature worktrees remain bounded (`<= 50`) and merged worktrees are pruned immediately post-merge.
