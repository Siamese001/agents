# Apps RG v2 — Thread Feedback Incorporation Plan

## Status and purpose

This is a **plan-only** document. It incorporates the substantive feedback
from this thread into one implementation and proof plan. It does not authorize
a provider call, deletion, merge, push, or pull request by itself.

The target is a genuinely usable, stripped-down Apps RG v2 resume workflow for
the Anthropic Applied AI Architecture / Partnerships JD. Its normal operator
path must be simple, transparent, and fully inspectable.

## Current-state rule

All work for this plan must be performed from the actual local `main` worktree:

```text
C:\Git\apps_rg_v2-worktrees\codex-e2e-live-cost-cap-w4
branch: main
```

The checkout at `C:\Git\apps_rg_v2` is currently a different feature branch.
No result from that checkout may be described as a local-main result unless
its commit is proven to be on local `main`.

## Non-negotiable end state

One public command must produce a complete resume package with no required
interactive inputs:

```text
python -m apps_rg run
```

With no overrides, it must use the canonical Amit Ayer base resume and the
canonical Anthropic partnership JD. Optional JD/resume overrides remain
available only for an explicitly requested custom run.

The normal live path is exactly:

```text
Inputs/Setup
  -> Apps Research
  -> U0
  -> L1
  -> L0
  -> C0
  -> PA
  -> L2
  -> X1
  -> X3
  -> Delivery
```

`X2` is not an implicit or hidden stage in this bare pipeline. If a future
feature needs an additional check, it must be given a clear name, be shown in
the run summary, and be approved as part of the core stage contract. A provider
ledger must never label an X3 evaluation as X2.

The required package is:

```text
research.md
sources.json
resume.md
resume.docx
outreach_email.md
evaluation.json
run_summary.json
raw provider outputs / provider ledger
```

## Feedback-to-plan traceability

