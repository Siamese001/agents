# C0.3 embedding production promotion

> **Historical assessment — legacy lane retired.** C0.3 cluster-embedding W5
> deleted the 13 one-vector-per-skill artifacts described below and installed a
> fail-closed retirement marker. The legacy preflight, build, qualify, activate,
> rebuild, and smoke commands in this document must not be run and are blocked
> by code. W6 may generate one vector per W4 graph-evidence cluster; it does not
> inherit any production authorization from this historical assessment.

## Decision

**Verdict: NOT PRODUCTION READY.**

This decision applies to the C0.3 graph-skill embedding path in the
`apps_rg_v2` standalone repository. The active artifact generation was
inherited from commit `71a2e2f4e23495256ea9aa09874377221f5f31df`, which was
`origin/main` when this audit began. The error-remediation changes described
here are not an authority pin until they are committed, and no later evaluation
may claim that commit unless it actually runs from the clean committed source.

The current implementation is suitable for deterministic regression checks,
GPU preflight, smoke testing, and controlled non-production embedding-treatment
runs. Those runs are evaluation activity, not the unimplemented runtime
`shadow` mode. Embeddings must remain off for production traffic. Do not set
`APPS_RG_GRAPH_SKILL_EMBEDDINGS_REQUIRED=true` in a production runtime until
every open gate in this document is closed and independently approved.

The file named `graph_skill_embedding_activation_manifest.json` activates a
validated artifact generation inside the repository. It is not a production
release authorization. Its bound qualification is explicitly
`REGRESSION_ONLY` and `release_authorizing: false`.

## Remediation completed on this branch

- Added a deterministic LF checkout contract so Windows cannot invalidate
  raw-byte SHA-256 bindings for manifests, receipts, QRELs, or source fixtures.
- Repaired standalone repository/package/resource resolution across Apps RG,
  Apps Eval, Apps Research handoff, graph materialization, and C0.3 evaluation.
- Restored the three omitted canonical evaluation fixtures from the recorded
  source-refreeze provenance; all 12 target JD/brief hashes now pass exactly.
- Made owner-only evaluation storage fail closed with an explicit unsupported
  platform result when POSIX ownership/mode guarantees cannot be verified, and
  reject symlink or Windows reparse-point ancestors for every sensitive path.
- Hardened projection and allowlist consumption so self-resealed or stale
  artifacts cannot pass on internal digests alone. Runtime consumption now
  verifies active graph/corpus/model/projection/qualification/runtime pins,
  projection metadata parity, current assertion rehydration, and accepted
  assertion bindings before use.
- Bound InsurTech and EY section skill allocation to exact selector output,
  preserving selector provenance and excluding DRAFT/pending-source roots.
  Unify, IBM, and executive-summary gaps remain typed fail-closed blockers.
- Removed collection ambiguity from duplicate test-module names and eliminated
  whole-file collection quarantines. Tests whose required source-only
  dependency was explicitly excluded now report a named module/test skip; a
  skip remains an audit boundary, not evidence that the dependency passed.
- Revalidated the active artifact chain, regression tests, strict preflight,
  and one real CUDA smoke query without changing graph authority. Test graph
  refreshes, Chroma state, and runtime caches are isolated outside the checkout.

## Authority boundary

The canonical C0.3 graph remains the only claim authority. Embeddings are a
derived, read-only ranking surface. The runtime may use only an assertion ID and
similarity score from the index, then must rehydrate the ID through the current
graph, fact lineage, section policy, allocation, and allowlists before use.
Similarity is never proof for a resume claim.

Machine automation may:

- verify digests, schemas, source identity, and model/runtime pins;
- build and query a derived embedding projection;
- freeze a source bundle after authoritative inputs exist;
- blind and seal an unlabeled review packet;
- validate returned reviews and adjudications;
- compute retrieval, grounding, section, whole-resume, repeatability, validity,
  latency, and resource metrics;
- emit non-release-authorizing receipts and enforce frozen policies.

Machine automation must not:

