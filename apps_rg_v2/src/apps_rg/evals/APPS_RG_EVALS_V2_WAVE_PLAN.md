# Apps RG Evaluations v2 — scoped wave plan

**Branch:** `codex/apps-rg-evals-v2`
**Status:** planning only; no evaluator behavior has changed in this document.
**Public entry point:** `python -m apps_rg run` (and its `eval` subcommand).
**Scope:** make the Apps RG evaluation result accurately measure: (1) whether a
real whole-resume run was evaluated, (2) whether the delivered resume violates
deterministic truth/safety/structure rules, and (3) whether evaluation itself is
trustworthy.  Keep uncalibrated prose-quality judgement advisory.

## Why this work is needed

The 2026-08-17 Anthropic Partnership run proved that the current post-run
evaluation result is internally contradictory:

- Apps Eval emitted 137 required rows: 24 `PASS`, 113 `FAIL`; 110 failures
  were `evidence.source_identity_missing`.
- The release-path evaluator indexes `modular_r4/sections`, while the public
  whole-resume CLI writes `lanes/<lane>`.
- L6 reports no bound Apps Eval rows, but ledger compatibility stages can still
  pass.
- `post_x3_completion` records evaluation quality but currently completes the
  pipeline when evaluation and L6 merely executed.
- `python -m apps_rg eval` currently verifies package/ledger readability rather
  than the substantive Apps Eval and L6 verdicts.

Those failures mean the evaluation is **invalid**.  They do not establish that
the resume has 113 content defects.  V2 must report that distinction precisely.

## Scope and non-goals

In scope:

- `src/apps_eval` Apps RG adapter, coverage, scorecard, and package contracts.
- Apps RG post-X3, L6, terminal ledger, CLI `run`/`eval`, and their direct tests.
- New, versioned evaluation artifacts and deterministic replay.
- A future qualification path for semantic claim entailment and resume quality.

Out of scope for this branch until a separate approved wave:

- Changing candidate facts, graph retrieval/ranking, resume prompts, or resume
  content merely to improve an eval score.
- Changing Apps Research handoff semantics, UWG authorization policy, or the
  provider roster used for generation.
- Adding a DOCX product requirement; the current public product is the final
  JSON and text outputs.
- External signing infrastructure.  The local-host V2 threat model uses
  allowlisted paths, hashes, containment, and independent re-read.  Add an
  external witness only when artifacts cross a machine/operator/storage boundary.
- A second public CLI.  `apps_eval` becomes an importable library surface; any
  replay/rejudge action remains under `python -m apps_rg`.

## Target decision model

V2 has four independent planes.  No scalar blends their rows into a release
decision.

| Plane | Question | Initial authority |
| --- | --- | --- |
| Execution integrity | Did the expected real provider run produce the exact required artifacts? | blocking |
| Deterministic product correctness | Are exact claims, policy rules, structural rules, and delivered files correct? | blocking |
| Semantic factuality and resume utility | Does a paraphrase preserve ownership/scope/outcome? Is the resume strong for the JD? | material factuality requires qualified evidence or review; utility is advisory until qualified |
| Evaluation assurance | Did Apps Eval and L6 independently inspect the same frozen inputs and agree on deterministic results? | blocking |

Every terminal evaluation record exposes, at minimum:

```text
execution_status
package_integrity_status
evaluation_validity
deterministic_product_status
semantic_factuality_status
quality_advisory_status
l6_integrity_status
pipeline_complete
```

Terminal disposition values are `PASS`, `PRODUCT_FAIL`, `REVIEW_REQUIRED`,
`EVALUATION_INVALID`, and `EVALUATION_ERROR`.

`product_authorized` remains the immutable prior UWG decision.  It is never
retroactively rewritten by post-authorization evaluation.  A failed or invalid
evaluation does, however, force `pipeline_complete=false` and a non-success CLI
exit.

## Wave 0 — contracts and regression characterization

**Goal:** freeze the V2 semantics before repairing implementations.

Deliverables:

1. `apps_rg.evaluation_decision.v2` schema with the fields above, status
   definitions, reason codes, and precedence.
2. A versioned evaluation-input artifact-role contract with `lanes/<lane>` as
   the release-path layout; legacy `modular_r4/sections/<lane>` is explicitly
   compatibility-only.
3. A single terminal-decision derivation specification used by post-X3,
   ledger, pipeline completion, `apps_rg run`, and `apps_rg eval`.
4. Regression tests that reproduce the current contradiction: a readable,
   sealed package with `failed_required > 0` or `apps_eval_rows_bound=false`
   must not return `PASS` or `pipeline_complete=true`.

Acceptance:

- Tests distinguish product defect, evaluator invalidity, and evaluator error.
- No existing artifact is rewritten to appear V2-compliant.
- No provider call is required.

