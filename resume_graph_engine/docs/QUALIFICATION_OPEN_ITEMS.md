# Judge and BGE-M3 qualification open items

Status date: 2026-08-07
Overall status: **IMPLEMENTED, NOT FULLY QUALIFIED, NOT PRODUCTION-AUTHORIZED**

This document records two independent human-evidence gates:

1. LLM proof-judge qualification after the Gemini 3.6 Flash migration.
2. BGE-M3 retrieval qualification after completion and adjudication of QREL labels.

Passing runtime tests or successfully calling a provider does not close either
gate. Judge labels and retrieval QRELs are different evidence and must never be
substituted for one another.

## Open-item register

| Item | Implemented state | Evidence still required | Closure condition |
|---|---|---|---|
| Gemini proof-judge migration | All active Gemini proof roles use `gemini-3.6-flash` with high thinking, structured output, no temperature, and receipt capture. A live smoke call passed. | Restore the missing frozen `001344` judge packet or freeze an equivalent packet set; obtain authorized human labels and adjudications. | Replay the frozen packets with 100% schema validity, no false-pass regression, correct abstention behavior, and human agreement/Spearman at or above the governed threshold. Seal a qualification receipt. |
| BGE-M3 retrieval qualification | C0 can invoke the governed BGE-M3 ranking surface and rehydrate returned graph IDs through claim authority. | Finish all human QREL grades and rationales, resolve conflicts, adjudicate, and freeze the digest-bound QREL set. | Run post-runtime retrieval evaluation against the frozen QRELs, satisfy the governed retrieval thresholds, and issue a separate promotion authorization. |

Human labels must not be inferred, generated, copied from model scores, or
prefilled. Until these items close, the corresponding qualification and
production-promotion claims remain open.

## Where LLM judges operate

### `apps_research` targeting-brief handoff

The `apps_research` X2 semantic gate uses one Gemini 3.6 Flash judge at high
thinking. It grades the completed targeting brief for evidence faithfulness,
role relevance, sufficient coverage, and evaluator-instruction attacks before
the brief can enter the canonical handoff and satisfy the `apps_rg` U0
prerequisite.

This judge does not retrieve evidence, generate résumé claims, or replace the
deterministic handoff gates.

### `apps_rg` section proof

For generated résumé sections, the sequence is:

1. C0 retrieves and rehydrates evidence under graph authority.
2. PA/L2 generates the candidate section.
3. Deterministic X2 validators check shape, grounding, and section contracts.
4. X1D proof judge or judges grade the same candidate, allowed evidence,
   rubric, deterministic-gate summary, and proof boundary.
5. X3 consumes deterministic and X1D results to determine the section
   disposition.

X1D is grade-only. A proof judge cannot add evidence, rewrite the candidate, or
repair a failed deterministic gate.

### Final aggregate résumé and post-Exit calibration

The final aggregate résumé receives the enhanced dual proof panel. After Exit,
L6 may compare judge results with authorized human labels for Spearman and
other calibration observability. That post-Exit measurement is informational
until its human authority and promotion requirements are satisfied; it does
not retroactively create evidence or authorize BGE-M3 weights.

## Current proof-judge roster

| Surface | Judge count | Required proof judge or judges |
|---|---:|---|
| `apps_research` targeting-brief X2 | 1 | Gemini 3.6 Flash, high |
| Executive summary | 2 | Gemini 3.6 Flash, high; GPT-5.6 Sol, high |
| Headline | 2 | Gemini 3.6 Flash, high; GPT-5.6 Sol, high |
| Competencies | 2 | Gemini 3.6 Flash, high; GPT-5.6 Sol, high |
| Final aggregate résumé | 2 | Gemini 3.6 Flash, high; GPT-5.6 Sol, high |
| Unify, IBM, Insurtech, and EY bullets | 1 per section | Gemini 3.6 Flash, high |
| Unify, IBM, Insurtech, and EY narratives | 1 per section | Gemini 3.6 Flash, high |

Claude Sonnet 5 candidate-pool selection is advisory selection, not X1D proof
judging. It cannot satisfy a required Gemini or OpenAI proof slot.

## One judge versus two judges

### One-judge section

One judge is still a real proof gate. The single configured judge must return a
model-backed, schema-valid result and satisfy the section threshold. If it is
missing, blocked, malformed, or fails, no second provider silently substitutes
for it. Deterministic X2 gates remain independently required.

A one-judge section can be qualified for systematic leniency, strictness,
false passes, false failures, and abstention bias by replaying a balanced frozen
packet set against authorized human labels. It cannot produce a same-run
cross-provider disagreement signal because only one provider is configured.

### Two-judge section

Both judges receive the same canonical packet and contract hash. The panel is
not a majority vote and not a permanent challenger lane: every configured
proof judge must produce the required model-backed pass for proof eligibility.
A disagreement therefore prevents an unqualified allow and routes through the
governed review or fail-closed disposition.

Two judges expose provider disagreement, but disagreement alone does not show
which judge is biased. The authorized human label is the truth anchor used to
identify whether either judge is systematically miscalibrated.

## What the frozen judge packets must cover

The qualification set must contain immutable candidate output, allowed
evidence, rubric, thresholds, deterministic-gate summaries, proof boundaries,
and authorized expected outcomes. It should deliberately cover:

- Clearly supported passes.
- Unsupported or fabricated claims that must fail.
- Borderline evidence and threshold cases.
- Insufficient-evidence cases that should abstain or return unknown.
- Employer, role, date, metric, credential, and scope binding errors.
- Adversarial instructions and attempts to manipulate the evaluator.
- Every single-judge and dual-judge section class.

Required reporting includes schema-valid response rate, false-pass and
false-fail rates, abstention behavior, per-judge human agreement, cross-judge
disagreement for dual panels, and adjudicated failure examples. Historical
baseline receipts may be used for comparison; the retired model does not need
to remain as a live challenger.

## BGE-M3 QREL boundary

BGE-M3 QRELs grade retrieval relevance for query-candidate pairs. They do not
grade résumé prose and they do not qualify an LLM judge.

- **C0 runtime retrieval:** BGE-M3/BM25 ranking returns candidate graph IDs;
  graph authority and allowlists govern whether rehydrated evidence can be
  used.
- **Post-runtime QREL scoring:** frozen human QRELs support Recall@K and other
  retrieval metrics. Metrics are not valid while labels or adjudication remain
  incomplete.
- **Post-Exit shadow observability:** judge-versus-human agreement measures LLM
  judge behavior. It is not BGE-M3 weight calibration.

Model-generated QRELs, technical packet validation, and reviewer-readiness
receipts cannot replace completed human grades or authorize production.

## Closeout checklist

### Judge qualification

- [x] Pin Gemini 3.6 Flash for all active Gemini proof roles.
- [x] Send and receipt high thinking; omit temperature.
- [x] Prove model-backed live transport and structured output.
- [ ] Restore or replace and freeze the missing judge packet set.
- [ ] Complete authorized human labels and adjudication.
- [ ] Replay every applicable single- and dual-judge role.
- [ ] Verify schema validity, false-pass, false-fail, abstention, and agreement requirements.
- [ ] Seal the qualification receipt and obtain production authorization.

### BGE-M3 retrieval qualification

- [x] Keep graph IDs as the sole claim authority during runtime retrieval.
- [ ] Finish all QREL grades and rationales.
- [ ] Resolve conflicts and complete adjudication.
- [ ] Freeze the QREL artifact and digest.
- [ ] Run retrieval metrics against the frozen set.
- [ ] Satisfy the governed promotion thresholds.
- [ ] Obtain separate production-promotion authorization.