- create or infer human relevance, proof, section-quality, or W9 labels;
- pose as a reviewer or adjudicator;
- create reviewer authority, qualifications, issuer approval, or owner pins;
- choose or relax acceptance thresholds after observing protected holdout
  results;
- convert an artifact-activation receipt or test result into release authority;
- authorize production rollout.

All evaluator receipts remain non-release-authorizing by design. A final
production decision must be a separate, owner-approved authority object that
binds the complete evidence chain.

## Current verified evidence

The committed artifact chain provides the following technical evidence:

| Evidence | Verified value | What it proves |
| --- | --- | --- |
| Canonical graph | `d622c689984798ae7aa0dba83a0ab3571996c92b7ffc2f94f5d52bc67568a739` | The embedding corpus binds to one graph snapshot. |
| Assertion corpus | `efd9e01bf82df9324c9b5485bf93b7f5595e9260c60f848a4b1241411a9c2ca6` | 198 included assertions and 56 explicit exclusions. |
| Model | `BAAI/bge-m3` revision `5617a9f61b028005a4858fdac845db406aefb181` | The intended embedding model and immutable revision. |
| Model artifact | `38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263` | The local model snapshot must match the recorded file inventory. |
| Projection generation | `68dc2043a5f7296259ec0de5878de4930093d4f30e602dd4adb96d6aa3e6c6e6` | One generation containing 198 1024-dimensional, L2-normalized vectors. |
| Projection file | `2d4fdce4a0a3dca99ca0c8c24bc186cf560114f9dec065c446e9c65510c3698e` | The immutable SQLite projection bytes. |
| Active generation manifest | `a8609456b34b908557945675d8b3c2d5217c77f715e3e8d784b2ce893190e2bc` | The active artifact pointer and full source/model/projection bindings. |
| Runtime contract | `ab2cacbff73801b52ab31a8f9016f3cec11e3e60551a16d4a2411cd6e2bb5c79` | Python 3.12, Torch `2.12.0.dev20260228+cu128`, Sentence Transformers `5.2.3`, `cuda:0`, offline-only, no fallback. |
| Qualification | `5b2b1dfb21a147644a97d662fed8bf422f4acb0ff5cec51461bb2d7559cd786f` | Seven-query regression qualification only. |
| Qualification manifest | `1c83f256452f074ee2e5ce48df9c7b0e0668784430db154cb5bd9dbec9891750` | Regression QRELs, thresholds, report, and generation are mutually bound. |
| Artifact activation | `4ce00bdb4fc61c99984b7ec9b04b141d2087a70434c06ab31da1db401af040a5` | The active pointer changed without mutating the graph. |

The active generation, projection, qualification, QREL, and activation files
are under `artifacts/apps_rg/c03/graph_skill_embeddings/`. The promoted runtime
contract is `tools/apps_rg_standalone/c03_embedding_runtime_contract.json`.
Measurement boundaries are recorded in
`src/apps_rg/evals/MEASUREMENT_VALIDITY_PLAN.md`, and the authoritative
evaluation CLI is documented in `src/apps_rg/evals/authoritative/README.md`.

The regression qualification reports:

| Mode | Recall@100 macro | Recall@100 micro |
| --- | ---: | ---: |
| Exact sparse | 1.000000 | 1.000000 |
| Fact-vector sparse | 0.748052 | 0.702703 |
| Dense | 0.891775 | 0.918919 |
| Hybrid | 0.939394 | 0.945946 |

It also reports perfect authority eligibility, exact graph paths, and assertion
vector parity, with zero stale, orphan, unauthorized, or authority-bypass
candidates.

Those results do not establish production usefulness. The gated cutoff is 100,
while the ungated cutoff-sensitive diagnostics are materially weaker:

| Mode | Recall@10 macro | MRR | nDCG@10 |
| --- | ---: | ---: | ---: |
| Exact sparse comparator | 0.536580 | 0.692857 | 0.533253 |
| Dense | 0.435714 | 0.329932 | 0.310512 |
| Hybrid | 0.457143 | 0.383333 | 0.336471 |

