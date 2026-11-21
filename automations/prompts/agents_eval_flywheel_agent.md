# On-Demand Assurance Workflow: Continuous Eval Flywheel & Post-Runtime Governance

> **Execution Posture**: Manual on-demand launcher only (unattended background schedules disabled per `AGENTS.md`). Runs strictly inside an isolated feature worktree or `--sandbox` directory with `$0.00` marginal API cost for deterministic grading, consolidation, and self-audits.

## Objective
Run one complete closed-loop evaluation and self-improvement cycle across `agents`:
1. Verify construct validity (`tools/audit_eval_construct_validity.py --verify-strict --include-e2e-pin`) and 5-vector judge-gate drift (`tools/audit_multi_ssot_judge_gate_drift.py`).
2. Execute the sandboxed flywheel cycle (`tools/run_eval_flywheel_cycle.py --sandbox`) to drain `RunTrace` logs, backfill zero-cost online grades, consolidate multi-surface findings into `remediation_queue.sqlite`, promote PII-scrubbed 80/20 golden cases, detect anchor-peak or rolling drift, and synthesize bounded `ImprovementProposal`s.
3. Enforce the 3-tier post-runtime auto-application policy (`config/governance/auto_apply_policy.yaml`):
   - **Tier A** bounded config/exemplar/regression-pin proposals may apply only after passing all 7 safety gates, zero-mutation shadow + locked `unlabeled_view` holdout replay, CAS commit, `LP5` post-apply canary, and `LP0..LP5` Merkle sealing.
   - **Tier B** prompt/prior proposals halt for atomic operator approval (`ask_question`) with cryptographic `finding_digest` and `proposal_digest` binding.
   - **Tier C** Python code, rubric, provider profile, or governance proposals emit `TRACK_2_CODE_FIX` packets routed strictly through `tools/pr_governance.py`.

## Verification Commands
```bash
python tools/audit_eval_construct_validity.py --verify-strict --include-e2e-pin
python tools/audit_multi_ssot_judge_gate_drift.py
python tools/run_eval_flywheel_cycle.py --sandbox
python tools/run_diff_scoped_eval_shield.py --all-domains
```
