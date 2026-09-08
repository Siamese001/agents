"""W1B derived multi-node clusters for full-resume owner-solo QREL review.

The frozen W4 registry remains unchanged.  This module derives review-only
Headline positioning and IBM role-episode clusters from existing runtime graph
packets, graph nodes, hardened edges, and source facts.  It never embeds a
single graph node, adds a fact, or writes source graph authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.evals.owner_solo.c03_full_resume_qrel_scope import (
    SCOPE_PATH,
    load_full_resume_scope,
    validate_full_resume_scope,
)
from apps_rg.fact_inventory.augmented_skills_graph import load_augmented_skills_graph
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (
    REGISTRY_PATH,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)
from apps_rg.runtime.sections.headline_positioning_evidence import (
    build_headline_positioning_section_packet,
)
from apps_rg.runtime.sections.ibm_role_episode_evidence import (
    build_ibm_role_episode_section_packet,
)


SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_derived_cluster_registry.v1"
STATUS = "W1B_DERIVED_CLUSTER_REGISTRY_READY_FOR_W1C"
FACT_LEDGER_PATH = Path(
    "artifacts/apps_rg/fact_inventory/"
    "master_candidate_skills_fact_ledger_20260518T1100Z.json"
)
HEADLINE_BUNDLE_SOURCE_PATH = Path(
    "src/apps_rg/runtime/sections/headline_positioning_registry.py"
)
IBM_BUNDLE_SOURCE_PATH = Path(
    "src/apps_rg/fact_inventory/ibm_role_episode_bundles.json"
)
RUNTIME_DIR = Path(".runtime/c03-owner-solo-qrel/w1b")
_ACTIVE_STATES = frozenset({"ACTIVE", "ACTIVE_CONFIRMED"})
_ACTIVE_EDGE_LIFECYCLE = "ACTIVE_POLICY_GATED"
_POLICY_TARGET = "policy_external_claim_policy"
_EXTERNAL_CLAIM_POLICY = "graph_ids_only_current_authority_rehydration_required"


class DerivedClusterError(ValueError):
    """Raised when W1B cannot preserve existing graph authority."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DerivedClusterError(f"JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise DerivedClusterError(f"JSON object required: {path}")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DerivedClusterError(f"File unavailable: {path}") from exc
    return digest.hexdigest()


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _active_rows(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["skill_id"]): dict(row)
        for row in graph.get("skill_rows") or []
        if isinstance(row, Mapping)
        and row.get("retrieval_eligible") is True
        and row.get("activation_status") in _ACTIVE_STATES
        and str(row.get("skill_id") or "")
    }


def _graph_nodes(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(node["node_id"]): dict(node)
        for node in graph.get("graph_nodes") or []
        if isinstance(node, Mapping) and str(node.get("node_id") or "")
    }


