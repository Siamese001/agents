"""Non-mock CLI smoke and edge-case tests for outreach_engine / apps_lic."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        shell=False,
        timeout=60,
    )


def test_cli_run_rejects_empty_and_whitespace_brief(tmp_path: Path) -> None:
    empty_brief = tmp_path / "empty.json"
    empty_brief.write_text("   \n  ", encoding="utf-8")

    res = _run_cli([
        "outreach_engine",
        "run",
        "--brief",
        str(empty_brief),
        "--offline-smoke",
        "--json",
    ])
    assert res.returncode == 1
    payload = json.loads(res.stdout)
    assert payload["status"] == "FAILED"
    assert "missing or empty" in payload["error"]


def test_cli_run_preserves_sender_profile_title_when_role_passed_with_brief(tmp_path: Path) -> None:
    brief_file = tmp_path / "mission_with_sender_title.json"
    brief_data = {
        "sender_profile": {
            "name": "Amit Ayer",
            "title": "AI/ML Engineering Leader",
        },
        "recipient_profile": {
            "name": "Charles Morris",
            "title": "EVP, Enterprise Technology",
            "company": "Truist",
            "recipient_class": "executive_peer",
            "relationship_distance": "cold",
        },
        "job_description": {
            "title": "Chief Information Officer",
            "company": "Truist",
            "strategic_priorities": [
                "enterprise AI governance",
                "cloud modern banking core",
            ],
        },
    }
    brief_file.write_text(json.dumps(brief_data, indent=2), encoding="utf-8")
    out_dir = tmp_path / "run_sender_title"

    res = _run_cli([
        "outreach_engine",
        "run",
        "--brief",
        str(brief_file),
        "--role",
        "VP of Core Banking",
        "--offline-smoke",
        "--artifact-dir",
        str(out_dir),
        "--json",
    ])
    assert res.returncode == 0, f"CLI run failed: {res.stderr}\n{res.stdout}"
    manifest = json.loads((out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate"]["target_title"] == "AI/ML Engineering Leader"
    assert manifest["opportunity"]["role_title"] == "VP of Core Banking"


def test_cli_validate_honors_company_and_priority_flags() -> None:
    # 1. Valid grounded draft with matching --company and --priority and grounded $4.2B metric
    body = (
        "Charles, given Truist's focus on enterprise AI governance, I wanted to connect. "
        "As an AI/ML Engineering Leader, I have scaled distributed enterprise platforms processing "
        "$4.2B annual volume with 99.995% reliability across regulated financial ecosystems. "
        "Would you be open to a brief 15-minute exchange next week?"
    )
    res_pass = _run_cli([
        "outreach_engine",
        "validate",
        "--company",
        "Truist",
        "--role",
        "EVP of Enterprise AI",
        "--priority",
        "enterprise AI governance",
        "--subject",
        "Truist enterprise AI governance",
        "--body",
        body,
        "--json",
    ])
    assert res_pass.returncode == 0, f"Expected pass, got: {res_pass.stdout}\n{res_pass.stderr}"
    data_pass = json.loads(res_pass.stdout)
    assert data_pass["passed"] is True
    assert data_pass["company"] == "Truist"
    assert "enterprise AI governance" in data_pass["strategic_priorities"]
    assert "privacy_score" in data_pass["scores"]
    assert "unsupported_personalization_score" in data_pass["scores"]

    # 2. Unverified personalization claim blocked when --unverified is set
    res_block = _run_cli([
        "outreach_engine",
        "validate",
        "--company",
        "Truist",
        "--unverified",
        "--subject",
        "Truist AI strategy",
        "--body",
        "Charles, given your focus on quantum ledger settlements, would you be open to connecting?",
        "--json",
    ])
    assert res_block.returncode == 1
    data_block = json.loads(res_block.stdout)
    assert data_block["passed"] is False
    assert data_block["scores"]["unsupported_personalization_score"] == 0.0
