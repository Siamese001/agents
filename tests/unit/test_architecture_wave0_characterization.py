"""tests/unit/test_architecture_wave0_characterization.py

Wave 0 Characterization Test Suite:
Locks baseline behavior, command matrix, route dispatch targets, prompt slot contracts,
and stage inventory across the Sovereign Agentic Platform before any refactoring edits.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RG_SRC = REPO_ROOT / "resume_graph_engine" / "src"
OE_SRC = REPO_ROOT / "outreach_engine" / "src"

for p in (REPO_ROOT, RG_SRC, OE_SRC):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

import agents.cli as agents_cli
import apps_rg.__main__ as apps_rg_main
import apps_rg.prompt_assembly.compiler as rg_compiler
import apps_lic.__main__ as apps_lic_main
from tools.characterize_runtime_routes import generate_characterization_report


def test_cli_parser_construction():
    """Verify that the unified CLI parser constructs with resume, outreach, and e2e."""
    parser = agents_cli._build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    assert parser.prog == "python -m agents"

    # Verify engines in subparsers
    subparsers_actions = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers_actions) == 1
    choices = subparsers_actions[0].choices
    assert "resume" in choices
    assert "outreach" in choices
    assert "e2e" in choices


def test_e2e_lifecycle_stage_inventory():
    """Characterize and lock the exact stages executed in run_e2e.
    
    Verifies that run_e2e explicitly accounts for company_research (Stage 1),
    resume_tailoring via apps_rg (Stage 2), and outreach via apps_lic (Stage 3).
    """
    source = inspect.getsource(agents_cli.run_e2e)
    
    # Stage 1: Governed research status
    assert "company_research" in source
    assert "research_status" in source
    
    # Stage 2: Resume tailoring via apps_rg
    assert "apps_rg.__main__" in source or "resume_main" in source
    
    # Stage 3: Outreach generation via apps_lic
    assert "apps_lic.__main__" in source or "outreach_main" in source


def test_prompt_compiler_canonical_slots():
    """Verify and freeze prompt slot authority and ordering."""
    # S0 must be sovereign and first
    assert rg_compiler.CANONICAL_SLOT_ORDER[0] == "S0"
    assert "D0" in rg_compiler.CANONICAL_SLOT_ORDER
    assert "I0" in rg_compiler.CANONICAL_SLOT_ORDER
    assert "R0" in rg_compiler.CANONICAL_SLOT_ORDER
    assert "M0" in rg_compiler.CANONICAL_SLOT_ORDER
    
    # Verify all 10 canonical slots are defined
    assert len(rg_compiler.CANONICAL_SLOT_ORDER) == 10
    
    # Verify slot authority mapping
    for slot in rg_compiler.CANONICAL_SLOT_ORDER:
        assert slot in rg_compiler.SLOT_TO_AUTHORITY


def test_apps_rg_dual_route_presence():
    """Verify that apps_rg currently defines both canonical and modular dispatch points."""
    rg_main_source = inspect.getsource(apps_rg_main)
    # Check canonical dispatch in CLI entrypoint
    assert "run_canonical_apps_rg_from_cli_primitives" in rg_main_source

    # Check modular R4 path in recipe steps
    from apps_rg.l2_recipe.steps import GenerateResumeStep
    steps_source = inspect.getsource(GenerateResumeStep)
    assert "run_modular_resume_generation" in steps_source


def test_characterization_report_generation():
    """Ensure the characterization report can be generated deterministically."""
    report = generate_characterization_report()
    assert report["report_type"] == "wave0_runtime_characterization"
    assert "entrypoints" in report
    assert "root_cli" in report["entrypoints"]
    assert "apps_rg_cli" in report["entrypoints"]
    assert "apps_lic_cli" in report["entrypoints"]
    assert report["e2e_lifecycle"]["advertised_research_stage_active_in_code"] is True
    assert len(report["e2e_lifecycle"]["active_stages"]) == 3
