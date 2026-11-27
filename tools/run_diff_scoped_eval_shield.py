#!/usr/bin/env python3
"""Diff-scoped unmocked domain evaluation shield (Tier 2 Stage 8).

Selects affected domains from changed git paths using pinned-fix watch prefixes plus
2-hop reverse dependency expansion, verifies the runtime environment is unmocked,
enforces a <10.0s per-domain SLA, and supports counterfactual --inject-fault checks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps_eval._core_governance_bridge import SHIELD_SLA_SECONDS
from tools.change_lane_classifier import classify_paths, collect_git_changed_paths
from tools.eval_shield_core.domain_eval_checks import (
    DOMAIN_RUNNERS,
    verify_unmocked_runtime_environment,
)

PER_DOMAIN_SLA_SECONDS: float = SHIELD_SLA_SECONDS

ALL_SHIELD_TRIGGER_PREFIXES: tuple[str, ...] = (
    "apps_eval/suites/",
    "tools/run_diff_scoped_eval_shield.py",
    "tools/eval_shield_core/",
    "config/judges/",
    "config/provider_profiles.yaml",
    "config/governance/",
)


def _expand_reverse_importers(repo_root: Path, paths: Sequence[str], *, max_callers: int = 40) -> list[str]:
    """Expand changed Python modules via centralized core-governance 2-hop reverse-importer scanner."""
    from apps_eval._core_governance_bridge import expand_reverse_python_importers

    return expand_reverse_python_importers(repo_root, paths, max_callers=max_callers, hops=2)


def select_domains_for_paths(
    paths: Sequence[str],
    *,
    effective_lane: int,
    run_all: bool = False,
    repo_root: Path | None = None,
) -> list[str]:
    if run_all or effective_lane >= 2 or not paths:
        return list(DOMAIN_RUNNERS.keys())

    norm_paths = [str(p).replace("\\", "/") for p in paths]
    if any(p.startswith(ALL_SHIELD_TRIGGER_PREFIXES) for p in norm_paths):
        return list(DOMAIN_RUNNERS.keys())

    if repo_root is not None:
        norm_paths = _expand_reverse_importers(repo_root, norm_paths)
        if "__HUB_EXCEEDED__" in norm_paths:
            return list(DOMAIN_RUNNERS.keys())

    selected: set[str] = set()
    for norm in norm_paths:
        if norm.startswith(("resume_graph_engine/", "resume_engine/")):
            selected.add("resume_graph_engine")
        elif norm.startswith("outreach_engine/"):
            selected.add("outreach_engine")
        elif norm.startswith("apps_research/"):
            selected.add("apps_research")
        elif norm.startswith(("apps_eval/", "agents/", "infrastructure/", "apps_model_telemetry/")):
            selected.add("agents_eval_flywheel")
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
    inject_fault: str | None = None,
    per_domain_sla_seconds: float = PER_DOMAIN_SLA_SECONDS,
) -> dict[str, Any]:
    root = repo_root.resolve()
    env_ok, env_msg = verify_unmocked_runtime_environment()
    if not env_ok:
        return {
            "schema_version": "agents.diff_scoped_eval_shield.v2",
            "status": "FAIL",
            "error": env_msg,
            "domains_run": [],
            "slow_domains": [],
            "results": [],
        }

    if inject_fault is not None and inject_fault not in DOMAIN_RUNNERS:
        return {
            "schema_version": "agents.diff_scoped_eval_shield.v2",
            "status": "FAIL",
            "error": f"Unknown --inject-fault domain: {inject_fault}",
            "domains_run": [],
            "slow_domains": [],
            "results": [],
        }

    changed = list(paths) if paths is not None else collect_git_changed_paths(root)[0]
    lane_info = classify_paths(changed, repo_root=root)
    domains = select_domains_for_paths(
        changed,
        effective_lane=int(lane_info["effective_lane"]),
        run_all=run_all,
        repo_root=root,
    )

    started = time.time()
    results: list[dict[str, Any]] = []
    slow_domains: list[str] = []
    for domain in domains:
        t0 = time.time()
        res = DOMAIN_RUNNERS[domain](root, inject_fault=(inject_fault == domain))
        elapsed = round(time.time() - t0, 3)
        res["elapsed_seconds"] = elapsed
        if elapsed > per_domain_sla_seconds:
            slow_domains.append(domain)
            res.setdefault("failures", []).append(
                f"per_domain_sla_exceeded:{elapsed}s>{per_domain_sla_seconds}s"
            )
            res["status"] = "FAIL"
        results.append(res)

    all_passed = all(r.get("status") == "PASS" for r in results) and bool(results) and not slow_domains
    return {
        "schema_version": "agents.diff_scoped_eval_shield.v2",
        "status": "PASS" if all_passed else "FAIL",
        "effective_lane": int(lane_info["effective_lane"]),
        "domains_run": domains,
        "slow_domains": slow_domains,
        "inject_fault": inject_fault,
        "elapsed_seconds": round(time.time() - started, 3),
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run unmocked diff-scoped domain eval shield.")
    parser.add_argument("--repo-root", default=str(_REPO_ROOT), help="Repository root path.")
    parser.add_argument(
        "--all",
        "--all-domains",
        action="store_true",
        dest="run_all",
        help="Run all domain shield checks.",
    )
    parser.add_argument("--paths", nargs="*", default=None, help="Explicit changed paths for scoping.")
    parser.add_argument(
        "--inject-fault",
        default=None,
        help="Inject a counterfactual failure into a named domain to prove fail-closed sensitivity.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    report = run_eval_shield(
        Path(args.repo_root).resolve(),
        paths=args.paths,
        run_all=args.run_all,
        inject_fault=args.inject_fault,
    )
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
