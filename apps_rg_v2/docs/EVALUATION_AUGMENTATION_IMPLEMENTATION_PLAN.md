# Apps RG pipeline evaluation augmentation plan

**Status:** plan only. This document does not change the runtime, generate labels,
set qualification thresholds, authorize release, or authorize production.

**Planning baseline (2026-08-11):**

- local branch: codex/evals at b494f3ef65658f70bc531fb5fafa9fe5606e6a0d;
- observed upstream: origin/main at 6c071fc06f9e10d46e13f98adafbcf8e7fffcba0,
  65 commits ahead of the branch baseline;
- the working tree contains pre-existing runtime-artifact changes which this plan
  must not absorb or modify.

## 1. Decision this evaluation system must support

Apps RG should be judged on whether it produces a useful, decision-ready resume
from an eligible research handoff without making unsupported, incorrectly bound,
unsafe, or operationally unusable output. A green fixture suite, a high scalar
score, or a valid receipt alone is not that decision.

The target system has two primary outcomes and a set of diagnostic and safety
gates:

| Role | Metric or gate | Correct unit and denominator | Current planning posture |
| --- | --- | --- | --- |
| Primary outcome | P1: blind finished-resume utility delta | Every eligible, completed, blinded candidate-versus-frozen-baseline pair | Contracted; not measured |
| Primary outcome | P2: grounded decision-ready completion rate | Every eligible attempted run, including failed and abstained attempts | Contracted; technical operational validator exists, but product outcome is not measured |
| Diagnostic driver | G1 retrieval | Frozen query plus its full human-labelled candidate universe | Active evaluator; requires frozen QREL authority |
| Safety diagnostic | G2 exact binding and G3 grounding | Every independently inventoried material output claim and binding | Active evaluator; current system-supplied inventory must be reconciled independently |
| Quality diagnostic | G4 section and whole-resume quality | Every declared output lane plus whole-resume pair | Active evaluator; independent human qualification remains required |
| Reliability diagnostic | G5 repeatability | At least three distinct sealed runs for each governed scenario | Active evaluator; representative run evidence remains required |
| Measurement diagnostic | G6 evaluator validity | Each release-affecting grader, clean control, and targeted mutation | Active evaluator; expand to the new outcome and denominator graders |
| Guardrails | Unsupported claims, critical binding errors, authority bypass, PII leakage, unfair counterfactual result | Every eligible attempt or reviewed pair where applicable | Zero-critical-error policy; do not blend into a compensating score |
| Regression signal | apps_eval snapshot and microstep scorecards | Development fixtures and sealed existing-run snapshots | Regression-only; cannot qualify human review, release, or production |

The current success-metric contract correctly prohibits a blended overall score and
states that a diagnostic gate pass is not outcome success. This plan keeps that
separation. P1 and P2 are the decision metrics; G1-G6 explain why they move or
why an attempt is unsafe.

## 2. Scope and non-negotiable constraints

The in-scope pipeline is:

Apps Research handoff -> U0 -> L1 -> L0 -> C0 -> PA -> L2 -> X2 -> X1D -> X3 -> Exit

Each eligible run must cover the 11 generated lanes declared in
src/apps_eval/registries/apps_rg_lane_contract.json:

1. competencies
2. unify_bullets
3. ibm_bullets
4. insurtech_bullets
5. ey_bullets
6. unify_narrative
7. ibm_narrative
8. insurtech_narrative
9. ey_narrative
10. executive_summary
11. headline

Constraints that every implementation phase must preserve:

- An Apps Research handoff is an eligibility prerequisite before U0. A missing or
  invalid handoff produces UNKNOWN or FAIL; it never silently enters P2.
- Unknown, missing, and not-run required evidence is not a pass.
- Development fixtures, model judges, technical receipts, and calibrated
  evaluators cannot create human labels, release authority, or production
  authority.
- Protected-holdout data stays inaccessible to development workflows. Code must
  not synthesize, infer, prefill, or expose human labels.
- Graph IDs, source bytes, and approved evidence paths remain the authority for
  claims. Retrieval can rank candidates but cannot become evidence authority.
- Apps Eval remains a read-only regression harness. Its scalar and row
  aggregates remain explicitly non-authoritative for product success.
