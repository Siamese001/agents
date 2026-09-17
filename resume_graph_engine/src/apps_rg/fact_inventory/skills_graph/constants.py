"""Constants, career epoch mappings, and signature reporting for skills graph."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    REGISTERED_GRAPH_EDGE_SIGNATURES,
    default_arsenal_ledger_path,
    derive_registered_graph_endpoint_types,
    skill_row_eligible_for_external_claim,
    validate_arsenal_ledger_shape,
)
from .schema import (
    CANONICAL_NODE_TYPES,
    EPOCH_LABELS,
    EPOCH_ORDINAL,
    LEGACY_SKILL_EPOCHS,
    ORDINAL_TO_EPOCH,
    P6_SKILLS,
    RAW_TO_CANONICAL_NODE_TYPE,
)

REPO_REL_DB = Path("artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite")
C03_SQLITE_MATERIALIZER_CODE_VERSION = (
    "c03_sqlite_materializer.v20260718.lossless_types_signatures_full_digest"
)


def canonical_career_epoch_and_ordinal(skill_id: str, raw_epoch: str | None) -> tuple[str, int | None]:
    """Map a skill ID and its raw career_epoch into canonical career_epoch and 1..6 ordinal."""
    sid = str(skill_id or "").strip()
    raw = str(raw_epoch or "").strip()
    if sid in LEGACY_SKILL_EPOCHS:
        epoch = LEGACY_SKILL_EPOCHS[sid]
    elif sid in P6_SKILLS:
        epoch = "epoch_ai_platform_commercialization"
    else:
        epoch = raw
    ordinal = EPOCH_ORDINAL.get(epoch)
    return epoch, ordinal


def project_registered_graph_node_type(raw_type: str) -> str:
    """Project one registered canonical node type into the SQLite type system."""
    normalized = str(raw_type or "").strip()
    projected = RAW_TO_CANONICAL_NODE_TYPE.get(normalized)
    if projected is None:
        raise ValueError(f"unregistered canonical graph node type: {normalized or '<blank>'}")
    return projected


def projected_registered_graph_edge_signatures() -> dict[str, frozenset[tuple[str, str]]]:
    """Return canonical-normalized plus app-derived projected signatures."""
    from apps_rg.fact_inventory.metric_outcome_materializer import (
        METRIC_OUTCOME_EDGE_SIGNATURES,
    )

    signatures = {
        edge_type: frozenset(
            (
                project_registered_graph_node_type(source_type),
                project_registered_graph_node_type(target_type),
            )
            for source_type, target_type in raw_signatures
        )
        for edge_type, raw_signatures in REGISTERED_GRAPH_EDGE_SIGNATURES.items()
    }
    overlap = set(signatures) & set(METRIC_OUTCOME_EDGE_SIGNATURES)
    if overlap:
        raise ValueError(f"metric-outcome edge signatures collide with canonical registry: {sorted(overlap)}")
    signatures.update(METRIC_OUTCOME_EDGE_SIGNATURES)
    return signatures


def projected_graph_edge_signature_report(
    *,
    node_types_by_id: Mapping[str, str],
    edge_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Assert registered edges retain a valid normalized endpoint signature."""
    projected_signatures = projected_registered_graph_edge_signatures()
    edge_count = 0
    registered_edge_count = 0
    valid_edge_count = 0
    unregistered_edge_count = 0
    failures: list[dict[str, Any]] = []
    for row in edge_rows:
        edge_count += 1
        edge_id = str(row.get("edge_id") or "").strip()
        edge_type = str(row.get("edge_type") or "").strip()
        source_node_id = str(row.get("source_node_id") or "").strip()
        target_node_id = str(row.get("target_node_id") or "").strip()
        source_type = str(node_types_by_id.get(source_node_id) or "").strip()
        target_type = str(node_types_by_id.get(target_node_id) or "").strip()
        allowed = projected_signatures.get(edge_type)
        if allowed is None:
            unregistered_edge_count += 1
            failures.append(
                {
                    "edge_id": edge_id or "<blank-edge-id>",
                    "edge_type": edge_type or "<blank-edge-type>",
                    "source_node_id": source_node_id,
                    "target_node_id": target_node_id,
                    "source_type": source_type or "<missing>",
                    "target_type": target_type or "<missing>",
                    "allowed_projected_signatures": [],
                    "reason": "edge_type_unregistered",
                }
            )
            continue
        registered_edge_count += 1
        if source_type and target_type and (source_type, target_type) in allowed:
            valid_edge_count += 1
            continue
        failures.append(
            {
                "edge_id": edge_id or "<blank-edge-id>",
                "edge_type": edge_type,
                "source_node_id": source_node_id,
                "target_node_id": target_node_id,
                "source_type": source_type or "<missing>",
                "target_type": target_type or "<missing>",
                "allowed_projected_signatures": [
                    {"source_type": allowed_source, "target_type": allowed_target}
                    for allowed_source, allowed_target in sorted(allowed)
                ],
                "reason": "projected_endpoint_signature_invalid",
            }
        )
    return {
        "edge_count": edge_count,
        "registered_edge_count": registered_edge_count,
        "valid_edge_count": valid_edge_count,
        "failure_count": len(failures),
        "unregistered_edge_count": unregistered_edge_count,
        "failure_locators": failures,
    }


POLICY_EDGE_SOURCE_KEYS = frozenset(
    {
        "skill_projection_not_proof",
        "skill_id_never_source_fact_id",
        "derived_supported_requires_fact_links",
        "jd_briefing_targeting_only",
        "metrics_require_metric_fact",
        "ats_keywords_not_claims",
        "blocked_phrase_fail_closed",
        "weak_snippet_internal_only",
        "repo_evidence_portfolio_not_resume_default",
        "pending_source_internal_only",
        "external_resume_claim_requires_active_fact_or_confirmed_snippet",
        "claim_ledger_fact_id_only",
        "no_jd_briefing_source_fact_id",
    }
)

