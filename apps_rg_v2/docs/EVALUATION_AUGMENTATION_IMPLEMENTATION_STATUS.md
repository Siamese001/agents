# Apps RG evaluation augmentation implementation status

**Status:** technical controls implemented; primary-outcome qualification remains
`NOT_MEASURED` until frozen cohort evidence and authorized human review exist.
Nothing in this document authorizes release or production.

## Decision model

Apps RG has two primary outcomes, deliberately separated from diagnostic gates,
guardrails, and development regression:

| Metric | Unit and denominator | Current authority |
| --- | --- | --- |
| P1 — blinded finished-resume utility delta | Every completed eligible candidate-versus-frozen-baseline pair in a frozen review cohort | Technical ledger validation only; independent human qualification still required |
| P2 — grounded decision-ready completion rate | Every eligible Apps Research-to-U0 attempt, including COMPLETE, FAILED, and ABSTAINED outcomes | Technical attempt-ledger validation only; human-qualified P2 remains unmeasured |
| G1–G6 and guardrails | Bound diagnostic and safety evidence for the relevant pipeline elements | Diagnostic/guardrail evidence; never a compensating outcome score |
| Apps Eval regression | Development fixture and snapshot regression signal | Regression diagnostic only |

The evaluator does not blend these measures into one scalar and does not infer
human labels from tests, model judgments, or technical receipts.

## Delivered controls

### Pipeline coverage contract

`src/apps_rg/evals/contracts/pipeline_measurement_coverage.v1.yaml` maps the
current runtime contracts to P1, P2, G1–G6, and the three critical guardrails.
The validator derives the actual pipeline surface from the live lane and
microstep registries, then fails closed if a stage, artifact role, authority
classification, direct primary-outcome link, or required metric is absent.

The current contract has 17 declared pipeline elements and expands lane-scoped
rows across all 11 generated lanes. A registry change therefore requires an
explicit measurement decision before the coverage check can pass.

### P2 source-bound attempt ledger

`src/apps_rg/evals/pipeline_attempt_evaluation.py` and its schema make the P2
denominator auditable without executing or mutating the runtime. A populated
ledger requires:

- a frozen calibration or holdout cohort and an exact member-ID digest;
- the current coverage and source-contract digests;
- one attempt per frozen member, including explicit governed exclusions;
- a validated Apps Research-to-U0 handoff, runtime provider/model/config/cache
  identity, input digest, and explicit slice values for eligible attempts; the
  cohort split and provider/model/cache/configuration slice fields must equal
  the recorded identity rather than being free-form labels;
- every declared stage/lane evidence row, with artifact digests and reason codes;
- terminal failure or abstention evidence at the declared terminal stage;
- G1–G6 and guardrail receipt references with the authority tier required by the
  coverage contract; and
- denominator conservation: eligible = complete + failed + abstained.

An excluded case remains in the frozen population with a reason, but is not in
the eligible P2 denominator. Optional trace reconciliation can be explicitly
`NOT_RUN`; required P2 elements cannot silently disappear.

The benchmark cohort validator now requires calibration cases to carry distinct
source-family, profile, job-description, request, research-handoff, baseline,
and candidate-output digests, as well as prompt and runtime configuration
digests. A valid Apps Research handoff receipt must bind to the case’s recorded
research digest. The protected-holdout commitment remains opaque to development
commands.

`src/apps_rg/evals/e2e_operational_evaluation.py` now also records `ABSTAINED`
attempts and retains them in the operational completion denominator. COMPLETE,
FAILED, and ABSTAINED terminal fields are mutually exclusive and are checked
against their stage lineage. Its operational report keeps latency, cost, tokens,
retries, provider errors, cold/warm mix, and failure/abstention stage
distributions as separate measures so a good latency or cost value cannot mask
a grounded-completion or guardrail failure.

### P1 blinded-review ledger

`src/apps_rg/evals/whole_resume/p1_blind_utility.py` validates a sealed P1
review ledger. Each frozen pair binds a source attempt, distinct baseline and
candidate output digests, blind packet digest, exact two independent primary
reviews, and one independent adjudication. Reviews carry blinded A/B/TIE
preferences only; the trusted adjudication resolves CANDIDATE/BASELINE/TIE.
Every review and adjudication has an identity digest, timestamp, rationale,
source locator, packet binding, and content digest.

`src/apps_rg/evals/finished_resume_outcome.py` now requires a completed P1
manifest to point to that ledger by safe relative path and file digest. It
recomputes and checks pair, review, adjudication, preference, and utility-margin
aggregates against the ledger. A material candidate regression, stale lane
contract, altered review file, duplicate reviewer, or aggregate mismatch blocks
the P1 receipt. The outcome still requires a genuine external human-authority
receipt before it can be anything other than technical validation.

### Evaluator-validity coverage

`src/apps_rg/evals/evaluator_validity_registry.v1.json` now explicitly tracks
the independent material-claim reconciliation, benchmark cohort design,
pipeline coverage map, P1 review ledger, and P2 attempt ledger. These entries
remain `NOT_MEASURED` until their clean controls, defect mutations, and required
human-pilot evidence are completed. A P1 or P2 assembler cannot silently escape
the G6-style registry.

The qualification receipt catalog now verifies that a receipt’s own authority
flags support the authority tier declared by the catalog entry. In particular,
a technical P1/P2 ledger with `human_qualified: false` cannot be relabeled as a
human-qualified result through catalog metadata.

## Remaining governed work

The following is intentionally not fabricated by this implementation:

1. Freeze real calibration cohorts, source-family isolation, and the protected
   holdout commitment under the authorized access process.
2. Populate the P1 ledger with independent blinded human reviews and
   adjudications, then supply a real human-authority receipt.
3. Populate P2 attempts from real source-bound runs, including document
   parse-back, operational, G1–G6, and guardrail receipts.
4. Bind the existing independent material-claim reconciliation to real final
   output receipts and complete its clean-control and defect-mutation evidence
   before G2/G3 can carry release-sensitive weight.
5. Calibrate and preregister P1/P2 intervals, thresholds, slice policy, and
   holdout decision rules before any protected-holdout execution.
6. Validate all release-affecting graders with clean controls and targeted
   mutations, then obtain separately named qualification, release, and
   production decisions.

## Verification

Run the narrow technical checks from the repository root:

```text
library API: apps_rg.evals.pipeline_measurement_coverage
library API: apps_rg.evals.pipeline_attempt_evaluation
library API: apps_rg.evals.whole_resume.p1_blind_utility
python -m pytest -q src/apps_rg/evals/tests/test_pipeline_measurement_coverage.py src/apps_rg/evals/tests/test_pipeline_attempt_evaluation.py src/apps_rg/evals/tests/test_e2e_operational_evaluation.py src/apps_rg/evals/tests/test_finished_resume_outcome.py src/apps_rg/evals/tests/test_success_metrics.py src/apps_rg/evals/tests/test_receipt_catalog.py src/apps_rg/evals/whole_resume/tests/test_p1_blind_utility.py
```

The two empty tracked ledgers deliberately return `NOT_MEASURED` with a nonzero
CLI status until real evidence is supplied. That is the intended fail-closed
posture, not a failed attempt to manufacture qualification.
