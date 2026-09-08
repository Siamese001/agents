# Apps RG evaluation contracts

This directory is import-only. It does not expose a `library API: apps_rg.evals.*`
CLI; the sole product command is `python -m apps_rg run`, which invokes the
current-run Apps Eval integration as part of full E2E completion.

`apps_rg/evals` evaluates sealed Apps RG artifacts. It does not launch the
resume-generation runtime, change retrieval, or authorize a release merely by
producing a score.

The versioned measurement contract is
[`contracts/evaluation_contract.v2.yaml`](contracts/evaluation_contract.v2.yaml).
It keeps six evaluation questions independent:

| Gate | Question | Current implementation state |
| --- | --- | --- |
| G1 - Retrieval | Did the graph retrieve the most relevant available evidence? | Active; legacy W6 metrics are preserved and the finite-universe API adds coverage, hard-negative, and slice results. |
| G2 - Binding | Was evidence bound to the correct employer, role, date, metric, credential, and graph path? | Active; the claim-evidence API verifies seven exact binding dimensions and graph paths. |
| G3 - Grounding | Is every material generated claim supported by exact cited evidence? | Active; the material-claim API recomputes support and fails closed on incomplete evidence. |
| G4 - Output quality | Is the resume relevant, natural, concise, credible, ATS-compatible, and personalized? | Active; five section lanes plus sealed whole-resume and six-pair W9 evaluation are implemented. |
| G5 - Robustness | Is behavior acceptable across stored runs and difficult evidence scenarios? | Active; eleven governed scenarios require at least three distinct sealed execution receipts and separate decision stability from prose variation. |
| G6 - Eval validity | Do the graders catch known defects without rejecting clean controls? | Active for machine-critical G1/G2/G3 graders; authorized human/judge agreement remains explicitly unmeasured pending a real pilot. |

## Result semantics

Every gate emits exactly one state:

- `PASS`: all required evidence exists and the gate's governed criteria pass.
- `FAIL`: sufficient evidence exists and at least one governed criterion fails.
- `UNKNOWN`: the gate should be measurable, but required evidence is missing,
  invalid, untrusted, or insufficient.
- `NOT_MEASURED`: the gate is outside the declared measurement coverage of the
  report or has no implemented measurement lane.

Missing evidence never becomes `PASS`. `UNKNOWN` is distinct from
`NOT_MEASURED`, and neither state is release-authorizing.

## Score groups

Reports use the following named groups without calculating a blended overall
score:

- `retrieval_quality`
- `binding_accuracy`
- `factual_grounding`
- `section_quality`
- `whole_resume_quality`
- `runtime_repeatability`
- `evaluator_validity`

The report schemas require all six gates and all seven score groups to be
present. An unavailable lane is represented explicitly as `UNKNOWN` or
`NOT_MEASURED`; it is not omitted.

## W0 success metrics and U0 admission

[`contracts/success_metric_contract.v1.yaml`](contracts/success_metric_contract.v1.yaml)
adds the outcome layer that the G1-G6 diagnostic gates do not supply on their
own. It defines two non-blended outcomes: blinded finished-resume utility over
a frozen baseline (P1), and the rate of eligible end-to-end attempts that
produce a grounded, decision-ready result (P2). Neither is measured by W0;
both remain explicitly `NOT_MEASURED` until their governed human-review and
full-denominator lanes exist.

W0 records Apps Research as a mandatory pre-U0 admission prerequisite. The
non-mutating `success_metrics.py` evaluator consumes the already-produced
`apps_rg.apps_research_handoff_validation_receipt.v2`: missing validation is
`UNKNOWN`, an observed invalid handoff is `FAIL`, and only an observed valid
handoff is `PASS`. That PASS merely makes a run eligible for the P2
denominator; it cannot make P1, P2, a guardrail, release, or production pass.
Its `success_metric_receipt.v1.schema.json` receipt is always technical-only,
non-promoting, and keeps G1-G6 diagnostic-only.

