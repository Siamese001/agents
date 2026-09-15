"""Comprehensive End-to-End Live LLM Enforcement & Mock Elimination Test Suite."""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

from agents.live_preflight import assert_engine_live_preflight, perform_live_preflight
from apps_lic.integrations.apps_research_bridge import MockAppsResearchBridge
from apps_research.engines.research_retrieval_engine import InMemoryResearchStore
from apps_rg.l2_recipe.resume_generation_contract import MODE_STUB_RECEIPT
from apps_rg.runtime.judges.executive_summary_x1d import run_llm_judges
from apps_rg.runtime.live_judge_only_guard import (
    assert_production_cli_no_mock_judge_flags,
)
from apps_rg.runtime.providers.provider_run_mode import (
    AppsRgEnvelopeProviderResolutionError,
    classify_provider_run_mode,
)
from infrastructure.live_execution import (
    LiveExecutionError,
    api_key,
    key_fingerprint,
    reject_mock_environment,
    require_live_pipeline,
)


class TestWave1UnifiedCredentials:
    """Test Wave 1: Centralized credential resolution and mock environment detection."""

    def test_live_keys_load_successfully(self):
        openai_key = "sk-real-valid-key-openai-12345"  # allow-secret
        ant_key = "sk-ant-real-valid-key-54321"  # allow-secret
        goog_key = "AIzaSyRealGoogleKey67890"  # allow-secret
        env = {
            "OPENAI_API_KEY": openai_key,
            "ANTHROPIC_API_KEY": ant_key,
            "GOOGLE_API_KEY": goog_key,
        }
        assert api_key("openai", environ=env) == openai_key
        assert api_key("anthropic", environ=env) == ant_key
        assert api_key("google", environ=env) == goog_key
        assert api_key("gemini", environ=env) == goog_key

    def test_rejects_placeholder_credentials(self):
        for dummy in ("", "dummy", "fake", "placeholder", "sk-local-dev-key", "none", "null"):
            with pytest.raises(LiveExecutionError):
                api_key("openai", environ={"OPENAI_API_KEY": dummy})

    def test_rejects_mock_flags(self):
        for flag in ("APPS_RG_L2_FORCE_STUB", "APPS_RG_ALLOW_SINGLE_PATH_SELECTOR_BYPASS", "APPS_RG_MOCK_JUDGES"):
            with pytest.raises(LiveExecutionError, match="PROHIBITED_MOCK_ENV"):
                reject_mock_environment(environ={flag: "1"})

    def test_rejects_stub_provider_mode(self):
        with pytest.raises(LiveExecutionError, match="requests non-live execution"):
            reject_mock_environment(environ={"APPS_RG_L2_PROVIDER_MODE": "stub"})


class TestWave2ResumeEngineEnforcement:
    """Test Wave 2: Resume Graph Engine provider and judge live enforcement."""

    def test_classify_provider_forbids_cli_stub(self):
        with mock.patch("apps_rg.runtime.providers.provider_run_mode._pytest_active", return_value=False):
            with mock.patch("apps_rg.runtime.live_judge_only_guard.is_test_harness", return_value=False):
                with pytest.raises(AppsRgEnvelopeProviderResolutionError, match="cli_explicit_stub is forbidden"):
                    classify_provider_run_mode(cli_explicit_stub=True)

    def test_classify_provider_forbids_stub_contract(self):
        with mock.patch("apps_rg.runtime.providers.provider_run_mode._pytest_active", return_value=False):
            with mock.patch("apps_rg.runtime.live_judge_only_guard.is_test_harness", return_value=False):
                with pytest.raises(AppsRgEnvelopeProviderResolutionError, match="contract_mode='stub_receipt' is forbidden"):
                    classify_provider_run_mode(resume_artifact_contract_mode=MODE_STUB_RECEIPT)

    def test_run_llm_judges_forbids_mocked_in_production(self):
        with mock.patch("apps_rg.runtime.judges.executive_summary_x1d._is_test_environment", return_value=False):
            with pytest.raises(RuntimeError, match="MOCK_JUDGE_FORBIDDEN"):
                run_llm_judges(
                    resume_display_text="Candidate Profile Text",
                    claim_ledger=[],
                    mode="mocked",
                    judge_keys=["openai_chatgpt"],
                )

    def test_cli_flags_reject_mock_judges(self):
        with pytest.raises(SystemExit) as exc:
            assert_production_cli_no_mock_judge_flags(["python", "-m", "apps_rg", "--mock-judges"])
        assert exc.value.code == 2


class TestWave3ResearchEngineEnforcement:
    """Test Wave 3: Research Engine live embedding and source discovery."""

    def test_research_store_requires_live_embedding(self):
        store = InMemoryResearchStore()
        with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "", "APPS_RG_TEST_HARNESS": ""}):
            with mock.patch("sys.modules", {k: v for k, v in sys.modules.items() if k != "pytest"}):
                with mock.patch("infrastructure.live_execution.api_key", side_effect=Exception("Missing live key")):
                    with pytest.raises(RuntimeError, match="LIVE_EMBEDDING_REQUIRED"):
                        store._mock_embed("test text")


class TestWave4OutreachEngineEnforcement:
    """Test Wave 4: Outreach Engine live bridge and generation enforcement."""

    def test_mock_research_bridge_forbidden_in_production(self):
        with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "", "APPS_RG_TEST_HARNESS": ""}):
            with mock.patch("sys.modules", {k: v for k, v in sys.modules.items() if k != "pytest"}):
                with pytest.raises(RuntimeError, match="MOCK_BRIDGE_FORBIDDEN"):
                    MockAppsResearchBridge()


class TestWave5UnifiedCLIPreflight:
    """Test Wave 5: Unified CLI preflight validation across all platforms."""

    def test_preflight_validates_pipeline(self):
        env = {
            "OPENAI_API_KEY": "sk-valid-key-openai-99999",  # allow-secret
            "ANTHROPIC_API_KEY": "sk-ant-valid-key-88888",  # allow-secret
            "GOOGLE_API_KEY": "AIzaSyValidKey77777",  # allow-secret
        }
        with mock.patch.dict(os.environ, env):
            fps = perform_live_preflight(providers=("openai", "anthropic", "google"))
            assert len(fps) == 3
            assert all(len(v) == 16 for v in fps.values())
