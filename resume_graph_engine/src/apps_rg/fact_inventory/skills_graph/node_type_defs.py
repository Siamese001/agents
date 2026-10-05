"""Canonical Node Type Definitions (Wave 3)."""
from __future__ import annotations

from typing import Any

#: Canonical Node Type Registry: 20 node types across 6 layers
NODE_TYPE_REGISTRY: dict[str, dict[str, Any]] = {
    "career_track": {
        "node_type": "career_track",
        "layer": "knowledge",
        "description": "Top-level professional trajectory spine anchoring career hierarchy",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "career_epoch": {
        "node_type": "career_epoch",
        "layer": "temporal",
        "description": "Time-bound operating era or career phase with defined ordinal",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "pillar": {
        "node_type": "pillar",
        "layer": "knowledge",
        "description": "Strategic capability pillar grouping capability domains and skills",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "capability_domain": {
        "node_type": "capability_domain",
        "layer": "knowledge",
        "description": "Cohesive functional or technical capability domain containing skills",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "skill": {
        "node_type": "skill",
        "layer": "knowledge",
        "description": "Atomic capability or competency node evaluated for resume surfacing",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "fact": {
        "node_type": "fact",
        "layer": "evidence",
        "description": "Grounded empirical fact or verified achievement claim",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "employment": {
        "node_type": "employment",
        "layer": "evidence",
        "description": "Formal employer organizational tenure with dates, title, and epoch",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "engagement": {
        "node_type": "engagement",
        "layer": "evidence",
        "description": "First-class role-episode bundle representing client/platform engagement",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "metric_outcome": {
        "node_type": "metric_outcome",
        "layer": "evidence",
        "description": "Reified quantifiable business or technical metric outcome",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "locked_bullet": {
        "node_type": "locked_bullet",
        "layer": "evidence",
        "description": "Approved immutable bullet artifact used as evidential anchor",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "certification": {
        "node_type": "certification",
        "layer": "evidence",
        "description": "External verified professional certification or credential",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "concept": {
        "node_type": "concept",
        "layer": "evidence",
        "description": "Technical concept or architectural terminology backing skill claims",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "repo_evidence": {
        "node_type": "repo_evidence",
        "layer": "evidence",
        "description": "Implementation repository artifact or code demonstration evidence",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "metric": {
        "node_type": "metric",
        "layer": "knowledge",
        "description": "Abstract metric type definition or KPI category",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "metric_bucket": {
        "node_type": "metric_bucket",
        "layer": "knowledge",
        "description": "Taxonomic category grouping metric types",
        "is_canonical": 1,
        "is_traversable": 1,
    },
    "section": {
        "node_type": "section",
        "layer": "projection",
        "description": "Target resume section for output rendering and candidate allocation",
        "is_canonical": 1,
        "is_traversable": 0,
    },
    "policy": {
        "node_type": "policy",
        "layer": "policy",
        "description": "Governance claim policy or release gate enforcement rule",
        "is_canonical": 1,
        "is_traversable": 0,
    },
    "policy_rule": {
        "node_type": "policy_rule",
        "layer": "policy",
        "description": "Discrete policy evaluation rule or guardrail check",
        "is_canonical": 1,
        "is_traversable": 0,
    },
    "role_family": {
        "node_type": "role_family",
        "layer": "projection",
        "description": "Target persona or role family projection weighting profile",
        "is_canonical": 1,
        "is_traversable": 0,
    },
    "graph_ref": {
        "node_type": "graph_ref",
        "layer": "projection",
        "description": "Generic external reference placeholder",
        "is_canonical": 0,
        "is_traversable": 0,
    },
}

__all__ = ["NODE_TYPE_REGISTRY"]