## W1 receipt catalog

`library API: apps_rg.evals.receipt_catalog` reads the tracked
`receipt_catalog_manifest.v1.json` and emits one fail-closed qualification
summary. The catalog keys every entry by input digest, evaluator version, data
split, runtime-configuration digest, and authority tier. It requires one
compatible holdout receipt for G1-G6, P1/P2, and each critical guardrail before
reporting `PASS`; it still never authorizes release or production.

`apps_eval` records can appear only as `regression_diagnostic` entries. A green
snapshot/regression record therefore remains visible in the summary but cannot
replace authoritative human-qualified receipts. Missing evidence emits
`NOT_MEASURED`; duplicate, stale/tampered, incompatible, or under-authorized
receipts emit `BLOCKED`.

## W2 benchmark and holdout design

`library API: apps_rg.evals.benchmark_design` validates the tracked W2 case
manifest without loading any holdout case identity. Calibration cases must use
distinct source bundles, target requests, and expected outputs; cover every
runtime-generated lane and each declared role, target-profile, evidence-density,
hard-negative, binding, and protected-risk slice; and carry a valid Apps
Research-to-U0 validation receipt. The protected holdout is represented only by
an external authority reference, sealed-index digest, and count, so development
code cannot access its case IDs.

The manifest pre-registers a paired normal-approximation power calculation. A
missing holdout seal or sample size reports `NOT_MEASURED`; duplicate cases,
holdout-identity exposure, invalid Apps Research admission, and an underpowered
plan report `BLOCKED`. This benchmark-design receipt is technical-only and does
not create human qualification, release, or production authority.

## W3 human truth and material-claim authority

`material_claim_authority.py` independently splits every rendered sentence or
bullet into a material candidate, then requires one exact system-claim record
for each candidate. Each record must bind a rendered-text locator, source ID,
source excerpt digest, and graph-path ID before it can be handed to the existing
source-byte and graph-path grounding evaluator. An omitted rendered statement,
duplicate locator, altered claim text, or incomplete evidence binding fails
closed.

`library API: apps_rg.evals.material_claim_authority` also reads the tracked W3
human-truth manifest. QREL and proof review each require two independent human
reviews and one adjudication per item, and synthetic grades are forbidden. The
tracked manifest deliberately remains `NOT_MEASURED` pending externally pinned
completed review/adjudication receipts; neither this readiness check nor an
inventory reconciliation creates human qualification or release authority.

## W4 finished-resume outcome

`library API: apps_rg.evals.finished_resume_outcome` enforces P1 at the complete
finished-resume level. It requires a frozen baseline, blinded pairs, two
independent primary reviews and one adjudication per pair, all 11 runtime lanes,
strictly positive utility effect and lower confidence bound, and more candidate
than baseline preferences. Ties cannot establish superiority. Authenticity,
grounding, ATS, readability, concision, and target relevance each require a
preregistered non-inferiority margin and interval.

Owner-solo review is recorded only as a complementary signal. A passing
technical summary remains non-release-authorizing until the referenced human
authority and completed-review receipts are independently verified.

## W5 evaluator criterion validity

`library API: apps_rg.evals.evaluator_validity_registry` inventories every
release-affecting evaluator: G1-G5, ATS/document, Apps Research-to-U0, privacy,
fairness, operational, and the post-Exit judge. Each versioned card requires a
mutation-suite version, declared slices, an externally referenced authorized
human pilot, and preregistered critical-false-pass and false-fail upper bounds.
The validator computes Wilson upper bounds from the pilot counts rather than
accepting a supplied rate.

Every tracked card remains `NOT_MEASURED` until that evidence exists. Synthetic
human labels block the registry, and even a technically complete card registry
does not independently authorize human qualification, release, or production.

## W6 source-bound operational and document evidence

