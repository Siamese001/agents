from __future__ import annotations

import pytest

from apps_eval.contracts import AppOutputSnapshot, EvalRequest
from apps_eval.coverage import (
    ANTHROPIC_DETERMINISTIC_FIXTURE_PROFILE_ID,
    apps_rg_contract_profile,
)
from apps_eval.runner.core import run_current_snapshot_eval, run_eval
from apps_eval.scenarios import validate_suite_fixtures


_SUITE = "apps_rg.fixture.anthropic_deterministic_e2e"


def test_anthropic_fixture_profile_is_structurally_valid_and_non_product() -> None:
    assert validate_suite_fixtures(_SUITE) == []
    profile = apps_rg_contract_profile(ANTHROPIC_DETERMINISTIC_FIXTURE_PROFILE_ID)
    assert profile["fixture_only"] is True
    assert profile["product_eligible"] is False
    assert profile["allowed_modes"] == ["snapshot"]


def test_anthropic_fixture_profile_rejects_non_harness_and_static_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    request = EvalRequest(suite_id=_SUITE, out_dir=str(tmp_path))
    monkeypatch.delenv("APPS_RG_TEST_HARNESS", raising=False)
    with pytest.raises(PermissionError, match="test harness"):
        run_eval(request)
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    with pytest.raises(PermissionError, match="runtime-produced snapshot override"):
        run_eval(request)


def test_anthropic_fixture_snapshot_cannot_enter_current_snapshot_or_release_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    snapshot = AppOutputSnapshot(
        app_id="apps_rg",
        scenario_id="anthropic_deterministic_fixture",
        x3_disposition="TEST_FIXTURE_ONLY",
        output={"runtime": {}, "sections": {}},
        provenance={
            "fixture_only": True,
            "source_unchanged": True,
            "source_seal_verified": False,
            "preflight_verified": False,
        },
    )
    with pytest.raises(ValueError, match="product authorization seal"):
        run_current_snapshot_eval(snapshot, out_dir=str(tmp_path))

    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    monkeypatch.setenv("APPS_EVAL_RELEASE_GATE", "1")
    with pytest.raises(PermissionError, match="fixture-only"):
        run_eval(
            EvalRequest(suite_id=_SUITE, out_dir=str(tmp_path)),
            snapshot_overrides={"anthropic_deterministic_fixture": snapshot},
        )

@pytest.mark.parametrize(
    "mode,deterministic_only,compare_baseline",
    [
        ("live_adapter", True, False),
        ("snapshot", False, False),
        ("snapshot", True, True),
    ],
)
def test_anthropic_fixture_profile_rejects_disallowed_eval_modes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    mode: str,
    deterministic_only: bool,
    compare_baseline: bool,
) -> None:
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    with pytest.raises(PermissionError, match="fixture-only"):
        run_eval(
            EvalRequest(
                suite_id=_SUITE,
                mode=mode,
                deterministic_only=deterministic_only,
                compare_baseline=compare_baseline,
                out_dir=str(tmp_path),
            ),
            snapshot_overrides={},
        )
