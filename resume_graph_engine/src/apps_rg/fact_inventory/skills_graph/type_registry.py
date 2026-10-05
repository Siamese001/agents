"""Canonical Type Registry for Graph Nodes and Edges (Wave 3).

Enforces:
- Exact (src_type, tgt_type) signatures for every edge_type (zero polymorphism).
- Layer classification: knowledge, evidence, policy, projection, derived, temporal.
- Explicit traversability flags (traversable=0 for policy/projection edges).
- Inverse traversal labels and cardinality constraints.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .node_type_defs import NODE_TYPE_REGISTRY
from .edge_type_defs import EDGE_TYPE_REGISTRY

POLICY_LAYER_EDGE_TYPES: frozenset[str] = frozenset(
    {et for et, spec in EDGE_TYPE_REGISTRY.items() if spec.get("traversable") == 0}
)


def get_node_type_registry_rows() -> list[dict[str, Any]]:
    """Return all node type registry rows sorted by node_type."""
    return [NODE_TYPE_REGISTRY[k] for k in sorted(NODE_TYPE_REGISTRY)]


def get_edge_type_registry_rows() -> list[dict[str, Any]]:
    """Return all edge type registry rows sorted by edge_type."""
    return [EDGE_TYPE_REGISTRY[k] for k in sorted(EDGE_TYPE_REGISTRY)]


def compute_type_registry_digest() -> str:
    """Compute sha256 digest over the canonical node and edge registries."""
    payload = {
        "nodes": get_node_type_registry_rows(),
        "edges": get_edge_type_registry_rows(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_edge_signature(edge_type: str) -> tuple[str, str] | None:
    """Return expected (src_type, tgt_type) for an edge_type, or None if unknown."""
    spec = EDGE_TYPE_REGISTRY.get(edge_type)
    if not spec:
        return None
    return (spec["src_type"], spec["tgt_type"])


def is_edge_traversable(edge_type: str) -> int:
    """Return 1 if edge is traversable, 0 otherwise."""
    spec = EDGE_TYPE_REGISTRY.get(edge_type)
    if not spec:
        return 1
    return int(spec.get("traversable", 1))


__all__ = [
    "NODE_TYPE_REGISTRY",
    "EDGE_TYPE_REGISTRY",
    "POLICY_LAYER_EDGE_TYPES",
    "get_node_type_registry_rows",
    "get_edge_type_registry_rows",
    "compute_type_registry_digest",
    "get_edge_signature",
    "is_edge_traversable",
]
