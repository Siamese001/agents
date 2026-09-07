# Apps RG v2 measurement-validity remediation

This plan implements a source-bound evaluation path without changing Apps RG
runtime behavior or fabricating human labels. Legacy evaluator APIs remain
available for compatibility and synthetic regression tests; authoritative
measurement uses `apps_rg.evals.authoritative`.

## E0 - Measurement architecture

- [x] Separate independently pinned truth, system output, score receipts, and
  human authority.
- [x] Add a seven-score-group evaluation manifest with external digest pins.
- [x] Keep every resulting receipt non-release-authorizing by itself.

## E1 - Standalone control plane and trust roots

- [x] Reuse the existing C0.3 owner-pinned human-review authority receipt.
- [x] Require the expected authority file SHA-256 from outside the evaluated
  artifact.
- [x] Add a standalone authoritative CLI and repair standalone evaluator test
  collection without a parent-package shadow.

## E2 - Source-bound retrieval

- [x] Separate candidate universe, system ranking, and human QREL artifacts.
- [x] Require independent pins for all three artifacts.
- [x] Require complete identity conservation across the three denominators.
- [x] Validate two rostered retrieval reviewers plus a rostered adjudicator.
- [x] Bind every QREL row to complete reviewer and adjudicator coverage.

## E3 - Source-verified binding and grounding

- [x] Separate source bytes, graph snapshot, system claims, and human truth.
- [x] Recompute source content and exact excerpt digests.
- [x] Resolve graph paths and derive binding comparisons rather than accepting
  system-authored `EXACT` or `FULL` declarations.
- [x] Preserve independent G2 and G3 results.

## E4 - Authorized section-quality review

- [x] Require two distinct rostered human reviewers for every case.
- [x] Require complete adjudication coverage bound to input and review digests.
- [x] Require externally pinned G3 coverage for every candidate and baseline
  artifact used in section comparison.
- [x] Keep model-only results outside authoritative human measurement.

## E5 - Whole-resume and W9 binding

- [x] Verify every candidate material claim against an externally pinned G3
  grounding index.
- [x] Bind W9 reviewers, qualifications, and adjudication to the owner-pinned
  human authority roster.
- [x] Require the whole-resume bundle itself to match an external digest pin.
- [x] Preserve the six-pair compatibility contract and non-release authority.

## E6 - Actual runtime repeatability

- [x] Add a controller that launches the declared command at least three times
  per governed scenario.
- [x] Bind controller nonce, command, source commit, input, timestamps, exit
  status, and semantic output into each execution receipt.
- [x] Require an externally pinned controller manifest and stability policy.
- [x] Make evidence and semantic instability fail when below policy rather than
  merely reporting it.

## E7 - Evaluator validity

- [x] Execute cross-grader isolation checks instead of recording an isolation
  assertion string.
- [x] Derive slice coverage, leakage incidents, threshold sensitivity, and
  clean-control confidence bounds.
- [x] Add an authorized human-pilot comparison with minimum sample size,
  agreement, and false-positive confidence-bound policy.
- [x] Require positive and negative pilot strata and enforce Wilson upper
  bounds for both false-positive and false-negative rates.

## E8 - Source-bound CI ratchet

- [x] Derive normalized counters from native evaluator receipts.
- [x] Require each native receipt to match an independently supplied source
  digest.
- [x] Add `SOURCE_BOUND_ALL_SCORE_GROUPS` mode while retaining the legacy
  normalized-receipt mode as compatibility-only.

## Evidence still required

Implementation completion is not empirical qualification. A real
qualification run still requires an owner-pinned evaluation manifest, frozen
corpus and graph, completed authorized human labels, actual controlled Apps RG
executions, frozen calibration thresholds, a one-time holdout run, and all
seven source-bound native receipts.

The implementation and its owned validation results are sealed separately in
`MEASUREMENT_VALIDITY_IMPLEMENTATION_RECEIPT.json`; that receipt is not an
empirical qualification result.
