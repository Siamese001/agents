# On-Demand Assurance Workflow: Continuous Eval Flywheel & Post-Runtime Governance

> **Execution Posture**: Manual on-demand launcher only (unattended background schedules disabled per `AGENTS.md`). Runs strictly inside an isolated feature worktree or `--sandbox` directory with `$0.00` marginal API cost for deterministic grading, consolidation, and self-audits.

## Objective
Run one complete closed-loop evaluation, hybrid auto-apply, and atomic remediation cycle across `agents`:
1. **Preflight & Flywheel Cycle**: Verify construct validity (`tools/audit_eval_construct_validity.py --verify-strict --include-e2e-pin`) and 6-vector judge/remediation drift (`tools/audit_multi_ssot_judge_gate_drift.py`), then execute `tools/run_eval_flywheel_cycle.py --sandbox --emit-next-hitl-question` to drain `RunTrace` logs, backfill zero-cost online grades, consolidate multi-surface findings into `remediation_queue.sqlite`, promote PII-scrubbed 80/20 golden cases, detect anchor-peak or rolling drift, and synthesize bounded `ImprovementProposal`s.
2. **Automatic Tier A Application (`INV-FLYWHEEL-AUTO-REMEDIATE`)**: Automatically apply verified **Tier A** bounded configuration/exemplar/regression-pin proposals (`confidence_margin > 0.20` and all 7 safety gates in `config/governance/auto_apply_policy.yaml` passing) via `agents/learning/commit_engine.py`, `LP5` canary checks with exact SHA-256 auto-rollback, and `LP0..LP5` Merkle sealing.
3. **One-at-a-Time `ask_question` Presentation**: Present `next_ask_question_payload` strictly **one finding at a time** (ranked by `impact_score DESC`) via `ask_question` for **Tier B** prompt/prior changes, **Tier C** code/validator defects (`TRACK_2_CODE_FIX`), and close-margin (`<= 0.20`) updates, keeping plain-English wording validated by `tools/hitl_governance.py` and bound to `finding_digest` and `proposal_digest`.
4. **Immediate Post-Approval Execution, Pinning & Promotion**: Upon operator choice via `record_remediation_decision()`, immediately execute approved Tier B updates (`commit_engine.py` + `LP5` canary), or immediately fix approved Tier C defects in an isolated worktree, pin unmocked regressions in `apps_eval/suites/pinned_fix_regressions.json` / `tests/end_to_end/`, and merge via `tools/pr_governance.py promote`; transition snoozes/rejections cleanly in `remediation_queue.sqlite` and `HITLDecisionStore`.

## Verification Commands
```bash
python tools/audit_eval_construct_validity.py --verify-strict --include-e2e-pin
python tools/audit_multi_ssot_judge_gate_drift.py
python tools/run_eval_flywheel_cycle.py --sandbox --emit-next-hitl-question
python tools/run_diff_scoped_eval_shield.py --all-domains
```
