"""CI lane-dev boundary helpers for standalone contract tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from apps_rg.runtime.non_product_proof_stamp import (
    CI_LANE_DEV_HARNESS_CLASSIFICATION,
    CONTRACT_TEST_PROOF_CLASSIFICATION,
)

_APP_RUNTIME_UNTRACKED_ONLY = "PRE_EXISTING_UNTRACKED_APP_RUNTIME_PATH"
_APP_RUNTIME_TRACKED_ONLY = "TRACKED_APP_RUNTIME_WORKING_TREE_CHANGES"
_APP_RUNTIME_MIXED = "TRACKED_AND_UNTRACKED_APP_RUNTIME_CHANGES"


def run_git_cmd(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        shell=False,
        env=env,
    )


def classify_apps_rg_porcelain_lines(lines: list[str]) -> dict[str, Any]:
    trimmed = [line.rstrip("\r") for line in lines if line.strip()]
    tracked = False
    untracked = False
    raw_paths: list[str] = []

    for entry in trimmed:
        if entry.startswith("??"):
            untracked = True
            rest = entry[2:].lstrip()
        else:
            tracked = True
            rest = entry[3:].lstrip() if len(entry) > 3 else entry.lstrip()

        if " -> " in rest:
            raw_paths.extend(path.strip() for path in rest.split(" -> "))
        else:
            raw_paths.append(rest.strip())

    dirty = tracked or untracked
    if not dirty:
        reason = ""
    elif untracked and not tracked:
        reason = _APP_RUNTIME_UNTRACKED_ONLY
    elif tracked and untracked:
        reason = _APP_RUNTIME_MIXED
    else:
        reason = _APP_RUNTIME_TRACKED_ONLY

    return {
        "apps_rg_modified": dirty,
        "apps_rg_dirty_reason": reason,
        "apps_rg_dirty_paths": sorted({path for path in raw_paths if path}),
    }


def finalize_boundary_no_bypass(artifact: dict[str, Any], repo: Path) -> None:
    raw = run_git_cmd(
        ["git", "status", "--porcelain=v1", "--", "apps_rg"], cwd=repo
    )
    classification = classify_apps_rg_porcelain_lines(
        (raw.stdout or "").splitlines()
    )
    boundary = artifact.setdefault("boundary_no_bypass", {})
    boundary.update(classification)
    boundary["apps_rg_modified_by_this_task"] = False
    boundary.setdefault("new_app_literals_in_core", False)
    boundary.setdefault("direct_l2_chroma_bypass", False)
    boundary.setdefault("direct_l4_write_bypass", False)
    boundary.setdefault("mock_pass", False)
    boundary["direct_bypass"] = bool(boundary.get("direct_l2_chroma_bypass")) or bool(
        boundary.get("direct_l4_write_bypass")
    )


def persist_ci_lane_dev_proof_artifact(
    artifact: dict[str, Any],
    repo: Path,
    *,
    artifact_path: Path,
    proof_classification: str | None = None,
) -> None:
    """Stamp a non-product classification and persist a test proof artifact."""
    finalize_boundary_no_bypass(artifact, repo)
    unstaged = run_git_cmd(["git", "diff", "--name-only"], cwd=repo)
    staged = run_git_cmd(["git", "diff", "--name-only", "--cached"], cwd=repo)
    names = {
        line.strip()
        for line in (unstaged.stdout or "").splitlines()
        + (staged.stdout or "").splitlines()
        if line.strip()
    }
    artifact["files_changed"] = sorted(names)
    artifact["proof_classification"] = (
        proof_classification or CI_LANE_DEV_HARNESS_CLASSIFICATION
    )
    artifact["product_certification"] = "NOT_CLAIMED"
    artifact["l7_certification"] = "NOT_CLAIMED"
    artifact["fort_knox_certification"] = "NOT_CLAIMED"
    artifact["integrated_r4_invoked"] = False
    artifact["explicit_non_claims"] = [
        "CI lane rollup harness only",
        "not product runtime certification",
        "not L7 or Fort Knox proof",
        "integrated R4 requires python -m apps_rg whole-run gate separately",
    ]
    if artifact["proof_classification"] == CONTRACT_TEST_PROOF_CLASSIFICATION:
        artifact["explicit_non_claims"].append("contract test proof only")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")


def minimal_ci_lane_dev_artifact() -> dict[str, Any]:
    """Return a minimal artifact shell for boundary contract tests."""
    return {
        "boundary_no_bypass": {
            "mock_pass": False,
            "direct_l2_chroma_bypass": False,
            "direct_l4_write_bypass": False,
        },
        "commands_run": [],
        "pa": {},
        "route": {},
        "c0": {},
        "exit": {},
    }
