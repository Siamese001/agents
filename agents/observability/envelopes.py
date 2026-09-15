"""Canonical serialization, deterministic hashing, and redaction helpers.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

_PROHIBITED_KEY_TOKENS = frozenset({
    "api_key", "apikey", "secret", "token", "password",
    "authorization", "bearer", "cookie", "credential",
})


def _json_serial_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.astimezone(timezone.utc).isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "as_dict") and callable(obj.as_dict):
        return obj.as_dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def canonical_json_dumps(data: Any) -> str:
    """Serialize data to a deterministic, canonical JSON string."""
    return json.dumps(
        data,
        default=_json_serial_default,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def sha256_bytes(content: bytes) -> str:
    """Compute lowercase hexadecimal SHA-256 hash of raw bytes."""
    return hashlib.sha256(content).hexdigest()


def canonical_digest(data: Any) -> str:
    """Compute SHA-256 digest of canonical serialized JSON representation."""
    canonical_str = canonical_json_dumps(data)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def redact_sensitive_payload(
    payload: Mapping[str, Any],
    *,
    allowlist: set[str] | None = None,
) -> dict[str, Any]:
    """Redact sensitive fields (keys containing auth/secret/token/password tokens)."""
    sanitized: dict[str, Any] = {}
    allowed = allowlist or set()

    for k, v in payload.items():
        k_lower = str(k).lower()
        if k in allowed:
            sanitized[k] = v
        elif any(token in k_lower for token in _PROHIBITED_KEY_TOKENS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, Mapping):
            sanitized[k] = redact_sensitive_payload(v, allowlist=allowlist)
        elif isinstance(v, (list, tuple)):
            sanitized[k] = [
                redact_sensitive_payload(item, allowlist=allowlist)
                if isinstance(item, Mapping) else item
                for item in v
            ]
        else:
            sanitized[k] = v

    return sanitized


__all__ = [
    "canonical_digest",
    "canonical_json_dumps",
    "redact_sensitive_payload",
    "sha256_bytes",
]
