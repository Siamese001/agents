# Owner-solo provisional C0.3 QREL lane

This is a deliberately separate `OWNER_SOLO_PROVISIONAL` lane for one named
human owner. It consumes only the blinded W8 `reviewer_a` packet and writes
private review data only beneath `.runtime`.

It does not change W7/W9. In particular, it cannot create
`FROZEN_HUMAN_ADJUDICATED`, an activation manifest, release qualification, or
production authority. The existing W9 two-primary-reviewer plus independent
adjudicator requirements remain the sole authoritative release contract.

Before review, place the exception policy and execution manifest below
`.runtime`, then validate the packet:

```powershell
$pkg = '.runtime\owner-solo-qrel-attachments-20260803\owner_solo_package'
python tools\apps_rg_standalone\c03_owner_solo_qrel.py `
  --exception-policy "$pkg\owner_solo_qrel_exception.v1.json" `
  --execution-manifest "$pkg\qrel_execution_manifest.v1.json" `
  packet-validate
```

Start or resume the blinded queue with `next`. It returns only the opaque item
and candidate references, target context, résumé section, evidence-cluster
text, and counts. It does not return a query ID, split, cluster ID, rank,
retrieval score, sealed mapping, or model choice.

```powershell
python tools\apps_rg_standalone\c03_owner_solo_qrel.py `
  --exception-policy "$pkg\owner_solo_qrel_exception.v1.json" `
  --execution-manifest "$pkg\qrel_execution_manifest.v1.json" `
  next
```

Record a human judgment exactly as given by the owner. Grades are restricted to
the explicit integers `0`, `1`, `2`, or `3`; a nonempty rationale is mandatory.
Corrections append a new event rather than replacing an old return.

```powershell
python tools\apps_rg_standalone\c03_owner_solo_qrel.py `
  --exception-policy "$pkg\owner_solo_qrel_exception.v1.json" `
  --execution-manifest "$pkg\qrel_execution_manifest.v1.json" `
  record --item-ref <opaque-item-ref> --candidate-ref <opaque-candidate-ref> `
  --grade <0|1|2|3> --rationale "<human rationale>"
```

`finalize` fails closed unless the append-only ledger has exactly 456 active,
explicit, rationalized returns. A completed owner-solo artifact has status
`FROZEN_OWNER_SOLO_PROVISIONAL`; it binds the full ledger, W8 packet, sealed
mapping digest, query manifest, registry, projection, ranking identity, and
exception policy. Metrics are diagnostic only and always carry the label
`OWNER_SOLO_PROVISIONAL — NOT INDEPENDENT RELEASE EVIDENCE`.

## Faster targeted calibration review UI

For the separately scoped Brown & Brown competencies calibration work, a local
browser UI presents eight reviewer-A cards at a time with grade buttons and a
short rationale field. It records only explicit owner selections in the
ignored, append-only targeted ledger; it neither finalizes QRELs nor changes
the authoritative W9 contract.

```powershell
python tools\apps_rg_standalone\c03_targeted_qrel_review_ui.py
```

It binds the page to the sealed scope internally but displays only the
reviewer-visible card text. Use `Ctrl+C` to stop the local server.

## W0 full-resume scope

The frozen W0 scope is separate from the original 456-judgment packet. It
covers six target JDs and eleven output sections: headline, executive summary,
competencies, Unify, IBM, EY, and InsurTech. It freezes no rankings and creates
no human grades; W1 must enumerate every candidate universe and validate the
Headline and IBM C0 paths before a new blinded packet can be generated.

```powershell
python tools\apps_rg_standalone\c03_full_resume_qrel_scope.py validate
```

W1 first runs a fail-closed C0 projection preflight. It distinguishes a missing
projection candidate universe from missing runtime graph authority: Headline
and IBM may already have graph source packets but still need a derived,
multi-node embedding unit in the C0.3 projection. It will not generate a
ranking until every scoped section has an active candidate universe:

```powershell
python tools\apps_rg_standalone\c03_full_resume_qrel_w1.py
```

W1B materializes review-only, multi-node embedding units from the existing
Headline positioning and IBM role-episode runtime bundles. It writes only an
immutable private artifact under `.runtime`; the authoritative W4 registry and
source graph stay unchanged.

```powershell
python tools\apps_rg_standalone\c03_full_resume_qrel_w1b.py
```

W1C combines the frozen 38-vector W6 projection with the 16 W1B bundle units
in an ignored, owner-solo-only 54-vector projection. It copies the 38 W6
vectors byte-for-byte and newly encodes only the 16 multi-node bundle texts
using the pinned local BGE-M3 model. It does not create a ranking, a human
label, a QREL, an activation, or release authority.

```powershell
python tools\apps_rg_standalone\c03_full_resume_qrel_w1c.py
```

W2 creates one query vector per frozen target from its exact job description
and brief, then ranks every allowed cluster for all 66 target-by-section cases.
The full order and similarity scores remain sealed in ignored runtime files;
they are not shown to the reviewer. W2 creates no human label or QREL.

```powershell
python tools\apps_rg_standalone\c03_full_resume_qrel_w2.py
```

## W3 blinded full-resume review packet and UI

W3 takes the W2 full-universe rankings and creates one owner-visible packet
for the six target jobs and eleven résumé sections. The packet contains the
complete job context, a human-readable section name, and the complete
source-backed graph-evidence cluster. It keeps the query ID, calibration /
holdout split, graph cluster ID, frozen rank, similarity score, model choice,
and sealed mapping out of the reviewer-visible files.

Build (or revalidate) the immutable packet. This command creates no human
grade, QREL, metric, activation, or release authority:

```powershell
python tools\apps_rg_standalone\c03_full_resume_qrel_w3.py build
python tools\apps_rg_standalone\c03_full_resume_qrel_w3.py validate
```

Start the local checkbox-style review UI after W3 validation. It displays a
small batch of whole evidence clusters with the target context and resume
section, and saves only your explicit 0–3 grade plus your selected rationale
to an ignored append-only ledger.

```powershell
python tools\apps_rg_standalone\c03_full_resume_qrel_review_ui.py
```

The W3 packet has 66 target-by-section items and 600 finite-universe candidate
judgments. That is the packet denominator, not a claim that the existing
authoritative two-reviewer release contract has been satisfied. The completed
Brown & Brown final-competency selection remains a separate final-prose
projection decision, not a retrieval QREL.

## Final résumé output review

If the owner can judge only the finished text that will appear on a résumé,
use the separate final-output lane. It accepts a completed, source-bound
`FINAL_RESUME_OUTPUT.json` with every output gate passing; it shows the exact
rendered top-of-résumé, competencies, Unify, IBM, InsurTech, and EY sections
as they appear on the résumé, along with the target job description. One
0–3 judgment applies to the complete visible section—not a graph node,
cluster, rank, embedding score, or isolated sentence. It never exposes graph
clusters, ranks, or embedding scores.

```powershell
python tools\apps_rg_standalone\c03_final_resume_output_review_ui.py `
  --run-root <completed-full-resume-run>
```

The default is six whole-section cards per completed résumé. The retained
`--review-unit output_unit` mode is only for compatibility with prior private
tooling; it is not the owner-review default.

Those labels measure final résumé-output usefulness only. They remain distinct
from BGE-M3 QRELs and cannot produce retrieval Recall@10, nDCG@10, or MRR.
The W3 graph-evidence packet is preserved but remains unstarted for owner
review.