The exact sparse row is a qualification comparator, not the production graph
allocator. It nevertheless shows why an operationally matched treatment versus
control evaluation is mandatory.

On 2026-08-02, the repaired standalone checkout passed the focused evaluator
regression slice with `263 passed, 21 skipped`; this is not a repository-wide
standalone qualification. The skips in that focused slice are the expected
Windows capability-bound symlink and POSIX owner/mode cases. Ruff also passed
over both evaluator trees.

The final uncapped repository suite passed `5418 passed, 161 skipped` with zero
failures or collection errors. Its pre/post Git status snapshots were exactly
identical, and no canonical graph, cache, context-receipt, or runtime artifact
changed. No `collect_ignore` quarantine remains. The 161 skips are explicit
coverage boundaries, dominated by excluded monorepo-owned `apps_rg`,
Apps LIC, operator/render/retrieval tools, Windows symlink/POSIX permission
capabilities, and historical runtime/certification fixtures that are not in the
standalone source baseline. They are not production qualification evidence.
Ruff passed all 256 changed/new Python files and `git diff --check` passed.

The checkout additionally passed strict local preflight and a real one-query
CUDA smoke run against the exact pinned BGE-M3 snapshot after the projection
and allowlist hardening. The runtime reported Python 3.12, Torch
`2.12.0.dev20260228+cu128`, Sentence Transformers `5.2.3`, `cuda:0` on an
NVIDIA GeForce RTX 5090, one 1024-dimensional vector, ten exactly rehydrated
candidates, and no fallback. That is useful operational proof, but it is an
operator probe rather than a source-bound controlled comparison or release
receipt.

The audit workstation is not dependency-isolated. With the documented
standalone test path (`PYTHONPATH=src;.`), importing `apps_rg` resolves to
`C:\Git\Agentic-Workflow-FRESH\apps_rg\__init__.py` through an ambient
editable installation outside this repository. The current test, preflight, and
smoke results are therefore workstation-local evidence, not proof that this
checkout can reproduce the runtime from its own declared inputs. The promoted
embedding runtime contract does not bind that external package provenance.

The runtime currently queries with `k` equal to the entire assertion count and
therefore returns all section-eligible assertions. Embedding similarity is the
fifth lexicographic allocation component after proof strength, path confidence,
source independence, and target alignment. The implementation protects graph
authority, but the current evidence does not show that embeddings materially
improve final allocation or resume quality.

The code-only measurement receipt at
`src/apps_rg/evals/MEASUREMENT_VALIDITY_IMPLEMENTATION_RECEIPT.json` records
`empirical_qualification.status: NOT_RUN`, no real human labels, no real corpus
qualification, and no release authority.

Three current graph integrations remain deliberately fail closed. The
executive-summary `reb_*` role-episode IDs have no governed
`role_episode_root -> skill -> linked graph fact` mapping into the
track-weighted hop namespace. Unify bullet slots have no
`role_episode_bundle_id` roots to bind to selector output. IBM has selector
roots absent from its section plan and a cross-employer sixth fact that must be
removed or rebound by source authority. The corresponding W5/D7 and W6
qualification tests are explicit typed skips; dedicated blocker tests pass.
These are not standalone path defects and must be closed with governed graph
data and bindings, not empty-seed retries, lifted fact skill IDs, or synthetic
allocation fallbacks.

Historical W0-W9 graph-skills receipts and the old operator guide are
intentionally not restored into active standalone paths. They bind an obsolete
monorepo commit, excluded `ops_scripts`, monorepo-shaped paths, old Brown input
digests, and include partial results. They are historical evidence only and
cannot close any gate below.

## Historical runtime evidence is not a shadow qualification

Three tracked runs contain passing embedding runtime receipts:

- `artifacts/apps_rg/runs/s2r3_r2/`
- `artifacts/apps_rg/runs/s2r3_r3/`
- `artifacts/apps_rg/runs/s2u0_r1/`

