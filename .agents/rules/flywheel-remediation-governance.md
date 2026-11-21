---
trigger: always_on
description: Governed hybrid post-runtime flywheel remediation: automatic Tier A bounded tuning and atomic one-at-a-time ask_question dispatch for Tier B, Tier C, and close-margin updates.
---

# Flywheel Hybrid Auto-Apply & Atomic HITL Remediation (`INV-FLYWHEEL-AUTO-REMEDIATE`)

Governs post-runtime learning commits and defect remediation across `agents` (`config/governance/auto_apply_policy.yaml` and `config/governance/policy_registry.yaml`).

## 1. Hybrid 3-Tier Remediation Policy

1. **Tier A Auto-Apply (`TIER_A_AUTO_APPLY`)**:
   - Bounded configuration updates (`bounded_threshold`, `routing_weight`, `repair_hint`, `trajectory_exemplar`, `regression_case_pin` within allowlisted targets) apply automatically without interrupting the operator **only** when all 7 safety gates in `agents/learning/policy_router.py` pass and calibrated confidence margin strictly exceeds `20%` (`> 0.20`).
   - Every Tier A commit executes atomically via `agents/learning/commit_engine.py` with CAS pre-checks, `LP5` canary evaluation, exact pre-apply SHA-256 rollback protection, 7-day post-rollback anti-oscillation locks, and `LP0..LP5` Merkle sealing.

2. **Tier B, Tier C, and Close-Margin Atomic `ask_question` Dispatch**:
   - Tier B prompt/prior updates (`prompt_prior`, `prompt_template`), Tier C code/validator/governance defects (`TRACK_2_CODE_FIX`, `validator_or_code`, `.py` or `LANE_2` targets), and any close-margin (`<= 0.20`) or gated update MUST surface strictly **one at a time** (ranked by `impact_score DESC`) via plain-English `ask_question` payloads compiled by `agents/learning/flywheel_hitl_dispatcher.py` and validated by `tools/hitl_governance.py` (`<= 300` char question, `<= 250` char options, zero jargon, bound to `finding_digest` and `proposal_digest`).

3. **Immediate Post-Approval Execution & Pinning**:
   - Upon operator approval through `ask_question`, `record_remediation_decision()` binds an authentic `HUMAN_HITL_APPROVED` receipt and executes immediately:
     - **Tier B**: Apply via `agents/learning/commit_engine.py` + `LP5` canary and transition the finding to `VERIFIED`.
     - **Tier C**: Transition finding `OPEN -> APPROVED -> IN_PROGRESS`, resolve the root cause across all connected layers in an isolated worktree, pin an unmocked regression in `apps_eval/suites/pinned_fix_regressions.json` / `tests/end_to_end/`, and promote via `tools/pr_governance.py`.

4. **Snooze & Rejection Transitions**:
   - Operator snoozes or rejections transition the finding (`SNOOZED` / `REJECTED`) in `remediation_queue.sqlite` and update `HITLDecisionStore` learning aggregates.
