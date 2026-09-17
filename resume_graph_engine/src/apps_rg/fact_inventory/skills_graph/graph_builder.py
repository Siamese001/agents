"""Graph node and edge builders, policy nodes, and external claim eligibility."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    ROLE_FAMILY_TRACK_WEIGHTS,
    SENIOR_ROLE_TAXONOMY_IDS,
    TAXONOMY_TO_PROJECTION_ROLE,
)
from .schema import CANONICAL_NODE_TYPES
from .constants import (
    BLOCKED_EXTERNAL_CLAIM_POLICIES,
    BLOCKED_SUPPORT_LEVELS,
    CONFIDENCE_GRADES,
    EXTERNAL_ACTIVE_STATUSES,
    FORBIDDEN_SKILL_NODE_IDS,
    NON_PROMOTE_ACTIVATION,
    POLICY_EDGE_SOURCE_KEYS,
    canonical_career_epoch_and_ordinal,
    project_registered_graph_node_type,
    skill_row_eligible_for_external_claim,
)
from .classification import (
    canonical_node_type,
    infer_node_type_from_id,
    resolve_node_type,
)
from .promotions import (
    build_skill_rows_by_id,
    confidence_grade_for_skill_row,
    derive_confidence_grade,
    load_candidate_fact_promotion_registry,
    resolve_confidence_grade,
)

def collect_high_and_exec_summary_counts(
    payload: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Before/after style counts from merged skill rows (no SQLite required)."""
    registry = load_candidate_fact_promotion_registry(repo_root)
    track_high: Counter[str] = Counter()
    exec_allowed = 0
    high_total = 0
    genai_high_skills: list[str] = []
    for sid, row in build_skill_rows_by_id(payload).items():
        if sid in FORBIDDEN_SKILL_NODE_IDS:
            continue
        has_link = bool(row.get("fact_id_links"))
        grade = confidence_grade_for_skill_row(row, has_fact_link=has_link, candidate_registry=registry)
        if grade == "HIGH":
            high_total += 1
            epoch = str(row.get("career_epoch") or "")
            pillar = str(row.get("pillar") or "")
            if "agentic" in epoch or pillar == "pillar_agentic_ai_platforms":
                track_high["track_genai_agentic"] += 1
                genai_high_skills.append(sid)
            elif "partner" in pillar or "gtm" in pillar or "presales" in pillar:
                track_high["track_data_tech_cloud_ml"] += 1
            elif "actuarial" in pillar or "capital" in pillar or "derivatives" in pillar:
                track_high["track_actuarial_risk_derivatives"] += 1
            else:
                track_high["track_data_tech_cloud_ml"] += 1
        elig = _executive_summary_eligibility(
            {**row, "confidence_grade": grade},
            has_fact_link=has_link,
            candidate_registry=registry,
        )
        if elig.get("allowed") == 1:
            exec_allowed += 1
    return {
        "high_skill_count": high_total,
        "high_skills_by_track": dict(track_high),
        "executive_summary_allowed_count": exec_allowed,
        "track_genai_agentic_high_skills": sorted(genai_high_skills),
    }

def _confidence_from_skill_row(
    row: dict[str, Any] | None,
    *,
    has_fact_link: bool = False,
    candidate_registry: dict[str, dict[str, Any]] | None = None,
) -> str:
    if not row:
        return ""
    return confidence_grade_for_skill_row(
        row,
        has_fact_link=has_fact_link,
        candidate_registry=candidate_registry,
    )

def _confidence_from_node(
    node: dict[str, Any],
    *,
    skill_row: dict[str, Any] | None = None,
    has_fact_link: bool = False,
    candidate_registry: dict[str, dict[str, Any]] | None = None,
) -> str:
    if skill_row is not None:
        return confidence_grade_for_skill_row(
            skill_row,
            has_fact_link=has_fact_link,
            candidate_registry=candidate_registry,
        )
    preset = str(node.get("confidence_grade") or node.get("confidence") or "").strip().upper()
    if preset in CONFIDENCE_GRADES:
        return preset
    ntype = str(node.get("node_type") or "")
    if ntype in ("policy", "policy_rule"):
        return ""
    if ntype == "fact":
        return "HIGH"
    return ""

