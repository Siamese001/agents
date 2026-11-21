#!/usr/bin/env python3
"""Diff-scoped unmocked domain evaluation shield (Tier 2 Stage 8).

Selects affected domains from changed git paths (or runs all 4 domains on Lane 2 / --all),
verifies the runtime environment is unmocked, and executes real production checks.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.change_lane_classifier import classify_paths, collect_git_changed_paths
from tools.eval_shield_core.domain_eval_checks import (
    DOMAIN_RUNNERS,
    verify_unmocked_runtime_environment,
)


def select_domains_for_paths(paths: Sequence[str], *, effective_lane: int, run_all: bool = False) -> list[str]:
    if run_all or effective_lane >= 2 or not paths:
        return list(DOMAIN_RUNNERS.keys())
    selected: set[str] = set()
    for p in paths:
        norm = str(p).replace("\\", "/")
        if norm.startswith(("resume_graph_engine/", "resume_engine/")):
            selected.add("resume_graph_engine")
        elif norm.startswith("outreach_engine/"):
            selected.add("outreach_engine")
        elif norm.startswith("apps_research/"):
            selected.add("apps_research")
        elif norm.startswith((".agents/", "config/governance/", "tools/")) or norm == "AGENTS.md":
            selected.add("governance_guards")
    if not selected:
        selected.add("governance_guards")
    return [d for d in DOMAIN_RUNNERS if d in selected]


def run_eval_shield(
    repo_root: Path,
    *,
    paths: Sequence[str] | None = None,
    run_all: bool = False,
) -> dict[str, Any]:
    root = repo_root.resolve()
    env_ok, env_msg = verify_unmocked_runtime_environment()
    if not env_ok:
        return {
            "schema_version": "agents.diff_scoped_eval_shield.v1",
            "status": "FAIL",
            "error": env_msg,
            "domains_run": [],
            "results": [],
        }

    changed = list(paths) if paths is not None else collect_git_changed_paths(root)[0]
    lane_info = classify_paths(changed, repo_root=root)
    domains = select_domains_for_paths(changed, effective_lane=int(lane_info["effective_lane"]), run_all=run_all)

    started = time.time()
    results: list[dict[str, Any]] = []
    for domain in domains:
        t0 = time.time()
        res = DOMAIN_RUNNERS[domain](root)
        res["elapsed_seconds"] = round(time.time() - t0, 3)
        results.append(res)

    all_passed = all(r.get("status") == "PASS" for r in results) and bool(results)
    return {
        "schema_version": "agents.diff_scoped_eval_shield.v1",
        "status": "PASS" if all_passed else "FAIL",
        "effective_lane": int(lane_info["effective_lane"]),
        "domains_run": domains,
        "elapsed_seconds": round(time.time() - started, 3),
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run unmocked diff-scoped domain eval shield.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--all", action="store_true", dest="run_all", help="Run all domain shield checks.")
    parser.add_argument("--paths", nargs="*", default=None, help="Explicit changed paths for scoping.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    report = run_eval_shield(Path(args.repo_root).resolve(), paths=args.paths, run_all=args.run_all)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[diff-scoped-eval-shield] status={report['status']} "
            f"domains={report['domains_run']} elapsed={report.get('elapsed_seconds', 0)}s"
        )
        for r in report.get("results", []):
            print(f"  - {r['domain']}: {r['status']} ({r.get('checks_run', 0)} checks, {r.get('elapsed_seconds', 0)}s)")
            for f in r.get("failures", []):
                print(f"      FAIL: {f}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