- App-local telemetry must not claim coverage of an external agentic_core seam
  without linked core evidence. The receipt must state a coverage gap when such
  linkage is absent.

## 3. Target architecture

Research handoff and U0 eligibility feed an immutable attempt ledger. The ledger
feeds G1-G6 diagnostics and guardrails as well as P2 end-to-end completion. A
separate blinded human-review and adjudication process feeds P1 finished-resume
utility. P1, P2, and the diagnostics feed a qualification receipt catalog, which
can then support named human and release decisions.

The central new object is an immutable, source-bound attempt record. It joins the
research handoff, stage ledger, lane artifacts, document-rendering evidence,
runtime identity, diagnostics, exclusions, and outcome references without
rewriting the run. P1 then joins blinded human pair records to the same frozen
attempt identities.

## 4. Implementation sequence

### P0 — Rebaseline before implementation

**Why:** codex/evals is intentionally based on a checkout that is 65 commits
behind observed origin/main. The later changes include Apps Eval replay and Apps
RG runtime work, so implementing against the older source can create false
coverage.

**Work:**

1. Preserve the four pre-existing runtime-artifact changes outside this plan.
2. Obtain a clean/recoverable branch state, then rebase or merge codex/evals onto
   the exact current origin/main tip selected for implementation.
3. Record the selected commit, contract digests, lane-contract digest, and
   runtime-package digest in a short baseline receipt.
4. Diff all changed pipeline stages, lane artifacts, and evaluator interfaces
   since b494f3ef. Add each new, removed, or materially changed element to the
   coverage matrix in P1.

**Acceptance criteria:**

- The implementation branch has a recorded exact source baseline.
- No pre-existing runtime-artifact file is included in the evaluation plan
  change set unless separately approved.
- A changed pipeline stage cannot be assumed covered merely because an older
  fixture exists.

### P1 — Make coverage and authority machine-checkable

**New or modified files:**

- Add src/apps_rg/evals/contracts/pipeline_measurement_coverage.v1.yaml.
- Add src/apps_rg/evals/schemas/pipeline_attempt_evaluation.v1.schema.json.
- Add src/apps_rg/evals/pipeline_attempt_evaluation.py.
- Extend src/apps_rg/evals/receipt_catalog.py and
  src/apps_rg/evals/receipt_catalog_manifest.v1.json.
- Extend src/apps_rg/evals/success_metrics.py only to consume sealed references;
  it must not execute the runtime or upgrade authority.
- Add focused tests under src/apps_rg/evals/tests/.

**Contract shape:**

For each stage, lane, and cross-run artifact, the coverage contract records:

- pipeline element and owner;
- construct measured, metric ID, numerator, denominator, and slice keys;
- input artifact roles and immutable digests;
- evaluator ID/version and whether it is deterministic, model-assisted, or human;
- authority tier, current status, and reason code for UNKNOWN or NOT_MEASURED;
- P1/P2/guardrail/G1-G6 linkage;
- recertification triggers and expected mutation tests.

The contract must contain rows for Apps Research-to-U0, all global stages,
all 11 lane paths, final document output, Exit, and post-Exit observer-only
evidence. Every required runtime element must map to at least one decision
metric or safety guardrail. Every metric must map back to a real pipeline
element; orphaned rubric rows are failures.

**Acceptance tests:**

- Missing an eligible stage, generated lane, metric denominator, slice policy,
  authority declaration, or source digest fails validation.
- An apps_eval regression row cannot be classified as P1, P2, human-qualified,
  release-authorized, or production-authorized.
- A new lane or stage in the runtime registry fails CI until coverage is
  explicitly declared.

### P2 — Build valid calibration and protected-holdout cohorts

**New or modified files:**

- Add a development cohort manifest and a protected-holdout commitment manifest
  under src/apps_rg/evals/fixtures/.
- Add src/apps_rg/evals/cohort_validation.py and a corresponding schema.
- Extend protected_holdout_qualification.py only with source-bound cohort and
  preregistration references; do not access holdout content in development.
- Add reviewer-ready packet builders under src/apps_rg/evals/owner_solo/ or a
  new human_review package, retaining the existing no-synthetic-label controls.

