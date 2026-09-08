"""Unit tests verifying Wave 3 provider boundary, live judge guard, and concurrency resilience."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps_rg.l2_recipe.modular_resume_generation import (
    _resolve_phase1_lane_provider_route_for_section,
)
from apps_rg.runtime.spine.apps_rg_spine_run import run_apps_rg_spine
from apps_rg.runtime.validators.companion_bullet_finalization import (
    companion_accepted_in_modular_sections_root,
)


def test_protected_claude_lanes_reject_global_openai_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Global APPS_RG_MODULAR_LANE_PROVIDER=external_openai must not override protected Claude lanes."""
    monkeypatch.setenv("APPS_RG_MODULAR_LANE_PROVIDER", "external_openai")

    # Protected proof lanes must remain external_claude
    for protected_lane in ("competencies", "executive_summary"):
        provider, source, _route = _resolve_phase1_lane_provider_route_for_section(
            None, protected_lane
        )
        assert provider == "external_claude", f"{protected_lane} provider must be external_claude"

    # Non-protected lane honors the global override
    narrative_provider, _source, _route = _resolve_phase1_lane_provider_route_for_section(
        None, "unify_narrative"
    )
    assert narrative_provider == "external_openai"


def test_protected_claude_lanes_accept_explicit_claude_override() -> None:
    """Explicitly configured provider is preserved."""
    provider, _source, _route = _resolve_phase1_lane_provider_route_for_section(
        "external_claude", "competencies"
    )
    assert provider == "external_claude"


def test_lane_mock_judges_blocked_without_test_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Invoking run_apps_rg_spine with lane_mock_judges=True outside test harness raises RuntimeError."""
    monkeypatch.delenv("APPS_RG_TEST_HARNESS", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        run_apps_rg_spine(
            scope="section",
            section_id="competencies",
            target_company="Acme Corp",
            target_role="Principal Engineer",
            target_level="IC-6",
            jd="Engineering leadership role",
            manual_brief="Briefing text",
            artifact_dir=str(tmp_path / "art"),
            lane_mock_judges=True,
        )

    assert "MOCK_JUDGE_VIOLATION" in str(exc_info.value)


def test_lane_mock_judges_allowed_in_test_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Invoking run_apps_rg_spine with lane_mock_judges=True inside test harness passes the guard."""
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")

    # Guard should pass without raising MOCK_JUDGE_VIOLATION; mock subsequent single_action execution
    with patch(
        "apps_rg.runtime.orchestration.integrated_spine_runner.run_integrated_single_action_spine",
        return_value=MagicMock(
            fault="",
            exit_status="success",
            l2_result={
                "section_result": {
                    "exit_status": "success",
                    "outcome_authorized": True,
                    "x3_disposition": "X3_ALLOW",
                    "x3_code": "X3_ALLOW",
                }
            },
        ),
    ):
        result = run_apps_rg_spine(
            scope="section",
            section_id="competencies",
            target_company="Acme Corp",
            target_role="Principal Engineer",
            target_level="IC-6",
            jd="Engineering leadership role",
            manual_brief="Briefing text",
            artifact_dir=str(tmp_path / "art_harness"),
            lane_mock_judges=True,
        )

    assert result.get("exit_status") == "success"


def test_companion_accepted_retries_on_transient_missing_file(tmp_path: Path) -> None:
    """Transient empty reads of the upstream pointer recover through the retry window."""
    repo = tmp_path
    sections_root = tmp_path / "sections"
    upstream_dir = sections_root / "ibm_bullets"
    upstream_dir.mkdir(parents=True)

    read_calls = 0

    def mock_read(path: Path) -> dict:
        nonlocal read_calls
        read_calls += 1
        if read_calls == 1:
            return {}  # Simulated transient flush latency
        return {"run_dir": "sections/ibm_bullets/run_001"}

    with patch(
        "apps_rg.runtime.runtime_proof_layout._read_json_dict",
        side_effect=mock_read,
    ), patch(
        "apps_rg.runtime.validators.companion_bullet_finalization.companion_run_dir_accepted",
        return_value=True,
    ):
        accepted = companion_accepted_in_modular_sections_root(
            repo=repo,
            sections_root=sections_root,
            upstream_section_id="ibm_bullets",
            expected_bullet_ids=("B1", "B2"),
        )

    assert accepted is True
    assert read_calls == 2


def test_companion_accepted_returns_false_after_3_failed_attempts(tmp_path: Path) -> None:
    """When upstream pointer never materializes, returns False after 3 attempts."""
    repo = tmp_path
    sections_root = tmp_path / "sections"
    read_calls = 0

    def mock_read(path: Path) -> dict:
        nonlocal read_calls
        read_calls += 1
        return {}

    with patch(
        "apps_rg.runtime.runtime_proof_layout._read_json_dict",
        side_effect=mock_read,
    ):
        accepted = companion_accepted_in_modular_sections_root(
            repo=repo,
            sections_root=sections_root,
            upstream_section_id="ibm_bullets",
            expected_bullet_ids=("B1", "B2"),
        )

    assert accepted is False
    assert read_calls == 3


def test_companion_accepted_returns_false_when_run_dir_missing(tmp_path: Path) -> None:
    """When data has empty or invalid run_dir, returns False."""
    repo = tmp_path
    sections_root = tmp_path / "sections"

    with patch(
        "apps_rg.runtime.runtime_proof_layout._read_json_dict",
        return_value={"run_dir": "   "},
    ):
        accepted = companion_accepted_in_modular_sections_root(
            repo=repo,
            sections_root=sections_root,
            upstream_section_id="ibm_bullets",
            expected_bullet_ids=("B1", "B2"),
        )

    assert accepted is False


def test_companion_accepted_retries_and_fails_if_companion_not_accepted(tmp_path: Path) -> None:
    """When companion_run_dir_accepted returns False, all 3 retry attempts are exhausted."""
    repo = tmp_path
    sections_root = tmp_path / "sections"
    read_calls = 0

    def mock_read(path: Path) -> dict:
        nonlocal read_calls
        read_calls += 1
        return {"run_dir": "sections/ibm_bullets/run_rejected"}

    with patch(
        "apps_rg.runtime.runtime_proof_layout._read_json_dict",
        side_effect=mock_read,
    ), patch(
        "apps_rg.runtime.validators.companion_bullet_finalization.companion_run_dir_accepted",
        return_value=False,
    ):
        accepted = companion_accepted_in_modular_sections_root(
            repo=repo,
            sections_root=sections_root,
            upstream_section_id="ibm_bullets",
            expected_bullet_ids=("B1", "B2"),
        )

    assert accepted is False
    assert read_calls == 3


def test_resolve_phase1_lane_provider_route_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no provider override is configured, protected lanes resolve to external_claude dev_default."""
    monkeypatch.delenv("APPS_RG_MODULAR_LANE_PROVIDER", raising=False)

    provider, source, _route = _resolve_phase1_lane_provider_route_for_section(
        None, "competencies"
    )
    assert provider == "external_claude"
    assert "default" in source.lower()
