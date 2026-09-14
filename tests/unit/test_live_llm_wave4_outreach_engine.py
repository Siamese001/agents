"""Unit tests for Wave 4: Outreach Engine Live Bridge & Generation Enforcement."""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

from apps_lic.integrations.apps_research_bridge import MockAppsResearchBridge


def test_mock_apps_research_bridge_fails_in_production():
    """Verify MockAppsResearchBridge fails closed in production runtime."""
    with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "", "APPS_RG_TEST_HARNESS": ""}):
        with mock.patch("sys.modules", {k: v for k, v in sys.modules.items() if k != "pytest"}):
            with pytest.raises(RuntimeError, match="MOCK_BRIDGE_FORBIDDEN"):
                MockAppsResearchBridge()
