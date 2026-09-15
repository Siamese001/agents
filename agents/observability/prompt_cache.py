#!/usr/bin/env python3
"""Shared Prompt Caching and Prefix Normalization Utilities.

Optimizes OpenAI automatic prompt caching across the platform by enforcing:
1. Exact static prefix normalization (whitespace, line endings).
2. Deterministic JSON serialization without arbitrary key order jitter.
3. Prefix fingerprinting for drift detection and auditability.
4. Stable routing keys for prompt cache routing.
5. Extraction and tracking of cached input tokens from API response usage.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def normalize_static_template(text: str) -> str:
    """Normalize whitespace and line endings for application-owned static templates."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip("\n") + "\n"


def json_text(value: Any, *, sort_keys: bool = True) -> str:
    """Serialize values to compact, deterministic JSON for prompt data segments."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=sort_keys,
        separators=(",", ":"),
    )


def prefix_fingerprint(
    *,
    model: str,
    prefix_messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None = None,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Compute deterministic SHA-256 fingerprint of the static prompt prefix."""
    manifest = {
        "model": model,
        "messages": prefix_messages,
        "tools": tools,
        "response_format": response_format,
    }
    canonical = json_text(manifest, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def routing_key(family: str, version: str, digest: str) -> str:
    """Generate bounded, stable prompt_cache_key for OpenAI request routing."""
    return f"{family}:{version}:{digest[:24]}"


def chat_usage_metrics(response: Any) -> dict[str, int | float]:
    """Extract prompt caching usage metrics from an OpenAI API response object or dictionary."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, Mapping):
        usage = response.get("usage")

    if usage is None:
        return {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "uncached_input_tokens": 0,
            "output_tokens": 0,
            "cache_read_ratio": 0.0,
        }

    # Handle object or dict
    if isinstance(usage, Mapping):
        total_input = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        details = usage.get("prompt_tokens_details") or {}
        if isinstance(details, Mapping):
            cached_input = int(details.get("cached_tokens") or 0)
        else:
            cached_input = int(getattr(details, "cached_tokens", 0) or 0)
    else:
        total_input = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        details = getattr(usage, "prompt_tokens_details", None)
        cached_input = int(getattr(details, "cached_tokens", 0) or 0) if details else 0

    uncached = max(0, total_input - cached_input)
    ratio = round(cached_input / total_input, 4) if total_input > 0 else 0.0

    return {
        "input_tokens": total_input,
        "cached_input_tokens": cached_input,
        "uncached_input_tokens": uncached,
        "output_tokens": output_tokens,
        "cache_read_ratio": ratio,
    }
