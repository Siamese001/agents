"""Canonical SDK wrapper factories for OpenAI, Anthropic, Vertex, and Gemini."""

from __future__ import annotations

import os
from infrastructure.live_execution import LiveExecutionError, api_key as get_live_api_key

__all__ = [
    "create_openai_client",
    "create_openai_sync_client",
    "create_anthropic_client",
    "create_anthropic_sync_client",
    "create_vertex_client",
    "create_gemini_model",
    "create_local_openai_client",
    "create_local_openai_sync_client",
    "OpenAIClient",
    "AnthropicClient",
    "VertexClient",
    "OpenAIConfig",
    "AnthropicConfig",
    "VertexConfig",
]


def create_openai_client():
    """Create an async OpenAI client from authenticated live credentials."""
    import openai

    key = get_live_api_key("openai")
    return openai.AsyncOpenAI(api_key=key)


def create_openai_sync_client():
    """Create a synchronous OpenAI client for sync call sites."""
    import openai

    key = get_live_api_key("openai")
    return openai.OpenAI(api_key=key)


def create_local_openai_client():
    """Create an async OpenAI client configured for an explicitly declared local server."""
    import openai

    key = os.getenv("LOCAL_OPENAI_API_KEY")
    base_url = os.getenv("LOCAL_OPENAI_BASE_URL")
    if not key or not base_url:
        raise LiveExecutionError(
            "LOCAL_PROVIDER_ERROR: LOCAL_OPENAI_API_KEY and LOCAL_OPENAI_BASE_URL must be explicitly configured. "
            "Implicit fallback to placeholder keys or localhost is prohibited in live runtime."
        )
    return openai.AsyncOpenAI(api_key=key, base_url=base_url)


def create_local_openai_sync_client():
    """Create a sync OpenAI client configured for an explicitly declared local server."""
    import openai

    key = os.getenv("LOCAL_OPENAI_API_KEY")
    base_url = os.getenv("LOCAL_OPENAI_BASE_URL")
    if not key or not base_url:
        raise LiveExecutionError(
            "LOCAL_PROVIDER_ERROR: LOCAL_OPENAI_API_KEY and LOCAL_OPENAI_BASE_URL must be explicitly configured. "
            "Implicit fallback to placeholder keys or localhost is prohibited in live runtime."
        )
    return openai.OpenAI(api_key=key, base_url=base_url)


def create_anthropic_client():
    """Create an async Anthropic client from authenticated live credentials."""
    import anthropic

    key = get_live_api_key("anthropic")
    return anthropic.AsyncAnthropic(api_key=key)


def create_anthropic_sync_client():
    """Create a synchronous Anthropic client from authenticated live credentials."""
    import anthropic

    key = get_live_api_key("anthropic")
    return anthropic.Anthropic(api_key=key)


def create_vertex_client():
    """Create a configured Vertex / Gemini module handle."""
    import google.generativeai as genai

    key = get_live_api_key("google")
    genai.configure(api_key=key)
    return genai


def create_gemini_model(model_name: str):
    """Create a configured Gemini ``GenerativeModel`` instance."""
    import google.generativeai as genai

    key = get_live_api_key("gemini")
    genai.configure(api_key=key)
    return genai.GenerativeModel(model_name)


class OpenAIClient:
    pass


class AnthropicClient:
    pass


class VertexClient:
    pass


class OpenAIConfig:
    pass


class AnthropicConfig:
    pass


class VertexConfig:
    pass