`library API: apps_rg.evals.e2e_operational_evaluation` reads a ledger of actual
Apps Research-to-U0-to-Exit attempts. Every attempt has a pinned Apps Research
handoff receipt, runtime/provider identity, ordered stage lineage, retry/token/
cost/latency fields, and either a complete all-lane result or an explicit failed
stage and failure code. Failed attempts remain in P2's completion denominator;
they cannot be omitted to improve an SLO.

For completed attempts the ledger requires all runtime lanes and digest-bound
PDF/DOCX render records. Source text must match both parsed renderings, section
order must be verified, and overflow must be zero. PII leaks, authority bypass,
or a failed counterfactual check fail the technical receipt. The tracked
manifest deliberately contains no attempts or SLO values and is therefore
`NOT_MEASURED` until a real source-bound execution is captured. A passing W6
technical receipt still does not create human qualification, release, or
production authority.

## W7 frozen protected-holdout qualification

`library API: apps_rg.evals.protected_holdout_qualification` validates the sealed
W7 receipt. Before protected-holdout access it fingerprints source commit,
metric/data files, provider-model pins, candidate and baseline configuration,
decision rules, and the holdout index. A changed file or source commit produces
`STALE_SCOPE`; it cannot be reused. The preregistration timestamp must precede
holdout access, and a complete evaluation may expose the holdout exactly once.

The receipt also requires P1/P2 intervals, G1-G6, zero-tolerance guardrails,
slice results, and paired or randomized ablations for retrieval, grounding,
section generation, and whole-resume assembly. The tracked receipt is pending;
no holdout result, human label, or release authorization is supplied by code.

## W8 shadow, canary, rollback, and promotion

`library API: apps_rg.evals.shadow_canary_promotion` validates source/model/
provider/graph identity against the W7 receipt before it evaluates shadow or
bounded-canary observations. Identity drift emits `STALE_SCOPE` and requires a
new qualification. The receipt measures traffic and window coverage, P1/P2
proxies, cost, stage failures, latency and error deltas, source/target/query
distribution drift, reviewer disagreement, zero-tolerance guardrails, slices,
and a digest-bound rollback rehearsal.

Technical monitoring can become `TECHNICALLY_QUALIFIED_NOT_AUTHORIZED`, never
production-authorizing by itself. `PROMOTION_AUTHORIZED` additionally requires
a separately bound `human-promotion-authority://` receipt. The tracked W8
manifest is pending and contains neither traffic observations nor authority.

## Authority boundary

This contract is declarative. It does not change the existing W6 authority,
the six-pair W9 prerequisite contract, current-run release authority, or the
future-run-only threshold-promotion rule. Model judges remain advisory until
calibrated against authorized human review. The existing
`resume_graph_evaluation.py` and `c03_w9_closeout.py` entry points retain their
current behavior. `c03_ci_ratchet.py` retains its legacy JUnit-only API and can
additionally fail closed over seven normalized sealed score-group receipts.

Schemas:

- [`schemas/evaluation_gate_result.v1.schema.json`](schemas/evaluation_gate_result.v1.schema.json)
  defines one named gate result.
- [`schemas/evaluation_report.v2.schema.json`](schemas/evaluation_report.v2.schema.json)
  defines a complete, non-blended report over G1-G6.
- [`schemas/claim_evidence_record.v1.schema.json`](schemas/claim_evidence_record.v1.schema.json)
  freezes one material claim, exact locator, path, entailment, and factual
  bindings. Additional runtime-authored support flags are rejected.
- [`schemas/retrieval_universe.v1.schema.json`](schemas/retrieval_universe.v1.schema.json)
  freezes one query and every candidate in its finite labelled universe.
- [`schemas/ci_gate_receipt.v1.schema.json`](schemas/ci_gate_receipt.v1.schema.json)
  defines the normalized sealed score-group boundary consumed by the CI
  ratchet.

## Grounding, binding, and retrieval APIs

`apps_rg.evals.resume_graph` exports the Wave 3 entry points:

