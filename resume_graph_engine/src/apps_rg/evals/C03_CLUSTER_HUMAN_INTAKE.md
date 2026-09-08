# C0.3 cluster human intake (W9)

W9 validates human-owned review evidence for the cluster-level embedding
projection created in W6 and packetized in W8. It does not create grades,
reviewer authority, adjudications, semantic-qualification results, an activation
manifest, or production approval.

Official finalization must run on controlled POSIX storage where Python can
verify owner-only files and directories. Native Windows may run readiness and
contract tests, but it fails closed for `--finalize`.

## Controlled input layout

Keep all inputs under ignored `.runtime/c03-cluster-w9/` or an equivalent
controller-owned POSIX location:

```text
authority/
  human_review_authority.v1.json
returns/
  reviewer_a/
    reviewer_return_manifest.v1.json
    reviews.jsonl
  reviewer_b/
    reviewer_return_manifest.v1.json
    reviews.jsonl
  adjudication/
    adjudication_manifest.v1.json
    adjudications.jsonl
```

The evaluation owner creates and externally pins the authority file. It must
bind the exact W8 receipt, packet manifest, packet-manifest file, and both cohort
manifests. Its roster contains exactly three distinct `human-reviewer://`
identities: one primary assigned to each reviewer distribution and one separate
adjudicator. Each participant needs a `cluster-relevance://` qualification.
Automation must never author this receipt.

Each primary return contains all 48 `item_ref` records and all 456
`candidate_ref` grades from its own W8 distribution. Every candidate has a
final integer `relevance_grade` from 0 through 3 and a nonempty human rationale.
The return manifest binds the reviewer identity, qualification, W8 packet,
source review-item file, completed return file, timestamp, and exact counts.

Adjudication uses the opaque references from `reviewer_a`, covers all 48 items
and 456 candidates, binds both primary-return manifests, and records the two
primary grades, one final grade from 0 through 3, and a nonempty rationale. The
adjudicator identity must be the separately rostered human.

## Why one reviewer is not enough

A relevance grade is a human judgment, not an objective property emitted by
BGE-M3. A single reviewer can produce a valuable **provisional** review, but
that review only proves what that one person believed about the candidate set.
It cannot establish that the ranking is generally relevant or that a parameter
choice is not simply optimized to that person's preferences.

Two blinded primary reviews make disagreement visible. This is important
because reasonable reviewers can differ about target fit, evidence sufficiency,
section fit, and whether a metric is exact. Without a second independent
return, there is no way to distinguish a retrieval weakness from one reviewer's
interpretation, no agreement signal to audit, and no defensible final label.

The separate adjudicator does not average guesses or create a model label. The
adjudicator reviews the two human grades and rationales, records the reason for
the final 0--3 grade, and creates one accountable answer key. That frozen QREL
answer key is what Recall@10, nDCG@10, and MRR are compared against.

Therefore a sole reviewer may label the full blinded packet for rubric testing
or a development-only experiment, but the result must be marked
`OWNER_SOLO_PROVISIONAL` and `NON_RELEASE_AUTHORIZING`. It may be frozen only
in a separate owner-solo artifact with status
`FROZEN_OWNER_SOLO_PROVISIONAL`; it must never be represented as the
authoritative `FROZEN_HUMAN_ADJUDICATED` QREL set. It must not tune against the
protected holdout, qualify BGE-M3 retrieval for release, set release
thresholds, or activate production. Those actions require two independent
complete reviews, separate adjudication, and the externally pinned
human-authority receipt.

### Current operating limitation: one available human grader

This evaluation currently has one available human grader. Any completed return
from that person is retained as a useful, attributable **Reviewer A**
development artifact only. It is not represented as a second review,
adjudication, frozen QREL, or independent confirmation.

Consequently, until an independent second reviewer and separate adjudicator are
available, the authoritative W9 state remains `BLOCKED_HUMAN_REVIEW_INPUTS`.
The separate owner-solo lane may report diagnostic Recall@10, nDCG@10, or MRR
only with its `OWNER_SOLO_PROVISIONAL — NOT INDEPENDENT RELEASE EVIDENCE`
label. It must not claim calibrated BGE-M3 release qualification or authorize
activation from those labels.

## Commands

Verify the non-authorizing readiness receipt and W8 packet:

```powershell
python tools/apps_rg_standalone/c03_graph_evidence_cluster_human_intake_wave9.py --check
```

After controlled human work is complete, transfer the owner-pinned authority
file SHA-256 through a separate trusted channel and finalize on the supported
POSIX authority host:

```bash
python tools/apps_rg_standalone/c03_graph_evidence_cluster_human_intake_wave9.py \
  --finalize \
  --expected-human-authority-file-sha256 "$TRUSTED_AUTHORITY_FILE_SHA256"
```

Successful finalization creates controlled W7-compatible QRELs and a W9
finalization receipt. It still does not qualify or activate embeddings; W7 must
be rerun against those QRELs and any later activation remains a separate,
explicitly authorized wave.
