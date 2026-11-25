"""Behavioral tests for Agent 7 (Live Keyless Canary, MCP Stdio Server, Graph Portal & Release Gate)."""
from __future__ import annotations

from pathlib import Path

from tools.live_canary_release_auditor import main as live_canary_main
from tools.live_canary_release_auditor import run_live_canary_release_audit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_live_canary_release_auditor_preflight_readiness_passes() -> None:
    report = run_live_canary_release_audit(REPO_ROOT, live_canary=False, run_release_gate=False)
    assert report["status"] == "PASS", report["gaps"]
    assert report["is_clean"] is True
    assert report["passing_pillars"] == 4
    assert report["pillars"]["pillar_1_vector_db_mcp_stdio"]["responses_verified"] == 3
    assert report["pillars"]["pillar_2_graph_explorer_and_portal"]["explorer_gate_passed"] is True
    assert live_canary_main(["--repo-root", str(REPO_ROOT), "--preflight-readiness", "--json"]) == 0
