# Apps RG v2 RCA and Branch-Convergence Baseline

## Scope

This is a factual baseline for the single resume pipeline implemented by
`python -m apps_rg run`. It distinguishes a run that is genuinely live from a
no-provider deterministic run, identifies why earlier reporting became
confusing, and records the branch convergence state before any unrelated
history is merged or deleted.

## Evidence inspected

| Evidence | Observation |
| --- | --- |
| `dd0418c60` | Local Apps RG runtime/cognition contract baseline on 2026-08-11. |
| `cf8014ee7` / `e5982233e` | Deterministic Anthropic fixture work, merged into local main by `2cb675750` on 2026-08-12. |
| `c0f0da1da` | Fresh Anthropic E2E work merged into local main on 2026-08-12. |
| `1280aaa2a` | Replaced the public `apps_rg.__main__` route with a compact live resume runner. |
| `08a9b7e7d` | Added missing full-resume section/email/DOCX checks and corrected live Gemini ledger stage to `X3`. |
| `afed13e3` | Captured the thread feedback plan that this branch implements. |
| `C:\Temp\apps-rg-main-full-resume-20260813\bare_e2e_20260813T061825Z_ce6d2750` | Prior live package: `SUCCESS`, all compact stages pass, actual OpenAI and Gemini provider receipts. |
| `C:\Temp\apps-rg-fixture-proof-a` and `...-b` | Fixture proof passed one-run tests but differed across runs due to timestamp/path data; it was not proof of byte-identical product determinism. |

## GitHub PR evidence

Remote PR metadata was inspected from `Siamese001/apps_rg_v2` on 2026-08-13.
It confirms that GitHub pull requests and local branch merges are different
events in this history:

| Remote PR | Merge commit | Relevance |
| --- | --- | --- |
| [#8 — Preserve zero-LLM RCA remediation evidence](https://github.com/Siamese001/apps_rg_v2/pull/8) | `27d129da6` | Historical zero-LLM/RCA work. |
| [#20 — scope local-generator scan to code](https://github.com/Siamese001/apps_rg_v2/pull/20) | `20f3b3781` | Merged head `codex/zero-llm-resume-e2e-r3`. |

The local-main commits `2cb675750` (`codex/anthropic-deterministic-e2e`) and
`c0f0da1da` (`codex/w3-anthropic-fresh-e2e`) have local merge messages, but
no corresponding merged GitHub PR appeared in the remote PR list. They must
be reported as **local merges**, never as PRs. This branch has not been pushed
and has no PR yet.

## Root causes

| Symptom | Root cause | Corrective action on this branch |
| --- | --- | --- |
| A deterministic fixture was described too close to a product E2E result. | The old fixture preserved per-run timestamps and paths; its test exercised one run and did not compare two independent executions. | Add an explicit `deterministic` mode with fixed local inputs, no provider code path, truthful `DETERMINISTIC_OFFLINE_PASS` label, and two-run normalized comparison. |
| A successful run did not prove every résumé section. | The old X1 gate accepted minimum text length and source presence, then marked a stage pass before caller-side failure handling. | Validate header, six headings, every base-resume employer, email subject/company/role, source availability, and reopened DOCX before X1/Delivery pass. |
| Gemini evidence was labelled as X2 while used as X3. | The shared helper defaulted all Gemini calls to historical `L2.X2_research_semantic_gate`. | The live X3 caller explicitly supplies `stage=X3` and `section_id=X3`; the live ledger check requires the corresponding terminal success event. |
| “Main” and branch claims conflicted. | `C:\Git\apps_rg_v2` and the local-main worktree were different checkouts. Artifact reporting did not always state which checkout executed. | Every run records repository root, branch, commit SHA, local-main ancestry, and dirty state. This branch begins from local-main plan commit `afed13e3`. |
| Multiple commands appeared to be pipeline entrypoints. | The repository contains many historical runtime, section, graph, eval, and maintenance modules. Search results were being treated as competing public product commands. | Define scope precisely: only `python -m apps_rg run` is a public end-to-end resume runner; `eval`/`show` are inspection actions under the same command. Other modules are explicitly non-pipeline surfaces. |
| W6/cache/telemetry blockers appeared in a simple resume run. | Older integrated runtime paths carried legacy product-proof and release controls. The compact runner had replaced that path, but the distinction was not made clear. | Keep the canonical runner restricted to the eleven visible core stages; it does not import the legacy shared runner, cache layer, telemetry collector, or release-authority stack. |
| Fake-key concern. | Tests and fixture lanes can inject transports/credentials, but that distinction was not visible at the user command surface. | Live mode fails before dispatch if actual environment credentials are absent. Deterministic mode reads neither provider credential nor provider/retrieval hook and writes a zero-call report. |

## Branch convergence manifest

The following relevant heads were checked against the implementation base
(`afed13e3`) before this branch began. Each is already an ancestor of that
base; therefore no pending resume-pipeline content is being silently omitted.

| Branch | Head | State at baseline | Decision |
| --- | --- | --- | --- |
| `codex/anthropic-deterministic-e2e` | `e5982233e` | Contained in local main. | Superseded by the explicit deterministic mode; retain history, no merge needed. |
| `codex/e2e-defect-remediation-w0` | `75a658508` | Contained in local main. | Already converged. |
| `codex/live-e2e-closeout-fix-w0` | `1ff8553bb` | Contained in local main. | Already converged. |
| `codex/w3-anthropic-fresh-e2e` | `835765198` | Contained in local main. | Already converged. |
| `codex/zero-llm-resume-e2e-r3` | `4b1db4cb` | Contained in local main. | Already converged; this branch supplies the clearer deterministic replacement contract. |
| `codex/evals-implementation` | `fa104ffb9` | Contained in local main. | Already converged; its separate evaluator tooling is not a resume-pipeline entrypoint. |
| `codex/patch-post-x3-continuation-w7` | `132d9305` | Contained in local main. | Already converged. |

Unrelated graph/embedding/telemetry worktrees were not merged merely because
they exist. They are outside the compact resume-pipeline scope and require
their own path-level review before any integration or deletion.

## Historical provider evidence

The prior live run at
`C:\Temp\apps-rg-main-full-resume-20260813\bare_e2e_20260813T061825Z_ce6d2750`
recorded:

```text
apps_research_openai  external_openai  gpt-5.6-terra      SUCCESS
l2_openai             external_openai  gpt-5.6-terra      SUCCESS
x3_gemini             google_gemini    gemini-3.6-flash   SUCCESS
```

It also recorded `SETUP`, `APPS_RESEARCH`, `U0`, `L1`, `L0`, `C0`, `PA`, `L2`,
`X1`, `X3`, and `DELIVERY` as passed. This is historical evidence to reproduce,
not a substitute for this branch's fresh live proof.

## Required verification after implementation

1. Run two fresh deterministic commands in separate directories and use
   `python -m apps_rg eval --compare-run-dir ...` to prove the documented
   normalized comparison.
2. Run one fresh live command from this branch. Inspect provider response IDs,
   observed models, stage order, X3 ledger record, all section checks, and
   DOCX reopen check.
3. Do not claim remote PR/push/main publication until an actual remote PR and
   exact local-main/origin-main SHA proof exist.
