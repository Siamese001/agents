"""Read-only SQLite dataset builder and HTML renderer for the Agents Knowledge Graph Explorer.

Mirrors the Decision Intelligence Engine (DIE) Knowledge Graph Explorer structure,
5-band confidence calibration, multi-workspace payload schema, and thin-shell portal
bootstrap contract while deriving 100% of entities, edges, evidence, engagements,
and role projections directly from ``augmented_skills_graph.sqlite`` (zero SQL writes).
"""

from __future__ import annotations

import html as html_lib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_GRAPH_RELPATH = Path(
    "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
)
DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "unified_agents_explorer_template.html"
)

# Maps raw SQLite node_type (20 canonical types) to concise, DIE-parity visual UI categories
RAW_TO_UI_TYPE: dict[str, str] = {
    "career_track": "backbone",
    "career_epoch": "epoch",
    "employment": "employment",
    "pillar": "pillar",
    "capability_domain": "domain",
    "skill": "skill",
    "engagement": "engagement",
    "fact": "evidence",
    "locked_bullet": "evidence",
    "certification": "evidence",
    "repo_evidence": "evidence",
    "concept": "evidence",
    "metric_outcome": "metric",
    "metric": "metric",
    "metric_bucket": "metric",
    "role_family": "projection",
    "section": "projection",
    "graph_ref": "projection",
    "policy": "policy",
    "policy_rule": "policy",
}

UI_TYPE_META: dict[str, dict[str, Any]] = {
    "backbone": {"label": "Identity & Tracks", "color": "#0f172a"},
    "epoch": {"label": "Career Epochs", "color": "#1d4ed8"},
    "employment": {"label": "Employments", "color": "#047857"},
    "pillar": {"label": "Pillars", "color": "#6b21a8"},
    "domain": {"label": "Capability Domains", "color": "#4338ca"},
    "skill": {"label": "Skills", "color": "#0891b2"},
    "engagement": {"label": "Engagements", "color": "#d97706"},
    "evidence": {"label": "Grounded Evidence", "color": "#0284c7"},
    "metric": {"label": "Metric Outcomes", "color": "#0e7490"},
    "projection": {"label": "Projections & Sections", "color": "#6366f1"},
    "policy": {"label": "Policy Guardrails", "color": "#b91c1c"},
}

BACKBONE_PILLAR_IDS: tuple[str, ...] = (
    "pillar_actuarial_foundation",
    "pillar_regulatory_governance",
    "pillar_cloud_data_aws",
    "pillar_partner_gtm_alliances",
    "pillar_agentic_ai_platforms",
    "pillar_executive_leadership",
)

BACKBONE_POLICY_IDS: tuple[str, ...] = (
    "policy_external_claim_policy",
    "section_executive_summary",
    "section_competencies",
)

IDENTITY_ROOT_ID = "identity_amit_ayer_governed_ai_platform_leader"

_BOOTSTRAP_ANCHOR_RE = re.compile(
    r"(const __AGENTS_BOOT_DATA__ = )(\{.*?\})(;\s*// END_AGENTS_BOOT_DATA)",
    re.S,
)


def resolve_primary_repo_root(anchor: Path | None = None) -> Path:
    """Resolve the primary repository root even when invoked inside ``.worktrees/<slug>``."""
    base = (anchor or Path(__file__).resolve()).resolve()
    if base.is_file():
        base = base.parent
    for parent in (base, *base.parents):
        if parent.name == ".worktrees":
            return parent.parent
        if (parent / "AGENTS.md").is_file() and parent.parent.name != ".worktrees":
            return parent
    return Path(__file__).resolve().parents[2]


def resolve_default_graph_db_path(repo_root: Path | None = None) -> Path:
    """Resolve the active ``augmented_skills_graph.sqlite`` path cleanly across root or worktree."""
    candidates: list[Path] = []
    if repo_root is not None:
        candidates.append(Path(repo_root).resolve() / DEFAULT_GRAPH_RELPATH)
    local_root = Path(__file__).resolve().parents[2]
    candidates.append(local_root / DEFAULT_GRAPH_RELPATH)
    primary_root = resolve_primary_repo_root(local_root)
    candidates.append(primary_root / DEFAULT_GRAPH_RELPATH)
    for cand in candidates:
        if cand.is_file():
            return cand.resolve()
    return candidates[0].resolve()


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def _format_mmddyyyy(raw_ts: str | None, fallback: str = "") -> str:
    if not raw_ts:
        return fallback or datetime.now(timezone.utc).strftime("%m/%d/%Y")
    val = str(raw_ts).strip()
    if re.match(r"^\d{2}/\d{2}/\d{4}$", val):
        return val
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", val)
    if m:
        return f"{m.group(2)}/{m.group(3)}/{m.group(1)}"
    return fallback or datetime.now(timezone.utc).strftime("%m/%d/%Y")


def _confidence_band(score: float) -> str:
    if score >= 0.95:
        return "VERIFIED"
    if score >= 0.90:
        return "HIGH"
    if score >= 0.85:
        return "ESTABLISHED"
    if score >= 0.70:
        return "PROVISIONAL"
    return "LOW"


def _confidence_tier(score: float) -> str:
    if score >= 0.85:
        return "HIGH"
    if score >= 0.50:
        return "MEDIUM"
    return "LOW"


def _clean_label(raw_label: str, node_id: str, raw_type: str) -> str:
    text = str(raw_label or "").strip()
    if not text:
        return node_id
    if raw_type == "career_track":
        mapping = {
            "track_actuarial_risk_derivatives": "Track 1: Actuarial, Risk & Derivatives (2002-2010)",
            "track_data_tech_cloud_ml": "Track 2: Data, Cloud, ML & Partner GTM (2010-2022)",
            "track_genai_agentic": "Track 3: GenAI & Agentic AI Platforms (2022-Present)",
        }
        return mapping.get(node_id, text)
    if raw_type == "skill" and "_" in text and " " not in text:
        return text.replace("_", " ").title()
    if raw_type == "policy" and text.startswith("policy_"):
        return text.replace("policy_", "").replace("_", " ").title()
    if raw_type == "policy_rule" and text.startswith("policy_rule_"):
        return text.replace("policy_rule_", "").replace("_", " ").title()
    if raw_type == "role_family" and text.isupper() and "_" in text:
        return text.replace("_", " ").title()
    return text


