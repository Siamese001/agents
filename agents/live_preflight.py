"""Unified preflight validator for live LLM execution across all engines."""

from __future__ import annotations

import os
import sys
from typing import Sequence

from infrastructure.live_execution import (
    LiveExecutionError,
    load_agent_environment,
    require_live_pipeline,
)


def _is_test_mode() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST") or ("pytest" in sys.modules):
        return True
    return os.environ.get("APPS_RG_TEST_HARNESS") == "1"


def perform_live_preflight(
    providers: Sequence[str] = ("openai", "anthropic", "google"),
) -> dict[str, str]:
    """Execute fail-closed credential and mock flag validation before running engine pipelines.

    Returns:
        Mapping of provider -> safe key fingerprint (for audit logging, never raw keys).
    """
    load_agent_environment()
    return require_live_pipeline(providers)


def assert_engine_live_preflight(
    engine: str,
    providers: Sequence[str] = ("openai", "anthropic", "google"),
    *,
    is_demo: bool = False,
) -> dict[str, str]:
    """Validate live posture for CLI command invocation.

    In test environments (pytest or APPS_RG_TEST_HARNESS=1), validation is bypassed.
    In production environments, any missing credential or mock flag raises LiveExecutionError.
    """
    if _is_test_mode():
        return {}
    if is_demo:
        # Canonical demo can run with single provider or existing keys
        providers = ("openai",)
    try:
        return perform_live_preflight(providers=providers)
    except LiveExecutionError as exc:
        sys.stderr.write(f"\n[FATAL] Live Execution Preflight Failed for '{engine}':\n  {exc}\n\n")
        raise
