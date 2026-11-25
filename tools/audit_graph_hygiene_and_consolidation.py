#!/usr/bin/env python3
"""DIE-Parity Graph Hygiene, Deduplication, Consolidation & Promotion Auditor for `agents`.

Implements 6 deterministic read-only scanners modeled on DIE Tier-2 Graph Hygiene:
1. Same-type & cross-type duplicate / near-duplicate node clustering (Scan 1 fuzzy + verbatim clones)
2. Quarantine / blocked / retired leakage across FTS5, semantic_unit, vectors, sparse, ColBERT & edges
3. Stranded topology & consolidation (verified metrics with 0 skill links + 2-hop fact closure, isolated nodes)
4. Staging-to-active promotion readiness (DRAFT structural nodes, internal skills, candidate fact ledger)
5. Evidence fragmentation & stub/sibling-fanout hygiene (Scan 4 + hex repo_evidence stubs)
6. Pre-promotion regression & parity gates (active-only FTS5, zero quarantine leaks, topology non-regression)

All SQLite reads execute strictly via read-only URI (`mode=ro`) with `PRAGMA query_only=ON`.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import difflib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
RGE_SRC = REPO_ROOT / "resume_graph_engine" / "src"
for _p in (str(REPO_ROOT), str(RGE_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_GRAPH_REL = Path("resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite")
INACTIVE_OR_QUARANTINED_STATUSES: tuple[str, ...] = (
    "QUARANTINED_UNVERIFIED_SYNTHETIC",
    "BLOCKED",
    "RETIRED",
)
STRUCTURAL_PROMOTABLE_TYPES: tuple[str, ...] = (
    "pillar",
    "capability_domain",
    "employment",
    "career_track",
)
_HEX_LABEL_RE = re.compile(r"^[0-9a-fA-F]{6}$")
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "for", "in", "on", "at", "to", "by", "with",
        "from", "as", "is", "into", "across", "through", "domain", "phase2", "skill",
    }
)


def resolve_primary_repo_root(repo_root: Path) -> Path:
    """Resolve primary git root (parent of .git common dir) when invoked inside a linked worktree."""
    resolved = Path(repo_root).resolve()
    git_dot = resolved / ".git"
    if git_dot.is_file():
        try:
            text = git_dot.read_text(encoding="utf-8").strip()
            if text.startswith("gitdir:"):
                raw_gitdir = Path(text.split(":", 1)[1].strip())
                gitdir = (raw_gitdir if raw_gitdir.is_absolute() else (resolved / raw_gitdir)).resolve()
                commondir_file = gitdir / "commondir"
                if commondir_file.is_file():
                    cd_raw = Path(commondir_file.read_text(encoding="utf-8").strip())
                    common = (cd_raw if cd_raw.is_absolute() else (gitdir / cd_raw)).resolve()
                    if common.name == ".git":
                        return common.parent
        except OSError:
            pass
    return resolved


def resolve_graph_db_path(repo_root: Path, db_path: Path | None = None) -> Path:
    """Resolve graph SQLite DB path, falling back read-only to primary git root when in a fresh worktree."""
    if db_path is not None:
        return Path(db_path).resolve()
    resolved_root = Path(repo_root).resolve()
    direct = resolved_root / DEFAULT_GRAPH_REL
    if direct.is_file():
        return direct
    primary = resolve_primary_repo_root(resolved_root)
    primary_db = primary / DEFAULT_GRAPH_REL
    if primary_db.is_file():
        return primary_db
    return direct


def open_readonly_sqlite(db_path: Path) -> sqlite3.Connection:
    """Open SQLite strictly read-only with PRAGMA query_only=ON."""
    resolved = Path(db_path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Graph SQLite DB not found: {resolved}")
    conn = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def normalize_text(text: str | None) -> str:
    """Normalize label/description text for fuzzy deduplication (DIE Scan 1 parity)."""
    if not text:
        return ""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    tokens = [t for t in cleaned.split() if t and t not in _STOPWORDS]
    return " ".join(tokens) if tokens else cleaned.strip()


def compute_string_similarity(
    norm_a: str,
    norm_b: str,
    tokens_a: set[str] | None = None,
    tokens_b: set[str] | None = None,
) -> tuple[float, float, float]:
    """Compute DIE Scan 1 combined similarity: 0.55 * SequenceMatcher + 0.45 * Jaccard."""
    if not norm_a and not norm_b:
        return 1.0, 1.0, 1.0
    if not norm_a or not norm_b:
        return 0.0, 0.0, 0.0
    if norm_a == norm_b:
        return 1.0, 1.0, 1.0
    seq_ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
    ta = tokens_a if tokens_a is not None else set(norm_a.split())
    tb = tokens_b if tokens_b is not None else set(norm_b.split())
    union = len(ta | tb)
    jaccard = (len(ta & tb) / union) if union > 0 else 0.0
    return round(0.55 * seq_ratio + 0.45 * jaccard, 4), round(seq_ratio, 4), round(jaccard, 4)


def _node_rank_tuple(node: Mapping[str, Any], degree_map: Mapping[str, dict[str, int]]) -> tuple[int, int, int, int, int, str]:
    """Deterministic survivor ranking (DIE Agent 9 fidelity): higher tuple wins survivor slot."""
    nid = str(node["node_id"])
    deg = degree_map.get(nid, {})
    is_direct = 1 if str(node.get("support_level") or "") == "DIRECT_FROM_RESUME_ARCHIVE" else 0
    is_ext = int(node.get("external_eligible") or 0)
    is_non_p2 = 0 if nid.startswith("skill_p2_") else 1
    fact_cnt = int(deg.get("fact_edges", 0))
    total_deg = int(deg.get("total_edges", 0))
    # Prefer shorter canonical ID on tie (negated length) and stable alphabetical tiebreak
    return (is_direct, is_ext, is_non_p2, fact_cnt, total_deg, f"{999 - min(len(nid), 999):03d}:{nid}")


def _build_degree_map(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    deg: dict[str, dict[str, int]] = defaultdict(lambda: {"total_edges": 0, "fact_edges": 0, "metric_edges": 0})
    for row in conn.execute("SELECT source_node_id, target_node_id, edge_type FROM graph_edges"):
        src, tgt, etype = str(row["source_node_id"]), str(row["target_node_id"]), str(row["edge_type"])
        deg[src]["total_edges"] += 1
        deg[tgt]["total_edges"] += 1
        if etype == "skill_supported_by_fact":
            deg[src]["fact_edges"] += 1
        elif etype == "skill_surfaces_metric_outcome":
            deg[src]["metric_edges"] += 1
    return deg


def scan_duplicate_and_near_duplicate_nodes(
    conn: sqlite3.Connection,
    *,
    domain_similarity_threshold: float = 0.65,
) -> dict[str, Any]:
    """Scanner 1 (DIE Scan 1 parity): exact twins, verbatim skill clones, and domain near-duplicates."""
    nodes = [
        dict(r)
        for r in conn.execute(
            "SELECT node_id, node_type, label, description, activation_status, support_level, external_eligible "
            "FROM graph_nodes ORDER BY node_id"
        ).fetchall()
    ]
    degree_map = _build_degree_map(conn)
    active_nodes = [
        n for n in nodes if str(n.get("activation_status") or "") not in INACTIVE_OR_QUARANTINED_STATUSES
    ]

    # 1a. Exact label duplicates (same-type vs cross-type)
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in active_nodes:
        lbl = str(n.get("label") or "").strip().lower()
        if lbl:
            by_label[lbl].append(n)

    exact_skill_twins: list[dict[str, Any]] = []
    cross_type_label_collisions: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for lbl, grp in sorted(by_label.items()):
        if len(grp) < 2:
            continue
        types = {str(x["node_type"]) for x in grp}
        if types == {"skill"}:
            ordered = sorted(grp, key=lambda x: _node_rank_tuple(x, degree_map), reverse=True)
            surv = ordered[0]
            for ret in ordered[1:]:
                pair_key = tuple(sorted((str(surv["node_id"]), str(ret["node_id"]))))
                seen_pairs.add(pair_key)
                exact_skill_twins.append(
                    {
                        "reason": "exact_duplicate_skill_label",
                        "shared_label": lbl,
                        "survivor_node_id": surv["node_id"],
                        "survivor_label": surv["label"],
                        "retired_node_id": ret["node_id"],
                        "retired_label": ret["label"],
                        "rationale": f"Exact duplicate skill label '{lbl}' across active skills.",
                    }
                )
        elif len(types) > 1:
            cross_type_label_collisions.append(
                {
                    "shared_label": lbl,
                    "nodes": [{"node_id": x["node_id"], "node_type": x["node_type"]} for x in grp],
                }
            )

    # 1b. Verbatim description clones across active skills
    skills_by_desc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in active_nodes:
        if n["node_type"] != "skill":
            continue
        desc = " ".join(str(n.get("description") or "").strip().lower().split())
        if len(desc) >= 24:
            skills_by_desc[desc].append(n)

    sorted_desc_groups = sorted(skills_by_desc.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for desc, grp in sorted_desc_groups:
        if len(grp) < 2:
            continue
        ordered = sorted(grp, key=lambda x: _node_rank_tuple(x, degree_map), reverse=True)
        p2_nodes = [x for x in ordered if str(x["node_id"]).startswith("skill_p2_")]
        non_p2_nodes = [x for x in ordered if not str(x["node_id"]).startswith("skill_p2_")]
        if p2_nodes and non_p2_nodes:
            surv = non_p2_nodes[0]
            for ret in p2_nodes:
                pair_key = tuple(sorted((str(surv["node_id"]), str(ret["node_id"]))))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                exact_skill_twins.append(
                    {
                        "reason": "p2_verbatim_description_twin",
                        "survivor_node_id": surv["node_id"],
                        "survivor_label": surv["label"],
                        "retired_node_id": ret["node_id"],
                        "retired_label": ret["label"],
                        "shared_description_prefix": desc[:100],
                        "rationale": (
                            f"Phase-2 derived skill '{ret['node_id']}' duplicates verbatim description of "
                            f"canonical skill '{surv['node_id']}'."
                        ),
                    }
                )

    retired_in_02a = {str(x["retired_node_id"]) for x in exact_skill_twins}
    verbatim_clone_groups: list[dict[str, Any]] = []
    for desc, grp in sorted_desc_groups:
        if len(grp) < 2:
            continue
        ordered = sorted(grp, key=lambda x: _node_rank_tuple(x, degree_map), reverse=True)
        remaining = [x for x in ordered if str(x["node_id"]) not in retired_in_02a]
        if len(remaining) >= 2:
            surv = remaining[0]
            verbatim_clone_groups.append(
                {
                    "survivor_candidate_id": surv["node_id"],
                    "member_ids": [x["node_id"] for x in remaining],
                    "member_labels": [x["label"] for x in remaining],
                    "member_count": len(remaining),
                    "shared_description_prefix": desc[:110],
                }
            )

    # 1c. Fuzzy same-type capability_domain clustering (DIE Scan 1 character-counter upper-bound pruning)
    domains = [n for n in active_nodes if n["node_type"] == "capability_domain"]
    proc_domains = []
    for d in domains:
        nn = normalize_text(str(d.get("label") or d["node_id"]))
        proc_domains.append(
            {
                "node": d,
                "norm": nn,
                "tokens": set(nn.split()),
                "chars": Counter(nn),
                "len": len(nn),
            }
        )
    domain_near_duplicates: list[dict[str, Any]] = []
    for i in range(len(proc_domains)):
        da = proc_domains[i]
        if da["len"] == 0:
            continue
        for j in range(i + 1, len(proc_domains)):
            db = proc_domains[j]
            if db["len"] == 0:
                continue
            common = sum(min(cnt, db["chars"].get(c, 0)) for c, cnt in da["chars"].items())
            if (2.0 * common) / (da["len"] + db["len"]) < domain_similarity_threshold:
                continue
            sim, seq, jacc = compute_string_similarity(da["norm"], db["norm"], da["tokens"], db["tokens"])
            if sim >= domain_similarity_threshold:
                ordered = sorted([da["node"], db["node"]], key=lambda x: _node_rank_tuple(x, degree_map), reverse=True)
                domain_near_duplicates.append(
                    {
                        "survivor_node_id": ordered[0]["node_id"],
                        "survivor_label": ordered[0]["label"],
                        "retired_node_id": ordered[1]["node_id"],
                        "retired_label": ordered[1]["label"],
                        "similarity": sim,
                        "seq_ratio": seq,
                        "jaccard": jacc,
                    }
                )
    domain_near_duplicates.sort(key=lambda x: (-float(x["similarity"]), str(x["survivor_node_id"])))

    return {
        "exact_skill_twins": exact_skill_twins,
        "verbatim_clone_groups": verbatim_clone_groups,
        "domain_near_duplicates": domain_near_duplicates,
        "cross_type_label_collisions": cross_type_label_collisions,
    }


def scan_quarantine_and_fts_leakage(conn: sqlite3.Connection) -> dict[str, Any]:
    """Scanner 2 (DIE Agent 12 & 13 parity): quarantined/blocked/retired rows in search or edges."""
    ph = ",".join("?" for _ in INACTIVE_OR_QUARANTINED_STATUSES)
    fts_leaks = [
        dict(r)
        for r in conn.execute(
            f"SELECT gn.node_id, gn.node_type, gn.activation_status FROM graph_nodes_fts f "
            f"JOIN graph_nodes gn ON gn.node_id = f.node_id "
            f"WHERE COALESCE(gn.activation_status, '') IN ({ph}) ORDER BY gn.node_id",
            INACTIVE_OR_QUARANTINED_STATUSES,
        ).fetchall()
    ]
    su_leaks = [
        dict(r)
        for r in conn.execute(
            f"SELECT su.unit_id, su.unit_type, su.root_node_id, gn.activation_status "
            f"FROM semantic_unit su JOIN graph_nodes gn ON gn.node_id = su.root_node_id "
            f"WHERE COALESCE(gn.activation_status, '') IN ({ph}) ORDER BY su.unit_id",
            INACTIVE_OR_QUARANTINED_STATUSES,
        ).fetchall()
    ]
    edge_leaks = [
        dict(r)
        for r in conn.execute(
            f"SELECT e.edge_id, e.source_node_id, e.target_node_id, e.edge_type, gn.activation_status "
            f"FROM graph_edges e JOIN graph_nodes gn ON gn.node_id = e.target_node_id "
            f"WHERE e.edge_type = 'skill_surfaces_metric_outcome' "
            f"  AND COALESCE(gn.activation_status, '') IN ({ph}) ORDER BY e.edge_id",
            INACTIVE_OR_QUARANTINED_STATUSES,
        ).fetchall()
    ]
    fts_count = int(conn.execute("SELECT COUNT(*) FROM graph_nodes_fts").fetchone()[0])
    active_fts_expected = int(
        conn.execute(
            f"SELECT COUNT(*) FROM graph_nodes WHERE COALESCE(activation_status, '') NOT IN ({ph})",
            INACTIVE_OR_QUARANTINED_STATUSES,
        ).fetchone()[0]
    )
    return {
        "fts_count": fts_count,
        "active_fts_expected": active_fts_expected,
        "fts_parity_delta": abs(fts_count - active_fts_expected),
        "fts_leaks": fts_leaks,
        "semantic_unit_leaks": su_leaks,
        "quarantined_skill_metric_edges": edge_leaks,
    }


def scan_stranded_topology_and_consolidation(conn: sqlite3.Connection) -> dict[str, Any]:
    """Scanner 3 (DIE stranded-topology parity): unlinked verified metrics with 2-hop skill closure & orphans."""
    # Stranded APPROVED_GRAPH_SSOT metrics lacking skill_surfaces_metric_outcome edges
    stranded_rows = conn.execute(
        """
        SELECT node_id, label, employer, activation_status
        FROM graph_nodes
        WHERE node_type = 'metric_outcome'
          AND COALESCE(external_eligible, 0) = 1
          AND activation_status = 'APPROVED_GRAPH_SSOT'
          AND node_id NOT IN (
              SELECT target_node_id FROM graph_edges WHERE edge_type = 'skill_surfaces_metric_outcome'
          )
        ORDER BY node_id
        """
    ).fetchall()

    stranded_verified_metrics: list[dict[str, Any]] = []
    for row in stranded_rows:
        mid = str(row["node_id"])
        # Compute 2-hop candidate skills via shared fact: skill -> fact -> metric_outcome
        cand_skills = [
            str(r[0])
            for r in conn.execute(
                """
                SELECT DISTINCT e_sf.source_node_id
                FROM graph_edges e_fm
                JOIN graph_edges e_sf
                  ON e_sf.target_node_id = e_fm.source_node_id
                 AND e_sf.edge_type = 'skill_supported_by_fact'
                JOIN graph_nodes sk ON sk.node_id = e_sf.source_node_id
                WHERE e_fm.target_node_id = ?
                  AND e_fm.edge_type = 'fact_has_metric_outcome'
                  AND COALESCE(sk.external_eligible, 0) = 1
                  AND COALESCE(sk.activation_status, '') NOT IN ('QUARANTINED_UNVERIFIED_SYNTHETIC', 'BLOCKED', 'RETIRED')
                ORDER BY e_sf.source_node_id
                """,
                (mid,),
            ).fetchall()
        ]
        # Fallback: 2-hop via engagement bundle: metric -> engagement -> skill
        if not cand_skills:
            cand_skills = [
                str(r[0])
                for r in conn.execute(
                    """
                    SELECT DISTINCT e_es.target_node_id
                    FROM graph_edges e_me
                    JOIN graph_edges e_es
                      ON e_es.source_node_id = e_me.target_node_id
                     AND e_es.edge_type = 'engagement_exercises_skill'
                    JOIN graph_nodes sk ON sk.node_id = e_es.target_node_id
                    WHERE e_me.source_node_id = ?
                      AND e_me.edge_type = 'metric_outcome_anchors_bundle'
                      AND COALESCE(sk.external_eligible, 0) = 1
                      AND COALESCE(sk.activation_status, '') NOT IN ('QUARANTINED_UNVERIFIED_SYNTHETIC', 'BLOCKED', 'RETIRED')
                    ORDER BY e_es.target_node_id
                    """,
                    (mid,),
                ).fetchall()
            ]
        stranded_verified_metrics.append(
            {
                "metric_id": mid,
                "label": str(row["label"] or ""),
                "employer": str(row["employer"] or ""),
                "candidate_skill_ids": cand_skills[:5],
                "auto_linkable": bool(cand_skills),
            }
        )

    isolated_nodes = [
        dict(r)
        for r in conn.execute(
            """
            SELECT node_id, node_type, label, activation_status
            FROM graph_nodes
            WHERE node_id NOT IN (
                SELECT source_node_id FROM graph_edges
                UNION
                SELECT target_node_id FROM graph_edges
            )
            ORDER BY node_type, node_id
            """
        ).fetchall()
    ]
    unlinked_facts = [
        dict(r)
        for r in conn.execute(
            """
            SELECT node_id, label, employer
            FROM graph_nodes
            WHERE node_type = 'fact'
              AND node_id NOT IN (SELECT target_node_id FROM graph_edges WHERE edge_type = 'skill_supported_by_fact')
            ORDER BY node_id
            """
        ).fetchall()
    ]
    self_loops = int(conn.execute("SELECT COUNT(*) FROM graph_edges WHERE source_node_id = target_node_id").fetchone()[0])
    dup_edges = int(
        conn.execute(
            "SELECT COUNT(*) FROM (SELECT source_node_id, target_node_id, edge_type, COUNT(*) c "
            "FROM graph_edges GROUP BY 1,2,3 HAVING c > 1)"
        ).fetchone()[0]
    )
    dangling_edges = int(
        conn.execute(
            "SELECT COUNT(*) FROM graph_edges WHERE source_node_id NOT IN (SELECT node_id FROM graph_nodes) "
            "OR target_node_id NOT IN (SELECT node_id FROM graph_nodes)"
        ).fetchone()[0]
    )
    return {
        "stranded_verified_metrics": stranded_verified_metrics,
        "stranded_auto_linkable_count": sum(1 for x in stranded_verified_metrics if x["auto_linkable"]),
        "isolated_nodes": isolated_nodes,
        "unlinked_facts": unlinked_facts,
        "self_loops": self_loops,
        "duplicate_edges": dup_edges,
        "dangling_edges": dangling_edges,
    }


def scan_promotion_readiness(conn: sqlite3.Connection) -> dict[str, Any]:
    """Scanner 4 (DIE Wave 1 Staging-to-Active Promotion parity): DRAFT structural nodes & internal skills."""
    ph = ",".join("?" for _ in STRUCTURAL_PROMOTABLE_TYPES)
    draft_structural = [
        dict(r)
        for r in conn.execute(
            f"""
            SELECT gn.node_id, gn.node_type, gn.label, gn.activation_status,
                   (SELECT COUNT(*) FROM graph_edges e
                    WHERE e.source_node_id = gn.node_id OR e.target_node_id = gn.node_id) AS edge_count
            FROM graph_nodes gn
            WHERE gn.node_type IN ({ph}) AND gn.activation_status = 'DRAFT'
            ORDER BY gn.node_type, gn.node_id
            """,
            STRUCTURAL_PROMOTABLE_TYPES,
        ).fetchall()
    ]

    internal_skills = [
        dict(r)
        for r in conn.execute(
            """
            SELECT gn.node_id, gn.label, gn.confidence_tier, gn.support_level,
                   (SELECT COUNT(*) FROM graph_edges e
                    WHERE e.source_node_id = gn.node_id AND e.edge_type = 'skill_supported_by_fact') AS fact_edges,
                   (SELECT COUNT(*) FROM graph_edges e
                    WHERE e.source_node_id = gn.node_id AND e.edge_type = 'skill_supported_by_locked_bullet') AS bullet_edges,
                   (SELECT COUNT(*) FROM graph_edges e
                    WHERE e.source_node_id = gn.node_id AND e.edge_type = 'skill_surfaces_metric_outcome') AS metric_edges
            FROM graph_nodes gn
            WHERE gn.node_type = 'skill'
              AND gn.activation_status = 'ACTIVE_CONFIRMED'
              AND COALESCE(gn.external_eligible, 0) = 0
            ORDER BY fact_edges DESC, bullet_edges DESC, gn.node_id
            """
        ).fetchall()
    ]
    for s in internal_skills:
        if int(s["fact_edges"]) > 0 or int(s["bullet_edges"]) > 0:
            s["triage"] = "PROMOTION_CANDIDATE_WITH_PROOF"
        else:
            s["triage"] = "KEEP_INTERNAL_UNLINKED"

    return {
        "draft_structural_nodes": draft_structural,
        "draft_promotable_count": sum(1 for d in draft_structural if int(d["edge_count"]) > 0),
        "internal_active_skills": internal_skills,
        "internal_skills_with_proof_count": sum(
            1 for s in internal_skills if s["triage"] == "PROMOTION_CANDIDATE_WITH_PROOF"
        ),
    }


_REPO_RELPATH_RE = re.compile(r"repo\s+evidence\s*:\s*([^\s,;\"']+)", re.IGNORECASE)
_FALLBACK_PATH_RE = re.compile(
    r"([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+/?|[A-Za-z0-9_.-]+\.(?:md|mdc|py|json|yaml|yml|sql|txt))"
)


def _extract_repo_stub_relpath(rationales: Sequence[str], description: str = "") -> str:
    for text in (*rationales, description):
        raw = str(text or "").strip()
        if not raw:
            continue
        m = _REPO_RELPATH_RE.search(raw)
        if m:
            return m.group(1).strip().strip("'\"`")
    for text in (*rationales, description):
        raw = str(text or "").strip()
        if not raw:
            continue
        m = _FALLBACK_PATH_RE.search(raw)
        if m:
            return m.group(1).strip().strip("'\"`")
    return ""


def _repo_relpath_exists(repo_root: Path | None, target_relpath: str) -> bool:
    if repo_root is None or not target_relpath.strip():
        return False
    clean = target_relpath.strip().lstrip("/")
    if not clean:
        return False
    candidates = (
        repo_root / clean,
        repo_root / "resume_graph_engine" / clean,
        repo_root / "resume_graph_engine" / "src" / clean,
    )
    return any(p.exists() for p in candidates)


def _suggested_label_for_repo_stub(node_id: str, target_relpath: str) -> str:
    clean = target_relpath.strip().rstrip("/")
    if clean:
        stem = Path(clean).stem.replace("_", " ").replace("-", " ").strip()
        if stem:
            return " ".join(stem.split()).title()
    return node_id.removeprefix("repo_").replace("_", " ").strip().title() or node_id


def scan_evidence_and_stub_hygiene(
    conn: sqlite3.Connection,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Scanner 5 (DIE Scan 4 parity): duplicate edge_evidence, hex repo_evidence stubs & sibling bloat."""
    dup_ev = int(
        conn.execute(
            "SELECT COUNT(*) FROM (SELECT edge_id, evidence_ref, COUNT(*) c FROM edge_evidence GROUP BY 1,2 HAVING c > 1)"
        ).fetchone()[0]
    )
    dangling_ev = int(
        conn.execute(
            "SELECT COUNT(*) FROM edge_evidence WHERE edge_id NOT IN (SELECT edge_id FROM graph_edges)"
        ).fetchone()[0]
    )
    hex_repo_stubs: list[dict[str, Any]] = []
    for r in conn.execute(
        "SELECT node_id, label, description FROM graph_nodes WHERE node_type = 'repo_evidence' ORDER BY node_id"
    ).fetchall():
        if not _HEX_LABEL_RE.match(str(r["label"] or "").strip()):
            continue
        stub_row = dict(r)
        nid = str(stub_row["node_id"])
        rationales = [
            str(er["rationale"] or "")
            for er in conn.execute(
                "SELECT rationale FROM graph_edges WHERE target_node_id = ? OR source_node_id = ? ORDER BY edge_id",
                (nid, nid),
            ).fetchall()
        ]
        target_relpath = _extract_repo_stub_relpath(rationales, str(stub_row.get("description") or ""))
        stub_row["target_relpath"] = target_relpath
        stub_row["suggested_label"] = _suggested_label_for_repo_stub(nid, target_relpath)
        stub_row["path_exists"] = _repo_relpath_exists(repo_root, target_relpath)
        hex_repo_stubs.append(stub_row)

    node_count = max(1, int(conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]))
    sibling_count = int(conn.execute("SELECT COUNT(*) FROM graph_sibling_links").fetchone()[0])
    sibling_ratio = round(sibling_count / node_count, 2)
    return {
        "duplicate_edge_evidence": dup_ev,
        "dangling_edge_evidence": dangling_ev,
        "hex_repo_evidence_stubs": hex_repo_stubs,
        "sibling_links_count": sibling_count,
        "sibling_links_per_node": sibling_ratio,
        "sibling_bloat_detected": sibling_ratio > 15.0,
    }


