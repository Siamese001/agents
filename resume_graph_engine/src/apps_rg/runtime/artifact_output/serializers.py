"""Deterministic Serializers for Run Artifacts.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
"""

from __future__ import annotations

import json
from typing import Any


class DeterministicSerializer:
    """Provides deterministic byte and text serialization."""

    @staticmethod
    def serialize_json(data: Any) -> bytes:
        """Serialize data to sorted, deterministic UTF-8 JSON bytes."""
        serialized = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        return (serialized + "\n").encode("utf-8")

    @staticmethod
    def serialize_markdown(text: str) -> bytes:
        """Normalize and encode markdown string to canonical UTF-8 bytes."""
        normalized = text.strip() + "\n"
        return normalized.encode("utf-8")