They prove that the projection was queried on `cuda:0`, IDs were exactly
rehydrated, allowlists were emitted, no fallback or network was used, and the
projection did not change. They do not close a production gate because all
three:

- bind old generation manifest `9c9cd463d552b730034cb317872a3adba29c7a15c79d181ca4e5938495c4c485`;
- bind old qualification `d10426272e04e63230877ec4ba7ffb92fab2e17c3f33ddf780b2a8aaa530380a`;
- ran from dirty monorepo commit `bb7a8e4620eacfa4d64ad44f71b46dcbbdf99b53`;
- cover one Unify target rather than the governed evaluation set;
- have no same-input embedding-disabled control;
- have no owner-pinned stability, quality, latency, capacity, or rollback policy.

## Open gates

Every gate below is mandatory for production unless the evaluation owner
explicitly narrows the release scope in a separately approved policy. A narrow
release does not permit fabricated or self-authorized evidence.

| Gate | Current status | Required closing evidence |
| --- | --- | --- |
| P0. Exact source snapshot | Open | A clean checkout at the exact source commit used for every evaluation and deployment artifact. |
| P1. Six-case source authority | Ready after P0 on a supported authority host | All 12 canonical JD/brief inputs now resolve in the standalone layout and match the frozen SHA-256 values. Close this gate by freezing from the clean committed source on a host that can verify owner-only storage, then externally pinning the source-freeze receipt. |
| P2. Reproducible production runtime | Partially verified | The exact local model/runtime passed strict CUDA preflight and smoke, but the audit environment imports `apps_rg` from an ambient editable `Agentic-Workflow-FRESH` checkout. Close with a fresh, provisioned, dependency-locked production image that installs only declared inputs, proves module provenance, and passes preflight on every deployment node class. Human-evaluation control storage remains a separate supported-platform requirement under P1/P4. |
| P3. Evaluation trust roots | Open | Owner-pinned evaluation manifest, graph/corpus bindings, human-authority file SHA, truth bundle digests, threshold policy digests, and split commitments. |
| P4. Sealed prelabel packet | Blocked; implementation available after P0/P1 on a supported authority host | A real six-case allocator freeze/readiness run followed by a 282-claim, 84-query, full-finite-universe packet; owner-held nonce; source-freeze pin; prelabel receipt; and out-of-band packet-manifest pin. |
| P5. Authorized human evidence | Open | Exactly two distinct authorized primary reviews per item, complete candidate labels, required adjudication receipts, no `UNKNOWN`, and optional W9 evidence from its separate qualified cohort. |
| P6. Embedding-specific controlled comparison | Blocked by current graph integration gaps | Governed role-episode-to-track-hop bindings and selected-skill allocations must first close the W5/D7/W6 fail-closed gaps. Then produce independently pinned full-universe rankings for graph-only control and embedding-enabled treatment on identical inputs and artifact pins. |
| P7. Calibration and protected holdout | Open | Calibration-only threshold selection, owner-frozen policies, then one protected holdout execution without leakage or post-hoc threshold changes. |
| P8. Seven source-bound score groups | Open | Passing native receipts for retrieval quality, binding accuracy, factual grounding, section quality, whole-resume quality, runtime repeatability, and evaluator validity. |
| P9. Source-bound CI ratchet | Open | A passing `SOURCE_BOUND_ALL_SCORE_GROUPS` receipt with independently pinned native source digests and baselines. |
| P10. Production activation authority | Not implemented | A separate owner-approved promotion receipt and runtime enforcement that distinguishes `off`, `shadow`, and `production`. |
| P11. Canary, SLO, and rollback | Open | Frozen rollout cohort, observation window/sample policy, SLOs, automatic abort rules, kill switch, and a tested graph-only rollback. |
| P12. Final human release decision | Open | Named owner approval binding P0-P11. No component receipt may self-promote. |

### P1 source recovery result