| Feedback incorporated | Plan treatment | Completion proof |
| --- | --- | --- |
| Make Apps RG v2 work end to end for the Anthropic partnership JD. | Make the canonical Anthropic JD and base resume the zero-argument defaults for the one public command. | Fresh run summary identifies the canonical JD/resume hashes, target company, target role, all stages, and delivery artifacts. |
| Prove a deterministic no-LLM-API run, including evals. | Build a separate, explicitly labelled `deterministic` mode using a fixed local source pack, fixed clock, and no provider call or credential. It must never be called a live-provider result. | Two clean deterministic executions yield equal normalized run records and pass the deterministic evaluator. |
| Also run the real pipeline with real providers; prior live OpenAI/Gemini runs worked. | Keep a separate `live` mode. It uses the configured actual OpenAI lane for Apps Research/L2 and actual Gemini lane for X3, with observed-model receipts. | One fresh `LIVE_PROVIDER_PASS` run has non-empty provider response IDs, observed models, and a successful X3 result. |
| The earlier Apps RG v2 implementation and earlier provider runs must not be dismissed as irrelevant. | Treat prior commits, PRs, and successful provider artifacts as the baseline to reproduce before changing the runner. | RCA timeline ties each historical success to its exact command, commit, worktree, provider receipt, and output package. |
| No fake keys. | Remove fake/default provider keys from the public runner, example commands, and runtime configuration. Provider calls receive only operator-supplied real credentials. Tests inject transports instead of inventing credentials. | Missing real credentials fail before dispatch; deterministic mode requires no keys; live ledger records real provider results only. |
| There should be no required manual inputs. | `python -m apps_rg run` uses canonical defaults and does not prompt. Overrides are optional flags. | A zero-argument command produces a run directory and records selected defaults. |
| Apps Research must happen before U0, then U0/L1/L0/C0/PA/L2/X1/X3 and email. | Freeze that exact stage order as the bare runtime contract; reject output if a stage is absent or out of order. | `run_summary.json.stages` is ordered exactly as the contract and each stage is terminal. |
| One correct main run; do not run the wrong branch/worktree. | Add an execution preflight that prints repository root, branch, commit SHA, and local-main ancestry before any run. | Run output and receipt contain the SHA; `git merge-base --is-ancestor HEAD main` and `git rev-parse main` are recorded. |
| There can be only one pipeline entry point. | Inventory every executable Apps RG entrypoint and retire, delete, or convert all non-canonical pipeline launchers into library-only code. Keep one public top-level command: `python -m apps_rg`. `run`, `eval`, and `show` are subcommands of that one command, not competing CLIs. | Entrypoint inventory has exactly one supported user-facing resume pipeline command; old launchers either no longer exist or exit with a migration message. |
| Preserve only the bare-bones core functionality, live LLM providers, and the named sub-stage structure. | Treat the stage contract below as the complete default product path; every retained dependency must have a direct role in one of those stages or be removed/isolated from `run`. | Dependency inventory contains no unused default-path component and each retained component maps to a named stage. |
| This is a stripped-down model; remove non-core governance and artificial blockers. | Make the normal run depend only on inputs, research sources, output structure, claim grounding, evaluation, and delivery. Remove W6/release-authority/cache/telemetry/legacy-spine requirements from the core command. Move any retained audit tooling outside the default path. | A clean environment with valid providers completes the core run without W6, policy-receipt, cache, or legacy-runner artifacts. |
| Do not introduce fake gates or call a partial fixture a full run. | Name the two modes truthfully: `DETERMINISTIC_OFFLINE_PASS` and `LIVE_PROVIDER_PASS`. Neither label may stand in for the other. | Mode, provider-call count, and evaluation type appear in every run summary. |
| Do a real RCA, including prior successful PRs/runs, rather than generic explanations. | Perform a commit/PR/artifact timeline audit before deleting or merging code. It must trace canonical CLI, actual worktree, provider configuration, success/failure artifact, and the exact code path used. | RCA table links each claim to commit SHA, PR, artifact directory, command, provider receipt, and root cause classification. |
| There should not be multiple competing COI/CLI paths. | Treat every executable route as a candidate competing entrypoint, including scripts, `__main__` modules, console scripts, and wrapper commands. | Static inventory plus command smoke test proves only the canonical command launches the resume pipeline. |
| Merge repository drift into local main rather than endlessly working in side branches. | Create a scoped worktree/branch convergence manifest. Compare each Apps RG v2 branch against local main, merge only resume-pipeline changes that are absent from main, and explicitly exclude unrelated work. | Manifest shows each scoped branch as already contained, merged, superseded, or rejected with a concrete path-level reason; local main passes the canonical run. |
| Commit dirty files intentionally. | Before any merge, classify dirty files by feature and commit only coherent, reviewed changes. Do not bulk-stage unrelated runtime artifacts. | `git status --short`, commit file lists, and branch diff are attached to the convergence manifest. |
| A PR means an actual PR. | Use a real remote GitHub pull request for publication: push a branch, create the PR, obtain the required review/merge decision, then fast-forward local main and verify `origin/main`. Never call a local merge a PR. | PR URL, merge commit, `main` SHA, and `origin/main` SHA are recorded separately. |
| Local main and origin/main must be handled clearly. | Separate local integration from remote publication. No push is implied by a local run; no claim of merge/push is made without exact SHA equality. | `git rev-parse main`, `git rev-parse origin/main`, and ancestry checks are reported after publication. |
| Do not run broad, unrelated tests or incidental files to claim success. | Use only targeted unit tests for changed contracts, one deterministic proof, and one live proof. No broad pytest sweep, `.exc`/Excel fixture, or unrelated legacy suite is part of the normal run. | Run log lists each command, its purpose, and the requirement it verifies. |
| Investigate the reported recurring “parlor”/wrong-run symptom instead of treating it as a new mystery blocker. | Add the exact observed symptom, command, stack trace, branch, worktree, and environment selection to the RCA; determine whether it is an alias, legacy entrypoint, stale import, or configuration fallback. | RCA names the concrete code path and includes a regression test that invokes the canonical command without that path. |
| Show outputs proving all gates passed and evals ran. | Standardize `run_summary.json` with one record per stage, detailed X1 section checks, X3 verdict/score, provider receipts, artifact paths, and explicit failure reason. CLI prints the same concise table and run directory. | A reviewer can open the summary alone and see every declared stage and evaluation outcome. |
| Show the full resume in a fenced block when asked. | Add `python -m apps_rg show --run-dir <dir> --artifact resume` to print the exact `resume.md`; operator reports must paste that exact text in a fenced block when requested. | CLI output byte-matches `resume.md`. |
| Not all resume sections ran; show every required section. | Make section validation data-driven and explicit. The canonical resume must contain header/contact, executive summary, core competencies, professional experience, technical expertise, education, certifications, and all source-resume employers. The email must have a subject, company, role, and minimum body. | X1 contains an individual PASS/FAIL for each required heading, each source employer, source availability, and each email field; any missing item fails the run. |
| Do not hide X3 under an X2/other provider label. | Pass the actual stage/section ID to the provider gateway and preserve it in the terminal ledger record. | X3 provider ledger terminal event has `stage=X3` and `section_id=X3`. |
| Do not claim completion from a partial result. | Define completion only as all declared stages plus every required artifact, section check, provider receipt (for live), and X3 pass. | Acceptance matrix below is satisfied on one fresh run; otherwise status is `FAIL` with the first failed stage. |
| No generic RCA, excuses, false reassurance, or misleading status claims. | Adopt evidence-first reporting: state the exact command, worktree, commit, run directory, individual stage result, and unproven item. Explain Git/PR distinctions plainly when requested. | Final run report can be independently checked from the linked artifacts; it uses `NOT RUN`/`FAIL` rather than implying success. |
| A plan-only request and a local-main request were both made. | When the current instruction says plan-only, make only a plan artifact. When the current instruction names local main, put the artifact in the actual local-main worktree. Do not silently create a different branch or execute the plan while presenting it as planning. | Plan commit/diff shows documentation-only paths; no provider call, code edit, merge, or push is made during plan-only work. |