FORBIDDEN_SKILL_NODE_IDS = frozenset(
    {
        "skill_projection_not_proof",
        "skill_id_never_source_fact_id",
    }
)

NON_PROMOTE_ACTIVATION = frozenset(
    {"DRAFT", "INTERNAL_ONLY", "DO_NOT_PROMOTE", "BLOCKED", "USER_CONFIRMED_PENDING_SOURCE"}
)

EXTERNAL_ACTIVE_STATUSES = frozenset({"ACTIVE", "ACTIVE_CONFIRMED"})

CONFIDENCE_GRADES = frozenset({"HIGH", "MEDIUM", "LOW", "BLOCKED"})

BLOCKED_SUPPORT_LEVELS = frozenset(
    {
        "INTERNAL_ONLY",
        "USER_CONFIRMED_PENDING_SOURCE",
        "REPO_EVIDENCE_PORTFOLIO",
        "BLOCKED",
        "TARGETING_ONLY",
        "STYLE_ONLY",
    }
)

BLOCKED_EXTERNAL_CLAIM_POLICIES = frozenset(
    {
        "pending_source_internal_only",
        "weak_snippet_internal_only",
        "repo_portfolio_not_resume_default",
        "internal_traversal_only",
        "skill_projection_not_proof",
    }
)

CONFIDENCE_GRADE_RANK: dict[str, int] = {
    "BLOCKED": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
}

CANDIDATE_LEDGER_REL_PATH = Path(
    "artifacts/apps_rg/fact_inventory/master_candidate_skills_fact_ledger_20260518T1100Z.json"
)

ENGINEERING_PLATFORM_CANDIDATE_FACT_IDS = frozenset(
    {
        "fact_engineering_platform_001",
        "fact_engineering_platform_002",
        "fact_engineering_platform_003",
        "fact_engineering_platform_004",
        "fact_engineering_platform_005",
        "fact_engineering_platform_006",
    }
)

HUMAN_CONFIRM_REQUIRED_ALLOWED_RESUME_USE = frozenset({"allowed_after_human_confirm"})

THEME_AGENTIC_SKILL_IDS = frozenset(
    {
        "skill_governed_agentic_systems_architecture",
        "skill_runtime_gate_mesh_design",
        "skill_prompt_assembly_architecture",
        "skill_context_engineering",
        "skill_evidence_contract_design",
        "skill_dense_sparse_exact_retrieval_design",
        "skill_graph_aware_relationship_grounding",
        "skill_audit_grade_observability",
        "skill_ai_governance_certification",
        "skill_reusable_agentic_platform_architecture",
        "skill_agentic_platform_productization",
        "skill_runtime_proof_bundle_design",
    }
)

OPERATOR_CONFIRMED_ARCHIVE_FACT_IDS = frozenset(
    {
        "fact_engineering_platform_001",
        "fact_engineering_platform_003",
        "fact_engineering_platform_004",
        "fact_engineering_platform_006",
    }
)

OPERATOR_ARCHIVE_PROMOTION_BY_SKILL: dict[str, list[str]] = {
    "skill_governed_agentic_systems_architecture": ["fact_engineering_platform_001"],
    "skill_runtime_gate_mesh_design": ["fact_engineering_platform_001"],
    "skill_context_engineering": ["fact_engineering_platform_003"],
    "skill_prompt_assembly_architecture": ["fact_engineering_platform_003"],
    "skill_dense_sparse_exact_retrieval_design": ["fact_engineering_platform_001"],
    "skill_graph_aware_relationship_grounding": ["fact_engineering_platform_001"],
    "skill_audit_grade_observability": [
        "fact_engineering_platform_003",
        "fact_engineering_platform_004",
    ],
    "skill_reusable_agentic_platform_architecture": ["fact_engineering_platform_006"],
    "skill_agentic_platform_productization": ["fact_engineering_platform_006"],
}

FORBIDDEN_PROMOTION_SKILL_SUBSTRINGS = (
    "airline",
    "brokerage",
    "underwriting",
    "claims",
    "marketplace",
)


__all__ = [
    "REPO_REL_DB",
    "C03_SQLITE_MATERIALIZER_CODE_VERSION",
    "canonical_career_epoch_and_ordinal",
    "project_registered_graph_node_type",
    "projected_registered_graph_edge_signatures",
    "projected_graph_edge_signature_report",
    "POLICY_EDGE_SOURCE_KEYS",
    "FORBIDDEN_SKILL_NODE_IDS",
    "NON_PROMOTE_ACTIVATION",
    "EXTERNAL_ACTIVE_STATUSES",
    "CONFIDENCE_GRADES",
    "BLOCKED_SUPPORT_LEVELS",
    "BLOCKED_EXTERNAL_CLAIM_POLICIES",
    "CONFIDENCE_GRADE_RANK",
    "CANDIDATE_LEDGER_REL_PATH",
    "ENGINEERING_PLATFORM_CANDIDATE_FACT_IDS",
    "HUMAN_CONFIRM_REQUIRED_ALLOWED_RESUME_USE",
    "THEME_AGENTIC_SKILL_IDS",
    "OPERATOR_CONFIRMED_ARCHIVE_FACT_IDS",
    "OPERATOR_ARCHIVE_PROMOTION_BY_SKILL",
    "FORBIDDEN_PROMOTION_SKILL_SUBSTRINGS",
]
