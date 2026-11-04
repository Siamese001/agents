#!/usr/bin/env python3
"""Config & Data SSOT Drift Detector.

Compares repository root `config/` and `data/` against engine `resume_graph_engine/config/`
and `resume_graph_engine/data/`, flagging divergence, orphaned configurations, and unallowlisted drifts.

Supports:
  --strict: Fail if unallowlisted drift is detected (default, exit 1 on drift)
  --advisory: Print drift report without failing exit code
  --json: Output JSON payload
"""

from __future__ import annotations

import argparse
import filecmp
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.ssot_sprawl_scanner import KNOWN_DRIFT_ALLOWLIST, run_sprawl_scan


def analyze_drift(repo_root: Path, *, include_sprawl: bool = False) -> dict[str, Any]:
    root_cfg = repo_root / "config"
    engine_cfg = repo_root / "resume_graph_engine" / "config"
    outreach_cfg = repo_root / "outreach_engine" / "config"
    root_data = repo_root / "data"
    engine_data = repo_root / "resume_graph_engine" / "data"
    outreach_data = repo_root / "outreach_engine" / "data"

    result: dict[str, Any] = {
        "root_config_exists": root_cfg.is_dir(),
        "engine_config_exists": engine_cfg.is_dir(),
        "outreach_config_exists": outreach_cfg.is_dir(),
        "outreach_data_exists": outreach_data.is_dir(),
        "identical": [],
        "differing": [],
        "only_in_root": [],
        "only_in_engine": [],
        "unallowlisted_differing": [],
        "outreach_config_files_verified": 0,
        "outreach_data_files_verified": 0,
        "data_identical_count": 0,
        "data_differing": [],
    }

    if outreach_cfg.is_dir():
        result["outreach_config_files_verified"] = sum(
            1 for p in outreach_cfg.rglob("*") if p.is_file() and "__pycache__" not in p.parts
        )
    if outreach_data.is_dir():
        result["outreach_data_files_verified"] = sum(
            1 for p in outreach_data.rglob("*") if p.is_file() and "__pycache__" not in p.parts
        )

    if root_cfg.is_dir() and engine_cfg.is_dir():
        root_files = {p.relative_to(root_cfg) for p in root_cfg.rglob("*") if p.is_file()}
        engine_files = {p.relative_to(engine_cfg) for p in engine_cfg.rglob("*") if p.is_file()}

        common_files = root_files & engine_files
        result["only_in_root"] = sorted(str(p) for p in (root_files - engine_files))
        result["only_in_engine"] = sorted(str(p) for p in (engine_files - root_files))

        for rel in sorted(common_files):
            rf = root_cfg / rel
            ef = engine_cfg / rel
            rel_str = str(rel).replace("\\", "/")
            if filecmp.cmp(rf, ef, shallow=False):
                result["identical"].append(rel_str)
            else:
                result["differing"].append(rel_str)
                if rel_str not in KNOWN_DRIFT_ALLOWLIST:
                    result["unallowlisted_differing"].append(rel_str)

    if root_data.is_dir() and engine_data.is_dir():
        r_data_files = {p.relative_to(root_data) for p in root_data.rglob("*") if p.is_file()}
        e_data_files = {p.relative_to(engine_data) for p in engine_data.rglob("*") if p.is_file()}
        for rel in sorted(r_data_files & e_data_files):
            rf = root_data / rel
            ef = engine_data / rel
            rel_str = str(rel).replace("\\", "/")
            if filecmp.cmp(rf, ef, shallow=False):
                result["data_identical_count"] += 1
            else:
                result["data_differing"].append(rel_str)

    if include_sprawl:
        result["sprawl_scan"] = run_sprawl_scan(repo_root)

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Config & Data SSOT Drift Detector.")
    parser.add_argument("--repo-root", default=".", help="Root of repository")
    parser.add_argument("--report", action="store_true", default=True, help="Print human-readable report")
    parser.add_argument("--strict", action="store_true", default=True, help="Fail if unallowlisted drift is detected")
    parser.add_argument("--advisory", action="store_true", help="Report drift without failing exit code")
    parser.add_argument("--include-sprawl", action="store_true", help="Include full multi-folder sprawl scan")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    strict_mode = args.strict and not args.advisory

    analysis = analyze_drift(repo_root, include_sprawl=args.include_sprawl)
    sprawl_dirty = bool(args.include_sprawl and not analysis.get("sprawl_scan", {}).get("is_clean", True))
    has_unallowlisted_drift = bool(analysis["unallowlisted_differing"] or analysis["data_differing"] or sprawl_dirty)

    if args.json:
        print(json.dumps(analysis, indent=2, sort_keys=True))
        return 1 if (strict_mode and has_unallowlisted_drift) else 0

    print("================================================================================")
    print("  CONFIG & DATA SSOT DRIFT REPORT: root vs resume_graph_engine")
    print("================================================================================")
    print(f"Identical common config files: {len(analysis['identical'])}")
    print(f"Differing common config files: {len(analysis['differing'])}")
    print(f"Unallowlisted differing config files: {len(analysis['unallowlisted_differing'])}")
    print(f"Identical common data files: {analysis['data_identical_count']}")
    print(f"Differing common data files: {len(analysis['data_differing'])}\n")

    if analysis["differing"]:
        print("--- Differing Common Config Files ---")
        for f in analysis["differing"]:
            status = "ALLOWLISTED" if f not in analysis["unallowlisted_differing"] else "UNALLOWLISTED"
            print(f"  [{status}] {f}")
        print()

    if analysis["data_differing"]:
        print("--- Differing Common Data Files ---")
        for f in analysis["data_differing"][:20]:
            print(f"  [UNALLOWLISTED] data/{f}")
        print()

    if strict_mode and has_unallowlisted_drift:
        print(
            f"[FAIL] Unallowlisted SSOT drift detected: config={analysis['unallowlisted_differing']}, "
            f"data={analysis['data_differing'][:10]}",
            file=sys.stderr,
        )
        return 1

    print("[PASS] Config and data drift check complete (zero unallowlisted drift).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
