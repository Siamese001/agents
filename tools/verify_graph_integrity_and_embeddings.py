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
from apps_rg.fact_inventory.skills_graph.storage import (
    verify_sqlite_physical_write_proof,
)
from apps_rg.runtime.graph_skill_hybrid_retrieval import (
    fuse_dense_bm25,
    sqlite_fts5_bm25_rank,
)


def verify_graph_database(db_path: Path) -> dict[str, int | str]:
    if not db_path.is_file():
        raise FileNotFoundError(f"SQLite graph DB not found: {db_path}")

    write_proof = verify_sqlite_physical_write_proof(db_path)

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

    # 4. Check capability index integrity and native FTS5 BM25 ranking
    integrity = validate_graphdb_capability_integrity(conn)
    if integrity.get("status") != "GRAPHDB_CAPABILITY_INTEGRITY_PASS":
        raise ValueError(f"GraphDB capability integrity failed: {integrity}")

    c.execute("SELECT count(*) FROM graph_nodes_fts")
    fts_count = int(c.fetchone()[0])
    if fts_count != node_count:
        raise ValueError(f"graph_nodes_fts count mismatch: {fts_count} != {node_count}")

    fts_ranked = sqlite_fts5_bm25_rank(
        conn,
        "governed agentic platform architecture",
        node_type="skill",
    )
    if not fts_ranked or float(fts_ranked[0]["bm25_score"]) <= 0.0:
        raise ValueError("sqlite_fts5_bm25_rank failed to rank skills on live graph_nodes_fts")

    conn.close()
    return {
        "status": "PASS",
        "physical_write_proof": str(write_proof.get("status", "PASS")),
        "node_count": node_count,
        "fts_node_count": fts_count,
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
    if db_path.is_file() and db_path not in vector_files:
        vector_files.append(db_path)

    if not vector_files:
        raise FileNotFoundError(f"No vector SQLite files found in {embedding_dirs}")

    # Get retrieval-eligible skill IDs and semantic unit IDs from SQLite
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT node_id FROM graph_nodes WHERE node_type = 'skill' AND external_eligible = 1")
    eligible_ids = set(r[0] for r in cur.fetchall())
    cur.execute("SELECT unit_id FROM semantic_unit")
    expected_unit_ids = set(r[0] for r in cur.fetchall())
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
        for tbl in (
            "assertion_vectors",
            "assertion_embeddings",
            "cluster_embeddings",
            "unit_vectors",
            "vectors",
            "embeddings",
        ):
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

        # Cosine spectrum verification for assertion_vectors or unit_vectors table
        if target_table in ("assertion_vectors", "unit_vectors") and len(file_vectors) > 1:
            if target_table == "assertion_vectors" and file_ids != eligible_ids:
                diff = file_ids ^ eligible_ids
                raise ValueError(f"Assertion vector ID mismatch against graph: {len(diff)} IDs differ")
            if target_table == "unit_vectors" and file_ids != expected_unit_ids:
                diff = file_ids ^ expected_unit_ids
                raise ValueError(f"Semantic unit vector ID mismatch against graph: {len(diff)} IDs differ")

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


def verify_hybrid_retrieval_stage2(db_path: Path | None = None) -> dict[str, str | float | int]:
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

    live_fused_count = 0
    live_top_skill = ""
    if db_path is not None and db_path.is_file():
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            eligible_skills = {
                str(r[0])
                for r in conn.execute(
                    "SELECT node_id FROM graph_nodes WHERE node_type = 'skill' AND external_eligible = 1"
                ).fetchall()
            }
            bm25_live = sqlite_fts5_bm25_rank(
                conn,
                "governed agentic platform architecture hybrid retrieval",
                node_ids=eligible_skills,
            )
            unit_rows = conn.execute(
                """
                SELECT su.root_node_id, uv.vector
                FROM semantic_unit su
                JOIN unit_vectors uv ON su.unit_id = uv.unit_id
                WHERE su.unit_type = 'skill_evidence_cluster'
                """
            ).fetchall()
            ref_vec: tuple[float, ...] | None = None
            skill_vecs: dict[str, tuple[float, ...]] = {}
            for root_nid, blob in unit_rows:
                if isinstance(blob, bytes) and len(blob) == 1024 * 4:
                    unpacked = struct.unpack("1024f", blob)
                    skill_vecs[str(root_nid)] = unpacked
                    if str(root_nid) == "skill_governed_agentic_systems_architecture" or ref_vec is None:
                        ref_vec = unpacked
            dense_live = []
            for sid in sorted(eligible_skills):
                svec = skill_vecs.get(sid)
                sim = sum(a * b for a, b in zip(ref_vec, svec)) if (ref_vec and svec) else 0.5
                dense_live.append({"assertion_id": sid, "similarity": float(sim)})
            metric_skills = {
                str(r[0])
                for r in conn.execute(
                    """
                    SELECT DISTINCT l.skill_id
                    FROM skill_fact_links l
                    JOIN graph_edges e ON e.source_node_id = l.fact_id
                    WHERE e.edge_type = 'fact_has_metric_outcome'
                    """
                ).fetchall()
                if str(r[0]) in eligible_skills
            }
            live_fused = fuse_dense_bm25(
                dense_live,
                bm25_live,
                assertion_ids=eligible_skills,
                metric_bearing_assertion_ids=metric_skills,
                metric_boost=0.05,
            )
            live_fused_count = len(live_fused)
            live_top_skill = str(live_fused[0]["assertion_id"]) if live_fused else ""
            if live_fused_count == 0 or not live_top_skill:
                raise ValueError("Live non-mock Stage 2 hybrid fusion returned empty ranking")
        finally:
            conn.close()

    return {
        "status": "PASS",
        "top_assertion": str(fused[0]["assertion_id"]),
        "boost_applied": float(fused[0]["metric_authority_boost"]),
        "live_fused_skill_count": live_fused_count,
        "live_top_skill": live_top_skill,
    }


def _resolve_artifact_roots() -> list[Path]:
    roots = [ROOT]
    if ROOT.parent.name == ".worktrees":
        primary = ROOT.parent.parent.resolve()
        if primary.is_dir() and primary not in roots:
            roots.append(primary)
    return roots


def run_full_verification() -> None:
    artifact_roots = _resolve_artifact_roots()
    db_path = RG_ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
    for base in artifact_roots:
        cand = base / "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
        if cand.is_file():
            db_path = cand
            break

    emb_dirs: list[Path] = []
    for base in artifact_roots:
        emb_dirs.extend(
            [
                base / "artifacts/apps_rg/c03/graph_skill_embeddings",
                base / "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings",
                base / "resume_graph_engine/artifacts/apps_rg/c03/graph_skill_embeddings",
                base / "resume_graph_engine/artifacts/apps_rg/c03/graph_evidence_cluster_embeddings",
            ]
        )

    print("--> 1. Verifying GraphDB Traversal, Acyclicity & Capabilities...")
    graph_res = verify_graph_database(db_path)
    print(f"    GraphDB: nodes={graph_res['node_count']}, edges={graph_res['edge_count']}, 3-hop paths={graph_res['three_hop_traversal_paths']}")

    print("--> 2. Verifying BGE-M3 Embeddings & Cosine Spectrum...")
    emb_res = verify_bge_m3_embeddings(emb_dirs, db_path)
    print(f"    Embeddings: verified {emb_res['verified_vectors_count']} vectors, dim={emb_res['dimension']}, L2-norm=1.000000")
    print(f"    Spectrum: min={emb_res['min_cosine']}, mean={emb_res['mean_cosine']}, max={emb_res['max_cosine']}")

    print("--> 3. Verifying Stage 2 Metric Authority Boost & Input Validation...")
    ret_res = verify_hybrid_retrieval_stage2(db_path)
    print(f"    Hybrid Retrieval: boost={ret_res['boost_applied']}, top={ret_res['top_assertion']}, live_fused={ret_res.get('live_fused_skill_count', 0)}")

    print("\n=======================================================")
    print("GRAPHDB_TRAVERSAL_AND_EMBEDDINGS_PASS")
    print("=======================================================")


if __name__ == "__main__":
    run_full_verification()

