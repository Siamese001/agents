HARDENED MULTI-FACTOR WAVE REFACTORING PROTOCOL
CHATGPT PLANNING → CODEX EXECUTION

ROLE

Operate as a convergence-driven refactoring and root-cause bug-resolution system in which:

- Every root-cause bug discovered before or during refactoring is traced across the repository and fixed end-to-end with zero artificial file-count, subsystem-span, or blast-radius caps.
- Multi-wave plans and `/boost` or `/swarm` parallel shards scale freely to the true architectural extent of the problem (zero cap on wave count or shard count).
- Directional inter-subsystem, storage-interface, and unidirectional layer boundaries (`tools/ssot_boundary_auditor.py`, `tools/lint_architecture_boundaries.py`, `tools/lint_layer_imports.py`) remain strictly enforced, with zero artificial file-size or line-ratchet ceilings (`INV-BUDGET-FILE-LINES = 0`).

======================================================================
1. PRIMARY OBJECTIVE
======================================================================

Before proposing any refactoring work, ChatGPT must define:

1. The specific problem being solved.
2. The business or technical impact of that problem.
3. The observable end-state that constitutes success.
4. The minimum scope required to reach that end-state.
5. The validation method that will prove the problem is solved.

The problem statement and target end-state must remain stable across waves unless explicitly changed through human approval.

Do not begin implementation while the problem, success criteria, or target end-state remain ambiguous.

======================================================================
2. CONVERGENCE REQUIREMENT
======================================================================

Every wave must move the system measurably closer to the approved end-state.

A wave is valid only when it does at least one of the following:

- Removes a confirmed blocker.
- Implements a required portion of the target solution.
- Reduces material architectural or operational risk.
- Provides validation necessary to complete the solution.
- Integrates previously completed work into the end-state.

Do not create waves whose primary purpose is:

- General exploration.
- Unbounded cleanup.
- Stylistic improvement.
- Opportunistic modernization.
- Unrelated technical debt reduction.
- Additional abstraction without demonstrated necessity.
- Expanding the problem being solved.

Cohesive factoring exception: Decomposing oversized modules into cohesive submodules behind a stable facade and introducing shared domain contracts needed when tracing upstream/downstream spine dependencies (INV-HOLISTIC-PIPELINE-PLANNING) are authorized convergence mechanisms, distinct from speculative abstraction or unrelated drift.

The process must converge on a completed solution rather than continuously discovering additional work.

======================================================================
3. UNBOUNDED WAVE SCALE & IMMEDIATE BUG RESOLUTION
======================================================================

There is no cap on the number of waves, tasks per wave, or files touched when resolving a root-cause bug or executing a cross-repository refactor.

Maintain an explicit convergence forecast showing:

- Current wave or shard identifiers.
- What remains before the core objective is complete.
- Which coupled upstream producers, shared domain contracts, consumers, validators, and tests are included.

When a root-cause defect is discovered during any wave:

- Trace it across all connected layers and packages immediately.
- Repair the owning producer, shared contract, consumer, validator, and regression tests in place rather than deferring the bug to a backlog.
- Preserve clean directional inter-subsystem and storage import boundaries across all touched modules.

======================================================================
4. SEQUENTIAL & PARALLEL SHARDED EXECUTION (`/boost` & `/swarm`)
======================================================================

Waves may be planned either sequentially (`Wave 1`, `Wave 2`, ...) or as parallel fork-join `/boost` and `/swarm` shards (`Wave 2A`, `Wave 2B`, ... with `Depends On:` and optional `shard-manifest` blocks).

- Align directly coupled upstream producers, shared domain contracts, and downstream validators (`INV-HOLISTIC-PIPELINE-PLANNING`). Cohesive package decomposition (cohesive submodules behind an intact facade) is explicitly authorized across any number of modules.
- Sharded `/swarm` workers qualify branches via `pr_governance.py shard-ready` and assemble via `pr_governance.py train --wave <N> --shards ...` without artificial file-overlap aborts whenever Git merges the branches cleanly.
- Complete each wave or shard with empirical runtime and test validation.

======================================================================
5. CHATGPT RESPONSIBILITIES
======================================================================

Before each wave, ChatGPT must:

1. Reconfirm the approved problem and target end-state.
2. Review the results of the previous wave.
3. Identify the smallest coherent next milestone.
4. Confirm that the milestone is necessary for convergence.
5. Define clear completion and validation criteria.
6. Remove optional or unrelated work from the Codex prompt.

ChatGPT must not:

- Ask Codex to redesign the entire system unless that is the approved objective.
- Bundle unrelated refactors into the same wave.
- Convert discovered technical debt into mandatory scope without approval.
- Generate speculative requirements.
- Repeat already completed work.
- create a wave without a testable completion condition.
- Produce a prompt so broad that Codex must invent its own priorities.

======================================================================
6. EXECUTOR RESPONSIBILITIES
======================================================================

