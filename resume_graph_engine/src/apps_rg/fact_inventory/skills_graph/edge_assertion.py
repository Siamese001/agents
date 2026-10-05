"""Edge assertion taxonomy, contract v2 loading, and lineage attribution for graph edges."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps_rg.repository_layout import repository_root

CONTRACT_V2_REL_PATH = "src/apps_rg/fact_inventory/c03_graph_edge_semantic_contract.v2.json"
SEMANTIC_CONTRACT_VERSION_V2 = "apps_rg.c03_graph_edge_semantic_contract.v2"

ASSERTION_TYPES: frozenset[str] = frozenset(
    {
        "STRUCTURAL_CONTAINMENT",
        "TAXONOMIC_ATTRIBUTION",
        "EVIDENTIAL_SUPPORT",
        "POLICY_ELIGIBILITY",
        "POLICY_RESTRICTION",
        "METRIC_BINDING",
        "TEMPORAL_SEQUENCE",
        "ASSOCIATIVE_BRIDGE",
    }
)

ASSERTION_BASIS_KINDS: frozenset[str] = frozenset(
    {
        "evidence_reference",
        "source_field_derivation",
        "taxonomy_rule",
        "policy_predicate",
        "non_causal_bridge",
        "operator_confirmation",
    }
)

LIFECYCLE_DISPOSITIONS: frozenset[str] = frozenset(
    {
        "ACTIVE_POLICY_GATED",
        "INTERNAL_TRAVERSAL_ONLY",
        "HELD_NON_ACTIVE_ENDPOINT",
        "HELD_INTEGRITY_GAP",
    }
)

ORIGIN_KINDS: frozenset[str] = frozenset(
    {
        "ledger_edge",
        "bundle_row",
        "derived_projection",
    }
)

_CONTRACT_CACHE: dict[str, dict[str, Any]] = {}


def load_edge_semantic_contract_v2(repo_root: Path | None = None) -> dict[str, Any]:
    """Load and cache the edge semantic contract v2 JSON."""
    root = repository_root(repo_root)
    cache_key = str(root)
    if cache_key in _CONTRACT_CACHE:
        return _CONTRACT_CACHE[cache_key]

    path = root / CONTRACT_V2_REL_PATH
    if not path.is_file():
        alt = root / "resume_graph_engine" / CONTRACT_V2_REL_PATH
        if alt.is_file():
            path = alt
        else:
            raise FileNotFoundError(f"c03_graph_edge_semantic_contract.v2.json not found at {path}")

    contract = json.loads(path.read_text(encoding="utf-8"))
    _CONTRACT_CACHE[cache_key] = contract
    return contract


def resolve_edge_assertion_type(
    edge_type: str,
    contract: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> str:
    """Return the canonical assertion_type for an edge_type, raising if unmapped."""
    c = contract or load_edge_semantic_contract_v2(repo_root)
    type_map = c.get("assertion_type_by_edge_type") or {}
    et = str(edge_type or "").strip()
    if et not in type_map:
        raise ValueError(
            f"edge_type {et!r} is not registered in semantic contract v2 (registered={len(type_map)})"
        )
    return str(type_map[et])


def resolve_edge_assertion_basis(
    edge_type: str,
    existing_basis: str | None = None,
    contract: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> str:
    """Return the valid assertion_basis for an edge."""
    if existing_basis and str(existing_basis).strip() in ASSERTION_BASIS_KINDS:
        return str(existing_basis).strip()
    c = contract or load_edge_semantic_contract_v2(repo_root)
    basis_map = c.get("basis_kind_by_edge_type") or {}
    et = str(edge_type or "").strip()
    if et in basis_map:
        return str(basis_map[et])
    return "source_field_derivation"


def resolve_derivation_rule_id(
    edge_type: str,
    contract: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> str:
    """Return the derivation_rule_id for an edge_type."""
    c = contract or load_edge_semantic_contract_v2(repo_root)
    rule_map = c.get("derivation_rule_id_by_edge_type") or {}
    et = str(edge_type or "").strip()
    return str(rule_map.get(et) or f"rule_{et}")


def resolve_inverse_label(
    edge_type: str,
    contract: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> str:
    """Return the inverse_label for an edge_type."""
    c = contract or load_edge_semantic_contract_v2(repo_root)
    inv_map = c.get("inverse_label_by_edge_type") or {}
    et = str(edge_type or "").strip()
    return str(inv_map.get(et) or f"{et}_reverse")


def harden_edge_row(
    raw_edge: dict[str, Any],
    *,
    build_run_id: str,
    contract: dict[str, Any] | None = None,
    default_origin_kind: str = "ledger_edge",
    default_origin_artifact_sha256: str = "",
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Ensure an edge dict contains all required assertion and lineage columns."""
    c = contract or load_edge_semantic_contract_v2(repo_root)
    edge_type = str(raw_edge.get("edge_type") or "").strip()
    edge_id = str(raw_edge.get("edge_id") or "").strip()
    src = str(raw_edge.get("source_node_id") or raw_edge.get("source") or "").strip()
    tgt = str(raw_edge.get("target_node_id") or raw_edge.get("target") or "").strip()

    assertion_type = str(
        raw_edge.get("assertion_type") or resolve_edge_assertion_type(edge_type, c)
    )
    assertion_basis = resolve_edge_assertion_basis(
        edge_type, raw_edge.get("assertion_basis"), c
    )

    # Basis references
    raw_refs = raw_edge.get("assertion_basis_refs")
    if isinstance(raw_refs, list) and raw_refs:
        refs = [str(r) for r in raw_refs if str(r).strip()]
    elif isinstance(raw_refs, str) and raw_refs.startswith("["):
        try:
            refs = json.loads(raw_refs)
        except json.JSONDecodeError:
            refs = []
    else:
        refs = []

    # If evidential support, ensure basis refs are present
    if assertion_type == "EVIDENTIAL_SUPPORT" and not refs:
        refs = [f"evidence:{tgt}", f"contract:edge_types/{edge_type}"]
    elif not refs:
        refs = [f"contract:edge_types/{edge_type}"]

    assertion_basis_refs_json = json.dumps(refs, sort_keys=True)

    canonical_text = str(
        raw_edge.get("canonical_assertion_text")
        or raw_edge.get("rationale")
        or f"{src} {edge_type} {tgt}"
    ).strip()

    # Lifecycle disposition
    disp = str(raw_edge.get("lifecycle_disposition") or "").strip()
    if disp not in LIFECYCLE_DISPOSITIONS:
        if assertion_type == "POLICY_RESTRICTION":
            disp = "INTERNAL_TRAVERSAL_ONLY"
        elif str(raw_edge.get("validation_status") or "") == "validated":
            disp = "ACTIVE_POLICY_GATED"
        else:
            disp = "ACTIVE_POLICY_GATED"

    # Enforce restriction invariant
    if assertion_type == "POLICY_RESTRICTION" and disp == "ACTIVE_POLICY_GATED":
        disp = "INTERNAL_TRAVERSAL_ONLY"

    origin_kind = str(raw_edge.get("origin_kind") or default_origin_kind).strip()
    if origin_kind not in ORIGIN_KINDS:
        origin_kind = "ledger_edge"

    origin_ref = str(raw_edge.get("origin_ref") or edge_id).strip()
    if not origin_ref:
        origin_ref = edge_id

    origin_sha = str(
        raw_edge.get("origin_artifact_sha256") or default_origin_artifact_sha256
    ).strip()
    derivation_rule_id = str(
        raw_edge.get("derivation_rule_id") or resolve_derivation_rule_id(edge_type, c)
    ).strip()

    row = dict(raw_edge)
    row["edge_id"] = edge_id
    row["source_node_id"] = src
    row["target_node_id"] = tgt
    row["edge_type"] = edge_type
    row["assertion_type"] = assertion_type
    row["assertion_basis"] = assertion_basis
    row["assertion_basis_refs_json"] = assertion_basis_refs_json
    row["canonical_assertion_text"] = canonical_text
    row["lifecycle_disposition"] = disp
    row["semantic_contract_version"] = SEMANTIC_CONTRACT_VERSION_V2
    row["origin_kind"] = origin_kind
    row["origin_ref"] = origin_ref
    row["origin_artifact_sha256"] = origin_sha
    row["derivation_rule_id"] = derivation_rule_id
    row["build_run_id"] = build_run_id
    return row