def _calibrate_confidence(
    raw_score: float | None,
    raw_tier: str | None,
    raw_type: str,
    activation_status: str,
    evidence_count: int,
    degree: int,
) -> float:
    status_up = (activation_status or "").upper()
    if status_up in ("BLOCKED", "QUARANTINED_UNVERIFIED_SYNTHETIC", "RETIRED"):
        return round(float(raw_score) if raw_score is not None and raw_score > 0 else 0.45, 2)
    if raw_score is not None:
        base = max(0.05, min(0.99, float(raw_score)))
        if evidence_count >= 12 and base >= 0.90:
            return min(0.99, round(max(base, 0.96), 2))
        if evidence_count >= 5 and base >= 0.85:
            return min(0.96, round(max(base, 0.92), 2))
        return round(base, 2)
    tier_up = (raw_tier or "").upper()
    if tier_up == "HIGH":
        return 0.92 if (evidence_count >= 4 or degree >= 8) else 0.88
    if tier_up == "MEDIUM":
        return 0.78
    if tier_up == "LOW":
        return 0.55
    # Structural backbone, tracks, epochs, pillars, sections, policies
    if raw_type in ("career_track", "career_epoch", "employment", "policy", "policy_rule"):
        return 0.97 if degree >= 4 else 0.95
    if raw_type in ("pillar", "capability_domain", "role_family", "section"):
        return 0.95 if degree >= 12 else (0.91 if degree >= 4 else 0.87)
    return 0.86


