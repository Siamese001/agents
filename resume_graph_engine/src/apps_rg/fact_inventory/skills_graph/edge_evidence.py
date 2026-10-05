"""Calibrated confidence and evidence linking for graph edges and nodes (Wave 2).

Provides:
- score_claim_bearing_edge: Noisy-OR over independent evidence, capped by source node score.
- calibrate_edge_confidence: Assigns confidence_score, confidence_tier, and confidence_method.
- extract_edge_evidence: Resolves evidence rows for claim-bearing and rule-backed edges.
- compute_node_confidence: Computes calibrated confidence for graph_nodes and splits BLOCKED into activation_status.
"""
from __future__ import annotations

import json
from typing import Any

CLAIM_BEARING_ASSERTION_TYPES = frozenset(
    {
        "EVIDENTIAL_SUPPORT",
        "METRIC_BINDING",
    }
)

RULE_BACKED_ASSERTION_TYPES = frozenset(
    {
        "POLICY_ELIGIBILITY",
        "POLICY_RESTRICTION",
        "TAXONOMIC_ATTRIBUTION",
        "STRUCTURAL_CONTAINMENT",
        "ASSOCIATIVE_BRIDGE",
        "TEMPORAL_SEQUENCE",
    }
)

CONFIDENCE_TIERS = frozenset({"HIGH", "MEDIUM", "LOW", "UNSCORED", "NOT_APPLICABLE"})

ALLOWED_EVIDENCE_KINDS: frozenset[str] = frozenset(
    {
        "fact",
        "locked_bullet",
        "repo_evidence",
        "employment",
        "certification",
        "concept",
        "metric_outcome",
        "bundle",
        "policy_rule",
        "edge_contract",
        "skill_row_field",
        "operator_confirmation",
    }
)


def _map_evidence_kind(raw_kind: str) -> str:
    k = str(raw_kind or "").strip().lower()
    if k in ALLOWED_EVIDENCE_KINDS:
        return k
    if k == "skill":
        return "skill_row_field"
    if k in ("metric", "metric_bucket"):
        return "metric_outcome"
    if k in ("policy", "policy_rule"):
        return "policy_rule"
    return "concept"


def score_claim_bearing_edge(
    *,
    evidence_rows: list[dict[str, Any]],
    source_node_score: float | None = None,
) -> tuple[float | None, str, str]:
    """Calculate calibrated confidence score and tier for a claim-bearing edge.

    Uses noisy-OR over independent evidence items:
        noisy_or = 1.0 - product(1.0 - s_i)
    capped by the source node's confidence score (if known).

    Returns:
        (confidence_score, confidence_tier, confidence_method)
    """
    independent_strengths = [
        float(r.get("evidence_strength") if r.get("evidence_strength") is not None else 1.0)
        for r in evidence_rows
        if int(r.get("is_independent") or 0) == 1
    ]
    if not independent_strengths:
        return None, "UNSCORED", "no_independent_evidence"

    product = 1.0
    for s in independent_strengths:
        clamped = max(0.0, min(1.0, s))
        product *= (1.0 - clamped)
    raw_score = 1.0 - product

    # Cap by source node score if provided
    if source_node_score is not None:
        capped_score = min(raw_score, max(0.0, min(1.0, float(source_node_score))))
    else:
        capped_score = raw_score

    score = round(capped_score, 4)
    if score >= 0.80:
        tier = "HIGH"
    elif score >= 0.55:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return score, tier, "noisy_or_independent_evidence"


def calibrate_edge_confidence(
    edge_row: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    *,
    source_node_score: float | None = None,
) -> dict[str, Any]:
    """Attach calibrated confidence_score, confidence_tier, and confidence_method to edge_row.

    Decouples confidence from validation_status by mirroring confidence_tier to
    the legacy confidence column.
    """
    assertion_type = str(edge_row.get("assertion_type") or "").strip()
    if assertion_type in CLAIM_BEARING_ASSERTION_TYPES:
        score, tier, method = score_claim_bearing_edge(
            evidence_rows=evidence_rows,
            source_node_score=source_node_score,
        )
    else:
        score = None
        tier = "NOT_APPLICABLE"
        method = "rule_governed"

    edge_row["confidence_score"] = score
    edge_row["confidence_tier"] = tier
    edge_row["confidence_method"] = method
    # Legacy confidence column mirrors confidence_tier (decoupled from validation_status)
    edge_row["confidence"] = tier
    return edge_row


