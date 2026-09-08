"""Deterministic W2 semantic hardening for canonical C0.3 graph edges."""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    W1_RECEIPT_SCHEMA_VERSION,
    canonical_sha256,
)
from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    derive_registered_graph_endpoint_types,
)

EDGE_SEMANTIC_CONTRACT_VERSION = "apps_rg.c03_graph_edge_semantic_contract.v1"
EDGE_SEMANTIC_HARDENING_WAVE = "C03_CLUSTER_EMBEDDING_W2"
W2_RECEIPT_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_w2_receipt.v1"
W2_COMPLETION_MARKER = "C03_CLUSTER_EMBEDDING_W2_EDGE_ASSERTIONS_HARDENED"

EDGE_SEMANTIC_CONTRACT_PATH = Path(
    "src/apps_rg/fact_inventory/c03_graph_edge_semantic_contract.v1.json"
)
GRAPH_PATH = Path("src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json")
W1_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave1_node_semantic_hardening_receipt.json"
)

W2_EDGE_FIELDS = frozenset(
    {
        "edge_semantic_contract_version",
        "canonical_assertion_text",
        "assertion_basis",
        "assertion_basis_refs",
        "edge_semantic_status",
        "integrity_gap_reason",
        "lifecycle_disposition",
        "hardening_wave",
    }
)
W2_REQUIRED_EDGE_FIELDS = W2_EDGE_FIELDS - {"integrity_gap_reason"}

BASIS_KIND_BY_EDGE_TYPE = {
    "employment_hosts_fact": "evidence_reference",
    "skill_supported_by_fact": "evidence_reference",
    "skill_supported_by_repo_evidence": "evidence_reference",
    "skill_supported_by_source_concept": "source_field_derivation",
    "capability_domain_contains_skill": "source_field_derivation",
    "career_track_contains_capability_domain": "taxonomy_rule",
    "career_track_contains_epoch": "taxonomy_rule",
    "career_track_contains_pillar": "taxonomy_rule",
    "epoch_contains_pillar": "taxonomy_rule",
    "epoch_contains_skill": "source_field_derivation",
    "identity_supported_by_epoch": "taxonomy_rule",
    "identity_supported_by_pillar": "taxonomy_rule",
    "metric_bucket_contains_metric": "source_field_derivation",
    "pillar_contains_capability_domain": "taxonomy_rule",
    "jd_briefing_targeting_only": "policy_predicate",
    "pillar_section_eligibility": "policy_predicate",
    "projection_excludes_blocked_skill": "policy_predicate",
    "section_blocks_pending_source_skill": "policy_predicate",
    "section_blocks_skill_without_fact": "policy_predicate",
    "section_can_select_skill": "source_field_derivation",
    "skill_allowed_in_section": "source_field_derivation",
    "skill_external_claim_eligible": "policy_predicate",
    "skill_projection_only_internal": "policy_predicate",
    "skill_requires_human_confirmation": "policy_predicate",
    "srfs_requires_fact_id_only": "policy_predicate",
    "career_track_precedes_career_track": "non_causal_bridge",
    "employment_in_career_track": "operator_confirmation",
    "employment_produces_skill": "evidence_reference",
    "pillar_phase_bridge": "non_causal_bridge",
    "skill_can_surface_metric": "source_field_derivation",
    "skill_has_metric_bucket": "source_field_derivation",
    "skill_reinforces_skill": "non_causal_bridge",
}

EDGE_FAMILY_BY_TYPE = {
    **{
        value: "evidence"
        for value in (
            "employment_hosts_fact",
            "skill_supported_by_fact",
            "skill_supported_by_repo_evidence",
            "skill_supported_by_source_concept",
        )
    },
    **{
        value: "taxonomy"
        for value in (
            "capability_domain_contains_skill",
            "career_track_contains_capability_domain",
            "career_track_contains_epoch",
            "career_track_contains_pillar",
            "epoch_contains_pillar",
            "epoch_contains_skill",
            "identity_supported_by_epoch",
            "identity_supported_by_pillar",
            "metric_bucket_contains_metric",
            "pillar_contains_capability_domain",
        )
    },
    **{
        value: "policy_and_projection"
        for value in (
            "jd_briefing_targeting_only",
            "pillar_section_eligibility",
            "projection_excludes_blocked_skill",
            "section_blocks_pending_source_skill",
            "section_blocks_skill_without_fact",
            "section_can_select_skill",
            "skill_allowed_in_section",
            "skill_external_claim_eligible",
            "skill_projection_only_internal",
            "skill_requires_human_confirmation",
            "srfs_requires_fact_id_only",
        )
    },
    **{
        value: "relationship"
        for value in (
            "career_track_precedes_career_track",
            "employment_in_career_track",
            "employment_produces_skill",
            "pillar_phase_bridge",
            "skill_can_surface_metric",
            "skill_has_metric_bucket",
            "skill_reinforces_skill",
        )
    },
}

ROW_FIELD_BINDINGS: dict[str, tuple[str, str]] = {
    "capability_domain_contains_skill": ("target", "domain_id"),
    "epoch_contains_skill": ("target", "career_epoch"),
    "metric_bucket_contains_metric": ("target", "bucket"),
    "section_can_select_skill": ("target", "allowed_sections"),
    "skill_allowed_in_section": ("source", "allowed_sections"),
    "skill_can_surface_metric": ("source", "metric_option_ids"),
    "skill_has_metric_bucket": ("source", "metric_bucket"),
    "skill_supported_by_fact": ("source", "fact_id_links"),
    "skill_supported_by_repo_evidence": ("source", "repo_evidence_files"),
    "skill_supported_by_source_concept": ("source", "source_concepts"),
    "skill_external_claim_eligible": ("source", "external_claim_policy"),
    "skill_projection_only_internal": ("source", "external_claim_policy"),
    "skill_requires_human_confirmation": ("source", "human_confirmation_required"),
}