The canonical target manifest declares six cases, 47 claims per case, and two
retrieval slots in each of seven independently ranked sections. This branch now
maps stable logical `apps_rg/...` resource names to the standalone
`src/apps_rg/...` package without changing the manifest identity. It also
enforces LF checkout bytes for digest-bound text and restores these three
fixtures from commit `f42e05c6f80f26b61505a42d193dae58215bd7cb`
in the source-refreeze worktree:

- `docs/reports/apps_rg/fixtures/senior_roles/anthropic_partner_applied_ai_brief.txt`
- `docs/reports/apps_rg/fixtures/senior_roles/lincoln_insurer_it_ai_jd.txt`
- `docs/reports/apps_rg/fixtures/senior_roles/lincoln_insurer_it_ai_brief.txt`

All 12 resolved files now match the manifest's exact raw-byte SHA-256 values,
and the target manifest itself matches its compiled canonical digest
`d36338de05e681dae2001f6e9c975eee4a79ef0963efd8875b1167456e3640d8`.
The official freezer still requires a clean committed checkout,
`source_commit_sha == HEAD`, controlled owner-only output storage, and an
externally pinned receipt. Therefore source availability is repaired, but P1
does not close until P0 creates the exact commit and the authoritative freeze
is executed outside this repository.

Native Windows is deliberately fail-closed for that authority step. The current
implementation returns
`PLATFORM_SECURITY_UNSUPPORTED:owner-only permissions cannot be verified on this platform`
when Python cannot inspect real POSIX ownership and mode. Test-only POSIX
emulation does not create official authority. Run `freeze-source`, `readiness`,
`build`, `validate`, `seal-prelabel`, completed validation, and `export` on a
controlled Linux/POSIX host. WSL is acceptable only when both the clean checkout
and controlled paths reside on storage with real, verifiable POSIX ownership
and mode; a Windows-mounted path must not be assumed equivalent. A future
Windows path would require a separately reviewed, owner-approved ACL verifier.

This audit created no source-freeze, prelabel, reviewer-authority, adjudicated
export, source-bound CI, or production-promotion receipt. Repository schemas and
templates are contracts, not evidence that those gates have closed.

### P5 human-review requirements

For W6, the packet contains 282 claim items and 84 retrieval queries. Every
retrieval review must label the complete allocator-bounded candidate universe,
not only system top-K. Each item requires two distinct authorized primary human
reviews and one adjudication receipt. Agreement may use the repository's
deterministic consensus path; a disagreement requires an independent authorized
human adjudicator who is not either primary reviewer.

Proof and retrieval reviewer cohorts must be disjoint. W9 may be omitted only
from an initial W6-only packet; it is mandatory before P8/P12 production
closure. Full whole-resume W9
requires six real baseline/hardened pairs and a third disjoint cohort whose
reviewers and human adjudicators carry the required `resume-coach://`
qualification. Synthetic, model, agent, judge, bot, or automated reviewer
identities are rejected. `UNKNOWN` never passes completed validation.

## Required embedding comparison

The controlled experiment must freeze the source commit, graph, corpus, model,
projection, runtime contract, target inputs, candidate universe, and evaluator
version before comparing:

- control: embeddings off, current graph-only allocation path;
- treatment: embeddings enabled with the current active projection;
- at least three actual executions per governed scenario, as required by the
  authoritative controller contract;
- the full six-case evaluation set, including calibration and protected
  holdout separation;
- full candidate rankings, allocation plans, accepted assertion bindings,
  final section artifacts, and whole-resume artifacts from both arms.

The comparison must report at minimum:

- Recall@1/3/5/10, pooled recall, nDCG@1/3/5/10, and MRR;
- relevant evidence omitted beyond the operational cutoff;
- hard-negative selection/rejection and top-K redundancy;
- exact-path accuracy and authority eligibility;
- changed skill/fact/metric/assertion assignments by lane;
- factual grounding, binding accuracy, section quality, and whole-resume quality;
- repeatability of rankings, allocation plans, and semantic outputs;
- cold and warm embedding latency, end-to-end latency delta, throughput, GPU
  memory, OOM/error rate, model-load failure rate, network use, and fallback use.

