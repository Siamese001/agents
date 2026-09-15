"""Unit tests for Wave 1: Live Execution Policy & Credential Enforcement."""

from __future__ import annotations

import pytest

from infrastructure.live_execution import (
    LiveExecutionError,
    api_key,
    key_fingerprint,
    reject_mock_environment,
    require_live_pipeline,
)
from infrastructure.sdks_mcps.client_wrappers import (
    create_local_openai_client,
    create_local_openai_sync_client,
)


def test_api_key_resolution_success():
    """Verify api_key successfully resolves configured providers."""
    openai_key = "live-sample-openai-credential-12345"
    ant_key = "live-sample-anthropic-credential-12345"
    goog_key = "live-sample-google-credential-12345"
    mock_env = {
        "OPENAI_API_KEY": openai_key,
        "ANTHROPIC_API_KEY": ant_key,
        "GOOGLE_API_KEY": goog_key,
    }
    assert api_key("openai", environ=mock_env) == openai_key
    assert api_key("anthropic", environ=mock_env) == ant_key
    assert api_key("gemini", environ=mock_env) == goog_key
    assert api_key("google", environ=mock_env) == goog_key


def test_api_key_rejects_placeholders():
    """Verify api_key rejects placeholders, dummy values, and local dev keys."""
    for placeholder in ("", "dummy", "fake", "placeholder", "sk-local-dev-key", "null", "none"):
        mock_env = {"OPENAI_API_KEY": placeholder}
        with pytest.raises(LiveExecutionError):
            api_key("openai", environ=mock_env)


def test_reject_mock_environment():
    """Verify reject_mock_environment flags forbidden mock configuration."""
    clean_env = {}
    reject_mock_environment(environ=clean_env)

    # Forbidden mock flags
    with pytest.raises(LiveExecutionError):
        reject_mock_environment(environ={"APPS_RG_L2_FORCE_STUB": "1"})

    with pytest.raises(LiveExecutionError):
        reject_mock_environment(environ={"APPS_RG_MOCK_JUDGES": "true"})

    with pytest.raises(LiveExecutionError):
        reject_mock_environment(environ={"APPS_RG_L2_PROVIDER_MODE": "stub"})


def test_key_fingerprint_deterministic():
    """Verify fingerprint is consistent and non-leaking."""
    key = "live-sample-fingerprint-key-99999"
    fp1 = key_fingerprint(key)
    fp2 = key_fingerprint(key)
    assert fp1 == fp2
    assert len(fp1) == 16
    assert "test" not in fp1


def test_local_client_requires_explicit_configuration(monkeypatch):
    """Verify local client creation fails if local endpoint/key is not explicitly set."""
    monkeypatch.delenv("LOCAL_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_OPENAI_BASE_URL", raising=False)

    with pytest.raises(LiveExecutionError):
        create_local_openai_client()

    with pytest.raises(LiveExecutionError):
        create_local_openai_sync_client()
