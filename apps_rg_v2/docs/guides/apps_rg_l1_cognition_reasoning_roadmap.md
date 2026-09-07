# L1 Cognitive Planner Roadmap

Status: replacement plan, derived from the goal of improving L1 cognition and
reasoning. The existing W0-W6 contracts are reusable support code; they are not
this roadmap and do not prove that L1 became more capable.

Scope: `apps_rg_v2` only. Do not add or modify any external runtime.

## Goal

Make L1 a materially better planner. Given a U0-validated request, it must:

1. understand the actual goal and constraints;
2. decompose it into atomic, related requirements;
3. deliberate over feasible ways to serve those requirements;
4. challenge its own assumptions before handing work downstream; and
5. revise the affected plan when observed outcomes disprove an assumption.

The success condition is a safer, more compliant downstream artifact—not a
larger L1 schema. L1 remains advisory: it may recommend a plan, uncertainty,
and verification work, but it does not take L0 route authority, C0 evidence
authority, PA prompt authority, or L2/L3 execution authority.

```
U0 request
   |
   v
L1: understand -> decompose -> deliberate -> critique -> revise
   |                  |              |             |          |
   |                  |              |             |          +-- bounded update
   |                  |              |             +-- assumptions and failures
   |                  |              +-- alternative advisory plans
   |                  +-- atomic goal and constraint graph
   +-- source-bound goal frame
```

## Current cognitive gaps

The present v2 capsule improves bookkeeping, but it does not yet supply the
full cognitive loop above.

| Gap | Current behavior | Needed reasoning capability |
| --- | --- | --- |
| Understanding | A bullet or explicit-requirement line is usually one requirement. | Recover atomic requirements, their logical relations, and qualifier scope. |
| Semantics | Type and target choices are mainly keyword/taxonomy matches. | Distinguish actual meaning, unknown concepts, hard constraints, and preferences. |
| Deliberation | The DAG orders work but does not compare ways to satisfy the goal. | Build feasible options, their dependencies, risks, and justification. |
| Critique | Open decisions exist, but L1 does not systematically challenge its plan. | Detect uncovered goals, conflicts, invalid assumptions, and broad targeting before execution. |
| Revision | Failure receipts are available after execution. | Update only the affected belief/plan after an observed contradiction, or escalate. |

## Target cognitive plan

L1 v3 is an immutable, source-bound cognitive plan with five linked ledgers.
Stable IDs and source/receipt references make its reasoning inspectable; raw JD
text remains targeting input and is never candidate evidence.

| Ledger | Cognitive function | Required content |
| --- | --- | --- |
| Goal and constraint frame | Understand success. | Requested artifact, audience, role, hard constraints, preferences, conflicts, input authority, definition of done, and one closed-vocabulary safe directive or explicit U0 escalation per constraint. Raw constraint prose is not retained. |
| Atomic requirement graph | Decompose meaning. | Atomic requirements, parent/child links, `AND`/`OR`/`NOT`/exception relations, source spans, type, modality, qualifier scope, unknown semantics, and whether the V2 parent has a C0 evidence-obligation path. |
| Feasibility graph | Deliberate over options. | Candidate work-unit options, dependencies, needed source/evidence shape, counterevidence risk, and target/escalation rationale. |
| Alternative-plan and critique ledger | Compare and challenge plans. | Primary/alternative plan when there is a real trade-off, coverage/risk rationale, uncovered goals, conflicts, assumptions, counterexamples, and designated resolver. |
| Revision ledger | Learn from observed outcomes. | Parent plan, disproved assumption, observed failure, affected requirement, bounded revision, predicted correction, and escalation when revision is unjustified. |

`MAPPED`, `ESCALATED`, and `UNMAPPED` are separate decisions. Escalation is a
safe result when appropriate; it is not successful targeting, evidence, or
completion.

## Evidence standard

Each wave has one direct capability claim and one acceptance gate. The gate is
not the work; it prevents a plausible implementation from being called an L1
improvement when it did not improve reasoning.

Before the first behavior change, lock a small source-bound development set and
a sealed holdout. Include ordinary, compound, cross-cutting, unknown,
conflicting, stale, and missing-evidence requests. Human review supplies only
semantic labels and final outcome judgments; fixtures and validators never
invent human grades.

Track these outcome measures:

1. **Understanding fidelity**: atomic requirement, relation, type, and
   qualifier accuracy against adjudicated source spans.
