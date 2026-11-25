"""Unmocked stdio JSON-RPC integration tests for Agents Graph Hygiene Studio MCP App Server v4."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = Path("/Users/amitayer/.gemini/config/plugins/agents-graph-hygiene")
SERVER_SCRIPT = PLUGIN_ROOT / "mcp" / "graph_hygiene_server.py"
BUILT_HTML = PLUGIN_ROOT / "mcp" / "ui" / "studio_app.html"


def _send_mcp_batch(requests: list[dict], *, data_dir: Path) -> list[dict]:
    stdin_payload = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.run(
        [sys.executable, "-u", str(SERVER_SCRIPT), "--data-dir", str(data_dir)],
        input=stdin_payload,
        capture_output=True,
        text=True,
        shell=False,
        timeout=60,
        check=True,
    )
    return [json.loads(ln) for ln in proc.stdout.splitlines() if ln.strip()]


def test_studio_v4_tools_bundle_state_and_fail_closed_promotion_guards(tmp_path: Path) -> None:
    assert BUILT_HTML.is_file(), "Studio v4 HTML bundle missing"
    html_text = BUILT_HTML.read_text(encoding="utf-8")
    assert "Graph Hygiene v4" in html_text
    assert "app_judge_item" in html_text
    assert "app_create_worktree" in html_text
    assert "app_promote_to_main" in html_text

    # Isolated synthetic worktree directory with zero judge receipts so this test stays
    # deterministic even after the real feature worktree seals its own PR promotion receipt.
    fake_unverified_wt = tmp_path / ".worktrees" / "fake_unverified_wt"
    fake_unverified_wt.mkdir(parents=True, exist_ok=True)
    fake_main_root = tmp_path / "fake_main_root"
    fake_main_root.mkdir(parents=True, exist_ok=True)

    resps = _send_mcp_batch(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"uri": "ui://agents-graph-hygiene/app.html"}},
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "app_get_state", "arguments": {"repo_root": str(REPO_ROOT), "force_rescan": False}},
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "app_promote_to_main",
                    "arguments": {"repo_root": str(fake_unverified_wt), "confirm_merge_to_main": False},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "app_promote_to_main",
                    "arguments": {"repo_root": str(fake_unverified_wt), "confirm_merge_to_main": True},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "app_promote_to_main",
                    "arguments": {"repo_root": str(fake_main_root), "confirm_merge_to_main": True},
                },
            },
        ],
        data_dir=tmp_path / "studio_data",
    )
    by_id = {r["id"]: r for r in resps}

    # 1. Version 4.0.0 initialize
    assert by_id[1]["result"]["serverInfo"]["version"] == "4.0.0"

    # 2. All 12 MCP tools exposed
    tool_names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert {
        "open_graph_hygiene_studio",
        "show_graph_hygiene_studio",
        "app_get_state",
        "app_save_item_decision",
        "app_save_cluster_decision",
        "app_rescan",
        "app_dry_run",
        "app_apply_approved",
        "app_judge_item",
        "app_judge_cluster",
        "app_create_worktree",
        "app_promote_to_main",
    }.issubset(tool_names)

    # 3. Resource serves built v4 HTML cleanly
    res_html = by_id[3]["result"]["contents"][0]["text"]
    assert "Graph Hygiene v4" in res_html

    # 4. State carries promotion_status and zero fake council_debate
    state = by_id[4]["result"]["structuredContent"]
    assert state["status"] == "READY"
    assert "promotion_status" in state
    assert state["audit"]["studio_enrich_version"] == "v4.0"
    for c in state["audit"]["hitl_clusters"]:
        assert "council_debate" not in c
        assert c["judge_metadata"]["panel_mode"] == "judge_v3_two_stage_cached"

    # 5. app_promote_to_main fails closed without explicit confirmation
    assert by_id[5]["result"].get("isError") is True
    assert "Explicit operator confirmation required" in by_id[5]["result"]["content"][0]["text"]

    # 6. app_promote_to_main fails closed without valid 2-family receipt (even when confirm=True)
    assert by_id[6]["result"].get("isError") is True
    assert "Promotion blocked fail-closed" in by_id[6]["result"]["content"][0]["text"]

    # 7. app_promote_to_main fails closed when targeting primary main (non-worktree)
    assert by_id[7]["result"].get("isError") is True
    assert "isolated feature worktree" in by_id[7]["result"]["content"][0]["text"]