## Wave 1 — frozen evaluation input and lane identity

**Goal:** make it possible to prove exactly which product bytes were evaluated.

Apps RG emits `candidate_evaluation_manifest.v2.json` after final assembly and
product-authorization close, before Apps Eval.  It is an allowlist, not a
recursive directory inventory.  It binds:

- canonical run/request/JD/candidate-evidence/runtime-exhaust identities;
- final JSON and text output paths and hashes;
- all eleven lanes, with lane ID, attempt ID, artifact role, relative path,
  schema, byte length, SHA-256, and upstream identity;
- X1, X2, X3, whole-run exit, UWG, and authorization receipts;
- evaluator contract and rubric versions.

Each lane emits a hash-bound lane evidence manifest.  Individual historical
receipts need not all duplicate every run identifier, but every evaluated file
must be bound by hash to the lane manifest and its parent/child/attempt/
runtime-exhaust identity.

Apps Eval then emits its own `apps_eval_intake_manifest.v2.json` after
independently re-reading contained source files, verifying hashes, schemas,
role uniqueness, and identity propagation.  A producer-provided manifest is
never self-certifying.

Acceptance:

- A `lanes/<lane>`-only run resolves all required artifacts.
- Cross-run lane splicing, duplicate roles, absolute paths, `..`, junction/
  symlink escapes, and hash changes produce `EVALUATION_INVALID`.
- A stale legacy directory cannot override a canonical lane artifact.

## Wave 2 — deterministic Apps Eval redesign

**Goal:** evaluate the delivered resume rather than receipt existence.

Replace heterogeneous release scoring with separate natural-grain scorecards:

1. **Run and artifact scorecard:** real-provider execution, required stages,
   manifest coverage, identity, hash, schema, and source containment.
2. **Exact-fact scorecard:** employer, title, date, number, credential, named
   partner, and other structured material fact against candidate evidence.
3. **Document scorecard:** required sections, final JSON/text agreement,
   required output presence, and prohibited-content rules.
4. **Claim scorecard:** atomic claims extracted from rendered final text,
   stable claim IDs, source bindings, exact-value comparisons, and a material
   semantic-transform classification.
5. **JD opportunity scorecard:** coverage of evidence-supported JD requirements;
   never reward asserting unsupported JD requirements or raw keyword coverage.

Exact fact, policy, output, and structural failures are `PRODUCT_FAIL`.
Missing identity, unavailable required input, non-running row, or ambiguous
artifact resolution is `EVALUATION_INVALID`.

Material transformations of ownership, causality, scope, or outcome are not
declared grounded merely because an evidence ID exists.  They are
`SUPPORTED`, `CONTRADICTED`, or `REVIEW_REQUIRED`.  Before a semantic entailment
evaluator is qualified, `REVIEW_REQUIRED` prevents automatic product success;
it is not mislabeled as fabrication.

Acceptance:

- No aggregate score determines release.
- Every blocking finding cites a stable rendered claim and immutable source
  binding.
- Faithful formatting/paraphrase controls pass; injected metrics, titles,
  dates, credentials, partner claims, and JD-only capabilities fail with the
  exact affected claim.

## Wave 3 — judge receipts and quality advisory

**Goal:** make model-backed review auditable without granting uncalibrated
quality authority.

For each model judge, bind exact serialized prompt/request bytes, complete
resume, JD, evidence packet, rubric, provider/model, inference settings,
output schema, parser version, raw response bytes, and cited sentence IDs.
No truncation may omit an evaluated portion of the resume or JD from the input
digest.

Judge outputs must include per-dimension scores, confidence/abstention,
findings, valid sentence citations, and evidence IDs for factual findings.
Untrusted resume, JD, and evidence text are delimited as data; injection
canaries are part of the evaluator test suite.  Generator self-judging remains
disallowed.

Initial live quality dimensions are advisory only:

- evidence-supported role fit;
- executive positioning and coherence;
- readability, density, and non-repetition;
- JD mimicry risk and recruiter utility.

An advisory judge cannot convert a deterministic product pass into fail, or a
deterministic product fail into pass.  Evidence-free, malformed, unavailable,
or wrong-model judge output is an evaluation validity/error issue, never a
silent passing vote.

Acceptance:

- Changing resume bytes after any former truncation boundary changes the judge
  input digest.
- Citation, prompt injection, malformed JSON, quorum loss, provider timeout,
  and wrong-model mutations cannot produce a passing judge receipt.

## Wave 4 — independent L6 evaluator assurance

**Goal:** ensure Apps Eval is not validating its own blind spots.

L6 consumes the frozen candidate evaluation manifest through an implementation
independent of the Apps Eval path resolver, snapshot normalizer, row builder,
and verdict calculator.  It:

1. reopens the allowlisted paths;
2. recomputes containment, hashes, identities, required inventory, and
   deterministic observations;