2. **Plan coherence**: each critical requirement has a defensible option or an
   explicit escalation; no conflict is silently ignored.
3. **Critique quality**: precision and recall for missing preconditions,
   contradictions, broad mappings, and unsupported assumptions.
4. **Revision quality**: resolvable L1 failures corrected by one bounded
   revision without widening unrelated scope.
5. **Downstream usefulness**: blinded requirement compliance, unsupported claim
   rate, latency, and cost for paired v1/v3 shadow artifacts.

Digests, schema validity, receipt presence, and unit-test counts are regression
checks. They are not cognition measures.

## Priority roadmap

### Wave 0 — Lock the behavioral target

Priority: P0. Small enabling checkpoint; not an L1 cognition claim.

Create the source-bound development/holdout split and a concise scoring guide.
For each request, annotate goal, atomic requirements, constraint relations,
appropriate escalation, and expected completion criteria. Run v1 and current
v2 once to identify the dominant error slice.

The Apps RG-local W0 baseline receipt runs those two planners once per frozen
development fixture, persists only fixture/source-span digests and structural
observations, and names the dominant slice using a declared risk order. It is
not a v3 comparison, a semantic-quality grade, or protected-holdout evidence.

Exit:

- The split and guide are locked before candidate tuning.
- The baseline includes source-span examples of decomposition, semantic,
  targeting, critique, and revision failures.
- One priority failure slice is named for Wave 1.

Defense: this is only enough measurement to ensure that the first direct
intervention attacks the real cognitive bottleneck rather than a convenient
infrastructure task.

### Wave 1 — Understand and decompose the request

Priority: P0. First direct cognition intervention.

Capability: L1 produces a goal/constraint frame and atomic requirement graph,
not a list of bullet-sized keyword matches.

Build:

- A deterministic clause and relation parser for bullets and prose. It splits
  independently actioned sentences and complete same-relation coordination
  chains only when every member has an explicit or safely inherited predicate;
  a mixed boolean chain or one ambiguous member keeps the full source-bound
  parent and records why review is needed.
- Parent/child requirement identities and `AND`, `OR`, `NOT`, exception, and
  shared-qualifier relationships.
- A constraint frame that separately binds U0 user constraints and U0 output
  preferences, while separating non-negotiable requirements, preferences,
  output constraints, and conflicting instructions.
- A precedence rule: a known hard user constraint wins over a conflicting
  non-binding preference. L1 withholds that preference, records the safe
  decision and critique finding, and never turns a preference into an
  unnecessary hard-goal block. Conflicting hard constraints still escalate to
  U0.
- A closed semantic vocabulary for ordinary output constraints (for example,
  known output format, numeric length limit, or a structured inclusion/exclusion
  directive). Each recognized constraint gets a source-bound safe directive;
  each unknown hard value becomes a named U0 escalation rather than silently
  disappearing or being copied into a provider prompt. Raw user-supplied keys
  and values are replaced by source digests in the persisted planning ledger.
- Explicit `UNKNOWN` semantics: a generic `must`/`required` pattern cannot
  disguise an unknown concept as a safe generic type.

Acceptance gate:

- Understanding fidelity improves over v1, especially on compound,
  cross-cutting, and unknown slices.
- Critical qualifier/relation errors do not increase.
- Every split, merge, and unknown result is source-span and rule explainable;
  ambiguity is escalated rather than invented.

Stop: if this capability fails, refine decomposition from observed errors or
reject it. Do not start targeting, scheduling, or replan work.

Defense: this improves the object L1 reasons over. Later stages cannot repair a
plan whose requirements were merged, mis-scoped, or misread.

### Wave 2 — Deliberate over feasible plans

Priority: P0. Second direct cognition intervention.

Capability: for each atomic requirement, L1 reasons about feasible ways to
serve it, what could disprove an option, and whether to target, defer, or
escalate.

Build:

- A feasibility graph linking a requirement to candidate work units, needed
  input/evidence shape, dependencies, and counterevidence risk.
- A primary advisory plan plus an alternative only when there is a real
  trade-off, such as split versus merge work or direct support versus escalation.
- A choice rationale comparing coverage, constraint satisfaction,
  preconditions, and risk. L1 recommends; L0 still selects routes and C0 still
  decides evidence.
