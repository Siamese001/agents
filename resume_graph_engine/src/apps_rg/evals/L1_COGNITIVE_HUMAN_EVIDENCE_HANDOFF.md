# L1 Cognitive W5/W6 Human-Evidence Handoff

This Apps RG v2-only procedure records, checks, and governs human evidence after a completed paired experiment. It does not launch a provider, invoke an external runtime, create a human judgment, or activate the candidate treatment.

## Roles and separation

| Role | May receive | Must not receive or do |
| --- | --- | --- |
| Primary reviewer | Blinded review packet only | Sealed arm map, treatment identity, rollout approval |
| Adjudicator | Blinded packet and primary-review records | Sealed arm map, treatment identity, rollout approval |
| Trusted evaluation coordinator | Sealed arm map after blind reviews close | Alter reviewer records or turn a negative result positive |
| Release approver | Validated holdout outcome and bounded rollout plan | Activate or promote the treatment through this handoff |

The packet has opaque variant IDs. Do not add an `arm` field to a reviewer or adjudication record; the evaluator requires an exact blind-variant assessment shape.

## Required sequence

1. Freeze matched input and configuration before either arm runs. Each completed arm must retain `l1_cognitive_shadow_run_binding.json`.
2. Capture one completed control/candidate pair for every committed opaque holdout case, using separate capture roots. Legacy pairs without that pre-execution binding cannot be used.
3. Assemble those one-pair receipts into a combined paired receipt and a cohort manifest. The manifest re-derives the combined receipt from every source capture; it cannot be a hand-picked subset.
4. Distribute the reviewer packet while keeping the sealed mapping outside reviewer and adjudicator access.
5. Collect two distinct primary reviewer records and one distinct adjudication for every blind pair. The adjudication binds both reviewer record digests.
6. After blinded review closes, a trusted evaluation authority attests a one-to-one binding from every sealed opaque case identity to its Apps-local frozen-input digest. The authority does not disclose protected case text.
7. Supply the bounded rollback plan and named human release approval to the non-activating gate.

## Human verdict content

Each primary reviewer record has identity, qualification, independence flag, `human_attestation=true`, timestamp, blinded packet digest, blind-pair ID, exactly two `variant_assessments`, and `record_digest`. Each assessment has exactly these fields:

| Field | Requirement |
| --- | --- |
| `variant_id` | One opaque packet ID; no arm identity. |
| `finished_resume_utility_score` | Human score from 1 through 5. |
| `grounded_decision_ready` | Human boolean judgment. |
| `unsupported_material_claim_count` | Human non-negative integer count. |

The adjudication repeats an assessment for both opaque variants, is independent from both primary reviewers, binds the review-record digests, and carries `human_attestation=true`. Its assessments, not an ungrounded `IMPROVED` declaration, are the authoritative pair-level verdicts.

## Outcome derivation

After sealed arm mapping, the gate re-derives `pair_count`, candidate/control utility-score sums, candidate/control grounded-decision-ready counts, and candidate/control unsupported-claim totals. `P1` is `IMPROVED` only when the candidate utility sum is strictly greater than control; `P2` is `IMPROVED` only when the candidate ready count is strictly greater than control. A valid `NOT_IMPROVED` result is retained as human evidence and blocks rollout; do not change or discard it.

The protected-holdout outcome must bind the human-outcome digest and the exact derived measurement summary. Its unsupported-claim guardrail must equal the candidate adjudicated total. Any nonzero listed guardrail or non-improved primary outcome leaves the rollout blocked.

## Direct L1 capability assessment

Downstream output utility is not a substitute for proof that L1 itself reasons better. A separate source-bound capability outcome is required for every protected pair. The outcome must cover all three identities in `l1_v2_protected_holdout_commitment.v1.json`, exactly once each; a favorable one-case subset is invalid. Two independent reviewers and a distinct adjudicator inspect the exact frozen-input digest, control L1 v2 capsule digest, candidate cognitive-plan digest, and candidate revision-set digest. They independently score each arm from 0 through 2 on all five dimensions: `goal_constraint_fidelity`, `atomic_requirement_fidelity`, `feasibility_plan_coherence`, `critique_quality`, and `revision_quality`.

For each source pair, a separately sealed `holdout_case_bindings` record gives the opaque fixture identity, committed source-input digest, matching Apps-local frozen-input digest, human-attested evaluation-authority identity, timestamp, verification locator, and integrity digest. The evaluator checks the full one-to-one coverage before it evaluates any scores. It then re-derives the candidate/control score sums per dimension from adjudications. Each dimension must be `IMPROVED` for rollout readiness. A valid `NOT_IMPROVED` dimension is retained and blocks the rollout. The capability outcome requires its own `human-eval-authority://` external seal and cannot be substituted by a planning schema, test fixture, or final-output score.

## Cohort assembly

After each Apps RG-local `capture-pair` operation has written its one-pair receipt, create new combined artifacts without overwriting any capture:

```powershell
library API: apps_rg.evals.l1_cognitive_evaluation_cli assemble-paired-cohort `
  --source-paired-receipt <case-1-pair.json> `
  --source-paired-receipt <case-2-pair.json> `
  --source-paired-receipt <case-3-pair.json> `
  --paired-receipt-output <combined-pairs.json> `
  --cohort-manifest-output <cohort-manifest.json>
```

This command joins only already-valid Apps RG capture receipts. It does not launch a runtime, create a human judgment, or activate a treatment.

## Digest sealing and gate check

Create the substantive human record first. To add only its canonical integrity digest, write a new output file rather than overwriting the authored input:

```powershell
library API: apps_rg.evals.l1_cognitive_evaluation_cli seal-evidence `
  --input <authored-record.json> `
  --digest-field record_digest `
  --output <sealed-record.json>
```

Use `plan_digest` for a rollout plan and `approval_digest` for a release approval. `seal-evidence` does not validate the record, attest a person, generate a score, or authorize rollout.

After all authored evidence is sealed, run:

```powershell
library API: apps_rg.evals.l1_cognitive_evaluation_cli rollout-gate `
  --paired-receipt <paired.json> `
  --paired-cohort-manifest <cohort-manifest.json> `
  --blind-review-packet <packet.json> `
  --sealed-mapping <sealed-map.json> `
  --human-outcome <human-outcome.json> `
  --cognitive-capability-outcome <capability-outcome.json> `
  --protected-holdout-outcome <holdout-outcome.json> `
  --rollout-plan <rollout-plan.json> `
  --release-approval <release-approval.json> `
  --output <gate-receipt.json>
```

`READY_FOR_HUMAN_OPERATED_LIMITED_ROLLOUT` only means that evidence binds and a human-operated, ten-or-fewer-run reversible rollout may be considered. It does not start a run, select a route, alter a provider response, promote the candidate, or authorize production.
