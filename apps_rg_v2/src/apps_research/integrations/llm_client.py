"""Standalone LLM client adapter for ``apps_research``.

The monorepo implementation delegated these factories to
``infrastructure.sdks_mcps``.  That package is intentionally outside this
standalone repository, so the adapter owns the same small, fail-closed API-key
contract locally and imports the optional SDK only when a client is requested.
"""
from __future__ import annotations

import os


_DEFAULT_OPENAI_TIMEOUT_SECONDS = 120.0
_OPENAI_MAX_RETRIES = 1


def _required_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY missing")
    return api_key


def _openai_timeout_seconds() -> float:
    """Return a bounded timeout for the governed company-brief lane.

    The approved provider profile declares a 120-second capacity timeout.  The
    SDK client must receive an explicit timeout too; otherwise a stalled
    transport can outlive the governed run and leave no terminal receipt.
    """

    raw = os.getenv("APPS_RESEARCH_OPENAI_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_OPENAI_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_OPENAI_TIMEOUT_SECONDS
    return min(600.0, max(5.0, value))


def create_openai_client():
    """Create an asynchronous OpenAI client without a monorepo dependency."""
    import openai

    return openai.AsyncOpenAI(
        api_key=_required_api_key(),
        timeout=_openai_timeout_seconds(),
        max_retries=_OPENAI_MAX_RETRIES,
    )


def create_openai_sync_client():
    """Create a synchronous OpenAI client without a monorepo dependency."""
    import openai

    return openai.OpenAI(
        api_key=_required_api_key(),
        timeout=_openai_timeout_seconds(),
        max_retries=_OPENAI_MAX_RETRIES,
    )


class OpenAIClient:
    """Compatibility marker retained for the historical adapter surface."""


class OpenAIConfig:
    """Compatibility marker retained for the historical adapter surface."""

# Re-export openai module components through sanctioned path
try:
    import openai as _openai
    OpenAI = _openai.OpenAI
    AsyncOpenAI = _openai.AsyncOpenAI
except ImportError:
    OpenAI = None  # type: ignore[misc,assignment]
    AsyncOpenAI = None  # type: ignore[misc,assignment]

__all__ = [
    "create_openai_client",
    "create_openai_sync_client",
    "OpenAI",
    "AsyncOpenAI",
    "OpenAIClient",
    "OpenAIConfig",
]