- A global constraint decision alongside each requirement decision: project a
  closed safe directive, retain an already-consumed scope, defer an unsafe
  preference, defer a preference that conflicts with a hard constraint, or
  escalate an unresolved/conflicting hard constraint to U0.
- A closed output-format family check: compatible resume variants may coexist,
  but incompatible final-artifact formats defer a non-binding preference or
  escalate the conflicting hard constraint rather than reaching PA together.
- A precise target rule: map only when a work-unit option satisfies the type and
  qualifiers. Otherwise ask the smallest resolver question.

Acceptance gate:

- Plan coherence and targeting precision improve on the holdout.
- Broad mappings decrease or remain zero; appropriate escalation stays high.
- Every critical requirement has a defensible option or a named unresolved
  decision. Escalation never counts as target success.

Stop: reject a decorative alternative-plan ledger, unjustified choices, or any
reversion to one-keyword-to-one-section mapping.

Defense: a DAG only orders work. Deliberation determines whether the work is
actually the right response to the user's goal.

### Wave 3 — Critique the plan before execution

Priority: P1. Third direct cognition intervention.

Capability: L1 performs a bounded adversarial review of its own plan and emits
an actionable critique instead of silently forwarding assumptions downstream.

For every critical requirement, the critique asks:

- Is source and qualifier scope preserved?
- Does the selected plan serve the requirement, or only a related keyword?
- Does another requirement or user constraint conflict with the plan?
- Is a briefing, candidate-evidence, output-format, or downstream-capability
  assumption unsupported?
- Would a counterexample create an unsupported candidate claim or invalid
  completion claim?
- Do independently valid constraints contradict each other (for example, a
  minimum output size that exceeds the maximum), or does one require and
  another forbid the same structured output feature?

The critique ledger contains severity, failed invariant, affected requirement,
counterexample/missing precondition, and permitted resolver. It may block its
own advisory plan or request clarification; it cannot create evidence, choose a
route, or fabricate a resolution.

Acceptance gate:

- Critique quality improves on seeded and natural conflict, missing-
  precondition, and broad-target cases.
- It suppresses no valid critical requirement and creates no candidate-evidence
  claim.

Defense: decomposition and deliberation still fail if their assumptions are not
challenged. This is an inspectable self-correction loop, not hidden
chain-of-thought or an unused model knob.

### Wave 4 — Revise from observed outcomes

Priority: P1. Fourth direct cognition intervention.

Capability: when the source-bound C0 evidence contract reports an observed
contradiction of a named plan assumption, L1 produces one smaller, justified
revised plan or escalates. PA/L2/L3 observations can prove a downstream
consumption or disposition defect, but cannot prove that L1's selected plan
assumption was false and therefore cannot manufacture a replan.

Build:

- Revision triggers are limited to source-bound C0 contradiction/absence that
  falsifies a named L1 assumption. PA/L2/L3 downstream omission and
  execution-precondition observations are retained as source-bound defects and
  safety blocks, never converted into an arbitrary L1 revision.
- When an atom is semantically targetable but its V2 parent has no C0
  obligation, record `C0_INSUFFICIENT` with
  `C0_PARENT_OBLIGATION_MISSING`; never manufacture evidence or silently
  promote the atom.
- Assumption-to-outcome links so L1 states what it learned rather than merely
  which receipt failed.
- One revision limited to affected requirements, option, and dependencies.
  Repeated/unchanged diagnostics escalate; they never automatic-retry or change
  routes.
- A parent-versus-revised comparison stating predicted correction and new risk.
- An Apps RG-local C0 outcome projection writes the exact source-bound gap
  disposition into L2's non-display diagnostics after parsing, rather than
  trusting a model to remember audit tags. It cannot change provider response
  content, display content, the claim ledger, evidence, a route, retries, or
  promotion authority. The following output-disposition gate verifies that the
  projection remains bound to L2; if it does not, it blocks the Apps RG X3
  mirror before the existing exit handoff.
- The same Apps RG-local finalization disposition verifies the source-bound
  goal-constraint advisory. A remaining hard-constraint escalation or semantic
  conflict blocks the local X3 mirror; it never invents a resolution, changes
  the provider response, or promotes the artifact.

Acceptance gate:

- One revision corrects more resolvable L1 planning errors than a no-revision
  control without increasing false targets, unsupported claims, or unrelated
  changes.
