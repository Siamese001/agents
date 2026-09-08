"""Deterministic Wave 4 registry for C0.3 graph-evidence clusters.

Wave 4 chooses the semantic retrieval grain.  It materializes only multi-node
clusters that already satisfy current graph authority and keeps rejected
groupings on a separate, non-embeddable audit surface.  It does not create
vectors, retire legacy artifacts, or authorize production use.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

REGISTRY_SCHEMA_VERSION = "apps_rg.c03_graph_evidence_cluster_registry.v1"
RECEIPT_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_w4_receipt.v1"
COMPLETION_MARKER = "C03_CLUSTER_EMBEDDING_W4_REGISTRY_MATERIALIZED"
CONTRACT_PATH = Path(
    "src/apps_rg/fact_inventory/" "c03_graph_evidence_cluster_registry_contract.v1.json"
)
GRAPH_PATH = Path("src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json")
W3_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave3_authority_reconciliation_receipt.json"
)
CANDIDATE_FACT_LEDGER_PATH = Path(
    "artifacts/apps_rg/fact_inventory/"
    "master_candidate_skills_fact_ledger_20260518T1100Z.json"
)
ROLE_EPISODE_BUNDLE_PATHS = (
    Path("src/apps_rg/fact_inventory/ey_role_episode_bundles.json"),
    Path("src/apps_rg/fact_inventory/ibm_role_episode_bundles.json"),
    Path("src/apps_rg/fact_inventory/insurtech_role_episode_bundles.json"),
    Path("src/apps_rg/fact_inventory/unify_role_episode_bundles.json"),
)
LEGACY_ARTIFACT_DIR = Path("artifacts/apps_rg/c03/graph_skill_embeddings")
REGISTRY_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "graph_evidence_cluster_registry.v1.json"
)
W4_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave4_cluster_registry_receipt.json"
)

_RETRIEVABLE_STATES = frozenset({"ACTIVE", "ACTIVE_CONFIRMED"})
_ACTIVE_EDGE_LIFECYCLE = "ACTIVE_POLICY_GATED"
_EXTERNAL_CLAIM_POLICY = "graph_ids_only_current_authority_rehydration_required"
_REQUIRED_CLUSTER_FIELDS = frozenset(
    {
        "cluster_id",
        "cluster_kind",
        "canonical_embedding_text",
        "member_node_ids",
        "member_edge_ids",
        "linked_fact_ids",
        "linked_metric_ids",
        "allowed_sections",
        "activation_status",
        "external_claim_policy",
        "authority_envelope_sha256",
    }
)


class ClusterRegistryWave4Error(ValueError):
    """Raised when a Wave 4 contract, registry, or receipt is invalid."""


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.replace("_", " ")


def _humanize(value: Any) -> str:
    text = _clean_text(value)
    for prefix in ("epoch ", "domain ", "pillar ", "skill ", "fact "):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().title()


def _stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{canonical_sha256(value)[:16]}"


def _active_rows(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["skill_id"]): dict(row)
        for row in graph.get("skill_rows") or []
        if isinstance(row, Mapping)
        and row.get("retrieval_eligible") is True
        and row.get("activation_status") in _RETRIEVABLE_STATES
    }


def _active_edges(
    graph: Mapping[str, Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in graph.get("graph_edges") or []:
        if not isinstance(edge, Mapping):
            continue
        if edge.get("validation_status") != "validated":
            continue
        if edge.get("edge_semantic_status") != "HARDENED":
            continue
        if edge.get("lifecycle_disposition") != _ACTIVE_EDGE_LIFECYCLE:
            continue
        signature = (
            str(edge.get("edge_type") or ""),
            str(edge.get("source_node_id") or ""),
            str(edge.get("target_node_id") or ""),
        )
        result[signature] = dict(edge)
    return result


def _all_edges_by_id(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(edge["edge_id"]): dict(edge)
        for edge in graph.get("graph_edges") or []
        if isinstance(edge, Mapping) and edge.get("edge_id")
    }


def _graph_nodes(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(node["node_id"]): dict(node)
        for node in graph.get("graph_nodes") or []
        if isinstance(node, Mapping) and node.get("node_id")
    }


def validate_registry_contract(contract: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if contract.get("schema_version") != (
        "apps_rg.c03_graph_evidence_cluster_registry_contract.v1"
    ):
        issues.append("schema_version")
    if contract.get("wave") != "W4" or contract.get("status") != "FROZEN":
        issues.append("wave_or_status")
    required_true = (
        ("source_authority", "graph_ids_remain_only_claim_authority"),
        ("role_episode_materialization", "largest_compatible_section_cohort_selected"),
        ("role_episode_materialization", "stable_lexical_tie_break_required"),
        ("capability_evidence_materialization", "singleton_embedding_forbidden"),
        ("capability_evidence_materialization", "oversize_arbitrary_split_forbidden"),
        ("registry_shape", "held_candidates_separate_from_clusters"),
        ("registry_shape", "held_candidates_have_no_canonical_embedding_text"),
        ("registry_shape", "one_future_vector_per_active_cluster"),
        ("semantic_text", "raw_ids_forbidden"),
        ("wave4_acceptance", "canonical_graph_must_remain_unchanged"),
        ("wave4_acceptance", "legacy_embedding_artifacts_must_remain_unchanged"),
    )
    for section, field in required_true:
        if (contract.get(section) or {}).get(field) is not True:
            issues.append(f"{section}.{field}")
    acceptance = contract.get("wave4_acceptance") or {}
    for field in (
        "replacement_vector_generation_authorized",
        "legacy_artifact_deletion_authorized",
        "production_promotion_authorized",
    ):
        if acceptance.get(field) is not False:
            issues.append(f"wave4_acceptance.{field}")
    if issues:
        raise ClusterRegistryWave4Error(
            f"Invalid Wave 4 registry contract fields: {sorted(issues)}"
        )


def _bundle_candidates(
    rows: Mapping[str, dict[str, Any]],
    bundles_by_path: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source_path in sorted(bundles_by_path):
        payload = bundles_by_path[source_path]
        for raw_bundle in payload.get("bundles") or []:
            if not isinstance(raw_bundle, Mapping):
                continue
            bundle = dict(raw_bundle)
            eligible = sorted(
                skill_id
                for skill_id in _strings(bundle.get("graph_skill_node_ids"))
                if skill_id in rows
            )
            bundle_sections = sorted(set(_strings(bundle.get("section_eligibility"))))
            cohorts = {
                section: sorted(
                    skill_id
                    for skill_id in eligible
                    if section in _strings(rows[skill_id].get("allowed_sections"))
                )
                for section in bundle_sections
            }
            selected_section = (
                min(cohorts, key=lambda item: (-len(cohorts[item]), item))
                if cohorts
                else None
            )
            selected = cohorts.get(selected_section, []) if selected_section else []
            common_sections = set(bundle_sections)
            for skill_id in selected:
                common_sections &= set(_strings(rows[skill_id].get("allowed_sections")))
            facts = sorted(set(_strings(bundle.get("linked_source_fact_ids"))))
            reasons: list[str] = []
            if not facts:
                reasons.append("NO_LINKED_SOURCE_FACT")
            if len(selected) < 2:
                reasons.append("INSUFFICIENT_COMPATIBLE_MEMBERS")
            if not common_sections:
                reasons.append("NO_COMMON_ALLOWED_SECTION")
            candidates.append(
                {
                    "candidate_id": f"candidate_role_{bundle.get('role_episode_bundle_id')}",
                    "candidate_kind": "role_episode",
                    "source_path": source_path,
                    "role_episode_bundle_id": str(
                        bundle.get("role_episode_bundle_id") or ""
                    ),
                    "bundle": bundle,
                    "candidate_member_node_ids": selected,
                    "excluded_member_node_ids": sorted(
                        set(_strings(bundle.get("graph_skill_node_ids")))
                        - set(selected)
                    ),
                    "candidate_allowed_sections": sorted(common_sections),
                    "linked_fact_ids": facts,
                    "linked_metric_ids": sorted(
                        set(_strings(bundle.get("linked_metric_outcome_ids")))
                    ),
                    "hold_reasons": reasons,
                }
            )
    return sorted(candidates, key=lambda item: item["candidate_id"])


def _fact_edge_ids_for_member(
    skill_id: str,
    row: Mapping[str, Any],
    edge_by_signature: Mapping[tuple[str, str, str], dict[str, Any]],
    *,
    restrict_to: set[str] | None = None,
) -> list[str]:
    result = []
    for fact_id in sorted(set(_strings(row.get("fact_id_links")))):
        if restrict_to is not None and fact_id not in restrict_to:
            continue
        edge = edge_by_signature.get(("skill_supported_by_fact", skill_id, fact_id))
        if edge:
            result.append(str(edge["edge_id"]))
    return result


def _member_authority(
    skill_id: str,
    row: Mapping[str, Any],
    allowed_sections: Sequence[str],
    edge_by_signature: Mapping[tuple[str, str, str], dict[str, Any]],
    *,
    restrict_facts_to: set[str] | None = None,
) -> dict[str, Any]:
    fact_edges = _fact_edge_ids_for_member(
        skill_id, row, edge_by_signature, restrict_to=restrict_facts_to
    )
    section_edges: list[str] = []
    for section in sorted(set(allowed_sections)):
        edge = edge_by_signature.get(
            ("skill_allowed_in_section", skill_id, f"section_{section}")
        )
        if edge:
            section_edges.append(str(edge["edge_id"]))
    policy_edge = edge_by_signature.get(
        ("skill_external_claim_eligible", skill_id, "policy_external_claim_policy")
    )
    return {
        "node_id": skill_id,
        "fact_edge_ids": fact_edges,
        "section_edge_ids": section_edges,
        "policy_edge_id": str(policy_edge["edge_id"]) if policy_edge else "",
    }


def _capability_phrase(row: Mapping[str, Any]) -> str:
    phrases = [_clean_text(item) for item in _strings(row.get("allowed_phrases"))]
    phrases = [item for item in phrases if item]
    if phrases:
        return phrases[0]
    for field in ("capability", "domain", "subpillar"):
        if row.get(field):
            return _humanize(row[field])
    return _humanize(row.get("skill_id"))


def _render_semantic_text(components: Mapping[str, Any]) -> str:
    capabilities = "; ".join(_strings(components.get("concrete_capabilities")))
    evidence = " ".join(_strings(components.get("approved_evidence_summaries")))
    return " ".join(
        (
            f"Action: {_clean_text(components.get('claim_action'))}",
            f"Scope: {_clean_text(components.get('claim_scope'))}",
            f"Outcome: {_clean_text(components.get('claim_outcome'))}",
            f"Operating context: {_clean_text(components.get('operating_context'))}",
            f"Capabilities: {capabilities}",
            f"Evidence: {evidence}",
        )
    ).strip()


def _role_semantic_components(
    bundle: Mapping[str, Any],
    member_ids: Sequence[str],
    rows: Mapping[str, dict[str, Any]],
    bundle_file: Mapping[str, Any],
) -> dict[str, Any]:
    metric_nodes = bundle_file.get("metric_outcome_nodes") or {}
    evidence_summaries: list[str] = []
    if isinstance(metric_nodes, Mapping):
        for metric_id in sorted(set(_strings(bundle.get("linked_metric_outcome_ids")))):
            metric = metric_nodes.get(metric_id)
            if isinstance(metric, Mapping) and metric.get("claim_text"):
                evidence_summaries.append(_clean_text(metric["claim_text"]))
    if not evidence_summaries:
        evidence_summaries = [_clean_text(bundle.get("claim_text"))]
    claim = _clean_text(bundle.get("claim_text") or bundle.get("claim_action"))
    return {
        "claim_action": _clean_text(bundle.get("claim_action") or claim),
        "claim_scope": _clean_text(
            bundle.get("claim_scope") or bundle.get("bundle_theme")
        ),
        "claim_outcome": claim,
        "operating_context": _clean_text(
            bundle.get("operating_context") or bundle.get("claim_scope")
        ),
        "concrete_capabilities": sorted(
            {_capability_phrase(rows[skill_id]) for skill_id in member_ids}
        ),
        "approved_evidence_summaries": evidence_summaries[:3],
    }


def _fact_records(
    candidate_fact_ledger: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        str(item["candidate_fact_id"]): dict(item)
        for item in candidate_fact_ledger.get("candidate_facts") or []
        if isinstance(item, Mapping) and item.get("candidate_fact_id")
    }


def _capability_semantic_components(
    fact_id: str,
    member_ids: Sequence[str],
    rows: Mapping[str, dict[str, Any]],
    facts: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    fact = facts.get(fact_id, {})
    first = rows[member_ids[0]]
    claim = _clean_text(fact.get("claim_text"))
    proof = _clean_text(fact.get("proof_text"))
    if not claim:
        snippets = [
            _clean_text(item)
            for skill_id in member_ids
            for item in _strings(rows[skill_id].get("source_snippets"))
        ]
        claim = next(
            (item for item in snippets if item), "Evidence-backed capability group"
        )
    if not proof:
        proof = claim
    domain = _humanize(
        first.get("domain") or first.get("domain_id") or first.get("pillar")
    )
    epoch = _humanize(first.get("career_epoch") or first.get("career_stage"))
    company = _clean_text(fact.get("company"))
    context_parts = [item for item in (company, domain, epoch) if item]
    return {
        "claim_action": claim,
        "claim_scope": f"Evidence scope: {domain} capabilities in the {epoch} context.",
        "claim_outcome": proof,
        "operating_context": ", ".join(context_parts),
        "concrete_capabilities": sorted(
            {_capability_phrase(rows[skill_id]) for skill_id in member_ids}
        ),
        "approved_evidence_summaries": [proof],
    }


def _authority_envelope(
    *,
    graph: Mapping[str, Any],
    cluster_kind: str,
    root_authority: Mapping[str, Any],
    member_ids: Sequence[str],
    member_authorities: Sequence[Mapping[str, Any]],
    member_edge_ids: Sequence[str],
    linked_fact_ids: Sequence[str],
    linked_metric_ids: Sequence[str],
    allowed_sections: Sequence[str],
) -> dict[str, Any]:
    nodes = _graph_nodes(graph)
    rows = {str(row["skill_id"]): dict(row) for row in graph.get("skill_rows") or []}
    edges = _all_edges_by_id(graph)
    member_records = []
    authority_by_member = {str(item["node_id"]): item for item in member_authorities}
    for skill_id in member_ids:
        authority = authority_by_member[skill_id]
        member_records.append(
            {
                "node_id": skill_id,
                "graph_node_sha256": canonical_sha256(nodes[skill_id]),
                "skill_row_sha256": canonical_sha256(rows[skill_id]),
                "fact_edge_ids": list(authority["fact_edge_ids"]),
                "section_edge_ids": list(authority["section_edge_ids"]),
                "policy_edge_id": authority["policy_edge_id"],
            }
        )
    return {
        "canonical_graph_sha256": canonical_sha256(graph),
        "cluster_kind": cluster_kind,
        "root_authority": dict(root_authority),
        "members": member_records,
        "member_edges": [
            {
                "edge_id": edge_id,
                "canonical_sha256": canonical_sha256(edges[edge_id]),
            }
            for edge_id in sorted(member_edge_ids)
        ],
        "linked_fact_ids": sorted(linked_fact_ids),
        "linked_metric_ids": sorted(linked_metric_ids),
        "allowed_sections": sorted(allowed_sections),
        "external_claim_policy": _EXTERNAL_CLAIM_POLICY,
    }


def _active_role_clusters(
    graph: Mapping[str, Any],
    rows: Mapping[str, dict[str, Any]],
    bundle_candidates: Sequence[dict[str, Any]],
    bundles_by_path: Mapping[str, Mapping[str, Any]],
    source_records: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edge_by_signature = _active_edges(graph)
    clusters: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    for candidate in bundle_candidates:
        if candidate["hold_reasons"]:
            held.append(
                {key: value for key, value in candidate.items() if key != "bundle"}
            )
            continue
        bundle = candidate["bundle"]
        members = candidate["candidate_member_node_ids"]
        sections = candidate["candidate_allowed_sections"]
        authorities = [
            _member_authority(skill_id, rows[skill_id], sections, edge_by_signature)
            for skill_id in members
        ]
        authority_issues = []
        for item in authorities:
            if not item["fact_edge_ids"]:
                authority_issues.append(f"{item['node_id']}:MISSING_FACT_EDGE")
            if len(item["section_edge_ids"]) != len(sections):
                authority_issues.append(f"{item['node_id']}:MISSING_SECTION_EDGE")
            if not item["policy_edge_id"]:
                authority_issues.append(f"{item['node_id']}:MISSING_POLICY_EDGE")
        if authority_issues:
            held.append(
                {key: value for key, value in candidate.items() if key != "bundle"}
                | {"hold_reasons": sorted(authority_issues)}
            )
            continue
        edge_ids = sorted(
            {
                edge_id
                for item in authorities
                for edge_id in (
                    list(item["fact_edge_ids"])
                    + list(item["section_edge_ids"])
                    + [item["policy_edge_id"]]
                )
            }
        )
        linked_facts = sorted(
            set(candidate["linked_fact_ids"])
            | {
                fact_id
                for skill_id in members
                for fact_id in _strings(rows[skill_id].get("fact_id_links"))
                if ("skill_supported_by_fact", skill_id, fact_id) in edge_by_signature
            }
        )
        components = _role_semantic_components(
            bundle,
            members,
            rows,
            bundles_by_path[candidate["source_path"]],
        )
        root_authority = {
            "kind": "role_episode_bundle",
            "role_episode_bundle_id": candidate["role_episode_bundle_id"],
            "source_path": candidate["source_path"],
            "source_file_sha256": source_records[candidate["source_path"]][
                "file_sha256"
            ],
        }
        envelope = _authority_envelope(
            graph=graph,
            cluster_kind="role_episode",
            root_authority=root_authority,
            member_ids=members,
            member_authorities=authorities,
            member_edge_ids=edge_ids,
            linked_fact_ids=linked_facts,
            linked_metric_ids=candidate["linked_metric_ids"],
            allowed_sections=sections,
        )
        cluster = {
            "cluster_id": f"cluster_role_{candidate['role_episode_bundle_id']}",
            "cluster_kind": "role_episode",
            "role_episode_bundle_id": candidate["role_episode_bundle_id"],
            "canonical_embedding_text": _render_semantic_text(components),
            "semantic_components": components,
            "member_node_ids": members,
            "member_edge_ids": edge_ids,
            "linked_fact_ids": linked_facts,
            "linked_metric_ids": candidate["linked_metric_ids"],
            "allowed_sections": sections,
            "activation_status": "ACTIVE_CONFIRMED",
            "external_claim_policy": _EXTERNAL_CLAIM_POLICY,
            "authority_envelope": envelope,
            "authority_envelope_sha256": canonical_sha256(envelope),
            "future_vector_count": 1,
            "excluded_candidate_member_ids": candidate["excluded_member_node_ids"],
            "member_limit_exception": (
                "PRIMARY_ROLE_EPISODE_ROOT_NOT_SECONDARY_CLUSTER_NO_FACETING"
                if len(members) > 8
                else None
            ),
        }
        clusters.append(cluster)
    return clusters, held


def _primary_fact(
    skill_id: str,
    row: Mapping[str, Any],
    edge_by_signature: Mapping[tuple[str, str, str], dict[str, Any]],
) -> str | None:
    linked = sorted(
        fact_id
        for fact_id in set(_strings(row.get("fact_id_links")))
        if ("skill_supported_by_fact", skill_id, fact_id) in edge_by_signature
    )
    preferred = row.get("source_ledger_ref")
    if isinstance(preferred, str) and preferred in linked:
        return preferred
    return linked[0] if linked else None


def _capability_candidates(
    rows: Mapping[str, dict[str, Any]],
    active_role_clusters: Sequence[Mapping[str, Any]],
    edge_by_signature: Mapping[tuple[str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    covered = {
        skill_id
        for cluster in active_role_clusters
        for skill_id in _strings(cluster.get("member_node_ids"))
    }
    groups: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    missing: list[str] = []
    for skill_id in sorted(set(rows) - covered):
        row = rows[skill_id]
        fact_id = _primary_fact(skill_id, row, edge_by_signature)
        if not fact_id:
            missing.append(skill_id)
            continue
        key = (
            fact_id,
            str(row.get("career_epoch") or row.get("career_stage") or ""),
            str(row.get("domain_id") or row.get("pillar") or ""),
            tuple(sorted(set(_strings(row.get("allowed_sections"))))),
        )
        groups[key].append(skill_id)
    candidates: list[dict[str, Any]] = []
    for key, member_ids in sorted(groups.items()):
        fact_id, career_context, domain_context, sections = key
        members = sorted(member_ids)
        reasons = []
        if len(members) == 1:
            reasons.append("SINGLETON_NOT_EMBEDDABLE")
        if len(members) > 8:
            reasons.append("MEMBER_LIMIT_REQUIRES_QREL_FACET_DECISION")
        signature = {
            "primary_fact_id": fact_id,
            "career_context_id": career_context,
            "domain_context_id": domain_context,
            "allowed_sections": list(sections),
        }
        candidates.append(
            {
                "candidate_id": _stable_id("candidate_capability", signature),
                "candidate_kind": "capability_evidence",
                "candidate_member_node_ids": members,
                "candidate_allowed_sections": list(sections),
                "primary_evidence_anchor_id": fact_id,
                "career_context_id": career_context,
                "domain_context_id": domain_context,
                "hold_reasons": reasons,
            }
        )
    for skill_id in missing:
        candidates.append(
            {
                "candidate_id": _stable_id(
                    "candidate_capability", {"skill_id": skill_id}
                ),
                "candidate_kind": "capability_evidence",
                "candidate_member_node_ids": [skill_id],
                "candidate_allowed_sections": sorted(
                    set(_strings(rows[skill_id].get("allowed_sections")))
                ),
                "primary_evidence_anchor_id": None,
                "career_context_id": str(
                    rows[skill_id].get("career_epoch")
                    or rows[skill_id].get("career_stage")
                    or ""
                ),
                "domain_context_id": str(
                    rows[skill_id].get("domain_id")
                    or rows[skill_id].get("pillar")
                    or ""
                ),
                "hold_reasons": ["NO_HARDENED_SHARED_FACT_EDGE"],
            }
        )
    return sorted(candidates, key=lambda item: item["candidate_id"])


def _active_capability_clusters(
    graph: Mapping[str, Any],
    rows: Mapping[str, dict[str, Any]],
    candidates: Sequence[dict[str, Any]],
    candidate_fact_ledger: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edge_by_signature = _active_edges(graph)
    facts = _fact_records(candidate_fact_ledger)
    clusters: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate["hold_reasons"]:
            held.append(dict(candidate))
            continue
        members = candidate["candidate_member_node_ids"]
        sections = candidate["candidate_allowed_sections"]
        fact_id = str(candidate["primary_evidence_anchor_id"])
        authorities = [
            _member_authority(
                skill_id,
                rows[skill_id],
                sections,
                edge_by_signature,
                restrict_facts_to={fact_id},
            )
            for skill_id in members
        ]
        authority_issues = []
        for item in authorities:
            if len(item["fact_edge_ids"]) != 1:
                authority_issues.append(f"{item['node_id']}:MISSING_SHARED_FACT_EDGE")
            if len(item["section_edge_ids"]) != len(sections):
                authority_issues.append(f"{item['node_id']}:MISSING_SECTION_EDGE")
            if not item["policy_edge_id"]:
                authority_issues.append(f"{item['node_id']}:MISSING_POLICY_EDGE")
        if authority_issues:
            held.append(dict(candidate) | {"hold_reasons": sorted(authority_issues)})
            continue
        edge_ids = sorted(
            {
                edge_id
                for item in authorities
                for edge_id in (
                    list(item["fact_edge_ids"])
                    + list(item["section_edge_ids"])
                    + [item["policy_edge_id"]]
                )
            }
        )
        components = _capability_semantic_components(fact_id, members, rows, facts)
        root_authority = {
            "kind": "hardened_shared_fact_edge",
            "primary_evidence_anchor_id": fact_id,
        }
        envelope = _authority_envelope(
            graph=graph,
            cluster_kind="capability_evidence",
            root_authority=root_authority,
            member_ids=members,
            member_authorities=authorities,
            member_edge_ids=edge_ids,
            linked_fact_ids=[fact_id],
            linked_metric_ids=[],
            allowed_sections=sections,
        )
        signature = {
            "primary_fact_id": fact_id,
            "career_context_id": candidate["career_context_id"],
            "domain_context_id": candidate["domain_context_id"],
            "allowed_sections": sections,
        }
        clusters.append(
            {
                "cluster_id": _stable_id("cluster_capability", signature),
                "cluster_kind": "capability_evidence",
                "primary_evidence_anchor_id": fact_id,
                "career_context_id": candidate["career_context_id"],
                "domain_context_id": candidate["domain_context_id"],
                "canonical_embedding_text": _render_semantic_text(components),
                "semantic_components": components,
                "member_node_ids": members,
                "member_edge_ids": edge_ids,
                "linked_fact_ids": [fact_id],
                "linked_metric_ids": [],
                "allowed_sections": sections,
                "activation_status": "ACTIVE_CONFIRMED",
                "external_claim_policy": _EXTERNAL_CLAIM_POLICY,
                "authority_envelope": envelope,
                "authority_envelope_sha256": canonical_sha256(envelope),
                "future_vector_count": 1,
                "member_limit_exception": None,
            }
        )
    return clusters, held


def registry_profile(registry: Mapping[str, Any]) -> dict[str, Any]:
    clusters = [dict(item) for item in registry.get("clusters") or []]
    held = [dict(item) for item in registry.get("held_candidates") or []]
    active_memberships = [
        skill_id
        for cluster in clusters
        for skill_id in _strings(cluster.get("member_node_ids"))
    ]
    membership_clusters: dict[str, list[str]] = defaultdict(list)
    for cluster in clusters:
        for skill_id in _strings(cluster.get("member_node_ids")):
            membership_clusters[skill_id].append(str(cluster["cluster_id"]))
    role_clusters = [
        item for item in clusters if item.get("cluster_kind") == "role_episode"
    ]
    capability_clusters = [
        item for item in clusters if item.get("cluster_kind") == "capability_evidence"
    ]
    role_held = [item for item in held if item.get("candidate_kind") == "role_episode"]
    capability_held = [
        item for item in held if item.get("candidate_kind") == "capability_evidence"
    ]
    reason_counts = Counter(
        reason for item in held for reason in _strings(item.get("hold_reasons"))
    )
    return {
        "materialized_cluster_count": len(clusters),
        "role_episode_cluster_count": len(role_clusters),
        "capability_evidence_cluster_count": len(capability_clusters),
        "future_vector_count": sum(
            int(item.get("future_vector_count") or 0) for item in clusters
        ),
        "held_candidate_count": len(held),
        "held_role_episode_candidate_count": len(role_held),
        "held_capability_candidate_count": len(capability_held),
        "active_member_membership_count": len(active_memberships),
        "active_unique_member_count": len(set(active_memberships)),
        "overlapping_active_member_count": sum(
            len(cluster_ids) > 1 for cluster_ids in membership_clusters.values()
        ),
        "maximum_active_memberships_per_skill": max(
            (len(cluster_ids) for cluster_ids in membership_clusters.values()),
            default=0,
        ),
        "cluster_size_counts": {
            str(size): count
            for size, count in sorted(
                Counter(
                    len(_strings(item.get("member_node_ids"))) for item in clusters
                ).items()
            )
        },
        "held_reason_counts": dict(sorted(reason_counts.items())),
    }


def materialize_cluster_registry(
    *,
    graph: Mapping[str, Any],
    bundles_by_path: Mapping[str, Mapping[str, Any]],
    candidate_fact_ledger: Mapping[str, Any],
    source_records: Mapping[str, Mapping[str, Any]],
    w3_receipt: Mapping[str, Any],
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    rows = _active_rows(graph)
    role_candidates = _bundle_candidates(rows, bundles_by_path)
    role_clusters, held_roles = _active_role_clusters(
        graph, rows, role_candidates, bundles_by_path, source_records
    )
    capability_candidates = _capability_candidates(
        rows, role_clusters, _active_edges(graph)
    )
    capability_clusters, held_capabilities = _active_capability_clusters(
        graph, rows, capability_candidates, candidate_fact_ledger
    )
    clusters = sorted(
        role_clusters + capability_clusters, key=lambda item: item["cluster_id"]
    )
    held = sorted(held_roles + held_capabilities, key=lambda item: item["candidate_id"])
    registry: dict[str, Any] = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "wave_id": "C03_CLUSTER_EMBEDDING_W4",
        "status": "MATERIALIZED_NOT_EMBEDDED",
        "completion_marker": COMPLETION_MARKER,
        "source_authority": {
            "commit": source_commit,
            "tree": source_tree,
            "canonical_graph_sha256": canonical_sha256(graph),
            "wave3_receipt_sha256": w3_receipt.get("receipt_sha256"),
            "inputs": [dict(source_records[path]) for path in sorted(source_records)],
        },
        "materialization_policy": {
            "logical_retrieval_unit": "graph_evidence_cluster",
            "active_clusters_only_in_clusters": True,
            "held_candidates_are_not_embeddable": True,
            "one_future_vector_per_cluster": True,
            "per_node_vector_default_forbidden": True,
            "facet_vectors_require_qrel_improvement": True,
            "current_graph_id_rehydration_required": True,
        },
        "clusters": clusters,
        "held_candidates": held,
        "eligible_skill_audit": {
            "retrieval_eligible_skill_count": len(rows),
            "active_unique_member_count": len(
                {
                    skill_id
                    for cluster in clusters
                    for skill_id in cluster["member_node_ids"]
                }
            ),
            "held_unembedded_skill_ids": sorted(
                set(rows)
                - {
                    skill_id
                    for cluster in clusters
                    for skill_id in cluster["member_node_ids"]
                }
            ),
        },
        "scope_guards": {
            "replacement_vectors_generated": False,
            "legacy_embedding_artifacts_changed": False,
            "legacy_artifact_deletion_authorized": False,
            "production_promotion_authorized": False,
        },
    }
    registry["profile"] = registry_profile(registry)
    registry["registry_sha256"] = canonical_sha256(registry)
    return registry


def collect_registry_issues(
    registry: Mapping[str, Any],
    *,
    graph: Mapping[str, Any] | None = None,
) -> list[str]:
    issues: list[str] = []
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        issues.append("REGISTRY_SCHEMA_VERSION")
    if registry.get("status") != "MATERIALIZED_NOT_EMBEDDED":
        issues.append("REGISTRY_STATUS")
    if registry.get("completion_marker") != COMPLETION_MARKER:
        issues.append("REGISTRY_COMPLETION_MARKER")
    clusters = registry.get("clusters") or []
    held = registry.get("held_candidates") or []
    cluster_ids: list[str] = []
    graph_edges = _all_edges_by_id(graph) if graph is not None else {}
    graph_rows = _active_rows(graph) if graph is not None else {}
    for index, raw_cluster in enumerate(clusters):
        if not isinstance(raw_cluster, Mapping):
            issues.append(f"REGISTRY_CLUSTER_NOT_OBJECT:{index}")
            continue
        cluster = raw_cluster
        cluster_id = str(cluster.get("cluster_id") or "")
        cluster_ids.append(cluster_id)
        missing = sorted(_REQUIRED_CLUSTER_FIELDS - set(cluster))
        if missing:
            issues.append(f"REGISTRY_CLUSTER_REQUIRED_FIELDS:{cluster_id}:{missing}")
        if cluster.get("activation_status") != "ACTIVE_CONFIRMED":
            issues.append(f"REGISTRY_CLUSTER_NOT_ACTIVE_CONFIRMED:{cluster_id}")
        members = _strings(cluster.get("member_node_ids"))
        if len(members) < 2:
            issues.append(f"REGISTRY_PER_NODE_OR_EMPTY_CLUSTER:{cluster_id}")
        if cluster.get("cluster_kind") == "capability_evidence" and len(members) > 8:
            issues.append(f"REGISTRY_CAPABILITY_MEMBER_LIMIT:{cluster_id}")
        if (
            cluster.get("cluster_kind") == "role_episode"
            and len(members) > 8
            and cluster.get("member_limit_exception")
            != "PRIMARY_ROLE_EPISODE_ROOT_NOT_SECONDARY_CLUSTER_NO_FACETING"
        ):
            issues.append(f"REGISTRY_ROLE_MEMBER_EXCEPTION_MISSING:{cluster_id}")
        components = cluster.get("semantic_components") or {}
        for field in (
            "claim_action",
            "claim_scope",
            "claim_outcome",
            "operating_context",
            "concrete_capabilities",
            "approved_evidence_summaries",
        ):
            if not components.get(field):
                issues.append(
                    f"REGISTRY_SEMANTIC_COMPONENT_MISSING:{cluster_id}:{field}"
                )
        expected_text = _render_semantic_text(components)
        if cluster.get("canonical_embedding_text") != expected_text:
            issues.append(f"REGISTRY_CANONICAL_TEXT_DRIFT:{cluster_id}")
        text_lower = str(cluster.get("canonical_embedding_text") or "").lower()
        forbidden = (
            [cluster_id]
            + members
            + _strings(cluster.get("linked_fact_ids"))
            + _strings(cluster.get("linked_metric_ids"))
            + _strings(cluster.get("allowed_sections"))
            + [str(cluster.get("authority_envelope_sha256") or "")]
        )
        leaked = sorted(
            {item for item in forbidden if item and item.lower() in text_lower}
        )
        if leaked:
            issues.append(f"REGISTRY_RAW_AUTHORITY_LEAK:{cluster_id}:{leaked}")
        envelope = cluster.get("authority_envelope")
        if not isinstance(envelope, Mapping) or canonical_sha256(
            envelope
        ) != cluster.get("authority_envelope_sha256"):
            issues.append(f"REGISTRY_AUTHORITY_ENVELOPE_DIGEST:{cluster_id}")
        if cluster.get("future_vector_count") != 1:
            issues.append(f"REGISTRY_FUTURE_VECTOR_COUNT:{cluster_id}")
        if graph is not None:
            edge_ids = set(_strings(cluster.get("member_edge_ids")))
            for edge_id in edge_ids:
                edge = graph_edges.get(edge_id)
                if (
                    not edge
                    or edge.get("validation_status") != "validated"
                    or edge.get("edge_semantic_status") != "HARDENED"
                    or edge.get("lifecycle_disposition") != _ACTIVE_EDGE_LIFECYCLE
                ):
                    issues.append(
                        f"REGISTRY_MEMBER_EDGE_NOT_ACTIVE_HARDENED:{cluster_id}:{edge_id}"
                    )
            for skill_id in members:
                if skill_id not in graph_rows:
                    issues.append(
                        f"REGISTRY_MEMBER_NOT_RETRIEVAL_ELIGIBLE:{cluster_id}:{skill_id}"
                    )
                    continue
                member_edges = [
                    graph_edges[item] for item in edge_ids if item in graph_edges
                ]
                if not any(
                    edge.get("edge_type") == "skill_supported_by_fact"
                    and edge.get("source_node_id") == skill_id
                    for edge in member_edges
                ):
                    issues.append(
                        f"REGISTRY_MEMBER_FACT_EDGE_MISSING:{cluster_id}:{skill_id}"
                    )
                if not any(
                    edge.get("edge_type") == "skill_external_claim_eligible"
                    and edge.get("source_node_id") == skill_id
                    for edge in member_edges
                ):
                    issues.append(
                        f"REGISTRY_MEMBER_POLICY_EDGE_MISSING:{cluster_id}:{skill_id}"
                    )
                for section in _strings(cluster.get("allowed_sections")):
                    if not any(
                        edge.get("edge_type") == "skill_allowed_in_section"
                        and edge.get("source_node_id") == skill_id
                        and edge.get("target_node_id") == f"section_{section}"
                        for edge in member_edges
                    ):
                        issues.append(
                            f"REGISTRY_MEMBER_SECTION_EDGE_MISSING:{cluster_id}:{skill_id}:{section}"
                        )
    if len(cluster_ids) != len(set(cluster_ids)) or not all(cluster_ids):
        issues.append("REGISTRY_CLUSTER_ID_UNIQUENESS")
    for index, candidate in enumerate(held):
        if not isinstance(candidate, Mapping):
            issues.append(f"REGISTRY_HELD_NOT_OBJECT:{index}")
            continue
        candidate_id = candidate.get("candidate_id")
        if "canonical_embedding_text" in candidate:
            issues.append(f"REGISTRY_HELD_HAS_EMBEDDING_TEXT:{candidate_id}")
        if not _strings(candidate.get("hold_reasons")):
            issues.append(f"REGISTRY_HELD_REASON_MISSING:{candidate_id}")
    profile = registry_profile(registry)
    if registry.get("profile") != profile:
        issues.append("REGISTRY_PROFILE_DRIFT")
    eligible_audit = registry.get("eligible_skill_audit") or {}
    if graph is not None:
        active_members = {
            skill_id
            for cluster in clusters
            for skill_id in _strings(cluster.get("member_node_ids"))
        }
        expected_held = sorted(set(graph_rows) - active_members)
        if eligible_audit.get("retrieval_eligible_skill_count") != len(graph_rows):
            issues.append("REGISTRY_ELIGIBLE_SKILL_COUNT")
        if eligible_audit.get("active_unique_member_count") != len(active_members):
            issues.append("REGISTRY_ACTIVE_MEMBER_COUNT")
        if eligible_audit.get("held_unembedded_skill_ids") != expected_held:
            issues.append("REGISTRY_HELD_SKILL_AUDIT")
    guards = registry.get("scope_guards") or {}
    if any(
        guards.get(field) is not False
        for field in (
            "replacement_vectors_generated",
            "legacy_embedding_artifacts_changed",
            "legacy_artifact_deletion_authorized",
            "production_promotion_authorized",
        )
    ):
        issues.append("REGISTRY_SCOPE_GUARDS")
    digest_payload = dict(registry)
    supplied_digest = digest_payload.pop("registry_sha256", None)
    if canonical_sha256(digest_payload) != supplied_digest:
        issues.append("REGISTRY_DIGEST")
    return sorted(set(issues))


def validate_registry(
    registry: Mapping[str, Any], *, graph: Mapping[str, Any] | None = None
) -> None:
    issues = collect_registry_issues(registry, graph=graph)
    if issues:
        raise ClusterRegistryWave4Error(f"Invalid Wave 4 registry: {issues}")


def build_w4_receipt(
    *,
    registry: Mapping[str, Any],
    contract: Mapping[str, Any],
    graph: Mapping[str, Any],
    w3_receipt: Mapping[str, Any],
    legacy_artifacts: Sequence[Mapping[str, Any]],
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    profile = registry_profile(registry)
    eligible_count = int(
        (registry.get("eligible_skill_audit") or {}).get(
            "retrieval_eligible_skill_count", 0
        )
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "wave_id": "C03_CLUSTER_EMBEDDING_W4",
        "status": "PASS",
        "completion_marker": COMPLETION_MARKER,
        "source_baseline": {
            "commit": source_commit,
            "tree": source_tree,
            "wave3_receipt_sha256": w3_receipt.get("receipt_sha256"),
            "canonical_graph_sha256": canonical_sha256(graph),
        },
        "contract": {
            "path": CONTRACT_PATH.as_posix(),
            "schema_version": contract.get("schema_version"),
            "canonical_sha256": canonical_sha256(contract),
        },
        "registry": {
            "path": REGISTRY_PATH.as_posix(),
            "schema_version": registry.get("schema_version"),
            "canonical_sha256": registry.get("registry_sha256"),
            "profile": profile,
        },
        "coverage": {
            "retrieval_eligible_skill_count": eligible_count,
            "active_cluster_covered_skill_count": profile["active_unique_member_count"],
            "held_unembedded_skill_count": eligible_count
            - profile["active_unique_member_count"],
            "all_retrieval_eligible_skills_audited": True,
        },
        "scope": {
            "cluster_registry_materialized": True,
            "claim_authority_expanded": False,
            "canonical_graph_changed": False,
            "skill_rows_changed": False,
            "legacy_embedding_artifacts_changed": False,
            "replacement_vectors_generated": False,
            "legacy_artifact_deletion_authorized": False,
            "production_promotion_authorized": False,
        },
        "legacy_embedding_artifacts": {
            "status": "STALE_FAIL_CLOSED_UNCHANGED_PENDING_W5_RETIREMENT",
            "artifact_count": len(legacy_artifacts),
            "artifacts": [dict(item) for item in legacy_artifacts],
        },
        "wave_exit_gates": {
            "node_semantic_hardening": "PASS_W1",
            "edge_assertion_hardening": "PASS_W2",
            "authority_reconciliation": "PASS_W3",
            "cluster_registry_materialization": "PASS_W4",
            "legacy_artifact_retirement": "OPEN_W5",
            "cluster_embedding_generation": "BLOCKED_UNTIL_W5",
            "production_promotion": "NOT_AUTHORIZED",
        },
        "next_wave": "C03_CLUSTER_EMBEDDING_W5_LEGACY_ARTIFACT_RETIREMENT",
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def validate_w4_receipt(receipt: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        issues.append("schema_version")
    if (
        receipt.get("status") != "PASS"
        or receipt.get("completion_marker") != COMPLETION_MARKER
    ):
        issues.append("status_or_marker")
    scope = receipt.get("scope") or {}
    if scope.get("cluster_registry_materialized") is not True:
        issues.append("cluster_registry_materialized")
    for field in (
        "claim_authority_expanded",
        "canonical_graph_changed",
        "skill_rows_changed",
        "legacy_embedding_artifacts_changed",
        "replacement_vectors_generated",
        "legacy_artifact_deletion_authorized",
        "production_promotion_authorized",
    ):
        if scope.get(field) is not False:
            issues.append(f"scope.{field}")
    gates = receipt.get("wave_exit_gates") or {}
    if gates.get("cluster_registry_materialization") != "PASS_W4":
        issues.append("wave_exit_gates.cluster_registry_materialization")
    if gates.get("legacy_artifact_retirement") != "OPEN_W5":
        issues.append("wave_exit_gates.legacy_artifact_retirement")
    if gates.get("cluster_embedding_generation") != "BLOCKED_UNTIL_W5":
        issues.append("wave_exit_gates.cluster_embedding_generation")
    payload = dict(receipt)
    supplied = payload.pop("receipt_sha256", None)
    if canonical_sha256(payload) != supplied:
        issues.append("receipt_sha256")
    if issues:
        raise ClusterRegistryWave4Error(
            f"Invalid Wave 4 receipt fields: {sorted(issues)}"
        )
