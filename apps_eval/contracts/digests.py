"""Canonical RFC-8259 JSON serialization and SHA-256 digest utilities for apps_eval."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


def _assert_finite(value: Any, path: str = "$") -> None:
    """Reject NaN and Inf floats fail-closed before canonical serialization."""
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite float at {path}: {value!r}")
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            _assert_finite(v, f"{path}.{k}")
        return
    if isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _assert_finite(item, f"{path}[{idx}]")


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize payload into deterministic RFC-8259-compatible UTF-8 JSON bytes."""
    _assert_finite(payload)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return encoded.encode("utf-8")


def canonical_sha256(payload: Any, *, exclude_keys: tuple[str, ...] = ()) -> str:
    """Compute SHA-256 hex digest of canonical JSON, optionally excluding top-level keys."""
    if exclude_keys and isinstance(payload, Mapping):
        filtered = {k: v for k, v in payload.items() if k not in exclude_keys}
        return hashlib.sha256(canonical_json_bytes(filtered)).hexdigest()
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file on disk."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    """Derive a deterministic prefixed identifier from canonical parts."""
    digest = canonical_sha256(list(parts))
    return f"{prefix}-{digest[:length]}"


def seal_with_digest(
    payload: Mapping[str, Any],
    *,
    digest_field: str = "canonical_digest",
) -> dict[str, Any]:
    """Return a shallow copy of payload stamped with its canonical SHA-256 digest."""
    out = dict(payload)
    out.pop(digest_field, None)
    out[digest_field] = canonical_sha256(out)
    return out


def verify_canonical_digest(
    payload: Mapping[str, Any],
    *,
    digest_field: str = "canonical_digest",
) -> bool:
    """Verify that payload's digest_field matches its recomputed canonical SHA-256."""
    recorded = str(payload.get(digest_field) or "")
    if len(recorded) != 64:
        return False
    expected = canonical_sha256(payload, exclude_keys=(digest_field,))
    return recorded == expected