## Planned runtime design

### 1. One command, three explicit actions

The only public entrypoint is `python -m apps_rg`. It has three actions:

```text
python -m apps_rg run [optional full-product overrides]
python -m apps_rg eval --run-dir <dir>
python -m apps_rg show --run-dir <dir> --artifact resume|research|summary|evaluation
```

There are no other supported pipeline launch commands. Library modules remain
importable only when needed by the canonical command or targeted tests.

### 2. Input contract

`run` with no flags loads the canonical resume and Anthropic JD. It records:

```text
repository root
branch and commit SHA
run mode
JD path and SHA-256
resume path and SHA-256
target company and role
```

No interactive questionnaire, fake key, fake provider, cached success, or
hidden worktree selection is allowed in the normal path.

### 3. Minimal stage contract

| Stage | Core responsibility | Required visible result |
| --- | --- | --- |
| SETUP | Resolve defaults, inputs, mode, and real credentials for live mode. | Input refs/hashes, branch/SHA, mode. |
| APPS_RESEARCH | Retrieve sources and produce a factual research brief. | Source register, research brief, retrieval result. |
| U0 | Verify the resolved core inputs exist. | Individual input-presence checks. |
| L1 | State the tailoring goal and source scope. | Small plan object. |
| L0 | Select the one live/deterministic route. | Named route. |
| C0 | Verify usable research source URLs or local deterministic source records. | Source count and URL/source-pack checks. |
| PA | Build the resume/email prompt from JD, source resume, and research. | Prompt shape/version summary, never secret contents. |
| L2 | Produce the tailored resume and outreach email. | Raw response plus extracted outputs. |
| X1 | Validate every required resume and email section. | Per-heading, per-employer, and per-email-field checks. |
| X3 | Evaluate tailoring, claim grounding, source use, and email targeting. | Verdict, score, reasoning, raw evaluator output, actual provider receipt in live mode. |
| DELIVERY | Write and reopen required output files. | Artifact list plus DOCX readability and content checks. |

The stage set is intentionally limited. W6, release authorization, cache
seals, telemetry collectors, external governance receipts, and legacy
multi-spine orchestration are not core stages and cannot block `run`.

### 4. Required resume and email outputs

The X1/DOCX checks must require:

```text
Resume
  Header/contact information
  Executive Summary
  Core Competencies
  Professional Experience
    Every employer represented in the selected base resume
  Technical Expertise
  Education
  Certifications

Email
  Subject line
  Target company named
  Target role named
  Candidate claims drawn only from the base resume
```

The machine-readable run summary must expose each check individually; a
character count alone is never a section-completeness result.

### 5. Two honest evaluation modes

#### Deterministic / no-provider mode

This mode exists solely to prove repeatability without any LLM API call. It
uses a fixed, versioned local source pack and deterministic transforms. It must
not require a credential, call a provider, or be described as a live model run.

It runs twice in clean run directories and compares a normalized evidence
projection: stage sequence, input hashes, output section checks, source IDs,
and evaluator result. Any timestamps, physical run paths, and reproducible
container metadata are normalized only by named rules.

#### Live-provider mode

This is the actual end-to-end product proof. It uses only valid configured
provider credentials. It records the requested and observed model, response
ID, terminal success, and usage for each provider call. It executes one
explicit X3 evaluation and fails on any non-pass verdict or score below the
configured threshold.

