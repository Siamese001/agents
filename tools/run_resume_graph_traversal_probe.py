#!/usr/bin/env python3
"""Read-only multi-hop resume and competency graph traversal probe for Agents sidecar audits."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if sys.prefix == sys.base_prefix:
    venv_py = REPO_ROOT / ".venv" / "bin" / "python"
    if venv_py.is_file():
        os.execv(str(venv_py), [str(venv_py)] + sys.argv)

RG_SRC = REPO_ROOT / "resume_graph_engine" / "src"
for p in (str(RG_SRC), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from apps_research.integrations.c0_graph_adapter import build_research_graph_traverse_input  # noqa: E402
from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (  # noqa: E402
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.runtime.graph_traversal import (  # noqa: E402
    JOURNEY_DOMAIN_SKILL_EVIDENCE,
    JOURNEY_SKILL_FACT_METRIC_EMPLOYMENT_EPOCH,
    traverse,
    traverse_journey,
)


def run_resume_graph_traversal_probe(max_paths: int = 200) -> dict[str, Any]:
    """Materializes a hermetic sandbox clone of the skills/resume graph and executes multi-hop walks."""
    with tempfile.TemporaryDirectory(prefix="agents_rg_probe_") as td:
        db_path = Path(td) / "sandbox_skills_graph.sqlite"
        meta = materialize_augmented_skills_graph_sqlite(db_path=db_path)

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
            seed_rows = conn.execute(
                "SELECT DISTINCT source_node_id FROM graph_edges WHERE traversable = 1 LIMIT 25"
            ).fetchall()
            seeds = [str(r[0]) for r in seed_rows]
            two_hop_paths = traverse(conn, seeds, direction="forward", max_depth=2, max_paths=max_paths)

            dom_rows = conn.execute(
                "SELECT DISTINCT source_node_id FROM graph_edges "
                "WHERE edge_type = 'capability_domain_contains_skill' LIMIT 25"
            ).fetchall()
            dom_seeds = [str(r[0]) for r in dom_rows]
            domain_paths = (
                traverse_journey(conn, JOURNEY_DOMAIN_SKILL_EVIDENCE, dom_seeds, max_paths=max_paths)
                if dom_seeds
                else []
            )

            skill_rows = conn.execute(
                "SELECT DISTINCT source_node_id FROM graph_edges "
                "WHERE edge_type = 'skill_supported_by_fact' LIMIT 25"
            ).fetchall()
            skill_seeds = [str(r[0]) for r in skill_rows]
            epoch_paths = (
                traverse_journey(
                    conn, JOURNEY_SKILL_FACT_METRIC_EMPLOYMENT_EPOCH, skill_seeds, max_paths=max_paths
                )
                if skill_seeds
                else []
            )
        finally:
            conn.close()

    research_contract = build_research_graph_traverse_input(
        {"graph_traverse": {"max_hops": 2}},
        hydrated_candidates=[{"node_id": seeds[0]}] if seeds else [],
    )

    passed = (
        integrity == "ok"
        and len(two_hop_paths) > 0
        and len(domain_paths) > 0
        and research_contract.get("max_hops") == 2
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "direct_graph_traversal": True,
        "integrity_check": integrity,
        "node_count_sqlite": meta.get("node_count_sqlite", 0),
        "edge_count_sqlite": meta.get("edge_count_sqlite", 0),
        "two_hop_path_count": len(two_hop_paths),
        "domain_skill_evidence_path_count": len(domain_paths),
        "skill_fact_metric_epoch_path_count": len(epoch_paths),
        "research_max_hops": research_contract.get("max_hops"),
        "sample_two_hop_nodes": two_hop_paths[0].node_path if two_hop_paths else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute hermetic multi-hop resume graph traversal probe.")
    parser.add_argument("--max-paths", type=int, default=200, help="Maximum paths per journey")
    args = parser.parse_args()
    payload = run_resume_graph_traversal_probe(max_paths=args.max_paths)
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