**Cohort rules:**

1. Use distinct requests, candidate evidence, JDs, research handoffs, and
   source-digest families across calibration and protected holdout.
2. Record source, profile, JD, research, prompt/runtime, and baseline-output
   digests per case. Reject duplicated or overlapping identities.
3. Cover every generated lane, sparse and rich evidence, ambiguity/escalation,
   hard negatives, multiple role families, document edge cases, and declared
   fairness/privacy slices.
4. Keep the P2 denominator as all eligible attempts. COMPLETE, FAILED, and
   governed abstention outcomes must each be recorded; exclusions need a
   predeclared reason and count.
5. Keep protected-holdout identifiers opaque to development commands and require
   the existing release-access control before resolution.

**Automated data-quality checks:**

- uniqueness of case, attempt, pair, review, and adjudication IDs;
- no cross-split digest overlap or source-family leakage;
- required source and evaluator fields populated;
- finite, valid timestamps and non-negative runtime measures;
- complete lane/stage coverage at the attempt grain;
- denominator conservation: complete + failed + abstained + governed exclusions
  equals the frozen cohort population;
- change detection for source, model, prompt, research, or runtime drift.

**Acceptance criteria:**

- Calibration fixtures measure distinct cases rather than repeated snapshots.
- A deliberate duplicate, split leak, omitted failed attempt, or missing lane
  fails its validation test.
- Holdout remains PENDING/NOT_MEASURED until authorized human process occurs.

### P3 — Independently verify the material-claim denominator

The existing material-claim inventory schema and grounding evaluator are useful,
but the system must show that an output claim cannot avoid G2/G3 simply by being
absent from a system-produced ledger.

**New or modified files:**

- Add an independent claim-span extractor interface and
  claim_inventory_reconciliation.v1 schema.
- Add src/apps_rg/evals/claim_inventory_reconciliation.py.
- Update the G2/G3 receipt assembly to bind both the runtime ledger and the
  independent inventory, including unmatched spans and dispositions.
- Add mutation fixtures for omitted claims, merged composite claims, altered
  numbers/dates/employers, paraphrases, unsupported certainty, and broken paths.

**Measurement rule:**

Every material span in the final rendered output is either (a) matched to a
source-bound claim record, (b) explicitly marked non-material under a reviewed
rule, or (c) a hard failure/UNKNOWN. Reconciliation coverage is:

matched material spans / all independently extracted material spans.

Release-sensitive G2/G3 reports require 100 percent coverage, zero unsupported
material claims, and zero critical binding errors. The independent extractor is
an auditing tool, not an authority generator; ambiguous cases route to named
human review.

**Acceptance tests:**

- Omitted or altered material claims are detected by the intended evaluator.
- Clean controls do not create false omissions.
- The reconciliation report cannot turn an unreviewed or synthetic label into
  human-qualified evidence.

### P4 — Implement P1: blinded finished-resume utility

**New or modified files:**

- Add P1 paired-review and adjudication schemas.
- Add src/apps_rg/evals/whole_resume/p1_blind_utility.py.
- Extend the whole-resume receipt only with immutable P1 references and
  authority state.
- Add a P1 summary receipt to the receipt catalog.

**Design:**

1. Freeze a baseline output and candidate output for each eligible case before
   reviewers see them.
2. Blind and randomize presentation order. Keep the link key outside reviewer
   packets.
3. Collect independent review on final usefulness, role relevance, factual
   credibility, clarity, decision readiness, and material-regression status.
   G4 component judgments stay visible as diagnostics; P1 uses a preregistered
   combined decision, not an opaque average.
4. Require adjudication for disagreements and preserve reviewer identity,
   timestamps, rationale, source locators, packet hash, and adjudication
   disposition.
5. Compute the exact P1 numerator and denominator from the success-metric
   contract, report uncertainty, and present slice results. A tie cannot be
   mislabeled as superiority.

**Threshold policy:**

Do not set a numerical utility target in source code before calibration. Use the
calibration cohort to preregister a material-improvement or non-inferiority
decision rule, an uncertainty method, a minimum sample plan, and a
material-regression rule. Freeze those values before accessing holdout.

