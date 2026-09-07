# Migration Provenance

## Imported source

- Repository: `C:\Git\Agentic-Workflow-FRESH`
- Worktree: `C:\Git\Agentic-Workflow-FRESH-worktrees\codex-apps-rg-source-refreeze`
- Branch: `codex-apps-rg-source-refreeze`
- Commit: `f42e05c6f80f26b61505a42d193dae58215bd7cb`
- Relation to the frozen source main: 21 commits ahead, 0 behind.

The five role-context retrieval files that were uncommitted during the initial
transplant are now bound by source commit `f42e05c6f80f26b61505a42d193dae58215bd7cb`:

- `apps_research/engines/company_brief_engine.py`
- `apps_research/engines/query_decomposer.py`
- `tests/unit/apps_research/engines/test_company_brief_engine.py`
- `tests/unit/apps_research/engines/test_query_decomposer_retrieval_contract.py`
- `tests/unit/apps_research/test_s2_grounded_retrieval_recovery.py`

`apps_rg/runtime/sections/competencies_lane_runtime.py` had no content diff and
therefore required no source commit.

The standalone diagnostic tooling was imported from
`C:\Git\Agentic-Workflow-FRESH-worktrees\codex-apps-rg-standalone`, where it
was uncommitted at import time.

## Imported paths

- `src/apps_rg/`
- `src/apps_research/`
- `src/apps_eval/`
- `config/`
- `data/`
- `tests/apps_rg/`
- `tests/apps_research/`
- `tests/unit/apps_rg/`
- `tests/unit/apps_research/`
- `tools/apps_rg_standalone/`
- `tests/unit/tools/apps_rg_standalone/`
- `artifacts/apps_rg/`
- `artifacts/apps_rg_source_refreeze/`

## Explicit exclusions

- `apps_rg/**` remains in the Agentic Workflow source repository.
- Source-only ADRs, source plans, `ops_scripts/apps_rg/**`, and
  `tests/**/apps_rg/**` remain in the source repository under the approved
  Wave 1 import boundary.
- `.runtime/**`, Python bytecode, and test caches were not imported.
- The source-refreeze branch was not merged into Agentic Workflow `main`.
- This target does not contain standalone packaging or a parity claim. Product
  entry now records `standalone_runtime_dependency_receipt.json` and fails
  closed unless the excluded `apps_rg` resolves as an external regular
  package with U0 → L1 → L0 → C0 → PA → L2 → Exit contract sentinels. This is
  an explicit external-runtime posture, not an independent-installability or
  behavior-parity assertion.

## Local main authority

`C:\Git\apps_rg_v2` on branch `main` is the local integration authority for
the imported Apps RG v2 surface. Agentic Workflow remains the provenance
source; its local `main` is not the v2 delivery branch.

The synchronization receipt in `SOURCE_SYNC_RECEIPT.json` proves that all 85
chat-changed files inside the approved import surface match the source head by
exact SHA-256 file bytes. The 22 source-only paths outside that surface are
listed explicitly in the receipt. No source-only authority was silently copied
into this repository.

## Evaluation convergence sync

The original `SOURCE_SYNC_RECEIPT.json` remains the immutable receipt for the
initial transplant. The evaluator was subsequently advanced from Agentic
Workflow local-main commit
`38796dc6cb66b273c682182cd7ed3fc5c14c84c8` into
`src/apps_rg/evals`.

The sync adds the completed W1-W6 measurement surface: six independent gates,
seven score groups, modular resume-graph evaluation, finite-universe retrieval,
exact binding and grounding, five section-quality lanes, whole-resume/W9
evaluation, stored-run repeatability, critical-grader mutation evaluation, and
sealed-receipt CI ratcheting.

Of 120 source evaluator files, 119 match after deterministic newline
normalization. The sole intentional source difference removes an unused local
from `resume_graph/metrics/retrieval.py` to satisfy standalone Ruff; it does not
change metrics or runtime behavior. The v2-only graph-embedding qualifier is
preserved. Exact counts, tree digests, validation results, and authority limits
are recorded in `src/apps_rg/evals/EVALUATION_SYNC_RECEIPT.json`.

This sync does not import `apps_rg` or `ops_scripts`, change Apps RG
runtime behavior, create human-review evidence, or claim release authority.

## Source-bound measurement remediation

The evaluator convergence code was later hardened in-place on the standalone
v2 branch. `src/apps_rg/evals/authoritative` separates externally pinned truth,
system output, authority, scoring, controller execution, and CI receipts. It
reuses the existing C0.3 human-review authority receipt as the trust root and
does not import excluded monorepo packages.

Legacy self-sealed evaluator functions remain compatibility and synthetic-test
surfaces. Qualification claims must use the authoritative APIs and provide the
owner-pinned artifacts listed in
`src/apps_rg/evals/MEASUREMENT_VALIDITY_PLAN.md`. No real labels, corpus
qualification, or release authority are created by the implementation alone.

## Standalone C0.3 embedding refreeze

The initial transplant retained a valid historical BGE-M3 projection, but its
active generation manifest still named monorepo paths under `apps_rg/**` while
this repository owns those sources under `src/apps_rg/**`. The standalone
operator in `tools/apps_rg_standalone/c03_embeddings.py` rebuilds and
requalifies candidates against the standalone paths before replacing the
active manifests. It does not restore the excluded monorepo `ops_scripts`
surface or import `apps_rg`.

The bundled seven-query qualification is explicitly `REGRESSION_ONLY` and
non-release-authorizing. Authoritative empirical qualification remains bound
to the independent human-QREL and source-evidence requirements in the
measurement-validity plan.

The standalone refreeze also binds the exact Python, Torch, Sentence
Transformers, model revision, CUDA target, and offline/no-fallback requirements
in `tools/apps_rg_standalone/c03_embedding_runtime_contract.json`.

## C0.3 human-evaluation source recovery

Production-readiness repair restored three manifest-bound targeting fixtures
that the initial source-only ADR/docs exclusion had omitted. Their source is
commit `f42e05c6f80f26b61505a42d193dae58215bd7cb` in the
`codex-apps-rg-source-refreeze` worktree:

- `docs/reports/apps_rg/fixtures/senior_roles/anthropic_partner_applied_ai_brief.txt`
- `docs/reports/apps_rg/fixtures/senior_roles/lincoln_insurer_it_ai_jd.txt`
- `docs/reports/apps_rg/fixtures/senior_roles/lincoln_insurer_it_ai_brief.txt`

Their exact LF byte digests are already pinned by
`src/apps_rg/evals/c03_human_eval/target_cases.v1.yaml`. Together with
standalone logical-path resolution and the repository LF policy, all 12 target
JD/brief inputs now match that manifest. This recovery imports targeting
fixtures only; it does not import source-only plans/ADRs, create human labels,
or grant evaluation or release authority.

The same source commit also supplies
`docs/reports/apps_rg/fixtures/p1_w4_single_track_jd_fixture.json`, an
app-owned deterministic contract fixture required by the graph concentration
policy test. Historical W0-W9 receipts and the legacy graph-skills operator
guide remain excluded report/documentation outputs; their absence is not
treated as fresh qualification evidence.
