"""Deterministic W3 authority reconciliation for the canonical C0.3 graph."""

from __future__ import annotations

import copy
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_graph_edge_semantic_hardening import (
    BASIS_KIND_BY_EDGE_TYPE,
    EDGE_SEMANTIC_CONTRACT_VERSION,
    W2_RECEIPT_SCHEMA_VERSION,
    _basis_refs,
    _canonical_assertion_text,
    _integrity_gap_reason,
    _lifecycle_disposition,
    collect_graph_edge_semantic_issues,
    validate_w2_receipt,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

AUTHORITY_RECONCILIATION_CONTRACT_VERSION = (
    "apps_rg.c03_graph_authority_reconciliation_contract.v1"
)
AUTHORITY_RECONCILIATION_WAVE = "C03_CLUSTER_EMBEDDING_W3"
W3_RECEIPT_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_w3_receipt.v1"
W3_COMPLETION_MARKER = "C03_CLUSTER_EMBEDDING_W3_AUTHORITY_RECONCILED"

AUTHORITY_RECONCILIATION_CONTRACT_PATH = Path(
    "src/apps_rg/fact_inventory/"
    "c03_graph_authority_reconciliation_contract.v1.json"
)
GRAPH_PATH = Path("src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json")
W2_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave2_edge_assertion_hardening_receipt.json"
)

_ACTIVE_STATES = frozenset({"ACTIVE", "ACTIVE_CONFIRMED"})
_LIFECYCLE_PERMISSIVENESS = {
    "RETIRED": 0,
    "DRAFT": 1,
    "ACTIVE": 2,
    "ACTIVE_CONFIRMED": 3,
}
_SUPPORT_PERMISSIVENESS = {
    "INTERNAL_ONLY": 0,
    "POLICY": 0,
    "USER_CONFIRMED_PENDING_SOURCE": 0,
    "DERIVED_SUPPORTED": 1,
    "DIRECT_FROM_RESUME_ARCHIVE": 2,
    "USER_CONFIRMED": 2,
}
_RISK_SEVERITY = {"low": 0, "medium": 1, "high": 2}
_POLICY_EDGE_TYPES = frozenset(
    {
        "skill_external_claim_eligible",
        "skill_projection_only_internal",
        "skill_requires_human_confirmation",
        "projection_excludes_blocked_skill",
    }
)


class GraphAuthorityReconciliationWave3Error(ValueError):
    """Raised when W3 cannot reconcile authority without expanding it."""


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _path_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _section_name(endpoint: str) -> str:
    for prefix in ("section:", "section_"):
        if endpoint.startswith(prefix):
            return endpoint.removeprefix(prefix)
    return endpoint


def _add_issue(issues: list[str], code: str, offenders: Iterable[Any]) -> None:
    values = sorted({str(value) for value in offenders if str(value).strip()})
    if values:
        issues.append(f"{code}: count={len(values)} offenders={values[:12]}")


def validate_authority_reconciliation_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != AUTHORITY_RECONCILIATION_CONTRACT_VERSION:
        raise GraphAuthorityReconciliationWave3Error(
            "W3 authority reconciliation contract schema is invalid"
        )
    if contract.get("wave_id") != AUTHORITY_RECONCILIATION_WAVE:
        raise GraphAuthorityReconciliationWave3Error(
            "W3 authority reconciliation contract wave is invalid"
        )
    if contract.get("status") != "FROZEN":
        raise GraphAuthorityReconciliationWave3Error(
            "W3 authority reconciliation contract is not frozen"
        )
    forbidden = set(_strings(contract.get("forbidden_mutations")))
    required_forbidden = {
        "change a skill retrieval_eligible value",
        "add a fact identifier or evidence reference",
        "expand an allowed_sections field",
        "delete or rewrite a legacy embedding artifact",
        "generate replacement vectors",
        "authorize production promotion",
    }
    if not required_forbidden <= forbidden:
        raise GraphAuthorityReconciliationWave3Error(
            "W3 forbidden mutation boundary is incomplete"
        )
    acceptance = contract.get("acceptance")
    if not isinstance(acceptance, Mapping):
        raise GraphAuthorityReconciliationWave3Error(
            "W3 acceptance contract is missing"
        )
    for field in (
        "w2_integrity_gap_count",
        "section_authority_drift_count",
        "retrieval_policy_partition_drift_count",
        "human_confirmation_policy_drift_count",
        "draft_projection_block_drift_count",
        "non_traversable_graph_hop_row_count",
        "active_orphan_node_count",
        "unregistered_node_row_difference_count",
    ):
        if acceptance.get(field) != 0:
            raise GraphAuthorityReconciliationWave3Error(
                f"W3 acceptance must fail closed at zero: {field}"
            )
    for field in (
        "legacy_embedding_artifacts_changed",
        "replacement_vectors_generated",
        "production_promotion_authorized",
    ):
        if acceptance.get(field) is not False:
            raise GraphAuthorityReconciliationWave3Error(
                f"W3 acceptance mutation boundary is invalid: {field}"
            )


def _conservative_value(
    left: str,
    right: str,
    *,
    ordering: Mapping[str, int],
    field: str,
) -> str:
    if left == right:
        return left
    if left not in ordering or right not in ordering:
        raise GraphAuthorityReconciliationWave3Error(
            f"cannot conservatively reconcile {field}: {left!r} versus {right!r}"
        )
    return min((left, right), key=lambda value: ordering[value])


