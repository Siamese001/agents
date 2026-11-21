---
name: receipt-auditor
description: Verify governance, wave completion, and merge receipts before committing changes or completing PR promotion.
---

# Receipt Auditor

Verify the existence, integrity, and validity of governance receipts required for boundary changes, wave completions, and PR promotions. Ensures every architectural or operational change is backed by durable, independently verified execution evidence.

## 1. When to Invoke

- Before marking a wave complete in an implementation plan.
- Before committing boundary-sensitive or architecture-altering changes.
- Prior to PR queue promotion (`.venv/bin/python tools/pr_governance.py promote`).
- During turn-gate validation (`.venv/bin/python tools/validate_turn_gates.py --mode all`).

## 2. Governed Receipt Types & Locations

| Receipt Type | Standard Storage Path | Verifier Tool / Authority |
| :--- | :--- | :--- |
| **Wave Completion** | `artifacts/governance/wave<N>_*_receipt.json` | `tools/validate_implementation_plan.py` |
| **Pre-Merge Receipt** | `artifacts/governance/merge_receipts/<branch>_pre_merge.json` | `tools/verify_merge_receipt.py` |
| **Post-Merge Proof** | `artifacts/governance/merge_receipts/<branch>_post_merge.json` | `tools/verify_post_merge.py` |
| **Eval Rubrics & Holdout** | `artifacts/evals/` / `reports/` | `tools/validate_eval_rubrics.py` |
| **Domain Smoke Receipt** | `artifacts/governance/*_smoke_receipt.json` | `ops_scripts/run_e2e_authoritative_smoke.py` |

## 3. Verification Protocol

1. **Existence & Non-Empty Check**:
   - Ensure the declared receipt file exists on disk and is non-empty.
   - Self-authored or empty receipt stubs fail closed.
2. **Schema & Field Completeness**:
   - Every wave completion receipt must record:
     - `timestamp`: ISO8601 UTC timestamp of execution.
     - `command`: Exact command executed.
     - `exit_code`: Expected exit code (`0`).
     - `passed_count`: Number of passing assertions/tests.
     - `failed_count`: Zero failures (`0`).
     - `artifacts`: List of generated or inspected artifacts.
3. **Independent Observation**:
   - Verify produced behavior or output state independently through files or database queries rather than trusting receipt metadata alone.
4. **Merge Queue Certification**:
   - Pre-merge hook (`.githooks/pre-merge-commit`) automatically executes `tools/verify_merge_receipt.py`.
   - Post-merge verification executes `tools/verify_post_merge.py` to confirm two-parent merge ancestry and worktree cleanup.

## 4. Closed-Loop Eval Rubrics, Holdout Custody & Continuous Flywheel Protocol

When invoked for evaluation, judge validity, or post-runtime learning flywheel assurance (`agents-evals-flywheel-assurance`):
1. **Static Rubric, Holdout & Purity Preflight**:
   - Verify `[0.0, 1.0]` exit-eval rubric bounds, 4-class judge verdicts (`SAFE`, `UNSAFE_DIFFERENT_INTENT`, `UNSAFE_POLICY_DRIFT`, `UNCERTAIN`), live 11-grader execution, and git-tracked holdout custody across all `315` dataset files (`tools/validate_eval_rubrics.py --json`).
   - Verify zero golden fixtures in production (`tools/lint_production_purity.py --all`), zero mock stubs in smoke/eval shields (`tools/audit_eval_construct_validity.py --verify-strict --include-e2e-pin`), and zero 6-vector judge/remediation drift (`tools/audit_multi_ssot_judge_gate_drift.py`).
2. **Closed-Loop Flywheel Cycle (`INV-FLYWHEEL-AUTO-REMEDIATE`)**:
   - Run `tools/run_eval_flywheel_cycle.py --sandbox --emit-next-hitl-question` (`$0.00` marginal API cost) to drain `RunTrace` logs, backfill online grades, consolidate findings into `remediation_queue.sqlite`, check longitudinal drift, and synthesize `ImprovementProposal`s.
   - Auto-apply verified **Tier A** bounded updates (`confidence_margin > 0.20` and all 7 safety gates in `config/governance/auto_apply_policy.yaml` passing) via `agents/learning/commit_engine.py` with `LP5` canary auto-rollback and `LP0..LP5` Merkle sealing.
   - Surface **Tier B**, **Tier C**, and close-margin (`<= 0.20`) findings strictly **one at a time** via `ask_question` (`<= 115` char front-loaded confidence options), then execute, pin unmocked regressions, and promote upon approval.

## 5. Verification Commands

```bash
.venv/bin/python tools/validate_implementation_plan.py --file <plan_file>
.venv/bin/python tools/validate_turn_gates.py --mode pre-turn
.venv/bin/python tools/validate_eval_rubrics.py --json
.venv/bin/python tools/audit_eval_construct_validity.py --verify-strict --include-e2e-pin
.venv/bin/python tools/audit_multi_ssot_judge_gate_drift.py
.venv/bin/python tools/run_eval_flywheel_cycle.py --sandbox --emit-next-hitl-question
```
