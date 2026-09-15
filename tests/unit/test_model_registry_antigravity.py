"""Rigorous test suite for Model Registry and Antigravity IDE execution.

Verifies:
1. When no model is specified, execution runs in Antigravity IDE hermetically with NO API key required.
2. Provider boundary strictly fails closed when unauthenticated live external calls are attempted without an API key.
3. Model registry enforces capability-only metadata (routing_allowed=False) and parameter immunity for reasoning models.
4. Operator-specified 'gpt-astra-6' is validated, rejected from unapproved catalogs, and banned from default fallback tiers.
5. Model-neutral naming linter flags proprietary tokens including 'astra'.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "resume_graph_engine" / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "resume_graph_engine" / "src"))

from agents.context.provenance import ContextItem, ContextSnapshot, ContextSourceType
from agents.gateway.contracts import CapabilityRequest, ModelTier
from agents.gateway.model_gateway import ModelCapabilityGateway
from apps_rg.bare_pipeline import run_bare_deterministic_e2e
from apps_rg.runtime.local_provider import (
    ProviderGateway,
    ProviderKind,
    ProviderMode,
    ProviderModeBlockedError,
    ProviderProfile,
    ProviderRequest,
)
from apps_rg.runtime.model_capabilities import (
    ModelCapabilityError,
    model_capabilities,
)
from infrastructure.live_execution import (
    LiveExecutionError,
    api_key,
    reject_mock_environment,
)
from infrastructure.sdks_mcps.client_wrappers import (
    create_local_openai_client,
    create_openai_client,
    create_openai_sync_client,
)
from tools.config_ssot_agent.registry import SSOTRegistry
from tools.lint_model_neutral_naming import check_path_model_neutrality


# -----------------------------------------------------------------------------
# 1. Antigravity IDE Execution When No Model Is Specified (No API Key)
# -----------------------------------------------------------------------------

def test_antigravity_ide_default_execution_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that when no model is specified, execution runs on Antigravity IDE with no API key."""
    # Ensure all provider API keys are stripped from environment and disk reload is disabled
    monkeypatch.setattr("infrastructure.live_execution.load_agent_environment", lambda *a, **kw: None)
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    gateway = ModelCapabilityGateway()
    item = ContextItem(
        source_id="req-ide-prompt",
        source_type=ContextSourceType.REQUEST,
        content="Evaluate default model registry behavior in Antigravity IDE",
    )
    snapshot = ContextSnapshot(
        snapshot_id="snap-ide-001",
        items=(item,),
        max_token_budget=1000,
    )
    request = CapabilityRequest(
        capability_name="antigravity_ide_task",
        prompt_snapshot=snapshot,
        model_tier=ModelTier.REASONING,
    )

    response = gateway.execute(request)

    assert response.status == "SUCCESS"
    assert response.provider == "simulated_default"
    assert response.model_id == "simulated-v1"
    assert "Simulated execution for capability 'antigravity_ide_task'" in response.content
    assert len(response.observation_digest) == 64
    assert response.is_success is True


def test_antigravity_bare_deterministic_pipeline_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that apps_rg deterministic pipeline executes 11 stages hermetically without any API keys."""
    monkeypatch.setattr("infrastructure.live_execution.load_agent_environment", lambda *a, **kw: None)
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    result = run_bare_deterministic_e2e()

    assert result.get("status") == "SUCCESS"
    assert result.get("outcome_label") == "DETERMINISTIC_OFFLINE_PASS"
    assert "run_id" in result
    assert len(result.get("stages", [])) == 11


def test_provider_gateway_allows_stubs_in_stub_only_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ProviderGateway executes hermetic stubs when in STUB_ONLY mode without API keys."""
    monkeypatch.delenv("APPS_RG_PRODUCTION_RUN", raising=False)
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    gateway = ProviderGateway(provider_mode=ProviderMode.STUB_ONLY)
    profile = ProviderProfile(profile_id="ide_hermetic_stub", provider_kind=ProviderKind.STUB)
    req = ProviderRequest(
        request_id="req-ide-001",
        provider_profile=profile,
        prompt_text="Hermetic prompt",
    )
    resp = gateway.invoke(req)

    assert resp.success is True
    assert "stub_receipt" in resp.text


# -----------------------------------------------------------------------------
# 2. Strict Fail-Closed Boundary When Live Calls Lack API Keys
# -----------------------------------------------------------------------------

def test_api_key_fails_closed_when_keys_missing() -> None:
    """Verify that calling live providers without an API key strictly raises LiveExecutionError."""
    clean_env: dict[str, str] = {}
    for provider in ("openai", "anthropic", "gemini", "google"):
        with pytest.raises(LiveExecutionError, match="LIVE_CREDENTIAL_ERROR"):
            api_key(provider, environ=clean_env)


