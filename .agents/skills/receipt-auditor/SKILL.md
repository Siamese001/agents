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

## 4. Verification Commands

```bash
.venv/bin/python tools/validate_implementation_plan.py --file <plan_file>
.venv/bin/python tools/validate_turn_gates.py --mode pre-turn
.venv/bin/python tools/validate_eval_rubrics.py --json
```