Numeric quality and operational thresholds must be selected from calibration
evidence and independently frozen before holdout. This document deliberately
does not invent those values.

The following remain unconditional hard failures:

- any stale, orphan, unauthorized, or authority-bypass candidate;
- any graph/path/allowlist/rehydration mismatch;
- any unsupported material claim;
- any protected-holdout leakage;
- any required `UNKNOWN` result;
- any network or fallback use;
- any durable graph mutation;
- any unapproved runtime, model, source, or receipt digest.

## Required activation design

The production implementation should expose one explicit mode with default
`off`:

| Mode | Permitted behavior | Required authority |
| --- | --- | --- |
| `off` | Preserve the current graph-only runtime. No embedding allocation or embedding allowlist may affect output. | None. This is the default and rollback state. |
| `shadow` | Run the embedding treatment only in an isolated governed comparison; do not return treatment output to production users. | Current regression artifact chain, exact model/runtime preflight, frozen shadow plan, and controlled output storage. |
| `production` | Permit embedding-ranked allocation only inside an approved rollout cohort. | Exact production promotion receipt, external expected receipt SHA, empirical evidence bindings, rollout policy, and non-expired owner approval. |

A future runtime contract may use a variable such as
`APPS_RG_GRAPH_SKILL_EMBEDDING_MODE=off|shadow|production`. The existing
`APPS_RG_GRAPH_SKILL_EMBEDDINGS_REQUIRED` boolean should remain shadow-only
compatibility or be rejected for production use. This design is not implemented
in the audited commit.

The production promotion receipt should bind at least:

- decision, scope, issuer, approval reference, issue time, and expiry/review
  time;
- source commit and clean-source receipt;
- graph, corpus, model artifact, projection generation/file, and runtime
  contract digests;
- owner-pinned authoritative evaluation manifest;
- all seven native receipt digests and the source-bound CI receipt;
- calibration policy and protected-holdout commitments/results;
- SLO, canary, monitoring, and rollback policy digests;
- a canonical receipt digest supplied to the runtime with an independent
  expected file SHA-256.

Production mode must fail before model invocation if any binding is absent,
mismatched, expired, or revoked. It must not silently degrade to a different
embedding model, a network download, or an unrecorded graph-only result inside a
run that declared embeddings mandatory.

## Canary, SLO, and rollback requirements

The rollout owner must freeze the following before canary:

- eligible cohort or traffic fraction;
- minimum sample count and observation duration;
- quality non-regression thresholds by lane and target slice;
- cold/warm latency and end-to-end latency budgets;
- GPU memory/capacity, error, OOM, and availability budgets;
- alert destinations and named on-call owner;
- automatic abort conditions and the maximum rollback time;
- the exact graph-only rollback configuration and verification command.

Recommended stage boundaries are:

1. Offline paired shadow on all governed cases, with at least three executions
   per scenario.
2. Owner review of calibration results; freeze thresholds and rollout policy.
3. One protected holdout run and all seven source-bound receipts.
4. Bounded production canary under the approved promotion receipt.
5. Hold at the frozen observation boundary; expand only after an explicit owner
   decision.

Rollback sets mode to `off`, removes production authorization from the next
run, and restores the already-tested graph-only path. A failed mandatory
embedding run must remain a recorded failure; rollback changes subsequent runs
and must not rewrite the failed run. Preserve the failed receipts, emit a
rollback decision record, and require a new qualification/promotion chain for
any replacement generation.

## Repository-supported commands

These commands produce or validate evidence. None authorizes production by
itself.

### Artifact preflight and smoke

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:APPS_RG_EMBEDDING_MODEL_PATH = 'C:\path\to\bge-m3\snapshots\5617a9f61b028005a4858fdac845db406aefb181'
$env:APPS_RG_GRAPH_SKILL_EMBEDDING_DEVICE = 'cuda:0'

