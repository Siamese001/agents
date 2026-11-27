"""Unit tests for Wave 2: Resume Graph Engine Live Provider & Judge Enforcement."""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

from apps_rg.l2_recipe.resume_generation_contract import MODE_STUB_RECEIPT
from apps_rg.runtime.judges.executive_summary_x1d import run_llm_judges
from apps_rg.runtime.live_judge_only_guard import (
    assert_production_cli_no_mock_judge_flags,
    assert_production_runtime,
)
from apps_rg.runtime.providers.provider_run_mode import (
    AppsRgEnvelopeProviderResolutionError,
    classify_provider_run_mode,
)


def test_classify_provider_rejects_cli_stub_in_production():
    """Verify cli_explicit_stub is rejected outside test harness."""
    with mock.patch("apps_rg.runtime.providers.provider_run_mode._pytest_active", return_value=False):
        with mock.patch("apps_rg.runtime.live_judge_only_guard.is_test_harness", return_value=False):
            with pytest.raises(AppsRgEnvelopeProviderResolutionError, match="cli_explicit_stub is forbidden"):
                classify_provider_run_mode(cli_explicit_stub=True)


def test_classify_provider_rejects_stub_mode_env_in_production():
    """Verify APPS_RG_L2_PROVIDER_MODE=stub is rejected outside test harness."""
    with mock.patch("apps_rg.runtime.providers.provider_run_mode._pytest_active", return_value=False):
        with mock.patch("apps_rg.runtime.live_judge_only_guard.is_test_harness", return_value=False):
            with mock.patch.dict(os.environ, {"APPS_RG_L2_PROVIDER_MODE": "stub"}):
                with pytest.raises(AppsRgEnvelopeProviderResolutionError, match="APPS_RG_L2_PROVIDER_MODE=stub is forbidden"):
                    classify_provider_run_mode()


def test_classify_provider_rejects_stub_contract_in_production():
    """Verify MODE_STUB_RECEIPT contract mode is rejected outside test harness."""
    with mock.patch("apps_rg.runtime.providers.provider_run_mode._pytest_active", return_value=False):
        with mock.patch("apps_rg.runtime.live_judge_only_guard.is_test_harness", return_value=False):
            with pytest.raises(AppsRgEnvelopeProviderResolutionError, match="contract_mode='stub_receipt' is forbidden"):
                classify_provider_run_mode(resume_artifact_contract_mode=MODE_STUB_RECEIPT)


def test_run_llm_judges_rejects_mocked_mode_in_production():
    """Verify run_llm_judges fails closed when mode='mocked' in production."""
    with mock.patch("apps_rg.runtime.judges.executive_summary_x1d._is_test_environment", return_value=False):
        with pytest.raises(RuntimeError, match="MOCK_JUDGE_FORBIDDEN"):
            run_llm_judges(
                resume_display_text="test input",
                claim_ledger=[],
                mode="mocked",
                judge_keys=["openai_chatgpt"],
            )


def test_assert_production_cli_rejects_mock_flags():
    """Verify production CLI rejects --mock-judges flag."""
    with pytest.raises(SystemExit) as exc_info:
        assert_production_cli_no_mock_judge_flags(["python", "-m", "apps_rg", "--mock-judges"])
    assert exc_info.value.code == 2
