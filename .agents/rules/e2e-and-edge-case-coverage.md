---
trigger: model_decision
description: Mandatory E2E and adversarial edge-case testing, zero-mock smoke/eval shield enforcement, and bilateral recall-precision gates
---

# E2E, Adversarial Edge-Case & Construct Validity Rules (`agents` Overrides)

Inherits shared non-mock execution, adversarial boundary, and timeout invariants from `~/.gemini/config/plugins/core-governance/rules/e2e-and-edge-case-coverage.md`.

## Repository Invariants & Gates

1. **Zero-Mock Smoke & Eval Construct Validity (`INV-EVALS-CONSTRUCT-VALIDITY-GATE`, `0` violations)**:
   - Smoke harnesses and diff-scoped eval shields (`tools/run_diff_scoped_eval_shield.py`, `tools/eval_shield_core/*.py`, `ops_scripts/ci/check_eval_harness_promotion_evidence.py`) execute real production modules without `unittest.mock`, `MagicMock`, `patch`, or `monkeypatch`, verified by `tools/audit_eval_construct_validity.py --verify-strict`.
   - Branch-touched `tests/end_to_end/*_e2e.py` files are verified mock-free by `tools/verify_fix_eval_pinning.py` (non-pipeline doc waves may declare `E2E-EXEMPT`).
2. **Bilateral Recall-Precision & Judge Negative Controls (`INV-BILATERAL-RECALL-PRECISION-GATE`, `INV-JUDGE-NEGATIVE-CONTROL-GOLDEN`)**:
   - Pair recall floors (`>= N` matched facts) with explicit `== 0` unverified-claim / off-domain precision ceilings.
   - Every LLM-as-a-Judge rubric or threshold update must pin `>= 1` real human-rejected output (`INV-JUDGE-NEGATIVE-CONTROL-GOLDEN`, e.g. inanimate-subject datasheet openers) verified to fail both deterministic guards and judge criteria in `tools/run_diff_scoped_eval_shield.py`.
3. **Readiness Enforcement**: Enforced in `tools/verify_main_readiness.py` Stage 7 and Stage 8 across `resume_graph_engine`, `outreach_engine`, `apps_research`, and `agents`.