python tools\apps_rg_standalone\c03_embeddings.py preflight
python tools\apps_rg_standalone\c03_embeddings.py smoke `
  --query 'regulated insurance AI transformation and cloud modernization' `
  --section competencies `
  --k 10
```

`rebuild --activate` and `activate --candidate-dir` are artifact-management
commands. They mutate the active artifact pointer after regression validation;
they are not production rollout commands.

### Freeze and seal the human-evaluation packet

The command shape below uses PowerShell 7 on a supported Linux/POSIX authority
host. Do not run the official sequence in native Windows PowerShell: it must
fail closed before emitting authority-bearing output. The controlled paths must
be outside the repository and provisioned with the access controls described in
`src/apps_rg/evals/c03_human_eval/README.md`.

```powershell
$sourceCommit = (git rev-parse HEAD).Trim()
$controlled = '/srv/controlled/apps-rg-c03'
$sourceBundle = Join-Path $controlled 'source_bundle.v1.json'
$freezeReceipt = Join-Path $controlled 'source_freeze_receipt.v1.json'
$packet = Join-Path $controlled 'c03_resume_graph_v1'
$prelabelReceipt = Join-Path $controlled 'c03_prelabel_packet_receipt.v1.json'
$nonceFile = Join-Path $controlled 'secrets\c03_blinding_nonce.hex'

python -m apps_rg.evals.c03_human_eval freeze-source `
  --source-commit-sha $sourceCommit `
  --out $sourceBundle `
  --receipt-out $freezeReceipt

python -m apps_rg.evals.c03_human_eval readiness `
  --source-bundle $sourceBundle `
  --freeze-receipt $freezeReceipt `
  --expected-freeze-receipt-digest $env:TRUSTED_FREEZE_RECEIPT_DIGEST `
  --blinding-nonce-file $nonceFile

python -m apps_rg.evals.c03_human_eval build `
  --source-bundle $sourceBundle `
  --freeze-receipt $freezeReceipt `
  --expected-freeze-receipt-digest $env:TRUSTED_FREEZE_RECEIPT_DIGEST `
  --blinding-nonce-file $nonceFile `
  --out $packet

python -m apps_rg.evals.c03_human_eval validate `
  --packet $packet `
  --phase prelabel `
  --expected-freeze-receipt-digest $env:TRUSTED_FREEZE_RECEIPT_DIGEST

python -m apps_rg.evals.c03_human_eval seal-prelabel `
  --packet $packet `
  --receipt-out $prelabelReceipt `
  --expected-freeze-receipt-digest $env:TRUSTED_FREEZE_RECEIPT_DIGEST
```

After real reviewers return their records, completed validation is:

```powershell
python -m apps_rg.evals.c03_human_eval validate `
  --packet $packet `
  --phase completed `
  --labels-dir (Join-Path $controlled 'returned_labels') `
  --expected-freeze-receipt-digest $env:TRUSTED_FREEZE_RECEIPT_DIGEST `
  --expected-prelabel-manifest-sha256 $env:TRUSTED_PRELABEL_MANIFEST_SHA256 `
  --human-review-authority-receipt (Join-Path $controlled 'human_review_authority.v1.json') `
  --expected-human-review-authority-receipt-sha256 $env:TRUSTED_HUMAN_AUTHORITY_SHA256
```

After completed validation passes, export the sealed adjudicated W6 dataset and
its trusted receipt:

```powershell
python -m apps_rg.evals.c03_human_eval export `
  --packet $packet `
  --labels-dir (Join-Path $controlled 'returned_labels') `
  --out (Join-Path $controlled 'adjudicated_evaluation.v1.jsonl') `
  --receipt-out (Join-Path $controlled 'adjudicated_export_receipt.v1.json') `
  --expected-freeze-receipt-digest $env:TRUSTED_FREEZE_RECEIPT_DIGEST `
  --expected-prelabel-manifest-sha256 $env:TRUSTED_PRELABEL_MANIFEST_SHA256 `
  --human-review-authority-receipt (Join-Path $controlled 'human_review_authority.v1.json') `
  --expected-human-review-authority-receipt-sha256 $env:TRUSTED_HUMAN_AUTHORITY_SHA256