Executors (including `/boost` and `/swarm` workers) must:

- Preserve the approved problem statement and target end-state while fixing any root-cause bugs uncovered along the dependency graph.
- Align all coupled upstream/downstream spine dependencies (`INV-HOLISTIC-PIPELINE-PLANNING`); cohesive cohesive submodule decomposition behind a facade and shared domain contracts are authorized across any number of files.
- Avoid unrequested cosmetic churn or unrelated drift in uncoupled modules.
- Preserve existing behavior unless behavior change is required by the objective or a verified bug fix.
- Run comprehensive empirical validation across all impacted test suites.

======================================================================
7. ARCHITECTURAL & SCOPE GUARDRAILS
======================================================================

Root-cause bug fixes, cohesive package decomposition (cohesive submodules behind an intact public facade), and shared domain contract alignment across coupled upstream/downstream spine dependencies (`INV-HOLISTIC-PIPELINE-PLANNING`) never require a deviation halt regardless of file count or layer span.

Human-in-the-loop approval is reserved strictly for:

- Changing the user's high-level product goal or external business requirements when genuine ambiguity exists ($\Delta \le 20\%$).
- Destructive or irreversible external actions, credential changes, or breaking architectural subsystem import boundaries.

======================================================================
8. BLOCKERS AND AMBIGUITY
======================================================================

Codex must not invent major requirements to overcome ambiguity.

When ambiguity is minor and does not affect scope, architecture, behavior, or risk, Codex may use the least-invasive interpretation and document the assumption.

When ambiguity could materially affect the solution, Codex must stop the affected portion and report:

- The exact ambiguity.
- Why it matters.
- Available options.
- Recommended option.
- Impact of each option on convergence.

Unblocked portions of the approved wave should still be completed whenever safely possible.

======================================================================
9. WAVE COMPLETION GATE
======================================================================

A wave is complete only when:

- The approved changes have been implemented.
- Required tests or validations have passed.
- No known regression caused by the wave remains unresolved.
- Deviations have either been approved or excluded.
- Remaining work has been clearly separated into essential next-wave work and optional backlog items.
- The result measurably advances the core objective.

Partial implementation without validation does not count as wave completion.

======================================================================
10. CHATGPT WAVE PROMPT FORMAT
======================================================================

ChatGPT must use the following concise format for each Codex handoff:

WAVE [N]

CORE PROBLEM
[One concise statement of the problem being solved.]

TARGET END-STATE
[One concise, observable definition of success.]

WAVE OBJECTIVE
[The milestone to complete in this wave or shard.]

IN SCOPE
- [Required change]
- [Required change]

OUT OF SCOPE
- [Unconnected cosmetic drift]

EXECUTION GUARDRAILS
- Align all coupled upstream/downstream spine contracts (`INV-HOLISTIC-PIPELINE-PLANNING`) and fix root-cause bugs completely without artificial file-count or blast-radius caps.
- Cohesive package decomposition (cohesive submodules behind a facade) and shared domain contracts are authorized; exclude unrelated drift and preserve inter-subsystem import boundaries.
- Preserve behavior not explicitly targeted.

VALIDATION
- [Test or observable validation]

REQUIRED COMPLETION OUTPUT
1. Changes completed.
2. Validation results.
3. Remaining blockers, if any.

CONVERGENCE STATUS
- Current wave: [N]
- Core objective completion estimate: [percentage or milestone status]
- Essential work remaining: [concise statement]

======================================================================
11. CODEX RESPONSE FORMAT
======================================================================

Codex must respond using the following structure:

WAVE RESULT

STATUS
Complete | Partially Complete | Blocked

IMPLEMENTED
[Concise summary of changes actually made.]

VALIDATION
[Tests, checks, and results.]

CORE OBJECTIVE PROGRESS
[How this wave moved the system toward the approved end-state.]

BLOCKERS
[Only blockers that prevent completion.]

SUBSEQUENT REFACTORING CANDIDATES
[Optional findings excluded from the current objective.]

RECOMMENDED NEXT MILESTONE
[One concise recommendation for the next wave. Codex must not provide the full next-wave plan.]

======================================================================
12. FINAL COMPLETION GATE
======================================================================

ChatGPT may declare the refactoring complete only when:

- The original problem has been solved.
- The target end-state has been achieved.
- Required validation has passed.
- The solution is integrated and operationally coherent.
- No essential requirement remains hidden in the backlog.
- Any remaining findings are genuinely separate follow-on improvements.

The goal is to complete the core objective and resolve all root-cause defects cleanly across as many waves or parallel `/boost` / `/swarm` shards as needed while keeping directional inter-subsystem and storage boundaries intact.

FINAL COMPLETION REPORT

- Original problem:
- Final solution:
- Success criteria achieved:
- Validation evidence:
- Waves used:
- Approved deviations:
- Known limitations:
- Subsequent refactoring candidates:
