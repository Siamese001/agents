"""W3 — Phase-1 ``lane_allow_non_allow_exit_zero`` parity with section CLI."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch
from tests.helpers.standalone_repo_view import materialize_standalone_repo_view

import pytest

from apps_rg.l2_recipe.modular_resume_generation import (
    ModularResumeInputPackage,
    ModularResumeProfile,
    run_modular_resume_generation,
)
from apps_rg.l2_recipe.steps import _phase1_allow_flag_from_recipe_context
from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.section_cli_defaults import resolve_phase1_lane_allow_non_allow_exit_zero


def test_phase1_allow_flag_from_recipe_context_keys_and_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPS_RG_ALLOW_NON_ALLOW_EXIT_ZERO", raising=False)
    assert _phase1_allow_flag_from_recipe_context({}) is False
    assert _phase1_allow_flag_from_recipe_context({"allow_non_allow_exit_zero": True}) is True
    assert _phase1_allow_flag_from_recipe_context({"lane_allow_non_allow_exit_zero": True}) is True
    monkeypatch.setenv("APPS_RG_ALLOW_NON_ALLOW_EXIT_ZERO", "1")
    assert _phase1_allow_flag_from_recipe_context({}) is True


@pytest.mark.parametrize(
    "env_val",
    ["yes", "TRUE", "on", "Y"],
)
def test_phase1_allow_flag_truthy_env_variants(
    monkeypatch: pytest.MonkeyPatch,
    env_val: str,
) -> None:
    monkeypatch.delenv("APPS_RG_ALLOW_NON_ALLOW_EXIT_ZERO", raising=False)
    monkeypatch.setenv("APPS_RG_ALLOW_NON_ALLOW_EXIT_ZERO", env_val)
    assert _phase1_allow_flag_from_recipe_context({}) is True


def test_phase1_allow_flag_false_for_empty_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPS_RG_ALLOW_NON_ALLOW_EXIT_ZERO", "  ")
    assert _phase1_allow_flag_from_recipe_context({}) is False


def test_resolve_phase1_lane_allow_denied_on_product_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPS_RG_TEST_HARNESS", raising=False)
    monkeypatch.delenv("APPS_RG_ALLOW_PRODUCT_SHORTCUTS", raising=False)
    monkeypatch.setenv("APPS_RG_ALLOW_NON_ALLOW_EXIT_ZERO", "1")
    assert resolve_phase1_lane_allow_non_allow_exit_zero(True) is False
    assert resolve_phase1_lane_allow_non_allow_exit_zero(False) is False


def test_phase1_dispatch_passes_lane_allow_when_harness_and_profile_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    captured: list[dict[str, object]] = []

    def _stub_lane_dispatch(**kwargs: object) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {"exit_status": "success", "fault": ""}

    repo = materialize_standalone_repo_view(tmp_path)
    art = repo / f"phase1_allow_{uuid.uuid4().hex[:10]}"
    art.mkdir(parents=True, exist_ok=True)

    with patch(
        "apps_rg.l2_recipe.modular_resume_generation.run_canonical_apps_rg_from_cli_primitives",
        side_effect=_stub_lane_dispatch,
    ):
        run_modular_resume_generation(
            ModularResumeInputPackage(repo_root=repo),
            art,
            "pytest_allow_true",
            ModularResumeProfile(
                phase1_invoke_real_lanes=True,
                phase1_allow_non_allow_exit_zero=True,
                run_phase0_synthetic_assembly=False,
                validate_rg_output_fixture=False,
            ),
        )

    assert captured, "expected at least one phase-1 dispatch"
    assert all(c.get("lane_allow_non_allow_exit_zero") is True for c in captured)

    inv_path = art / "modular_r4" / "phase1_lane_inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    assert inv.get("phase1_allow_non_allow_exit_zero_effective") is True


def test_phase1_dispatch_lane_allow_false_on_product_despite_profile_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("APPS_RG_TEST_HARNESS", raising=False)
    monkeypatch.delenv("APPS_RG_ALLOW_PRODUCT_SHORTCUTS", raising=False)
    monkeypatch.setenv("APPS_RG_ALLOW_NON_ALLOW_EXIT_ZERO", "1")
    captured: list[dict[str, object]] = []

    def _stub_lane_dispatch(**kwargs: object) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {"exit_status": "success", "fault": ""}

    repo = materialize_standalone_repo_view(tmp_path)
    art = repo / f"phase1_allow_{uuid.uuid4().hex[:10]}"
    art.mkdir(parents=True, exist_ok=True)

    with patch(
        "apps_rg.l2_recipe.modular_resume_generation.run_canonical_apps_rg_from_cli_primitives",
        side_effect=_stub_lane_dispatch,
    ):
        run_modular_resume_generation(
            ModularResumeInputPackage(repo_root=repo),
            art,
            "pytest_allow_false",
            ModularResumeProfile(
                phase1_invoke_real_lanes=True,
                phase1_allow_non_allow_exit_zero=True,
                run_phase0_synthetic_assembly=False,
                validate_rg_output_fixture=False,
            ),
        )

    assert captured, "expected at least one phase-1 dispatch"
    assert all(c.get("lane_allow_non_allow_exit_zero") is False for c in captured)

    inv_path = art / "modular_r4" / "phase1_lane_inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    assert inv.get("phase1_allow_non_allow_exit_zero_effective") is False


def test_parallel_phase1_whole_run_uses_certified_dependency_scheduler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The whole-run seam supplies the app acceptance gate to the rolling L3 scheduler."""
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    captured: list[str] = []

    def _stub_lane_dispatch(**kwargs: object) -> dict[str, object]:
        lane = str(kwargs.get("section") or "")
        captured.append(lane)
        return {"section": lane, "exit_status": "success", "fault": ""}

    repo = materialize_standalone_repo_view(tmp_path)
    art = repo / f"phase1_parallel_{uuid.uuid4().hex[:10]}"
    art.mkdir(parents=True, exist_ok=True)

    with (
        patch(
            "apps_rg.l2_recipe.modular_resume_generation.run_canonical_apps_rg_from_cli_primitives",
            side_effect=_stub_lane_dispatch,
        ),
        patch(
            "apps_rg.runtime.validators.companion_bullet_finalization.companion_accepted_in_modular_sections_root",
            return_value=True,
        ),
    ):
        run_modular_resume_generation(
            ModularResumeInputPackage(repo_root=repo),
            art,
            "pytest_parallel_phase1",
            ModularResumeProfile(
                phase1_invoke_real_lanes=True,
                parallel_phase1_lanes=True,
                phase1_max_parallel=5,
                run_phase0_synthetic_assembly=False,
                validate_rg_output_fixture=False,
            ),
        )

    assert set(captured) == set(GENERATED_LANES)
    inv_path = art / "modular_r4" / "phase1_lane_inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    assert inv.get("phase1_parallel_enabled") is True
    assert inv.get("phase1_max_parallel") == 5