def _reconcile_duplicate_safety_fields(
    *,
    nodes: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    node_by_id = {str(node.get("node_id") or ""): node for node in nodes}
    for row in rows:
        skill_id = str(row.get("skill_id") or "")
        node = node_by_id.get(skill_id)
        if node is None:
            raise GraphAuthorityReconciliationWave3Error(
                f"skill row has no graph node during W3: {skill_id}"
            )
        for field, ordering in (
            ("activation_status", _LIFECYCLE_PERMISSIVENESS),
            ("support_level", _SUPPORT_PERMISSIVENESS),
        ):
            row_value = str(row.get(field) or "")
            node_value = str(node.get(field) or "")
            selected = _conservative_value(
                row_value,
                node_value,
                ordering=ordering,
                field=field,
            )
            row[field] = selected
            node[field] = selected
        if row.get("evidence_risk") == node.get("evidence_risk"):
            continue
        row_risk = str(row.get("evidence_risk") or "").lower()
        node_risk = str(node.get("evidence_risk") or "").lower()
        if row_risk not in _RISK_SEVERITY or node_risk not in _RISK_SEVERITY:
            raise GraphAuthorityReconciliationWave3Error(
                f"cannot reconcile evidence risk for {skill_id}"
            )
        selected_risk = max(
            (row_risk, node_risk), key=lambda value: _RISK_SEVERITY[value]
        )
        row["evidence_risk"] = selected_risk
        node["evidence_risk"] = selected_risk


def _retirement_reason(
    edge: Mapping[str, Any],
    *,
    rows: Mapping[str, Mapping[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
) -> str:
    w2_reason = str(edge.get("integrity_gap_reason") or "")
    if edge.get("edge_semantic_status") == "HELD_INTEGRITY_GAP":
        return f"W2_INTEGRITY_GAP:{w2_reason}"
    edge_type = str(edge.get("edge_type") or "")
    source = str(edge.get("source_node_id") or "")
    target = str(edge.get("target_node_id") or "")
    if edge_type == "skill_allowed_in_section":
        allowed = set(_strings((rows.get(source) or {}).get("allowed_sections")))
        if _section_name(target) not in allowed:
            return "SECTION_EDGE_NOT_IN_SKILL_ROW_ALLOWLIST"
    if edge_type == "section_can_select_skill":
        allowed = set(_strings((rows.get(target) or {}).get("allowed_sections")))
        if _section_name(source) not in allowed:
            return "SECTION_EDGE_NOT_IN_SKILL_ROW_ALLOWLIST"
    if edge_type == "capability_domain_contains_skill":
        row = rows.get(target) or {}
        source_node = nodes.get(source) or {}
        field = "pillar" if source_node.get("node_type") == "domain_pillar" else "domain_id"
        if str(row.get(field) or "") != source:
            return f"TAXONOMY_MEMBERSHIP_CONFLICT:{field}"
    row = rows.get(source) or {}
    eligible = row.get("retrieval_eligible") is True
    if edge_type == "skill_external_claim_eligible" and not eligible:
        return "EXTERNAL_ELIGIBLE_EDGE_CONFLICTS_WITH_INELIGIBLE_ROW"
    if edge_type == "skill_projection_only_internal" and eligible:
        return "INTERNAL_ONLY_EDGE_CONFLICTS_WITH_ELIGIBLE_ROW"
    if edge_type == "skill_requires_human_confirmation" and (
        row.get("human_confirmation_required") is not True
    ):
        return "HUMAN_CONFIRMATION_EDGE_CONFLICTS_WITH_ROW"
    if edge_type == "projection_excludes_blocked_skill" and (
        str(row.get("activation_status") or "") != "DRAFT"
    ):
        return "DRAFT_BLOCK_EDGE_CONFLICTS_WITH_ROW"
    return ""


def _base_edge(
    *,
    edge_type: str,
    skill_id: str,
    target: str,
    rationale: str,
    external_claim_policy: str = "skill_projection_not_proof",
) -> dict[str, Any]:
    return {
        "edge_id": f"edge:w3:{edge_type}:{skill_id}->{target}",
        "edge_type": edge_type,
        "source_node_id": skill_id,
        "target_node_id": target,
        "rationale": rationale,
        "projection_behavior": "graph_traversal",
        "external_claim_policy": external_claim_policy,
        "validation_status": "validated",
        "hardening_wave": AUTHORITY_RECONCILIATION_WAVE,
    }


def _materialize_row_derived_edges(
    *,
    edges: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    triples = {
        (
            str(edge.get("edge_type") or ""),
            str(edge.get("source_node_id") or ""),
            str(edge.get("target_node_id") or ""),
        )
        for edge in edges
    }
    additions: list[dict[str, Any]] = []

    def add_if_missing(edge: dict[str, Any]) -> None:
        triple = (
            str(edge["edge_type"]),
            str(edge["source_node_id"]),
            str(edge["target_node_id"]),
        )
        if triple not in triples:
            additions.append(edge)
            triples.add(triple)

    for row in sorted(rows, key=lambda value: str(value.get("skill_id") or "")):
        skill_id = str(row.get("skill_id") or "")
        for section in _strings(row.get("allowed_sections")):
            add_if_missing(
                _base_edge(
                    edge_type="skill_allowed_in_section",
                    skill_id=skill_id,
                    target=f"section_{section}",
                    rationale=f"Allowed in {section}",
                )
            )
        if row.get("retrieval_eligible") is True:
            add_if_missing(
                _base_edge(
                    edge_type="skill_external_claim_eligible",
                    skill_id=skill_id,
                    target="policy_external_claim_policy",
                    rationale="Conditionally eligible when fact active",
                )
            )
        else:
            add_if_missing(
                _base_edge(
                    edge_type="skill_projection_only_internal",
                    skill_id=skill_id,
                    target="policy_external_claim_policy",
                    rationale="Internal ranking only",
                )
            )
        if row.get("human_confirmation_required") is True:
            add_if_missing(
                _base_edge(
                    edge_type="skill_requires_human_confirmation",
                    skill_id=skill_id,
                    target="policy_external_claim_policy",
                    rationale="Requires human confirmation",
                )
            )
        if str(row.get("activation_status") or "") == "DRAFT":
            add_if_missing(
                _base_edge(
                    edge_type="projection_excludes_blocked_skill",
                    skill_id=skill_id,
                    target="policy_external_claim_policy",
                    rationale=(
                        "Block external: "
                        f"{row.get('external_claim_policy') or 'non_active'}"
                    ),
                    external_claim_policy=str(
                        row.get("external_claim_policy")
                        or "skill_projection_not_proof"
                    ),
                )
            )
    return additions


def _rewrite_broken_hop_paths(
    *,
    rows: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    pairs = {
        (str(edge.get("source_node_id") or ""), str(edge.get("target_node_id") or ""))
        for edge in edges
    }
    epochs_by_skill: dict[str, set[str]] = defaultdict(set)
    tracks_by_epoch: dict[str, set[str]] = defaultdict(set)
    facts_by_skill: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        edge_type = str(edge.get("edge_type") or "")
        source = str(edge.get("source_node_id") or "")
        target = str(edge.get("target_node_id") or "")
        if edge_type == "epoch_contains_skill":
            epochs_by_skill[target].add(source)
        elif edge_type == "career_track_contains_epoch":
            tracks_by_epoch[target].add(source)
        elif edge_type == "skill_supported_by_fact":
            facts_by_skill[source].add(target)
    for row in rows:
        skill_id = str(row.get("skill_id") or "")
        current = _path_values(row.get("graph_hop_path"))
        if current and all(pair in pairs for pair in zip(current, current[1:])):
            continue
        epoch_candidates = sorted(epochs_by_skill.get(skill_id) or set())
        if not epoch_candidates:
            raise GraphAuthorityReconciliationWave3Error(
                f"no registered epoch path for skill row: {skill_id}"
            )
        preferred_epoch = str(row.get("career_epoch") or "")
        epoch = (
            preferred_epoch
            if preferred_epoch in epoch_candidates
            else epoch_candidates[0]
        )
        track_candidates = sorted(tracks_by_epoch.get(epoch) or set())
        path = [epoch, skill_id]
        if track_candidates:
            preferred_track = str(row.get("career_track_id") or "").lower()
            track = next(
                (
                    value
                    for value in track_candidates
                    if value.lower() == preferred_track
                ),
                track_candidates[0],
            )
            path.insert(0, track)
        linked_facts = sorted(
            set(_strings(row.get("fact_id_links")))
            & facts_by_skill.get(skill_id, set())
        )
        preferred_fact = str(row.get("source_ledger_ref") or "")
        if preferred_fact in linked_facts:
            path.append(preferred_fact)
        elif linked_facts:
            path.append(linked_facts[0])
        if not all(pair in pairs for pair in zip(path, path[1:])):
            raise GraphAuthorityReconciliationWave3Error(
                f"reconciled path is not traversable for {skill_id}: {path}"
            )
        row["graph_hop_path"] = path


def _retire_active_orphans(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    incident: Counter[str] = Counter()
    for edge in edges:
        incident[str(edge.get("source_node_id") or "")] += 1
        incident[str(edge.get("target_node_id") or "")] += 1
    for node in nodes:
        node_id = str(node.get("node_id") or "")
        if not incident[node_id] and str(node.get("activation_status") or "") in (
            _ACTIVE_STATES
        ):
            node["activation_status"] = "RETIRED"


def _refresh_edge_semantics(
    *,
    edges: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    node_by_id = {str(node.get("node_id") or ""): node for node in nodes}
    row_by_id = {str(row.get("skill_id") or ""): row for row in rows}
    for edge in edges:
        edge_type = str(edge.get("edge_type") or "")
        if edge_type not in BASIS_KIND_BY_EDGE_TYPE:
            raise GraphAuthorityReconciliationWave3Error(
                f"unregistered W3 edge type: {edge_type}"
            )
        edge["edge_semantic_contract_version"] = EDGE_SEMANTIC_CONTRACT_VERSION
        edge["canonical_assertion_text"] = _canonical_assertion_text(
            edge, nodes=node_by_id
        )
        edge["assertion_basis"] = BASIS_KIND_BY_EDGE_TYPE[edge_type]
        edge["assertion_basis_refs"] = _basis_refs(
            edge, nodes=node_by_id, rows=row_by_id
        )
        gap = _integrity_gap_reason(edge, nodes=node_by_id, rows=row_by_id)
        if gap:
            raise GraphAuthorityReconciliationWave3Error(
                f"W3 retained an authority-conflicting edge: {edge.get('edge_id')}={gap}"
            )
        edge["edge_semantic_status"] = "HARDENED"
        edge.pop("integrity_gap_reason", None)
        edge["lifecycle_disposition"] = _lifecycle_disposition(
            edge, nodes=node_by_id, rows=row_by_id
        )


def _edge_summary(edge: Mapping[str, Any], reason: str | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "edge_id": str(edge.get("edge_id") or ""),
        "edge_type": str(edge.get("edge_type") or ""),
        "source_node_id": str(edge.get("source_node_id") or ""),
        "target_node_id": str(edge.get("target_node_id") or ""),
        "canonical_sha256": canonical_sha256(edge),
    }
    if reason:
        summary["retirement_reason"] = reason
    return summary


def reconcile_graph_authority_wave3(graph_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the idempotent W3 authority-closed graph."""

    output = copy.deepcopy(dict(graph_payload))
    metadata = output.get("graph_metadata")
    if not isinstance(metadata, dict):
        raise GraphAuthorityReconciliationWave3Error(
            "graph_metadata must be an object"
        )
    existing = metadata.get("authority_reconciliation")
    if isinstance(existing, Mapping) and existing.get("wave_id") == (
        AUTHORITY_RECONCILIATION_WAVE
    ):
        issues = collect_graph_authority_reconciliation_issues(output)
        if issues:
            raise GraphAuthorityReconciliationWave3Error(
                f"existing W3 marker is invalid: {issues[:8]}"
            )
        return output
    source_w2_issues = collect_graph_edge_semantic_issues(output)
    if source_w2_issues:
        raise GraphAuthorityReconciliationWave3Error(
            f"W3 source graph is not valid W2 output: {source_w2_issues[:8]}"
        )
    raw_nodes = output.get("graph_nodes")
    raw_edges = output.get("graph_edges")
    raw_rows = output.get("skill_rows")
    if not all(isinstance(value, list) for value in (raw_nodes, raw_edges, raw_rows)):
        raise GraphAuthorityReconciliationWave3Error(
            "graph nodes, edges, and skill rows must be lists"
        )
    nodes = [dict(node) for node in raw_nodes if isinstance(node, dict)]
    edges = [dict(edge) for edge in raw_edges if isinstance(edge, dict)]
    rows = [dict(row) for row in raw_rows if isinstance(row, dict)]
    if (len(nodes), len(edges), len(rows)) != (
        len(raw_nodes),
        len(raw_edges),
        len(raw_rows),
    ):
        raise GraphAuthorityReconciliationWave3Error(
            "graph contains non-object nodes, edges, or rows"
        )
    source_nodes = copy.deepcopy(nodes)
    source_edges = copy.deepcopy(edges)
    source_rows = copy.deepcopy(rows)
    source_w1_marker = copy.deepcopy(metadata.get("node_semantic_hardening") or {})
    source_w2_marker = copy.deepcopy(metadata.get("edge_semantic_hardening") or {})

    _reconcile_duplicate_safety_fields(nodes=nodes, rows=rows)
    row_by_id = {str(row.get("skill_id") or ""): row for row in rows}
    node_by_id = {str(node.get("node_id") or ""): node for node in nodes}
    retirement_records: list[dict[str, Any]] = []
    retained_edges: list[dict[str, Any]] = []
    for edge in edges:
        reason = _retirement_reason(edge, rows=row_by_id, nodes=node_by_id)
        if reason:
            retirement_records.append(_edge_summary(edge, reason))
        else:
            retained_edges.append(edge)
    additions = _materialize_row_derived_edges(edges=retained_edges, rows=rows)
    edges = retained_edges + additions
    _rewrite_broken_hop_paths(rows=rows, edges=edges)
    _retire_active_orphans(nodes=nodes, edges=edges)
    _refresh_edge_semantics(edges=edges, nodes=nodes, rows=rows)

    output["graph_nodes"] = nodes
    output["graph_edges"] = edges
    output["skill_rows"] = rows
    metadata["node_count"] = len(nodes)
    metadata["edge_count"] = len(edges)
    added_records = sorted(
        (_edge_summary(edge) for edge in additions), key=lambda item: item["edge_id"]
    )
    changed_hop_rows = [
        str(after.get("skill_id") or "")
        for before, after in zip(source_rows, rows, strict=True)
        if before.get("graph_hop_path") != after.get("graph_hop_path")
    ]
    retired_orphans = [
        str(after.get("node_id") or "")
        for before, after in zip(source_nodes, nodes, strict=True)
        if before.get("activation_status") in _ACTIVE_STATES
        and after.get("activation_status") == "RETIRED"
    ]
    safety_node_changes = [
        str(after.get("node_id") or "")
        for before, after in zip(source_nodes, nodes, strict=True)
        if any(
            before.get(field) != after.get(field)
            for field in ("activation_status", "support_level", "evidence_risk")
        )
        and str(after.get("node_id") or "") not in retired_orphans
    ]
    safety_row_changes = [
        str(after.get("skill_id") or "")
        for before, after in zip(source_rows, rows, strict=True)
        if any(
            before.get(field) != after.get(field)
            for field in ("activation_status", "support_level", "evidence_risk")
        )
    ]
    metadata["authority_reconciliation"] = {
        "contract_version": AUTHORITY_RECONCILIATION_CONTRACT_VERSION,
        "wave_id": AUTHORITY_RECONCILIATION_WAVE,
        "source_edge_count": len(source_edges),
        "source_graph_edges_sha256": canonical_sha256(source_edges),
        "source_graph_nodes_sha256": canonical_sha256(source_nodes),
        "source_skill_rows_sha256": canonical_sha256(source_rows),
        "source_w1_marker_sha256": canonical_sha256(source_w1_marker),
        "source_w2_marker_sha256": canonical_sha256(source_w2_marker),
        "current_edge_count": len(edges),
        "current_graph_edges_sha256": canonical_sha256(edges),
        "current_graph_nodes_sha256": canonical_sha256(nodes),
        "current_skill_rows_sha256": canonical_sha256(rows),
        "retired_edge_count": len(retirement_records),
        "retired_edge_reason_counts": dict(
            sorted(Counter(record["retirement_reason"] for record in retirement_records).items())
        ),
        "retired_edge_inventory_sha256": canonical_sha256(retirement_records),
        "added_edge_count": len(added_records),
        "added_edge_type_counts": dict(
            sorted(Counter(record["edge_type"] for record in added_records).items())
        ),
        "added_edge_inventory_sha256": canonical_sha256(added_records),
        "changed_hop_row_count": len(changed_hop_rows),
        "changed_hop_row_ids_sha256": canonical_sha256(sorted(changed_hop_rows)),
        "retired_orphan_node_count": len(retired_orphans),
        "retired_orphan_node_ids_sha256": canonical_sha256(sorted(retired_orphans)),
        "safety_node_change_count": len(safety_node_changes),
        "safety_node_ids_sha256": canonical_sha256(sorted(safety_node_changes)),
        "safety_row_change_count": len(safety_row_changes),
        "safety_row_ids_sha256": canonical_sha256(sorted(safety_row_changes)),
        "semantic_status_counts": dict(
            sorted(Counter(str(edge.get("edge_semantic_status") or "") for edge in edges).items())
        ),
        "lifecycle_disposition_counts": dict(
            sorted(Counter(str(edge.get("lifecycle_disposition") or "") for edge in edges).items())
        ),
        "production_promotion_authorized": False,
    }
    issues = collect_graph_authority_reconciliation_issues(output)
    if issues:
        raise GraphAuthorityReconciliationWave3Error(
            f"W3 authority reconciliation failed: {issues[:12]}"
        )
    return output


def _intentional_node_row_difference_issues(
    *,
    nodes: Mapping[str, Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    offenders: list[str] = []
    exact_fields = (
        "activation_status",
        "support_level",
        "visibility_rule",
        "evidence_risk",
        "retrieval_eligible",
    )
    for skill_id, row in rows.items():
        node = nodes.get(skill_id)
        if not node:
            offenders.append(f"{skill_id}.node_missing")
            continue
        for field in exact_fields:
            left = str(node.get(field) or "").lower() if field == "evidence_risk" else node.get(field)
            right = str(row.get(field) or "").lower() if field == "evidence_risk" else row.get(field)
            if left != right:
                offenders.append(f"{skill_id}.{field}")
        if node.get("node_type") != row.get("node_type"):
            if not (
                node.get("node_type") == "skill"
                and row.get("node_type") in {None, "skill_row"}
            ):
                offenders.append(f"{skill_id}.node_type")
        eligible = row.get("retrieval_eligible") is True
        for field, safe_value in (
            ("projection_behavior", "non_retrieval_identity"),
            ("external_claim_policy", "skill_projection_not_proof"),
        ):
            if node.get(field) == row.get(field):
                continue
            if row.get(field) is None and str(node.get(field) or ""):
                continue
            if not eligible and node.get(field) == safe_value:
                continue
            offenders.append(f"{skill_id}.{field}")
    return offenders


def collect_graph_authority_reconciliation_issues(
    graph_payload: Mapping[str, Any],
) -> list[str]:
    """Return deterministic W3 authority, integrity, and topology issues."""

    issues: list[str] = []
    nodes_list = [
        node for node in graph_payload.get("graph_nodes") or [] if isinstance(node, dict)
    ]
    edges = [
        edge for edge in graph_payload.get("graph_edges") or [] if isinstance(edge, dict)
    ]
    rows_list = [
        row for row in graph_payload.get("skill_rows") or [] if isinstance(row, dict)
    ]
    nodes = {str(node.get("node_id") or ""): node for node in nodes_list}
    rows = {str(row.get("skill_id") or ""): row for row in rows_list}
    metadata = graph_payload.get("graph_metadata") or {}
    marker = metadata.get("authority_reconciliation") if isinstance(metadata, Mapping) else None
    if not isinstance(marker, Mapping):
        return ["GRAPH_AUTHORITY_RECONCILIATION_MARKER_MISSING"]

    semantic_gaps = [
        str(edge.get("edge_id") or "")
        for edge in edges
        if edge.get("edge_semantic_status") != "HARDENED"
        or str(edge.get("integrity_gap_reason") or "")
    ]
    _add_issue(issues, "GRAPH_AUTHORITY_EDGE_NOT_HARDENED", semantic_gaps)

    section_actual: dict[str, set[str]] = defaultdict(set)
    inverse_section_conflicts: list[str] = []
    for edge in edges:
        edge_type = str(edge.get("edge_type") or "")
        source = str(edge.get("source_node_id") or "")
        target = str(edge.get("target_node_id") or "")
        if edge_type == "skill_allowed_in_section":
            section_actual[source].add(_section_name(target))
        elif edge_type == "section_can_select_skill":
            if _section_name(source) not in set(
                _strings((rows.get(target) or {}).get("allowed_sections"))
            ):
                inverse_section_conflicts.append(str(edge.get("edge_id") or ""))
    section_drift = [
        skill_id
        for skill_id, row in rows.items()
        if section_actual.get(skill_id, set())
        != set(_strings(row.get("allowed_sections")))
    ]
    _add_issue(issues, "GRAPH_AUTHORITY_SECTION_DRIFT", section_drift)
    _add_issue(
        issues,
        "GRAPH_AUTHORITY_INVERSE_SECTION_CONFLICT",
        inverse_section_conflicts,
    )

    by_type_source: Counter[tuple[str, str]] = Counter(
        (str(edge.get("edge_type") or ""), str(edge.get("source_node_id") or ""))
        for edge in edges
    )
    retrieval_policy_drift: list[str] = []
    human_policy_drift: list[str] = []
    draft_policy_drift: list[str] = []
    for skill_id, row in rows.items():
        eligible = row.get("retrieval_eligible") is True
        external_count = by_type_source[("skill_external_claim_eligible", skill_id)]
        internal_count = by_type_source[("skill_projection_only_internal", skill_id)]
        if (external_count, internal_count) != ((1, 0) if eligible else (0, 1)):
            retrieval_policy_drift.append(skill_id)
        human_count = by_type_source[("skill_requires_human_confirmation", skill_id)]
        if human_count != (1 if row.get("human_confirmation_required") is True else 0):
            human_policy_drift.append(skill_id)
        blocked_count = by_type_source[("projection_excludes_blocked_skill", skill_id)]
        if blocked_count != (1 if row.get("activation_status") == "DRAFT" else 0):
            draft_policy_drift.append(skill_id)
    _add_issue(
        issues, "GRAPH_AUTHORITY_RETRIEVAL_POLICY_DRIFT", retrieval_policy_drift
    )
    _add_issue(issues, "GRAPH_AUTHORITY_HUMAN_POLICY_DRIFT", human_policy_drift)
    _add_issue(issues, "GRAPH_AUTHORITY_DRAFT_POLICY_DRIFT", draft_policy_drift)

    pairs = {
        (str(edge.get("source_node_id") or ""), str(edge.get("target_node_id") or ""))
        for edge in edges
    }
    broken_paths = [
        skill_id
        for skill_id, row in rows.items()
        if not _path_values(row.get("graph_hop_path"))
        or any(
            pair not in pairs
            for pair in zip(
                _path_values(row.get("graph_hop_path")),
                _path_values(row.get("graph_hop_path"))[1:],
            )
        )
    ]
    _add_issue(issues, "GRAPH_AUTHORITY_HOP_PATH_NOT_TRAVERSABLE", broken_paths)

    incident: Counter[str] = Counter()
    for edge in edges:
        incident[str(edge.get("source_node_id") or "")] += 1
        incident[str(edge.get("target_node_id") or "")] += 1
    active_orphans = [
        node_id
        for node_id, node in nodes.items()
        if not incident[node_id]
        and str(node.get("activation_status") or "") in _ACTIVE_STATES
    ]
    _add_issue(issues, "GRAPH_AUTHORITY_ACTIVE_ORPHAN_NODE", active_orphans)
    _add_issue(
        issues,
        "GRAPH_AUTHORITY_NODE_ROW_DIFFERENCE_UNREGISTERED",
        _intentional_node_row_difference_issues(nodes=nodes, rows=rows),
    )

    marker_mismatches: list[str] = []
    w1_marker = metadata.get("node_semantic_hardening") or {}
    w2_marker = metadata.get("edge_semantic_hardening") or {}
    expected_marker_values = {
        "contract_version": AUTHORITY_RECONCILIATION_CONTRACT_VERSION,
        "wave_id": AUTHORITY_RECONCILIATION_WAVE,
        "source_edge_count": w2_marker.get("edge_count"),
        "source_graph_edges_sha256": w2_marker.get("hardened_graph_edges_sha256"),
        "source_graph_nodes_sha256": w2_marker.get("graph_nodes_sha256_after"),
        "source_skill_rows_sha256": w2_marker.get("skill_rows_sha256_after"),
        "source_w1_marker_sha256": canonical_sha256(w1_marker),
        "source_w2_marker_sha256": canonical_sha256(w2_marker),
        "current_edge_count": len(edges),
        "current_graph_edges_sha256": canonical_sha256(edges),
        "current_graph_nodes_sha256": canonical_sha256(nodes_list),
        "current_skill_rows_sha256": canonical_sha256(rows_list),
    }
    for field, expected in expected_marker_values.items():
        if marker.get(field) != expected:
            marker_mismatches.append(field)
    w3_edges = [
        edge
        for edge in edges
        if edge.get("hardening_wave") == AUTHORITY_RECONCILIATION_WAVE
    ]
    w3_records = sorted(
        (_edge_summary(edge) for edge in w3_edges), key=lambda item: item["edge_id"]
    )
    if marker.get("added_edge_count") != len(w3_edges):
        marker_mismatches.append("added_edge_count")
    if marker.get("added_edge_inventory_sha256") != canonical_sha256(w3_records):
        marker_mismatches.append("added_edge_inventory_sha256")
    expected_added_types = dict(
        sorted(Counter(str(edge.get("edge_type") or "") for edge in w3_edges).items())
    )
    if marker.get("added_edge_type_counts") != expected_added_types:
        marker_mismatches.append("added_edge_type_counts")
    statuses = dict(
        sorted(Counter(str(edge.get("edge_semantic_status") or "") for edge in edges).items())
    )
    if marker.get("semantic_status_counts") != statuses:
        marker_mismatches.append("semantic_status_counts")
    lifecycles = dict(
        sorted(Counter(str(edge.get("lifecycle_disposition") or "") for edge in edges).items())
    )
    if marker.get("lifecycle_disposition_counts") != lifecycles:
        marker_mismatches.append("lifecycle_disposition_counts")
    if marker.get("production_promotion_authorized") is not False:
        marker_mismatches.append("production_promotion_authorized")
    _add_issue(issues, "GRAPH_AUTHORITY_RECONCILIATION_MARKER_MISMATCH", marker_mismatches)
    return issues


def authority_reconciliation_profile(graph_payload: Mapping[str, Any]) -> dict[str, Any]:
    edges = [
        edge for edge in graph_payload.get("graph_edges") or [] if isinstance(edge, dict)
    ]
    nodes = [
        node for node in graph_payload.get("graph_nodes") or [] if isinstance(node, dict)
    ]
    rows = [
        row for row in graph_payload.get("skill_rows") or [] if isinstance(row, dict)
    ]
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "skill_row_count": len(rows),
        "retrieval_eligible_skill_count": sum(
            1 for row in rows if row.get("retrieval_eligible") is True
        ),
        "retired_node_count": sum(
            1 for node in nodes if node.get("activation_status") == "RETIRED"
        ),
        "edge_type_counts": dict(
            sorted(Counter(str(edge.get("edge_type") or "") for edge in edges).items())
        ),
        "semantic_status_counts": dict(
            sorted(Counter(str(edge.get("edge_semantic_status") or "") for edge in edges).items())
        ),
        "lifecycle_disposition_counts": dict(
            sorted(Counter(str(edge.get("lifecycle_disposition") or "") for edge in edges).items())
        ),
        "authority_issue_count": len(
            collect_graph_authority_reconciliation_issues(graph_payload)
        ),
        "graph_nodes_sha256": canonical_sha256(nodes),
        "graph_edges_sha256": canonical_sha256(edges),
        "skill_rows_sha256": canonical_sha256(rows),
    }


def _field_change_records(
    before: Iterable[Mapping[str, Any]],
    after: Iterable[Mapping[str, Any]],
    *,
    identity_field: str,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    before_by_id = {str(item.get(identity_field) or ""): item for item in before}
    records: list[dict[str, Any]] = []
    for item in after:
        identity = str(item.get(identity_field) or "")
        source = before_by_id.get(identity) or {}
        changes = {
            field: {"before": source.get(field), "after": item.get(field)}
            for field in fields
            if source.get(field) != item.get(field)
        }
        if changes:
            records.append({identity_field: identity, "changes": changes})
    return records


def build_w3_receipt(
    *,
    before_graph: Mapping[str, Any],
    after_graph: Mapping[str, Any],
    contract: Mapping[str, Any],
    w2_receipt: Mapping[str, Any],
    legacy_artifacts: list[Mapping[str, Any]],
    historical_retired_edge_references: list[str],
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    validate_authority_reconciliation_contract(contract)
    if w2_receipt.get("schema_version") != W2_RECEIPT_SCHEMA_VERSION:
        raise GraphAuthorityReconciliationWave3Error("W3 source W2 receipt is invalid")
    validate_w2_receipt(w2_receipt)
    issues = collect_graph_authority_reconciliation_issues(after_graph)
    if issues:
        raise GraphAuthorityReconciliationWave3Error(
            f"cannot receipt invalid W3 graph: {issues[:8]}"
        )
    before_edges = {
        str(edge.get("edge_id") or ""): edge
        for edge in before_graph.get("graph_edges") or []
        if isinstance(edge, dict)
    }
    after_edges = {
        str(edge.get("edge_id") or ""): edge
        for edge in after_graph.get("graph_edges") or []
        if isinstance(edge, dict)
    }
    before_rows = {
        str(row.get("skill_id") or ""): row
        for row in before_graph.get("skill_rows") or []
        if isinstance(row, dict)
    }
    before_nodes = {
        str(node.get("node_id") or ""): node
        for node in before_graph.get("graph_nodes") or []
        if isinstance(node, dict)
    }
    retired = [
        _edge_summary(
            before_edges[edge_id],
            _retirement_reason(
                before_edges[edge_id], rows=before_rows, nodes=before_nodes
            ),
        )
        for edge_id in sorted(before_edges.keys() - after_edges.keys())
    ]
    added = [
        _edge_summary(after_edges[edge_id])
        for edge_id in sorted(after_edges.keys() - before_edges.keys())
    ]
    node_changes = _field_change_records(
        before_graph.get("graph_nodes") or [],
        after_graph.get("graph_nodes") or [],
        identity_field="node_id",
        fields=("activation_status", "support_level", "evidence_risk"),
    )
    row_changes = _field_change_records(
        before_graph.get("skill_rows") or [],
        after_graph.get("skill_rows") or [],
        identity_field="skill_id",
        fields=(
            "activation_status",
            "support_level",
            "evidence_risk",
            "graph_hop_path",
        ),
    )
    before_profile = authority_reconciliation_profile(before_graph)
    before_profile["authority_issue_count"] = None
    after_profile = authority_reconciliation_profile(after_graph)
    receipt: dict[str, Any] = {
        "schema_version": W3_RECEIPT_SCHEMA_VERSION,
        "wave_id": AUTHORITY_RECONCILIATION_WAVE,
        "status": "PASS",
        "completion_marker": W3_COMPLETION_MARKER,
        "source_baseline": {
            "commit": source_commit,
            "tree": source_tree,
            "wave2_receipt_sha256": str(w2_receipt.get("receipt_sha256") or ""),
        },
        "contract": {
            "path": AUTHORITY_RECONCILIATION_CONTRACT_PATH.as_posix(),
            "schema_version": contract.get("schema_version"),
            "canonical_sha256": canonical_sha256(contract),
        },
        "scope": {
            "repository": "apps_rg_v2",
            "authority_reconciled": True,
            "claim_authority_expanded": False,
            "skill_rows_added_or_deleted": False,
            "graph_nodes_added_or_deleted": False,
            "retrieval_eligibility_changed": False,
            "fact_authority_changed": False,
            "allowed_sections_expanded": False,
            "legacy_embedding_artifacts_changed": False,
            "replacement_vectors_generated": False,
            "production_promotion_authorized": False,
        },
        "before": {
            "graph_canonical_sha256": canonical_sha256(before_graph),
            "authority_profile": before_profile,
        },
        "after": {
            "graph_canonical_sha256": canonical_sha256(after_graph),
            "authority_profile": after_profile,
        },
        "reconciliation": {
            "retired_edge_count": len(retired),
            "retired_edge_reason_counts": dict(
                sorted(Counter(item["retirement_reason"] for item in retired).items())
            ),
            "retired_edges": retired,
            "added_edge_count": len(added),
            "added_edge_type_counts": dict(
                sorted(Counter(item["edge_type"] for item in added).items())
            ),
            "added_edges": added,
            "node_field_changes": node_changes,
            "skill_row_field_changes": row_changes,
        },
        "preservation": {
            "graph_node_identity_set_preserved": set(before_nodes) == {
                str(node.get("node_id") or "")
                for node in after_graph.get("graph_nodes") or []
            },
            "skill_row_identity_set_preserved": set(before_rows) == {
                str(row.get("skill_id") or "")
                for row in after_graph.get("skill_rows") or []
            },
            "retrieval_eligibility_preserved": {
                key: value.get("retrieval_eligible") for key, value in before_rows.items()
            }
            == {
                str(row.get("skill_id") or ""): row.get("retrieval_eligible")
                for row in after_graph.get("skill_rows") or []
            },
            "fact_id_links_preserved": {
                key: _strings(value.get("fact_id_links")) for key, value in before_rows.items()
            }
            == {
                str(row.get("skill_id") or ""): _strings(row.get("fact_id_links"))
                for row in after_graph.get("skill_rows") or []
            },
            "allowed_sections_preserved": {
                key: _strings(value.get("allowed_sections")) for key, value in before_rows.items()
            }
            == {
                str(row.get("skill_id") or ""): _strings(row.get("allowed_sections"))
                for row in after_graph.get("skill_rows") or []
            },
        },
        "historical_runtime_snapshots": {
            "status": "STALE_SNAPSHOT_REQUIRES_CURRENT_GRAPH_ID_REHYDRATION",
            "retired_edge_reference_file_count": len(
                historical_retired_edge_references
            ),
            "files": sorted(historical_retired_edge_references),
        },
        "legacy_embedding_artifacts": {
            "status": "STALE_FAIL_CLOSED_UNCHANGED_PENDING_W5_RETIREMENT",
            "artifact_count": len(legacy_artifacts),
            "artifacts": [dict(record) for record in legacy_artifacts],
        },
        "wave_exit_gates": {
            "node_semantic_hardening": "PASS_W1",
            "edge_assertion_hardening": "PASS_W2",
            "authority_reconciliation": "PASS_W3",
            "cluster_registry_materialization": "OPEN_W4",
            "legacy_artifact_retirement": "OPEN_W5",
            "cluster_embedding_generation": "OPEN_W6",
            "production_promotion": "NOT_AUTHORIZED",
        },
        "next_wave": "C03_CLUSTER_EMBEDDING_W4_CLUSTER_REGISTRY_MATERIALIZATION",
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    validate_w3_receipt(receipt)
    return receipt


def validate_w3_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema_version") != W3_RECEIPT_SCHEMA_VERSION:
        raise GraphAuthorityReconciliationWave3Error("W3 receipt schema is invalid")
    if receipt.get("status") != "PASS" or receipt.get("completion_marker") != (
        W3_COMPLETION_MARKER
    ):
        raise GraphAuthorityReconciliationWave3Error("W3 completion truth is invalid")
    scope = receipt.get("scope")
    required_false = (
        "claim_authority_expanded",
        "skill_rows_added_or_deleted",
        "graph_nodes_added_or_deleted",
        "retrieval_eligibility_changed",
        "fact_authority_changed",
        "allowed_sections_expanded",
        "legacy_embedding_artifacts_changed",
        "replacement_vectors_generated",
        "production_promotion_authorized",
    )
    if not isinstance(scope, Mapping) or scope.get("authority_reconciled") is not True:
        raise GraphAuthorityReconciliationWave3Error("W3 scope is invalid")
    if any(scope.get(field) is not False for field in required_false):
        raise GraphAuthorityReconciliationWave3Error(
            "W3 scope exceeds its mutation boundary"
        )
    preservation = receipt.get("preservation")
    if not isinstance(preservation, Mapping) or not all(
        preservation.get(field) is True
        for field in (
            "graph_node_identity_set_preserved",
            "skill_row_identity_set_preserved",
            "retrieval_eligibility_preserved",
            "fact_id_links_preserved",
            "allowed_sections_preserved",
        )
    ):
        raise GraphAuthorityReconciliationWave3Error(
            "W3 preservation contract failed"
        )
    after_profile = (receipt.get("after") or {}).get("authority_profile")
    if not isinstance(after_profile, Mapping) or after_profile.get(
        "authority_issue_count"
    ) != 0:
        raise GraphAuthorityReconciliationWave3Error(
            "W3 authority issue gate did not close"
        )
    legacy = receipt.get("legacy_embedding_artifacts")
    if not isinstance(legacy, Mapping) or legacy.get("artifact_count") != 13:
        raise GraphAuthorityReconciliationWave3Error(
            "W3 legacy artifact inventory is incomplete"
        )
    unsigned = dict(receipt)
    recorded = str(unsigned.pop("receipt_sha256", "") or "")
    observed = canonical_sha256(unsigned)
    if not recorded or recorded != observed:
        raise GraphAuthorityReconciliationWave3Error(
            f"W3 receipt digest mismatch: expected {observed}, observed {recorded}"
        )


__all__ = [
    "AUTHORITY_RECONCILIATION_CONTRACT_PATH",
    "AUTHORITY_RECONCILIATION_CONTRACT_VERSION",
    "AUTHORITY_RECONCILIATION_WAVE",
    "GRAPH_PATH",
    "GraphAuthorityReconciliationWave3Error",
    "W2_RECEIPT_PATH",
    "W3_COMPLETION_MARKER",
    "W3_RECEIPT_SCHEMA_VERSION",
    "authority_reconciliation_profile",
    "build_w3_receipt",
    "collect_graph_authority_reconciliation_issues",
    "reconcile_graph_authority_wave3",
    "validate_authority_reconciliation_contract",
    "validate_w3_receipt",
]
