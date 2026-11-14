"""Core cross-section X2 gate evaluation runner."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.runtime.aggregation._digest_utils import normalize_claim_text, sha256_utf8, tokenize
from apps_rg.runtime.aggregation.cross_section.graph_coherence import (
    build_cross_section_graph_coherence_receipt,
    check_cross_section_graph_coherence,
    check_cross_section_pillar_coherence,
)
from apps_rg.runtime.aggregation.cross_section.models import (
    EM_DASH,
    METRIC_PATTERN,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    VERDICT_WARN,
    CrossSectionGateResult,
    _allowed_fact_union,
    _extract_claim_rows,
    _jaccard,
    _priority,
    _section_plaintext,
)
from apps_rg.runtime.aggregation.cross_section.overlap_and_reports import (
    _overlap_class_fully_dispositioned,
    build_overlap_artifacts,
)
from apps_rg.runtime.assembly.final_resume_x2 import GENERATED_LANE_IDS

def run_cross_section_x2_gates(
    *,
    repo: Path,
    final_resume_blob: dict[str, Any],
    fingerprint: dict[str, Any],
    sealed_index: dict[str, Any],
) -> tuple[list[CrossSectionGateResult], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    gates: list[CrossSectionGateResult] = []
    sections = [s for s in (final_resume_blob.get("sections") or []) if isinstance(s, dict)]

    kept, removed, rewritten, decisions = build_overlap_artifacts(
        final_resume_blob=final_resume_blob,
        sealed_index=sealed_index,
        repo=repo,
    )

    exact = [d for d in decisions if d.get("overlap_class") == "exact_duplicate"]
    exact_resolved = _overlap_class_fully_dispositioned(decisions, removed, "exact_duplicate")
    if exact and exact_resolved:
        exact_verdict = VERDICT_PASS
        exact_reason = (
            f"{len(exact)} exact duplicate groups dispositioned in overlap ledger "
            "(provenance retained; L2 snapshots unchanged)"
        )
    elif exact:
        exact_verdict = VERDICT_FAIL
        exact_reason = f"{len(exact)} exact duplicate claim groups pending overlap disposition"
    else:
        exact_verdict = VERDICT_PASS
        exact_reason = None
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_exact_duplicate",
            verdict=exact_verdict,
            decisive_reason=exact_reason,
            observed=len(exact),
            threshold="advisory",
            evidence_refs=["kept_removed_claims.json", "overlap_decisions.json"] if exact else [],
        ),
    )

    near = [d for d in decisions if d.get("overlap_class") == "near_duplicate"]
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_near_duplicate",
            verdict=VERDICT_WARN if near else VERDICT_PASS,
            decisive_reason=None if not near else f"{len(near)} near-duplicate pairs",
            observed=len(near),
            threshold="jaccard>=0.85",
        ),
    )

    same_diff = [d for d in decisions if d.get("overlap_class") == "same_claim_different_wording"]
    same_resolved = _overlap_class_fully_dispositioned(decisions, removed, "same_claim_different_wording")
    if same_diff and same_resolved:
        same_verdict = VERDICT_PASS
        same_reason = (
            f"{len(same_diff)} same-fact-id wording variants dispositioned in overlap ledger "
            "(provenance retained)"
        )
    elif same_diff:
        same_verdict = VERDICT_FAIL
        same_reason = f"{len(same_diff)} same-fact-id wording variants pending overlap disposition"
    else:
        same_verdict = VERDICT_PASS
        same_reason = None
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_same_claim_different_wording",
            verdict=same_verdict,
            decisive_reason=same_reason,
            observed=len(same_diff),
            evidence_refs=["kept_removed_claims.json", "overlap_decisions.json"] if same_diff else [],
        ),
    )

    # Repeated metrics across sections — keyed by (metric, source fact), not bare
    # string. Distinct canonical facts may legitimately share a value: "40%" is
    # simultaneously InsurTech TCO reduction (bul_insurtech_001), EY audit
    # remediation, and the exec error-reduction claim, so literal counting made
    # the locked fact base unshippable (first full aggregation, 2026-06-11).
    # Recycling the SAME fact's metric into >=3 sections still fails, and metric
    # text not attributable to any claim row stays keyed as unattributed —
    # unattributed repetition across >=3 sections fails closed.
    metric_hits: dict[tuple[str, str], set[str]] = {}
    for sec in sections:
        if sec.get("section_kind") != "generated_lane":
            continue
        sid = str(sec.get("section_id"))
        snap = sec.get("l2_output_snapshot") if isinstance(sec.get("l2_output_snapshot"), dict) else {}
        claim_metric_facts: dict[str, set[str]] = {}
        for row in snap.get("claim_ledger") or []:
            if not isinstance(row, dict):
                continue
            fact_ids = {str(x) for x in (row.get("source_fact_ids") or []) if str(x).strip()}
            for m in METRIC_PATTERN.findall(str(row.get("claim_text") or "")):
                claim_metric_facts.setdefault(m.lower(), set()).update(fact_ids or {"unattributed"})
        text = _section_plaintext(sec)
        for m in METRIC_PATTERN.findall(text):
            ml = m.lower()
            for fid in sorted(claim_metric_facts.get(ml) or {"unattributed"}):
                metric_hits.setdefault((ml, fid), set()).add(sid)
    repeated = {
        f"{metric}[{fid}]": sorted(sids)
        for (metric, fid), sids in metric_hits.items()
        if len(sids) >= 3
    }
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_repeated_metric",
            verdict=VERDICT_FAIL if repeated else VERDICT_PASS,
            decisive_reason=None if not repeated else f"metrics in >=3 sections: {list(repeated.keys())[:5]}",
            observed=repeated,
            threshold=3,
        ),
    )

    unsupported = [d for d in decisions if d.get("overlap_class") == "unsupported_carryover"]
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_unsupported_carryover",
            verdict=VERDICT_FAIL if unsupported else VERDICT_PASS,
            decisive_reason=None if not unsupported else f"{len(unsupported)} claims with out-of-pool fact ids",
            observed=unsupported,
        ),
    )

    # Section intent conflict: narrative substring or high pairwise cosine similarity vs bullets
    from apps_rg.runtime.validators.bullet_quality_floor_x2 import count_participial_gerunds
    from apps_rg.runtime.validators.narrative_quality_x2 import (
        check_exec_summary_bullet_cosine_similarity, check_narrative_bullet_cosine_similarity,
        check_within_section_bullet_cosine_similarity,
    )

    conflicts: list[str] = []
    by_id = {str(s.get("section_id")): s for s in sections}
    for narr_sid, bullet_sid in (
        ("slalom_narrative", "slalom_bullets"), ("unify_narrative", "unify_bullets"),
        ("ibm_narrative", "ibm_bullets"), ("insurtech_narrative", "insurtech_bullets"), ("ey_narrative", "ey_bullets"),
    ):
        narr, bullets = by_id.get(narr_sid), by_id.get(bullet_sid)
        if not narr or not bullets:
            continue
        raw_ntext, raw_btext = _section_plaintext(narr), _section_plaintext(bullets)
        ntext, btext = normalize_claim_text(raw_ntext), normalize_claim_text(raw_btext)
        if len(ntext) < 40:
            continue
        if ntext in btext or btext in ntext:
            conflicts.append(f"{narr_sid}_vs_{bullet_sid}_substring")
        cos_res = check_narrative_bullet_cosine_similarity(
            raw_ntext, raw_btext, max_pairwise_cosine=0.28, max_pool_cosine=0.38,
            forbid_shared_opener=True, forbid_repeated_metrics=True,
        )
        if not cos_res.passed:
            conflicts.append(f"{narr_sid}_vs_{bullet_sid}_cosine({';'.join(cos_res.signals)})")

    exec_sec = by_id.get("executive_summary")
    raw_exec_text = _section_plaintext(exec_sec) if exec_sec else ""
    etext = normalize_claim_text(raw_exec_text)
    for bullet_sid in ("slalom_bullets", "unify_bullets", "ibm_bullets", "insurtech_bullets", "ey_bullets"):
        bullets = by_id.get(bullet_sid)
        if not bullets:
            continue
        raw_btext = _section_plaintext(bullets)
        b_within = check_within_section_bullet_cosine_similarity(raw_btext, max_pairwise_cosine=0.35)
        if not b_within.passed:
            conflicts.append(f"{bullet_sid}_within_cosine({';'.join(b_within.signals)})")
        for b_line in [ln.strip() for ln in raw_btext.splitlines() if ln.strip()]:
            if len(count_participial_gerunds(b_line)) > 2:
                conflicts.append(f"{bullet_sid}_gerund_rhythm_excess")
                break
        if raw_exec_text:
            e_cos = check_exec_summary_bullet_cosine_similarity(raw_exec_text, raw_btext, max_pairwise_cosine=0.35, max_internal_cosine=0.35)
            if not e_cos.passed:
                conflicts.append(f"executive_summary_vs_{bullet_sid}_cosine({';'.join(e_cos.signals)})")
            for stem in (" ".join(tokenize(etext)[:6]),):
                if len(stem) >= 20 and stem in normalize_claim_text(raw_btext):
                    conflicts.append(f"executive_summary_vs_{bullet_sid}_stem")

    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_section_intent_conflict",
            verdict=VERDICT_WARN if conflicts else VERDICT_PASS,
            decisive_reason=None if not conflicts else f"conflicts: {conflicts}",
            observed=conflicts,
        ),
    )

    # Em dash and first-person across all sections (including locked_copy_inline)
    corpus_parts = [
        _section_plaintext(s)
        for s in sections
        if s.get("section_kind") in ("generated_lane", "locked_copy_inline")
    ]
    corpus = "\n".join(p for p in corpus_parts if p)
    first_person_hit = bool(re.search(r"\b(i|my|me|mine|myself|we|our|ours)\b", corpus, re.IGNORECASE))
    em_fail = EM_DASH in corpus or first_person_hit
    em_reason = None
    if EM_DASH in corpus and first_person_hit:
        em_reason = "em dash and first-person pronoun present in assembled corpus"
    elif EM_DASH in corpus:
        em_reason = "em dash present in assembled generated corpus"
    elif first_person_hit:
        em_reason = "first-person pronoun present in assembled corpus"
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_no_em_dash",
            verdict=VERDICT_FAIL if em_fail else VERDICT_PASS,
            decisive_reason=em_reason,
        ),
    )

    # Undefined industry acronyms across all sections (INV-RESUME-NO-UNDEFINED-ACRONYMS)
    # Bare MGA/MGAs without explicit definition (e.g. "managing general agents (MGAs)") is forbidden.
    mga_hit = bool(re.search(r"\bMGAs?\b", corpus))
    mga_defined = bool(re.search(r"\bmanaging\s+general\s+agents?\b", corpus, re.IGNORECASE))
    mga_undefined = mga_hit and not mga_defined
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_no_undefined_mga_acronym",
            verdict=VERDICT_FAIL if mga_undefined else VERDICT_PASS,
            decisive_reason=(
                "undefined acronym MGA/MGAs present in assembled corpus; "
                "must be defined as 'managing general agents (MGAs)' or expanded"
                if mga_undefined
                else None
            ),
            observed={"mga_present": mga_hit, "mga_defined": mga_defined},
        ),
    )

    review_lanes = list(fingerprint.get("review_lanes") or [])
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_x3_review_present",
            verdict=VERDICT_WARN if review_lanes else VERDICT_PASS,
            decisive_reason=None if not review_lanes else f"review lanes (not product ALLOW): {review_lanes}",
            observed=review_lanes,
        ),
    )

    # Store overlap counts on gates metadata via module-level last build — caller writes files
    has_claims = any(_extract_claim_rows(sec) for sec in sections)
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_overlap_ledger_emitted",
            verdict=VERDICT_PASS if has_claims else VERDICT_UNKNOWN,
            decisive_reason=None if has_claims else "no claim rows extracted from generated sections",
            observed={"kept": len(kept), "removed": len(removed), "rewritten": len(rewritten)},
        ),
    )
    gates.append(
        check_cross_section_graph_coherence(
            repo=repo,
            final_resume_blob=final_resume_blob,
            sealed_index=sealed_index,
        ),
    )
    pillar_gate = check_cross_section_pillar_coherence(sections)
    if pillar_gate.verdict == VERDICT_UNKNOWN:
        pillar_gate = CrossSectionGateResult(
            gate_id=pillar_gate.gate_id,
            verdict=VERDICT_WARN,
            decisive_reason=pillar_gate.decisive_reason,
            threshold=pillar_gate.threshold,
            observed=pillar_gate.observed,
            evidence_refs=pillar_gate.evidence_refs,
        )
    gates.append(pillar_gate)

    whole_resume = final_resume_blob.get("whole_resume_graph_evidence_contract")
    if isinstance(whole_resume, Mapping) and whole_resume.get("active") is True:
        engineering_pass = whole_resume.get("engineering_pass") is True
        gates.append(
            CrossSectionGateResult(
                gate_id="x2_whole_resume_graph_evidence_engineering",
                verdict=VERDICT_PASS if engineering_pass else VERDICT_FAIL,
                decisive_reason=(
                    None
                    if engineering_pass
                    else "whole-resume graph evidence reconciliation is non-PASS"
                ),
                observed={
                    "engineering_pass": whole_resume.get("engineering_pass"),
                    "release_pass": whole_resume.get("release_pass"),
                    "contract_digest": whole_resume.get("contract_digest"),
                },
                evidence_refs=["whole_resume_graph_evidence_contract.json"],
            ),
        )

    return gates, kept, removed, rewritten, decisions
