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
    jd_text: str | None = None,
    ats_min_coverage: float = 0.70,
    pct_certificate: Mapping[str, Any] | None = None,
    pct_allowed_fact_ids: set[str] | None = None,
    pct_source_facts: dict[str, str] | None = None,
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
            verdict=VERDICT_FAIL if near else VERDICT_PASS,
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

    # Section intent conflict and unified Overlap Engine across all assembled sections
    from apps_rg.runtime.quality.overlap_engine import (
        ResumeUnit,
        _SENT_SPLIT_RE,
        _clean_bullet_strings,
        evaluate_resume_overlap,
    )
    from apps_rg.runtime.validators.bullet_quality_floor_x2 import count_participial_gerunds

    conflicts: list[str] = []
    by_id = {str(s.get("section_id")): s for s in sections}
    cross_units: list[ResumeUnit] = []

    hl_sec = by_id.get("headline")
    if hl_sec:
        for idx, seg in enumerate([p.strip() for p in _section_plaintext(hl_sec).split("|") if p.strip()], start=1):
            cross_units.append(ResumeUnit(unit_id=f"headline:seg_{idx}", section_id="headline", text=seg, unit_kind="headline_segment"))

    exec_sec = by_id.get("executive_summary")
    raw_exec_text = _section_plaintext(exec_sec) if exec_sec else ""
    etext = normalize_claim_text(raw_exec_text)
    if raw_exec_text:
        for idx, sent in enumerate([s.strip() for s in _SENT_SPLIT_RE.split(raw_exec_text.strip()) if s.strip()], start=1):
            cross_units.append(ResumeUnit(unit_id=f"executive_summary:S{idx}", section_id="executive_summary", text=sent, unit_kind="summary_sentence"))

    for narr_sid, bullet_sid in (
        ("slalom_narrative", "slalom_bullets"), ("unify_narrative", "unify_bullets"),
        ("ibm_narrative", "ibm_bullets"), ("insurtech_narrative", "insurtech_bullets"), ("ey_narrative", "ey_bullets"),
    ):
        emp = narr_sid.split("_", 1)[0]
        narr, bullets = by_id.get(narr_sid), by_id.get(bullet_sid)
        if narr:
            raw_ntext = _section_plaintext(narr).strip()
            if raw_ntext:
                cross_units.append(ResumeUnit(unit_id=f"{narr_sid}:N1", section_id=narr_sid, text=raw_ntext, employer=emp, unit_kind="narrative"))
        if bullets:
            raw_btext = _section_plaintext(bullets)
            for idx, b_line in enumerate(_clean_bullet_strings(raw_btext), start=1):
                cross_units.append(ResumeUnit(unit_id=f"{bullet_sid}:B{idx}", section_id=bullet_sid, text=b_line, employer=emp, unit_kind="bullet"))
            for b_line in [ln.strip() for ln in raw_btext.splitlines() if ln.strip()]:
                if len(count_participial_gerunds(b_line)) > 2:
                    conflicts.append(f"{bullet_sid}_gerund_rhythm_excess")
                    break
            if raw_exec_text:
                for stem in (" ".join(tokenize(etext)[:6]),):
                    if len(stem) >= 20 and stem in normalize_claim_text(raw_btext):
                        conflicts.append(f"executive_summary_vs_{bullet_sid}_stem")
        if narr and bullets:
            raw_ntext, raw_btext = _section_plaintext(narr), _section_plaintext(bullets)
            ntext, btext = normalize_claim_text(raw_ntext), normalize_claim_text(raw_btext)
            if len(ntext) >= 40 and (ntext in btext or btext in ntext):
                conflicts.append(f"{narr_sid}_vs_{bullet_sid}_substring")

    cross_ov = evaluate_resume_overlap(cross_units)
    for f in cross_ov.findings:
        conflicts.append(f"{f.finding_type}({f.left_unit_id}<->{f.right_unit_id}={f.observed_value})")

    ov_verdict = VERDICT_PASS if cross_ov.verdict == "PASS" else (VERDICT_UNKNOWN if cross_ov.verdict == "UNKNOWN" else VERDICT_FAIL)
    gates.append(
        CrossSectionGateResult(
            gate_id="x2_overlap_engine",
            verdict=ov_verdict,
            decisive_reason=None if cross_ov.passed else cross_ov.diagnostic_summary(),
            observed=cross_ov.to_dict(),
            threshold="max_signature_repeats=1; max_number_repeats=1; pairwise_idf_cosine<=0.35",
        ),
    )

    gates.append(
        CrossSectionGateResult(
            gate_id="x2_cross_section_section_intent_conflict",
            verdict=VERDICT_FAIL if conflicts else VERDICT_PASS,
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

    effective_jd = jd_text if jd_text is not None else final_resume_blob.get("ats_jd_text")
    if isinstance(effective_jd, str) and effective_jd.strip():
        from apps_rg.runtime.validators.ats_validator import evaluate_ats_jd_requirement_coverage

        ats_res = evaluate_ats_jd_requirement_coverage(
            final_resume_blob,
            effective_jd,
            min_coverage=ats_min_coverage,
        )
        gates.append(
            CrossSectionGateResult(
                gate_id="x2_cross_section_ats_jd_coverage",
                verdict=VERDICT_PASS if ats_res.passed else VERDICT_FAIL,
                decisive_reason=(
                    None
                    if ats_res.passed
                    else (
                        f"ATS JD requirement coverage {ats_res.coverage_ratio:.2%} "
                        f"< {ats_res.min_coverage:.2%}; missing={list(ats_res.missing_terms)}"
                    )
                ),
                observed=ats_res.to_dict(),
                threshold=ats_min_coverage,
            ),
        )

    effective_pct = pct_certificate if pct_certificate is not None else final_resume_blob.get("pct_certificate")
    if isinstance(effective_pct, Mapping):
        from apps_rg.runtime.assembly.full_resume_text import flatten_final_resume_to_text
        from apps_rg.runtime.validators.proof_carrying_text_verifier import verify_pct_certificate

        rendered_text = flatten_final_resume_to_text(final_resume_blob)
        allowed_ids = (
            set(pct_allowed_fact_ids)
            if pct_allowed_fact_ids is not None
            else _allowed_fact_union(sealed_index, repo=repo)
        )
        pct_ok = verify_pct_certificate(
            rendered_text,
            dict(effective_pct),
            allowed_fact_ids=allowed_ids,
            source_facts=pct_source_facts,
        )
        gates.append(
            CrossSectionGateResult(
                gate_id="x2_cross_section_pct_certificate",
                verdict=VERDICT_PASS if pct_ok else VERDICT_FAIL,
                decisive_reason=None if pct_ok else "Proof-Carrying Text certificate verification failed",
                observed={
                    "verified": pct_ok,
                    "text_hash": str(effective_pct.get("text_hash") or ""),
                    "span_count": len(effective_pct.get("spans") or []),
                },
            ),
        )

    return gates, kept, removed, rewritten, decisions
