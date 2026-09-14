"""tests/unit/test_architecture_wave1_correctness.py

Wave 1 P0 Correctness & Safety Verification Test Suite:
Validates that:
1. Upstream Research lifecycle status is explicit (ENABLED, DISABLED, OPTIONAL) in agents/cli.py
2. E2E lifecycle summary manifest records all stages honestly without silent omission
3. Explicitly requested research fails closed if the decoupled internal engine is unavailable
4. CLI parser options expose governance controls
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RG_SRC = REPO_ROOT / "resume_graph_engine" / "src"
OE_SRC = REPO_ROOT / "outreach_engine" / "src"

import agents.cli as agents_cli


def test_cli_parser_exposes_research_governance_flags():
    """Verify that agents e2e parser exposes --research-status and --with-research."""
    parser = agents_cli._build_parser()
    subparsers_actions = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers_actions) == 1
    e2e_parser = subparsers_actions[0].choices["e2e"]
    
    option_dests = [a.dest for a in e2e_parser._actions]
    assert "research_status" in option_dests
    assert "with_research" in option_dests


def test_run_e2e_research_default_disabled(tmp_path: Path):
    """Verify that default e2e run explicitly records company_research as SKIPPED/DISABLED."""
    parser = agents_cli._build_parser()
    args = parser.parse_args(["e2e", "--skip-resume", "--demo", "--artifact-dir", str(tmp_path)])
    
    # Mock outreach_main to succeed without external network
    with patch("apps_lic.__main__.main", return_value=0):
        code = agents_cli.run_e2e(args)
        assert code == 0

    summary_file = tmp_path / "e2e_lifecycle_summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text(encoding="utf-8"))

    assert "stages" in summary
    stages = summary["stages"]
    assert "company_research" in stages
    assert stages["company_research"]["configured_status"] == "DISABLED"
    assert stages["company_research"]["status"] == "SKIPPED"
    assert "reason" in stages["company_research"]
    assert "decoupled" in stages["company_research"]["reason"]

    assert "resume_tailoring" in stages
    assert stages["resume_tailoring"]["status"] == "SKIPPED"

    assert "executive_outreach" in stages
    assert stages["executive_outreach"]["status"] == "PASSED"


def test_run_e2e_with_research_fails_closed(tmp_path: Path):
    """Verify that if research is enabled, but internal apps_research fails/rejects, run_e2e fails closed."""
    parser = agents_cli._build_parser()
    args = parser.parse_args(["e2e", "--with-research", "--skip-resume", "--artifact-dir", str(tmp_path)])

    code = agents_cli.run_e2e(args)
    # apps_research.__main__ returns exit code 1 because it is an internal library
    assert code != 0
