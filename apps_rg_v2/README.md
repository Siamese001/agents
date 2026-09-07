# Apps RG V2

## Canonical resume workflow

The sole public Apps RG resume command is:

```powershell
python -m apps_rg run
```

It defaults to the canonical Anthropic partnership JD and canonical base
resume. It always executes the full governed product flow, including Apps Eval,
L6 shadow evidence, and terminal E2E sealing. `eval` verifies a completed
full run without a provider call, and `show` prints an exact stored output. See
[the canonical-entrypoint guide](docs/APPS_RG_V2_CANONICAL_ENTRYPOINTS.md).

No legacy section, cache, telemetry, or external-governance command is an
alternate resume-run entrypoint. The full product route still fails closed when
its governed runtime and authority gates are not satisfied.

Local `main` integration target for the simplified `apps_rg` extraction.

This initial commit is a provenance-preserving source transplant from the
Agentic Workflow source-refreeze and standalone worktrees. It is intentionally
not independently installable: product entry requires an external
`apps_rg` source runtime. Before any product preflight, it writes
`standalone_runtime_dependency_receipt.json`, proving the resolved external
package and the U0 → L1 → L0 → C0 → PA → L2 → Exit contract sentinels. An
uninstalled editable/source-tree dependency is valid; the receipt does not
claim vendoring, independent installability, or behavior parity.
Repository-local import precedence is enforced by small root-package shims.
Bare `python` commands started from this repository root resolve `apps_rg`,
`apps_research`, and `apps_eval` from `src/` before the editable Agentic
Workflow installation.

The complete six-wave offline evaluation surface is now implemented under
`src/apps_rg/evals`. It provides the G1-G6 measurement contract, modular
resume-graph metrics, section and whole-resume quality evaluation, stored-run
repeatability, critical-grader mutation testing, and seven-receipt CI
ratcheting. Run its owned suite with:

`python -m pytest -q src/apps_rg/evals`

The owned fixture suite does not create human labels, qualify a real corpus, or
authorize release. A source-bound control plane now exists under
`src/apps_rg/evals/authoritative`: it can invoke an explicit operator-supplied
Apps RG command, but reports real repeatability only when controller receipts,
human authority, truth, thresholds, and native evaluator receipts are
independently pinned.

See `MIGRATION_PROVENANCE.md` for the exact imported source state and explicit
exclusions. `SOURCE_SYNC_RECEIPT.json` binds this local main to the complete
chat-owned source history inside the original v2 import surface.
`src/apps_rg/evals/EVALUATION_SYNC_RECEIPT.json` records the later evaluator
convergence sync and its single lint-only source difference.
`src/apps_rg/evals/MEASUREMENT_VALIDITY_PLAN.md` records the subsequent
source-bound measurement remediation and remaining real-evidence gates;
`src/apps_rg/evals/MEASUREMENT_VALIDITY_IMPLEMENTATION_RECEIPT.json` seals its
code-only validation evidence.

Current human-evidence gates, the single-versus-dual proof-judge roster, and
the separate BGE-M3 QREL qualification boundary are documented in
[`docs/QUALIFICATION_OPEN_ITEMS.md`](docs/QUALIFICATION_OPEN_ITEMS.md).

## C0.3 graph embeddings

The canonical C0.3 ledger remains the only claim authority. When an authorized
C0.3 retrieval invocation is enabled, its ranking surface fuses dense BGE-M3
and deterministic BM25 rankings with reciprocal-rank fusion (RRF). It returns
assertion IDs and ranking scores,
then rehydrates those IDs through the current graph, source facts, section
authority, and allowlists before they can affect allocation.

The former one-vector-per-skill lane was retired in C0.3 cluster-embedding W5.
Its 13 malformed artifacts were deleted, and a digest-bound retirement marker
now makes the legacy loader and standalone build, preflight, qualification,
activation, rebuild, and smoke commands fail closed. Verify that boundary with:

```powershell
python tools\apps_rg_standalone\c03_legacy_embedding_retirement_wave5.py --check
```

The W4 registry contains 38 multi-node graph-evidence clusters. W5 generated no
replacement vectors and did not create an activation manifest. W6 is the first
wave authorized to generate one vector per active cluster; production promotion
remains separately gated. `APPS_RG_GRAPH_SKILL_EMBEDDINGS_REQUIRED` is a retired
legacy flag and must not be repurposed for the cluster lane.

The historical production-readiness assessment is retained in
[`C03_EMBEDDING_PRODUCTION_PROMOTION.md`](C03_EMBEDDING_PRODUCTION_PROMOTION.md)
for audit context, but its per-skill operator commands are retired and blocked.
