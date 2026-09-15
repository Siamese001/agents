"""Unit tests for Wave 5: Unified CLI Preflight & Orchestration Hardening."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from agents.live_preflight import (
    assert_engine_live_preflight,
    perform_live_preflight,
)
from infrastructure.live_execution import LiveExecutionError


def test_perform_live_preflight_rejects_mock_flag():
    """Verify live preflight fails closed when APPS_RG_L2_FORCE_STUB=1 is set."""
    with mock.patch.dict(os.environ, {"APPS_RG_L2_FORCE_STUB": "1"}):
        with pytest.raises(LiveExecutionError, match="PROHIBITED_MOCK_ENV"):
            perform_live_preflight(providers=("openai",))


def test_perform_live_preflight_rejects_missing_key():
    """Verify live preflight fails closed when required provider key is missing."""
    with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=True):
        with pytest.raises(LiveExecutionError, match="Missing live API key"):
            perform_live_preflight(providers=("openai",))


def test_perform_live_preflight_succeeds_with_keys():
    """Verify live preflight returns safe key fingerprints when keys exist."""
    openai_key = "sk-real-test-openai-key-54321"  # allow-secret
    with mock.patch.dict(os.environ, {"OPENAI_API_KEY": openai_key, "APPS_RG_L2_FORCE_STUB": ""}):
        fingerprints = perform_live_preflight(providers=("openai",))
        assert "openai" in fingerprints
        assert len(fingerprints["openai"]) == 16


def test_assert_engine_live_preflight_in_production():
    """Verify assert_engine_live_preflight raises in production when mock flags exist."""
    with mock.patch("agents.live_preflight._is_test_mode", return_value=False):
        with mock.patch.dict(os.environ, {"APPS_RG_L2_FORCE_STUB": "1"}):
            with pytest.raises(LiveExecutionError, match="PROHIBITED_MOCK_ENV"):
                assert_engine_live_preflight("agents resume", providers=("openai",))
