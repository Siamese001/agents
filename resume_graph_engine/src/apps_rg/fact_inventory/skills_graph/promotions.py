"""Candidate fact promotion registry, audit decisions, and operator archive promotion."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from apps_rg.fact_inventory.master_skills_arsenal_ledger import skill_row_eligible_for_external_claim
from .constants import (
    BLOCKED_EXTERNAL_CLAIM_POLICIES,
    BLOCKED_SUPPORT_LEVELS,
    CANDIDATE_LEDGER_REL_PATH,
    CONFIDENCE_GRADES,
    CONFIDENCE_GRADE_RANK,
    ENGINEERING_PLATFORM_CANDIDATE_FACT_IDS,
    FORBIDDEN_PROMOTION_SKILL_SUBSTRINGS,
    FORBIDDEN_SKILL_NODE_IDS,
    HUMAN_CONFIRM_REQUIRED_ALLOWED_RESUME_USE,
    NON_PROMOTE_ACTIVATION,
    OPERATOR_ARCHIVE_PROMOTION_BY_SKILL,
    OPERATOR_CONFIRMED_ARCHIVE_FACT_IDS,
    THEME_AGENTIC_SKILL_IDS,
)
from .classification import (
    _is_skill_id,
    canonical_node_type,
    default_candidate_fact_ledger_path,
)
from .storage import _repo_root, _utc_now

def derive_confidence_grade(
    row: dict[str, Any],
    *,
    has_fact_link: bool = False,
) -> str:
    """Map provenance support_level + activation to confidence_grade (not support_level overload)."""
    visibility = str(row.get("visibility_rule") or "").strip()
    if visibility == "never_external":
        return "BLOCKED"
    policy = str(row.get("external_claim_policy") or "").strip()
    if policy in BLOCKED_EXTERNAL_CLAIM_POLICIES:
        return "BLOCKED"
    support = str(row.get("support_level") or "").strip()
    if support in BLOCKED_SUPPORT_LEVELS:
        return "BLOCKED"
    status = str(row.get("activation_status") or "").strip()
    if status in ("BLOCKED", "DO_NOT_PROMOTE"):
        return "BLOCKED"
    links = row.get("fact_id_links") or []
    has_link = has_fact_link or bool(links)

    if status == "ACTIVE_CONFIRMED" and has_link:
        if support == "DIRECT_FROM_RESUME_ARCHIVE":
            return "HIGH"
        if support == "BUNDLE_SUPPORTED" and skill_row_eligible_for_external_claim(row):
            return "HIGH"
    if status == "ACTIVE" and support == "DERIVED_SUPPORTED" and has_link:
        return "MEDIUM"
    if status == "DRAFT" and support in ("DIRECT_FROM_RESUME_ARCHIVE", "DERIVED_SUPPORTED"):
        return "LOW"
    if status == "ACTIVE" and support == "DIRECT_FROM_RESUME_ARCHIVE" and has_link:
        return "MEDIUM"
    if status == "ACTIVE_CONFIRMED" and support == "DERIVED_SUPPORTED" and has_link:
        return "MEDIUM"
    return "BLOCKED"

def cap_derived_grade_for_candidate_facts(
    row: dict[str, Any],
    derived: str,
    *,
    candidate_registry: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Prevent candidate-only facts from yielding HIGH without human confirmation."""
    if derived != "HIGH":
        return derived
    if skill_links_only_engineering_candidate_pending_confirm(row, candidate_registry):
        return "MEDIUM"
    return derived

