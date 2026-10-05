"""Deep Graph Traversal Engine (Wave 4 / AC4.1-AC4.3, AC4.7).

Provides governed multi-hop graph traversal over read-only C0.3 SQLite snapshot:
- Recursive CTE with cycle detection, depth cap, and step-level edge type gating.
- Forward, inverse, and bidirectional traversal support.
- Path confidence propagation with hop-discounting and pass-fail structural gating.
- Lineage, evidence resolution, and proof status classification.
- Canonical journeys:
    1. skill -> fact -> metric_outcome -> employment -> career_epoch
    2. skill -> engagement -> employment
    3. metric_outcome -> fact -> skill (inverse)
    4. capability_domain -> skill -> evidence
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Sequence

# Canonical journey names
JOURNEY_SKILL_FACT_METRIC_EMPLOYMENT_EPOCH = "skill_fact_metric_employment_epoch"
JOURNEY_SKILL_ENGAGEMENT_EMPLOYMENT = "skill_engagement_employment"
JOURNEY_METRIC_FACT_SKILL = "metric_fact_skill"
JOURNEY_DOMAIN_SKILL_EVIDENCE = "domain_skill_evidence"

CANONICAL_JOURNEYS: dict[str, dict[str, Any]] = {
    JOURNEY_SKILL_FACT_METRIC_EMPLOYMENT_EPOCH: {
        "description": "Skill to Career Epoch via Fact, Metric Outcome, and Employment",
        "direction": "forward",
        "max_depth": 4,
        "steps": [
            ("skill_supported_by_fact", "skill", "fact"),
            ("fact_has_metric_outcome", "fact", "metric_outcome"),
            ("metric_outcome_bound_to_employer", "metric_outcome", "employment"),
            ("employment_in_epoch", "employment", "career_epoch"),
        ],
    },
    JOURNEY_SKILL_ENGAGEMENT_EMPLOYMENT: {
        "description": "Skill to Employment via Role-Episode Engagement",
        "direction": "custom",
        "max_depth": 2,
        "steps": [
            ("skill_exercised_in_engagement", "skill", "engagement"),
            ("engagement_at_employment", "engagement", "employment"),
        ],
    },
    JOURNEY_METRIC_FACT_SKILL: {
        "description": "Metric Outcome to Skill via Fact (Inverse Traversal)",
        "direction": "inverse",
        "max_depth": 2,
        "steps": [
            ("metric_outcome_from_fact", "metric_outcome", "fact"),
            ("fact_supports_skill", "fact", "skill"),
        ],
    },
    JOURNEY_DOMAIN_SKILL_EVIDENCE: {
        "description": "Capability Domain to Evidence via Skill Containment",
        "direction": "forward",
        "max_depth": 2,
        "steps": [
            ("capability_domain_contains_skill", "capability_domain", "skill"),
            ("skill_supported_by_fact", "skill", "fact"),
        ],
    },
}

CLAIM_BEARING_ASSERTION_TYPES = {
    "EVIDENTIAL_SUPPORT",
    "METRIC_BINDING",
}


@dataclass(frozen=True)
class TraversalPath:
    """Represents a validated multi-hop path through the graph."""

    path_id: str
    journey_name: str
    start_node_id: str
    end_node_id: str
    path_depth: int
    node_path: list[str]
    edge_path: list[str]
    edge_types: list[str]
    assertion_types: list[str]
    path_confidence: float
    weakest_edge: dict[str, Any]
    evidence_ids: list[str]
    build_run_id: str
    is_proof: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compute_path_id(node_path: list[str], edge_path: list[str]) -> str:
    payload = "->".join(node_path) + "|" + ",".join(edge_path)
    return "path:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _load_edge_cache(
    conn: sqlite3.Connection,
    edge_ids: Sequence[str],
) -> dict[str, dict[str, Any]]:
    if not edge_ids:
        return {}
    placeholders = ",".join("?" for _ in edge_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT edge_id, source_node_id, target_node_id, edge_type,
               confidence_score, confidence_tier, weight,
               assertion_type, traversable, build_run_id
        FROM graph_edges
        WHERE edge_id IN ({placeholders})
        """,
        tuple(edge_ids),
    )
    cols = [
        "edge_id",
        "source_node_id",
        "target_node_id",
        "edge_type",
        "confidence_score",
        "confidence_tier",
        "weight",
        "assertion_type",
        "traversable",
        "build_run_id",
    ]
    return {r[0]: dict(zip(cols, r, strict=False)) for r in cur.fetchall()}


