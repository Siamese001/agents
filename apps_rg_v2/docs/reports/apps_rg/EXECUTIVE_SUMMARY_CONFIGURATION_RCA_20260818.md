# Executive-summary configuration RCA — 2026-08-18

## Scope and evidence standard

This is a read-only comparison of the failed local run `full_resume_1f45bd518c68` against Apps RG run receipts retained on GitHub. It does not weaken an X2, X3, exit, or judge gate.

GitHub inventory covered `Siamese001/apps_rg_v2` across all 26 remote branches. GitHub Actions has one successful workflow run, `Copilot cloud agent` (`30320852035`), and no Apps RG Actions workflow or uploaded artifact. The comparison population is therefore tracked Apps RG sealed receipts, not GitHub Actions.

## Full E2E-success result

There are not ten successful full E2E runs on GitHub.

- 94 distinct `APPS_RG_MANDATORY_RUN_OUTPUT.json` blobs were found across remote branches.
- Exactly one has both `exit_status=success` and `outcome_authorized=true`: `artifacts/apps_rg/runs/anthropic_partnership_fresh_s2e_20260630_094000`.
- That June receipt does not retain the executive-summary input, prompt, provider request, claim ledger, or section-gate bundle needed for a configuration comparison.
- Seven receipts assert `product_authorized=true` while also reporting execution error. They are inconsistent records, not successful E2E runs.

The following are therefore the last ten **real executive-summary section passes** (`REAL_LLM`, X2 PASS, X3_ALLOW). They are not full E2E successes: each root receipt reports `exit_status=error`.

| Generated UTC | Run root | Root outcome authorized |
| --- | --- | --- |
| 2026-08-17 11:30:04 | `full_resume_1bf5a3fd73c8` | true |
| 2026-08-17 03:58:32 | `full_resume_de1b62903cdb` | true |
| 2026-08-17 03:43:29 | `full_resume_eec64f4d7ffc` | true |
| 2026-08-17 03:27:12 | `full_resume_5862e3a2adf8` | false |
| 2026-08-17 03:13:31 | `full_resume_ce77c5d3b476` | true |
| 2026-08-17 02:43:36 | `full_resume_ff337a0f42e4` | true |
| 2026-08-17 02:29:28 | `full_resume_4c35613f7666` | false |
| 2026-08-17 02:01:51 | `full_resume_21d0b9ffa6cd` | false |
| 2026-08-17 01:44:28 | `full_resume_1efd49f44ca9` | false |
| 2026-08-09 13:44:51 | `w8_anthropic_positive_final7_20260809/e2e_20260809T133612Z_53df76de` | false |

The first nine have directly comparable `lanes/executive_summary` evidence. The tenth uses an older `modular_r4/sections/executive_summary` layout.

## Configuration comparison

For the nine directly comparable X3_ALLOW records:

| Configuration | Section passes | Failed current run |
| --- | --- | --- |
| Provider | `external_claude` | `external_claude` |
| Model | `claude-sonnet-5` | `claude-sonnet-5` |
| Temperature | `0.45` | `0.45` |
| Max tokens | `4096` | `4096` |
| Prompt template | `executive_summary.generate_scratch_v1.yaml` | same |
| Required root facts | same three roots | same three roots |
| Composition brushstrokes | same B1/B2/B3/B4 mapping | same mapping |
| Allowed-fact count | six runs: 17; three runs: 21 | 21 |
| X2 gate count | 95 | 91 |

The passing 21-fact records disprove the theory that a 21-fact proof pool causes this failure. Provider, model, temperature, token cap, prompt template, required roots, and brushstroke topology do not distinguish passing from failing runs.

The failed run has **four fewer**, not more, X2 checks:

```text
x2_x1d_judge_packet_hash_uniform
x2_x1d_raw_responses_written
x2_x1d_required_judges_present
x2_x1d_schema_valid
```

The failure is not caused by stricter gates or additional judge requirements.

## Isolated failure configuration

The unchanged composition plan requires this root fact in B1 and B4:

```text
reb_ibm_devsecops_release_resilience
```

The failed final ledger never cites that root. Its release-automation sentence cites subordinate skill and metric facts instead:

