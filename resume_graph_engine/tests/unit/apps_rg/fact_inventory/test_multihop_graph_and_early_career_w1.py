from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.fact_inventory.graph_sqlite_path_index import (
    GRAPH_INDEX_CAPABILITY_VERSION,
    query_reverse_metric_paths,
    validate_graphdb_capability_integrity,
)

REPO = Path(__file__).resolve().parents[4]


def test_wave1_multihop_graph_bridges_and_early_career_reachability(tmp_path: Path) -> None:
    db_path = tmp_path / "wave1_graph.sqlite"
    summary = materialize_augmented_skills_graph_sqlite(repo_root=REPO, db_path=db_path)
    assert summary["graph_path_count"] > 0

    conn = sqlite3.connect(db_path)
    try:
        integrity = validate_graphdb_capability_integrity(conn)
        assert integrity["status"] == "GRAPHDB_CAPABILITY_INTEGRITY_PASS", integrity

        # 1. Multi-hop paths (depth 2..4) and multi-hop neighborhoods (distance 2..3) exist.
        depths = {
            int(r[0]): int(r[1])
            for r in conn.execute("SELECT path_depth, COUNT(*) FROM graph_paths GROUP BY path_depth").fetchall()
        }
        assert depths.get(1, 0) > 0
        assert sum(cnt for d, cnt in depths.items() if d >= 2) > 500, depths

        dists = {
            int(r[0]): int(r[1])
            for r in conn.execute(
                "SELECT distance, COUNT(*) FROM graph_neighborhoods GROUP BY distance"
            ).fetchall()
        }
        assert dists.get(1, 0) > 0
        assert sum(cnt for d, cnt in dists.items() if d >= 2) > 500, dists

        # 2. Cross-track bridge paths exist in graph_paths.
        bridge_paths = conn.execute(
            "SELECT COUNT(*) FROM graph_paths WHERE edge_types_json LIKE '%pillar_phase_bridge%' AND path_depth >= 2"
        ).fetchone()[0]
        assert bridge_paths > 0

        # 3. Canonical skill_reinforces_skill edges connect canonical skill_* nodes across tracks (not orphan c03 island).
        canonical_reinforces = conn.execute(
            """
            SELECT COUNT(*) FROM graph_edges
            WHERE edge_type = 'skill_reinforces_skill'
              AND source_node_id LIKE 'skill_%'
              AND target_node_id LIKE 'skill_%'
            """
        ).fetchone()[0]
        assert canonical_reinforces >= 10

        # 4. Early-career bundles and credential elevation metric outcomes are materialized.
        ec_bundles = conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE node_type='engagement' AND node_id LIKE 'reb_early_career_%'"
        ).fetchone()[0]
        assert ec_bundles >= 4

        fsa_bundle_links = conn.execute(
            """
            SELECT COUNT(*) FROM graph_edges
            WHERE edge_type = 'engagement_exercises_skill'
              AND target_node_id = 'skill_actuarial_fsa_fellowship'
            """
        ).fetchone()[0]
        assert fsa_bundle_links >= 1

        # 5. Track 1 skills are no longer contaminated by TRACK_ENGINEERING_PLATFORM / TRACK_BANKING_PLATFORM_AI
        #    and archive-backed actuarial/derivatives skills are ACTIVE_CONFIRMED + external_eligible=1.
        for sid in (
            "skill_actuarial_fsa_fellowship",
            "skill_capital_reserving",
            "skill_capital_pricing_actuarial",
            "skill_derivatives_structured_derivatives",
            "skill_insurance_liabilities_embedded_options",
            "skill_insurance_liabilities_insurance_liabilities",
            "skill_greeks_delta",
        ):
            row = conn.execute(
                """
                SELECT career_track_id, activation_status, external_eligible
                FROM c03_skill_selection_features
                WHERE skill_id = ?
                """,
                (sid,),
            ).fetchone()
            assert row is not None, sid
            assert row[0] == "track_actuarial_risk_derivatives", (sid, row)
            assert str(row[1]).startswith("ACTIVE"), (sid, row)
            assert int(row[2]) == 1, (sid, row)

        # 6. Every role_family_projection profile has >0 c03_role_family_skill_weights rows.
        empty_profiles = conn.execute(
            """
            SELECT p.projection_role_family_key
            FROM role_family_projection p
            LEFT JOIN c03_role_family_skill_weights w
              ON w.role_family_key = p.projection_role_family_key
            GROUP BY p.projection_role_family_key
            HAVING COUNT(w.skill_id) = 0
            """
        ).fetchall()
        assert empty_profiles == [], empty_profiles

        # 7. Reverse metric paths support multi-hop depth >= 2.
        rev_paths = query_reverse_metric_paths(
            conn,
            metric_id="metric_early_career_fsa_charter_actuarial_authority",
            max_depth=4,
            limit=50,
        )
        assert any(p["path_depth"] >= 2 for p in rev_paths), rev_paths

        # 8. Sibling links are bounded (no 27k explosion).
        sib_count = int(conn.execute("SELECT COUNT(*) FROM graph_sibling_links").fetchone()[0])
        assert 0 < sib_count < 15000, sib_count

        # 9. No dangling edges and capability version reflects multihop_bounded.
        assert "multihop" in GRAPH_INDEX_CAPABILITY_VERSION
        dangling = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM graph_edges e
                WHERE NOT EXISTS (SELECT 1 FROM graph_nodes n WHERE n.node_id = e.source_node_id)
                   OR NOT EXISTS (SELECT 1 FROM graph_nodes n WHERE n.node_id = e.target_node_id)
                """
            ).fetchone()[0]
        )
        assert dangling == 0
    finally:
        conn.close()
