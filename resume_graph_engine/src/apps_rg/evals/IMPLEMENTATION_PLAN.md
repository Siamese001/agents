# Apps RG v2 evaluation implementation plan

This plan ports the completed six-wave `apps_rg/evals` measurement surface from
the Agentic Workflow provenance repository into the standalone `src/apps_rg`
layout. The implementation remains offline, future-run-only, and
non-release-authorizing by itself.

## W1 - Measurement contract

- Define six independent gates and seven named score groups.
- Add fail-closed PASS, FAIL, UNKNOWN, and NOT_MEASURED semantics.
- Add schemas for complete reports and named gate results.

## W2 - Modular resume-graph evaluator

- Split dataset, normalization, validation, metrics, gates, and reporting.
- Preserve the compatibility entry point and legacy C0.3 evaluators.
- Keep the v2-only graph-embedding qualification module unchanged.

## W3 - Retrieval, binding, and grounding

- Evaluate the full finite retrieval universe rather than emitted Top-K alone.
- Add exact employer, role, date, metric, credential, scope, certainty, and
  graph-path binding checks.
- Add governed hard-negative and grounding mutation fixtures.

## W4 - Section quality

- Implement five sealed section lanes with explicit rubrics and schemas.
- Keep human and model-judge results distinct and non-authorizing.
- Preserve historical section schema compatibility files.

## W5 - Whole resume and W9

- Add deterministic whole-resume checks and six-pair human no-worse scoring.
- Seal the complete receipt and make W9 closeout consume it explicitly.
- Preserve current-run release authority and legacy closeout compatibility.

## W6 - Robustness, evaluator validity, and CI ratchet

- Add stored-run repeatability across eleven governed scenarios and at least
  three independently sealed execution receipts per scenario.
- Exercise real critical graders with clean controls and controlled mutations.
- Require seven sealed score-group receipts plus expected baseline signatures
  in the active CI ratchet path.

## Validation and authority

- Run evaluator-owned tests with `PYTHONPATH=<repo>/src`.
- Run the repeatability, meta-evaluation, and sealed-receipt CI CLIs on explicit
  test controls.
- Do not claim real-run G5 qualification without qualifying stored artifacts.
- Do not invent human labels or freeze human-agreement thresholds.
- Do not import or modify `apps_rg`, `ops_scripts`, or runtime behavior.