```text
skill_ibm_automated_release_pipelines
metric_ibm_deployment_blueprint_repeatability
metric_ibm_release_gate_security_scanning_coverage
```

The existing X2 outcome is therefore correct:

```text
x2_exec_summary_allowed_fact_utilization = FAIL
uncovered_required_brushstrokes=['reb_ibm_devsecops_release_resilience']
```

In the newest comparable passing bundle (`full_resume_1bf5a3fd73c8`), the same release material is bound directly to `reb_ibm_devsecops_release_resilience` in sentences 1 and 5. It clears the required-root coverage rule.

This isolates the defect to **root-versus-leaf claim binding after model generation**. It is not provider availability, parallelism, proof-pool size, a judge threshold, or a relaxed/hardened exit gate. The failed run's finalizer recorded no utilization patch despite the final ledger lacking the required root.

## Hardening that preserves gates

1. Keep the required-root X2 gate exactly as-is; subordinate facts must not count as an implicit pass.
2. Deterministically close a claim's root lineage from the approved graph/selected-fact plan after terminal prose or ledger mutations. Add a root only when that exact root-to-leaf relationship is in the plan; otherwise leave the lane blocked.
3. Run this closure check before the unchanged X2 evaluation of final materialized output.
4. Record the executing source commit/tree SHA, prompt hash, selected-fact-plan digest, provider request, and final ledger hash in every mandatory receipt. The failed run lacks its executing source SHA.
5. Report an executed X3 block as `EXECUTED_X3_BLOCK`, not `PHASE1_NO_RUN_DIR`. Aggregation remains withheld; this only corrects diagnostic truth.

## Cross-repository path-authority failure

The failed run was not fully local to `C:\Git\apps_rg_v2`.

The host process inherited these environment values:

```text
AGENTIC_REPO_ROOT=C:\Git\Agentic-Workflow-FRESH
CHROMA_PERSIST_DIR=C:/Git/Agentic-Workflow-FRESH/data/cache/chromadb
APPS_RG_EMBEDDING_MODEL_PATH=C:/Users/amita/.cache/huggingface/.../bge-m3/...
```

The run's own `apps_rg_embedding_settings.json` records that the BGE-M3 model
was loaded from the user Hugging Face cache and that dense retrieval plus
semantic caching used
`C:/Git/Agentic-Workflow-FRESH/data/cache/chromadb`. C0.2 retrieval receipts
for the executive summary and other lanes record that same foreign Chroma
path. The foreign Chroma directory was modified at `2026-08-18 10:00:57Z`,
immediately after the failed run's 10:00Z receipts.

`C:\Users\amita\.cache` is model-weight residency, not a résumé/research
directory. `C:\Users\amita\.cash` does not exist. The material path-authority
violation is the Agentic-Workflow Chroma store, which was read and written by
the Apps RG run.

### Mechanism

`run_whole_run_with_route_governance` obtains its repository with
`find_repo_root()` and passes that root to the embedding bootstrap. However,
the bootstrap calls `os.environ.setdefault("AGENTIC_REPO_ROOT", ...)` and
only writes `CHROMA_PERSIST_DIR` when it is empty. C0.2 then reads the existing
`CHROMA_PERSIST_DIR` before its bootstrap and passes that existing value to the
fact-vector upsert/query path. An inherited foreign path therefore wins over
the explicit Apps RG repository root.

This is a deterministic configuration-isolation defect. It can alter dense
retrieval/cache state between runs and invalidates claims that the failed run
was replayed solely from the local Apps RG main checkout. It does not replace
the immediate executive-summary blocker above: that blocker is still the
missing required DevSecOps root binding in the final claim ledger.

### Required path controls

1. In the product envelope, derive Chroma and all writable runtime stores from
   the resolved Apps RG repository root; do not retain inherited values from a
   different checkout.
2. Fail closed before retrieval if an effective Chroma, semantic-cache, OTel,
   or artifact path lies outside `C:\Git\apps_rg_v2` (except an explicitly
   authorized immutable model-weight location).
3. If all model weights must also be local, require
   `APPS_RG_EMBEDDING_MODEL_PATH` under the Apps RG checkout and reject the
   user-level Hugging Face fallback in the product envelope.
4. Emit the effective repository root and every external path exception in the
   mandatory receipt before dispatch.
