"""Compatibility facade re-exporting canonical `infrastructure.sdks_mcps.agy_cli_transport`."""
from __future__ import annotations

import os
import subprocess
from typing import Any

from infrastructure.sdks_mcps import agy_cli_transport as _canonical
from infrastructure.sdks_mcps.agy_cli_transport import (
    AGY_CLI_ENV_VAR,
    AGY_MAX_CONCURRENCY_ENV_VAR,
    AgyQuotaExhaustedError,
    AgyResult,
    AgyTransportError,
    DEFAULT_AGY_MAX_CONCURRENCY,
    KEY_ENV_VARS,
    MAX_PROMPT_CHARS,
    NO_TOOLS_SETTINGS,
    _acquire_cli_slot,
    _parse_quota_cooldown_seconds,
    _ready_cached,
    _verify_banner,
    clear_agy_quota_cooldowns,
    ide_cli_ready,
    is_agy_model_quota_cooled_down,
    is_agy_quota_error,
    mark_agy_model_quota_exhausted,
    parse_models_output,
    parse_stream,
    resolve_agy_bin,
    resolve_agy_max_concurrency,
)


def list_agy_models(
    agy_bin: str | os.PathLike[str] | None = None,
    *,
    timeout_s: int = 30,
) -> list[str]:
    """Delegate to canonical `infrastructure.sdks_mcps.agy_cli_transport.list_agy_models`."""
    return _canonical.list_agy_models(agy_bin=agy_bin, timeout_s=timeout_s, _resolver=resolve_agy_bin)


def run_agy(
    prompt: str,
    *,
    model: str,
    json_schema: dict[str, Any] | None = None,
    effort: str | None = None,
    timeout_s: int = 600,
    agy_bin: str | os.PathLike[str] | None = None,
) -> AgyResult:
    """Delegate to canonical `infrastructure.sdks_mcps.agy_cli_transport.run_agy`."""
    return _canonical.run_agy(
        prompt,
        model=model,
        json_schema=json_schema,
        effort=effort,
        timeout_s=timeout_s,
        agy_bin=agy_bin,
        _resolver=resolve_agy_bin,
    )


__all__ = [
    "AGY_CLI_ENV_VAR",
    "AGY_MAX_CONCURRENCY_ENV_VAR",
    "AgyQuotaExhaustedError",
    "AgyResult",
    "AgyTransportError",
    "DEFAULT_AGY_MAX_CONCURRENCY",
    "KEY_ENV_VARS",
    "MAX_PROMPT_CHARS",
    "NO_TOOLS_SETTINGS",
    "_acquire_cli_slot",
    "_parse_quota_cooldown_seconds",
    "_ready_cached",
    "_verify_banner",
    "clear_agy_quota_cooldowns",
    "ide_cli_ready",
    "is_agy_model_quota_cooled_down",
    "is_agy_quota_error",
    "list_agy_models",
    "mark_agy_model_quota_exhausted",
    "parse_models_output",
    "parse_stream",
    "resolve_agy_bin",
    "resolve_agy_max_concurrency",
    "run_agy",
    "subprocess",
]