```

Add `--require-w9` only after all six real baseline/hardened whole-resume pairs
exist and the separate W9 authority/cohort is ready.

Never commit or publish the full packet, source bundle, blinding nonce,
`sealed_internal/`, reviewer distributions, identity mappings, returned labels,
or owner-only authority receipts.

### Authoritative evaluation and controlled execution

Continue on the same supported authority host and controlled filesystem. The
`/srv/controlled/apps-rg-c03` paths below are examples, not repository output
locations.

Validate the externally pinned seven-score-group manifest:

```powershell
python -m apps_rg.evals.authoritative validate-manifest `
  --manifest /srv/controlled/apps-rg-c03/evaluation-manifest.json `
  --expected-digest $env:TRUSTED_EVALUATION_MANIFEST_DIGEST
```

Run an owner-pinned controller plan. The plan must name an explicit timeout, a
40-character source commit, real non-symlink work/input paths, and at least three
executions per scenario. The output root must be new and empty.

```powershell
python -m apps_rg.evals.authoritative run-controller `
  --plan /srv/controlled/apps-rg-c03/controller-plan.json `
  --expected-plan-digest $env:TRUSTED_CONTROLLER_PLAN_DIGEST `
  --output-root /srv/controlled/apps-rg-c03/controller-output
```

The supported authoritative lanes are `retrieval`, `grounding`, `sections`,
`whole-resume`, `repeatability`, and `validity`. Each request must contain its
independently pinned source/truth/threshold inputs.

```powershell
python -m apps_rg.evals.authoritative evaluate `
  --lane retrieval `
  --request /srv/controlled/apps-rg-c03/retrieval-request.json `
  --output /srv/controlled/apps-rg-c03/retrieval-receipt.json
```

### Source-bound CI ratchet

After all native receipts and their external source/baseline pins exist:

```powershell
python -m apps_rg.evals.c03_ci_ratchet `
  --strict-junit /srv/controlled/apps-rg-c03/strict-junit.xml `
  --baseline-junit /srv/controlled/apps-rg-c03/baseline-junit.xml `
  --source-commit $sourceCommit `
  --base-commit $env:TRUSTED_BASE_COMMIT `
  --native-receipts /srv/controlled/apps-rg-c03/native-receipts.json `
  --expected-source-receipt-digests /srv/controlled/apps-rg-c03/native-source-digests.json `
  --expected-baselines /srv/controlled/apps-rg-c03/expected-baselines.json `
  --out /srv/controlled/apps-rg-c03/source-bound-ci-receipt.json
```

The acceptance receipt must report `PASS` and
`evaluation_receipt_mode: SOURCE_BOUND_ALL_SCORE_GROUPS`. The older
`--evaluation-receipts` mode is compatibility-only and does not prove native
source bindings.

## Production-ready definition

C0.3 graph embeddings are production-ready only when all of the following are
simultaneously true:

- [ ] P0-P12 are closed against one exact source and artifact identity.
- [ ] The active projection and deployed model/runtime pass strict preflight.
- [ ] A fresh dependency-locked environment reproduces the tests and runtime
  without ambient editable imports from another checkout.
- [ ] Human QREL/proof/W9 evidence is complete, authorized, blinded, and
  adjudicated.
- [ ] Calibration policies were frozen before the protected holdout.
- [ ] The treatment passes all seven source-bound score groups and the paired
  graph-only comparison.
- [ ] Operational SLOs and automatic abort conditions are frozen and passing.
- [ ] Runtime production mode validates an external owner-approved promotion
  receipt before model invocation.
- [ ] Canary scope and rollback have been exercised successfully.
- [ ] The release owner records the final decision.

Until then, the authoritative operational state is **off**. Controlled
non-production embedding-treatment runs are permitted only under explicitly
pinned inputs; they are not runtime `shadow` mode or production activation.
