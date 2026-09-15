"""End-to-End Live LLM Enforcement & Mock Elimination Verification Suite."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from agents.live_preflight import (
    assert_engine_live_preflight,
    perform_live_preflight,
)
from apps_rg.runtime.assembly.full_resume_llm_coherence import (
    run_full_resume_coherence_judges,
)
from apps_rg.runtime.local_provider import (
    ProviderGateway,
    ProviderKind,
    ProviderMode,
    ProviderModeBlockedError,
    ProviderProfile,
    ProviderRequest,
)
from infrastructure.live_execution import (
    LiveExecutionError,
    require_live_pipeline,
)
from tools.audit_mock_reachability import run_audit


def test_audit_mock_reachability_zero_violations():
    """Verify that tools/audit_mock_reachability.py detects zero violations in production."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    code, violations = run_audit(repo_root)
    assert code == 0, f"Found mock reachability violations: {violations}"
    assert len(violations) == 0


def test_full_resume_llm_coherence_blocks_mocked_in_production():
    """Verify full_resume_llm_coherence blocks mode='mocked' when in production runtime."""
    with mock.patch("apps_rg.runtime.assembly.full_resume_llm_coherence._is_test_environment", return_value=False):
        with pytest.raises(RuntimeError, match="MOCK_JUDGE_FORBIDDEN"):
            run_full_resume_coherence_judges(
                full_resume_text="Candidate text",
                target_company="Acme",
                target_role="VP Eng",
                judge_roster=["openai_chatgpt"],
                mode="mocked",
            )


def test_e2e_preflight_validates_env_agents_credentials():
    """Verify perform_live_preflight validates required live keys and returns fingerprints."""
    env = {
        "OPENAI_API_KEY": "sk-real-openai-live-key-99999",  # allow-secret
        "ANTHROPIC_API_KEY": "sk-ant-real-live-key-88888",  # allow-secret
        "GOOGLE_API_KEY": "AIzaSyRealGoogleKey-77777",  # allow-secret
    }
    with mock.patch.dict(os.environ, env):
        fingerprints = perform_live_preflight(providers=("openai", "anthropic", "google"))
        assert len(fingerprints) == 3
        assert fingerprints["openai"]
        assert fingerprints["anthropic"]
        assert fingerprints["google"]

    # Verify fail-closed when a key is missing
    with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=True):
        with pytest.raises(LiveExecutionError, match="Missing live API key"):
            perform_live_preflight(providers=("openai",))


def test_cli_runner_rejects_mock_flags():
    """Verify CLI preflight rejects prohibited mock flags."""
    with mock.patch("agents.live_preflight._is_test_mode", return_value=False):
        for prohibited_flag in (
            "APPS_RG_L2_FORCE_STUB",
            "APPS_RG_ALLOW_SINGLE_PATH_SELECTOR_BYPASS",
            "APPS_RG_MOCK_JUDGES",
        ):
            with mock.patch.dict(os.environ, {prohibited_flag: "1"}):
                with pytest.raises(LiveExecutionError, match="PROHIBITED_MOCK_ENV"):
                    assert_engine_live_preflight("agents resume", providers=("openai",))


def test_provider_gateway_blocks_stub_in_live_allowed_mode():
    """Verify ProviderGateway blocks stub invocations in LIVE_ALLOWED mode."""
    gateway = ProviderGateway(provider_mode=ProviderMode.LIVE_ALLOWED)
    stub_profile = ProviderProfile(
        profile_id="test_stub",
        provider_kind=ProviderKind.STUB,
    )
    request = ProviderRequest(
        request_id="req-live-e2e-1",
        provider_profile=stub_profile,
        prompt_text="Analyze executive resume",
    )
    with pytest.raises(ProviderModeBlockedError, match="strictly prohibited when ProviderMode is LIVE_ALLOWED"):
        gateway.invoke(request)