**Acceptance tests:**

- Swapping candidate/baseline labels changes no reviewer-visible identity.
- Missing reviewer, timestamp, rationale, packet digest, or adjudication blocks
  human-qualified status.
- A quality improvement cannot pass P1 when it has a material grounding,
  binding, privacy, or authority guardrail failure.

### P5 — Complete P2 as an end-to-end product outcome

src/apps_rg/evals/e2e_operational_evaluation.py already validates technical
operational evidence. Extend it into a source-bound P2 assembler, without
changing the current runtime:

**Work:**

1. Ingest the P1/P2 attempt envelope from P1 and require the valid Apps
   Research-to-U0 receipt, stage sequence, runtime identity, cache mode,
   operational measures, and every lane artifact.
2. Preserve every eligible COMPLETE, FAILED, and governed abstained attempt.
   Reject a manifest that drops failed attempts or rewrites their failed stage.
3. For COMPLETE attempts, require all 11 lane completion rows, G1-G6 references,
   final document evidence, PDF and DOCX parse-back digests, and overflow/text
   loss checks.
4. Report completion rate, latency p50/p95, cost per completed resume, provider
   error rate, retries, tokens, cold/warm split, and failure stage distribution
   as separate fields. None may offset a safety failure.
5. Attach eligible/excluded counts and reason codes so operators can audit the
   denominator, not just completed output.

**Acceptance tests:**

- Removing one failed or abstained attempt changes the denominator and fails
  conservation.
- A successful text artifact with a PDF/DOCX round-trip mismatch fails the
  relevant guardrail.
- Missing research, stage, lane, model, cost, retry, or fairness evidence is
  UNKNOWN/BLOCKED, never a completed P2 pass.

### P6 — Close diagnostic coverage and validate every evaluator

Enhance G1-G6 only where it makes P1/P2 safer, more diagnosable, or more
trustworthy:

| Gate | Augmentation |
| --- | --- |
| G1 retrieval | Score full frozen candidate universes against human QRELs; retain Recall@K, nDCG, path accuracy, coverage, hard-negative rejection, redundancy, and slice reporting separately. |
| G2/G3 | Consume P3 reconciliation coverage; validate every exact binding and evidence path against source bytes. |
| G4 quality | Extend explicit lane coverage from currently implemented section surfaces to all 11 lanes plus final assembled resume; keep absolute, pairwise, human, and model-judge results separate. |
| G5 repeatability | Run distinct sealed executions across representative scenarios; compare evidence and disposition identity separately from allowed prose variation. |
| G6 evaluator validity | Give every release-affecting deterministic grader, model judge, P1 assembler, P2 assembler, and cohort validator a clean control plus isolated defect mutation. Validate determinism, leakage rejection, tamper detection, and false-positive behavior. |

No G1-G6 result is promoted into P1/P2 automatically. Each receipt must state
which primary outcome it informs, its authority tier, and whether it is
diagnostic, guardrail, or outcome evidence.

**Acceptance tests:**

- At least one intentional defect per critical evaluator fails only the intended
  evaluator or has a documented dependency reason.
- Clean controls remain clean.
- A new metric or grader cannot enter a release catalog without a G6 card,
  mutation coverage, ownership, and evidence version.

### P7 — Calibrate thresholds and prove causal usefulness

The current protected-holdout contract already expects primary outcomes,
guardrails, slices, and paired/randomized ablations for retrieval, grounding,
section generation, and whole-resume assembly. Implement the missing
preregistration and calibration process before holdout use.

**Work:**

1. Run calibration only on the non-holdout cohort.
2. Pre-register P1/P2 thresholds, non-inferiority or superiority rules,
   uncertainty calculations, sample/power rationale, slice policy, SLO policy,
   missing-data policy, and error-budget ownership.
3. Freeze baseline versions and run paired or randomized ablations. Each
   component change must report its impact on P1, P2, and critical guardrails,
   not just its local metric.
4. Bind the exact source commit, source/profile/JD/research digests, evaluator
   versions, and threshold receipt to the holdout manifest.
5. Reject stale scope automatically when any frozen identity changes.

**Acceptance criteria:**