def _load_evidence_map(
    conn: sqlite3.Connection,
    edge_ids: Sequence[str],
) -> dict[str, list[str]]:
    if not edge_ids:
        return {}
    placeholders = ",".join("?" for _ in edge_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT edge_id, evidence_ref, evidence_node_id
        FROM edge_evidence
        WHERE edge_id IN ({placeholders})
        """,
        tuple(edge_ids),
    )
    mapping: dict[str, list[str]] = {}
    for edge_id, ref, node_id in cur.fetchall():
        target = node_id or ref
        if target:
            mapping.setdefault(edge_id, []).append(target)
    return mapping


def _build_step_conditions(
    steps: Sequence[Any],
    direction: str,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for depth, step in enumerate(steps):
        if isinstance(step, tuple):
            edge_type = step[0]
        else:
            edge_type = str(step)
        clauses.append(f"(t.depth = {depth} AND e.edge_type = ?)")
        params.append(edge_type)
    return " OR ".join(clauses), params


def traverse(
    conn: sqlite3.Connection,
    seeds: Sequence[str],
    *,
    direction: str = "forward",
    max_depth: int = 4,
    allowed_steps: Sequence[Any] | None = None,
    max_paths: int = 1000,
    min_path_confidence: float = 0.0,
    discount_factor: float = 0.95,
    journey_name: str = "custom_traversal",
) -> list[TraversalPath]:
    """Execute deep traversal using recursive CTE with cycle prevention and depth budgeting.

    Args:
        conn: Open SQLite connection.
        seeds: List of starting node IDs.
        direction: 'forward', 'inverse', or 'custom'.
        max_depth: Maximum path depth (1-6).
        allowed_steps: Sequence of step specifications (edge_type or tuple).
        max_paths: Maximum number of paths to collect.
        min_path_confidence: Minimum score threshold (0.0 - 1.0).
        discount_factor: Multiplicative penalty per hop (default: 0.95).
        journey_name: Label for emitted paths.

    Returns:
        List of TraversalPath records satisfying all constraints.
    """
    if not seeds:
        return []

    # AC4.2: Unrestricted deep walk rejection
    if allowed_steps is None:
        if max_depth >= 3:
            raise ValueError(
                f"Unrestricted graph traversal at depth={max_depth} >= 3 is strictly rejected. "
                "allowed_steps must be explicitly specified to bound blast radius."
            )

    seeds_clean = [str(s).strip() for s in seeds if str(s).strip()]
    if not seeds_clean:
        return []

    seed_placeholders = ",".join("?" for _ in seeds_clean)
    params: list[Any] = list(seeds_clean)

    step_condition_sql = ""
    step_params: list[Any] = []
    if allowed_steps:
        step_sql, step_params = _build_step_conditions(allowed_steps, direction)
        step_condition_sql = f"AND ({step_sql})"

    # Choose edge relation: for custom/inverse, allow querying graph_edges or reverse
    # We join directly on graph_edges for high index performance
    # For inverse: e.target_node_id = t.current_node
    is_inverse = direction == "inverse"
    join_on = (
        "e.target_node_id = t.current_node"
        if is_inverse
        else "e.source_node_id = t.current_node"
    )
    next_node_col = "e.source_node_id" if is_inverse else "e.target_node_id"

    # In reverse/inverse mode, map edge_type from inverse label if allowed_steps specifies inverse
    # For inverse canonical steps, we match against edge_type in graph_edges via target join
    cte_sql = f"""
    WITH RECURSIVE traversal(start_node, current_node, depth, path_nodes, path_edges, path_types) AS (
        SELECT node_id, node_id, 0, node_id, '', ''
        FROM graph_nodes
        WHERE node_id IN ({seed_placeholders})
      UNION ALL
        SELECT t.start_node, {next_node_col}, t.depth + 1,
               t.path_nodes || '->' || {next_node_col},
               t.path_edges || (CASE WHEN t.path_edges = '' THEN '' ELSE ',' END) || e.edge_id,
               t.path_types || (CASE WHEN t.path_types = '' THEN '' ELSE ',' END) || e.edge_type
        FROM traversal t
        JOIN graph_edges e ON {join_on}
        WHERE t.depth < ?
          AND INSTR('->' || t.path_nodes || '->', '->' || {next_node_col} || '->') = 0
          AND e.traversable = 1
          {step_condition_sql}
    )
    SELECT start_node, current_node, depth, path_nodes, path_edges, path_types
    FROM traversal
    WHERE depth = ?
    LIMIT ?;
    """

    exec_params = list(seeds_clean) + [max_depth] + list(step_params) + [max_depth, max_paths]

    cur = conn.cursor()
    cur.execute(cte_sql, tuple(exec_params))
    raw_rows = cur.fetchall()

    if not raw_rows:
        return []

    # Gather all referenced edges to load metadata and evidence in batch
    all_edge_ids: set[str] = set()
    parsed_paths: list[dict[str, Any]] = []
    for r in raw_rows:
        start_node, end_node, depth, nodes_str, edges_str, types_str = r
        node_list = nodes_str.split("->")
        edge_list = edges_str.split(",") if edges_str else []
        type_list = types_str.split(",") if types_str else []
        all_edge_ids.update(edge_list)
        parsed_paths.append(
            {
                "start_node": start_node,
                "end_node": end_node,
                "depth": depth,
                "node_list": node_list,
                "edge_list": edge_list,
                "type_list": type_list,
            }
        )

    edge_cache = _load_edge_cache(conn, list(all_edge_ids))
    evidence_map = _load_evidence_map(conn, list(all_edge_ids))

    results: list[TraversalPath] = []
    for p in parsed_paths:
        edge_list = p["edge_list"]
        node_list = p["node_list"]
        type_list = p["type_list"]

        assertion_types: list[str] = []
        claim_confidences: list[float] = []
        weakest_edge: dict[str, Any] = {}
        min_conf = 1.0
        is_proof = True
        build_run_id = ""

        path_evidence_ids: list[str] = []
        for eid in edge_list:
            edge_data = edge_cache.get(eid, {})
            build_run_id = edge_data.get("build_run_id") or build_run_id
            atype = edge_data.get("assertion_type", "STRUCTURAL_CONTAINMENT")
            assertion_types.append(atype)

            conf_score = edge_data.get("confidence_score")
            weight = edge_data.get("weight", 1.0)

            # Evidential / metric claim edges must be scored
            if atype in CLAIM_BEARING_ASSERTION_TYPES:
                if conf_score is not None:
                    score = float(conf_score)
                    claim_confidences.append(score)
                    if score < min_conf:
                        min_conf = score
                        weakest_edge = dict(edge_data)
                else:
                    # Unscored claim-bearing edge marks path as non-proof
                    claim_confidences.append(0.50)
                    is_proof = False
                    if 0.50 < min_conf:
                        min_conf = 0.50
                        weakest_edge = dict(edge_data)
            else:
                # Structural/policy edges behave as pass/fail
                pass

            ev_ids = evidence_map.get(eid, [])
            path_evidence_ids.extend(ev_ids)

        # Path confidence calculation: product of claim scores * discount^(k-1)
        k = len(edge_list)
        discount = (discount_factor ** max(0, k - 1)) if k > 1 else 1.0
        score_product = 1.0
        for sc in claim_confidences:
            score_product *= sc
        final_confidence = round(score_product * discount, 4)

        if not path_evidence_ids:
            is_proof = False

        if final_confidence < min_path_confidence:
            continue

        path_id = _compute_path_id(node_list, edge_list)
        results.append(
            TraversalPath(
                path_id=path_id,
                journey_name=journey_name,
                start_node_id=p["start_node"],
                end_node_id=p["end_node"],
                path_depth=p["depth"],
                node_path=node_list,
                edge_path=edge_list,
                edge_types=type_list,
                assertion_types=assertion_types,
                path_confidence=final_confidence,
                weakest_edge=weakest_edge,
                evidence_ids=sorted(set(path_evidence_ids)),
                build_run_id=build_run_id,
                is_proof=is_proof,
            )
        )

    return results


def traverse_journey(
    conn: sqlite3.Connection,
    journey_name: str,
    seeds: Sequence[str],
    *,
    max_paths: int = 1000,
    min_path_confidence: float = 0.0,
) -> list[TraversalPath]:
    """Execute one of the four named canonical journeys."""
    if journey_name not in CANONICAL_JOURNEYS:
        raise ValueError(
            f"Unknown canonical journey: {journey_name!r}. "
            f"Must be one of: {list(CANONICAL_JOURNEYS.keys())}"
        )

    spec = CANONICAL_JOURNEYS[journey_name]

    if journey_name == JOURNEY_SKILL_ENGAGEMENT_EMPLOYMENT:
        # Custom bidirectional join:
        # Step 1: skill <- engagement via engagement_exercises_skill (target join)
        # Step 2: engagement -> employment via engagement_at_employment (source join)
        cur = conn.cursor()
        seeds_clean = [str(s).strip() for s in seeds if str(s).strip()]
        if not seeds_clean:
            return []
        seed_placeholders = ",".join("?" for _ in seeds_clean)
        sql = f"""
        SELECT e1.target_node_id AS skill_id,
               e1.source_node_id AS engagement_id,
               e2.target_node_id AS employment_id,
               e1.edge_id AS edge1_id,
               e2.edge_id AS edge2_id,
               e1.edge_type AS edge1_type,
               e2.edge_type AS edge2_type
        FROM graph_edges e1
        JOIN graph_edges e2 ON e1.source_node_id = e2.source_node_id
           AND e2.edge_type = 'engagement_at_employment'
           AND e2.traversable = 1
        WHERE e1.edge_type = 'engagement_exercises_skill'
          AND e1.traversable = 1
          AND e1.target_node_id IN ({seed_placeholders})
        LIMIT ?;
        """
        params = list(seeds_clean)
        params.append(max_paths)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()

        all_edges = [r[3] for r in rows] + [r[4] for r in rows]
        edge_cache = _load_edge_cache(conn, all_edges)
        evidence_map = _load_evidence_map(conn, all_edges)

        results: list[TraversalPath] = []
        for r in rows:
            skill_id, eng_id, emp_id, e1_id, e2_id, e1_type, e2_type = r
            node_path = [skill_id, eng_id, emp_id]
            edge_path = [e1_id, e2_id]
            edge_types = [e1_type, e2_type]

            ed1 = edge_cache.get(e1_id, {})
            ed2 = edge_cache.get(e2_id, {})
            assertion_types = [
                ed1.get("assertion_type", "EVIDENTIAL_SUPPORT"),
                ed2.get("assertion_type", "STRUCTURAL_CONTAINMENT"),
            ]
            c1 = float(ed1.get("confidence_score") or 0.85)
            c2 = float(ed2.get("confidence_score") or 1.0)
            path_conf = round(c1 * c2 * 0.95, 4)

            ev_ids = evidence_map.get(e1_id, []) + evidence_map.get(e2_id, [])
            weakest = ed1 if c1 <= c2 else ed2

            results.append(
                TraversalPath(
                    path_id=_compute_path_id(node_path, edge_path),
                    journey_name=journey_name,
                    start_node_id=skill_id,
                    end_node_id=emp_id,
                    path_depth=2,
                    node_path=node_path,
                    edge_path=edge_path,
                    edge_types=edge_types,
                    assertion_types=assertion_types,
                    path_confidence=path_conf,
                    weakest_edge=weakest,
                    evidence_ids=sorted(set(ev_ids)),
                    build_run_id=ed1.get("build_run_id") or "",
                    is_proof=bool(ev_ids and path_conf >= 0.70),
                )
            )
        return results

    if journey_name == JOURNEY_METRIC_FACT_SKILL:
        # Inverse traversal: metric_outcome -> fact -> skill
        # Step 1: metric <- fact via fact_has_metric_outcome (target join)
        # Step 2: fact <- skill via skill_supported_by_fact (target join)
        cur = conn.cursor()
        seeds_clean = [str(s).strip() for s in seeds if str(s).strip()]
        if not seeds_clean:
            return []
        seed_placeholders = ",".join("?" for _ in seeds_clean)
        sql = f"""
        SELECT e1.target_node_id AS metric_id,
               e1.source_node_id AS fact_id,
               e2.source_node_id AS skill_id,
               e1.edge_id AS edge1_id,
               e2.edge_id AS edge2_id,
               'metric_outcome_from_fact' AS edge1_type,
               'fact_supports_skill' AS edge2_type
        FROM graph_edges e1
        JOIN graph_edges e2 ON e1.source_node_id = e2.target_node_id
           AND e2.edge_type = 'skill_supported_by_fact'
           AND e2.traversable = 1
        WHERE e1.edge_type = 'fact_has_metric_outcome'
          AND e1.traversable = 1
          AND e1.target_node_id IN ({seed_placeholders})
        LIMIT ?;
        """
        params = list(seeds_clean)
        params.append(max_paths)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()

        all_edges = [r[3] for r in rows] + [r[4] for r in rows]
        edge_cache = _load_edge_cache(conn, all_edges)
        evidence_map = _load_evidence_map(conn, all_edges)

        results: list[TraversalPath] = []
        for r in rows:
            metric_id, fact_id, skill_id, e1_id, e2_id, e1_type, e2_type = r
            node_path = [metric_id, fact_id, skill_id]
            edge_path = [e1_id, e2_id]
            edge_types = [e1_type, e2_type]

            ed1 = edge_cache.get(e1_id, {})
            ed2 = edge_cache.get(e2_id, {})
            assertion_types = [
                ed1.get("assertion_type", "METRIC_BINDING"),
                ed2.get("assertion_type", "EVIDENTIAL_SUPPORT"),
            ]
            c1 = float(ed1.get("confidence_score") or 0.90)
            c2 = float(ed2.get("confidence_score") or 0.85)
            path_conf = round(c1 * c2 * 0.95, 4)

            ev_ids = evidence_map.get(e1_id, []) + evidence_map.get(e2_id, [])
            weakest = ed1 if c1 <= c2 else ed2

            results.append(
                TraversalPath(
                    path_id=_compute_path_id(node_path, edge_path),
                    journey_name=journey_name,
                    start_node_id=metric_id,
                    end_node_id=skill_id,
                    path_depth=2,
                    node_path=node_path,
                    edge_path=edge_path,
                    edge_types=edge_types,
                    assertion_types=assertion_types,
                    path_confidence=path_conf,
                    weakest_edge=weakest,
                    evidence_ids=sorted(set(ev_ids)),
                    build_run_id=ed1.get("build_run_id") or "",
                    is_proof=bool(ev_ids and path_conf >= 0.70),
                )
            )
        return results

    # Forward canonical journeys (Journey 1 and Journey 4)
    step_types = [s[0] for s in spec["steps"]]
    return traverse(
        conn,
        seeds,
        direction=spec["direction"],
        max_depth=spec["max_depth"],
        allowed_steps=step_types,
        max_paths=max_paths,
        min_path_confidence=min_path_confidence,
        journey_name=journey_name,
    )
