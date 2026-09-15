"""Unit tests for Wave 4: Strict Live Providers & Non-Stub Receipts in ProviderGateway and L2 Envelopes."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from apps_rg.l2_recipe.artifact_assembler import ArtifactAssembler
from apps_rg.runtime.bindings.l2_envelope_adapter import (
    AppsRgEnvelopeProviderResolutionError,
    _provider_profile_for_cpa,
)
from apps_rg.runtime.local_provider import (
    ProviderGateway,
    ProviderKind,
    ProviderMode,
    ProviderModeBlockedError,
    ProviderProfile,
    ProviderRequest,
)
from apps_rg.runtime.providers.provider_run_mode import ProviderRunMode


def test_provider_gateway_rejects_stub_in_live_allowed_mode():
    """Verify ProviderGateway raises ProviderModeBlockedError on stubs when LIVE_ALLOWED."""
    gateway = ProviderGateway(provider_mode=ProviderMode.LIVE_ALLOWED)
    stub_profile = ProviderProfile(
        profile_id="test_stub",
        provider_kind=ProviderKind.STUB,
    )
    request = ProviderRequest(
        request_id="req-123",
        provider_profile=stub_profile,
        prompt_text="Hello world",
    )
    with pytest.raises(ProviderModeBlockedError, match="strictly prohibited when ProviderMode is LIVE_ALLOWED"):
        gateway.invoke(request)


def test_provider_gateway_rejects_stub_in_production_runtime(monkeypatch):
    """Verify ProviderGateway raises ProviderModeBlockedError on stubs during APPS_RG_PRODUCTION_RUN=1."""
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    gateway = ProviderGateway(provider_mode=ProviderMode.STUB_ONLY)
    stub_profile = ProviderProfile(
        profile_id="test_stub",
        provider_kind=ProviderKind.STUB,
    )
    request = ProviderRequest(
        request_id="req-123",
        provider_profile=stub_profile,
        prompt_text="Hello world",
    )
    with pytest.raises(ProviderModeBlockedError, match="strictly prohibited.*during production runtime"):
        gateway.invoke(request)


def test_provider_gateway_allows_stub_in_stub_only_mode(monkeypatch):
    """Verify ProviderGateway allows stubs when mode is STUB_ONLY and not production."""
    monkeypatch.delenv("APPS_RG_PRODUCTION_RUN", raising=False)
    gateway = ProviderGateway(provider_mode=ProviderMode.STUB_ONLY)
    stub_profile = ProviderProfile(
        profile_id="test_stub",
        provider_kind=ProviderKind.STUB,
    )
    request = ProviderRequest(
        request_id="req-123",
        provider_profile=stub_profile,
        prompt_text="Hello world",
    )
    resp = gateway.invoke(request)
    assert resp.success is True
    assert "stub_receipt" in resp.text


def test_cpa_provider_resolution_rejects_unmapped_in_live_required():
    """Verify _provider_profile_for_cpa fails closed on unmapped providers under LIVE_REQUIRED."""
    cpa = SimpleNamespace(target_provider="unmapped_foreign_model", target_model="gpt-4")
    with pytest.raises(AppsRgEnvelopeProviderResolutionError, match="LIVE_REQUIRED"):
        _provider_profile_for_cpa(
            cpa,
            provider_mode=ProviderMode.LIVE_ALLOWED,
            run_mode=ProviderRunMode.LIVE_REQUIRED,
        )


def test_cpa_provider_resolution_rejects_unmapped_in_production(monkeypatch):
    """Verify _provider_profile_for_cpa fails closed on unmapped providers during production."""
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    cpa = SimpleNamespace(target_provider="unmapped_foreign_model", target_model="gpt-4")
    with pytest.raises(AppsRgEnvelopeProviderResolutionError, match="LIVE_REQUIRED"):
        _provider_profile_for_cpa(
            cpa,
            provider_mode=ProviderMode.LIVE_ALLOWED,
            run_mode=ProviderRunMode.LIVE_REQUIRED,
        )


def test_artifact_assembler_rejects_minimal_l2_blob_in_production(monkeypatch):
    """Verify minimal_l2_blob fails closed during production runtime."""
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    monkeypatch.delenv("APPS_RG_TEST_HARNESS", raising=False)
    with pytest.raises(AppsRgEnvelopeProviderResolutionError, match="LIVE_REQUIRED_ENFORCEMENT"):
        ArtifactAssembler.minimal_l2_blob("headline", run_id="test_run")


def test_artifact_assembler_allows_minimal_l2_blob_in_test_harness(monkeypatch):
    """Verify minimal_l2_blob is permitted under APPS_RG_TEST_HARNESS=1."""
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    blob = ArtifactAssembler.minimal_l2_blob("headline", run_id="test_run")
    assert blob["runtime_generation_status"] == "MOCKED"
    assert blob["section_id"] == "headline"
