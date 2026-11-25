#!/usr/bin/env python3
"""Export a self-contained interactive knowledge graph explorer HTML from augmented_skills_graph.sqlite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.interactive_graph_export_core.dataset_builder import (
    build_agents_explorer_dataset,
    render_explorer_html,
    render_portal_shell_html,
    resolve_default_graph_db_path,
    resolve_primary_repo_root,
)
from tools.verify_graph_explorer_gate import run_agents_graph_quality_gate


def export_interactive_knowledge_graph(
    graph_path: Path | str | None = None,
    *,
    output_dir: Path | str | None = None,
    default_mode: str = "graph",
) -> dict[str, Any]:
    """Build live dataset from SQLite, verify quality & firewall gate, and write interactive_knowledge_graph.html."""
    db_path = Path(graph_path).resolve() if graph_path else resolve_default_graph_db_path(ROOT)
    data = build_agents_explorer_dataset(db_path)
    html_text = render_explorer_html(data, default_mode=default_mode)
    portal_html = render_portal_shell_html(data, default_mode=default_mode)
    gate_res = run_agents_graph_quality_gate(
        html_text,
        portal_html_text=portal_html,
        run_vm=(default_mode == "graph"),
    )
    if not gate_res["passed"]:
        joined = "; ".join(gate_res["violations"])
        raise RuntimeError(f"Graph Explorer quality/firewall gate failed: {joined}")
    out_dir = (
        Path(output_dir).resolve()
        if output_dir is not None
        else (resolve_primary_repo_root(ROOT) / "artifacts" / "explorer")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "interactive_knowledge_graph.html"
    tmp_file = out_dir / "interactive_knowledge_graph.html.tmp"
    tmp_file.write_text(html_text, encoding="utf-8")
    tmp_file.replace(out_file)
    return {
        "graph_path": str(db_path),
        "output_html": str(out_file),
        "file_url": f"file://{out_file}",
        "total_nodes": data["total_nodes"],
        "total_edges": data["total_edges"],
        "total_evidence_links": data["total_evidence_links"],
        "generation_id": data["generation_id"],
        "snapshot_date": data["snapshot_date"],
        "quality_gate_passed": True,
        "quality_gate_profile": gate_res["profile"],
        "vm_hop_counts": gate_res["vm_metrics"].get("counts", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export interactive knowledge graph HTML from augmented_skills_graph.sqlite"
    )
    parser.add_argument("--graph-path", default=None, help="Explicit path to augmented_skills_graph.sqlite")
    parser.add_argument("--output-dir", default=None, help="Output directory for interactive_knowledge_graph.html")
    parser.add_argument(
        "--default-mode",
        default="graph",
        choices=("graph", "opmodel", "portfolio", "signals", "delivery", "agendas"),
        help="Default initial workspace tab",
    )
    args = parser.parse_args(argv)
    receipt = export_interactive_knowledge_graph(
        args.graph_path,
        output_dir=args.output_dir,
        default_mode=args.default_mode,
    )
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