def _safe_json_loads(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _employer_slug(employer: str) -> str:
    low = (employer or "").strip().lower()
    if "slalom" in low:
        return "emp_slalom"
    if "unify" in low:
        return "emp_unify"
    if "ibm" in low:
        return "emp_ibm"
    if "insurtech" in low:
        return "emp_insurtech"
    if "ernst" in low or low == "ey":
        return "emp_ey"
    if "early" in low:
        return "emp_early"
    return ""


def _build_node_highlights(
    node_id: str,
    semantic_units_by_root: dict[str, list[dict[str, Any]]],
    edge_stories_by_node: dict[str, list[dict[str, Any]]],
    fallback_date: str,
) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    seen_claims: set[str] = set()
    for su in semantic_units_by_root.get(node_id, [])[:5]:
        claim = str(su.get("text") or "").strip()
        if not claim or claim in seen_claims:
            continue
        seen_claims.add(claim)
        conf_num = float(su.get("min_confidence") or 0.92)
        highlights.append(
            {
                "predicate": str(su.get("unit_type") or "SEMANTIC_UNIT").upper(),
                "claim": claim[:220],
                "confidence": f"{int(round(conf_num * 100))}%",
                "status": "external_eligible" if su.get("external_eligible") else "internal",
                "window": _format_mmddyyyy(su.get("created_at"), fallback_date),
            }
        )
    for st in edge_stories_by_node.get(node_id, [])[:6]:
        if len(highlights) >= 6:
            break
        claim = str(st.get("claim") or "").strip()
        if not claim or claim in seen_claims:
            continue
        seen_claims.add(claim)
        highlights.append(
            {
                "predicate": str(st.get("predicate") or "GRAPH_ASSERTION").upper(),
                "claim": claim[:220],
                "confidence": f"{int(round(float(st.get('confidence') or 0.90) * 100))}%",
                "status": str(st.get("status") or "canonical"),
                "window": fallback_date,
            }
        )
    return highlights


def build_agents_explorer_dataset(graph_path: Path | str | None = None) -> dict[str, Any]:
    """Read ``augmented_skills_graph.sqlite`` (read-only) and return the full 6-workspace dataset."""
    db_path = Path(graph_path).resolve() if graph_path else resolve_default_graph_db_path()
    if not db_path.is_file():
        raise FileNotFoundError(f"Agents skills graph database not found: {db_path}")

    conn = _connect_readonly(db_path)
    try:
        meta_row = conn.execute("SELECT * FROM graph_metadata LIMIT 1").fetchone()
        build_row = conn.execute("SELECT * FROM graph_build_runs ORDER BY built_at DESC LIMIT 1").fetchone()
        snapshot_iso = (
            str(build_row["built_at"])
            if build_row and build_row["built_at"]
            else (str(meta_row["materialized_at"]) if meta_row else "")
        )
        snapshot_date = _format_mmddyyyy(snapshot_iso)
        build_run_id = str(build_row["build_run_id"]) if build_row else "run-active"
        graph_version = str(meta_row["graph_version"]) if meta_row else "master_skills_arsenal_graph_v1"
        ledger_hash = str(meta_row["ledger_hash"] or "")[:12] if meta_row else ""

        node_type_layers: dict[str, str] = {
            str(r["node_type"]): str(r["layer"])
            for r in conn.execute("SELECT node_type, layer FROM node_type_registry").fetchall()
        }
        edge_evidence_counts: dict[str, int] = {
            str(r[0]): int(r[1])
            for r in conn.execute(
                "SELECT edge_id, COUNT(*) FROM edge_evidence GROUP BY edge_id"
            ).fetchall()
        }
        total_evidence_links = sum(edge_evidence_counts.values())
        total_paths = int(conn.execute("SELECT COUNT(*) FROM graph_paths").fetchone()[0])
        total_neighborhoods = int(conn.execute("SELECT COUNT(*) FROM graph_neighborhoods").fetchone()[0])
        total_build_inputs = int(conn.execute("SELECT COUNT(*) FROM graph_build_inputs").fetchone()[0])

        # Load raw nodes & edges
        raw_node_rows = conn.execute("SELECT * FROM graph_nodes").fetchall()
        raw_edge_rows = conn.execute("SELECT * FROM graph_edges").fetchall()

        # Skill features lookup
        skill_features: dict[str, dict[str, Any]] = {}
        for r in conn.execute("SELECT * FROM c03_skill_selection_features").fetchall():
            skill_features[str(r["skill_id"])] = dict(r)

        # Skill -> role family weights
        skill_rf_weights: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute(
            "SELECT skill_id, role_family_key, weight FROM c03_role_family_skill_weights ORDER BY weight DESC"
        ).fetchall():
            skill_rf_weights[str(r["skill_id"])].append(
                {"role_family": str(r["role_family_key"]), "weight": round(float(r["weight"]), 2)}
            )

        # Section eligibility lookup
        node_sections: dict[str, list[str]] = defaultdict(list)
        for r in conn.execute(
            "SELECT node_id, section_id FROM section_eligibility WHERE allowed = 1"
        ).fetchall():
            node_sections[str(r["node_id"])].append(str(r["section_id"]))

        # Semantic units lookup
        semantic_units_by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
        all_semantic_units: list[dict[str, Any]] = []
        for r in conn.execute("SELECT * FROM semantic_unit ORDER BY created_at DESC").fetchall():
            item = {
                "unit_id": str(r["unit_id"]),
                "unit_type": str(r["unit_type"]),
                "root_node_id": str(r["root_node_id"]),
                "text": str(r["text"] or ""),
                "confidence_tier": str(r["confidence_tier"] or "HIGH"),
                "min_confidence": float(r["min_confidence"]) if r["min_confidence"] is not None else 0.90,
                "external_eligible": bool(r["external_eligible"]),
                "allowed_sections": _safe_json_loads(r["allowed_sections_json"], []),
                "created_at": str(r["created_at"] or ""),
            }
            semantic_units_by_root[item["root_node_id"]].append(item)
            all_semantic_units.append(item)

        # Role family projections
        role_projections_raw = conn.execute(
            "SELECT * FROM role_family_projection ORDER BY role_family_id"
        ).fetchall()

        # Pre-compute degree, evidence counts, and cluster propagation via edges
        node_degree: dict[str, int] = defaultdict(int)
        node_ev_count: dict[str, int] = defaultdict(int)
        edge_stories_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
        adj_by_type: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        node_clusters: dict[str, set[str]] = defaultdict(lambda: {"all"})

        raw_nodes_by_id: dict[str, dict[str, Any]] = {}
        for r in raw_node_rows:
            d = dict(r)
            nid = str(d["node_id"])
            raw_nodes_by_id[nid] = d

        for r in raw_edge_rows:
            src = str(r["source_node_id"])
            tgt = str(r["target_node_id"])
            et = str(r["edge_type"])
            eid = str(r["edge_id"])
            if src not in raw_nodes_by_id or tgt not in raw_nodes_by_id or src == tgt:
                continue
            node_degree[src] += 1
            node_degree[tgt] += 1
            ev_cnt = edge_evidence_counts.get(eid, 0)
            node_ev_count[src] += ev_cnt
            node_ev_count[tgt] += ev_cnt
            adj_by_type[src].append((et, tgt, "out"))
            adj_by_type[tgt].append((et, src, "in"))

            story = str(
                r["business_story"]
                or r["technical_story"]
                or r["canonical_assertion_text"]
                or r["rationale"]
                or ""
            ).strip()
            if story and len(story) > 12:
                e_conf = float(r["confidence_score"]) if r["confidence_score"] is not None else 0.90
                rec = {
                    "predicate": et,
                    "claim": story,
                    "confidence": round(e_conf, 2),
                    "status": str(r["evidence_status"] or "canonical"),
                }
                if len(edge_stories_by_node[src]) < 8:
                    edge_stories_by_node[src].append(rec)
                if len(edge_stories_by_node[tgt]) < 8:
                    edge_stories_by_node[tgt].append(rec)

        # Assign scope clusters (tracks, epochs, employers, pillars, policy)
        backbone_ids: set[str] = {
            IDENTITY_ROOT_ID,
            *BACKBONE_PILLAR_IDS,
            *BACKBONE_POLICY_IDS,
        }
        for nid, nd in raw_nodes_by_id.items():
            rt = str(nd["node_type"])
            if rt in ("career_track", "career_epoch", "employment"):
                if nid not in ("cross_career", "epoch_ibm_client_partner_consulting", "epoch_unify_chief_ai_officer"):
                    backbone_ids.add(nid)
            if rt == "career_track":
                node_clusters[nid].add(nid)
            if rt == "career_epoch":
                node_clusters[nid].add(nid)
            if rt == "employment":
                node_clusters[nid].add(nid)
                es = _employer_slug(str(nd.get("employer") or nd.get("label") or ""))
                if es:
                    node_clusters[nid].add(es)
            if nd.get("career_epoch"):
                node_clusters[nid].add(str(nd["career_epoch"]))
            if nd.get("employer"):
                es = _employer_slug(str(nd["employer"]))
                if es:
                    node_clusters[nid].add(es)
            if rt in ("policy", "policy_rule"):
                node_clusters[nid].add("policy_guardrails")
            if rt in ("role_family", "section"):
                node_clusters[nid].add("projections_layer")

        # Propagate track, epoch, pillar, and employer clusters along direct structural edges
        for r in raw_edge_rows:
            src = str(r["source_node_id"])
            tgt = str(r["target_node_id"])
            if src not in raw_nodes_by_id or tgt not in raw_nodes_by_id:
                continue
            src_t = str(raw_nodes_by_id[src]["node_type"])
            tgt_t = str(raw_nodes_by_id[tgt]["node_type"])
            if src_t == "career_track":
                node_clusters[tgt].add(src)
            if tgt_t == "career_track":
                node_clusters[src].add(tgt)
            if src_t == "career_epoch":
                node_clusters[tgt].add(src)
            if tgt_t == "career_epoch":
                node_clusters[src].add(tgt)
            if src_t == "employment":
                node_clusters[tgt].add(src)
                es = _employer_slug(str(raw_nodes_by_id[src].get("employer") or ""))
                if es:
                    node_clusters[tgt].add(es)
            if tgt_t == "employment":
                node_clusters[src].add(tgt)
                es = _employer_slug(str(raw_nodes_by_id[tgt].get("employer") or ""))
                if es:
                    node_clusters[src].add(es)
            if src_t == "pillar":
                node_clusters[tgt].add(src)
            if tgt_t == "pillar":
                node_clusters[src].add(tgt)

        # Second pass: inherit track from skill_features and epoch->track mapping
        epoch_to_track: dict[str, set[str]] = defaultdict(set)
        for r in raw_edge_rows:
            if str(r["edge_type"]) == "career_track_contains_epoch":
                epoch_to_track[str(r["target_node_id"])].add(str(r["source_node_id"]))
        for nid, sf in skill_features.items():
            if sf.get("career_track_id"):
                node_clusters[nid].add(str(sf["career_track_id"]))
            if sf.get("career_epoch"):
                node_clusters[nid].add(str(sf["career_epoch"]))
            if sf.get("pillar"):
                node_clusters[nid].add(str(sf["pillar"]))
        for nid, cset in list(node_clusters.items()):
            for cid in list(cset):
                if cid in epoch_to_track:
                    cset.update(epoch_to_track[cid])

        # Build canonical explorer nodes
        graph_nodes: list[dict[str, Any]] = []
        for nid, nd in raw_nodes_by_id.items():
            raw_type = str(nd["node_type"])
            ui_type = "backbone" if nid == IDENTITY_ROOT_ID else RAW_TO_UI_TYPE.get(raw_type, "evidence")
            deg = node_degree.get(nid, 0)
            ev_cnt = node_ev_count.get(nid, 0)
            sf = skill_features.get(nid)
            fact_cnt = int(sf["source_fact_count"]) if sf and sf.get("source_fact_count") is not None else max(1, ev_cnt or deg)
            cal_conf = _calibrate_confidence(
                nd.get("confidence_score"),
                nd.get("confidence_tier"),
                raw_type,
                str(nd.get("activation_status") or ""),
                ev_cnt,
                deg,
            )
            label = _clean_label(str(nd.get("label") or ""), nid, raw_type)
            desc = str(nd.get("description") or "").strip() or f"Canonical {raw_type.replace('_', ' ')} node in Agents Career & Skills Graph."
            updated = _format_mmddyyyy(nd.get("updated_at") or nd.get("created_at"), snapshot_date)
            clusters = sorted(node_clusters[nid])
            if nid in backbone_ids:
                clusters.append("backbone")

            node_entry: dict[str, Any] = {
                "id": nid,
                "label": label,
                "type": ui_type,
                "rawType": raw_type,
                "layer": node_type_layers.get(raw_type, "knowledge"),
                "cluster": clusters,
                "desc": desc,
                "facts": max(1, fact_cnt),
                "evidenceCount": ev_cnt,
                "degree": deg,
                "confidence": cal_conf,
                "confidenceTier": _confidence_tier(cal_conf),
                "confidenceBand": _confidence_band(cal_conf),
                "activationStatus": str(nd.get("activation_status") or "ACTIVE"),
                "externalEligible": bool(nd.get("external_eligible")),
                "careerEpoch": str(nd.get("career_epoch") or (sf.get("career_epoch") if sf else "") or ""),
                "employer": str(nd.get("employer") or ""),
                "title": str(nd.get("title") or ""),
                "startDate": str(nd.get("start_date") or ""),
                "endDate": str(nd.get("end_date") or ""),
                "isCurrent": bool(nd.get("is_current")),
                "phaseOrdinal": nd.get("phase_ordinal"),
                "pillar": str(sf.get("pillar") or "") if sf else "",
                "domainId": str(sf.get("domain_id") or "") if sf else "",
                "trackId": str(sf.get("career_track_id") or "") if sf else "",
                "allowedSections": node_sections.get(nid, []),
                "coreBackbone": nid in backbone_ids,
                "updated": updated,
                "dbBacked": True,
                "highlights": _build_node_highlights(
                    nid, semantic_units_by_root, edge_stories_by_node, snapshot_date
                ),
            }
            graph_nodes.append(node_entry)

        # Sort nodes deterministically (backbone first, then by degree DESC, id ASC)
        graph_nodes.sort(key=lambda n: (0 if n["coreBackbone"] else 1, -n["degree"], n["id"]))
        node_by_id = {n["id"]: n for n in graph_nodes}

        # Build canonical explorer edges
        graph_edges: list[dict[str, Any]] = []
        seen_edges: set[tuple[str, str, str]] = set()
        for r in raw_edge_rows:
            src = str(r["source_node_id"])
            tgt = str(r["target_node_id"])
            et = str(r["edge_type"] or "RELATED_TO")
            eid = str(r["edge_id"])
            if src not in node_by_id or tgt not in node_by_id or src == tgt:
                continue
            key = (src, tgt, et)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            raw_c = r["confidence_score"]
            ev_cnt = edge_evidence_counts.get(eid, 0)
            if raw_c is not None:
                c_val = round(max(0.05, min(0.99, float(raw_c))), 2)
            else:
                c_val = 0.96 if (src in backbone_ids and tgt in backbone_ids) else (0.92 if ev_cnt > 0 else 0.88)
            mat = "critical" if (
                (src in backbone_ids and tgt in backbone_ids)
                or et in (
                    "identity_supported_by_epoch",
                    "identity_supported_by_pillar",
                    "career_track_contains_epoch",
                    "employment_in_epoch",
                    "employment_in_career_track",
                    "skill_supported_by_fact",
                    "skill_surfaces_metric_outcome",
                    "engagement_exercises_skill",
                )
            ) else "high"
            desc_txt = str(
                r["business_story"]
                or r["canonical_assertion_text"]
                or r["rationale"]
                or ""
            ).strip()
            graph_edges.append(
                {
                    "edgeId": eid,
                    "from": src,
                    "to": tgt,
                    "label": et,
                    "family": str(r["edge_family"] or ""),
                    "mat": mat,
                    "desc": desc_txt[:220],
                    "role": str(r["evidence_status"] or ""),
                    "evidenceCount": ev_cnt,
                    "traversable": bool(r["traversable"]),
                    "confidence": c_val,
                    "confidenceTier": _confidence_tier(c_val),
                    "confidenceBand": _confidence_band(c_val),
                }
            )

        # Workspace 2: Skills & Pillars Arsenal Table
        skills_rows: list[dict[str, Any]] = []
        for n in graph_nodes:
            if n["rawType"] != "skill":
                continue
            sid = n["id"]
            sf = skill_features.get(sid, {})
            pillar_id = str(sf.get("pillar") or "")
            pillar_lbl = node_by_id[pillar_id]["label"] if pillar_id in node_by_id else pillar_id.replace("pillar_", "").replace("_", " ").title()
            dom_id = str(sf.get("domain_id") or "")
            dom_lbl = node_by_id[dom_id]["label"] if dom_id in node_by_id else dom_id.replace("domain_", "").replace("_", " ").title()
            track_id = str(sf.get("career_track_id") or "")
            track_lbl = node_by_id[track_id]["label"] if track_id in node_by_id else ""
            epoch_id = n["careerEpoch"]
            epoch_lbl = node_by_id[epoch_id]["label"] if epoch_id in node_by_id else epoch_id

            linked_facts = [
                {"id": t, "label": node_by_id[t]["label"]}
                for et, t, _ in adj_by_type.get(sid, [])
                if t in node_by_id and node_by_id[t]["rawType"] in ("fact", "locked_bullet", "repo_evidence", "certification")
            ]
            linked_metrics = [
                {"id": t, "label": node_by_id[t]["label"]}
                for et, t, _ in adj_by_type.get(sid, [])
                if t in node_by_id and node_by_id[t]["rawType"] in ("metric_outcome", "metric")
            ]
            linked_engagements = [
                {"id": t, "label": node_by_id[t]["label"], "employer": node_by_id[t]["employer"]}
                for et, t, _ in adj_by_type.get(sid, [])
                if t in node_by_id and node_by_id[t]["rawType"] == "engagement"
            ]
            skills_rows.append(
                {
                    "id": sid,
                    "label": n["label"],
                    "desc": n["desc"],
                    "pillarId": pillar_id,
                    "pillar": pillar_lbl or "Cross-Pillar",
                    "domainId": dom_id,
                    "domain": dom_lbl or "Core Capability",
                    "trackId": track_id,
                    "track": track_lbl,
                    "epochId": epoch_id,
                    "epoch": epoch_lbl,
                    "confidence": n["confidence"],
                    "confidenceBand": n["confidenceBand"],
                    "activationStatus": n["activationStatus"],
                    "externalEligible": n["externalEligible"],
                    "sourceFactCount": int(sf.get("source_fact_count") or len(linked_facts)),
                    "metricCount": len(linked_metrics),
                    "engagementCount": len(linked_engagements),
                    "allowedSections": n["allowedSections"],
                    "topRoleFamilies": skill_rf_weights.get(sid, [])[:5],
                    "linkedFacts": linked_facts[:8],
                    "linkedMetrics": linked_metrics[:8],
                    "linkedEngagements": linked_engagements[:6],
                    "clusters": n["cluster"],
                }
            )
        skills_rows.sort(key=lambda s: (0 if s["externalEligible"] else 1, -s["confidence"], -s["sourceFactCount"], s["label"]))

        # Workspace 3: Evidence, Metric Outcomes & Policy Guardrails
        evidence_rows: list[dict[str, Any]] = []
        for n in graph_nodes:
            if n["rawType"] not in ("metric_outcome", "fact", "repo_evidence", "locked_bullet", "certification", "policy", "policy_rule"):
                continue
            category = (
                "metric_outcome"
                if n["rawType"] == "metric_outcome"
                else (
                    "policy"
                    if n["rawType"] in ("policy", "policy_rule")
                    else ("repo_evidence" if n["rawType"] == "repo_evidence" else "grounded_fact")
                )
            )
            linked_skills = [
                {"id": t, "label": node_by_id[t]["label"]}
                for _, t, _ in adj_by_type.get(n["id"], [])
                if t in node_by_id and node_by_id[t]["rawType"] == "skill"
            ]
            evidence_rows.append(
                {
                    "id": n["id"],
                    "category": category,
                    "rawType": n["rawType"],
                    "label": n["label"],
                    "desc": n["desc"],
                    "employer": n["employer"] or "Cross-Career",
                    "epoch": node_by_id[n["careerEpoch"]]["label"] if n["careerEpoch"] in node_by_id else "",
                    "confidence": n["confidence"],
                    "confidenceBand": n["confidenceBand"],
                    "externalEligible": n["externalEligible"],
                    "activationStatus": n["activationStatus"],
                    "degree": n["degree"],
                    "linkedSkills": linked_skills[:6],
                    "clusters": n["cluster"],
                }
            )
        evidence_rows.sort(key=lambda e: (-e["confidence"], -e["degree"], e["label"]))

        # Workspace 4: Engagements & Employments Roster
        engagement_rows: list[dict[str, Any]] = []
        for n in graph_nodes:
            if n["rawType"] != "engagement":
                continue
            eid = n["id"]
            linked_skills = [
                {"id": t, "label": node_by_id[t]["label"]}
                for _, t, _ in adj_by_type.get(eid, [])
                if t in node_by_id and node_by_id[t]["rawType"] == "skill"
            ]
            linked_facts = [
                {"id": t, "label": node_by_id[t]["label"]}
                for _, t, _ in adj_by_type.get(eid, [])
                if t in node_by_id and node_by_id[t]["rawType"] == "fact"
            ]
            linked_metrics = [
                {"id": t, "label": node_by_id[t]["label"]}
                for _, t, _ in adj_by_type.get(eid, [])
                if t in node_by_id and node_by_id[t]["rawType"] == "metric_outcome"
            ]
            engagement_rows.append(
                {
                    "id": eid,
                    "code": eid.replace("reb_", "").upper()[:18],
                    "label": n["label"],
                    "desc": n["desc"],
                    "employer": n["employer"] or "Portfolio",
                    "employerSlug": _employer_slug(n["employer"]),
                    "epochId": n["careerEpoch"],
                    "epoch": node_by_id[n["careerEpoch"]]["label"] if n["careerEpoch"] in node_by_id else "",
                    "confidence": n["confidence"],
                    "confidenceBand": n["confidenceBand"],
                    "externalEligible": n["externalEligible"],
                    "activationStatus": n["activationStatus"],
                    "skillCount": len(linked_skills),
                    "factCount": len(linked_facts),
                    "metricCount": len(linked_metrics),
                    "linkedSkills": linked_skills[:8],
                    "linkedFacts": linked_facts[:6],
                    "linkedMetrics": linked_metrics[:6],
                    "clusters": n["cluster"],
                }
            )
        engagement_rows.sort(key=lambda r: (r["employer"], -r["skillCount"], r["label"]))

        # Workspace 5: Role Family Projections (18 target personas)
        role_projection_cards: list[dict[str, Any]] = []
        for r in role_projections_raw:
            rf_id = str(r["role_family_id"])
            track_weights = _safe_json_loads(r["track_weight_profile"], {})
            kw_pillars = _safe_json_loads(r["targeting_keywords"], [])
            weighted_pillars = []
            for entry in kw_pillars if isinstance(kw_pillars, list) else []:
                if isinstance(entry, dict) and entry.get("pillar_id"):
                    pid = str(entry["pillar_id"])
                    weighted_pillars.append(
                        {
                            "id": pid,
                            "label": node_by_id[pid]["label"] if pid in node_by_id else pid,
                            "weight": round(float(entry.get("weight") or 0.0), 2),
                        }
                    )
            top_skills = sorted(
                [
                    {
                        "id": sid,
                        "label": node_by_id[sid]["label"],
                        "weight": w["weight"],
                    }
                    for sid, wlist in skill_rf_weights.items()
                    if sid in node_by_id
                    for w in wlist
                    if w["role_family"] == rf_id
                ],
                key=lambda x: (-x["weight"], x["label"]),
            )[:6]
            # Categorize persona group for filter pills
            rf_up = rf_id.upper()
            if any(k in rf_up for k in ("CHIEF_AI", "CTO", "SVP", "ENGINEERING", "AI_SOLUTIONS", "DATA_ANALYTICS")):
                group = "Executive & Platform Engineering"
            elif any(k in rf_up for k in ("PARTNER", "HYPERSCALER", "CONSULTING", "REVENUE", "SALES")):
                group = "Partner GTM & Commercial"
            elif any(k in rf_up for k in ("INSUR", "BANK", "REGULATED", "GOVERNANCE", "RISK", "QUANT")):
                group = "Regulated FS & Risk"
            else:
                group = "Multi-Track Generalist"
            role_projection_cards.append(
                {
                    "id": rf_id,
                    "label": rf_id.replace("_", " ").title(),
                    "group": group,
                    "proofPolicy": str(r["proof_policy_note"] or "graph_routing_not_claim_proof"),
                    "trackWeights": {
                        "actuarial": round(float(track_weights.get("track_actuarial_risk_derivatives", 0.0)) * 100),
                        "cloud_gtm": round(float(track_weights.get("track_data_tech_cloud_ml", 0.0)) * 100),
                        "agentic": round(float(track_weights.get("track_genai_agentic", 0.0)) * 100),
                    },
                    "weightedPillars": weighted_pillars[:6],
                    "topSkills": top_skills,
                }
            )

        # Architecture Map summary counts by Track, Epoch, Employer, Layer
        employments_summary: list[dict[str, Any]] = []
        for n in graph_nodes:
            if n["rawType"] != "employment":
                continue
            es = _employer_slug(n["employer"])
            emp_engs = [e for e in engagement_rows if e["employerSlug"] == es]
            emp_facts = [e for e in evidence_rows if _employer_slug(e["employer"]) == es and e["rawType"] == "fact"]
            emp_metrics = [e for e in evidence_rows if _employer_slug(e["employer"]) == es and e["rawType"] == "metric_outcome"]
            employments_summary.append(
                {
                    "id": n["id"],
                    "slug": es,
                    "label": n["label"],
                    "employer": n["employer"],
                    "title": n["title"],
                    "startDate": n["startDate"],
                    "endDate": n["endDate"] or "Present",
                    "isCurrent": n["isCurrent"],
                    "epochId": n["careerEpoch"],
                    "engagements": len(emp_engs),
                    "facts": len(emp_facts),
                    "metrics": len(emp_metrics),
                    "degree": n["degree"],
                }
            )
        employments_summary.sort(key=lambda x: x["startDate"], reverse=True)

        layer_counts: dict[str, int] = defaultdict(int)
        type_counts: dict[str, int] = defaultdict(int)
        for n in graph_nodes:
            layer_counts[n["layer"]] += 1
            type_counts[n["type"]] += 1

        return {
            "repo_name": "agents",
            "title": "Agents Repo — Career, Skills & Evidence Knowledge Graph Explorer",
            "graph_version": graph_version,
            "generation_id": build_run_id,
            "ledger_hash": ledger_hash,
            "snapshot_date": snapshot_date,
            "db_path": str(db_path),
            "total_nodes": len(graph_nodes),
            "total_edges": len(graph_edges),
            "total_evidence_links": total_evidence_links,
            "total_paths": total_paths,
            "total_neighborhoods": total_neighborhoods,
            "total_semantic_units": len(all_semantic_units),
            "total_build_inputs": total_build_inputs,
            "layer_counts": dict(layer_counts),
            "type_counts": dict(type_counts),
            "nodes": graph_nodes,
            "edges": graph_edges,
            "skills": skills_rows,
            "evidence": evidence_rows,
            "engagements": engagement_rows,
            "role_projections": role_projection_cards,
            "employments": employments_summary,
        }
    finally:
        conn.close()


def filter_bundle_lens(bundle: dict[str, Any], lens_id: str) -> dict[str, Any]:
    """Filter a dataset bundle by cluster/scope lens ID."""
    clean_lens = str(lens_id or "all").strip()
    nodes = list(bundle.get("nodes") or [])
    edges = list(bundle.get("edges") or [])
    if clean_lens in ("", "all"):
        matched_nodes = nodes
    elif clean_lens == "backbone":
        matched_nodes = [n for n in nodes if n.get("coreBackbone")]
    else:
        matched_nodes = [n for n in nodes if clean_lens in (n.get("cluster") or []) or n.get("id") == clean_lens]
    valid_ids = {str(n["id"]) for n in matched_nodes}
    matched_edges = [e for e in edges if e["from"] in valid_ids and e["to"] in valid_ids]
    return {
        "lens": clean_lens,
        "node_count": len(matched_nodes),
        "edge_count": len(matched_edges),
        "nodes": matched_nodes,
        "edges": matched_edges,
    }


_NON_TRAVERSABLE_BRIDGE_RAW_TYPES: frozenset[str] = frozenset(
    {"section", "policy", "policy_rule", "role_family", "graph_ref"}
)
_BROAD_CONTAINER_RAW_TYPES: frozenset[str] = frozenset(
    {"career_track", "career_epoch", "employment"}
)


def compute_multihop_subgraph(
    bundle: dict[str, Any],
    center_id: str,
    *,
    hops: int = 2,
    enabled_types: set[str] | None = None,
) -> dict[str, Any]:
    """Compute a strictly connected multi-hop subgraph around ``center_id`` without super-hub hairball bounce."""
    max_hops = max(1, min(3, int(hops)))
    nodes = list(bundle.get("nodes") or [])
    edges = list(bundle.get("edges") or [])
    node_by_id = {str(n["id"]): n for n in nodes}
    center_node = node_by_id.get(center_id)
    if center_node is None:
        return {"center_id": center_id, "hops": max_hops, "nodes": [], "edges": []}

    allowed_ids = {
        str(n["id"])
        for n in nodes
        if str(n["id"]) == center_id
        or enabled_types is None
        or str(n.get("type") or "") in enabled_types
    }
    adj_edges: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for e in edges:
        u, v = str(e["from"]), str(e["to"])
        if u in allowed_ids and v in allowed_ids and u != v:
            adj_edges[u].append((v, e))
            adj_edges[v].append((u, e))

    keep: set[str] = {center_id}
    hop_dist: dict[str, int] = {center_id: 0}
    frontier: list[str] = [center_id]
    center_raw = str(center_node.get("rawType") or "")

    for h in range(1, max_hops + 1):
        next_f: list[str] = []
        for cid in frontier:
            cur_node = node_by_id[cid]
            cur_raw = str(cur_node.get("rawType") or "")
            for nb_id, edge_obj in adj_edges.get(cid, []):
                if nb_id in keep:
                    continue
                if h >= 2 and cid != center_id:
                    if cid == IDENTITY_ROOT_ID or cur_raw in _NON_TRAVERSABLE_BRIDGE_RAW_TYPES:
                        continue
                    if edge_obj.get("traversable") is False:
                        continue
                    if center_raw not in _BROAD_CONTAINER_RAW_TYPES and center_id != IDENTITY_ROOT_ID:
                        if cur_raw in _BROAD_CONTAINER_RAW_TYPES:
                            continue
                    if center_raw == "pillar" and cur_raw == "pillar":
                        continue
                    nb_raw = str(node_by_id[nb_id].get("rawType") or "")
                    if nb_raw in _NON_TRAVERSABLE_BRIDGE_RAW_TYPES:
                        continue
                keep.add(nb_id)
                hop_dist[nb_id] = h
                next_f.append(nb_id)
        frontier = next_f
        if not frontier:
            break

    # Strict connected-component verification over induced edges
    connected: set[str] = {center_id}
    q: list[str] = [center_id]
    while q:
        cur = q.pop(0)
        for nb_id, _ in adj_edges.get(cur, []):
            if nb_id in keep and nb_id not in connected:
                connected.add(nb_id)
                q.append(nb_id)

    sub_nodes = [
        {**node_by_id[nid], "hopDistance": hop_dist.get(nid, 0)}
        for nid in connected
        if nid in node_by_id
    ]
    sub_edges = [e for e in edges if str(e["from"]) in connected and str(e["to"]) in connected]
    return {
        "center_id": center_id,
        "hops": max_hops,
        "node_count": len(sub_nodes),
        "edge_count": len(sub_edges),
        "nodes": sub_nodes,
        "edges": sub_edges,
    }


def search_bundle_nodes(bundle: dict[str, Any], query: str, *, limit: int = 40) -> dict[str, Any]:
    """Search nodes across label, id, rawType, employer, pillar, and description."""
    q = str(query or "").strip().lower()
    nodes = list(bundle.get("nodes") or [])
    if not q:
        return {"query": "", "count": 0, "results": []}
    hits: list[dict[str, Any]] = []
    for n in nodes:
        hay = " ".join(
            [
                str(n.get("id") or ""),
                str(n.get("label") or ""),
                str(n.get("rawType") or ""),
                str(n.get("employer") or ""),
                str(n.get("pillar") or ""),
                str(n.get("desc") or ""),
            ]
        ).lower()
        if q in hay:
            hits.append(
                {
                    "id": n["id"],
                    "label": n["label"],
                    "type": n["type"],
                    "rawType": n["rawType"],
                    "confidence": n["confidence"],
                    "confidenceBand": n["confidenceBand"],
                    "employer": n.get("employer") or "",
                    "degree": n.get("degree") or 0,
                }
            )
            if len(hits) >= limit:
                break
    return {"query": query, "count": len(hits), "results": hits}


def _apply_header_placeholders(template_html: str, data: dict[str, Any]) -> str:
    replacements = {
        "__SNAPSHOT_DATE__": html_lib.escape(str(data.get("snapshot_date") or "")),
        "__GENERATION_SHORT__": html_lib.escape(str(data.get("generation_id") or "")[:24]),
        "__ACTIVE_NODE_TOTAL__": f"{int(data.get('total_nodes') or 0):,}",
        "__CANONICAL_EDGE_TOTAL__": f"{int(data.get('total_edges') or 0):,}",
        "__EVIDENCE_LINK_TOTAL__": f"{int(data.get('total_evidence_links') or 0):,}",
        "__SEMANTIC_UNIT_TOTAL__": f"{int(data.get('total_semantic_units') or 0):,}",
    }
    out = template_html
    for token, val in replacements.items():
        out = out.replace(token, val)
    return out


def render_explorer_html(
    data: dict[str, Any],
    *,
    template_path: Path | None = None,
    default_mode: str = "graph",
) -> str:
    """Render a fully self-contained offline interactive HTML file with embedded graph data."""
    tpl_path = Path(template_path) if template_path else DEFAULT_TEMPLATE_PATH
    html_text = _apply_header_placeholders(tpl_path.read_text(encoding="utf-8"), data)
    payload_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    m = _BOOTSTRAP_ANCHOR_RE.search(html_text)
    if not m:
        raise ValueError(f"Explorer template missing __AGENTS_BOOT_DATA__ anchor: {tpl_path}")
    rendered = (
        html_text[: m.start()]
        + f"const __AGENTS_BOOT_DATA__ = {payload_json};\n    const __DEFAULT_INITIAL_MODE__ = {json.dumps(default_mode)};\n    // END_AGENTS_BOOT_DATA"
        + html_text[m.end() :]
    )
    return rendered


def render_portal_shell_html(
    data: dict[str, Any],
    *,
    bootstrap_endpoint: str = "/api/v1/bootstrap",
    template_path: Path | None = None,
    default_mode: str = "graph",
) -> str:
    """Render the live HTTP portal shell that hydrates live from ``/api/v1/bootstrap``."""
    tpl_path = Path(template_path) if template_path else DEFAULT_TEMPLATE_PATH
    html_text = _apply_header_placeholders(tpl_path.read_text(encoding="utf-8"), data)
    m = _BOOTSTRAP_ANCHOR_RE.search(html_text)
    if not m:
        raise ValueError(f"Explorer template missing __AGENTS_BOOT_DATA__ anchor: {tpl_path}")

    script_open = html_text.rfind("<script", 0, m.start())
    script_body_start = html_text.find(">", script_open) + 1 if script_open != -1 else -1
    last_script_end = html_text.rfind("</script>")
    if script_body_start <= 0 or last_script_end == -1:
        raise ValueError("Explorer template missing enclosing <script> tags.")

    banner = (
        '<div id="agentsPortalBanner" class="no-print" style="background:linear-gradient(90deg,#0f172a 0%,#1e293b 50%,#0f172a 100%);'
        'border-bottom:1px solid #334155;color:#f8fafc;padding:2px 14px;font-family:var(--font-sans);'
        'font-size:clamp(11.5px,0.76vw,12.5px);line-height:1.25;flex-shrink:0;display:flex;align-items:center;'
        'justify-content:space-between;gap:10px;z-index:40;position:relative;">'
        '<div style="display:flex;align-items:center;gap:8px;">'
        '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#10b981;"></span>'
        '<strong style="color:#f8fafc;letter-spacing:0.03em;">AGENTS REPO | CAREER, SKILLS &amp; EVIDENCE KNOWLEDGE GRAPH</strong>'
        '</div>'
        f'<div style="color:#cbd5e1;">Source: <strong style="color:#34d399;">augmented_skills_graph.sqlite</strong> '
        f'<span style="margin:0 6px;">|</span> {int(data.get("total_nodes") or 0):,} Nodes &middot; '
        f'{int(data.get("total_edges") or 0):,} Edges &middot; {int(data.get("total_evidence_links") or 0):,} Evidence Links '
        '<span style="margin-left:6px;color:#93c5fd;">[Live Read-Only Stream]</span></div></div>'
    )

    body_idx = html_text.find("<body")
    body_close = html_text.find(">", body_idx) + 1 if body_idx != -1 else -1
    if body_close > 0:
        html_text = html_text[:body_close] + "\n  " + banner + html_text[body_close:]
        m = _BOOTSTRAP_ANCHOR_RE.search(html_text)
        assert m is not None
        script_open = html_text.rfind("<script", 0, m.start())
        script_body_start = html_text.find(">", script_open) + 1
        last_script_end = html_text.rfind("</script>")

    html_replaced = (
        html_text[: m.start()]
        + f"const __AGENTS_BOOT_DATA__ = __LIVE_BOOT__;\n    const __DEFAULT_INITIAL_MODE__ = {json.dumps(default_mode)};\n    // END_AGENTS_BOOT_DATA"
        + html_text[m.end() :]
    )
    last_script_end = html_replaced.rfind("</script>")
    loader_head = (
        "\n    (async function() {\n"
        f"      const resp = await fetch({json.dumps(bootstrap_endpoint)}, {{ cache: 'no-store' }});\n"
        '      if (!resp.ok) { document.body.innerHTML = \'<div style="padding:40px;color:#f8fafc;background:#0f172a;font-family:sans-serif;"><h2>Graph Bootstrap Unavailable</h2><p>Unable to load live graph dataset from server.</p></div>\'; return; }\n'
        "      const __LIVE_BOOT__ = await resp.json();\n"
    )
    loader_tail = (
        "\n      document.addEventListener('click', (ev) => {\n"
        "        const el = ev.target && ev.target.closest ? ev.target.closest('[data-node-id],[data-view],button') : null;\n"
        "        if (el && navigator.sendBeacon) {\n"
        "          navigator.sendBeacon('/api/v1/telemetry', JSON.stringify({event:'click', label:(el.innerText||el.textContent||'').trim().slice(0,80)}));\n"
        "        }\n"
        "      });\n"
        "    })();\n  </script>"
    )
    return (
        html_replaced[:script_body_start]
        + loader_head
        + html_replaced[script_body_start:last_script_end]
        + loader_tail
        + html_replaced[last_script_end + len("</script>") :]
    )
