"""Candidate scoring, selection margin computation, normalization, and assignment views."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from apps_rg.runtime.c0.allocation.contracts_and_validation import (
    _Slot,
    _candidate_identity,
    _strings,
    normalize_metric_signature,
)
from apps_rg.runtime.c0.c0_fact_anchor import build_fact_anchor
from apps_rg.runtime.quality.rare_term_lexicon import RareTermLexicon


def _candidate_score(
    row: Mapping[str, Any],
) -> tuple[float, float, float, float, float, str]:
    return (
        round(float(row.get("proof_strength_raw") or 0.0), 6),
        round(float(row.get("path_confidence_raw") or 0.0), 6),
        round(float(row.get("source_independence_score") or 0.0), 6),
        round(float(row.get("target_alignment_score") or 0.0), 6),
        round(float(row.get("embedding_similarity") or 0.0), 9),
        str(row.get("candidate_id") or ""),
    )


def _candidate_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    proof, path, independence, target, embedding, candidate_id = _candidate_score(row)
    return (-proof, -path, -independence, -target, -embedding, candidate_id)


def _selection_margin_receipt(
    selected: Mapping[str, Any],
    eligible_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare a selected row with its best locally eligible rejected peer.

    The allocator's objective is lexicographic, not a probability or a blended
    score.  The margin is therefore the signed difference at the first
    objective component that distinguishes the selected row from the best
    per-slot alternative.  A negative margin is expected when a globally
    feasible assignment must yield local rank to uniqueness or concentration
    constraints.
    """
    selected_id = str(selected.get("candidate_id") or "")
    alternatives = sorted(
        (
            row
            for row in eligible_rows
            if str(row.get("candidate_id") or "") != selected_id
        ),
        key=_candidate_sort_key,
    )
    if not alternatives:
        return {
            "selection_margin": 0.0,
            "selection_margin_available": False,
            "selection_margin_basis": "no_eligible_rejected_alternative",
            "best_eligible_rejected_candidate_id": "",
        }
    alternative = alternatives[0]
    components = (
        "proof_strength_raw",
        "path_confidence_raw",
        "source_independence_score",
        "target_alignment_score",
        "embedding_similarity",
    )
    basis = "stable_candidate_id_tie"
    margin = 0.0
    for field in components:
        selected_value = round(float(selected.get(field) or 0.0), 6)
        alternative_value = round(float(alternative.get(field) or 0.0), 6)
        if selected_value != alternative_value:
            basis = field
            margin = round(selected_value - alternative_value, 6)
            break
    return {
        "selection_margin": margin,
        "selection_margin_available": True,
        "selection_margin_basis": basis,
        "best_eligible_rejected_candidate_id": str(
            alternative.get("candidate_id") or ""
        ),
    }


