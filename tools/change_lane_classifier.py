#!/usr/bin/env python3
"""Fail-closed 3-lane risk classifier (Lane 0 / Lane 1 / Lane 2) for AI-SDLC governance.

Classifies changed file paths against config/governance/risk_lanes_policy.json:
- Unrecognized paths strictly escalate to Lane 2 (fail-closed).
- Mixed-lane changes strictly escalate to the highest lane touched.
- Self-referential governance controls (policy & classifier) are locked to Lane 2.
- Emits non-blocking batch/lane-mixing advisories without capping root-cause refactors.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_RELPATH = "config/governance/risk_lanes_policy.json"

SELF_REFERENTIAL_LOCKED_PATHS: frozenset[str] = frozenset(
    {
        "config/governance/risk_lanes_policy.json",
        "tools/change_lane_classifier.py",
        "tools/verify_commit.py",
        "tools/verify_main_readiness.py",
        "tools/pr_governance.py",
    }
)


def _normalize_relpath(raw: str, repo_root: Path | None = None) -> str:
    text = str(raw or "").strip().replace("\\", "/")
    if repo_root is not None:
        try:
            p = Path(text)
            if p.is_absolute():
                text = p.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            pass
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def _glob_matches(relpath: str, pattern: str) -> bool:
    norm_path = _normalize_relpath(relpath)
    norm_pat = str(pattern or "").strip().replace("\\", "/")
    if not norm_path or not norm_pat:
        return False
    if norm_pat.endswith("/**"):
        prefix = norm_pat[:-3].rstrip("/")
        return norm_path == prefix or norm_path.startswith(prefix + "/")
    if "**" in norm_pat:
        try:
            if PurePosixPath(norm_path).match(norm_pat):
                return True
        except ValueError:
            pass
        return fnmatch.fnmatch(norm_path, norm_pat.replace("**/", "*"))
    return fnmatch.fnmatch(norm_path, norm_pat)


def load_risk_lanes_policy(repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or _REPO_ROOT).resolve()
    policy_path = root / DEFAULT_POLICY_RELPATH
    if not policy_path.is_file():
        raise FileNotFoundError(f"Missing risk lanes policy: {policy_path}")
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "lanes" not in data:
        raise ValueError(f"Invalid risk lanes policy structure: {policy_path}")
    return data


def _domain_bucket(relpath: str) -> str:
    norm = _normalize_relpath(relpath)
    if not norm:
        return "root"
    parts = norm.split("/")
    if parts[0] in {".agents", ".antigravity", ".githooks", "config", "tools"} or norm == "AGENTS.md":
        return "governance"
    if parts[0] in {"tests", "docs", "reports", "plans"}:
        return parts[0]
    return parts[0]


def classify_single_path(
    relpath: str,
    policy: Mapping[str, Any],
) -> tuple[int, str, bool]:
    """Return (lane, reason, is_self_referential_lock) for one normalized path."""
    norm = _normalize_relpath(relpath)
    locked = set(SELF_REFERENTIAL_LOCKED_PATHS) | {
        _normalize_relpath(p) for p in (policy.get("self_referential_immutable_paths") or ())
    }
    if norm in locked:
        return 2, "self_referential_immutable_lock", True

    lanes = policy.get("lanes") or {}
    # Precedence: Lane 2 > Lane 1 > Lane 0 (fail-closed escalation when patterns overlap).
    for lane_id in (2, 1, 0):
        spec = lanes.get(str(lane_id)) or {}
        for pattern in spec.get("globs") or ():
            if _glob_matches(norm, str(pattern)):
                return lane_id, f"matched_lane_{lane_id}:{pattern}", False

    default_lane = int(policy.get("default_unrecognized_lane", 2))
    if default_lane < 2:
        default_lane = 2
    return default_lane, "unrecognized_path_escalated_to_lane_2", False


def classify_paths(
    paths: Sequence[str],
    *,
    repo_root: Path | None = None,
    policy: Mapping[str, Any] | None = None,
    churn_loc: int = 0,
) -> dict[str, Any]:
    """Classify a set of changed paths with fail-closed escalation and batch advisories."""
    root = (repo_root or _REPO_ROOT).resolve()
    pol = dict(policy) if policy is not None else load_risk_lanes_policy(root)
    normalized = sorted({_normalize_relpath(p, root) for p in paths if str(p or "").strip()})

    per_path: list[dict[str, Any]] = []
    lanes_seen: set[int] = set()
    unrecognized_paths: list[str] = []
    self_ref_paths: list[str] = []
    prod_files: list[str] = []
    domains: set[str] = set()

    for rel in normalized:
        lane_id, reason, is_locked = classify_single_path(rel, pol)
        lanes_seen.add(lane_id)
        if reason == "unrecognized_path_escalated_to_lane_2":
            unrecognized_paths.append(rel)
        if is_locked:
            self_ref_paths.append(rel)
        domain = _domain_bucket(rel)
        domains.add(domain)
        if lane_id >= 1 and not rel.startswith(("tests/", "docs/", "reports/", "plans/")) and "/tests/" not in rel:
            prod_files.append(rel)
        per_path.append(
            {
                "path": rel,
                "lane": lane_id,
                "reason": reason,
                "domain": domain,
                "self_referential_lock": is_locked,
            }
        )

    effective_lane = max(lanes_seen) if lanes_seen else 0
    lane_spec = (pol.get("lanes") or {}).get(str(effective_lane)) or {}
    required_stages = list(lane_spec.get("readiness_stages") or [])

    soft_caps = pol.get("soft_caps") or {}
    advisories: list[dict[str, Any]] = []
    if len(lanes_seen) > 1:
        advisories.append(
            {
                "code": "MIXED_RISK_LANES",
                "severity": "advisory",
                "message": f"Change touches multiple risk lanes {sorted(lanes_seen)}; escalated to Lane {effective_lane}.",
            }
        )
    if (
        soft_caps.get("advisory_warn_on_lane2_governance_escalation", True)
        and effective_lane == 2
        and len(domains) > 1
        and "governance" in domains
    ):
        advisories.append(
            {
                "code": "LANE2_GOVERNANCE_ESCALATION",
                "severity": "advisory",
                "message": f"Governance changes mixed with application domains {sorted(domains)}; all files verified under Lane 2.",
            }
        )
    max_prod = int(soft_caps.get("advisory_max_production_files", 8))
    if max_prod > 0 and len(prod_files) > max_prod:
        advisories.append(
            {
                "code": "SOFT_BATCH_PROD_FILES",
                "severity": "advisory",
                "message": f"{len(prod_files)} production files touched (soft advisory threshold: {max_prod}; non-blocking).",
            }
        )
    max_churn = int(soft_caps.get("advisory_max_code_churn_loc", 500))
    if max_churn > 0 and churn_loc > max_churn:
        advisories.append(
            {
                "code": "SOFT_BATCH_CHURN_LOC",
                "severity": "advisory",
                "message": f"{churn_loc} LOC changed (soft advisory threshold: {max_churn}; non-blocking).",
            }
        )
    if unrecognized_paths:
        advisories.append(
            {
                "code": "UNRECOGNIZED_PATH_ESCALATED",
                "severity": "advisory",
                "message": f"{len(unrecognized_paths)} unmapped path(s) escalated fail-closed to Lane 2.",
            }
        )

    return {
        "schema_version": "agents.change_lane_classification.v1",
        "effective_lane": effective_lane,
        "lane": effective_lane,
        "lane_name": str(lane_spec.get("name") or f"Lane {effective_lane}"),
        "lanes_touched": sorted(lanes_seen),
        "path_count": len(normalized),
        "production_file_count": len(prod_files),
        "domains_touched": sorted(domains),
        "unrecognized_paths": unrecognized_paths,
        "self_referential_lock": bool(self_ref_paths),
        "self_referential_paths": self_ref_paths,
        "required_readiness_stages": required_stages,
        "advisories": advisories,
        "classifications": per_path,
    }


def collect_git_changed_paths(
    repo_root: Path,
    *,
    staged: bool = False,
    base_ref: str = "main",
) -> tuple[list[str], int]:
    """Collect changed file paths and approximate churn LOC from git."""
    if staged:
        cmd = ["git", "diff", "--cached", "--name-only"]
        stat_cmd = ["git", "diff", "--cached", "--numstat"]
    else:
        cmd = ["git", "diff", "--name-only", f"{base_ref}...HEAD"]
        stat_cmd = ["git", "diff", "--numstat", f"{base_ref}...HEAD"]
    res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, shell=False, timeout=15)
    paths = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()] if res.returncode == 0 else []
    if not paths and not staged:
        # Fallback to working tree + staged changes when already on main or single-commit repo.
        fallback = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            shell=False,
            timeout=15,
        )
        if fallback.returncode == 0:
            for line in fallback.stdout.splitlines():
                if len(line) >= 4:
                    entry = line[3:].strip()
                    if " -> " in entry:
                        entry = entry.split(" -> ", 1)[1].strip()
                    if entry:
                        paths.append(entry)

    churn_loc = 0
    stat_res = subprocess.run(stat_cmd, cwd=repo_root, capture_output=True, text=True, shell=False, timeout=15)
    if stat_res.returncode == 0:
        for line in stat_res.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                churn_loc += int(parts[0]) + int(parts[1])
    return sorted(set(paths)), churn_loc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed 3-lane AI-SDLC change classifier.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--paths", nargs="*", default=None, help="Explicit relative paths to classify.")
    parser.add_argument("--staged", action="store_true", help="Classify git staged paths.")
    parser.add_argument("--base-ref", default="main", help="Base ref for branch diff classification.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    churn_loc = 0
    if args.paths is not None:
        paths = list(args.paths)
    else:
        paths, churn_loc = collect_git_changed_paths(repo_root, staged=args.staged, base_ref=args.base_ref)

    report = classify_paths(paths, repo_root=repo_root, churn_loc=churn_loc)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Risk Lane: {report['lane_name']} (Lane {report['effective_lane']}, {report['path_count']} path(s))")
        if report["unrecognized_paths"]:
            print(f"  Unrecognized paths escalated to Lane 2: {report['unrecognized_paths']}")
        for adv in report["advisories"]:
            print(f"  [ADVISORY:{adv['code']}] {adv['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