- Failures outside L1's causal responsibility are recorded as downstream defects
  and do not trigger arbitrary plan changes.

Defense: a planner reasons over time only if it changes the relevant belief or
plan after a prediction fails. Generic failure records and retry loops are not
learning.

### Wave 5 — Prove the better plan improves the pipeline

Priority: P0 gate for any product-visible use. It adds no new L1 capability; it
proves that Waves 1-4 are useful.

Run paired v1/v3 shadows on every case in the sealed holdout. Each arm must
persist the same frozen-input and provider/tool configuration binding before
execution; capture must verify that binding and the U0 JD payload before it
records a pair. Assemble the one-pair captures into a manifest that re-derives
the complete cohort, then require an independent evaluation authority to bind
each opaque committed case identity to exactly one Apps-local frozen-input
digest. Bind each requirement and critique decision to C0, PA, and L2/L3
receipts, then blind-review the final artifacts. Report understanding
fidelity, plan coherence, critique/revision quality, output requirement
compliance, unsupported-claim rate, completion, latency, and cost.

Promotion requires:

- Meaningful protected-holdout improvement across the complete committed cohort
  in Wave 1 and Wave 2 measures and downstream requirement compliance.
- No safety regression; escalation stays separate from successful targeting and
  C0 remains the evidence authority.
- Human adjudication for ambiguous semantics and named release approval for a
  limited, observable, reversible rollout.
- Requirement-level observation and rollback.

### Apps RG-only evidence handoff

Use `library API: apps_rg.evals.l1_cognitive_evaluation_cli` to freeze the
non-secret input/configuration receipts, capture an already-completed pair,
build separately routed blinded-review material, seal exactly human-authored
records, and evaluate W6 readiness. The CLI has no runtime-launch,
reviewer-label, or treatment-activation command. Digest sealing neither creates
a human judgment nor attests an identity. The handoff procedure is
`src/apps_rg/evals/L1_COGNITIVE_HUMAN_EVIDENCE_HANDOFF.md`.

Defense: the goal is a better cognitive plan that causes a safer, more compliant
pipeline result—not a smarter-looking planning artifact.

## Existing code: disposition

Reuse existing v2 capsules, C0 reconciliation, execution receipts, scheduling,
diagnostics, and comparison tooling only where they serve a named capability.

- Keep source spans, taxonomy versioning, immutable capsules, and C0 claim
  boundaries as safety constraints.
- Replace line-level parsing and keyword-only targeting in Waves 1 and 2.
- Reuse the DAG only after Wave 2 gives its nodes and edges feasibility
  rationale.
- Reuse failure diagnostics only after Wave 4 binds them to a disproved L1
  assumption and scored revision result.
- Keep the current W6 comparator as a tamper/determinism regression tool. It
  cannot claim semantic improvement because its fixtures are synthetic and its
  human/runtime outcomes are absent.

No supporting artifact is a roadmap exit condition by itself.

## Delivery-wave map and current evidence boundary

The capability roadmap above is the goal. The delivery waves below are the
implementation and proof sequence that prevents any one of its ledgers from
being mistaken for the goal itself.