def compute_node_confidence(
    node: dict[str, Any],
    *,
    skill_row: dict[str, Any] | None = None,
) -> tuple[float | None, str, str]:
    """Calculate calibrated confidence score and tier for a graph node.

    Splits BLOCKED out of legacy confidence into activation_status='BLOCKED'.
    Returns:
        (confidence_score, confidence_tier, updated_activation_status)
    """
    ntype = str(node.get("node_type") or "").strip()
    raw_conf = str(node.get("confidence") or "").strip().upper()
    act_status = str(node.get("activation_status") or "").strip()

    # Split BLOCKED from confidence into activation_status
    if raw_conf == "BLOCKED" or act_status == "BLOCKED":
        return 0.0, "LOW", "BLOCKED"

    if ntype == "skill":
        # Grade from skill_row or confidence column
        grade = raw_conf or (str(skill_row.get("confidence_grade") or "").upper() if skill_row else "")
        if grade == "HIGH":
            return 0.90, "HIGH", act_status or "ACTIVE"
        elif grade == "MEDIUM":
            return 0.75, "MEDIUM", act_status or "ACTIVE"
        elif grade == "LOW":
            return 0.50, "LOW", act_status or "ACTIVE"
        return 0.75, "MEDIUM", act_status or "ACTIVE"

    if ntype in ("fact", "locked_bullet", "repo_evidence", "certification"):
        if act_status == "ACTIVE_CONFIRMED" or str(node.get("support_level") or "") == "DIRECT_FROM_RESUME_ARCHIVE":
            return 0.95, "HIGH", act_status or "ACTIVE_CONFIRMED"
        if act_status in ("ACTIVE", "APPROVED_GRAPH_SSOT"):
            return 0.90, "HIGH", act_status
        return 0.85, "HIGH", act_status or "ACTIVE"

    if ntype in ("metric", "metric_outcome", "metric_bucket"):
        return 0.90, "HIGH", act_status or "APPROVED_GRAPH_SSOT"

    # Reference / structural nodes
    return None, "NOT_APPLICABLE", act_status or "ACTIVE"