No fixture, mock, local response, or fake key may be used to report
`LIVE_PROVIDER_PASS`.

## Nuclear RCA workstream

Before major deletion or consolidation, produce a factual RCA with these
evidence columns:

| Question | Required evidence |
| --- | --- |
| Which historical PR/commit introduced Apps RG v2? | Git log and GitHub PR URL/merge SHA. |
| Which commands previously produced live provider success? | Exact command, artifact path, response IDs, observed models, and dates. |
| Why did later work invoke a different path? | Stack/CLI trace from invocation to runner, plus checked-out branch/worktree. |
| Why did W6 or other non-core blockers appear? | Call graph showing whether the legacy runner was selected; identify the exact import/entrypoint that introduced it. |
| Why were provider keys or fixture semantics observed? | Configuration lookup trace with values redacted; distinguish test-only injection from public runtime. |
| Why did output reporting claim success without all sections? | Compare prior X1 logic and artifact contract against the required section matrix. |
| Why are there multiple entrypoints? | Full entrypoint inventory and ownership/deletion decision for each. |

The RCA must name a root cause for each divergence: wrong worktree, wrong
entrypoint, wrong mode, unmerged code, config fallback, or incomplete output
contract. It may not use generic labels such as "governance blocker" without
the exact call path that selected it.

## Worktree, branch, and publication plan

1. Create a scoped Apps RG v2 convergence manifest from all current worktrees
   and branches. For each candidate, record head SHA, changed paths relative to
   local main, canonical-entrypoint impact, and whether it is already contained
   in main.
2. Reconcile only changes that affect the one resume pipeline, its required
   tests, or its required outputs. Do not silently merge unrelated graph,
   embedding, telemetry, or experimental work merely because it is present in
   the repository.
3. Make every retained change an intentional commit. Preserve unrelated dirty
   data and never bulk-stage generated artifacts.
4. For remote publication, create a normal branch, push it, and open an actual
   GitHub pull request. A local merge is not a PR.
5. After the PR merge decision, fast-forward the actual local-main worktree,
   run the canonical proof from that worktree, then verify exact local/remote
   SHA ancestry before saying it is on `origin/main`.

## Acceptance matrix

The plan is complete only when all rows are independently proven:

| Requirement | Required proof |
| --- | --- |
| One public pipeline entrypoint | Entrypoint inventory + `python -m apps_rg --help` shows the sole supported command. |
| Zero-input default run | `python -m apps_rg run` succeeds with the canonical Anthropic JD/resume. |
| Deterministic proof | Two no-provider executions pass and compare equal under documented normalization. |
| Live product proof | Fresh live run has real OpenAI and Gemini receipts, no mocks/fake keys, and every declared stage PASS. |
| Stage completeness | Summary contains SETUP, APPS_RESEARCH, U0, L1, L0, C0, PA, L2, X1, X3, DELIVERY in order. |
| Résumé completeness | Every required heading and base-resume employer passes X1 and DOCX reopen check. |
| Email completeness | Subject/company/role/grounding checks pass. |
| Evaluation | X3 raw output, verdict, score, provider identity, and terminal receipt exist. |
| Observable outputs | CLI prints run directory and stage table; `show` emits exact requested artifact. |
| No artificial core blocker | Live canonical path completes without W6, legacy spine, cache seal, or telemetry requirements. |
| RCA | Commit/PR/run timeline and exact divergence roots are written and evidence-linked. |
| Local-main / remote truth | Branch/commit/PR/push state is reported with exact SHAs; no local merge is called a PR. |

## Execution order

1. Freeze the above contract and write the RCA/convergence manifest.
2. Consolidate the entrypoints into the single public command.
3. Strip the default run to the listed core stages and isolate/remove non-core
   blockers from that route.
4. Implement the explicit output, section, email, and provider-receipt
   contracts.
5. Add only targeted contract tests; do not use broad legacy tests as a stand-in
   for an end-to-end proof.
6. Run the deterministic proof twice.
7. Run one fresh live proof from local main.
8. Open every requested output, show the exact full résumé when requested, and
   report the artifacts without claiming more than they prove.
9. Complete the PR/local-main/origin-main sequence only after the proof passes.

## Immediate plan-only deliverable

This document is the incorporated plan. The next implementation turn should
start at step 1 (RCA and convergence manifest) and must not silently substitute
a fixture, a different worktree, a broad unrelated test suite, or a legacy
governance path for the required product run.
