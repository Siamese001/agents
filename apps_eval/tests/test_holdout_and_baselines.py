"""Wave 1 verification tests for populated holdout suites and named baselines."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_eval.baselines import load_baseline
from apps_eval.bootstrap_baselines import (
    CORE_BASELINE_SUITES,
    bootstrap_named_baselines,
    verify_named_baselines,
)
from apps_eval.contracts import CURRENT_EVAL_RECORD_SCHEMA_VERSION, EvalRequest
from apps_eval.runner.core import compare_record_to_baseline, run_eval
from apps_eval.scenarios import validate_suite_fixtures


def test_all_core_dev_and_holdout_fixtures_validate_cleanly() -> None:
    for suite_id in CORE_BASELINE_SUITES:
        problems = validate_suite_fixtures(suite_id)
        assert problems == [], f"{suite_id} fixture problems: {problems}"


def test_holdout_suites_run_cleanly_under_release_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPS_EVAL_RELEASE_GATE", "1")
    for suite_id in ("apps_rg.holdout.resume_generation", "apps_lic.holdout.outreach_message"):
        record = run_eval(
            EvalRequest(
                suite_id=suite_id,
                mode="snapshot",
                deterministic_only=True,
                out_dir=str(tmp_path),
                emit_l6_handoff=True,
            )
        )
        assert record.scorecard.finding_count > 0
        assert record.scorecard.passed_findings == record.scorecard.finding_count
        if suite_id.startswith("apps_lic."):
            assert record.scorecard.verdict == "pass"
            assert record.scorecard.score == 1.0


def test_committed_named_baselines_verify_and_detect_injected_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    res = verify_named_baselines()
    assert res["status"] == "PASS", f"baseline verification failed: {res}"
    assert set(res["verified"]) == set(CORE_BASELINE_SUITES)

    monkeypatch.setenv("APPS_EVAL_RELEASE_GATE", "1")
    for suite_id in CORE_BASELINE_SUITES:
        baseline = load_baseline(suite_id)
        assert baseline["schema_version"] == CURRENT_EVAL_RECORD_SCHEMA_VERSION
        rec = run_eval(
            EvalRequest(
                suite_id=suite_id,
                mode="snapshot",
                deterministic_only=True,
                out_dir=str(tmp_path),
                emit_l6_handoff=True,
            )
        )
        rec_dict = json.loads(Path(rec.artifact_paths["eval_record"]).read_text(encoding="utf-8"))
        cmp_ok = compare_record_to_baseline(rec_dict, baseline)
        assert cmp_ok.delta == 0.0
        assert cmp_ok.verdict == "pass"

        # Inject a score drop and verify fail-closed regression detection
        regressed = json.loads(json.dumps(rec_dict))
        regressed["scorecard"]["score"] = max(0.0, float(regressed["scorecard"]["score"]) - 0.10)
        cmp_bad = compare_record_to_baseline(regressed, baseline)
        assert cmp_bad.delta < 0.0
        assert cmp_bad.verdict == "regression"


def test_bootstrap_named_baselines_isolated_directory(tmp_path: Path) -> None:
    out = bootstrap_named_baselines(baseline_dir=tmp_path)
    assert out["status"] == "PASS"
    assert out["promoted_count"] == len(CORE_BASELINE_SUITES)
    check = verify_named_baselines(baseline_dir=tmp_path)
    assert check["status"] == "PASS"