def _active_edges(graph: Mapping[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in graph.get("graph_edges") or []:
        if not isinstance(edge, Mapping):
            continue
        if (
            edge.get("validation_status") != "validated"
            or edge.get("edge_semantic_status") != "HARDENED"
            or edge.get("lifecycle_disposition") != _ACTIVE_EDGE_LIFECYCLE
        ):
            continue
        key = (
            str(edge.get("edge_type") or ""),
            str(edge.get("source_node_id") or ""),
            str(edge.get("target_node_id") or ""),
        )
        result[key] = dict(edge)
    return result


def _fact_records(ledger: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["candidate_fact_id"]): dict(row)
        for row in ledger.get("candidate_facts") or []
        if isinstance(row, Mapping) and str(row.get("candidate_fact_id") or "")
    }


def _active_member_edges(
    skill_id: str,
    row: Mapping[str, Any],
    edges: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> tuple[list[str], str]:
    fact_edge_ids = [
        str(edge["edge_id"])
        for fact_id in sorted({str(value) for value in row.get("fact_id_links") or []})
        if (edge := edges.get(("skill_supported_by_fact", skill_id, fact_id)))
    ]
    policy = edges.get(
        ("skill_external_claim_eligible", skill_id, _POLICY_TARGET)
    )
    return fact_edge_ids, str(policy.get("edge_id") or "") if policy else ""


def _phrases(rows: Mapping[str, Mapping[str, Any]], members: Sequence[str]) -> list[str]:
    result: list[str] = []
    for skill_id in members:
        phrases = rows[skill_id].get("allowed_phrases") or []
        phrase = next((_clean_text(value) for value in phrases if _clean_text(value)), "")
        if phrase and phrase not in result:
            result.append(phrase)
    return result[:6]


def _fact_evidence(facts: Mapping[str, Mapping[str, Any]], fact_ids: Sequence[str]) -> list[str]:
    result: list[str] = []
    for fact_id in fact_ids:
        fact = facts[fact_id]
        value = _clean_text(fact.get("proof_text") or fact.get("claim_text"))
        if value and value not in result:
            result.append(value)
    return result[:3]


def _semantic_text(
    *,
    action: str,
    scope: str,
    outcome: str,
    operating_context: str,
    capabilities: Sequence[str],
    evidence: Sequence[str],
) -> str:
    return " ".join(
        (
            f"Action: {_clean_text(action)}",
            f"Scope: {_clean_text(scope)}",
            f"Outcome: {_clean_text(outcome)}",
            f"Operating context: {_clean_text(operating_context)}",
            f"Capabilities: {'; '.join(capabilities)}",
            f"Evidence: {' '.join(evidence)}",
        )
    ).strip()


def _cluster(
    *,
    cluster_id: str,
    cluster_kind: str,
    root_authority: Mapping[str, Any],
    members: Sequence[str],
    allowed_sections: Sequence[str],
    linked_fact_ids: Sequence[str],
    semantic_components: Mapping[str, Any],
    graph: Mapping[str, Any],
    rows: Mapping[str, Mapping[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    member_records: list[dict[str, Any]] = []
    edge_ids: set[str] = set()
    for skill_id in members:
        fact_edges, policy_edge_id = _active_member_edges(skill_id, rows[skill_id], edges)
        if not fact_edges or not policy_edge_id:
            raise DerivedClusterError(f"member authority incomplete: {skill_id}")
        if skill_id not in nodes:
            raise DerivedClusterError(f"graph node missing for active skill: {skill_id}")
        edge_ids.update(fact_edges)
        edge_ids.add(policy_edge_id)
        member_records.append(
            {
                "node_id": skill_id,
                "graph_node_sha256": canonical_sha256(nodes[skill_id]),
                "skill_row_sha256": canonical_sha256(rows[skill_id]),
                "fact_edge_ids": fact_edges,
                "policy_edge_id": policy_edge_id,
            }
        )
    envelope = {
        "canonical_graph_sha256": canonical_sha256(graph),
        "cluster_kind": cluster_kind,
        "root_authority": dict(root_authority),
        "members": member_records,
        "member_edges": sorted(edge_ids),
        "linked_fact_ids": list(linked_fact_ids),
        "allowed_sections": list(allowed_sections),
        "external_claim_policy": _EXTERNAL_CLAIM_POLICY,
        "section_authority": "runtime_bundle_section_eligibility",
    }
    return {
        "cluster_id": cluster_id,
        "cluster_kind": cluster_kind,
        "canonical_embedding_text": _semantic_text(
            action=str(semantic_components["claim_action"]),
            scope=str(semantic_components["claim_scope"]),
            outcome=str(semantic_components["claim_outcome"]),
            operating_context=str(semantic_components["operating_context"]),
            capabilities=list(semantic_components["concrete_capabilities"]),
            evidence=list(semantic_components["approved_evidence_summaries"]),
        ),
        "semantic_components": dict(semantic_components),
        "member_node_ids": list(members),
        "member_edge_ids": sorted(edge_ids),
        "linked_fact_ids": list(linked_fact_ids),
        "linked_metric_ids": [],
        "allowed_sections": list(allowed_sections),
        "activation_status": "DERIVED_REVIEW_ONLY",
        "external_claim_policy": _EXTERNAL_CLAIM_POLICY,
        "authority_envelope": envelope,
        "authority_envelope_sha256": canonical_sha256(envelope),
        "future_vector_count": 1,
        "derived_for": "OWNER_SOLO_FULL_RESUME_QREL_W1B",
    }


def _eligible_members(
    bundle: Mapping[str, Any], rows: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    return sorted(
        {
            str(skill_id)
            for skill_id in bundle.get("graph_skill_node_ids") or []
            if str(skill_id) in rows
        }
    )


def _held(
    *,
    source_kind: str,
    source_bundle_id: str,
    allowed_sections: Sequence[str],
    members: Sequence[str],
    reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "source_kind": source_kind,
        "source_bundle_id": source_bundle_id,
        "candidate_allowed_sections": list(allowed_sections),
        "candidate_member_node_ids": list(members),
        "hold_reasons": sorted(set(reasons)),
    }


def build_derived_bundle_registry(repo_root: Path | str) -> dict[str, Any]:
    """Derive review-only, multi-node clusters from existing section bundles."""

    root = Path(repo_root).resolve()
    scope = load_full_resume_scope(root)
    issues = validate_full_resume_scope(scope, root)
    if issues:
        raise DerivedClusterError(f"W0 scope invalid: {issues}")
    base_registry = _read_json(root / REGISTRY_PATH)
    graph = load_augmented_skills_graph(repo_root=root)
    if canonical_sha256(graph) != (base_registry.get("source_authority") or {}).get(
        "canonical_graph_sha256"
    ):
        raise DerivedClusterError("base registry graph binding drifted")
    facts_path = root / FACT_LEDGER_PATH
    facts = _fact_records(_read_json(facts_path))
    rows = _active_rows(graph)
    nodes = _graph_nodes(graph)
    edges = _active_edges(graph)
    source_records = {
        str(HEADLINE_BUNDLE_SOURCE_PATH): _file_sha256(root / HEADLINE_BUNDLE_SOURCE_PATH),
        str(IBM_BUNDLE_SOURCE_PATH): _file_sha256(root / IBM_BUNDLE_SOURCE_PATH),
    }
    clusters: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []

    headline = build_headline_positioning_section_packet(repo_root=root)
    for bundle in headline["headline_positioning_bundles"]:
        bundle_id = str(bundle["headline_positioning_bundle_id"])
        members = _eligible_members(bundle, rows)
        fact_ids = sorted({str(value) for value in bundle["linked_source_fact_ids"]})
        reasons: list[str] = []
        if len(members) < 2:
            reasons.append("INSUFFICIENT_ACTIVE_MULTI_NODE_MEMBERS")
        if not fact_ids:
            reasons.append("NO_LINKED_SOURCE_FACT")
        if any(fact_id not in facts for fact_id in fact_ids):
            reasons.append("UNKNOWN_LINKED_SOURCE_FACT")
        if reasons:
            held.append(
                _held(
                    source_kind="headline_positioning_bundle",
                    source_bundle_id=bundle_id,
                    allowed_sections=["headline"],
                    members=members,
                    reasons=reasons,
                )
            )
            continue
        components = {
            "claim_action": f"Position executive profile as {bundle['display_phrase_candidate']}",
            "claim_scope": (
                "Headline positioning for "
                f"{bundle['positioning_family'].replace('_', ' ')}"
            ),
            "claim_outcome": bundle["target_relevance_rationale"],
            "operating_context": "Executive headline positioning",
            "concrete_capabilities": _phrases(rows, members),
            "approved_evidence_summaries": _fact_evidence(facts, fact_ids),
        }
        clusters.append(
            _cluster(
                cluster_id=f"cluster_full_resume_headline_{bundle_id}",
                cluster_kind="headline_positioning_bundle",
                root_authority={
                    "kind": "headline_positioning_bundle",
                    "bundle_id": bundle_id,
                    "source_path": str(HEADLINE_BUNDLE_SOURCE_PATH),
                    "source_file_sha256": source_records[
                        str(HEADLINE_BUNDLE_SOURCE_PATH)
                    ],
                    "section_eligibility": ["headline"],
                },
                members=members,
                allowed_sections=["headline"],
                linked_fact_ids=fact_ids,
                semantic_components=components,
                graph=graph,
                rows=rows,
                nodes=nodes,
                edges=edges,
            )
        )

    ibm = build_ibm_role_episode_section_packet("ibm_bullets", repo_root=root)
    for bundle in ibm["role_episode_bundles"]:
        bundle_id = str(bundle["role_episode_bundle_id"])
        sections = [
            section
            for section in ("ibm_bullets", "ibm_narrative")
            if section in bundle["section_eligibility"]
        ]
        members = _eligible_members(bundle, rows)
        fact_ids = sorted({str(value) for value in bundle["linked_source_fact_ids"]})
        reasons = []
        if not sections:
            reasons.append("NO_IBM_SECTION_ELIGIBILITY")
        if len(members) < 2:
            reasons.append("INSUFFICIENT_ACTIVE_MULTI_NODE_MEMBERS")
        if not fact_ids:
            reasons.append("NO_LINKED_SOURCE_FACT")
        if any(fact_id not in facts for fact_id in fact_ids):
            reasons.append("UNKNOWN_LINKED_SOURCE_FACT")
        if reasons:
            held.append(
                _held(
                    source_kind="ibm_role_episode_bundle",
                    source_bundle_id=bundle_id,
                    allowed_sections=sections,
                    members=members,
                    reasons=reasons,
                )
            )
            continue
        story = bundle["graph_bundle_story"]
        components = {
            "claim_action": story["claim_action"],
            "claim_scope": story["claim_scope"],
            "claim_outcome": story["claim_outcome"],
            "operating_context": bundle["operating_context"],
            "concrete_capabilities": _phrases(rows, members),
            "approved_evidence_summaries": _fact_evidence(facts, fact_ids),
        }
        clusters.append(
            _cluster(
                cluster_id=f"cluster_full_resume_ibm_{bundle_id}",
                cluster_kind="ibm_role_episode_bundle",
                root_authority={
                    "kind": "ibm_role_episode_bundle",
                    "bundle_id": bundle_id,
                    "source_path": str(IBM_BUNDLE_SOURCE_PATH),
                    "source_file_sha256": source_records[str(IBM_BUNDLE_SOURCE_PATH)],
                    "section_eligibility": sections,
                },
                members=members,
                allowed_sections=sections,
                linked_fact_ids=fact_ids,
                semantic_components=components,
                graph=graph,
                rows=rows,
                nodes=nodes,
                edges=edges,
            )
        )

    clusters = sorted(clusters, key=lambda item: item["cluster_id"])
    held = sorted(
        held, key=lambda item: (item["source_kind"], item["source_bundle_id"])
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "purpose": (
            "Review-only derived multi-node C0.3 embedding clusters for the full-resume "
            "owner-solo QREL lane."
        ),
        "source_authority": {
            "scope_path": str(SCOPE_PATH),
            "scope_manifest_sha256": scope["scope_manifest_sha256"],
            "base_registry_path": str(REGISTRY_PATH),
            "base_registry_sha256": base_registry["registry_sha256"],
            "canonical_graph_sha256": canonical_sha256(graph),
            "fact_ledger_path": str(FACT_LEDGER_PATH),
            "fact_ledger_file_sha256": _file_sha256(facts_path),
            "bundle_source_files": source_records,
        },
        "materialization_policy": {
            "source_graph_authority_changed": False,
            "individual_graph_node_embedding_forbidden": True,
            "minimum_active_member_count": 2,
            "linked_source_fact_required": True,
            "active_hardened_fact_and_policy_edges_required": True,
            "runtime_bundle_section_eligibility_required": True,
            "derived_clusters_review_only": True,
            "production_promotion_authorized": False,
        },
        "clusters": clusters,
        "held_candidates": held,
        "coverage": {
            "headline": sum("headline" in row["allowed_sections"] for row in clusters),
            "ibm_bullets": sum("ibm_bullets" in row["allowed_sections"] for row in clusters),
            "ibm_narrative": sum("ibm_narrative" in row["allowed_sections"] for row in clusters),
            "cluster_count": len(clusters),
            "held_candidate_count": len(held),
        },
    }
    payload["derived_registry_sha256"] = canonical_sha256(payload)
    return payload


def validate_derived_bundle_registry(
    payload: Mapping[str, Any], repo_root: Path | str
) -> list[str]:
    """Fail closed if a materialized W1B registry drifts from its authority."""

    root = Path(repo_root).resolve()
    issues: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") != STATUS:
        issues.append("SCHEMA_OR_STATUS")
    unsigned = dict(payload)
    digest = unsigned.pop("derived_registry_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(unsigned) != digest:
        issues.append("DERIVED_REGISTRY_DIGEST")
    policy = payload.get("materialization_policy")
    if not isinstance(policy, Mapping) or any(
        policy.get(field) is not True
        for field in (
            "individual_graph_node_embedding_forbidden",
            "linked_source_fact_required",
            "active_hardened_fact_and_policy_edges_required",
            "runtime_bundle_section_eligibility_required",
            "derived_clusters_review_only",
        )
    ):
        issues.append("MATERIALIZATION_POLICY")
    if isinstance(policy, Mapping) and (
        policy.get("source_graph_authority_changed") is not False
        or policy.get("production_promotion_authorized") is not False
    ):
        issues.append("AUTHORITY_BOUNDARY")
    coverage = payload.get("coverage")
    if not isinstance(coverage, Mapping) or any(
        coverage.get(section) != 8
        for section in ("headline", "ibm_bullets", "ibm_narrative")
    ):
        issues.append("SECTION_COVERAGE")
    clusters = payload.get("clusters")
    if not isinstance(clusters, list) or len(clusters) != 16:
        issues.append("CLUSTER_COUNT")
    else:
        ids = [str(row.get("cluster_id") or "") for row in clusters if isinstance(row, Mapping)]
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            issues.append("CLUSTER_IDENTITIES")
        for row in clusters:
            if not isinstance(row, Mapping):
                issues.append("CLUSTER_SHAPE")
                continue
            if len(row.get("member_node_ids") or []) < 2 or row.get("future_vector_count") != 1:
                issues.append("MULTI_NODE_VECTOR_UNIT")
            if row.get("activation_status") != "DERIVED_REVIEW_ONLY":
                issues.append("DERIVED_ACTIVATION_BOUNDARY")
            if not row.get("linked_fact_ids") or not row.get("authority_envelope_sha256"):
                issues.append("CLUSTER_AUTHORITY")
    source = payload.get("source_authority")
    if not isinstance(source, Mapping):
        issues.append("SOURCE_AUTHORITY")
    else:
        base = _read_json(root / REGISTRY_PATH)
        if source.get("base_registry_sha256") != base.get("registry_sha256"):
            issues.append("BASE_REGISTRY_BINDING")
        graph = load_augmented_skills_graph(repo_root=root)
        if source.get("canonical_graph_sha256") != canonical_sha256(graph):
            issues.append("GRAPH_BINDING")
    return sorted(set(issues))


def write_derived_bundle_registry(repo_root: Path | str) -> tuple[Path, dict[str, Any]]:
    """Materialize the deterministic W1B artifact only below ignored runtime."""

    root = Path(repo_root).resolve()
    payload = build_derived_bundle_registry(root)
    issues = validate_derived_bundle_registry(payload, root)
    if issues:
        raise DerivedClusterError(f"Derived registry invalid: {issues}")
    directory = root / RUNTIME_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"derived_bundle_registry.{payload['derived_registry_sha256']}.json"
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise DerivedClusterError(f"Immutable derived registry collision: {path}")
    if not path.exists():
        path.write_text(rendered, encoding="utf-8")
    return path, payload