- Thresholds have an evidence-backed calibration receipt rather than a constant
  selected from development fixtures.
- Retrieval, grounding, section-generation, and assembly claims each have a
  causal design and an outcome-level result.
- The protected-holdout validator remains non-passing unless all required
  receipts, human review, guardrails, slices, and ablations are complete.

### P8 — Govern qualification, release, and post-release monitoring

**Receipt catalog changes:**

- Record technical validation, human-qualified, release-authorized, and
  production-authorized states separately.
- Require immutable references for P1, P2, G1-G6, guardrails, calibration,
  holdout scope, reviewer/adjudication, and a named release decision.
- Make current-run promotion future-runs-only unless an explicit governing
  policy says otherwise.
- Reject stale source, runtime, evaluator, cohort, prompt, model, research, or
  threshold bindings.

**Recertification triggers:**

- source corpus/profile/JD/research handoff change;
- graph/retrieval/index change;
- prompt, routing, model, judge, or provider change;
- lane/stage/artifact-contract change;
- document renderer/parser change;
- metric formula, threshold, reviewer rubric, or cohort change;
- detected production drift, slice regression, or guardrail incident.

**Operational monitoring:**

Post-Exit shadow measurements may monitor outcome drift, provider behavior,
latency, cost, reviewer disagreement, and canary coverage. They must be
observer-only and cannot recalibrate weights, mutate a completed run, or grant
qualification. Core-owned telemetry is linked when available; otherwise the
receipt declares the coverage gap explicitly.

## 5. Verification matrix

| Layer | Evidence / command | What it proves | What it does not prove |
| --- | --- | --- | --- |
| Contract | python -m pytest -q src/apps_rg/evals/tests/test_evaluation_contract.py src/apps_rg/evals/tests/test_success_metrics.py | Contract and receipt semantics | Human utility or production readiness |
| Cohort quality | New cohort-validation and leakage-mutation tests | Cohort identity, split isolation, denominator integrity | Representative human quality by itself |
| Component gates | G1-G6 unit, fixture, and mutation suites | Calculator and evaluator behavior | Outcome superiority |
| Apps Eval regression | python -m apps_eval run-matrix --app apps_rg --split dev --mode snapshot --deterministic-only | Development regression signal | P1, P2, or human qualification |
| P1 pilot | Blinded, independently reviewed calibration pairs plus adjudication | Calibrated utility measurement | Protected-holdout result |
| P2 pilot | Source-bound attempt ledger across complete/failed/abstained runs | End-to-end denominator and operational measurement | Release authority |
| Protected holdout | Operator-authorized, frozen cohort execution | Qualified outcome estimate if all gates complete | Production authorization |
| Release | Named approver, threshold receipt, catalog validation | Release authorization | Production change authorization |

## 6. Delivery order and human gates

1. Complete P0-P3 and their deterministic tests before collecting or using any
   human labels.
2. Obtain approval of the P1 rubric, P2 completion definition, cohort slices,
   reviewer protocol, and calibration plan.
3. Run the calibration cohort, validate evaluator-human agreement, and freeze
   thresholds and the holdout commitment.
4. Obtain authorized independent reviews and adjudications; do not infer them
   from a single owner or an empty template.
5. Run P1/P2 and G1-G6 on protected holdout exactly once under the frozen
   protocol.
6. Require a named release decision after all qualified evidence is present.
   Production activation remains a separately authorized action.

## 7. Definition of done

This work is complete only when:

- every real pipeline stage and every generated lane has an auditable,
  source-bound measurement mapping;
- P1 and P2 have valid numerator, denominator, cohort, slice, uncertainty,
  threshold, and authority definitions;
- P1 and P2 are populated only from frozen, authorized evidence;
- G1-G6 are demonstrably sensitive to intended defects and remain diagnostic;
- all safety guardrails are fail-closed and cannot be compensated by a quality
  score;
- calibration, holdout, release, and production authority remain distinguishable
  in both code and receipts; and
- a change to source, pipeline, model, evaluator, corpus, or threshold invokes
  the specified recertification path.

Until then, the correct status is technical validation and/or NOT_MEASURED, not
human qualification, release authorization, or production authorization.
