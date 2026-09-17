"""Verify graphDB integrity, multi-hop traversal, and BGE-M3 embedding vectors.

Plan: graph-skills-metrics-embeddings-completion-b4e8a2 Wave 5.
"""
from __future__ import annotations

import math
import sqlite3
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RG_ROOT = ROOT / "resume_graph_engine"
SRC = RG_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(RG_ROOT) not in sys.path:
    sys.path.insert(0, str(RG_ROOT))

from apps_rg.fact_inventory.graph_sqlite_path_index import (
    validate_graphdb_capability_integrity,
)
from apps_rg.runtime.graph_skill_hybrid_retrieval import (
    fuse_dense_bm25,
)


def verify_graph_database(db_path: Path) -> dict[str, int | str]:
    if not db_path.is_file():
        raise FileNotFoundError(f"SQLite graph DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    # 1. Check basic node and edge volume
    c.execute("SELECT count(*) FROM graph_nodes")
    node_count = c.fetchone()[0]
    c.execute("SELECT count(*) FROM graph_edges")
    edge_count = c.fetchone()[0]

    if node_count < 300:
        raise ValueError(f"Insufficient node count: {node_count} < 300")
    if edge_count < 2000:
        raise ValueError(f"Insufficient edge count: {edge_count} < 2000")

    # 2. Check 3-hop traversal: domain -> skill -> fact -> metric
    c.execute(
        """
        SELECT e1.source_node_id, e1.target_node_id, e2.target_node_id, e3.target_node_id,
               n1.node_type, n2.node_type, n3.node_type, n4.node_type
        FROM graph_edges e1
        JOIN graph_edges e2 ON e1.target_node_id = e2.source_node_id
        JOIN graph_edges e3 ON e2.target_node_id = e3.source_node_id
        JOIN graph_nodes n1 ON e1.source_node_id = n1.node_id
        JOIN graph_nodes n2 ON e1.target_node_id = n2.node_id
        JOIN graph_nodes n3 ON e2.target_node_id = n3.node_id
        JOIN graph_nodes n4 ON e3.target_node_id = n4.node_id
        WHERE e1.edge_type = 'capability_domain_contains_skill'
          AND e2.edge_type = 'skill_supported_by_fact'
          AND e3.edge_type = 'fact_has_metric_outcome'
        """
    )
    paths = c.fetchall()
    traversal_count = len(paths)
    if traversal_count == 0:
        raise ValueError("3-hop domain -> skill -> fact -> metric traversal returned 0 paths")

    # Verify each path is acyclic and strictly typed
    for s, h1, h2, t, t1, t2, t3, t4 in paths:
        nodes = [s, h1, h2, t]
        if len(set(nodes)) != 4:
            raise ValueError(f"Cycle detected in 3-hop traversal: {nodes}")
        if t1 != "capability_domain" or t2 != "skill" or t3 not in ("fact", "locked_bullet", "employment") or t4 != "metric_outcome":
            raise ValueError(f"Endpoint type violation in path: {[t1, t2, t3, t4]}")

    # 3. Check reverse view existence and coverage
    c.execute("SELECT count(*) FROM graph_edges_reverse")
    reverse_edge_count = c.fetchone()[0]
    if reverse_edge_count != edge_count:
        raise ValueError(
            f"Reverse edge view count mismatch: {reverse_edge_count} != {edge_count}"
        )

    # 4. Check capability index integrity
    integrity = validate_graphdb_capability_integrity(conn)
    if integrity.get("status") != "GRAPHDB_CAPABILITY_INTEGRITY_PASS":
        raise ValueError(f"GraphDB capability integrity failed: {integrity}")

    conn.close()
    return {
        "status": "PASS",
        "node_count": node_count,
        "edge_count": edge_count,
        "three_hop_traversal_paths": traversal_count,
        "reverse_edge_count": reverse_edge_count,
    }


def verify_bge_m3_embeddings(embedding_dirs: list[Path], db_path: Path) -> dict[str, int | str | float]:
    total_vectors = 0
    dim_target = 1024
    vector_files = []

    for d in embedding_dirs:
        if d.is_dir():
            vector_files.extend(d.glob("*.sqlite"))

    if not vector_files:
        raise FileNotFoundError(f"No vector SQLite files found in {embedding_dirs}")

    # Get retrieval-eligible skill IDs from SQLite
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT node_id FROM graph_nodes WHERE node_type = 'skill' AND external_eligible = 1")
    eligible_ids = set(r[0] for r in cur.fetchall())
    conn.close()

    min_sim_global = 1.0
    max_sim_global = -1.0
    mean_sim_global = 0.0

    for vf in vector_files:
        conn = sqlite3.connect(str(vf))
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]

        target_table = None
        vec_col = None
        for tbl in ("assertion_vectors", "assertion_embeddings", "cluster_embeddings", "vectors", "embeddings"):
            if tbl in tables:
                target_table = tbl
                break

        if not target_table:
            conn.close()
            continue

        c.execute(f"PRAGMA table_info({target_table})")
        cols = c.fetchall()
        id_col = cols[0][1]
        for col in cols:
            cname = col[1].lower()
            ctype = col[2].upper()
            if cname in ("vector", "embedding") or ("BLOB" in ctype and "sha" not in cname):
                vec_col = col[1]
                break

        if not vec_col:
            conn.close()
            continue

        c.execute(f"SELECT {id_col}, {vec_col} FROM {target_table}")
        rows = c.fetchall()
        file_vectors = []
        file_ids = set()

        for aid, blob in rows:
            if not isinstance(blob, bytes):
                continue
            if len(blob) != dim_target * 4:
                raise ValueError(
                    f"Vector length mismatch in {vf.name}: {len(blob)} bytes != {dim_target * 4} bytes"
                )
            floats = struct.unpack(f"{dim_target}f", blob)
            norm = math.sqrt(sum(x * x for x in floats))
            if abs(norm - 1.0) > 1e-4:
                raise ValueError(
                    f"Vector not L2 normalized in {vf.name}: norm={norm:.6f} (expected 1.0)"
                )
            if any(math.isnan(x) or math.isinf(x) for x in floats):
                raise ValueError(f"Vector contains NaN/Inf in {vf.name}")
            file_vectors.append(floats)
            file_ids.add(str(aid))
            total_vectors += 1

        # Cosine spectrum verification for assertion_vectors table
        if target_table == "assertion_vectors" and len(file_vectors) > 1:
            if file_ids != eligible_ids:
                diff = file_ids ^ eligible_ids
                raise ValueError(f"Assertion vector ID mismatch against graph: {len(diff)} IDs differ")

            # Compute pairwise cosine similarities: vectors are unit norm
            n = len(file_vectors)
            sim_sum = 0.0
            pair_count = 0
            for i in range(n):
                vi = file_vectors[i]
                for j in range(i + 1, n):
                    vj = file_vectors[j]
                    dot = sum(a * b for a, b in zip(vi, vj))
                    if dot < min_sim_global:
                        min_sim_global = dot
                    if dot > max_sim_global:
                        max_sim_global = dot
                    sim_sum += dot
                    pair_count += 1

            mean_sim = sim_sum / pair_count if pair_count else 0.0
            mean_sim_global = mean_sim

            if min_sim_global < 0.0:
                raise ValueError(f"Negative cosine similarity observed: {min_sim_global:.4f}")
            if max_sim_global >= 0.98:
                raise ValueError(f"Near-duplicate vector collapse detected: max={max_sim_global:.4f} >= 0.98")
            if not (0.50 <= mean_sim <= 0.80):
                raise ValueError(f"Mean cosine similarity out of healthy bounds: {mean_sim:.4f}")

        conn.close()

    if total_vectors == 0:
        raise ValueError("Zero vectors verified across embedding sqlite databases")

    return {
        "status": "PASS",
        "verified_vectors_count": total_vectors,
        "dimension": dim_target,
        "l2_norm_validated": True,
        "min_cosine": round(min_sim_global, 4),
        "max_cosine": round(max_sim_global, 4),
        "mean_cosine": round(mean_sim_global, 4),
    }