3. only then reads Apps Eval rows;
4. compares check inventory, input-manifest digest, source hashes, observed
   values, thresholds, and deterministic verdicts.

L6 does not independently score prose quality and cannot rescue a failed Apps
Eval.  It validates evaluator integrity.

Acceptance:

- A seeded Apps Eval resolver bug is detected by L6.
- `L6_SHADOW=PASS` only with a complete independent closure.
- `INDEPENDENT_PARITY=PASS` only with exact source and deterministic-result
  agreement; microstep-ID presence is insufficient.

## Wave 5 — terminal, replay, and sole CLI behavior

**Goal:** make public runtime status match the evaluation decision.

Stage semantics:

1. `PRODUCT_AUTHORIZATION_CLOSE` records the prior immutable UWG decision.
2. `APPS_EVAL` passes only when evaluation is valid and all deterministic
   blocking product checks pass; it is `FAIL`, `BLOCKED`, or `ERROR` otherwise.
3. `L6_SHADOW` passes only with independent closure.
4. `INDEPENDENT_PARITY` passes only with V2 byte/identity/result agreement.
5. `PIPELINE_COMPLETION_CLOSE` sets `pipeline_complete=true` only when all
   required terminal, evaluation, L6, parity, output, and seal gates pass.

The sole public CLI exposes these exit codes:

```text
0  E2E_PASS
2  PRODUCT_FAIL_OR_REVIEW_REQUIRED
3  EVALUATION_INVALID
4  EXECUTION_OR_EVALUATOR_ERROR
```

Precedence is `4 > 3 > 2 > 0`.  The inline `EVALS` output must report the full
decision vector, blocking reason codes, and advisory count rather than merely
package-seal status.

`python -m apps_rg eval` is a read-only, zero-provider replay.  It reopens the
frozen V2 inputs, reparses sealed judge responses, recomputes deterministic
checks into a separate replay artifact directory, and compares decision
digests.  A provider rejudge creates a new evaluation record and never
overwrites the original; it is not part of the initial public CLI contract.

Acceptance:

- A sealed evaluation with substantive failures cannot yield CLI success.
- Replay makes zero provider calls and does not modify the original product or
  evaluation package.
- No executable `apps_eval` module remains as an alternate public product path.

## Wave 6 — human qualification and future quality promotion

**Goal:** earn authority for semantic entailment and utility measurement.

Create frozen, blinded benchmarks with separate reviewer roles:

- evidence auditors for factual entailment;
- recruiters/hiring managers for role-specific utility;
- resume specialists for readability and document quality.

Use two independent assessments plus adjudication.  Preserve and report
pre-adjudication disagreement using an ordinal-appropriate metric (weighted
kappa or Krippendorff's alpha).  Separate development, validation, and hidden
holdout by candidate/source family and target company so related cases cannot
leak across splits.

The benchmark must include normal cases, unsupported-JD traps, fabricated claim
mutations, evidence-poor cases, partner/ownership/scope transformations,
supported paraphrases, prompt injections, and protected-attribute
counterfactuals.

Sample size is calculated per pre-registered endpoint.  The existing 393-pair
design is retained only if its stated paired-utility assumptions remain.  Rare
catastrophic false-pass claims use one-sided binomial confidence bounds; judge
calibration uses sufficient positives and negatives in every required slice.

Only a frozen combination of rubric, model, prompt, evidence projection,
parser, threshold, and human-calibration record may promote a semantic or
quality result from advisory to blocking.  Any change to those components
requires requalification.

## Cross-wave acceptance suite

The required regression suite covers:

1. live lane layout and legacy-layout isolation;
2. source containment and Windows path aliasing;
3. cross-run artifact splice and post-seal mutation;
4. required identity omission classification;
5. claim-census evasion through headings, tables, terse fragments, and compound
   bullets;
6. fabricated exact facts and supported-paraphrase controls;
7. final-assembly divergence from otherwise valid lane evidence;
8. prompt-injection, missing-citation, and malformed-judge cases;
9. L6 common-mode resolver fault;
10. zero-provider replay and no-mutation proof;
11. substantive Apps Eval/L6 failure preventing `pipeline_complete=true`.

## Final implementation proof

After Waves 0–5 pass focused deterministic and integration tests, run one fresh
Anthropic Partnership `python -m apps_rg run`.  It is complete only when the
inline output and sealed receipts agree on:

```text
product_authorized=true
pipeline_complete=true
execution_status=PASS
evaluation_validity=PASS
deterministic_product_status=PASS
semantic_factuality_status=PASS
l6_integrity_status=PASS
```

Then execute the zero-provider `python -m apps_rg eval` replay and require the
same deterministic decision digest.  Do not mutate or relabel historical runs
to satisfy this proof.
