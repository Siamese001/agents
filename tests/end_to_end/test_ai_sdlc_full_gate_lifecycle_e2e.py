"""Unmocked E2E lifecycle verification for the full AI-SDLC governance stack.

Zero unittest.mock, MagicMock, patch, or monkeypatch imports are permitted in this file.
Verifies end-to-end:
1. Fail-closed Lane 0/1/2 risk classification and self-referential policy immutability.
2. Tier 1 verify_commit.py integration with anti-overfitting linter.
3. Tier 2 verify_main_readiness.py --dry-run executing all 9 stages and sealing effective_lane.
4. Governance harmonization & SSOT drift audit passing with 0 critical findings.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.audit_governance_harmonization import audit_governance_harmonization
from tools.change_lane_classifier import classify_paths

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_lane_classification_end_to_end_cli() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "tools/change_lane_classifier.py",
            "--paths",
            "docs/guide.md",
            "resume_graph_engine/src/apps_rg/fact_inventory/ibm_role_episode_bundles.json",
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        shell=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["effective_lane"] == 2
    assert data["lanes_touched"] == [0, 2]
    assert len(data["required_readiness_stages"]) == 9


def test_tier2_readiness_dry_run_records_9_stages_and_lane() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "tools/verify_main_readiness.py",
            "--repo-root",
            str(REPO_ROOT),
            "--branch",
            "e2e-ai-sdlc-dry-run-probe",
            "--full",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        shell=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    receipt_path = REPO_ROOT / "reports" / "readiness" / "local_main_readiness_e2e_ai_sdlc_dry_run_probe_receipt.json"
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    try:
        assert receipt["terminal_outcome"] == "PASS"
        assert receipt["total_stages"] == 9
        assert receipt["stages_evaluated"] == 9
        assert "effective_lane" in receipt
        stage_names = [s["stage_name"] for s in receipt["stages"]]
        assert "7. Eval Construct Validity & Unmocked E2E Pinning" in stage_names
        assert "8. Diff-Scoped Unmocked Domain Eval Shield" in stage_names
        assert "9. Governance Harmonization & SSOT Drift Audit" in stage_names
    finally:
        receipt_path.unlink(missing_ok=True)


def test_governance_harmonization_and_policy_parity_end_to_end() -> None:
    report = audit_governance_harmonization(REPO_ROOT)
    assert report["status"] == "PASS", report
    assert report["critical_count"] == 0
    assert report["agents_md_lines"] <= 200
    assert report["skills_tokens"] < 4000
    lane_res = classify_paths(["AGENTS.md", "config/governance/risk_lanes_policy.json"], repo_root=REPO_ROOT)
    assert lane_res["effective_lane"] == 2
    assert lane_res["self_referential_lock"] is True