def verify_hybrid_retrieval_stage2() -> dict[str, str | float]:
    fused = fuse_dense_bm25(
        [
            {"assertion_id": "skill_alpha", "similarity": 0.91},
            {"assertion_id": "skill_beta", "similarity": 0.88},
        ],
        [
            {"assertion_id": "skill_alpha", "bm25_score": 1.5},
            {"assertion_id": "skill_beta", "bm25_score": 1.5},
        ],
        assertion_ids={"skill_alpha", "skill_beta"},
        metric_bearing_assertion_ids={"skill_beta"},
        metric_boost=0.05,
    )
    if fused[0]["assertion_id"] != "skill_beta":
        raise ValueError("Stage 2 metric boost did not prioritize metric-bearing skill")

    # Validate fail-closed behavior on out-of-bounds boost
    try:
        fuse_dense_bm25(
            [{"assertion_id": "skill_alpha", "similarity": 0.91}],
            [{"assertion_id": "skill_alpha", "bm25_score": 1.5}],
            assertion_ids={"skill_alpha"},
            metric_bearing_assertion_ids={"skill_alpha"},
            metric_boost=0.50,
        )
        raise AssertionError("Expected error on metric_boost > 0.20")
    except Exception as exc:
        if "metric_boost" not in str(exc):
            raise

    # Validate fail-closed behavior on unauthorized metric assertion IDs
    try:
        fuse_dense_bm25(
            [{"assertion_id": "skill_alpha", "similarity": 0.91}],
            [{"assertion_id": "skill_alpha", "bm25_score": 1.5}],
            assertion_ids={"skill_alpha"},
            metric_bearing_assertion_ids={"skill_unauthorized"},
            metric_boost=0.05,
        )
        raise AssertionError("Expected error on unauthorized metric_bearing_assertion_ids")
    except Exception as exc:
        if "unauthorized IDs" not in str(exc):
            raise

    return {
        "status": "PASS",
        "top_assertion": str(fused[0]["assertion_id"]),
        "boost_applied": float(fused[0]["metric_authority_boost"]),
    }