def run_pre_promotion_regression_gates(
    after_db_path: Path,
    *,
    before_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """DIE pre_promotion_regression_gates.py parity: fail-closed FTS5, quarantine, vector & topology gates."""
    conn = open_readonly_sqlite(after_db_path)
    try:
        leak = scan_quarantine_and_fts_leakage(conn)
        topo = scan_stranded_topology_and_consolidation(conn)
        su_cnt = int(conn.execute("SELECT COUNT(*) FROM semantic_unit").fetchone()[0])
        uv_cnt = int(conn.execute("SELECT COUNT(*) FROM unit_vectors").fetchone()[0])
        sp_cnt = int(conn.execute("SELECT COUNT(*) FROM assertion_learned_sparse").fetchone()[0])
        cb_cnt = int(conn.execute("SELECT COUNT(*) FROM assertion_colbert_vectors").fetchone()[0])
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()

    fts_ok = leak["fts_parity_delta"] == 0 and len(leak["fts_leaks"]) == 0
    quarantine_su_ok = len(leak["semantic_unit_leaks"]) == 0
    vector_parity_ok = su_cnt == uv_cnt and sp_cnt == cb_cnt and su_cnt > 0
    edge_hygiene_ok = topo["self_loops"] == 0 and topo["duplicate_edges"] == 0 and topo["dangling_edges"] == 0

    topo_non_regression_ok = True
    if before_metrics is not None:
        prev_iso = int(before_metrics.get("isolated_count", 10**9))
        prev_stranded = int(before_metrics.get("stranded_verified_metrics_count", 10**9))
        if len(topo["isolated_nodes"]) > prev_iso or len(topo["stranded_verified_metrics"]) > prev_stranded:
            topo_non_regression_ok = False

    passed = all((integrity == "ok", fts_ok, quarantine_su_ok, vector_parity_ok, edge_hygiene_ok, topo_non_regression_ok))
    return {
        "status": "PASS" if passed else "FAIL",
        "integrity_check": integrity,
        "fts_exact_active_parity": {"status": "PASS" if fts_ok else "FAIL", "delta": leak["fts_parity_delta"], "leaks": len(leak["fts_leaks"])},
        "quarantine_semantic_unit_isolation": {"status": "PASS" if quarantine_su_ok else "FAIL", "leaks": len(leak["semantic_unit_leaks"])},
        "vector_sparse_colbert_parity": {
            "status": "PASS" if vector_parity_ok else "FAIL",
            "semantic_units": su_cnt,
            "unit_vectors": uv_cnt,
            "sparse": sp_cnt,
            "colbert": cb_cnt,
        },
        "edge_integrity": {
            "status": "PASS" if edge_hygiene_ok else "FAIL",
            "self_loops": topo["self_loops"],
            "duplicate_edges": topo["duplicate_edges"],
            "dangling_edges": topo["dangling_edges"],
        },
        "topology_non_regression": {
            "status": "PASS" if topo_non_regression_ok else "FAIL",
            "isolated_count": len(topo["isolated_nodes"]),
            "stranded_verified_metrics_count": len(topo["stranded_verified_metrics"]),
        },
    }


def _make_cluster(
    *,
    cluster_id: str,
    title: str,
    category: str,
    severity: str,
    proposed_fix: str,
    items: list[dict[str, Any]],
    requires_isolated_scrutiny: bool,
    confidence_top: float,
    confidence_second: float,
    triage_rationale: str,
    recommended_disposition: str,
    high_risk_for_llm_judge: bool = False,
) -> dict[str, Any]:
    margin = round(confidence_top - confidence_second, 4)
    return {
        "cluster_id": cluster_id,
        "title": title,
        "category": category,
        "severity": severity,
        "proposed_fix": proposed_fix,
        "item_count": len(items),
        "requires_isolated_scrutiny": requires_isolated_scrutiny,
        "confidence_top": confidence_top,
        "confidence_second": confidence_second,
        "margin": margin,
        "autonomous_permitted": (not requires_isolated_scrutiny) and margin > 0.20 and confidence_top >= 0.65,
        "judge_metadata": {
            "panel_mode": "judge_v3_two_stage_cached",
            "high_risk_cluster": bool(high_risk_for_llm_judge),
            "triage_profile_id": "graph_hygiene:forensic_item_triage",
            "promotion_profile_id": "graph_hygiene:promotion_release_gate",
            "triage_rationale": triage_rationale,
            "recommended_disposition": recommended_disposition,
            "judged_item_count": 0,
        },
        "items": items,
    }


def build_hitl_clusters(
    dup_scan: Mapping[str, Any],
    leak_scan: Mapping[str, Any],
    topo_scan: Mapping[str, Any],
    promo_scan: Mapping[str, Any],
    stub_scan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Compile atomic, non-overlapping DIE-parity HITL decision clusters."""
    clusters: list[dict[str, Any]] = []

    leak_items = [
        {"kind": "fts_leak", **x} for x in leak_scan["fts_leaks"]
    ] + [
        {"kind": "semantic_unit_leak", **x} for x in leak_scan["semantic_unit_leaks"]
    ] + [
        {"kind": "quarantined_skill_metric_edge", **x} for x in leak_scan["quarantined_skill_metric_edges"]
    ]
    if leak_items:
        clusters.append(
            _make_cluster(
                cluster_id="CLUSTER-01-QUARANTINE-SEARCH-LEAKS",
                title="Quarantined, Blocked & Retired Leakage in Search & Skill Edges",
                category="quarantine_isolation",
                severity="P0",
                proposed_fix="purge_quarantined_search_and_edges",
                items=leak_items,
                requires_isolated_scrutiny=False,
                confidence_top=0.96,
                confidence_second=0.35,
                triage_rationale="Unverified synthetic or retired rows must stay excluded from FTS5, semantic units, and skill edges while preserving audit rows.",
                recommended_disposition="PURGE_FROM_RETRIEVAL_KEEP_QUARANTINE_NODE",
                high_risk_for_llm_judge=True,
            )
        )

    if dup_scan["exact_skill_twins"]:
        clusters.append(
            _make_cluster(
                cluster_id="CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS",
                title="Exact Duplicate Skill Labels & Phase-2 Verbatim Twins",
                category="deduplication",
                severity="P1",
                proposed_fix="merge_duplicate_skill_twins",
                items=list(dup_scan["exact_skill_twins"]),
                requires_isolated_scrutiny=True,
                confidence_top=0.88,
                confidence_second=0.72,
                triage_rationale="Exact label twins and Phase-2 copy-paste twins split retrieval rank; union facts onto canonical survivor with alias redirects.",
                recommended_disposition="MERGE_WITH_ALIAS_REDIRECT_UPON_APPROVAL",
                high_risk_for_llm_judge=True,
            )
        )

    if dup_scan["verbatim_clone_groups"]:
        clusters.append(
            _make_cluster(
                cluster_id="CLUSTER-02B-VERBATIM-CLONE-SKILL-GROUPS",
                title="Multi-Skill Verbatim Description Clone Groups",
                category="deduplication",
                severity="P1",
                proposed_fix="consolidate_or_differentiate_clone_skills",
                items=list(dup_scan["verbatim_clone_groups"]),
                requires_isolated_scrutiny=True,
                confidence_top=0.81,
                confidence_second=0.69,
                triage_rationale="Identical descriptions across distinct skills cause dense vector collisions; evaluate merge vs evidence-grounded differentiation.",
                recommended_disposition="ISOLATED_REVIEW_MERGE_OR_REWRITE_DESCRIPTIONS",
                high_risk_for_llm_judge=True,
            )
        )

    if dup_scan["domain_near_duplicates"]:
        clusters.append(
            _make_cluster(
                cluster_id="CLUSTER-02C-CAPABILITY-DOMAIN-CONSOLIDATION",
                title="Overlapping & Near-Duplicate Capability Domains",
                category="consolidation",
                severity="P2",
                proposed_fix="consolidate_overlapping_domains",
                items=list(dup_scan["domain_near_duplicates"]),
                requires_isolated_scrutiny=True,
                confidence_top=0.79,
                confidence_second=0.67,
                triage_rationale="Overlapping capability domains fragment 3-hop capability walks; verify domain consolidation against role-family projections.",
                recommended_disposition="ISOLATED_DOMAIN_CONSOLIDATION_REVIEW",
                high_risk_for_llm_judge=True,
            )
        )

    if topo_scan["stranded_verified_metrics"]:
        clusters.append(
            _make_cluster(
                cluster_id="CLUSTER-03-STRANDED-VERIFIED-METRICS",
                title="Verified APPROVED_GRAPH_SSOT Metrics With Zero Skill Edges",
                category="consolidation",
                severity="P1",
                proposed_fix="wire_stranded_verified_metrics_via_fact_closure",
                items=list(topo_scan["stranded_verified_metrics"]),
                requires_isolated_scrutiny=True,
                confidence_top=0.86,
                confidence_second=0.71,
                triage_rationale="Verified metrics lacking skill_surfaces_metric_outcome links are invisible to skill-seeded retrieval; wire only via explicit 2-hop fact or engagement proof.",
                recommended_disposition="WIRE_VIA_VERIFIED_2HOP_CLOSURE",
                high_risk_for_llm_judge=True,
            )
        )

    retired_isolated = [n for n in topo_scan["isolated_nodes"] if str(n.get("activation_status")) == "RETIRED"]
    active_isolated = [n for n in topo_scan["isolated_nodes"] if str(n.get("activation_status")) != "RETIRED"]
    if retired_isolated or active_isolated:
        clusters.append(
            _make_cluster(
                cluster_id="CLUSTER-04-ISOLATED-AND-RETIRED-NODES",
                title="Zero-Edge Isolated & Retired Graph Nodes",
                category="topology_hygiene",
                severity="P2",
                proposed_fix="archive_retired_isolated_nodes",
                items=[{"disposition": "archive_retired", **n} for n in retired_isolated]
                + [{"disposition": "review_unlinked_active", **n} for n in active_isolated],
                requires_isolated_scrutiny=True,
                confidence_top=0.85,
                confidence_second=0.70,
                triage_rationale="Archive zero-edge retired policy nodes while preserving active resume section anchors unless explicitly retired.",
                recommended_disposition="ARCHIVE_RETIRED_PRESERVE_ACTIVE_SECTIONS",
                high_risk_for_llm_judge=False,
            )
        )

    promotable_drafts = [d for d in promo_scan["draft_structural_nodes"] if int(d["edge_count"]) > 0]
    if promotable_drafts:
        clusters.append(
            _make_cluster(
                cluster_id="CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS",
                title="Edge-Backed Structural Nodes Stuck in DRAFT Status",
                category="promotion",
                severity="P1",
                proposed_fix="promote_edge_backed_draft_structural_nodes",
                items=promotable_drafts,
                requires_isolated_scrutiny=True,
                confidence_top=0.90,
                confidence_second=0.74,
                triage_rationale="Edge-backed structural pillars, domains, employments, and career tracks belong in ACTIVE status without touching DRAFT skills or unverified facts.",
                recommended_disposition="PROMOTE_STRUCTURAL_DRAFT_TO_ACTIVE",
                high_risk_for_llm_judge=False,
            )
        )

    promo_skills = [s for s in promo_scan["internal_active_skills"] if s["triage"] == "PROMOTION_CANDIDATE_WITH_PROOF"]
    if promo_skills:
        clusters.append(
            _make_cluster(
                cluster_id="CLUSTER-06-INTERNAL-SKILL-PROMOTION-TRIAGE",
                title="ACTIVE_CONFIRMED Internal Skills With Fact/Bullet Proof",
                category="promotion",
                severity="P2",
                proposed_fix="triage_internal_skills_for_external_promotion",
                items=promo_skills,
                requires_isolated_scrutiny=True,
                confidence_top=0.76,
                confidence_second=0.68,
                triage_rationale="Confirmed internal skills backed by verified facts or locked resume bullets require forensic provenance and claim-policy triage before external promotion.",
                recommended_disposition="OPERATOR_PROMOTION_TRIAGE_REQUIRED",
                high_risk_for_llm_judge=True,
            )
        )

    if stub_scan["hex_repo_evidence_stubs"] or stub_scan["sibling_bloat_detected"]:
        stub_items = [{"kind": "hex_repo_stub", **x} for x in stub_scan["hex_repo_evidence_stubs"]]
        if stub_scan["sibling_bloat_detected"]:
            stub_items.append(
                {
                    "kind": "sibling_fanout_bloat",
                    "sibling_links_count": stub_scan["sibling_links_count"],
                    "sibling_links_per_node": stub_scan["sibling_links_per_node"],
                }
            )
        clusters.append(
            _make_cluster(
                cluster_id="CLUSTER-07-STUB-AND-SIBLING-BLOAT",
                title="Hex-Labeled Repo Evidence Stubs & Sibling-Link Fan-Out Bloat",
                category="evidence_hygiene",
                severity="P2",
                proposed_fix="normalize_repo_stubs_and_cap_sibling_fanout",
                items=stub_items,
                requires_isolated_scrutiny=True,
                confidence_top=0.80,
                confidence_second=0.66,
                triage_rationale="Enrich verified live repo_evidence stubs, prune dead missing paths, and cap sibling-link fan-out to top-k peers.",
                recommended_disposition="ENRICH_STUB_LABELS_AND_CAP_SIBLINGS",
                high_risk_for_llm_judge=False,
            )
        )

    return clusters


def run_graph_hygiene_audit(
    repo_root: Path = REPO_ROOT,
    db_path: Path | None = None,
    *,
    run_llm_judge: bool = False,
    judge_clusters: Sequence[str] | None = None,
    judge_cache_path: Path | None = None,
) -> dict[str, Any]:
    """Execute full read-only DIE-parity graph hygiene, dedup, consolidation & promotion audit."""
    resolved_root = Path(repo_root).resolve()
    target_db = resolve_graph_db_path(resolved_root, db_path)
    conn = open_readonly_sqlite(target_db)
    try:
        node_count = int(conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0])
        edge_count = int(conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0])
        dup_scan = scan_duplicate_and_near_duplicate_nodes(conn)
        leak_scan = scan_quarantine_and_fts_leakage(conn)
        topo_scan = scan_stranded_topology_and_consolidation(conn)
        promo_scan = scan_promotion_readiness(conn)
        stub_scan = scan_evidence_and_stub_hygiene(conn, repo_root=resolved_root)
    finally:
        conn.close()

    regression_gates = run_pre_promotion_regression_gates(target_db)
    clusters = build_hitl_clusters(dup_scan, leak_scan, topo_scan, promo_scan, stub_scan)

    p0_clusters = [c["cluster_id"] for c in clusters if c["severity"] == "P0"]
    p1_clusters = [c["cluster_id"] for c in clusters if c["severity"] == "P1"]
    total_actionable_items = sum(int(c["item_count"]) for c in clusters)
    is_clean = len(p0_clusters) == 0 and len(p1_clusters) == 0 and regression_gates["status"] == "PASS"

    report: dict[str, Any] = {
        "schema_version": "agents.graph_hygiene_consolidation_audit.v1",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo_root": str(resolved_root),
        "db_path": str(target_db),
        "read_only": True,
        "status": "PASS" if is_clean else "FINDINGS_OPEN",
        "is_clean": is_clean,
        "baseline_counts": {
            "node_count": node_count,
            "edge_count": edge_count,
            "fts_count": leak_scan["fts_count"],
            "active_fts_expected": leak_scan["active_fts_expected"],
            "isolated_count": len(topo_scan["isolated_nodes"]),
            "stranded_verified_metrics_count": len(topo_scan["stranded_verified_metrics"]),
            "draft_structural_count": len(promo_scan["draft_structural_nodes"]),
            "exact_skill_twins_count": len(dup_scan["exact_skill_twins"]),
            "verbatim_clone_groups_count": len(dup_scan["verbatim_clone_groups"]),
            "domain_near_duplicates_count": len(dup_scan["domain_near_duplicates"]),
        },
        "pre_promotion_regression_gates": regression_gates,
        "p0_blocking_clusters": p0_clusters,
        "p1_actionable_clusters": p1_clusters,
        "total_clusters": len(clusters),
        "total_actionable_items": total_actionable_items,
        "scanners": {
            "duplicate_and_near_duplicate_nodes": dup_scan,
            "quarantine_and_fts_leakage": leak_scan,
            "stranded_topology_and_consolidation": topo_scan,
            "promotion_readiness": promo_scan,
            "evidence_and_stub_hygiene": stub_scan,
        },
        "hitl_clusters": clusters,
    }

    from tools.graph_hygiene_judge_v3 import (  # noqa: E402
        HIGH_RISK_CLUSTERS,
        evaluate_hygiene_cluster_v3,
        hydrate_audit_report_with_cached_judges,
    )

    hydrate_audit_report_with_cached_judges(report, repo_root=resolved_root, cache_path=judge_cache_path)
    if run_llm_judge:
        target_cids = set(judge_clusters) if judge_clusters else set(HIGH_RISK_CLUSTERS)
        for c in report["hitl_clusters"]:
            if c["cluster_id"] in target_cids:
                verdicts = evaluate_hygiene_cluster_v3(
                    cluster=c,
                    repo_root=resolved_root,
                    cache_path=judge_cache_path,
                )
                for it, verd in zip(c.get("items") or [], verdicts):
                    it["judge_verdict"] = verd
                c["judge_metadata"]["judged_item_count"] = sum(
                    1 for v in verdicts if v.get("llm_judge_executed")
                )

    return report


def render_cluster_markdown_preview(report: Mapping[str, Any]) -> str:
    """Render concise plain-English cluster preview table for operator HITL review."""
    lines = [
        "# Graph Hygiene, Deduplication, Consolidation & Promotion Cluster Preview",
        "",
        f"- **Database:** `{report['db_path']}`",
        f"- **Status:** `{report['status']}` (`{report['total_clusters']}` clusters, `{report['total_actionable_items']}` items)",
        f"- **Pre-Promotion Regression Gate:** `{report['pre_promotion_regression_gates']['status']}`",
        "",
        "| Cluster ID | Severity | Items | Scrutiny | Proposed Action | Judge v3 Coverage |",
        "| :--- | :---: | :---: | :---: | :--- | :---: |",
    ]
    for c in report.get("hitl_clusters") or []:
        scrutiny = "HITL_REQUIRED" if c["requires_isolated_scrutiny"] else "AUTONOMOUS_OK"
        jmeta = c.get("judge_metadata") or {}
        judged = int(jmeta.get("judged_item_count") or 0)
        tier_tag = "HIGH_RISK" if jmeta.get("high_risk_cluster") else "STANDARD"
        lines.append(
            f"| `{c['cluster_id']}` | {c['severity']} | {c['item_count']} | {scrutiny} | "
            f"`{c['proposed_fix']}` | `{judged}/{c['item_count']} ({tier_tag})` |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DIE-parity read-only Graph Hygiene, Dedup, Consolidation & Promotion Auditor.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--read-only", action="store_true", help="Enforce strictly read-only audit (always on).")
    parser.add_argument("--json", action="store_true", help="Emit full JSON hygiene package.")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown cluster preview table.")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write JSON hygiene package.")
    parser.add_argument("--strict-hygiene", action="store_true", help="Exit 1 when any P0/P1 hygiene cluster is open.")
    parser.add_argument("--run-llm-judge", action="store_true", help="Execute live Stage B Judge v3 forensic triage on high-risk clusters.")
    parser.add_argument("--judge-clusters", type=str, default="", help="Optional comma-separated cluster IDs to judge.")
    args = parser.parse_args(argv)

    selected_judge_clusters = [c.strip() for c in args.judge_clusters.split(",") if c.strip()] or None
    report = run_graph_hygiene_audit(
        repo_root=args.repo_root,
        db_path=args.db,
        run_llm_judge=bool(args.run_llm_judge),
        judge_clusters=selected_judge_clusters,
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.markdown:
        print(render_cluster_markdown_preview(report))
    elif args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_cluster_markdown_preview(report))

    if args.strict_hygiene:
        return 0 if report["is_clean"] else 1
    return 0 if report["pre_promotion_regression_gates"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