| Delivery wave | Goal capability served | Apps RG implementation evidence | What it cannot prove alone |
| --- | --- | --- | --- |
| W0 | Measure the target before tuning. | Frozen v2-control/v3-candidate protocol, a source-bound development-only receipt that runs v1 and v2 exactly once per fixture, development calibration, protected-holdout commitment, and non-promoting outcome receipt. The baseline names `COMPOUND_AND_RELATION_DECOMPOSITION` as the Wave 1 technical priority slice. | Human utility, protected-holdout performance, or promotion. |
| W1 | Make understanding and decomposition affect the pipeline. | The v3 plan splits independently actioned sentences and unambiguous coordinated clauses, then projects atom identity, relation scope, qualifier scope, inherited-predicate state, and source-bound coverage directives into section-scoped PA prompts. Its goal frame now interprets both U0 user constraints and U0 output preferences, converts known output constraints into closed safe directives, and turns unknown hard values into explicit U0 escalations without retaining raw request keys or prose. Conditional relations and ambiguous coordination are escalated rather than arbitrarily targeted. | Understanding fidelity or output improvement. |
| W2 | Make deliberation affect the pipeline without granting authority. | Each target is conditional on C0, has a named safe fallback, and plan validation re-derives the feasibility and alternative ledgers so a decorative selection cannot be substituted. The same ledger chooses a safe action for every goal constraint: a hard constraint overrides a conflicting non-binding preference, while hard-versus-hard semantic conflict escalates to U0. The unassigned default is v2 control; candidate requires an explicit U0 assignment. | A matched provider run or a quality decision. |
| W3 | Make critique actionable before execution. | The critique is deterministically re-derived from the goal frame, atomic graph, and selected options; it catches missing evidence input, conditional C0 obligations, broad target collisions, qualifier scope, unknown hard constraints, and semantic numeric/require-forbid conflicts. | Critique precision/recall on a protected set or human agreement. |
| W4 | Revise only the disproved part of the plan and retain the safe output disposition. | An observed C0 failure replaces only the selected affected option with its declared escalation fallback. The revision carries the exact C0 outcome-receipt digest, and its PA-safe advisory must bind the same digest; a re-digested non-C0 outcome code or unsafe observation reference is rejected. The Apps RG-owned L2 diagnostic projection retains the required gap disposition and is verified before X3 finalization. That local disposition also blocks X3 finalization for a source-bound unresolved hard goal constraint; it does not solve the constraint or alter generated content. | A quality decision before blinded review. |
| W5 | Decide whether better cognition produced a better résumé. | Both shadow arms must retain the same Apps RG-local frozen-input/configuration binding; capture verifies the U0 JD payload. One-pair captures are assembled into a manifest that re-derives the complete sealed cohort before blinded review accepts opaque completed-output variants. A separate source-bound human capability assessment must score the exact control capsule and candidate plan/revision evidence for every committed case. | Release or production authorization. |
| W6 | Govern a bounded rollout from the evidence. | An Apps RG-only verifier re-derives the captured cohort, blinded packet/mapping provenance, two opaque-variant human assessments plus an independent adjudication per pair, P1/P2 measurement deltas, the candidate unsupported-claim count, and five source-bound L1 capability deltas. Independent human-attested case bindings must cover every opaque committed holdout identity exactly once. It then binds holdout, rollback-plan, and named approval. A valid negative result remains a blocked result rather than invalid evidence. Even when all verify, it only reports readiness for a human-operated limited rollout; it cannot activate or promote. | Any automatic promotion. |

The priority is W0 -> W2 -> W4 -> W5 -> W6. W1 and W3 are prerequisites for
that chain, not substitutes for it: the pipeline cannot demonstrate a causal
effect without downstream consumption, and downstream consumption cannot
demonstrate utility without matched runs and blind review.

### Current implementation status and causal evidence

| Delivery wave | State | Evidence / decision |
| --- | --- | --- |
| W0 | Implemented; technical baseline passed | The Apps RG-only baseline runs v1 and v2 once for every frozen development fixture, records source-span-digest examples of decomposition, semantic, targeting, critique, and revision limitations, and deterministically names `COMPOUND_AND_RELATION_DECOMPOSITION` for Wave 1. The baseline and calibration remain technical-only; neither opens the holdout nor creates a human quality result. |
| W1 | Implemented; capability acceptance pending | Apps RG-only regression verifies source-bound atomic decomposition from independently actioned prose sentences and complete safe shared-predicate chains, ambiguity preservation/escalation without partial targeting, relation escalation, and PA projection. It also verifies safe format/length/inclusion-exclusion directives from U0 user constraints and output preferences, raw arbitrary key/value omission for an unknown hard constraint, and U0 escalation for that unknown hard constraint. Protected-holdout understanding fidelity and human semantic adjudication remain unrun. |
| W2 | Implemented; capability acceptance pending | Apps RG-only regression verifies conditional C0 target options, named escalation alternatives, rejection of a re-digested decorative selection, and control-by-default treatment isolation. It verifies that a hard min/max or incompatible hard output-format conflict escalates to U0, while a conflicting output preference is withheld so the hard user constraint remains enforceable. No protected-holdout plan-coherence result exists. |
| W3 | Implemented; capability acceptance pending | Apps RG-only regression verifies deterministic critique re-derivation, unknown-hard-constraint escalation, semantic numeric-conflict detection, broad-target collision detection even when atoms share a requirement type, and rejection of a re-digested unjustified critique. The development-only QA/calibration remains separate from the holdout; no generated metric is called human qualification. |
| W4 | Implemented; technical safety regression passed | Apps RG-only regression verifies a C0-source-bound failure option replacement, revision/advisory C0-outcome-digest equality, rejection of a re-digested downstream-omission code or unsafe observation reference, no retry/route/evidence authority, and the app-owned L2 diagnostic projection/output gate. It also verifies that a source-bound unresolved hard goal constraint changes an otherwise `X3_ALLOW` Apps RG mirror into a non-authorizing local block. No new external-runtime run is used as evidence after the Apps RG-only scope lock. |
| W5 | Blocked; complete-cohort provenance gate implemented | Apps RG-only regression verifies that a mismatched input/configuration arm, a mismatched U0 JD payload, or a completed pair without run-local provenance cannot enter blinded review. Legacy v1 attempts without a pre-execution Apps RG-local input/configuration binding are rejected before any pair receipt can be issued. One-pair capture receipts now assemble only into a source-preserving cohort manifest; duplicated or substituted capture evidence is rejected. There is still no valid matched, completed control/candidate cohort for blinded output review. A blocked candidate is safety evidence, not a reviewable quality win. |
| W6 | Blocked; complete-cohort readiness verifier implemented | Apps RG-only regression verifies that metadata-only reviews are rejected; reviewer/adjudicator opaque-variant assessments must re-derive the reported P1/P2 result and candidate unsupported-claim count after sealed arm mapping; direct source-bound reviewers/adjudicators must also re-derive all five L1 capability deltas; and human-attested bindings must cover every committed opaque holdout identity exactly once. Valid negative evidence remains `BLOCKED`; an approval must bind both holdout and capability outcomes. The test-only records are validator inputs, not human evidence. No protected-holdout outcome decision, independent human review, capability assessment, or named release approval exists; no rollout or promotion is authorized. |