def test_api_key_rejects_placeholder_and_dummy_keys() -> None:
    """Verify that placeholder/dummy keys are rejected and never treated as valid credentials."""
    for bad_key in ("", "dummy", "fake", "test-key", "placeholder", "sk-local-dev-key", "null"):
        with pytest.raises(LiveExecutionError, match="LIVE_CREDENTIAL_ERROR"):
            api_key("openai", environ={"OPENAI_API_KEY": bad_key})


def test_client_wrappers_fail_closed_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify SDK client wrapper factories fail closed immediately without live credentials."""
    monkeypatch.setattr("infrastructure.live_execution.load_agent_environment", lambda *a, **kw: None)
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(LiveExecutionError, match="LIVE_CREDENTIAL_ERROR"):
        create_openai_client()

    with pytest.raises(LiveExecutionError, match="LIVE_CREDENTIAL_ERROR"):
        create_openai_sync_client()

    for provider in ("anthropic", "gemini", "google"):
        with pytest.raises(LiveExecutionError, match="LIVE_CREDENTIAL_ERROR"):
            api_key(provider)

    monkeypatch.delenv("LOCAL_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_OPENAI_BASE_URL", raising=False)
    with pytest.raises(LiveExecutionError, match="LOCAL_PROVIDER_ERROR"):
        create_local_openai_client()


def test_provider_gateway_blocks_stubs_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ProviderGateway strictly blocks stubs when APPS_RG_PRODUCTION_RUN=1."""
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    gateway = ProviderGateway(provider_mode=ProviderMode.STUB_ONLY)
    profile = ProviderProfile(profile_id="stub_profile", provider_kind=ProviderKind.STUB)
    req = ProviderRequest(
        request_id="req-prod-001",
        provider_profile=profile,
        prompt_text="Live task",
    )
    with pytest.raises(ProviderModeBlockedError, match="strictly prohibited.*during production runtime"):
        gateway.invoke(req)


# -----------------------------------------------------------------------------
# 3. Model Registry Capabilities & Parameter Immunity
# -----------------------------------------------------------------------------

def test_model_catalog_metadata_only_invariant() -> None:
    """Verify model catalog is strictly capability metadata with routing_allowed=False."""
    catalog_path = ROOT / "resume_graph_engine" / "config" / "model_catalog.json"
    data = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert data.get("schema_version") == "model_capability_catalog.v3"
    assert data.get("catalog_role") == "capability_metadata_only"
    assert data.get("routing_allowed") is False


def test_model_capabilities_registered_models_and_parameter_immunity() -> None:
    """Verify registered models enforce parameter immunity (temperature_parameter=omit)."""
    reasoning_models = ["gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra"]
    for mid in reasoning_models:
        caps = model_capabilities(mid)
        assert caps.provider == "openai"
        assert caps.temperature_parameter == "omit"
        assert caps.structured_output is True
        assert caps.supports_endpoint("responses")
        assert caps.supports_endpoint("chat_completions")


# -----------------------------------------------------------------------------
# 4. Rigorous Testing of 'gpt-astra-6' Handling
# -----------------------------------------------------------------------------

def test_gpt_astra_6_rejected_from_model_capabilities() -> None:
    """Verify that unapproved model 'gpt-astra-6' fails closed with MODEL_CAPABILITY_NOT_REGISTERED."""
    with pytest.raises(ModelCapabilityError, match="MODEL_CAPABILITY_NOT_REGISTERED: gpt-astra-6"):
        model_capabilities("gpt-astra-6")

    with pytest.raises(ModelCapabilityError, match="MODEL_CAPABILITY_NOT_REGISTERED: gpt-6-astra"):
        model_capabilities("gpt-6-astra")


def test_gpt_astra_6_banned_from_default_registry_catalogs() -> None:
    """Verify that 'gpt-astra-6' and 'gpt-6-astra' are excluded from default model tiers."""
    catalog_path = ROOT / "config" / "model_catalog.json"
    if catalog_path.is_file():
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        default_model = data.get("openai", {}).get("default")
        assert default_model != "gpt-astra-6"
        assert default_model != "gpt-6-astra"

    rg_catalog_path = ROOT / "resume_graph_engine" / "config" / "model_catalog.json"
    rg_data = json.loads(rg_catalog_path.read_text(encoding="utf-8"))
    registered = set(rg_data.get("models", {}).keys())
    assert "gpt-astra-6" not in registered
    assert "gpt-6-astra" not in registered


def test_model_neutral_naming_prohibits_astra_token() -> None:
    """Verify lint_model_neutral_naming flags paths containing 'astra'."""
    violating_path = Path("reports/gpt_astra_6_evaluation.md")
    violations = check_path_model_neutrality(violating_path, ROOT)
    assert len(violations) > 0
    assert any("astra" in v.lower() for v in violations)

    violating_plan = Path("plans/astra_latency_optimization.md")
    violations_plan = check_path_model_neutrality(violating_plan, ROOT)
    assert len(violations_plan) > 0