def _normalize_candidate(
    raw: Mapping[str, Any],
    *,
    slot: _Slot,
) -> tuple[dict[str, Any], list[str]]:
    row = dict(raw)
    row["candidate_id"] = _candidate_identity(row, slot=slot)
    row["section_id"] = str(row.get("section_id") or slot.section_id)
    row["claim_unit_id"] = str(row.get("claim_unit_id") or slot.slot_id)
    row["skill_id"] = str(row.get("skill_id") or "").strip()
    row["fact_id"] = str(row.get("fact_id") or "").strip()
    row["metric_outcome_id"] = str(row.get("metric_outcome_id") or "").strip()
    row["metric_text"] = str(row.get("metric_text") or "").strip()
    row["root_id"] = str(row.get("root_id") or "").strip()
    row["normalized_metric_signature"] = str(
        row.get("normalized_metric_signature")
        or normalize_metric_signature(row["metric_text"])
    )
    lexicon = RareTermLexicon.from_default_fact_inventory()
    raw_fps = row.get("metric_fingerprint_tokens")
    if isinstance(raw_fps, (list, tuple, set, frozenset)):
        row["metric_fingerprint_tokens"] = sorted(str(x) for x in raw_fps if str(x).strip())
    else:
        row["metric_fingerprint_tokens"] = sorted(lexicon.extract_metric_fingerprint(row["metric_text"]))
    row["employer_lane"] = str(row.get("employer_lane") or "").strip()
    row["source_family"] = str(
        row.get("source_family") or row["employer_lane"] or row["fact_id"]
    ).strip()
    row["graph_path_ids"] = _strings(row.get("graph_path_ids"))
    row["edge_ids"] = _strings(row.get("edge_ids"))
    row["citation_refs"] = _strings(row.get("citation_refs"))
    row["authority_pass"] = row.get("authority_pass") is True
    for key in (
        "proof_strength_raw",
        "target_alignment_score",
        "path_confidence_raw",
        "source_independence_score",
        "selection_margin",
    ):
        row[key] = round(float(row.get(key) or 0.0), 6)

    reasons: list[str] = []
    if not row["authority_pass"]:
        reasons.append("authority_gate_failed")
    if row["section_id"] != slot.section_id or row["claim_unit_id"] != slot.slot_id:
        reasons.append("slot_identity_mismatch")
    if not row["skill_id"]:
        reasons.append("missing_skill_id")
    if not row["fact_id"]:
        reasons.append("missing_fact_id")
    if not row["graph_path_ids"]:
        reasons.append("missing_graph_path_ids")
    if not row["edge_ids"]:
        reasons.append("missing_edge_ids")
    if not row["citation_refs"]:
        reasons.append("missing_citation_refs")
    if slot.employer_lane and row["employer_lane"] != slot.employer_lane:
        reasons.append("employer_locality_mismatch")
    if slot.allowed_employer_lanes and row["employer_lane"] not in slot.allowed_employer_lanes:
        reasons.append("employer_locality_mismatch")
    if slot.required_root_id and row["root_id"] != slot.required_root_id:
        reasons.append("slot_role_episode_bundle_mismatch")
    if slot.metric_outcome_required:
        if not row["metric_outcome_id"]:
            reasons.append("metric_outcome_required_missing_metric_outcome_id")
        if not row["metric_text"]:
            reasons.append("metric_outcome_required_missing_metric_text")
    if slot.metric_required:
        if not row["metric_outcome_id"]:
            reasons.append("metric_required_missing_metric_outcome_id")
        if not row["normalized_metric_signature"]:
            reasons.append("metric_required_missing_normalized_metric_signature")
        if not str(row.get("metric_value") or "").strip():
            reasons.append("metric_required_missing_exact_value")
        if not str(row.get("metric_unit") or "").strip():
            reasons.append("metric_required_missing_exact_unit")
    anchor = build_fact_anchor(row)
    row["fact_anchor"] = anchor
    row["raw_chunk"] = anchor["resolved_raw_chunk"]
    return row, reasons


def _assignment_view(row: Mapping[str, Any], *, slot: _Slot) -> dict[str, Any]:
    fields = (
        "candidate_id", "section_id", "claim_unit_id", "skill_id", "skill_label", "fact_id",
        "metric_outcome_id", "metric_text", "metric_value", "metric_unit",
        "normalized_metric_signature", "metric_fingerprint_tokens", "root_id", "employer_lane", "source_family",
        "proof_strength_raw", "target_alignment_score", "claim_entailment_score",
        "metric_binding_score", "path_confidence_raw", "source_independence_score",
        "selection_margin", "selection_margin_available", "selection_margin_basis",
        "best_eligible_rejected_candidate_id", "graph_path_ids", "edge_ids",
        "citation_refs", "source_refs", "root_bundle_theme", "root_claim_text",
        "root_claim_action", "root_claim_scope", "root_claim_outcome",
        "fact_anchor", "raw_chunk",
    )
    out = {key: row.get(key) for key in fields if key in row}
    out["section_id"] = slot.section_id
    out["claim_unit_id"] = slot.slot_id
    out["metric_required"] = slot.metric_required
    out["metric_outcome_required"] = slot.metric_outcome_required
    if slot.required_root_id:
        out["required_root_id"] = slot.required_root_id
    out["counts_toward_global_uniqueness"] = slot.counts_toward_global_uniqueness
    return out