The decisive pre-projection W4 result is retained under
`artifacts/apps_rg/l1_cognitive_w4/20260811_pair_003/candidate_attempt_009`.
It predates the Apps RG-only scope lock and is retained for diagnosis only;
the current implementation modifies no external-runtime source, configuration, or
tests, and it invokes no new external-runtime shadow run.
It was a real non-product Apps RG run with four real provider generations plus
real selector/judge calls. C0 emitted two source-bound `C0_INSUFFICIENT`
outcomes and L1 proposed a bounded, non-retrying revision for exactly those
atoms. The competencies L2 output did not retain the required gap or
change-log tags. Therefore the Apps RG-local
`l1_cognitive_output_disposition.json` returned
`C0_OUTCOME_DISPOSITION_UNRETAINED`, set `blocks_finalization=true`, and marked
the Apps RG X3 mirror as locally blocked.

That is a successful proof of the **pre-projection revision-and-escalation
safety behavior**: the planner's observed C0 failure changed downstream
finalization rather than being an unused prompt hint. The observed provider
drop also established why tag-only prompting was inadequate. The current Apps
RG-only implementation replaces that fragile dependence with a source-bound
projection into L2 diagnostics, and the output gate now accepts only an
app-owned projection whose post-projection L2 digest still matches. It remains
non-promoting and does not alter provider or display content. In the retained
live lane, the ordinary X3 evaluation had also already returned `X3_BLOCK`;
therefore neither the earlier result nor the local regression demonstrates a
résumé-quality delta. The focused regression test proves that the local gate
changes an otherwise `X3_ALLOW` mirror to a non-authorizing Apps RG block. It
is not proof of better output quality. The same campaign retains earlier failed
attempts and an earlier direct
candidate/control comparison; neither produced a completed pair. W5 and W6
remain blocked until a valid matched holdout pair exists and independent human
review supplies the required judgment.

## Pull-request rule

Every L1 change must name:

1. the cognitive capability it changes: understand, decompose, deliberate,
   critique, or revise;
2. the failure slice and source-bound examples it addresses;
3. the expected behavior change from the parent planner;
4. the direct acceptance measure and safety guardrail; and
5. the reject/stop condition that prevents the next wave.

Reject a pull request that adds receipts, schemas, scheduler behavior, model
knobs, or tests without a causal connection to one of the five capabilities.

## Completion definition

This roadmap is complete only when the accepted L1 planner demonstrably
understands, decomposes, deliberates, critiques, and revises better than the
baseline on protected source-bound inputs, and that improvement yields safer,
more compliant downstream artifacts under bounded human-approved rollout.
