"""Unit tests for Wave 3: Research Engine Live Retrieval & Synthesis Enforcement."""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

from apps_research.engines.research_retrieval_engine import InMemoryResearchStore
from apps_research.reasoning.enterprise_research_orchestrator import (
    EnterpriseResearchOrchestrator,
)
from apps_research.services.source_discovery_service import SourceDiscoveryService


def test_in_memory_research_store_rejects_mock_embed_in_production():
    """Verify InMemoryResearchStore._mock_embed fails closed in production."""
    store = InMemoryResearchStore()
    with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "", "APPS_RG_TEST_HARNESS": ""}):
        with mock.patch("sys.modules", {k: v for k, v in sys.modules.items() if k != "pytest"}):
            with mock.patch("infrastructure.live_execution.api_key", side_effect=Exception("Missing key")):
                with pytest.raises(RuntimeError, match="LIVE_EMBEDDING_REQUIRED"):
                    store._mock_embed("test research content")


import asyncio


def test_orchestrator_validate_rejects_missing_content_in_production():
    """Verify _step_validate fails closed when real content/sources are missing in production."""
    with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "", "APPS_RG_TEST_HARNESS": ""}):
        with mock.patch("sys.modules", {k: v for k, v in sys.modules.items() if k != "pytest"}):
            orch = object.__new__(EnterpriseResearchOrchestrator)
            with pytest.raises(RuntimeError, match="LIVE_VALIDATION_ERROR"):
                asyncio.run(
                    orch._step_validate(
                        topic="test topic",
                        artifact_mode="brief",
                        generated_content=None,
                        generated_sources=None,
                    )
                )


def test_source_discovery_rejects_mock_discovery_in_production():
    """Verify discover_sources fails closed when seed_urls is missing in production."""
    service = SourceDiscoveryService()
    with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "", "APPS_RG_TEST_HARNESS": ""}):
        with mock.patch("sys.modules", {k: v for k, v in sys.modules.items() if k != "pytest"}):
            with pytest.raises(RuntimeError, match="LIVE_SOURCE_DISCOVERY_REQUIRED"):
                service.discover_sources(query="test query", seed_urls=None)
