"""Node type resolution and basic classification."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .schema import CANONICAL_NODE_TYPES, RAW_TO_CANONICAL_NODE_TYPE
from .constants import (
    CANDIDATE_LEDGER_REL_PATH,
    FORBIDDEN_SKILL_NODE_IDS,
    POLICY_EDGE_SOURCE_KEYS,
    THEME_AGENTIC_SKILL_IDS,
)
from .storage import _repo_root

def infer_node_type_from_id(node_id: str) -> str:
    nid = str(node_id or "").strip()
    if not nid:
        return "graph_ref"
    if nid.startswith("policy_rule_") or nid in POLICY_EDGE_SOURCE_KEYS:
        return "policy_rule"
    if nid.startswith("policy_"):
        return "policy"
    if nid.startswith("section_"):
        return "section"
    if nid.startswith("concept_"):
        return "concept"
    if nid.startswith("repo_"):
        return "repo_evidence"
    if nid.startswith("domain_"):
        return "capability_domain"
    if nid.startswith("employment_") or nid.startswith("exp_"):
        return "employment"
    if nid.startswith("bul_"):
        return "locked_bullet"
    if nid.startswith("cert_"):
        return "certification"
    if nid.startswith("fact_") or nid.startswith("node_fact_"):
        return "fact"
    # W2.0: metric_outcome IDs are minted as ``metric_<employer>_<...>`` in
    # role_episode_bundle files. Inference precedes the skill_ branch because
    # neither prefix collides with the other.
    if nid.startswith("metric_"):
        return "metric_outcome"
    if nid.startswith("skill_"):
        return "skill"
    if nid.startswith("pillar_"):
        return "pillar"
    if nid.startswith("track_"):
        return "career_track"
    if nid.startswith("epoch_"):
        return "career_epoch"
    return "graph_ref"

def resolve_node_type(node_id: str, raw_type: str) -> str:
    nid = str(node_id or "").strip()
    low = str(raw_type or "").strip()
    if nid in FORBIDDEN_SKILL_NODE_IDS:
        return "policy_rule"
    if low in CANONICAL_NODE_TYPES and low != nid:
        return low
    mapped = RAW_TO_CANONICAL_NODE_TYPE.get(low)
    if mapped and mapped != nid:
        return mapped
    inferred = infer_node_type_from_id(nid)
    if inferred != "graph_ref":
        return inferred
    if low and low != nid:
        return low
    return inferred

def canonical_node_type(raw: str, *, node_id: str = "") -> str:
    if node_id:
        return resolve_node_type(node_id, raw)
    r = str(raw or "").strip()
    if r in CANONICAL_NODE_TYPES or r in RAW_TO_CANONICAL_NODE_TYPE:
        return resolve_node_type("", r)
    return resolve_node_type(r, "")

def _is_skill_id(value: str) -> bool:
    return str(value or "").startswith("skill_")

def default_candidate_fact_ledger_path(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root()
    return (root / CANDIDATE_LEDGER_REL_PATH).resolve()


__all__ = ['infer_node_type_from_id', 'resolve_node_type', 'canonical_node_type', '_is_skill_id', 'default_candidate_fact_ledger_path']
