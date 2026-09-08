"""Authenticated persistence helpers for R1B durable/read projections.

The cache is a derived optimisation, never an authority.  Its on-disk records
still need origin integrity: a writer that can alter a cache directory must not
be able to manufacture an admissible record or refresh receipt.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


R1B_CACHE_INTEGRITY_HMAC_KEY_ENV = "APPS_RG_R1B_CACHE_INTEGRITY_HMAC_KEY"
R1B_CACHE_INTEGRITY_KEY_ID_ENV = "APPS_RG_R1B_CACHE_INTEGRITY_KEY_ID"
_ALGORITHM = "HMAC-SHA256"


class R1BCacheIntegrityError(RuntimeError):
    """Raised when an R1B projection is unsigned, malformed, or tampered."""


def _key() -> bytes:
    raw = os.environ.get(R1B_CACHE_INTEGRITY_HMAC_KEY_ENV, "")
    key = raw.encode("utf-8")
    if len(key) < 32:
        raise R1BCacheIntegrityError(
            f"{R1B_CACHE_INTEGRITY_HMAC_KEY_ENV} must be set to at least 32 bytes"
        )
    return key


def _body(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "integrity"}


def _canonical_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def payload_sha256(document: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(_body(document))).hexdigest()


def attach_integrity(document: dict[str, Any], *, artifact_kind: str) -> dict[str, Any]:
    body = _body(document)
    digest = payload_sha256(body)
    key_id = os.environ.get(R1B_CACHE_INTEGRITY_KEY_ID_ENV, "apps-rg-r1b-cache-v1")
    signed = f"{artifact_kind}:{key_id}:{digest}".encode("utf-8")
    body["integrity"] = {
        "schema_version": "apps_rg.r1b.cache_integrity.v1",
        "algorithm": _ALGORITHM,
        "artifact_kind": artifact_kind,
        "key_id": key_id,
        "payload_sha256": digest,
        "signature": hmac.new(_key(), signed, hashlib.sha256).hexdigest(),
    }
    return body


def verify_integrity(document: dict[str, Any], *, artifact_kind: str) -> bool:
    integrity = document.get("integrity")
    if not isinstance(integrity, dict):
        return False
    if integrity.get("algorithm") != _ALGORITHM or integrity.get("artifact_kind") != artifact_kind:
        return False
    digest = payload_sha256(document)
    if not hmac.compare_digest(str(integrity.get("payload_sha256") or ""), digest):
        return False
    key_id = str(integrity.get("key_id") or "")
    signed = f"{artifact_kind}:{key_id}:{digest}".encode("utf-8")
    expected = hmac.new(_key(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(integrity.get("signature") or ""), expected)


def write_signed_json(path: Path, document: dict[str, Any], *, artifact_kind: str) -> dict[str, Any]:
    signed = attach_integrity(document, artifact_kind=artifact_kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return signed


def load_verified_json(path: Path, *, artifact_kind: str) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(value, dict):
        return None
    try:
        return value if verify_integrity(value, artifact_kind=artifact_kind) else None
    except R1BCacheIntegrityError:
        return None


__all__ = [
    "R1B_CACHE_INTEGRITY_HMAC_KEY_ENV",
    "R1BCacheIntegrityError",
    "attach_integrity",
    "load_verified_json",
    "payload_sha256",
    "write_signed_json",
]
