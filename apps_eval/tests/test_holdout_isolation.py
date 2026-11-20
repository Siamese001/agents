from __future__ import annotations

from pathlib import Path

import pytest

from apps_eval.contracts import EvalRequest
from apps_eval.registry import load_suites_registry
from apps_eval.runner.core import run_eval


def test_holdout_suites_are_populated_isolated_and_release_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suites = load_suites_registry()
    holdouts = {key: value for key, value in suites.items() if value["split"] == "holdout"}
    assert set(holdouts) == {"apps_rg.holdout.resume_generation", "apps_lic.holdout.outreach_message"}
    assert all(len(value["scenarios"]) >= 4 for value in holdouts.values())

    # Holdout scenario IDs must be strictly disjoint from dev scenario IDs.
    dev_scenarios = {
        sid
        for value in suites.values()
        if value["split"] == "dev"
        for sid in value["scenarios"]
    }
    holdout_scenarios = {sid for value in holdouts.values() for sid in value["scenarios"]}
    assert dev_scenarios.isdisjoint(holdout_scenarios)

    monkeypatch.delenv("APPS_EVAL_RELEASE_GATE", raising=False)
    for holdout_suite in ("apps_rg.holdout.resume_generation", "apps_lic.holdout.outreach_message"):
        with pytest.raises(PermissionError):
            run_eval(
                EvalRequest(
                    suite_id=holdout_suite,
                    mode="snapshot",
                    deterministic_only=True,
                    out_dir=str(tmp_path),
                    emit_l6_handoff=True,
                )
            )
