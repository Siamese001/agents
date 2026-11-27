"""Indexing stage: metric outcomes, clusters, selection features, and evidence budgets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.candidate_fact_ledger import load_master_role_family_taxonomy
from apps_rg.fact_inventory.graph_metric_heterogeneity_policy import (
    POLICY_VERSION as C03_METRIC_POLICY_VERSION,
    metric_bucket_for_row,
)
from apps_rg.fact_inventory.graph_sqlite_path_index import (
    GRAPH_INDEX_SCHEMA_VERSION,
    build_graph_index_rows,
)
from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    ROLE_FAMILY_TRACK_WEIGHTS,
    SENIOR_ROLE_TAXONOMY_IDS,
)
from .constants import (
    C03_SQLITE_MATERIALIZER_CODE_VERSION,
    FORBIDDEN_SKILL_NODE_IDS,
    canonical_career_epoch_and_ordinal,
)
from .classification import _is_skill_id
from .graph_builder import _resolve_projection_pillar_hints

def run_materializer_indexing(ctx: dict[str, Any]) -> None:
    """Compute metric outcomes, clusters, section features, and graph summary."""
    root = ctx["root"]
    repo_root = root
    out_path = ctx["out_path"]
    payload = ctx["payload"]
    skill_rows_by_id = ctx["skill_rows_by_id"]
    node_rows = ctx["node_rows"]
    edge_rows = ctx["edge_rows"]
    section_rows = ctx["section_rows"]
    skill_fact_rows = ctx["skill_fact_rows"]
    projected_signature_report = ctx["projected_signature_report"]
    ts = ctx["ts"]
    gver = ctx["gver"]
    ledger_hash = ctx["ledger_hash"]
    src_path = ctx["src_path"]

    from apps_rg.fact_inventory.graph_metric_heterogeneity_policy import (
        POLICY_VERSION as C03_METRIC_POLICY_VERSION,
    )
    from apps_rg.fact_inventory.graph_metric_heterogeneity_policy import (
        metric_bucket_for_row,
    )

    allowed_sections_by_skill: dict[str, list[str]] = {}
    for row in section_rows:
        if int(row.get("allowed") or 0) != 1:
            continue
        sid = str(row.get("node_id") or "").strip()
        sec = str(row.get("section_id") or "").strip()
        if sid and sec:
            allowed_sections_by_skill.setdefault(sid, []).append(sec)

    skill_epoch_link_rows = ctx.get("skill_epoch_link_rows") or []
    skill_employment_link_rows = ctx.get("skill_employment_link_rows") or []
    epochs_by_skill: dict[str, list[dict[str, Any]]] = {}
    for _el in skill_epoch_link_rows:
        epochs_by_skill.setdefault(str(_el["skill_id"]), []).append(_el)
    emps_by_skill: dict[str, list[dict[str, Any]]] = {}
    for _em in skill_employment_link_rows:
        emps_by_skill.setdefault(str(_em["skill_id"]), []).append(_em)

    def _ym_to_years(ym: str) -> float | None:
        s = str(ym or "").strip()
        if not s:
            return None
        parts = s.split("-")
        try:
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 6
            return year + (month - 1) / 12.0
        except (ValueError, IndexError):
            return None

    selection_feature_rows: list[dict[str, Any]] = []
    role_family_skill_weight_rows: list[dict[str, Any]] = []
    for sid, row in skill_rows_by_id.items():
        if sid in FORBIDDEN_SKILL_NODE_IDS or sid not in node_rows:
            continue
        fact_ids = [
            str(fid).strip()
            for fid in row.get("fact_id_links") or []
            if str(fid).strip() and not _is_skill_id(str(fid))
        ]
        pillar = str(row.get("pillar") or "").strip()
        domain_id = str(row.get("domain_id") or row.get("domain") or "").strip()
        subpillar = str(row.get("subpillar") or "").strip()
        family = pillar or domain_id or subpillar or "unclassified"
        raw_track = str(row.get("career_track_id") or "").strip()
        track_mapping = {
            "TRACK_ACTUARIAL_RISK_DERIVATIVES": "track_actuarial_risk_derivatives",
            "TRACK_DATA_TECH_CLOUD_ML": "track_data_tech_cloud_ml",
            "TRACK_GENAI_AGENTIC": "track_genai_agentic",
            "TRACK_ENTERPRISE_GTM_SALES": "track_data_tech_cloud_ml",
            "TRACK_REVENUE_OPERATIONS": "track_data_tech_cloud_ml",
            "TRACK_ENGINEERING_PLATFORM": "track_data_tech_cloud_ml",
            "TRACK_STRATEGIC_FINANCE": "track_data_tech_cloud_ml",
            "TRACK_PARTNERSHIPS_GTM": "track_data_tech_cloud_ml",
            "TRACK_BANKING_PLATFORM_AI": "track_data_tech_cloud_ml",
            "TRACK_CUSTOMER_SUCCESS": "track_data_tech_cloud_ml",
        }
        canonical_track_id = track_mapping.get(
            raw_track, raw_track.lower() if raw_track.startswith("track_") else "track_data_tech_cloud_ml"
        )
        epoch, ordinal = canonical_career_epoch_and_ordinal(sid, row.get("career_epoch"))
        sk_epochs = epochs_by_skill.get(sid) or []
        sk_emps = emps_by_skill.get(sid) or []
        ep_ordinals = [
            int(e["phase_ordinal"]) for e in sk_epochs if e.get("phase_ordinal") is not None
        ]
        if not ep_ordinals and ordinal is not None:
            ep_ordinals = [int(ordinal)]
        span_start_ord = min(ep_ordinals) if ep_ordinals else ordinal
        span_end_ord = max(ep_ordinals) if ep_ordinals else ordinal
        epoch_recurrence = max(1, len({str(e["epoch_id"]) for e in sk_epochs if e.get("epoch_id")}))
        start_vals = [v for e in sk_emps if (v := _ym_to_years(str(e.get("start_date") or ""))) is not None]
        end_vals = [
            (2026.9 if not str(e.get("end_date") or "").strip() else _ym_to_years(str(e.get("end_date") or "")))
            for e in sk_emps
        ]
        end_vals_clean = [v for v in end_vals if v is not None]
        tenure_span_years = (
            round(max(0.5, max(end_vals_clean) - min(start_vals)), 1)
            if start_vals and end_vals_clean
            else 0.0
        )
        last_ex_dates = [str(e.get("last_exercised_date") or "") for e in sk_emps if str(e.get("last_exercised_date") or "")]
        last_exercised_date = max(last_ex_dates) if last_ex_dates else ""
        employers_list = sorted({str(e.get("employer") or "") for e in sk_emps if str(e.get("employer") or "")})
        selection_feature_rows.append(
            {
                "skill_id": sid,
                "pillar": pillar,
                "subpillar": subpillar,
                "domain_id": domain_id,
                "career_track_id": canonical_track_id,
                "career_epoch": epoch,
                "phase_ordinal": ordinal,
                "span_start_ordinal": span_start_ord,
                "span_end_ordinal": span_end_ord,
                "epoch_recurrence_count": epoch_recurrence,
                "tenure_span_years": tenure_span_years,
                "last_exercised_date": last_exercised_date,
                "employers_json": json.dumps(employers_list),
                "skill_family": family,
                "metric_bucket": metric_bucket_for_row(row),
                "role_family_weights": json.dumps(row.get("role_family_weights") or {}, sort_keys=True),
                "allowed_sections": json.dumps(
                    sorted(set(allowed_sections_by_skill.get(sid) or row.get("allowed_sections") or []))
                ),
                "source_fact_count": len(fact_ids),
                "confidence": str(node_rows[sid].get("confidence_tier") or node_rows[sid].get("confidence") or ""),
                "confidence_score": node_rows[sid].get("confidence_score"),
                "confidence_tier": str(node_rows[sid].get("confidence_tier") or "UNSCORED"),
                "activation_status": str(node_rows[sid].get("activation_status") or ""),
                "support_level": str(node_rows[sid].get("support_level") or ""),
                "external_eligible": int(node_rows[sid].get("external_eligible") or 0),
                "source_authority": "augmented_skills_graph",
                "source_trace": json.dumps(list(row.get("source_resume_files") or [])[:5]),
                "updated_at": ts,
            }
        )
        weights = row.get("role_family_weights") or {}
        if isinstance(weights, dict):
            for role_family_key, weight in weights.items():
                rf_key = str(role_family_key or "").strip()
                if rf_key == "CTO_FIELD_CTO":
                    rf_key = "FIELD_CTO"
                if not rf_key:
                    continue
                try:
                    weight_f = float(weight)
                except (TypeError, ValueError):
                    continue
                role_family_skill_weight_rows.append(
                    {
                        "skill_id": sid,
                        "role_family_key": rf_key,
                        "weight": weight_f,
                        "source": "skill_row.role_family_weights",
                    }
                )

    projection_rows: list[dict[str, Any]] = []
    profiles = payload.get("role_family_projection_profiles") or {}
    from apps_rg.fact_inventory.candidate_fact_ledger import load_master_role_family_taxonomy

    tax = load_master_role_family_taxonomy(repo_root=repo_root)
    for rf_key in ROLE_FAMILY_TRACK_WEIGHTS:
        if rf_key in profiles:
            continue
        if rf_key not in SENIOR_ROLE_TAXONOMY_IDS:
            continue
        pillar_ids = list(_resolve_projection_pillar_hints(rf_key, taxonomy=tax))
        weights = ROLE_FAMILY_TRACK_WEIGHTS.get(rf_key, {})
        profiles[rf_key] = {
            "label": rf_key.replace("_", " ").title(),
            "taxonomy_ids": [rf_key],
            "top_weighted_pillars": [
                {"pillar_id": pid, "weight": round(1.0 - (i * 0.08), 2)}
                for i, pid in enumerate(pillar_ids[:6])
            ],
            "synthesized_for_sqlite": True,
        }
    for rf_key, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        weights = ROLE_FAMILY_TRACK_WEIGHTS.get(rf_key, {})
        note = "graph_routing_not_claim_proof"
        if rf_key == "ANTHROPIC_PARTNERSHIPS_APPLIED_AI":
            note = (
                "graph_routing_not_claim_proof;"
                " marketplace_listing_claims_blocked;"
                " pillars_include_hyperscaler_marketplace_and_applied_ai_partner_architecture"
            )
        projection_rows.append(
            {
                "role_family_id": rf_key,
                "projection_role_family_key": rf_key,
                "track_weight_profile": json.dumps(weights, sort_keys=True),
                "taxonomy_source": json.dumps(list(prof.get("taxonomy_ids") or [])),
                "targeting_keywords": json.dumps(list(prof.get("top_weighted_pillars") or [])[:8]),
                "proof_policy_note": note,
            }
        )

    # Reconcile c03_role_family_skill_weights onto every canonical projection key so zero
    # role_family_projection profiles have 0 skill-weight rows at runtime.
    weight_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for wrow in role_family_skill_weight_rows:
        pair = (str(wrow["skill_id"]), str(wrow["role_family_key"]))
        prev = weight_by_pair.get(pair)
        if prev is None or float(wrow["weight"]) > float(prev["weight"]):
            weight_by_pair[pair] = wrow

    skill_weights_by_tax: dict[str, list[tuple[str, float]]] = {}
    for wrow in list(weight_by_pair.values()):
        skill_weights_by_tax.setdefault(str(wrow["role_family_key"]), []).append(
            (str(wrow["skill_id"]), float(wrow["weight"]))
        )

    for rf_key, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        tax_ids = [str(tid).strip() for tid in (prof.get("taxonomy_ids") or []) if str(tid).strip()]
        for tid in tax_ids:
            for sid, wval in skill_weights_by_tax.get(tid, ()):
                pair = (sid, rf_key)
                if pair not in weight_by_pair or wval > float(weight_by_pair[pair]["weight"]):
                    weight_by_pair[pair] = {
                        "skill_id": sid,
                        "role_family_key": rf_key,
                        "weight": round(float(wval), 4),
                        "source": "projection_taxonomy_bridge",
                    }
        pillar_weights = {
            str(p.get("pillar_id") or "").strip(): float(p.get("weight") or 0.8)
            for p in (prof.get("top_weighted_pillars") or [])
            if isinstance(p, dict) and str(p.get("pillar_id") or "").strip()
        }
        if pillar_weights:
            for sfeat in selection_feature_rows:
                spillar = str(sfeat.get("pillar") or "").strip()
                if spillar in pillar_weights:
                    sid = str(sfeat["skill_id"])
                    pair = (sid, rf_key)
                    pw = round(min(1.0, max(0.1, pillar_weights[spillar])), 4)
                    if pair not in weight_by_pair or pw > float(weight_by_pair[pair]["weight"]):
                        weight_by_pair[pair] = {
                            "skill_id": sid,
                            "role_family_key": rf_key,
                            "weight": pw,
                            "source": "projection_pillar_bridge",
                        }
    role_family_skill_weight_rows = sorted(
        weight_by_pair.values(),
        key=lambda r: (str(r["role_family_key"]), str(r["skill_id"])),
    )

    from apps_rg.fact_inventory.graph_sqlite_path_index import (
        GRAPH_INDEX_SCHEMA_VERSION,
        build_graph_index_rows,
        compute_sqlite_graph_digest,
        compute_sqlite_schema_digest,
        require_graphdb_capability_schema,
        validate_graphdb_capability_integrity,
    )

    gm = payload.get("graph_metadata") if isinstance(payload.get("graph_metadata"), dict) else {}
    raw_max_siblings = gm.get("max_siblings_per_node")
    max_siblings_per_node = (
        int(raw_max_siblings)
        if isinstance(raw_max_siblings, int)
        and not isinstance(raw_max_siblings, bool)
        and raw_max_siblings > 0
        else None
    )

    graph_index_rows = build_graph_index_rows(
        node_rows=list(node_rows.values()),
        edge_rows=edge_rows,
        section_rows=section_rows,
        role_family_projection_rows=projection_rows,
        created_at=ts,
        build_run_id=ctx.get("build_run_id", ""),
        max_siblings_per_node=max_siblings_per_node,
    )

    summary = {
        "c03_sqlite_materializer_code_version": C03_SQLITE_MATERIALIZER_CODE_VERSION,
        "node_count_json": gm.get("node_count"),
        "edge_count_json": gm.get("edge_count"),
        "node_count_sqlite": len(node_rows),
        "edge_count_sqlite": len(edge_rows),
        "skill_fact_link_count": len(skill_fact_rows),
        "skill_epoch_link_count": len(skill_epoch_link_rows),
        "skill_employment_link_count": len(skill_employment_link_rows),
        "section_eligibility_count": len(section_rows),
        "role_family_projection_count": len(projection_rows),
        "c03_skill_selection_feature_count": len(selection_feature_rows),
        "c03_role_family_skill_weight_count": len(role_family_skill_weight_rows),
        "c03_metric_policy_version": C03_METRIC_POLICY_VERSION,
        "graph_index_schema_version": GRAPH_INDEX_SCHEMA_VERSION,
        "graph_path_count": len(graph_index_rows["graph_paths"]),
        "graph_neighborhood_count": len(graph_index_rows["graph_neighborhoods"]),
        "graph_sibling_link_count": len(graph_index_rows["graph_sibling_links"]),
        "section_evidence_budget_count": len(graph_index_rows["section_evidence_budget"]),
        "projected_registered_edge_count": projected_signature_report["registered_edge_count"],
        "projected_registered_edge_signature_valid_count": projected_signature_report["valid_edge_count"],
    }
    if max_siblings_per_node is not None:
        summary["max_siblings_per_node"] = max_siblings_per_node


    # Wave 2: Populate skill_lexical_aliases for ATS screening and FTS5 recall
    _CANONICAL_ACRONYM_PAIRS: tuple[tuple[str, str, str], ...] = (
        ("fsa", "FSA", "Fellow of the Society of Actuaries (FSA)"),
        ("erm", "ERM", "Enterprise Risk Management (ERM)"),
        ("enterprise risk", "ERM", "Enterprise Risk Management (ERM)"),
        ("rag", "RAG", "Retrieval-Augmented Generation (RAG)"),
        ("graphrag", "GraphRAG", "Graph Retrieval-Augmented Generation (GraphRAG)"),
        ("hpc", "HPC", "High-Performance Computing (HPC)"),
        ("soc 2", "SOC 2", "Service Organization Control 2 (SOC 2)"),
        ("bcbs", "BCBS 239", "Basel Committee on Banking Supervision 239 (BCBS 239)"),
        ("ccar", "CCAR", "Comprehensive Capital Analysis and Review (CCAR)"),
        ("ag43", "AG43", "Actuarial Guideline 43 (AG43)"),
        ("solvency", "Solvency II", "Solvency II Regulatory Capital"),
        ("aws", "AWS", "Amazon Web Services (AWS)"),
        ("hitl", "HITL", "Human-in-the-Loop (HITL)"),
        ("mcp", "MCP", "Model Context Protocol (MCP)"),
        ("a2a", "A2A", "Agent-to-Agent (A2A)"),
    )
    skill_lexical_alias_rows: list[dict[str, Any]] = []
    seen_aliases: set[tuple[str, str]] = set()
    for sid, row in sorted(skill_rows_by_id.items()):
        if sid in FORBIDDEN_SKILL_NODE_IDS or sid not in node_rows:
            continue
        ext_elig = int(node_rows[sid].get("external_eligible") or 0)
        lbl = str(node_rows[sid].get("label") or row.get("capability") or "").strip()

        def _push_alias(text: str, kind: str, pair: str = "") -> None:
            clean = " ".join(str(text or "").replace("_", " ").split()).strip()
            if not clean or len(clean) < 2:
                return
            key = (sid, clean.lower())
            if key in seen_aliases:
                return
            seen_aliases.add(key)
            skill_lexical_alias_rows.append(
                {
                    "skill_id": sid,
                    "alias_text": clean,
                    "alias_kind": kind,
                    "acronym_pair": pair,
                    "external_eligible": ext_elig,
                }
            )

        if lbl:
            _push_alias(lbl, "canonical_noun")
        for kw in row.get("ats_keywords") or []:
            _push_alias(str(kw), "ats_canonical")
        for ph in (row.get("allowed_phrases") or [])[:4]:
            _push_alias(str(ph), "allowed_phrase")
        corpus_low = " ".join([sid, lbl, str(node_rows[sid].get("description") or "")]).lower()
        for needle, acro, expanded in _CANONICAL_ACRONYM_PAIRS:
            if needle in corpus_low:
                _push_alias(acro, "acronym", expanded)
                _push_alias(expanded, "expanded_form", expanded)

    ctx["selection_feature_rows"] = selection_feature_rows
    ctx["role_family_skill_weight_rows"] = role_family_skill_weight_rows
    ctx["projection_rows"] = projection_rows
    ctx["graph_index_rows"] = graph_index_rows
    ctx["skill_lexical_alias_rows"] = skill_lexical_alias_rows
    summary["skill_lexical_alias_count"] = len(skill_lexical_alias_rows)
    ctx["summary"] = summary

__all__ = ["run_materializer_indexing"]
