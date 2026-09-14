#!/usr/bin/env python3
"""tools/characterize_runtime_routes.py

Wave 0 Characterization Tool:
Maps the executable CLI commands, dispatch targets, stage ordering, prompt slot order,
and output schemas across the Sovereign Agentic Platform. Emits a deterministic JSON artifact.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
RG_SRC = REPO_ROOT / "resume_graph_engine" / "src"
OE_SRC = REPO_ROOT / "outreach_engine" / "src"

for p in (REPO_ROOT, RG_SRC, OE_SRC):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

import agents.cli as agents_cli
import apps_rg.__main__ as apps_rg_main
import apps_rg.prompt_assembly.compiler as rg_compiler
import apps_lic.__main__ as apps_lic_main


def extract_parser_info(parser: argparse.ArgumentParser) -> Dict[str, Any]:
    """Extract actions, options, and defaults from an ArgumentParser."""
    options = []
    for action in parser._actions:
        options.append({
            "option_strings": action.option_strings,
            "dest": action.dest,
            "default": str(action.default) if action.default is not None else None,
            "required": action.required,
            "help": action.help,
        })
    return {
        "prog": parser.prog,
        "description": parser.description,
        "options": options,
    }


def characterize_e2e_stages() -> Dict[str, Any]:
    """Characterize the exact stages executed in agents.cli.run_e2e."""
    source = inspect.getsource(agents_cli.run_e2e)
    stages = []
    if "apps_research" in source or "company_research" in source:
        stages.append({
            "stage_index": 1,
            "name": "company_research",
            "entrypoint": "apps_research.__main__.main",
            "package": "apps_research",
            "governance_status": "governed_explicit_status",
        })
    if "apps_rg.__main__" in source or "resume_main" in source:
        stages.append({
            "stage_index": 2,
            "name": "resume_tailoring",
            "entrypoint": "apps_rg.__main__.main",
            "package": "resume_graph_engine",
            "cli_equivalent": "python -m agents resume run",
        })
    if "apps_lic.__main__" in source or "outreach_main" in source:
        stages.append({
            "stage_index": 3,
            "name": "executive_outreach",
            "entrypoint": "apps_lic.__main__.main",
            "package": "outreach_engine",
            "cli_equivalent": "python -m agents outreach run",
        })
    
    return {
        "active_stages": stages,
        "advertised_research_stage_active_in_code": "apps_research" in source,
    }


def characterize_prompt_assembly() -> Dict[str, Any]:
    """Characterize the prompt compiler slot order and authority classes."""
    return {
        "canonical_slot_order": rg_compiler.CANONICAL_SLOT_ORDER,
        "slot_to_authority": {
            slot: auth.value for slot, auth in rg_compiler.SLOT_TO_AUTHORITY.items()
        },
        "precedence": [a.value for a in rg_compiler.AUTHORITY_PRECEDENCE],
    }


def characterize_rg_routes() -> Dict[str, Any]:
    """Characterize apps_rg execution routes (canonical vs modular)."""
    rg_main_source = inspect.getsource(apps_rg_main)
    has_canonical = "run_canonical_apps_rg_from_cli_primitives" in rg_main_source
    has_modular = "modular" in rg_main_source
    return {
        "supports_canonical_dispatch": has_canonical,
        "supports_modular_r4_dispatch": has_modular,
        "canonical_dispatch_symbol": "apps_rg.runtime.orchestration.canonical_dispatch.run_canonical_apps_rg_from_cli_primitives",
        "modular_recipe_module": "apps_rg.l2_recipe.modular_resume_generation",
    }


def generate_characterization_report() -> Dict[str, Any]:
    """Generate complete Wave 0 characterization report."""
    root_parser = agents_cli._build_parser()
    rg_parser = apps_rg_main._build_parser()
    lic_parser = apps_lic_main._build_parser()

    report = {
        "report_type": "wave0_runtime_characterization",
        "version": "1.0.0",
        "entrypoints": {
            "root_cli": extract_parser_info(root_parser),
            "apps_rg_cli": extract_parser_info(rg_parser),
            "apps_lic_cli": extract_parser_info(lic_parser),
        },
        "e2e_lifecycle": characterize_e2e_stages(),
        "rg_dispatch_routes": characterize_rg_routes(),
        "prompt_assembly": characterize_prompt_assembly(),
    }
    return report


def main() -> int:
    report = generate_characterization_report()
    out_file = REPO_ROOT / "artifacts" / "wave0_runtime_characterization_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wave 0 characterization report generated at {out_file} ({out_file.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
