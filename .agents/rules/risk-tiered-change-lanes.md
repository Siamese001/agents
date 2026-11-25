---
trigger: model_decision
description: Path-classified 3-lane risk tiering policy (Lane 0/1/2), fail-closed escalation, and non-blocking batch advisories
---

# Risk-Tiered Change Lanes Rules (`agents` Overrides)

Inherits 3-lane proportional ceremony, fail-closed escalation, and unbounded cohesive refactor principles from `~/.gemini/config/plugins/core-governance/rules/risk-tiered-change-lanes.md`.

## `agents` Policy & Classifier Bindings

- **Fail-Closed Classification (`INV-RISK-TIERED-CHANGE-LANES`, `default_unrecognized_lane = 2`)**: Defined in `config/governance/risk_lanes_policy.json` and enforced by `tools/change_lane_classifier.py` across `tools/verify_commit.py`, `tools/verify_main_readiness.py`, and `tools/pr_governance.py`.
- **Lane Scopes**:
  - **Lane 0 (4 readiness stages)**: `docs/**`, `README.md`, `reports/**`, `plans/**`, and `tests/**` / `*/tests/**`.
  - **Lane 1 (9 readiness stages)**: `agents/**`, `apps_eval/**`, `apps_model_telemetry/**`, `apps_research/**`, `outreach_engine/**`, `resume_engine/**`, `resume_graph_engine/src/**` (non-Lane-2), `infrastructure/**`, `scripts/**`, `ops_scripts/**`, `tools/**`, `config/**`.
  - **Lane 2 (all 10 readiness stages)**: `fact_inventory/**`, `runtime/{c0,validators,judges,providers}/**`, `provider_profiles.yaml`, `domain_contract/**`, `AGENTS.md`, `.agents/**`, `.githooks/**`, `config/governance/**`, and self-referential governance verifiers.
- **Unbounded Churn & Worktree Cap (`INV-REFACTOR-EXTENT-UNBOUNDED`)**: `max_non_generated_loc_per_merge` is `0` (non-blocking batch advisories only); active feature worktrees stay `<= 50`.
