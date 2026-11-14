"""Overlap ledger construction and cross-section warn/status reports."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.runtime.aggregation._digest_utils import normalize_claim_text, sha256_utf8, tokenize
from apps_rg.runtime.aggregation.cross_section.models import (
    VERDICT_FAIL,
    VERDICT_UNKNOWN,
    CrossSectionGateResult,
    _allowed_fact_union,
    _extract_claim_rows,
    _jaccard,
    _priority,
    _section_plaintext,
)
from apps_rg.runtime.assembly.final_resume_x2 import GENERATED_LANE_IDS

def _overlap_class_fully_dispositioned(
    decisions: list[dict[str, Any]],
    removed: list[dict[str, Any]],
    overlap_class: str,
) -> bool:
    """True when every overlap decision of this class has a removed ledger row with provenance retained."""
    class_decisions = [d for d in decisions if d.get("overlap_class") == overlap_class]
    if not class_decisions:
        return True
    class_removed = [
        r
        for r in removed
        if r.get("overlap_class") == overlap_class
        and r.get("disposition") == "removed"
        and r.get("provenance_retained") is True
    ]
    return len(class_removed) >= len(class_decisions)


def build_overlap_artifacts(
    *,
    final_resume_blob: dict[str, Any],
    sealed_index: dict[str, Any],
    repo: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return kept_claims, removed_claims, rewritten_claims, overlap_decisions."""
    sections = [s for s in (final_resume_blob.get("sections") or []) if isinstance(s, dict)]
    all_claims: list[dict[str, Any]] = []
    for sec in sections:
        if sec.get("section_kind") == "generated_lane":
            all_claims.extend(_extract_claim_rows(sec))

    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    rewritten: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []

    # Index by normalized text and by source_fact_ids frozenset
    by_norm: dict[str, list[dict[str, Any]]] = {}
    by_sf: dict[str, list[dict[str, Any]]] = {}
    for c in all_claims:
        by_norm.setdefault(c["normalized_text"], []).append(c)
        sf_key = ",".join(sorted(c["source_fact_ids"]))
        by_sf.setdefault(sf_key, []).append(c)

    def _winner(group: list[dict[str, Any]]) -> dict[str, Any]:
        return min(group, key=lambda x: _priority(str(x["section_id"])))

    seen_kept_keys: set[str] = set()

    for norm, group in by_norm.items():
        if len(group) <= 1 or not norm or len({str(c.get("section_id") or "") for c in group}) <= 1:
            continue
        w = _winner(group)
        for c in group:
            if c["claim_key"] == w["claim_key"] or c["section_id"] == w["section_id"]:
                if c["claim_key"] not in seen_kept_keys:
                    kept.append({**c, "disposition": "kept", "overlap_class": "exact_duplicate"})
                    seen_kept_keys.add(c["claim_key"])
            else:
                removed.append({**c, "disposition": "removed", "overlap_class": "exact_duplicate", "kept_in_section": w["section_id"], "kept_claim_key": w["claim_key"], "provenance_retained": True, "note": "L2 snapshot unchanged; aggregate overlap audit only"})
                decisions.append({"overlap_class": "exact_duplicate", "removed_section": c["section_id"], "kept_section": w["section_id"], "claim_text_preview": norm[:120]})

    for sf_key, group in by_sf.items():
        if not sf_key or len(group) <= 1 or len({str(c.get("section_id") or "") for c in group}) <= 1 or len({c["normalized_text"] for c in group}) <= 1:
            continue
        w = _winner(group)
        for c in group:
            if c["normalized_text"] == w["normalized_text"] or c["section_id"] == w["section_id"] or c["claim_key"] in seen_kept_keys or any(r.get("claim_key") == c["claim_key"] for r in removed):
                continue
            removed.append({**c, "disposition": "removed", "overlap_class": "same_claim_different_wording", "kept_in_section": w["section_id"], "kept_claim_key": w["claim_key"], "provenance_retained": True})
            decisions.append({"overlap_class": "same_claim_different_wording", "source_fact_ids": c["source_fact_ids"], "removed_section": c["section_id"], "kept_section": w["section_id"]})

    # Near duplicate across sections (token Jaccard)
    gen_claims = [c for c in all_claims if c["section_id"] in GENERATED_LANE_IDS]
    for i, a in enumerate(gen_claims):
        ta = set(tokenize(a["claim_text"]))
        for b in gen_claims[i + 1 :]:
            if a["section_id"] == b["section_id"]:
                continue
            tb = set(tokenize(b["claim_text"]))
            jac = _jaccard(ta, tb)
            if jac >= 0.85 and a["normalized_text"] != b["normalized_text"]:
                w = _winner([a, b])
                loser = b if w["claim_key"] == a["claim_key"] else a
                if loser["claim_key"] not in seen_kept_keys and not any(
                    r.get("claim_key") == loser["claim_key"] for r in removed
                ):
                    removed.append(
                        {
                            **loser,
                            "disposition": "removed",
                            "overlap_class": "near_duplicate",
                            "similarity": round(jac, 3),
                            "kept_in_section": w["section_id"],
                            "provenance_retained": True,
                        },
                    )
                    decisions.append(
                        {
                            "overlap_class": "near_duplicate",
                            "similarity": round(jac, 3),
                            "sections": [a["section_id"], b["section_id"]],
                        },
                    )

    # Claims not in any removal — kept
    removed_keys = {r["claim_key"] for r in removed}
    for c in all_claims:
        if c["claim_key"] not in removed_keys and c["claim_key"] not in seen_kept_keys:
            kept.append({**c, "disposition": "kept", "overlap_class": None})
            seen_kept_keys.add(c["claim_key"])

    # Unsupported carryover vs pool allowlist
    allowed_union = _allowed_fact_union(sealed_index, repo)
    if allowed_union:
        for c in all_claims:
            bad = [fid for fid in c["source_fact_ids"] if fid and fid not in allowed_union]
            if bad:
                decisions.append(
                    {
                        "overlap_class": "unsupported_carryover",
                        "section_id": c["section_id"],
                        "unsupported_source_fact_ids": bad,
                    },
                )

    return kept, removed, rewritten, decisions


