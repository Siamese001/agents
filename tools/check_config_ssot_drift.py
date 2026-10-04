#!/usr/bin/env python3
"""Config SSOT Drift Detector.

Compares repository root `config/` against engine `resume_graph_engine/config/`
and flags divergence, orphaned configurations, and unallowlisted drifts.

Supports:
  --report: Print full drift analysis (default, exit 0)
  --strict: Fail if unallowlisted drift is detected (exit 1)
  --json: Output JSON payload
"""

from __future__ import annotations

import argparse
import filecmp
import json
import sys
from pathlib import Path
from typing import Any

# Files that are intentionally governance-only or have documented temporary deviations
KNOWN_DRIFT_ALLOWLIST = {
    # Governance files unique to root or engine
    "governance",
    "adg_gate_fanin_map.yaml",
    "wiring_gate_waivers.yaml",
    "wiring_dynamic_dispatch_anchors.yaml",
    "notion_databases.yaml",
    "lifecycle_pairs.yaml",
    "ledger_freshness_slo.yaml",
    "expected_wiring.yaml",
    "excluded_paths.yaml",
    "dashboards",
    "contracts",
    "crosswalk",
    "certification",
    "canonical_pipelines.yaml",
    "architectural_exceptions.yaml",
    "apps_spine_delegation_allowlist.yaml",
    "provider_profiles.yaml",
    "model_catalog.json",
    "runtime_budget_policy.yaml",
    "routing_thresholds.yaml",
    "routing_calibration.yaml",
    "token_budget.yaml",
    "exception_contracts.yaml",
    "sc_ap_config.json",
    "north_star_state.json",
    "test_harness_coverage_allowlist.yaml",
}


def analyze_drift(repo_root: Path) -> dict[str, Any]:
    root_cfg = repo_root / "config"
    engine_cfg = repo_root / "resume_graph_engine" / "config"

    result: dict[str, Any] = {
        "root_config_exists": root_cfg.is_dir(),
        "engine_config_exists": engine_cfg.is_dir(),
        "identical": [],
        "differing": [],
        "only_in_root": [],
        "only_in_engine": [],
        "unallowlisted_differing": [],
    }

    if not root_cfg.is_dir() or not engine_cfg.is_dir():
        return result

    root_files = {p.relative_to(root_cfg) for p in root_cfg.rglob("*") if p.is_file()}
    engine_files = {p.relative_to(engine_cfg) for p in engine_cfg.rglob("*") if p.is_file()}

    common_files = root_files & engine_files
    result["only_in_root"] = sorted(str(p) for p in (root_files - engine_files))
    result["only_in_engine"] = sorted(str(p) for p in (engine_files - root_files))

    for rel in sorted(common_files):
        rf = root_cfg / rel
        ef = engine_cfg / rel
        if filecmp.cmp(rf, ef, shallow=False):
            result["identical"].append(str(rel))
        else:
            result["differing"].append(str(rel))
            # Check allowlist
            top_level = rel.parts[0]
            if top_level not in KNOWN_DRIFT_ALLOWLIST and str(rel) not in KNOWN_DRIFT_ALLOWLIST:
                result["unallowlisted_differing"].append(str(rel))

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Config SSOT Drift Detector.")
    parser.add_argument("--repo-root", default=".", help="Root of repository")
    parser.add_argument("--report", action="store_true", default=True, help="Print human-readable report")
    parser.add_argument("--strict", action="store_true", help="Fail if unallowlisted drift is detected")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    analysis = analyze_drift(repo_root)

    if args.json:
        print(json.dumps(analysis, indent=2, sort_keys=True))
        return 1 if (args.strict and analysis["unallowlisted_differing"]) else 0

    print("================================================================================")
    print("  CONFIG SSOT DRIFT REPORT: config/ vs resume_graph_engine/config/")
    print("================================================================================")
    print(f"Identical common files: {len(analysis['identical'])}")
    print(f"Differing common files: {len(analysis['differing'])}")
    print(f"Files only in root config/: {len(analysis['only_in_root'])}")
    print(f"Files only in engine config/: {len(analysis['only_in_engine'])}")
    print(f"Unallowlisted differing files: {len(analysis['unallowlisted_differing'])}\n")

    if analysis["differing"]:
        print("--- Differing Common Files ---")
        for f in analysis["differing"]:
            status = "ALLOWLISTED" if f not in analysis["unallowlisted_differing"] else "UNALLOWLISTED"
            print(f"  [{status}] {f}")
        print()

    if args.strict and analysis["unallowlisted_differing"]:
        print(f"[FAIL] Unallowlisted config drift detected: {analysis['unallowlisted_differing']}", file=sys.stderr)
        return 1

    print("[PASS] Config drift report complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