def _policy_rule_node_id(policy_key: str) -> str:
    key = str(policy_key or "").strip()
    if key.startswith("policy_rule_"):
        return key
    return f"policy_rule_{key}"

def _redirect_edge_source(src: str) -> str:
    s = str(src or "").strip()
    if s in POLICY_EDGE_SOURCE_KEYS:
        return _policy_rule_node_id(s)
    return s

def _dedupe_edge_rows(edge_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    seen_triple: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in edge_by_id.values():
        triple = (
            str(row["source_node_id"]),
            str(row["target_node_id"]),
            str(row["edge_type"]),
        )
        if triple in seen_triple:
            continue
        seen_triple.add(triple)
        out.append(row)
    return out

def _ensure_policy_nodes(
    node_rows: dict[str, dict[str, Any]],
    payload: dict[str, Any],
    *,
    ts: str,
) -> None:
    policies = payload.get("external_claim_policies") or {}
    seeds: list[tuple[str, str, str]] = [
        ("policy_external_claim_policy", "policy", "External claim policy anchor"),
        (
            "policy_executive_summary_high_confidence_only",
            "policy",
            "executive_summary: confidence_grade=HIGH + ACTIVE/ACTIVE_CONFIRMED + fact-backed skills only",
        ),
    ]
    if isinstance(policies, dict):
        for key, body in policies.items():
            if not isinstance(key, str) or not key.strip():
                continue
            desc = ""
            if isinstance(body, dict):
                desc = str(body.get("description") or key)
            seeds.append((_policy_rule_node_id(key), "policy_rule", desc or key))
    for nid, ntype, desc in seeds:
        if nid in node_rows:
            continue
        node_rows[nid] = {
            "node_id": nid,
            "node_type": ntype,
            "label": nid,
            "description": desc,
            "activation_status": "ACTIVE",
            "support_level": "POLICY",
            "confidence": "",
            "external_eligible": 0,
            "career_epoch": "",
            "phase_ordinal": None,
            "source_authority": "augmented_skills_graph",
            "created_at": ts,
            "updated_at": ts,
        }

def _executive_summary_eligibility(
    skill_row: dict[str, Any],
    *,
    has_fact_link: bool = False,
    candidate_registry: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sid = str(skill_row.get("skill_id") or "")
    grade = confidence_grade_for_skill_row(
        skill_row,
        has_fact_link=has_fact_link,
        candidate_registry=candidate_registry,
    )
    status = str(skill_row.get("activation_status") or "")
    support = str(skill_row.get("support_level") or "")
    has_links = has_fact_link or bool(skill_row.get("fact_id_links"))

    blocked_activation = status in NON_PROMOTE_ACTIVATION or status == "DRAFT"
    blocked_support = support in BLOCKED_SUPPORT_LEVELS

    if (
        grade == "HIGH"
        and status in EXTERNAL_ACTIVE_STATUSES
        and not blocked_activation
        and not blocked_support
        and has_links
        and skill_row_eligible_for_external_claim(skill_row)
    ):
        return {
            "node_id": sid,
            "section_id": "executive_summary",
            "allowed": 1,
            "claim_policy": "executive_summary_high_confidence_grade_fact_backed",
            "reason": "confidence_grade=HIGH with fact_id_links",
            "blocked_reason": "",
        }
    if not grade or grade not in CONFIDENCE_GRADES:
        return {
            "node_id": sid,
            "section_id": "executive_summary",
            "allowed": 0,
            "claim_policy": "executive_summary_missing_confidence_grade",
            "reason": "Missing confidence_grade (support_level is provenance only)",
            "blocked_reason": "missing_confidence_grade",
        }
    return {
        "node_id": sid,
        "section_id": "executive_summary",
        "allowed": 0,
        "claim_policy": f"executive_summary_blocked_{grade.lower()}",
        "reason": f"executive_summary requires confidence_grade=HIGH; got {grade}",
        "blocked_reason": f"blocked_{grade.lower()}",
    }

def collect_graph_counts(payload: dict[str, Any]) -> dict[str, Any]:
    nodes = [n for n in payload.get("graph_nodes") or [] if isinstance(n, dict)]
    edges = [e for e in payload.get("graph_edges") or [] if isinstance(e, dict)]
    skills = [r for r in payload.get("skill_rows") or [] if isinstance(r, dict)]
    pillars = sum(1 for n in nodes if str(n.get("node_type")) in ("pillar", "domain_pillar"))
    active = sum(1 for r in skills if str(r.get("activation_status")) in EXTERNAL_ACTIVE_STATUSES)
    draft = sum(1 for r in skills if str(r.get("activation_status")) == "DRAFT")
    bridges = sum(1 for e in edges if str(e.get("edge_type")) == "pillar_phase_bridge")
    grade_dist = Counter(str(r.get("confidence_grade") or derive_confidence_grade(r)).upper() for r in skills)
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "pillars": pillars,
        "skills": len(skills),
        "active_skills": active,
        "draft_skills": draft,
        "phase_bridges": bridges,
        "confidence_grade": dict(grade_dist),
    }

def _skill_external_eligible(
    skill_row: dict[str, Any],
    *,
    has_fact_link: bool,
) -> bool:
    if str(skill_row.get("skill_id") or "") in FORBIDDEN_SKILL_NODE_IDS:
        return False
    status = str(skill_row.get("activation_status") or "")
    if status not in EXTERNAL_ACTIVE_STATUSES:
        return False
    if status in NON_PROMOTE_ACTIVATION:
        return False
    if not has_fact_link:
        return False
    return skill_row_eligible_for_external_claim(skill_row)

def _external_eligible_node(
    node: dict[str, Any],
    *,
    skill_row: dict[str, Any] | None = None,
    has_fact_link: bool = False,
) -> bool:
    nid = str(node.get("node_id") or "")
    if nid in FORBIDDEN_SKILL_NODE_IDS:
        return False
    ntype = str(node.get("node_type") or "")
    if ntype in ("policy", "policy_rule", "section", "concept", "graph_ref"):
        return False
    if skill_row is not None:
        return _skill_external_eligible(skill_row, has_fact_link=has_fact_link)
    policy = str(node.get("external_claim_policy") or "")
    if policy in (
        "pending_source_internal_only",
        "weak_snippet_internal_only",
        "repo_portfolio_not_resume_default",
        "skill_projection_not_proof",
        "internal_traversal_only",
    ):
        return False
    status = str(node.get("activation_status") or "")
    if status in NON_PROMOTE_ACTIVATION:
        return False
    return False

def _parse_section_id(target: str) -> str:
    tgt = str(target or "").strip()
    if tgt.startswith("section_"):
        return tgt.removeprefix("section_")
    return tgt

def _ensure_fact_node(
    nodes: dict[str, dict[str, Any]],
    fact_id: str,
    *,
    ts: str,
) -> None:
    fid = str(fact_id or "").strip()
    if not fid or fid in nodes:
        return
    nodes[fid] = {
        "node_id": fid,
        "node_type": "fact",
        "label": fid,
        "description": "Atomic proof fact node (routing only; proof via SRFS/candidate ledger)",
        "activation_status": "ACTIVE",
        "support_level": "FACT_SUBSTRATE",
        "confidence": "HIGH",
        "external_eligible": 0,
        "career_epoch": "",
        "phase_ordinal": None,
        "source_authority": "augmented_skills_graph",
        "created_at": ts,
        "updated_at": ts,
    }

def _resolve_projection_pillar_hints(
    role_family_key: str,
    *,
    taxonomy: dict[str, Any],
) -> tuple[str, ...]:
    """Lightweight C0.3 pillar hint resolver for offline SQLite materialization."""
    projection_to_taxonomy = {v: k for k, v in TAXONOMY_TO_PROJECTION_ROLE.items()}
    tax_id = projection_to_taxonomy.get(role_family_key, role_family_key)
    for row in taxonomy.get("role_families") or []:
        if isinstance(row, dict) and str(row.get("id") or "") == tax_id:
            raw = row.get("proposed_pillar_ids") or []
            return tuple(str(p).strip() for p in raw if str(p).strip())
    return ()


__all__ = ['collect_high_and_exec_summary_counts', '_confidence_from_skill_row', '_confidence_from_node', '_policy_rule_node_id', '_redirect_edge_source', '_dedupe_edge_rows', '_ensure_policy_nodes', '_executive_summary_eligibility', 'collect_graph_counts', '_skill_external_eligible', '_external_eligible_node', '_parse_section_id', '_ensure_fact_node', '_resolve_projection_pillar_hints']
