---
trigger: model_decision
description: Mandatory E2E and adversarial edge-case testing, zero-mock smoke/eval shield enforcement, and bilateral recall-precision gates
---
# E2E, Adversarial Edge-Case & Eval Construct Validity Governance

Governs end-to-end verification, adversarial edge-case coverage, unmocked smoke/eval shields, and construct-validity enforcement across all pipeline-touching changes.

## 1. Core Verification Contract

Every Lane 1 or Lane 2 wave or pull request touching production pipelines (`resume_graph_engine/src/`, `outreach_engine/`, `apps_research/`, `agents/`, `infrastructure/`, or `tools/`) must include:

1. **Targeted regression or E2E coverage** verifying the real runtime seam without mocking away the subsystem under test.
2. **Adversarial edge-case coverage** across at least 3 categories for new adversarial suites:
   - **Boundary payload**: empty inputs, zero-length sections, empty candidate pools.
   - **Malformed input**: truncated JSON, wrong field types, missing required keys.
   - **Concurrency & race**: parallel lane execution, shared lock contention, queue drain.
   - **Overflow & exhaustion**: token budget exhaustion, retry budget depletion, timeout bounds.
   - **Invariant bypass attempt**: off-domain leakage, unverified synthetic facts, fake digests, self-downgrading policy edits.
   - **Rollback & recovery**: mid-cycle X2 rollback, ledger resync, atomic merge rollback.
   - **Exact production regression**: named regression test pinning an observed production defect with exact failing input and expected output.

Non-pipeline waves (documentation or receipts only) may declare `E2E-EXEMPT` in Acceptance Criteria.

## 2. Zero-Mock Smoke & Eval Construct Validity (`INV-EVALS-CONSTRUCT-VALIDITY-GATE`)

1. **Zero-Mock Smoke & Shield Execution (`FORBIDDEN_MOCK_IN_SMOKE_HARNESS`)**: Smoke harnesses and diff-scoped eval shields (`tools/run_diff_scoped_eval_shield.py`, `tools/eval_shield_core/*.py`, `ops_scripts/ci/check_eval_harness_promotion_evidence.py`) execute against real production modules and real schemas. Importing or invoking `unittest.mock`, `MagicMock`, `patch`, or `monkeypatch` inside those harnesses fails closed in `tools/audit_eval_construct_validity.py --verify-strict`.
2. **Zero Tautological Evaluators (`VACUOUS_EVALUATE_STUB` & `CLAMPED_REGRESSION_DELTA`)**: Evaluators must inspect candidate inputs rather than returning hardcoded passing constants, and must never coerce failing blind judge scores upward to mask regressions.
3. **Branch-Diff Unmocked E2E Pinning (`FORBIDDEN_MOCK_IN_E2E_PIN`)**: `tools/verify_fix_eval_pinning.py` inspects `tests/end_to_end/*_e2e.py` files touched on a branch and fails closed if any pinned E2E file imports `unittest.mock`, `MagicMock`, `patch`, or `monkeypatch`.

## 3. Diff-Scoped Unmocked Domain Eval Shield

`tools/run_diff_scoped_eval_shield.py` executes real unmocked domain checks across `resume_graph_engine`, `outreach_engine`, `apps_research`, and `governance_guards` (scoped to touched domains on Lane 1, and all domains on Lane 2). Both happy-path passes and fault-injection fail-closed rejections are verified.

## 4. Benchmark Specification Parity & Bilateral Recall-Precision (`INV-BILATERAL-RECALL-PRECISION-GATE`)

1. **Zero-Drift Specification Parity**: Numeric latency, score, or coverage targets stated in approved plans must be asserted with identical or stricter thresholds in automated tests; silently relaxing assertions fails closed.
2. **Bilateral Recall-and-Precision Bounds**: Recall floors (`>= N` matched facts or outcomes) must be paired with explicit precision ceilings (`== 0` unverified claims, `== 0` off-domain leaks, `== 0` forbidden patterns) so noisy inflation never looks like a pass.

## 5. Enforcement

- Tier 2 Stage 7 (`tools/verify_main_readiness.py`): `tools/audit_eval_construct_validity.py --verify-strict` + `tools/verify_fix_eval_pinning.py`.
- Tier 2 Stage 8 (`tools/verify_main_readiness.py`): `tools/run_diff_scoped_eval_shield.py`.