def extract_edge_evidence(
    edge_row: dict[str, Any],
    *,
    node_types_by_id: dict[str, str] | None = None,
    connecting_facts_by_pair: dict[tuple[str, str], list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Extract and build edge_evidence rows for an edge."""
    types_map = node_types_by_id or {}
    eid = str(edge_row.get("edge_id") or "")
    et = str(edge_row.get("edge_type") or "")
    src = str(edge_row.get("source_node_id") or "")
    tgt = str(edge_row.get("target_node_id") or "")
    assertion_type = str(edge_row.get("assertion_type") or "")
    rule_id = str(edge_row.get("derivation_rule_id") or "")

    evidence_rows: list[dict[str, Any]] = []
    seen_refs: set[str] = set()

    def _add_evidence(
        *,
        evidence_ref: str,
        evidence_node_id: str,
        evidence_kind: str,
        is_independent: int,
        evidence_strength: float = 1.0,
        human_confirmed: int = 0,
        source_doc: str = "",
        span: str = "",
        quote_sha256: str = "",
    ) -> None:
        ref_s = str(evidence_ref).strip()
        if not ref_s or ref_s in seen_refs:
            return
        # Ensure evidence_node_id resolves to graph_nodes or is empty
        if evidence_node_id and evidence_node_id not in types_map:
            evidence_node_id = ""
        seen_refs.add(ref_s)
        evidence_rows.append(
            {
                "edge_id": eid,
                "evidence_ref": ref_s,
                "evidence_node_id": evidence_node_id,
                "evidence_kind": _map_evidence_kind(evidence_kind),
                "is_independent": is_independent,
                "source_doc": source_doc,
                "span": span,
                "quote_sha256": quote_sha256,
                "human_confirmed": human_confirmed,
                "evidence_strength": round(max(0.0, min(1.0, evidence_strength)), 4),
            }
        )

    # 1. Claim-bearing edges: must link to resolvable evidence node(s) in graph_nodes
    if assertion_type == "EVIDENTIAL_SUPPORT":
        # Target node is the supporting evidence
        target_kind = types_map.get(tgt, "fact")
        is_human = 1 if str(edge_row.get("validation_status") or "") == "validated" else 0
        strength = 0.95 if is_human else 0.85
        _add_evidence(
            evidence_ref=f"node:{tgt}",
            evidence_node_id=tgt,
            evidence_kind=target_kind,
            is_independent=1,
            evidence_strength=strength,
            human_confirmed=is_human,
        )

    elif assertion_type == "METRIC_BINDING":
        if et == "skill_surfaces_metric_outcome":
            # Connecting facts from proof chain serve as independent evidence
            cfacts = connecting_facts_by_pair.get((src, tgt), []) if connecting_facts_by_pair else []
            if cfacts:
                for fid in cfacts:
                    _add_evidence(
                        evidence_ref=f"fact:{fid}",
                        evidence_node_id=fid,
                        evidence_kind="fact",
                        is_independent=1,
                        evidence_strength=0.90,
                    )
            # Also add target metric node
            _add_evidence(
                evidence_ref=f"metric:{tgt}",
                evidence_node_id=tgt,
                evidence_kind="metric_outcome" if types_map.get(tgt) == "metric_outcome" else "metric",
                is_independent=1,
                evidence_strength=0.85,
            )
        elif et == "fact_has_metric_outcome":
            # Source fact node is independent evidence
            _add_evidence(
                evidence_ref=f"fact:{src}",
                evidence_node_id=src,
                evidence_kind="fact",
                is_independent=1,
                evidence_strength=0.90,
            )
        elif et == "skill_can_surface_metric":
            # Target metric node
            _add_evidence(
                evidence_ref=f"metric:{tgt}",
                evidence_node_id=tgt,
                evidence_kind="metric_outcome" if types_map.get(tgt) == "metric_outcome" else "fact",
                is_independent=1,
                evidence_strength=0.85,
            )
        elif et in ("metric_outcome_anchors_bundle", "metric_outcome_bound_to_employer"):
            # Metric node or employer node in graph_nodes
            node_id = src if src in types_map else tgt
            kind = types_map.get(node_id, "metric_outcome")
            _add_evidence(
                evidence_ref=f"node:{node_id}",
                evidence_node_id=node_id,
                evidence_kind=kind,
                is_independent=1,
                evidence_strength=0.90,
            )

    # 2. Rule-backed / non-claim-bearing edges: must cite policy_rule or edge_contract
    elif assertion_type in ("POLICY_ELIGIBILITY", "POLICY_RESTRICTION"):
        ref_rule = rule_id or f"rule_{et}"
        _add_evidence(
            evidence_ref=f"policy_rule:{ref_rule}",
            evidence_node_id="",
            evidence_kind="policy_rule",
            is_independent=0,
            evidence_strength=1.0,
        )
    else:
        # Taxonomic, Structural, Associative, Temporal
        _add_evidence(
            evidence_ref=f"contract:edge_types/{et}",
            evidence_node_id="",
            evidence_kind="edge_contract",
            is_independent=0,
            evidence_strength=1.0,
        )

    # 3. Ingest any explicit assertion_basis_refs from ledger/contract
    raw_refs = edge_row.get("assertion_basis_refs")
    if not raw_refs and edge_row.get("assertion_basis_refs_json"):
        try:
            raw_refs = json.loads(edge_row["assertion_basis_refs_json"])
        except Exception:
            raw_refs = []

    if isinstance(raw_refs, list):
        for ref_str in raw_refs:
            r = str(ref_str).strip()
            if not r or r in seen_refs:
                continue
            # Parse ref structure
            if r.startswith("ledger:graph_nodes/") or r.startswith("baseline:graph_nodes/"):
                nid = r.split("/")[-1]
                if nid in types_map:
                    _add_evidence(
                        evidence_ref=r,
                        evidence_node_id=nid,
                        evidence_kind=types_map.get(nid, "fact"),
                        is_independent=1,
                        evidence_strength=0.85,
                    )
                else:
                    _add_evidence(
                        evidence_ref=r,
                        evidence_node_id="",
                        evidence_kind="fact",
                        is_independent=0,
                        evidence_strength=1.0,
                    )
            elif any(r.startswith(p) for p in ("fact:", "metric:", "node:", "employment:", "skill:")):
                prefix, nid = r.split(":", 1)
                if nid in types_map:
                    _add_evidence(
                        evidence_ref=r,
                        evidence_node_id=nid,
                        evidence_kind=types_map.get(nid, prefix),
                        is_independent=1,
                        evidence_strength=0.90,
                    )
            elif r.startswith("contract:edge_types/"):
                _add_evidence(
                    evidence_ref=r,
                    evidence_node_id="",
                    evidence_kind="edge_contract",
                    is_independent=0,
                    evidence_strength=1.0,
                )
            elif r.startswith("policy:") or "policy" in r:
                _add_evidence(
                    evidence_ref=r,
                    evidence_node_id="",
                    evidence_kind="policy_rule",
                    is_independent=0,
                    evidence_strength=1.0,
                )
            elif r.startswith("reb_") or "bundle" in r:
                _add_evidence(
                    evidence_ref=r,
                    evidence_node_id="",
                    evidence_kind="bundle",
                    is_independent=0,
                    evidence_strength=1.0,
                )

    return evidence_rows