INTERNAL_ONLY_POLICIES = frozenset(
    {
        "internal_only",
        "internal_traversal_only",
        "pending_source_internal_only",
        "weak_snippet_internal_only",
    }
)
INTERNAL_ONLY_EDGE_TYPES = frozenset(
    {
        "jd_briefing_targeting_only",
        "projection_excludes_blocked_skill",
        "section_blocks_pending_source_skill",
        "section_blocks_skill_without_fact",
        "skill_projection_only_internal",
        "skill_requires_human_confirmation",
        "srfs_requires_fact_id_only",
    }
)
NON_ACTIVE_STATES = frozenset({"DRAFT", "HELD", "RETIRED"})
NON_CAUSAL_EDGE_TYPES = frozenset(
    {
        "career_track_precedes_career_track",
        "pillar_phase_bridge",
        "skill_reinforces_skill",
    }
)


class GraphEdgeSemanticHardeningError(RuntimeError):
    """Raised when W2 cannot deterministically harden or verify edge semantics."""


def validate_edge_semantic_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != EDGE_SEMANTIC_CONTRACT_VERSION:
        raise GraphEdgeSemanticHardeningError("W2 edge semantic contract is invalid")
    if contract.get("status") != "FROZEN":
        raise GraphEdgeSemanticHardeningError("W2 edge semantic contract is not frozen")
    if contract.get("basis_kind_by_edge_type") != BASIS_KIND_BY_EDGE_TYPE:
        raise GraphEdgeSemanticHardeningError("W2 edge basis registry is invalid")
    if set(BASIS_KIND_BY_EDGE_TYPE) != set(EDGE_FAMILY_BY_TYPE):
        raise GraphEdgeSemanticHardeningError("W2 edge family registry is incomplete")
    boundaries = contract.get("mutation_boundaries")
    if not isinstance(boundaries, Mapping):
        raise GraphEdgeSemanticHardeningError("W2 mutation boundaries are missing")
    expected = {
        "edge_id_changes_allowed": False,
        "edge_type_changes_allowed": False,
        "edge_endpoint_changes_allowed": False,
        "legacy_edge_field_changes_allowed": False,
        "graph_node_changes_allowed": False,
        "skill_row_changes_allowed": False,
        "legacy_embedding_artifact_changes_allowed": False,
        "replacement_embedding_generation_allowed": False,
        "production_promotion_allowed": False,
    }
    for field, value in expected.items():
        if boundaries.get(field) is not value:
            raise GraphEdgeSemanticHardeningError(
                f"W2 mutation boundary is invalid: {field}"
            )


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _humanize(value: str) -> str:
    normalized = value
    for prefix in (
        "section:",
        "section_",
        "concept_",
        "policy_",
        "repo_",
        "fact_",
        "skill:",
        "skill_",
        "domain_",
        "pillar_",
        "epoch_",
        "track_",
        "metric_bucket:",
        "metric_",
        "employment_",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized.replace(":", " ").replace("_", " ").strip()


def _endpoint_label(node_id: str, nodes: Mapping[str, Mapping[str, Any]]) -> str:
    node = nodes.get(node_id)
    if node:
        return str(node.get("label") or node_id).strip()
    if node_id == "jd_text":
        return "job-description and briefing input"
    return _humanize(node_id)


def _canonical_assertion_text(
    edge: Mapping[str, Any],
    *,
    nodes: Mapping[str, Mapping[str, Any]],
) -> str:
    edge_type = str(edge.get("edge_type") or "")
    source = _endpoint_label(str(edge.get("source_node_id") or ""), nodes)
    target = _endpoint_label(str(edge.get("target_node_id") or ""), nodes)
    templates = {
        "employment_hosts_fact": (
            f"{source} hosts {target} within its employment evidence episode; the "
            "relationship preserves source scope and does not expand the evidence claim."
        ),
        "skill_supported_by_fact": (
            f"{source} may be supported by {target}; external use is limited to the "
            "authorized content of that evidence record, not the skill label alone."
        ),
        "skill_supported_by_repo_evidence": (
            f"{source} is traceable to repository evidence {target} for portfolio context; "
            "repository evidence is not default resume-claim proof."
        ),
        "skill_supported_by_source_concept": (
            f"{source} is traceable to source concept {target}; the concept establishes "
            "implementation provenance but cannot independently authorize a claim."
        ),
        "capability_domain_contains_skill": (
            f"{source} classifies {target} as a member capability for taxonomy traversal; "
            "membership is structural and does not independently prove a claim."
        ),
        "career_track_contains_capability_domain": (
            f"{source} includes {target} within its operator-confirmed career taxonomy; "
            "the relationship scopes traversal and is not evidence of causation."
        ),
        "career_track_contains_epoch": (
            f"{source} includes the {target} epoch in its chronological career taxonomy; "
            "the relationship orders context and does not independently prove a claim."
        ),
        "career_track_contains_pillar": (
            f"{source} groups {target} as a career pillar for taxonomy traversal; the "
            "membership is structural and not external claim authority."
        ),
        "epoch_contains_pillar": (
            f"The {source} epoch groups {target} as a phase-specific pillar; this "
            "taxonomy relationship scopes chronology and is not independent claim proof."
        ),
        "epoch_contains_skill": (
            f"The {source} epoch classifies {target} within its career phase according to "
            "the canonical skill-row epoch field; membership does not prove a claim."
        ),
        "identity_supported_by_epoch": (
            f"The identity anchor uses the {target} epoch as one registered career context; "
            "this structural support does not independently authorize identity claims."
        ),
        "identity_supported_by_pillar": (
            f"The identity anchor uses {target} as one registered capability pillar; this "
            "structural support does not independently authorize identity claims."
        ),
        "metric_bucket_contains_metric": (
            f"The {source} metric bucket contains {target} as an internal outcome option; "
            "the option requires a separately authorized metric fact before external use."
        ),
        "pillar_contains_capability_domain": (
            f"{source} groups {target} as a capability-domain boundary for traversal; the "
            "taxonomy relationship is not independent claim proof."
        ),
        "jd_briefing_targeting_only": (
            f"The {source} may influence targeting only through {target}; it cannot become "
            "candidate evidence or supply a source fact for a resume claim."
        ),
        "pillar_section_eligibility": (
            f"{source} may be considered for the {target} section only when active member "
            "evidence and the section policy both pass; the edge adds no evidence."
        ),
        "projection_excludes_blocked_skill": (
            f"{source} is excluded from external projection under {target} while its "
            "evidence or lifecycle status remains blocked or pending."
        ),
        "section_blocks_pending_source_skill": (
            f"The {source} section applies {target} to block pending-source skills from "
            "external output until their evidence authority is activated."
        ),
        "section_blocks_skill_without_fact": (
            f"The {source} section applies {target} to block any skill that lacks an "
            "authorized supporting fact; the skill identifier is never proof."
        ),
        "section_can_select_skill": (
            f"The {source} section may select {target} only within the skill row's section "
            "allowlist and active evidence policy; selection cannot add evidence."
        ),
        "skill_allowed_in_section": (
            f"{source} is allowlisted for the {target} section by its canonical skill row; "
            "section eligibility narrows projection but does not authorize a claim."
        ),
        "skill_external_claim_eligible": (
            f"{source} is conditionally eligible under {target} only when its current "
            "external-claim policy and linked active evidence both permit projection."
        ),
        "skill_projection_only_internal": (
            f"{source} is restricted by {target} to internal ranking and traversal; this "
            "edge cannot authorize external resume language."
        ),
        "skill_requires_human_confirmation": (
            f"{source} remains gated by {target} until the required human confirmation "
            "and evidence activation are both recorded."
        ),
        "srfs_requires_fact_id_only": (
            f"{source} is governed by {target}: external proof must resolve to an authorized "
            "fact identifier, and skill or targeting identifiers cannot substitute."
        ),
        "career_track_precedes_career_track": (
            f"{source} precedes {target} in the operator-confirmed career sequence; this is "
            "a non-causal chronology bridge used only for ordered traversal."
        ),
        "employment_in_career_track": (
            f"{source} belongs to {target} under the operator-confirmed date-overlap "
            "taxonomy; the assignment scopes chronology and is not a causal assertion."
        ),
        "employment_produces_skill": (
            f"{target} is associated with the {source} employment episode through its "
            "linked evidence; the relationship attributes context without claiming causation."
        ),
        "pillar_phase_bridge": (
            f"{source} connects to {target} as an evidence-scoped, non-causal career-phase "
            "bridge; traversal must retain the bridge's registered evidence references."
        ),
        "skill_can_surface_metric": (
            f"{source} may surface the {target} metric option for selection diversity only; "
            "external use still requires a linked metric-bearing fact."
        ),
        "skill_has_metric_bucket": (
            f"{source} is assigned to the {target} metric bucket for outcome-diversity "
            "selection; the bucket supplies no metric proof."
        ),
        "skill_reinforces_skill": (
            f"{source} is adjacent to {target} for sibling and reverse traversal; this is a "
            "non-causal reinforcement link and cannot expand claim authority."
        ),
    }
    try:
        return templates[edge_type]
    except KeyError as exc:
        raise GraphEdgeSemanticHardeningError(
            f"unregistered edge semantic template: {edge_type}"
        ) from exc


def _endpoint_ref(node_id: str, nodes: Mapping[str, Mapping[str, Any]]) -> str:
    prefix = "ledger:graph_nodes/" if node_id in nodes else "endpoint:"
    return f"{prefix}{node_id}"


def _basis_refs(
    edge: Mapping[str, Any],
    *,
    nodes: Mapping[str, Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    edge_id = str(edge.get("edge_id") or "")
    edge_type = str(edge.get("edge_type") or "")
    source_id = str(edge.get("source_node_id") or "")
    target_id = str(edge.get("target_node_id") or "")
    provenance = (
        "authority_reconciliation"
        if edge.get("hardening_wave") == "C03_CLUSTER_EMBEDDING_W3"
        else "baseline"
    )
    refs = {
        f"contract:edge_types/{edge_type}",
        f"{provenance}:graph_edges/{edge_id}",
        _endpoint_ref(source_id, nodes),
        _endpoint_ref(target_id, nodes),
    }
    binding = ROW_FIELD_BINDINGS.get(edge_type)
    if edge_type == "capability_domain_contains_skill":
        source = nodes.get(source_id)
        field = (
            "pillar"
            if source and source.get("node_type") == "domain_pillar"
            else "domain_id"
        )
        binding = ("target", field)
    if binding:
        side, field = binding
        endpoint_id = source_id if side == "source" else target_id
        if endpoint_id in rows and field in rows[endpoint_id]:
            refs.add(f"ledger:skill_rows/{endpoint_id}/{field}")
        elif endpoint_id in nodes and field in nodes[endpoint_id]:
            refs.add(f"ledger:graph_nodes/{endpoint_id}/{field}")
    if edge_type in {
        "employment_hosts_fact",
        "skill_supported_by_fact",
    }:
        refs.add(f"evidence:{target_id}")
    if edge_type == "employment_produces_skill" and target_id in rows:
        refs.add(f"ledger:skill_rows/{target_id}/fact_id_links")
    if edge_type == "employment_in_career_track" and source_id in nodes:
        for field in ("start_date", "end_date"):
            if field in nodes[source_id]:
                refs.add(f"ledger:graph_nodes/{source_id}/{field}")
    for fact_id in _strings(edge.get("evidence_fact_ids")):
        refs.add(f"evidence:{fact_id}")
    return sorted(refs)


def _section_id(value: str) -> str:
    for prefix in ("section:", "section_"):
        if value.startswith(prefix):
            return value.removeprefix(prefix)
    return value


def _integrity_gap_reason(
    edge: Mapping[str, Any],
    *,
    nodes: Mapping[str, Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
) -> str:
    edge_type = str(edge.get("edge_type") or "")
    source_id = str(edge.get("source_node_id") or "")
    target_id = str(edge.get("target_node_id") or "")
    if edge_type == "capability_domain_contains_skill":
        row = rows.get(target_id) or {}
        source = nodes.get(source_id)
        field = (
            "pillar"
            if source and source.get("node_type") == "domain_pillar"
            else "domain_id"
        )
        if str(row.get(field) or "") != source_id:
            return f"SOURCE_FIELD_CONFLICT:{field}"
    if edge_type == "section_can_select_skill":
        allowed = _strings((rows.get(target_id) or {}).get("allowed_sections"))
        if _section_id(source_id) not in allowed:
            return "SECTION_NOT_IN_SKILL_ROW_ALLOWLIST"
    if edge_type == "skill_projection_only_internal":
        row = rows.get(source_id) or {}
        if row.get("retrieval_eligible") is True:
            return "INTERNAL_ONLY_EDGE_CONFLICTS_WITH_RETRIEVAL_ELIGIBLE_ROW"
    return ""


def _lifecycle_disposition(
    edge: Mapping[str, Any],
    *,
    nodes: Mapping[str, Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
) -> str:
    if _integrity_gap_reason(edge, nodes=nodes, rows=rows):
        return "HELD_INTEGRITY_GAP"
    endpoint_nodes = [
        nodes[node_id]
        for node_id in (
            str(edge.get("source_node_id") or ""),
            str(edge.get("target_node_id") or ""),
        )
        if node_id in nodes
    ]
    if any(
        str(node.get("activation_status") or "") in NON_ACTIVE_STATES
        or node.get("semantic_hardening_status") == "HELD_INTERNAL_ONLY"
        for node in endpoint_nodes
    ):
        return "HELD_NON_ACTIVE_ENDPOINT"
    if (
        str(edge.get("edge_type") or "") in INTERNAL_ONLY_EDGE_TYPES
        or str(edge.get("external_claim_policy") or "") in INTERNAL_ONLY_POLICIES
        or any(
            node.get("visibility_rule") == "never_external" for node in endpoint_nodes
        )
    ):
        return "INTERNAL_TRAVERSAL_ONLY"
    return "ACTIVE_POLICY_GATED"


def _edge_identity_rows(edges: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted(str(edge.get("edge_id") or "") for edge in edges)


def _edge_topology_rows(edges: Iterable[Mapping[str, Any]]) -> list[list[str]]:
    return sorted(
        [
            str(edge.get("edge_id") or ""),
            str(edge.get("source_node_id") or ""),
            str(edge.get("edge_type") or ""),
            str(edge.get("target_node_id") or ""),
        ]
        for edge in edges
    )


def _legacy_edges(edges: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: copy.deepcopy(value)
            for key, value in edge.items()
            if key not in W2_EDGE_FIELDS
        }
        for edge in edges
    ]


def harden_graph_edge_semantics(graph_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a W2 graph with concrete edge assertions and lifecycle dispositions."""

    output = copy.deepcopy(dict(graph_payload))
    metadata = output.get("graph_metadata")
    if not isinstance(metadata, dict):
        raise GraphEdgeSemanticHardeningError("graph_metadata must be an object")
    existing = metadata.get("edge_semantic_hardening")
    if (
        isinstance(existing, dict)
        and existing.get("contract_version") == EDGE_SEMANTIC_CONTRACT_VERSION
    ):
        issues = collect_graph_edge_semantic_issues(output)
        if issues:
            raise GraphEdgeSemanticHardeningError(
                f"existing W2 hardening marker is invalid: {issues[:5]}"
            )
        return output
    raw_edges = output.get("graph_edges")
    raw_nodes = output.get("graph_nodes")
    raw_rows = output.get("skill_rows")
    if not all(isinstance(value, list) for value in (raw_edges, raw_nodes, raw_rows)):
        raise GraphEdgeSemanticHardeningError(
            "graph edges, nodes, and rows must be lists"
        )
    edges = [dict(edge) for edge in raw_edges if isinstance(edge, dict)]
    nodes = [dict(node) for node in raw_nodes if isinstance(node, dict)]
    rows = [dict(row) for row in raw_rows if isinstance(row, dict)]
    if len(edges) != len(raw_edges):
        raise GraphEdgeSemanticHardeningError("graph contains non-object edges")
    node_by_id = {str(node.get("node_id") or ""): node for node in nodes}
    row_by_id = {str(row.get("skill_id") or ""): row for row in rows}
    source_edge_digest = canonical_sha256(edges)
    source_legacy_digest = canonical_sha256(_legacy_edges(edges))
    source_identity_digest = canonical_sha256(_edge_identity_rows(edges))
    source_topology_digest = canonical_sha256(_edge_topology_rows(edges))
    source_node_digest = canonical_sha256(nodes)
    source_row_digest = canonical_sha256(rows)

    for edge in edges:
        edge_type = str(edge.get("edge_type") or "")
        if edge_type not in BASIS_KIND_BY_EDGE_TYPE:
            raise GraphEdgeSemanticHardeningError(
                f"unregistered W2 edge type: {edge_type}"
            )
        edge["edge_semantic_contract_version"] = EDGE_SEMANTIC_CONTRACT_VERSION
        assertion_text = _canonical_assertion_text(
            edge,
            nodes=node_by_id,
        )
        integrity_gap_reason = _integrity_gap_reason(
            edge,
            nodes=node_by_id,
            rows=row_by_id,
        )
        if integrity_gap_reason:
            assertion_text += (
                " This registered relationship is held from release use because its "
                "asserted authority conflicts with the current source fields."
            )
        edge["canonical_assertion_text"] = assertion_text
        edge["assertion_basis"] = BASIS_KIND_BY_EDGE_TYPE[edge_type]
        edge["assertion_basis_refs"] = _basis_refs(
            edge,
            nodes=node_by_id,
            rows=row_by_id,
        )
        edge["edge_semantic_status"] = (
            "HELD_INTEGRITY_GAP" if integrity_gap_reason else "HARDENED"
        )
        if integrity_gap_reason:
            edge["integrity_gap_reason"] = integrity_gap_reason
        edge["lifecycle_disposition"] = _lifecycle_disposition(
            edge,
            nodes=node_by_id,
            rows=row_by_id,
        )
        edge["hardening_wave"] = EDGE_SEMANTIC_HARDENING_WAVE

    output["graph_edges"] = edges
    dispositions = Counter(str(edge["lifecycle_disposition"]) for edge in edges)
    metadata["edge_semantic_contract_version"] = EDGE_SEMANTIC_CONTRACT_VERSION
    metadata["edge_semantic_hardening"] = {
        "contract_version": EDGE_SEMANTIC_CONTRACT_VERSION,
        "wave_id": EDGE_SEMANTIC_HARDENING_WAVE,
        "edge_count": len(edges),
        "semantically_specified_edge_count": len(edges),
        "hardened_edge_count": sum(
            1 for edge in edges if edge["edge_semantic_status"] == "HARDENED"
        ),
        "held_integrity_gap_edge_count": sum(
            1 for edge in edges if edge["edge_semantic_status"] == "HELD_INTEGRITY_GAP"
        ),
        "semantic_status_counts": dict(
            sorted(Counter(str(edge["edge_semantic_status"]) for edge in edges).items())
        ),
        "integrity_gap_count": sum(
            1 for edge in edges if edge["edge_semantic_status"] == "HELD_INTEGRITY_GAP"
        ),
        "integrity_gap_reason_counts": dict(
            sorted(
                Counter(
                    str(edge.get("integrity_gap_reason") or "")
                    for edge in edges
                    if edge["edge_semantic_status"] == "HELD_INTEGRITY_GAP"
                ).items()
            )
        ),
        "basis_kind_counts": dict(
            sorted(Counter(str(edge["assertion_basis"]) for edge in edges).items())
        ),
        "lifecycle_disposition_counts": dict(sorted(dispositions.items())),
        "source_graph_edges_sha256": source_edge_digest,
        "hardened_graph_edges_sha256": canonical_sha256(edges),
        "legacy_edge_payload_sha256_before": source_legacy_digest,
        "legacy_edge_payload_sha256_after": canonical_sha256(_legacy_edges(edges)),
        "edge_identity_sha256_before": source_identity_digest,
        "edge_identity_sha256_after": canonical_sha256(_edge_identity_rows(edges)),
        "edge_topology_sha256_before": source_topology_digest,
        "edge_topology_sha256_after": canonical_sha256(_edge_topology_rows(edges)),
        "graph_nodes_sha256_before": source_node_digest,
        "graph_nodes_sha256_after": canonical_sha256(output["graph_nodes"]),
        "skill_rows_sha256_before": source_row_digest,
        "skill_rows_sha256_after": canonical_sha256(output["skill_rows"]),
        "production_promotion_authorized": False,
    }
    issues = collect_graph_edge_semantic_issues(output)
    if issues:
        raise GraphEdgeSemanticHardeningError(
            f"W2 edge semantic hardening failed: {issues[:12]}"
        )
    return output


def _is_generic_assertion(edge: Mapping[str, Any]) -> bool:
    text = str(edge.get("canonical_assertion_text") or "").strip()
    return bool(
        len(text) < 80
        or text.lower() in {"", "none", "null", "n/a", "tbd", "unknown"}
        or text == str(edge.get("rationale") or "").strip()
        or text == str(edge.get("edge_type") or "").strip()
    )


def _ref_resolves(
    ref: str,
    *,
    edge: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
    derived_endpoints: Mapping[str, str],
) -> bool:
    if ref == f"contract:edge_types/{edge.get('edge_type')}":
        return True
    if ref == f"baseline:graph_edges/{edge.get('edge_id')}":
        return True
    if ref == f"authority_reconciliation:graph_edges/{edge.get('edge_id')}":
        return edge.get("hardening_wave") == "C03_CLUSTER_EMBEDDING_W3"
    if ref.startswith("ledger:graph_nodes/"):
        parts = ref.removeprefix("ledger:graph_nodes/").split("/")
        node = nodes.get(parts[0])
        return bool(node and (len(parts) == 1 or parts[1] in node))
    if ref.startswith("ledger:skill_rows/"):
        parts = ref.removeprefix("ledger:skill_rows/").split("/")
        row = rows.get(parts[0])
        return bool(row and len(parts) == 2 and parts[1] in row)
    if ref.startswith("endpoint:"):
        return ref.removeprefix("endpoint:") in derived_endpoints
    if ref.startswith("evidence:"):
        endpoint_type = derived_endpoints.get(ref.removeprefix("evidence:"), "")
        return endpoint_type in {
            "atomic_proof_fact",
            "bullet_fact",
            "certification_evidence",
            "experience_evidence",
        }
    return False


def _add_issue(issues: list[str], code: str, offenders: Iterable[Any]) -> None:
    values = sorted({str(value) for value in offenders if str(value).strip()})
    if values:
        issues.append(f"{code}: count={len(values)} offenders={values[:12]}")


def collect_graph_edge_semantic_issues(
    graph_payload: Mapping[str, Any],
) -> list[str]:
    """Return deterministic W2 semantic and lifecycle issues for all graph edges."""

    issues: list[str] = []
    edges = list(graph_payload.get("graph_edges") or [])
    nodes = {
        str(node.get("node_id") or ""): node
        for node in graph_payload.get("graph_nodes") or []
        if isinstance(node, dict)
    }
    rows = {
        str(row.get("skill_id") or ""): row
        for row in graph_payload.get("skill_rows") or []
        if isinstance(row, dict)
    }
    metadata = graph_payload.get("graph_metadata")
    marker = (
        metadata.get("edge_semantic_hardening")
        if isinstance(metadata, Mapping)
        else None
    )
    if not isinstance(marker, Mapping):
        return ["GRAPH_EDGE_SEMANTIC_HARDENING_MARKER_MISSING"]
    reconciliation_marker = (
        metadata.get("authority_reconciliation")
        if isinstance(metadata, Mapping)
        else None
    )
    has_w3_reconciliation = isinstance(reconciliation_marker, Mapping)
    derived_endpoints = derive_registered_graph_endpoint_types(dict(graph_payload))
    missing_fields: list[str] = []
    generic_assertions: list[str] = []
    basis_mismatch: list[str] = []
    basis_refs_invalid: list[str] = []
    basis_refs_unresolved: list[str] = []
    status_invalid: list[str] = []
    lifecycle_invalid: list[str] = []
    causal_violations: list[str] = []
    required_fields = tuple(W2_REQUIRED_EDGE_FIELDS)

    for index, raw_edge in enumerate(edges):
        if not isinstance(raw_edge, dict):
            missing_fields.append(f"graph_edges[{index}]")
            continue
        edge = raw_edge
        edge_id = str(edge.get("edge_id") or f"graph_edges[{index}]")
        edge_type = str(edge.get("edge_type") or "")
        for field in required_fields:
            value = edge.get(field)
            if value is None or value == "" or value == []:
                missing_fields.append(f"{edge_id}.{field}")
        if edge.get("edge_semantic_contract_version") != EDGE_SEMANTIC_CONTRACT_VERSION:
            missing_fields.append(f"{edge_id}.edge_semantic_contract_version")
        allowed_hardening_waves = {EDGE_SEMANTIC_HARDENING_WAVE}
        if has_w3_reconciliation:
            allowed_hardening_waves.add("C03_CLUSTER_EMBEDDING_W3")
        if edge.get("hardening_wave") not in allowed_hardening_waves:
            missing_fields.append(f"{edge_id}.hardening_wave")
        if _is_generic_assertion(edge):
            generic_assertions.append(edge_id)
        if edge.get("assertion_basis") != BASIS_KIND_BY_EDGE_TYPE.get(edge_type):
            basis_mismatch.append(edge_id)
        refs = edge.get("assertion_basis_refs")
        expected_refs = _basis_refs(edge, nodes=nodes, rows=rows)
        if not isinstance(refs, list) or refs != sorted(set(_strings(refs))):
            basis_refs_invalid.append(edge_id)
            normalized_refs: list[str] = []
        else:
            normalized_refs = _strings(refs)
            if normalized_refs != expected_refs:
                basis_refs_invalid.append(edge_id)
        basis_refs_unresolved.extend(
            f"{edge_id}={ref}"
            for ref in normalized_refs
            if not _ref_resolves(
                ref,
                edge=edge,
                nodes=nodes,
                rows=rows,
                derived_endpoints=derived_endpoints,
            )
        )
        expected_gap = _integrity_gap_reason(edge, nodes=nodes, rows=rows)
        expected_status = "HELD_INTEGRITY_GAP" if expected_gap else "HARDENED"
        if edge.get("edge_semantic_status") != expected_status:
            status_invalid.append(edge_id)
        if str(edge.get("integrity_gap_reason") or "") != expected_gap:
            status_invalid.append(f"{edge_id}.integrity_gap_reason")
        expected_lifecycle = _lifecycle_disposition(edge, nodes=nodes, rows=rows)
        if edge.get("lifecycle_disposition") != expected_lifecycle:
            lifecycle_invalid.append(edge_id)
        if edge_type in NON_CAUSAL_EDGE_TYPES:
            text = str(edge.get("canonical_assertion_text") or "").lower()
            if edge.get("causal") is True or "non-causal" not in text:
                causal_violations.append(edge_id)

    _add_issue(issues, "GRAPH_EDGE_SEMANTIC_FIELD_MISSING", missing_fields)
    _add_issue(issues, "GRAPH_EDGE_ASSERTION_NOT_CONCRETE", generic_assertions)
    _add_issue(issues, "GRAPH_EDGE_ASSERTION_BASIS_MISMATCH", basis_mismatch)
    _add_issue(issues, "GRAPH_EDGE_ASSERTION_BASIS_REFS_INVALID", basis_refs_invalid)
    _add_issue(
        issues,
        "GRAPH_EDGE_ASSERTION_BASIS_REF_UNRESOLVED",
        basis_refs_unresolved,
    )
    _add_issue(issues, "GRAPH_EDGE_SEMANTIC_STATUS_INVALID", status_invalid)
    _add_issue(issues, "GRAPH_EDGE_LIFECYCLE_DISPOSITION_INVALID", lifecycle_invalid)
    _add_issue(issues, "GRAPH_EDGE_CAUSALITY_VIOLATION", causal_violations)

    marker_mismatches: list[str] = []
    if marker.get("contract_version") != EDGE_SEMANTIC_CONTRACT_VERSION:
        marker_mismatches.append("contract_version")
    if marker.get("wave_id") != EDGE_SEMANTIC_HARDENING_WAVE:
        marker_mismatches.append("wave_id")
    if has_w3_reconciliation:
        historical_bindings = {
            "edge_count": reconciliation_marker.get("source_edge_count"),
            "hardened_graph_edges_sha256": reconciliation_marker.get(
                "source_graph_edges_sha256"
            ),
            "graph_nodes_sha256_after": reconciliation_marker.get(
                "source_graph_nodes_sha256"
            ),
            "skill_rows_sha256_after": reconciliation_marker.get(
                "source_skill_rows_sha256"
            ),
        }
        for field, expected in historical_bindings.items():
            if marker.get(field) != expected:
                marker_mismatches.append(field)
        if reconciliation_marker.get("source_w2_marker_sha256") != canonical_sha256(
            marker
        ):
            marker_mismatches.append("source_w2_marker_sha256")
        if marker.get("semantically_specified_edge_count") != marker.get(
            "edge_count"
        ):
            marker_mismatches.append("semantically_specified_edge_count")
        if marker.get("hardened_edge_count", 0) + marker.get(
            "held_integrity_gap_edge_count", 0
        ) != marker.get("edge_count"):
            marker_mismatches.append("historical_semantic_counts")
        if marker.get("integrity_gap_count") != marker.get(
            "held_integrity_gap_edge_count"
        ):
            marker_mismatches.append("historical_integrity_gap_count")
        for before, after in (
            ("legacy_edge_payload_sha256_before", "legacy_edge_payload_sha256_after"),
            ("edge_identity_sha256_before", "edge_identity_sha256_after"),
            ("edge_topology_sha256_before", "edge_topology_sha256_after"),
            ("graph_nodes_sha256_before", "graph_nodes_sha256_after"),
            ("skill_rows_sha256_before", "skill_rows_sha256_after"),
        ):
            if marker.get(before) != marker.get(after):
                marker_mismatches.append(f"{before}!={after}")
        if marker.get("production_promotion_authorized") is not False:
            marker_mismatches.append("production_promotion_authorized")
        _add_issue(
            issues,
            "GRAPH_EDGE_SEMANTIC_MARKER_MISMATCH",
            marker_mismatches,
        )
        return issues
    if marker.get("edge_count") != len(edges):
        marker_mismatches.append("edge_count")
    if marker.get("semantically_specified_edge_count") != len(edges):
        marker_mismatches.append("semantically_specified_edge_count")
    expected_hardened_count = sum(
        1 for edge in edges if edge.get("edge_semantic_status") == "HARDENED"
    )
    expected_held_count = sum(
        1 for edge in edges if edge.get("edge_semantic_status") == "HELD_INTEGRITY_GAP"
    )
    if marker.get("hardened_edge_count") != expected_hardened_count:
        marker_mismatches.append("hardened_edge_count")
    if marker.get("held_integrity_gap_edge_count") != expected_held_count:
        marker_mismatches.append("held_integrity_gap_edge_count")
    expected_marker_digests = {
        "hardened_graph_edges_sha256": canonical_sha256(edges),
        "legacy_edge_payload_sha256_after": canonical_sha256(_legacy_edges(edges)),
        "edge_identity_sha256_after": canonical_sha256(_edge_identity_rows(edges)),
        "edge_topology_sha256_after": canonical_sha256(_edge_topology_rows(edges)),
        "graph_nodes_sha256_after": canonical_sha256(
            graph_payload.get("graph_nodes") or []
        ),
        "skill_rows_sha256_after": canonical_sha256(
            graph_payload.get("skill_rows") or []
        ),
    }
    for field, expected in expected_marker_digests.items():
        if marker.get(field) != expected:
            marker_mismatches.append(field)
    for before, after in (
        ("legacy_edge_payload_sha256_before", "legacy_edge_payload_sha256_after"),
        ("edge_identity_sha256_before", "edge_identity_sha256_after"),
        ("edge_topology_sha256_before", "edge_topology_sha256_after"),
        ("graph_nodes_sha256_before", "graph_nodes_sha256_after"),
        ("skill_rows_sha256_before", "skill_rows_sha256_after"),
    ):
        if marker.get(before) != marker.get(after):
            marker_mismatches.append(f"{before}!={after}")
    dispositions = dict(
        sorted(
            Counter(
                str(edge.get("lifecycle_disposition") or "") for edge in edges
            ).items()
        )
    )
    if marker.get("lifecycle_disposition_counts") != dispositions:
        marker_mismatches.append("lifecycle_disposition_counts")
    statuses = dict(
        sorted(
            Counter(
                str(edge.get("edge_semantic_status") or "") for edge in edges
            ).items()
        )
    )
    if marker.get("semantic_status_counts") != statuses:
        marker_mismatches.append("semantic_status_counts")
    if marker.get("integrity_gap_count") != statuses.get("HELD_INTEGRITY_GAP", 0):
        marker_mismatches.append("integrity_gap_count")
    gap_reasons = dict(
        sorted(
            Counter(
                str(edge.get("integrity_gap_reason") or "")
                for edge in edges
                if edge.get("edge_semantic_status") == "HELD_INTEGRITY_GAP"
            ).items()
        )
    )
    if marker.get("integrity_gap_reason_counts") != gap_reasons:
        marker_mismatches.append("integrity_gap_reason_counts")
    if marker.get("production_promotion_authorized") is not False:
        marker_mismatches.append("production_promotion_authorized")
    _add_issue(issues, "GRAPH_EDGE_SEMANTIC_MARKER_MISMATCH", marker_mismatches)
    return issues


def edge_semantic_profile(graph_payload: Mapping[str, Any]) -> dict[str, Any]:
    edges = [
        edge
        for edge in graph_payload.get("graph_edges") or []
        if isinstance(edge, dict)
    ]
    metadata = graph_payload.get("graph_metadata") or {}
    has_marker = isinstance(metadata.get("edge_semantic_hardening"), Mapping)
    return {
        "edge_count": len(edges),
        "edge_type_count": len({str(edge.get("edge_type") or "") for edge in edges}),
        "edge_type_counts": dict(
            sorted(Counter(str(edge.get("edge_type") or "") for edge in edges).items())
        ),
        "missing_canonical_assertion_count": sum(
            1
            for edge in edges
            if not str(edge.get("canonical_assertion_text") or "").strip()
        ),
        "missing_assertion_basis_count": sum(
            1 for edge in edges if not str(edge.get("assertion_basis") or "").strip()
        ),
        "generic_assertion_count": sum(
            1 for edge in edges if _is_generic_assertion(edge)
        ),
        "semantic_status_counts": dict(
            sorted(
                Counter(
                    str(edge.get("edge_semantic_status") or "UNSET") for edge in edges
                ).items()
            )
        ),
        "integrity_gap_count": sum(
            1
            for edge in edges
            if edge.get("edge_semantic_status") == "HELD_INTEGRITY_GAP"
        ),
        "integrity_gap_reason_counts": dict(
            sorted(
                Counter(
                    str(edge.get("integrity_gap_reason") or "")
                    for edge in edges
                    if edge.get("edge_semantic_status") == "HELD_INTEGRITY_GAP"
                ).items()
            )
        ),
        "lifecycle_disposition_counts": dict(
            sorted(
                Counter(
                    str(edge.get("lifecycle_disposition") or "UNSET") for edge in edges
                ).items()
            )
        ),
        "semantic_issue_count": (
            len(collect_graph_edge_semantic_issues(graph_payload))
            if has_marker
            else None
        ),
        "graph_edges_sha256": canonical_sha256(edges),
        "edge_identity_sha256": canonical_sha256(_edge_identity_rows(edges)),
        "edge_topology_sha256": canonical_sha256(_edge_topology_rows(edges)),
        "legacy_edge_payload_sha256": canonical_sha256(_legacy_edges(edges)),
    }


def build_w2_receipt(
    *,
    before_graph: Mapping[str, Any],
    after_graph: Mapping[str, Any],
    w1_receipt: Mapping[str, Any],
    contract: Mapping[str, Any],
    legacy_artifacts: list[Mapping[str, Any]],
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    validate_edge_semantic_contract(contract)
    if w1_receipt.get("schema_version") != W1_RECEIPT_SCHEMA_VERSION:
        raise GraphEdgeSemanticHardeningError("W2 source W1 receipt is invalid")
    issues = collect_graph_edge_semantic_issues(after_graph)
    if issues:
        raise GraphEdgeSemanticHardeningError(
            f"cannot receipt invalid W2 graph: {issues}"
        )
    before_profile = edge_semantic_profile(before_graph)
    after_profile = edge_semantic_profile(after_graph)
    marker = (after_graph.get("graph_metadata") or {}).get(
        "edge_semantic_hardening"
    ) or {}
    receipt: dict[str, Any] = {
        "schema_version": W2_RECEIPT_SCHEMA_VERSION,
        "wave_id": EDGE_SEMANTIC_HARDENING_WAVE,
        "status": "PASS",
        "completion_marker": W2_COMPLETION_MARKER,
        "source_baseline": {
            "commit": source_commit,
            "tree": source_tree,
            "wave1_receipt_sha256": str(w1_receipt.get("receipt_sha256") or ""),
        },
        "contract": {
            "path": EDGE_SEMANTIC_CONTRACT_PATH.as_posix(),
            "schema_version": contract.get("schema_version"),
            "canonical_sha256": canonical_sha256(contract),
        },
        "scope": {
            "repository": "apps_rg_v2",
            "edge_assertions_semantically_specified": True,
            "edge_assertions_fully_reconciled": False,
            "edge_topology_changed": False,
            "graph_nodes_changed": False,
            "skill_rows_changed": False,
            "legacy_embedding_artifacts_changed": False,
            "replacement_vectors_generated": False,
            "production_promotion_authorized": False,
        },
        "before": {
            "graph_canonical_sha256": canonical_sha256(before_graph),
            "edge_semantic_profile": before_profile,
        },
        "after": {
            "graph_canonical_sha256": canonical_sha256(after_graph),
            "edge_semantic_profile": after_profile,
            "basis_kind_counts": dict(marker.get("basis_kind_counts") or {}),
            "semantic_status_counts": dict(marker.get("semantic_status_counts") or {}),
        },
        "preservation": {
            "edge_count_preserved": before_profile["edge_count"]
            == after_profile["edge_count"],
            "edge_identity_set_preserved": before_profile["edge_identity_sha256"]
            == after_profile["edge_identity_sha256"],
            "edge_topology_preserved": before_profile["edge_topology_sha256"]
            == after_profile["edge_topology_sha256"],
            "legacy_edge_payload_preserved": before_profile[
                "legacy_edge_payload_sha256"
            ]
            == after_profile["legacy_edge_payload_sha256"],
            "graph_nodes_preserved": canonical_sha256(
                before_graph.get("graph_nodes") or []
            )
            == canonical_sha256(after_graph.get("graph_nodes") or []),
            "skill_rows_preserved": canonical_sha256(
                before_graph.get("skill_rows") or []
            )
            == canonical_sha256(after_graph.get("skill_rows") or []),
        },
        "legacy_embedding_artifacts": {
            "status": "STALE_FAIL_CLOSED_UNCHANGED_PENDING_W5_RETIREMENT",
            "artifact_count": len(legacy_artifacts),
            "artifacts": [dict(record) for record in legacy_artifacts],
        },
        "wave_exit_gates": {
            "node_semantic_hardening": "PASS_W1",
            "edge_assertion_hardening": (
                f"PASS_WITH_{after_profile['integrity_gap_count']}_HELD_INTEGRITY_GAPS"
            ),
            "edge_basis_resolution": "PASS",
            "edge_lifecycle_disposition": "PASS",
            "edge_topology_preservation": "PASS",
            "integrity_gaps_held": (
                f"PASS_{after_profile['integrity_gap_count']}_HELD_FOR_W3"
            ),
            "authority_reconciliation": "OPEN_W3",
            "cluster_registry_materialization": "OPEN_W4",
            "legacy_artifact_retirement": "OPEN_W5",
            "cluster_embedding_generation": "OPEN_W6",
        },
        "next_wave": "C03_CLUSTER_EMBEDDING_W3_AUTHORITY_RECONCILIATION",
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    validate_w2_receipt(receipt)
    return receipt


def validate_w2_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema_version") != W2_RECEIPT_SCHEMA_VERSION:
        raise GraphEdgeSemanticHardeningError("W2 receipt schema is invalid")
    if receipt.get("status") != "PASS" or receipt.get("completion_marker") != (
        W2_COMPLETION_MARKER
    ):
        raise GraphEdgeSemanticHardeningError("W2 completion truth is invalid")
    scope = receipt.get("scope")
    expected_scope = {
        "edge_assertions_semantically_specified": True,
        "edge_assertions_fully_reconciled": False,
        "edge_topology_changed": False,
        "graph_nodes_changed": False,
        "skill_rows_changed": False,
        "legacy_embedding_artifacts_changed": False,
        "replacement_vectors_generated": False,
        "production_promotion_authorized": False,
    }
    if not isinstance(scope, Mapping) or any(
        scope.get(field) is not expected for field, expected in expected_scope.items()
    ):
        raise GraphEdgeSemanticHardeningError("W2 scope claim is invalid")
    preservation = receipt.get("preservation")
    if not isinstance(preservation, Mapping) or not all(
        preservation.get(field) is True
        for field in (
            "edge_count_preserved",
            "edge_identity_set_preserved",
            "edge_topology_preserved",
            "legacy_edge_payload_preserved",
            "graph_nodes_preserved",
            "skill_rows_preserved",
        )
    ):
        raise GraphEdgeSemanticHardeningError("W2 preservation contract failed")
    after_profile = (receipt.get("after") or {}).get("edge_semantic_profile")
    if not isinstance(after_profile, Mapping):
        raise GraphEdgeSemanticHardeningError("W2 after profile is missing")
    for field in (
        "missing_canonical_assertion_count",
        "missing_assertion_basis_count",
        "generic_assertion_count",
        "semantic_issue_count",
    ):
        if after_profile.get(field) != 0:
            raise GraphEdgeSemanticHardeningError(
                f"W2 semantic exit gate failed: {field}={after_profile.get(field)}"
            )
    legacy = receipt.get("legacy_embedding_artifacts")
    if not isinstance(legacy, Mapping) or legacy.get("artifact_count") != 13:
        raise GraphEdgeSemanticHardeningError(
            "W2 legacy artifact inventory is incomplete"
        )
    unsigned = dict(receipt)
    recorded = str(unsigned.pop("receipt_sha256", "") or "")
    observed = canonical_sha256(unsigned)
    if not recorded or recorded != observed:
        raise GraphEdgeSemanticHardeningError(
            f"W2 receipt digest mismatch: expected {observed}, observed {recorded}"
        )


__all__ = [
    "BASIS_KIND_BY_EDGE_TYPE",
    "EDGE_SEMANTIC_CONTRACT_VERSION",
    "EDGE_SEMANTIC_HARDENING_WAVE",
    "GraphEdgeSemanticHardeningError",
    "W2_COMPLETION_MARKER",
    "W2_RECEIPT_SCHEMA_VERSION",
    "build_w2_receipt",
    "collect_graph_edge_semantic_issues",
    "edge_semantic_profile",
    "harden_graph_edge_semantics",
    "validate_edge_semantic_contract",
    "validate_w2_receipt",
]
