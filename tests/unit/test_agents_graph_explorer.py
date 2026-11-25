"""Unmocked integration tests for the Agents Knowledge Graph Explorer dataset, HTML export, and HTTP portal."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

from scripts.serve_agents_graph_portal import create_agents_graph_portal_server
from tools.export_interactive_knowledge_graph import export_interactive_knowledge_graph
from tools.interactive_graph_export_core.dataset_builder import (
    IDENTITY_ROOT_ID,
    build_agents_explorer_dataset,
    filter_bundle_lens,
    render_explorer_html,
    resolve_default_graph_db_path,
    search_bundle_nodes,
)


def test_build_agents_explorer_dataset_from_live_sqlite() -> None:
    db_path = resolve_default_graph_db_path()
    assert db_path.is_file(), f"Expected live skills graph DB at {db_path}"

    data = build_agents_explorer_dataset(db_path)
    assert data["repo_name"] == "agents"
    assert data["total_nodes"] >= 800
    assert data["total_edges"] >= 4000
    assert data["total_evidence_links"] > 0
    assert len(data["nodes"]) == data["total_nodes"]
    assert len(data["edges"]) == data["total_edges"]

    node_ids = {n["id"] for n in data["nodes"]}
    assert IDENTITY_ROOT_ID in node_ids
    for edge in data["edges"]:
        assert edge["from"] in node_ids
        assert edge["to"] in node_ids
        assert edge["from"] != edge["to"]

    assert len(data["skills"]) >= 200
    assert len(data["engagements"]) >= 40
    assert len(data["evidence"]) >= 150
    assert len(data["role_projections"]) >= 15
    assert len(data["employments"]) == 6


def test_filter_lens_and_search_helpers() -> None:
    data = build_agents_explorer_dataset()
    backbone = filter_bundle_lens(data, "backbone")
    assert 15 <= backbone["node_count"] <= 35
    assert backbone["edge_count"] > 0

    track_slice = filter_bundle_lens(data, "track_genai_agentic")
    assert track_slice["node_count"] > 10
    assert track_slice["edge_count"] > 0

    hits = search_bundle_nodes(data, "agentic")
    assert hits["count"] > 0
    assert all("id" in r and "label" in r for r in hits["results"])


def test_export_standalone_html(tmp_path: Path) -> None:
    receipt = export_interactive_knowledge_graph(output_dir=tmp_path)
    out_file = Path(receipt["output_html"])
    assert out_file.is_file()
    html_text = out_file.read_text(encoding="utf-8")
    assert "Agents Repo - Career &amp; Skills Graph" in html_text
    assert 'id="graphCanvas"' in html_text
    assert 'id="archMatrixSvg"' in html_text
    assert IDENTITY_ROOT_ID in html_text
    assert "__SNAPSHOT_DATE__" not in html_text

    rendered_arch = render_explorer_html(build_agents_explorer_dataset(), default_mode="opmodel")
    assert '"opmodel"' in rendered_arch


def test_live_http_portal_endpoints() -> None:
    server = create_agents_graph_portal_server(host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{base}/healthz", timeout=10) as resp:
            assert resp.status == 200
            health = json.loads(resp.read().decode("utf-8"))
            assert health["status"] == "ok"
            assert health["total_nodes"] >= 800

        with urllib.request.urlopen(f"{base}/graph", timeout=10) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "/api/v1/bootstrap" in body
            assert 'id="graphCanvas"' in body

        with urllib.request.urlopen(f"{base}/api/v1/bootstrap", timeout=10) as resp:
            assert resp.status == 200
            boot = json.loads(resp.read().decode("utf-8"))
            assert boot["total_nodes"] >= 800
            assert len(boot["skills"]) >= 200

        with urllib.request.urlopen(f"{base}/api/v1/lens/backbone", timeout=10) as resp:
            assert resp.status == 200
            lens = json.loads(resp.read().decode("utf-8"))
            assert 15 <= lens["node_count"] <= 35

        with urllib.request.urlopen(f"{base}/api/v1/node/{IDENTITY_ROOT_ID}", timeout=10) as resp:
            assert resp.status == 200
            node_resp = json.loads(resp.read().decode("utf-8"))
            assert node_resp["node"]["id"] == IDENTITY_ROOT_ID
            assert len(node_resp["edges"]) > 0

        with urllib.request.urlopen(f"{base}/api/v1/search?q=slalom", timeout=10) as resp:
            assert resp.status == 200
            srch = json.loads(resp.read().decode("utf-8"))
            assert srch["count"] > 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
