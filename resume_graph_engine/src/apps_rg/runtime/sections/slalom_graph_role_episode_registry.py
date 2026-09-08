"""Slalom Role Episode Bundle registry — graph-backed, employer-bound bundles for slalom lanes.

Loads slalom_role_episode_bundles.json and exposes typed accessors plus guards. Enforces
the role_episode_bundle_id gating invariant: slalom_bullets/slalom_narrative may only consume
graph context when a role_episode_bundle_id is explicitly bound, not from flat skill lists.

Runtime status: ENABLED_WITH_ROLE_EPISODE_BUNDLE_GUARDS — graph_expansion consumes bundles only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from apps_rg.runtime.sections.role_episode_bundle_registry import (
    get_all_role_episode_bundles,
    get_role_episode_bundle_by_id,
    get_role_episode_bundles_for_section,
    load_role_episode_bundle_doc,
    validate_role_episode_bundle_base,
)
from apps_rg.runtime.sections.role_episode_metric_registry import (
    approved_metric_outcome_ids_from_path,
)

BUNDLES_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "apps_rg"
    / "fact_inventory"
    / "slalom_role_episode_bundles.json"
)

SLALOM_EMPLOYER_ID: str = "Slalom"
SLALOM_EMPLOYER_NODE_ID: str = "employment_exp_slalom_001"
SLALOM_TIME_WINDOW: str = "2026-06 to present"

_VALID_EMPLOYER_LABELS: frozenset[str] = frozenset({"Slalom"})

REQUIRED_BUNDLE_FIELDS: frozenset[str] = frozenset({
    "role_episode_bundle_id",
    "employer",
    "title",
    "employer_node_id",
    "executive_scope_signals",
    "architecture_scope_signals",
    "graph_skill_node_ids",
    "linked_source_fact_ids",
    "operating_context",
    "bullet_intent",
    "section_eligibility",
    "external_claim_policy",
    "activation_status",
})

# Metric approval is graph-native: presence in metric_outcome_nodes.
APPROVED_METRIC_OUTCOME_IDS: tuple[str, ...] = approved_metric_outcome_ids_from_path(BUNDLES_PATH)

VALID_ACTIVATION_STATUS: frozenset[str] = frozenset({
    "ACTIVE_CONFIRMED",
    "ACTIVE_INTERNAL_ONLY",
    "DRAFT",
    "BLOCKED_NO_SOURCE",
    "SUPPORTING_CONTEXT_ONLY",
})


def _load_bundles(path: Path = BUNDLES_PATH) -> dict[str, Any]:
    return load_role_episode_bundle_doc(path)


def get_all_bundles(path: Path = BUNDLES_PATH) -> list[dict[str, Any]]:
    return get_all_role_episode_bundles(path)


def get_bundle_by_id(bundle_id: str, path: Path = BUNDLES_PATH) -> dict[str, Any] | None:
    return get_role_episode_bundle_by_id(path, bundle_id)


def get_bundles_for_section(section_id: str, path: Path = BUNDLES_PATH) -> list[dict[str, Any]]:
    return get_role_episode_bundles_for_section(path, section_id)


def validate_bundle(bundle: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a Slalom role episode bundle against required schema and invariants."""
    violations = validate_role_episode_bundle_base(
        bundle,
        required_fields=REQUIRED_BUNDLE_FIELDS,
        employer_id=SLALOM_EMPLOYER_ID,
        employer_node_id=SLALOM_EMPLOYER_NODE_ID,
        valid_sections={
            "slalom_bullets",
            "slalom_narrative",
            "competencies",
            "headline",
            "executive_summary",
        },
        valid_employer_labels=_VALID_EMPLOYER_LABELS,
        shared_sections=(),
    )
    return len(violations) == 0, violations


__all__ = [
    "APPROVED_METRIC_OUTCOME_IDS",
    "BUNDLES_PATH",
    "REQUIRED_BUNDLE_FIELDS",
    "SLALOM_EMPLOYER_ID",
    "SLALOM_EMPLOYER_NODE_ID",
    "SLALOM_TIME_WINDOW",
    "VALID_ACTIVATION_STATUS",
    "get_all_bundles",
    "get_bundle_by_id",
    "get_bundles_for_section",
    "validate_bundle",
]