def all_claims_empty(sections: list[dict[str, Any]]) -> bool:
    for sec in sections:
        if _extract_claim_rows(sec):
            return False
    return True


def cross_section_gates_all_pass(gates: list[CrossSectionGateResult]) -> bool:
    for g in gates:
        if g.verdict in (VERDICT_FAIL, VERDICT_UNKNOWN):
            return False
    return True


def cross_section_fail_gate_ids(gates: list[CrossSectionGateResult]) -> list[str]:
    return [g.gate_id for g in gates if g.verdict in (VERDICT_FAIL, VERDICT_UNKNOWN)]


def build_cross_section_warn_resolution_report(
    *,
    cross_gates: list[CrossSectionGateResult],
    kept_claims: list[dict[str, Any]],
    removed_claims: list[dict[str, Any]],
    rewritten_claims: list[dict[str, Any]],
    overlap_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """W18 artifact: overlap WARN resolution matrix (deterministic ledger, provenance retained)."""
    from datetime import datetime, timezone

    matrix: list[dict[str, Any]] = []
    for gate_id in (
        "x2_cross_section_exact_duplicate",
        "x2_cross_section_same_claim_different_wording",
    ):
        g = next((x for x in cross_gates if x.gate_id == gate_id), None)
        overlap_class = gate_id.replace("x2_cross_section_", "")
        if overlap_class == "exact_duplicate":
            oc = "exact_duplicate"
        else:
            oc = "same_claim_different_wording"
        decisions_n = sum(1 for d in overlap_decisions if d.get("overlap_class") == oc)
        removed_n = sum(
            1
            for r in removed_claims
            if r.get("overlap_class") == oc and r.get("disposition") == "removed"
        )
        matrix.append(
            {
                "gate_id": gate_id,
                "verdict": g.verdict if g else VERDICT_UNKNOWN,
                "overlap_class": oc,
                "decisions_count": decisions_n,
                "removed_with_provenance_count": removed_n,
                "fully_dispositioned": _overlap_class_fully_dispositioned(
                    overlap_decisions,
                    removed_claims,
                    oc,
                ),
                "decisive_reason": g.decisive_reason if g else None,
                "evidence_refs": [
                    "artifacts/apps_rg/runtime_proofs/final_resume_assembly/kept_removed_claims.json",
                    "artifacts/apps_rg/runtime_proofs/final_resume_assembly/overlap_decisions.json",
                ],
            },
        )
    return {
        "schema": "apps_rg.cross_section_warn_resolution.v1",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "resolution_method": "deterministic_overlap_ledger",
        "provenance_retained": True,
        "l2_snapshots_unchanged": True,
        "product_warn_waiver_used": False,
        "warn_resolution_matrix": matrix,
        "summary": {
            "kept": len(kept_claims),
            "removed": len(removed_claims),
            "rewritten": len(rewritten_claims),
            "overlap_decisions": len(overlap_decisions),
        },
    }
