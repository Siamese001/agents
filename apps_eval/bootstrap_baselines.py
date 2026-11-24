"""Deterministic named baseline bootstrap and verification helper for apps_eval.

Pure JSON/filesystem module (zero SQLite imports to preserve domain storage isolation).
Runs registered dev and holdout suites for ``apps_rg`` and ``apps_lic``, validates fixture
hashes, checks grader pass invariants, and seals named baseline records under
``apps_eval/baselines/``.

Note on ``apps_rg`` lightweight snapshot suites:
``apps_rg.product.v1`` requires full 11-lane product run bundles for ``scorecard.verdict == "pass"``
so lightweight snapshots can never spoof full product coverage (enforced by
``test_apps_rg_dev_suite.py``). For those snapshot suites, baseline promotion enforces
100% deterministic grader pass (``passed_findings == finding_count``) and locks the
exact baseline score so any regression fails closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

from apps_eval.baselines import DEFAULT_BASELINE_DIR, baseline_path, load_baseline, promote_baseline
from apps_eval.contracts import EvalRequest
from apps_eval.registry import load_suites_registry
from apps_eval.runner.core import compare_record_to_baseline, run_eval
from apps_eval.scenarios import validate_suite_fixtures

CORE_BASELINE_SUITES: tuple[str, ...] = (
    "apps_rg.dev.resume_generation",
    "apps_rg.holdout.resume_generation",
    "apps_lic.dev.outreach_message",
    "apps_lic.holdout.outreach_message",
)

# Suites whose lightweight snapshot fixtures intentionally trigger apps_rg.product.v1
# missing-artifact microstep coverage guards while requiring 100% deterministic grader pass.
SNAPSHOT_GRADER_ONLY_SUITES: frozenset[str] = frozenset(
    {
        "apps_rg.dev.resume_generation",
        "apps_rg.holdout.resume_generation",
    }
)


def compute_snapshot_hash(snapshot_payload: dict[str, Any]) -> str:
    """Compute canonical SHA-256 deterministic hash for an app_output_snapshot payload."""
    data = dict(snapshot_payload)
    data.pop("deterministic_hash", None)
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _check_record_baseline_eligibility(suite_id: str, scorecard: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    finding_count = int(scorecard.get("finding_count", 0))
    passed_findings = int(scorecard.get("passed_findings", 0))
    verdict = str(scorecard.get("verdict", ""))

    if finding_count <= 0:
        errors.append(f"{suite_id}: finding_count must be > 0")
    if passed_findings != finding_count:
        errors.append(
            f"{suite_id}: deterministic graders failed ({passed_findings}/{finding_count} passed)"
        )
    if suite_id not in SNAPSHOT_GRADER_ONLY_SUITES and verdict != "pass":
        errors.append(f"{suite_id}: scorecard verdict is {verdict!r}, expected 'pass'")
    return errors


def bootstrap_named_baselines(
    *,
    suites: Sequence[str] = CORE_BASELINE_SUITES,
    baseline_dir: str | Path = DEFAULT_BASELINE_DIR,
) -> dict[str, Any]:
    """Run deterministic snapshot suites and promote eligible records to named baselines."""
    registry = load_suites_registry()
    promoted: dict[str, dict[str, Any]] = {}
    problems_by_suite: dict[str, list[str]] = {}

    from infrastructure.config.env_loader import temporary_env_override

    with temporary_env_override({"APPS_EVAL_RELEASE_GATE": "1"}), tempfile.TemporaryDirectory(
        prefix="apps_eval_baseline_boot_"
    ) as tmp_dir:
        for suite_id in suites:
            if suite_id not in registry:
                raise KeyError(f"unknown suite_id: {suite_id}")
            problems = validate_suite_fixtures(suite_id)
            if problems:
                problems_by_suite[suite_id] = problems
                continue
            record = run_eval(
                EvalRequest(
                    suite_id=suite_id,
                    mode="snapshot",
                    deterministic_only=True,
                    out_dir=tmp_dir,
                    emit_l6_handoff=True,
                )
            )
            sc_dict = record.scorecard.to_dict()
            eligibility_errs = _check_record_baseline_eligibility(suite_id, sc_dict)
            if eligibility_errs:
                problems_by_suite[suite_id] = eligibility_errs
                continue
            record_path = Path(record.artifact_paths["eval_record"])
            require_pass = suite_id not in SNAPSHOT_GRADER_ONLY_SUITES
            target = promote_baseline(
                record_path,
                suite_id,
                baseline_dir=baseline_dir,
                require_pass=require_pass,
            )
            record_dict = json.loads(record_path.read_text(encoding="utf-8"))
            baseline_dict = load_baseline(suite_id, baseline_dir)
            comparison = compare_record_to_baseline(record_dict, baseline_dict)
            promoted[suite_id] = {
                "baseline_path": target.as_posix(),
                "record_id": record.record_id,
                "verdict": record.scorecard.verdict,
                "score": record.scorecard.score,
                "finding_count": int(sc_dict.get("finding_count", 0)),
                "passed_findings": int(sc_dict.get("passed_findings", 0)),
                "scenario_count": int(sc_dict.get("scenario_count", 0)),
                "comparison_delta": float(comparison.delta),
                "regression": comparison.verdict == "regression",
                "comparison_verdict": str(comparison.verdict),
            }

    if problems_by_suite:
        raise ValueError(f"baseline bootstrap failed: {json.dumps(problems_by_suite, sort_keys=True)}")

    return {
        "status": "PASS",
        "baseline_dir": Path(baseline_dir).as_posix(),
        "promoted_count": len(promoted),
        "suites": promoted,
    }


def verify_named_baselines(
    *,
    suites: Sequence[str] = CORE_BASELINE_SUITES,
    baseline_dir: str | Path = DEFAULT_BASELINE_DIR,
) -> dict[str, Any]:
    """Verify every required named baseline exists, validates against schema, and meets pass invariants."""
    missing: list[str] = []
    invalid: list[str] = []
    verified: dict[str, dict[str, Any]] = {}

    for suite_id in suites:
        path = baseline_path(suite_id, baseline_dir)
        if not path.is_file():
            missing.append(suite_id)
            continue
        try:
            data = load_baseline(suite_id, baseline_dir)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            invalid.append(f"{suite_id}: {exc}")
            continue
        scorecard = data.get("scorecard") or {}
        eligibility_errs = _check_record_baseline_eligibility(suite_id, scorecard)
        if eligibility_errs:
            invalid.extend(eligibility_errs)
            continue
        verified[suite_id] = {
            "path": path.as_posix(),
            "record_id": str(data.get("record_id", "")),
            "score": float(scorecard.get("score", 0.0)),
            "verdict": str(scorecard.get("verdict", "")),
            "finding_count": int(scorecard.get("finding_count", 0)),
            "passed_findings": int(scorecard.get("passed_findings", 0)),
            "suite_id": str(data.get("suite_id", "")),
        }

    ok = not missing and not invalid and len(verified) == len(suites)
    return {
        "status": "PASS" if ok else "FAIL",
        "missing": missing,
        "invalid": invalid,
        "verified": verified,
    }