def finalize_and_harden_edge_rows(
    edge_rows: list[dict[str, Any]],
    *,
    build_run_id: str,
    contract: dict[str, Any],
    ledger_hash: str,
    repo_root: Path,
) -> list[dict[str, Any]]:
    """Apply default edge fields and harden edge rows against contract v2."""
    for row in edge_rows:
        edge_type = str(row.get("edge_type") or "")
        row.setdefault("rationale", edge_type)
        row.setdefault("projection_behavior", "graph_traversal")
        row.setdefault("external_claim_policy", "graph_routing_not_claim_proof")
        row.setdefault("validation_status", str(row.get("evidence_status") or ""))
        row.setdefault("edge_note", "")
        row.setdefault("operator_note", "")
        row.setdefault("business_story", "")
        row.setdefault("technical_story", "")

    return [
        harden_edge_row(
            raw_edge,
            build_run_id=build_run_id,
            contract=contract,
            default_origin_kind="ledger_edge",
            default_origin_artifact_sha256=ledger_hash,
            repo_root=repo_root,
        )
        for raw_edge in edge_rows
    ]


__all__ = [
    "ASSERTION_BASIS_KINDS",
    "ASSERTION_TYPES",
    "CONTRACT_V2_REL_PATH",
    "LIFECYCLE_DISPOSITIONS",
    "ORIGIN_KINDS",
    "SEMANTIC_CONTRACT_VERSION_V2",
    "harden_edge_row",
    "finalize_and_harden_edge_rows",
    "load_edge_semantic_contract_v2",
    "resolve_derivation_rule_id",
    "resolve_edge_assertion_basis",
    "resolve_edge_assertion_type",
    "resolve_inverse_label",
]
