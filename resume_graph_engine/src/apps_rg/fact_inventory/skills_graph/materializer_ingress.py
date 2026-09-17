"""Ingress stage for skills graph materialization: nodes, edges, promotions."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from apps_rg.fact_inventory.augmented_skills_graph import (
    graph_version_from_payload,
    load_augmented_skills_graph,
)
from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    REGISTERED_GRAPH_EDGE_SIGNATURES,
    default_arsenal_ledger_path,
    derive_registered_graph_endpoint_types as _orig_derive_registered_graph_endpoint_types,
    skill_row_eligible_for_external_claim,
    validate_arsenal_ledger_shape,
)
from apps_rg.fact_inventory.metric_outcome_materializer import (
    metric_outcome_node_and_edge_rows,
)
from .schema import (
    CANONICAL_NODE_TYPES,
    EMPLOYMENT_PHASES,
    EPOCH_ORDINAL,
)
from .constants import (
    FORBIDDEN_SKILL_NODE_IDS,
    NON_PROMOTE_ACTIVATION,
    canonical_career_epoch_and_ordinal,
    project_registered_graph_node_type,
    projected_graph_edge_signature_report,
    projected_registered_graph_edge_signatures,
)
from .storage import (
    _repo_root,
    _require_sidecar_free_atomic_target,
    _sha256_hex,
    _utc_now,
    default_graph_sqlite_path,
)
from .classification import (
    _is_skill_id,
    infer_node_type_from_id,
    resolve_node_type,
)
from .promotions import (
    build_skill_rows_by_id,
    confidence_grade_for_skill_row,
    has_valid_human_confirmed_archive_promotion,
    load_candidate_fact_promotion_registry,
)
from .graph_builder import (
    _confidence_from_node,
    _dedupe_edge_rows,
    _ensure_fact_node,
    _ensure_policy_nodes,
    _executive_summary_eligibility,
    _parse_section_id,
    _redirect_edge_source,
    _skill_external_eligible,
)

def _get_derive_registered_graph_endpoint_types():
    facade = sys.modules.get("apps_rg.fact_inventory.augmented_skills_graph_sqlite")
    return getattr(facade, "derive_registered_graph_endpoint_types", _orig_derive_registered_graph_endpoint_types)

def run_materializer_ingress(
    *,
    graph: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    db_path: Path | None = None,
    json_source_path: Path | None = None,
) -> dict[str, Any]:
    """Execute materializer ingress: parse payload, assemble nodes, edges, promotions."""
    derive_registered_graph_endpoint_types = _get_derive_registered_graph_endpoint_types()
    root = repo_root or _repo_root()
    out_path = db_path or default_graph_sqlite_path(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _require_sidecar_free_atomic_target(out_path)
    payload = graph or load_augmented_skills_graph(repo_root=root)
    validate_arsenal_ledger_shape(payload)
    src_path = json_source_path or default_arsenal_ledger_path(root)
    ledger_hash = _sha256_hex(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    gver = graph_version_from_payload(payload)
    ts = _utc_now()
    skill_rows_by_id = build_skill_rows_by_id(payload)
    registered_endpoint_types = derive_registered_graph_endpoint_types(payload)
    candidate_registry = load_candidate_fact_promotion_registry(root)

    node_rows: dict[str, dict[str, Any]] = {}
    for raw in payload.get("graph_nodes") or []:
        if not isinstance(raw, dict):
            continue
        nid = str(raw.get("node_id") or "").strip()
        if not nid or nid in FORBIDDEN_SKILL_NODE_IDS:
            continue
        ntype = resolve_node_type(nid, str(raw.get("node_type") or ""))
        skill_row = skill_rows_by_id.get(nid) if ntype == "skill" else None
        epoch = ""
        ordinal = None
        act_status = str(raw.get("activation_status") or "")
        conf = (
            confidence_grade_for_skill_row(skill_row, candidate_registry=candidate_registry)
            if skill_row
            else _confidence_from_node(raw, candidate_registry=candidate_registry)
        )
        if ntype == "career_epoch":
            epoch = nid
            ordinal = EPOCH_ORDINAL.get(nid)
            act_status = "ACTIVE"
            conf = "HIGH"
        elif ntype == "employment":
            phases = EMPLOYMENT_PHASES.get(nid)
            ordinal = phases[0] if phases else None
        elif ntype == "skill":
            raw_epoch = skill_row.get("career_epoch") if skill_row else raw.get("career_epoch")
            epoch, ordinal = canonical_career_epoch_and_ordinal(nid, raw_epoch)
        else:
            epoch = str(raw.get("career_epoch") or "")
            ordinal = raw.get("phase_ordinal")

        node_rows[nid] = {
            "node_id": nid,
            "node_type": ntype,
            "label": str(raw.get("label") or nid),
            "description": str(raw.get("description") or ""),
            "activation_status": act_status,
            "support_level": str(raw.get("support_level") or ""),
            "confidence": conf,
            "external_eligible": 0,
            "career_epoch": epoch,
            "phase_ordinal": ordinal,
            "source_authority": "augmented_skills_graph",
            "created_at": ts,
            "updated_at": ts,
        }

    _ensure_policy_nodes(node_rows, payload, ts=ts)

    for profile_key in payload.get("role_family_projection_profiles") or {}:
        if profile_key in node_rows:
            continue
        node_rows[profile_key] = {
            "node_id": profile_key,
            "node_type": "role_family",
            "label": profile_key,
            "description": "Role family projection profile anchor",
            "activation_status": "ACTIVE",
            "support_level": "PROJECTION",
            "confidence": "",
            "external_eligible": 0,
            "career_epoch": "",
            "phase_ordinal": None,
            "source_authority": "augmented_skills_graph",
            "created_at": ts,
            "updated_at": ts,
        }

    edge_by_id: dict[str, dict[str, Any]] = {}
    section_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    skill_fact_rows: list[dict[str, Any]] = []

    for raw in payload.get("graph_edges") or []:
        if not isinstance(raw, dict):
            continue
        eid = str(raw.get("edge_id") or "").strip()
        src = _redirect_edge_source(str(raw.get("source_node_id") or raw.get("source") or "").strip())
        tgt = str(raw.get("target_node_id") or raw.get("target") or "").strip()
        et = str(raw.get("edge_type") or "").strip()
        if not eid or not src or not tgt or not et:
            continue
        if src in FORBIDDEN_SKILL_NODE_IDS:
            continue

        def _ensure_endpoint(endpoint_id: str) -> None:
            eid_s = str(endpoint_id or "").strip()
            if not eid_s or eid_s in node_rows or eid_s in FORBIDDEN_SKILL_NODE_IDS:
                return
            skill_row = skill_rows_by_id.get(eid_s)
            registered_raw_type = registered_endpoint_types.get(eid_s)
            if registered_raw_type == "__type_conflict__":
                raise ValueError(
                    f"registered graph endpoint has conflicting canonical types: endpoint_id={eid_s}"
                )
            ntype = resolve_node_type(
                eid_s,
                ("skill" if skill_row else registered_raw_type or infer_node_type_from_id(eid_s)),
            )
            epoch = ""
            ordinal = None
            act_status = str(skill_row.get("activation_status") if skill_row else "")
            conf = _confidence_from_node({}, skill_row=skill_row) if skill_row else ""
            if ntype == "career_epoch":
                epoch = eid_s
                ordinal = EPOCH_ORDINAL.get(eid_s)
                act_status = "ACTIVE"
                conf = "HIGH"
            elif ntype == "employment":
                phases = EMPLOYMENT_PHASES.get(eid_s)
                ordinal = phases[0] if phases else None
            elif ntype == "skill":
                raw_epoch = skill_row.get("career_epoch") if skill_row else ""
                epoch, ordinal = canonical_career_epoch_and_ordinal(eid_s, raw_epoch)

            node_rows[eid_s] = {
                "node_id": eid_s,
                "node_type": ntype,
                "label": str(skill_row.get("capability") if skill_row else eid_s),
                "description": "",
                "activation_status": act_status,
                "support_level": str(skill_row.get("support_level") if skill_row else ""),
                "confidence": conf,
                "external_eligible": 0,
                "career_epoch": epoch,
                "phase_ordinal": ordinal,
                "source_authority": "augmented_skills_graph",
                "created_at": ts,
                "updated_at": ts,
            }

        _ensure_endpoint(src)
        _ensure_endpoint(tgt)
        weight = float(raw.get("weight") or 1.0)
        edge_conf = str(raw.get("validation_status") or "validated")
        edge_rationale = str(raw.get("rationale") or "")
        edge_claim_policy = str(raw.get("external_claim_policy") or "")
        if et == "epoch_contains_skill":
            edge_conf = "HIGH"
            edge_rationale = str(raw.get("rationale") or f"The career epoch {src} contains skill {tgt}.")
            edge_claim_policy = str(raw.get("external_claim_policy") or "skill_projection_not_proof")

        edge_by_id[eid] = {
            "edge_id": eid,
            "source_node_id": src,
            "target_node_id": tgt,
            "edge_family": str(raw.get("bridge_edge_family") or ""),
            "edge_type": et,
            "weight": weight,
            "confidence": edge_conf,
            "directional": 1 if str(raw.get("direction") or "forward") != "bidirectional" else 0,
            "evidence_status": str(raw.get("validation_status") or ""),
            "section_fit": _parse_section_id(tgt) if tgt.startswith("section_") else "",
            "source_authority": "augmented_skills_graph",
            "rationale": edge_rationale,
            "projection_behavior": str(raw.get("projection_behavior") or ""),
            "external_claim_policy": edge_claim_policy,
            "validation_status": str(raw.get("validation_status") or ""),
            "edge_note": str(raw.get("edge_note") or raw.get("note") or ""),
            "operator_note": str(raw.get("operator_note") or ""),
            "business_story": str(raw.get("business_story") or ""),
            "technical_story": str(raw.get("technical_story") or ""),
        }
        edge_row = edge_by_id[eid]
        et = edge_row["edge_type"]

        def _upsert_section(row: dict[str, Any]) -> None:
            key = (str(row["node_id"]), str(row["section_id"]))
            prior = section_by_key.get(key)
            if prior is None:
                section_by_key[key] = row
                return
            if int(row.get("allowed") or 0) == 0:
                section_by_key[key] = row
            elif int(prior.get("allowed") or 0) == 0:
                return
            section_by_key[key] = row

        if et == "skill_allowed_in_section":
            sec = _parse_section_id(tgt)
            row = skill_rows_by_id.get(src, {})
            if sec == "executive_summary" and row:
                link_n = sum(
                    1
                    for fid in row.get("fact_id_links") or []
                    if str(fid).strip() and not _is_skill_id(str(fid))
                )
                _upsert_section(_executive_summary_eligibility(row, has_fact_link=link_n > 0))
            else:
                blocked = str(row.get("activation_status") or "") in NON_PROMOTE_ACTIVATION
                _upsert_section(
                    {
                        "node_id": src,
                        "section_id": sec,
                        "allowed": 0 if blocked else 1,
                        "claim_policy": str(raw.get("external_claim_policy") or "skill_projection_not_proof"),
                        "reason": str(raw.get("rationale") or "skill_allowed_in_section"),
                        "blocked_reason": "activation_blocked" if blocked else "",
                    }
                )
        elif et == "pillar_section_eligibility":
            sec = _parse_section_id(tgt)
            pillar_allowed = 0 if sec == "executive_summary" else 1
            _upsert_section(
                {
                    "node_id": src,
                    "section_id": sec,
                    "allowed": pillar_allowed,
                    "claim_policy": str(raw.get("external_claim_policy") or "internal_traversal_only"),
                    "reason": str(raw.get("rationale") or "pillar_section_eligibility"),
                    "blocked_reason": "executive_summary_skills_high_only"
                    if sec == "executive_summary"
                    else "",
                }
            )
        elif et in (
            "projection_excludes_blocked_skill",
            "section_blocks_pending_source_skill",
            "section_blocks_skill_without_fact",
        ):
            sec = "executive_summary" if "executive" in eid else ""
            _upsert_section(
                {
                    "node_id": src,
                    "section_id": sec or "*",
                    "allowed": 0,
                    "claim_policy": str(raw.get("external_claim_policy") or "blocked"),
                    "reason": str(raw.get("rationale") or et),
                    "blocked_reason": et,
                }
            )

    skill_link_counts: dict[str, int] = {}
    for sid, row in skill_rows_by_id.items():
        if sid in FORBIDDEN_SKILL_NODE_IDS:
            continue
        epoch, ordinal = canonical_career_epoch_and_ordinal(sid, row.get("career_epoch"))
        if sid not in node_rows:
            node_rows[sid] = {
                "node_id": sid,
                "node_type": "skill",
                "label": str(row.get("capability") or sid),
                "description": "",
                "activation_status": str(row.get("activation_status") or ""),
                "support_level": str(row.get("support_level") or ""),
                "confidence": _confidence_from_node(row, skill_row=row),
                "external_eligible": 0,
                "career_epoch": epoch,
                "phase_ordinal": ordinal,
                "source_authority": "augmented_skills_graph",
                "created_at": ts,
                "updated_at": ts,
            }
        for fid in row.get("fact_id_links") or []:
            fid_s = str(fid).strip()
            if not fid_s or _is_skill_id(fid_s):
                continue
            _ensure_fact_node(node_rows, fid_s, ts=ts)
            skill_link_counts[sid] = skill_link_counts.get(sid, 0) + 1
            claim_ok = _skill_external_eligible(row, has_fact_link=True)
            skill_fact_rows.append(
                {
                    "skill_id": sid,
                    "fact_id": fid_s,
                    "support_level": str(row.get("support_level") or ""),
                    "claim_eligibility": 1 if claim_ok else 0,
                    "source_trace": json.dumps(list(row.get("source_resume_files") or [])[:3]),
                    "archive_trace": "",
                    "human_confirmed": (
                        1
                        if row.get("user_confirmed") or has_valid_human_confirmed_archive_promotion(row)
                        else 0
                    ),
                    "external_eligible": 1 if claim_ok else 0,
                }
            )

    for sid, row in skill_rows_by_id.items():
        if sid in FORBIDDEN_SKILL_NODE_IDS:
            continue
        has_link = skill_link_counts.get(sid, 0) > 0
        grade = confidence_grade_for_skill_row(
            row, has_fact_link=has_link, candidate_registry=candidate_registry
        )
        epoch, ordinal = canonical_career_epoch_and_ordinal(sid, row.get("career_epoch"))
        if sid not in node_rows:
            node_rows[sid] = {
                "node_id": sid,
                "node_type": "skill",
                "label": str(row.get("capability") or sid),
                "description": "",
                "activation_status": str(row.get("activation_status") or ""),
                "support_level": str(row.get("support_level") or ""),
                "confidence": grade,
                "external_eligible": 0,
                "career_epoch": epoch,
                "phase_ordinal": ordinal,
                "source_authority": "augmented_skills_graph",
                "created_at": ts,
                "updated_at": ts,
            }
        else:
            node_rows[sid]["confidence"] = grade
            node_rows[sid]["support_level"] = str(row.get("support_level") or "")
            node_rows[sid]["activation_status"] = str(row.get("activation_status") or "")
            node_rows[sid]["career_epoch"] = epoch
            node_rows[sid]["phase_ordinal"] = ordinal
        node_rows[sid]["external_eligible"] = (
            1 if _skill_external_eligible(row, has_fact_link=has_link) else 0
        )
        section_by_key[(sid, "executive_summary")] = _executive_summary_eligibility(
            row,
            has_fact_link=has_link,
            candidate_registry=candidate_registry,
        )
        for sec_raw in row.get("allowed_sections") or []:
            sec_s = str(sec_raw or "").strip()
            if not sec_s or sec_s == "executive_summary":
                continue
            key = (sid, sec_s)
            prior = section_by_key.get(key)
            if prior is not None and int(prior.get("allowed") or 0) == 0:
                continue
            blocked = str(row.get("activation_status") or "") in NON_PROMOTE_ACTIVATION
            if prior is None:
                section_by_key[key] = {
                    "node_id": sid,
                    "section_id": sec_s,
                    "allowed": 0 if blocked else 1,
                    "claim_policy": str(row.get("external_claim_policy") or "skill_projection_not_proof"),
                    "reason": "skill_row.allowed_sections",
                    "blocked_reason": "activation_blocked" if blocked else "",
                }

    edge_rows = _dedupe_edge_rows(edge_by_id)

    # W2.0 (typed-edge-role-facet-guardrails-a6f3d2): materialize first-class
    # metric_outcome nodes + edges from role_episode_bundle JSON files. New rows
    # are net-additive (node_type="metric_outcome" + 3 new edge_types in
    # METRIC_OUTCOME_EDGE_TYPES) — existing node_type/edge_type queries are
    # unaffected. Validators do not consume these yet; W2.2 migrates consumers
    # to the resolver in metric_outcome_materializer.resolve_metric_outcome_graph_node.
    from apps_rg.fact_inventory.metric_outcome_materializer import (
        metric_outcome_node_and_edge_rows,
    )

    _mo_node_rows, _mo_edge_rows = metric_outcome_node_and_edge_rows(
        root, ts=ts, known_node_ids=set(node_rows.keys())
    )
    for _row in _mo_node_rows:
        _nid = _row["node_id"]
        # Behavior-neutral guard: never overwrite an existing node row. If a
        # metric ID collides with a pre-existing graph node, the bundle JSON is
        # malformed and W2.0 fails closed at materialization.
        if _nid in node_rows:
            raise ValueError(
                f"metric_outcome materialization: id collision with existing graph_node {_nid!r}"
            )
        _row.setdefault("career_epoch", "")
        _row.setdefault("phase_ordinal", None)
        node_rows[_nid] = _row
    for _edge in _mo_edge_rows:
        _ensure_endpoint(str(_edge.get("source_node_id") or ""))
        _ensure_endpoint(str(_edge.get("target_node_id") or ""))
    edge_rows.extend(_mo_edge_rows)
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

    projected_signature_report = projected_graph_edge_signature_report(
        node_types_by_id={node_id: str(row.get("node_type") or "") for node_id, row in node_rows.items()},
        edge_rows=edge_rows,
    )
    if projected_signature_report["failure_count"] or projected_signature_report["unregistered_edge_count"]:
        raise ValueError(
            "projected graph edge signature integrity failed: "
            f"count={projected_signature_report['failure_count']} "
            f"unregistered={projected_signature_report['unregistered_edge_count']} "
            f"failures={projected_signature_report['failure_locators'][:12]}"
        )

    section_rows = list(section_by_key.values())

    return {
        "root": root,
        "out_path": out_path,
        "payload": payload,
        "src_path": src_path,
        "ledger_hash": ledger_hash,
        "gver": gver,
        "ts": ts,
        "skill_rows_by_id": skill_rows_by_id,
        "node_rows": node_rows,
        "edge_rows": edge_rows,
        "skill_fact_rows": skill_fact_rows,
        "section_rows": section_rows,
        "projected_signature_report": projected_signature_report,
    }

__all__ = ["run_materializer_ingress"]