def run_full_verification() -> None:
    db_path = RG_ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
    emb_dirs = [
        ROOT / "artifacts/apps_rg/c03/graph_skill_embeddings",
        ROOT / "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings",
        RG_ROOT / "artifacts/apps_rg/c03/graph_skill_embeddings",
        RG_ROOT / "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings",
    ]

    print("--> 1. Verifying GraphDB Traversal, Acyclicity & Capabilities...")
    graph_res = verify_graph_database(db_path)
    print(f"    GraphDB: nodes={graph_res['node_count']}, edges={graph_res['edge_count']}, 3-hop paths={graph_res['three_hop_traversal_paths']}")

    print("--> 2. Verifying BGE-M3 Embeddings & Cosine Spectrum...")
    emb_res = verify_bge_m3_embeddings(emb_dirs, db_path)
    print(f"    Embeddings: verified {emb_res['verified_vectors_count']} vectors, dim={emb_res['dimension']}, L2-norm=1.000000")
    print(f"    Spectrum: min={emb_res['min_cosine']}, mean={emb_res['mean_cosine']}, max={emb_res['max_cosine']}")

    print("--> 3. Verifying Stage 2 Metric Authority Boost & Input Validation...")
    ret_res = verify_hybrid_retrieval_stage2()
    print(f"    Hybrid Retrieval: boost={ret_res['boost_applied']}, top={ret_res['top_assertion']}")

    print("\n=======================================================")
    print("GRAPHDB_TRAVERSAL_AND_EMBEDDINGS_PASS")
    print("=======================================================")


if __name__ == "__main__":
    run_full_verification()

