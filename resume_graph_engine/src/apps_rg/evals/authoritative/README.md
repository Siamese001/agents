# Source-bound Apps RG evaluation

This package is the authoritative measurement path for Apps RG v2. It compares
actual system artifacts with independently pinned truth and rejects self-sealed
authority. It does not contain human labels and cannot authorize release by
itself.

## Trust model

An internal record digest proves integrity only. Authoritative evaluation also
requires the expected digest or file SHA-256 from the caller. Human review uses
the existing C0.3 owner-only authority receipt and verifies roster, cohort,
role, qualification, and identity hashes.
Truth rows bind review coverage for both rostered reviewers and the rostered
adjudicator; a bundle-level participant list alone is insufficient.

The principal APIs are:

- `evaluate_authoritative_retrieval`: independent universe + system ranking +
  completed QRELs.
- `evaluate_authoritative_cluster_retrieval`: cluster-only candidate identities,
  exact graph/registry/corpus/model/projection/query/runtime bindings, a bounded
  production `top_k`, and completed QRELs. Wave 1 remains non-release-authorizing.
- `build_cluster_qrel_prelabel_packet`: builds a deterministic blinded reviewer
  packet plus a separately sealed identity/split manifest. It creates no labels,
  QRELs, evaluation result, or release authority.
- `validate_completed_cluster_qrel_reviews`: requires two distinct rostered human
  reviewers and an independent rostered human adjudicator for every blinded
  query/candidate item. Unknown or incomplete judgments are non-passing.
- `evaluate_cluster_authority_pipeline`: compares pinned runtime rehydration and
  allocation traces with the current graph, cluster registry, and completed
  grounding receipt. It enforces zero authority, lifecycle, section, policy,
  facet-collapse, and unsupported-claim violations.
- `evaluate_cluster_runtime_quality`: evaluates at least three cold and three
  warm observations for bounded-k compliance, rank and rehydration determinism,
  reported p50/p95 latency against caller-pinned p95 ceilings, and fail-closed
  missing/invalid manifests.
- `freeze_cluster_calibration_thresholds`: freezes the exact threshold policy
  only when every source-pinned retrieval result is in the calibration split.
- `qualify_cluster_embedding_release`: consumes the frozen thresholds and a
  controller-bound, holdout-only chain of completed QREL, retrieval, authority,
  grounding, repeatability, runtime, and evaluator-validity receipts. It is the
  only evaluator API capable of emitting cluster release authority.
- `evaluate_authoritative_grounding`: source bytes + graph paths + system
  claims + completed human truth.
- `evaluate_authoritative_sections`: two rostered human reviews, one
  adjudication per case, and externally pinned G3 coverage for every compared
  artifact.
- `evaluate_authoritative_whole_resume`: an externally pinned W9 bundle plus
  externally pinned G3 coverage for every candidate material claim.
- `execute_controller_plan` and `evaluate_controller_bound_repeatability`:
  actual command execution plus pinned G5 stability policy.
- `evaluate_authoritative_validity`: machine mutation validity plus an
  authorized, two-class human criterion pilot with agreement and Wilson-bound
  false-positive and false-negative policies.
- `normalize_native_receipt_bundle`: native-receipt-derived CI inputs.

## CLI

Set the standalone source root on `PYTHONPATH`, then validate a manifest:

```text
library API: apps_rg.evals.authoritative validate-manifest \
  --manifest evaluation-manifest.json \
  --expected-digest <owner-pinned-canonical-digest>
```

Run an actual repeatability controller plan:

```text
library API: apps_rg.evals.authoritative run-controller \
  --plan controller-plan.json \
  --expected-plan-digest <owner-pinned-canonical-digest> \
  --output-root <new-empty-output-directory>
```

Controller plans require an explicit timeout, a 40-character source commit,
at least three executions per scenario, and real non-symlink input/work paths.
Outputs are create-once and bind command, input, timestamps, exit status,
stdout/stderr, and semantic results.

All source-bound evaluators are available through one request envelope:

```text
library API: apps_rg.evals.authoritative evaluate \
  --lane retrieval \
  --request retrieval-request.json \
  --output retrieval-receipt.json
```

Supported lanes are `retrieval`, `cluster-retrieval`, `cluster-authority`,
`cluster-runtime`, `cluster-threshold-freeze`, `cluster-release`, `grounding`,
`sections`, `whole-resume`, `repeatability`, and `validity`. The request object
uses the corresponding Python API keyword names. Paths to authority receipts
remain filesystem paths; truth and system artifacts are embedded with their
independently supplied expected digests.

## CI

`c03_ci_ratchet.py --native-receipts` consumes a score-group-to-native-file
mapping plus owner-pinned source digests and baseline signatures. It derives
all failure counters and emits `SOURCE_BOUND_ALL_SCORE_GROUPS`. The older
`--evaluation-receipts` mode validates compatibility receipts but does not
prove their source artifacts.
