"""Hardened Anthropic executor with resilient client wiring (EX1 / EX2).

RETIRED (Wave 4 SSOT): Direct Anthropic SDK client construction in apps_rg
is retired in favor of the centralized provider gateway and external_provider.
This module is retained as a compatibility stub.

Regression suite: ``tests/unit/apps_rg/enforcement/test_hardened_anthropic_executor_setup.py``.
"""

from __future__ import annotations

import logging
import os
import warnings
from typing import Any

from dotenv import load_dotenv

from apps_rg.runtime.core_mixins import HardeningMixin

load_dotenv()

logger = logging.getLogger(__name__)


class HardenedAnthropicExecutor(HardeningMixin):
    """Retired compatibility executor stub.

    All LLM execution is routed via apps_rg.runtime.providers.
    """

    def __init__(self) -> None:
        super().__init__(component_name="HardenedAnthropicExecutor")
        warnings.warn(
            "HardenedAnthropicExecutor is retired; use apps_rg.runtime.providers.provider_gateway",
            DeprecationWarning,
            stacklevel=2,
        )
        self._client: Any | None = None
        self._setup_client()

    def _setup_client(self) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning(
                "ANTHROPIC_API_KEY not set; anthropic executor has no authenticated client.",
            )
        # Retired: direct SDK instantiation retired in favor of apps_rg provider gateway
        self._client = None