- `seal_claim_evidence_record` and `evaluate_claim_evidence` operate on one
  claim-evidence record. `evaluate_binding_gate` and `evaluate_grounding_gate`
  emit independent G2 and G3 dispositions over the same complete denominator.
- `seal_retrieval_query` freezes the candidate denominator.
  `evaluate_retrieval_query` preserves Recall and nDCG at 1, 3, 5, and 10,
  adds coverage and hard-negative metrics, and never evaluates only emitted
  Top-K. `evaluate_retrieval_gate` requires distinct calibration and holdout
  sets and reports governed slices.

The deterministic rubrics live in
[`contracts/grounding_binding_rubric.v1.yaml`](contracts/grounding_binding_rubric.v1.yaml)
and
[`contracts/retrieval_coverage_rubric.v1.yaml`](contracts/retrieval_coverage_rubric.v1.yaml).
They are future-run-only measurement rules; they do not promote thresholds or
change runtime delivery authorization.

## Section quality benchmark

[`section_quality_benchmark/`](section_quality_benchmark/) provides the active
five-lane offline G4 section evaluator. It consumes sealed artifacts and
completed absolute or blinded pairwise reviews, keeps human and model-judge
results separate, and emits no runtime or release authority. Whole-resume and
W9 scoring remain outside this section benchmark and are measured separately
below.

## Whole-resume and W9 evaluation

[`whole_resume/`](whole_resume/) calculates substantive whole-resume metrics and
the three governed human no-worse decisions over exactly six blinded W9 pairs.
Its sealed receipt feeds the existing `c03_w9_closeout.py` prerequisite checker;
neither component launches the runtime or changes current-run release authority.

## Stored-run robustness

[`repeatability/`](repeatability/) implements G5 over already-completed sealed
runs. It never launches Apps RG. The governed registry covers rich and sparse
evidence, ambiguity, binding collisions, unsupported requests, prompt
injection, inflation requests, and legitimate omission. At least three
distinct execution identities and receipt digests are required per scenario;
copying a run directory cannot satisfy independence. Evidence, bindings,
grounding, dispositions, semantic section decisions, quality scores, and raw
wording variation are reported separately. Any critical grounding or final
disposition divergence fails.

## Evaluator validity and CI ratchet

[`meta_eval/`](meta_eval/) implements the machine-critical part of G6 by
running the real G1/G2/G3 graders against clean controls and controlled defects.
It covers hard-negative promotion, relevant evidence outside Top-K,
calibration/holdout leakage, exact-binding mutations, unsupported entailment,
source removal, digest tampering, and wrong graph paths. Critical grounding and
provenance mutation recall must be 1.0 and clean-control false-positive rate
must be at most 0.05. Human-grader, judge-human, reviewer, and adjudication
agreement remain `null` until an authorized pilot; the receipt cannot freeze
those thresholds or authorize release.

The optional sealed-receipt mode in `c03_ci_ratchet.py` requires exactly the
seven named score groups and validates each digest, status, baseline signature,
and governed failure counter. Missing receipts, invalid digests, required
`UNKNOWN`, critical regression, unsupported material claims, holdout leakage,
mutation failures, and unexpected baseline signatures fail the ratchet. This
is an evaluator-owned aggregation surface only; workflow files are unchanged.

## Source-bound authoritative path

The evaluators above remain useful calculators and synthetic regression
surfaces. Real measurement uses
[`authoritative/`](authoritative/README.md), which prevents the scorer from
creating its own truth, reviewer authority, execution independence, or CI
source receipts. The implementation and remaining real-evidence prerequisites
are recorded in
[`MEASUREMENT_VALIDITY_PLAN.md`](MEASUREMENT_VALIDITY_PLAN.md).
The code-only completion and validation commands are sealed in
[`MEASUREMENT_VALIDITY_IMPLEMENTATION_RECEIPT.json`](MEASUREMENT_VALIDITY_IMPLEMENTATION_RECEIPT.json).