def resolve_confidence_grade(
    row: dict[str, Any],
    *,
    has_fact_link: bool = False,
    candidate_registry: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve effective grade with override guardrails and candidate-fact cap."""
    derived = derive_confidence_grade(row, has_fact_link=has_fact_link)
    derived = cap_derived_grade_for_candidate_facts(row, derived, candidate_registry=candidate_registry)
    preset = str(row.get("confidence_grade") or "").strip().upper()
    override_blocked_reason = ""
    effective = derived
    if preset in CONFIDENCE_GRADES:
        preset_rank = CONFIDENCE_GRADE_RANK.get(preset, -1)
        derived_rank = CONFIDENCE_GRADE_RANK.get(derived, -1)
        if preset_rank > derived_rank:
            if has_valid_human_confirmed_archive_promotion(row):
                effective = preset
            else:
                effective = derived
                override_blocked_reason = "confidence_override_blocked_missing_human_confirmation"
        else:
            # Stale lower presets must not suppress proof-derived grades.
            effective = derived
    return {
        "derived_grade": derived,
        "effective_grade": effective,
        "preset_grade": preset if preset in CONFIDENCE_GRADES else "",
        "override_blocked_reason": override_blocked_reason,
        "human_confirmed_archive_promotion": has_valid_human_confirmed_archive_promotion(row),
        "candidate_pending_only": skill_links_only_engineering_candidate_pending_confirm(
            row, candidate_registry
        ),
    }

def confidence_grade_for_skill_row(
    row: dict[str, Any],
    *,
    has_fact_link: bool = False,
    candidate_registry: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Effective confidence_grade: derived proof or explicit human-confirmed override only."""
    return resolve_confidence_grade(
        row,
        has_fact_link=has_fact_link,
        candidate_registry=candidate_registry,
    )["effective_grade"]

def classify_skill_archive_promotion(
    row: dict[str, Any],
    *,
    candidate_registry: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Promotion decision enum for governed agentic/platform skills."""
    sid = str(row.get("skill_id") or "")
    support = str(row.get("support_level") or "")
    activation = str(row.get("activation_status") or "")
    links = list(row.get("fact_id_links") or [])

    if has_valid_human_confirmed_archive_promotion(row):
        return "PROMOTE_NOW_HUMAN_CONFIRMED"
    if support in BLOCKED_SUPPORT_LEVELS or activation in NON_PROMOTE_ACTIVATION:
        if support == "REPO_EVIDENCE_PORTFOLIO" or (activation == "DRAFT" and not links):
            return "KEEP_BLOCKED_REPO_ONLY"
        return "KEEP_BLOCKED_REPO_ONLY"
    if sid == "skill_runtime_gate_mesh_design":
        primary = str(row.get("primary_fact_id") or "")
        if primary == "fact_engineering_platform_001":
            return "SEMANTIC_REWIRE_ONLY"
        if "fact_governance_003" in links and "fact_engineering_platform_001" not in links:
            return "SEMANTIC_REWIRE_READY"
    if not links:
        return "KEEP_MEDIUM_NEEDS_ARCHIVE_LINK"
    if skill_links_only_engineering_candidate_pending_confirm(row, candidate_registry):
        return "PROMOTION_READY_NEEDS_HUMAN_CONFIRM"
    return "KEEP_MEDIUM_NEEDS_ARCHIVE_LINK"

def load_candidate_fact_promotion_registry(
    repo_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load candidate-fact promotion metadata; does not auto-promote skills."""
    path = default_candidate_fact_ledger_path(repo_root)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for raw in payload.get("candidate_facts") or []:
        if not isinstance(raw, dict):
            continue
        fid = str(raw.get("candidate_fact_id") or "").strip()
        if not fid:
            continue
        allowed = str(raw.get("allowed_resume_use") or "").strip()
        human_records = raw.get("human_confirmed_archive_promotions") or []
        has_human = bool(
            raw.get("human_confirmed_archive_promotion")
            or (isinstance(human_records, list) and human_records)
        )
        out[fid] = {
            "candidate_fact_id": fid,
            "candidate_confidence": str(raw.get("confidence") or ""),
            "allowed_resume_use": allowed,
            "source_resume_variants": list(raw.get("source_resume_variants") or []),
            "capability_tags": list(raw.get("capability_tags") or []),
            "claim_text": str(raw.get("claim_text") or ""),
            "ledger_status": str(payload.get("status") or ""),
            "has_explicit_human_confirmation": has_human,
            "promotion_status": (
                "PROMOTE_NOW"
                if has_human
                else "PROMOTION_READY_NEEDS_HUMAN_CONFIRM"
                if allowed in HUMAN_CONFIRM_REQUIRED_ALLOWED_RESUME_USE
                else "NEEDS_REVIEW"
            ),
        }
    return out

def parse_human_confirmed_archive_promotion(row: dict[str, Any]) -> dict[str, Any] | None:
    promo = row.get("human_confirmed_archive_promotion")
    if not isinstance(promo, dict):
        return None
    required = (
        "human_confirmed_by",
        "human_confirmed_at",
        "source_fact_ids",
        "override_reason",
    )
    if not all(str(promo.get(k) or "").strip() for k in required):
        return None
    source_ids = promo.get("source_fact_ids")
    if not isinstance(source_ids, list) or not source_ids:
        return None
    return promo

def has_valid_human_confirmed_archive_promotion(row: dict[str, Any]) -> bool:
    return parse_human_confirmed_archive_promotion(row) is not None

def skill_links_only_engineering_candidate_pending_confirm(
    row: dict[str, Any],
    candidate_registry: dict[str, dict[str, Any]] | None,
) -> bool:
    """True when every linked fact is an engineering-platform candidate awaiting human confirm.

    Does not cap skills anchored to governance/GTM/archive facts that already meet HIGH derivation.
    """
    if has_valid_human_confirmed_archive_promotion(row):
        return False
    registry = candidate_registry or {}
    links = [str(x).strip() for x in (row.get("fact_id_links") or []) if str(x).strip()]
    if not links:
        return False
    if not all(fid in ENGINEERING_PLATFORM_CANDIDATE_FACT_IDS for fid in links):
        return False
    return all(
        registry.get(fid, {}).get("promotion_status") == "PROMOTION_READY_NEEDS_HUMAN_CONFIRM"
        for fid in links
    )

def audit_candidate_fact_promotions(
    payload: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Graph-only promotion plan for engineering-platform candidate facts."""
    registry = load_candidate_fact_promotion_registry(repo_root)
    skill_rows = {
        str(r["skill_id"]): r
        for r in payload.get("skill_rows") or []
        if isinstance(r, dict) and r.get("skill_id")
    }
    for r in payload.get("agentic_runtime_matrix") or []:
        if isinstance(r, dict) and r.get("skill_id"):
            sid = str(r["skill_id"])
            if sid not in skill_rows:
                skill_rows[sid] = r
            else:
                links = set(skill_rows[sid].get("fact_id_links") or [])
                links.update(r.get("fact_id_links") or [])
                skill_rows[sid]["fact_id_links"] = sorted(links)
    audits: list[dict[str, Any]] = []
    for fid in sorted(ENGINEERING_PLATFORM_CANDIDATE_FACT_IDS):
        meta = registry.get(fid, {})
        linked = sorted(sid for sid, row in skill_rows.items() if fid in (row.get("fact_id_links") or []))
        audits.append(
            {
                "candidate_fact_id": fid,
                "candidate_confidence": meta.get("candidate_confidence", ""),
                "allowed_resume_use": meta.get("allowed_resume_use", ""),
                "source_resume_variants": meta.get("source_resume_variants", []),
                "capability_tags": meta.get("capability_tags", []),
                "eligible_linked_skills": linked,
                "promotion_decision": meta.get("promotion_status", "UNKNOWN"),
                "PROMOTE_NOW": meta.get("promotion_status") == "PROMOTE_NOW",
                "PROMOTION_READY_NEEDS_HUMAN_CONFIRM": meta.get("promotion_status")
                == "PROMOTION_READY_NEEDS_HUMAN_CONFIRM",
            }
        )
    return audits

def audit_theme_skill_promotion_decisions(
    payload: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    registry = load_candidate_fact_promotion_registry(repo_root)
    skill_rows = {
        str(r["skill_id"]): r
        for r in payload.get("skill_rows") or []
        if isinstance(r, dict) and r.get("skill_id")
    }
    for r in payload.get("agentic_runtime_matrix") or []:
        if isinstance(r, dict) and r.get("skill_id"):
            skill_rows.setdefault(str(r["skill_id"]), r)
    out: list[dict[str, Any]] = []
    for sid in sorted(THEME_AGENTIC_SKILL_IDS):
        row = skill_rows.get(sid)
        if not row:
            out.append({"skill_id": sid, "decision": "MISSING_SKILL_ROW"})
            continue
        resolved = resolve_confidence_grade(
            row,
            has_fact_link=bool(row.get("fact_id_links")),
            candidate_registry=registry,
        )
        out.append(
            {
                "skill_id": sid,
                "decision": classify_skill_archive_promotion(row, candidate_registry=registry),
                "confidence_grade_derived": resolved["derived_grade"],
                "confidence_grade_effective": resolved["effective_grade"],
                "activation_status": row.get("activation_status"),
                "support_level": row.get("support_level"),
                "fact_id_links": list(row.get("fact_id_links") or []),
                "primary_fact_id": row.get("primary_fact_id"),
                "override_blocked_reason": resolved["override_blocked_reason"],
            }
        )
    return out

def build_skill_rows_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Merge skill_rows SSOT with agentic_runtime_matrix (agentic wins on collision)."""
    out: dict[str, dict[str, Any]] = {}
    for r in payload.get("skill_rows") or []:
        if isinstance(r, dict) and r.get("skill_id"):
            out[str(r["skill_id"])] = r
    for r in payload.get("agentic_runtime_matrix") or []:
        if isinstance(r, dict) and r.get("skill_id"):
            out[str(r["skill_id"])] = r
    return out

def _reject_operator_promotion_reason(row: dict[str, Any], fact_ids: list[str]) -> str:
    sid = str(row.get("skill_id") or "")
    if any(tok in sid.lower() for tok in FORBIDDEN_PROMOTION_SKILL_SUBSTRINGS):
        return f"forbidden_skill_id_pattern:{sid}"
    support = str(row.get("support_level") or "")
    activation = str(row.get("activation_status") or "")
    if support in BLOCKED_SUPPORT_LEVELS:
        return f"blocked_support_level:{support}"
    if activation in NON_PROMOTE_ACTIVATION:
        return f"blocked_activation_status:{activation}"
    if str(row.get("visibility_rule") or "") == "never_external":
        return "never_external_visibility"
    policy = str(row.get("external_claim_policy") or "")
    if policy in BLOCKED_EXTERNAL_CLAIM_POLICIES:
        return f"blocked_external_claim_policy:{policy}"
    if not fact_ids:
        return "missing_confirmed_fact_ids"
    for fid in fact_ids:
        if fid not in OPERATOR_CONFIRMED_ARCHIVE_FACT_IDS:
            return f"fact_not_operator_confirmed:{fid}"
    if any(_is_skill_id(str(x)) for x in fact_ids):
        return "invalid_fact_id_links_skill_id_shape"
    return ""

def _sync_skill_row_to_payload_collections(
    payload: dict[str, Any],
    row: dict[str, Any],
) -> None:
    """Keep graph_nodes / agentic_runtime_matrix / skill_rows aligned for one skill."""
    sid = str(row.get("skill_id") or "")
    if not sid:
        return
    for collection, key in (
        ("agentic_runtime_matrix", "skill_id"),
        ("graph_nodes", "node_id"),
    ):
        for existing in payload.get(collection) or []:
            if isinstance(existing, dict) and str(existing.get(key)) == sid:
                existing.update(row)
    skill_rows = payload.setdefault("skill_rows", [])
    found = False
    for i, existing in enumerate(skill_rows):
        if isinstance(existing, dict) and str(existing.get("skill_id")) == sid:
            skill_rows[i] = {**existing, **row}
            found = True
            break
    if not found:
        skill_rows.append(dict(row))

def _rewire_skill_fact_edges(
    payload: dict[str, Any],
    skill_id: str,
    fact_ids: list[str],
) -> int:
    """Ensure skill_supported_by_fact edges target operator-confirmed facts only."""
    rewritten = 0
    primary = fact_ids[0] if fact_ids else ""
    keep_ids = set(fact_ids)
    edges = payload.get("graph_edges") or []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if str(edge.get("edge_type")) != "skill_supported_by_fact":
            continue
        if str(edge.get("source_node_id")) != skill_id:
            continue
        tgt = str(edge.get("target_node_id") or "")
        if tgt in keep_ids:
            continue
        if primary:
            edge["target_node_id"] = primary
            edge["edge_id"] = f"edge_skill_fact_{skill_id}_{primary}"
            edge["rationale"] = "Operator-confirmed archive promotion anchor"
            rewritten += 1
    for fid in fact_ids:
        eid = f"edge_skill_fact_{skill_id}_{fid}"
        if any(isinstance(e, dict) and str(e.get("edge_id")) == eid for e in edges):
            continue
        edges.append(
            {
                "edge_id": eid,
                "edge_type": "skill_supported_by_fact",
                "source_node_id": skill_id,
                "target_node_id": fid,
                "rationale": "Operator-confirmed archive promotion anchor",
                "projection_behavior": "graph_traversal",
                "external_claim_policy": "atomic_fact_default_external_proof",
                "validation_status": "validated",
            }
        )
        rewritten += 1
    return rewritten

def apply_operator_archive_promotions(
    payload: dict[str, Any],
    *,
    human_confirmed_by: str = "Amit Ayer",
    human_confirmed_at: str | None = None,
) -> dict[str, Any]:
    """Apply bounded operator-confirmed archive promotions (graph metadata only)."""
    ts = human_confirmed_at or _utc_now()
    rows_by_id = build_skill_rows_by_id(payload)
    promoted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    human_records: list[dict[str, Any]] = []

    for skill_id, fact_ids in OPERATOR_ARCHIVE_PROMOTION_BY_SKILL.items():
        row = rows_by_id.get(skill_id)
        if not row:
            rejected.append({"skill_id": skill_id, "reason": "missing_skill_row"})
            continue
        clean_facts = [str(x).strip() for x in fact_ids if str(x).strip()]
        reason = _reject_operator_promotion_reason(row, clean_facts)
        if reason:
            rejected.append({"skill_id": skill_id, "reason": reason})
            continue

        record = {
            "human_confirmed_by": human_confirmed_by,
            "human_confirmed_at": ts,
            "source_fact_ids": clean_facts,
            "override_reason": "archive_snippet_verified_by_operator",
        }
        row["human_confirmed_archive_promotion"] = record
        row["fact_id_links"] = clean_facts
        row["primary_fact_id"] = clean_facts[0]
        row["activation_status"] = "ACTIVE_CONFIRMED"
        row["support_level"] = "DIRECT_FROM_RESUME_ARCHIVE"
        row["user_confirmed"] = True
        row["operator_archive_promotion_applied_at"] = ts
        row.pop("confidence_override_blocked", None)
        row.pop("confidence_grade_override_attempted", None)
        row.pop("confidence_override_blocked_reason", None)

        registry = load_candidate_fact_promotion_registry()
        resolved = resolve_confidence_grade(row, has_fact_link=True, candidate_registry=registry)
        row["confidence_grade_derived"] = resolved["derived_grade"]
        row["confidence_grade"] = resolved["effective_grade"]

        _sync_skill_row_to_payload_collections(payload, row)
        edge_n = _rewire_skill_fact_edges(payload, skill_id, clean_facts)
        rows_by_id[skill_id] = row

        promoted.append(
            {
                "skill_id": skill_id,
                "fact_id_links": clean_facts,
                "confidence_grade": row["confidence_grade"],
                "activation_status": row["activation_status"],
                "support_level": row["support_level"],
                "edges_rewired": edge_n,
            }
        )
        human_records.append({"skill_id": skill_id, **record})

    gm = payload.setdefault("graph_metadata", {})
    if isinstance(gm, dict):
        gm["operator_archive_promotion_wave"] = {
            "applied_at": ts,
            "human_confirmed_by": human_confirmed_by,
            "confirmed_fact_ids": sorted(OPERATOR_CONFIRMED_ARCHIVE_FACT_IDS),
            "promoted_skill_count": len(promoted),
            "rejected_skill_count": len(rejected),
        }

    return {
        "promoted": promoted,
        "rejected": rejected,
        "human_confirmation_records": human_records,
    }


__all__ = ['derive_confidence_grade', 'cap_derived_grade_for_candidate_facts', 'resolve_confidence_grade', 'confidence_grade_for_skill_row', 'classify_skill_archive_promotion', 'load_candidate_fact_promotion_registry', 'parse_human_confirmed_archive_promotion', 'has_valid_human_confirmed_archive_promotion', 'skill_links_only_engineering_candidate_pending_confirm', 'audit_candidate_fact_promotions', 'audit_theme_skill_promotion_decisions', 'build_skill_rows_by_id', '_reject_operator_promotion_reason', '_sync_skill_row_to_payload_collections', '_rewire_skill_fact_edges', 'apply_operator_archive_promotions']
