"""Strict, run-local reuse of an already successful external-model response.

This is deliberately narrower than a semantic cache.  A result can be replayed
only when the caller explicitly marks the request as idempotent and the full
request identity is exactly the same inside the same declared run.  In
particular, it never joins two sections, two run directories, or two sampling
paths merely because their prompts look similar.

The cache is an ignored runtime artifact.  It stores response material because
the corresponding run already persists provider-response artifacts; the usage
ledger continues to store metadata only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ENV_EXACT_RESPONSE_REUSE = "APPS_RG_EXACT_RESPONSE_REUSE"
EXACT_RESPONSE_CACHE_FILENAME = "external_model_exact_response_cache.jsonl"
EXACT_RESPONSE_CACHE_SCHEMA_VERSION = "apps.external_model_exact_response_cache.v1"
EXACT_RESPONSE_REUSE_RECEIPT_SCHEMA_VERSION = "apps.external_model_exact_response_reuse_receipt.v1"

_cache_lock = threading.RLock()


class ExactResponseReuseError(ValueError):
    """Raised when an enabled cache cannot be verified safely."""


@dataclass(frozen=True)
class ExactRequestIdentity:
    """Non-secret identity of one idempotent external request."""

    run_id: str
    stage: str
    section_id: str
    provider: str
    model: str
    request_digest: str
    prompt_sha256: str
    native_payload_sha256: str
    temperature: str
    max_output_tokens: int
    timeout_seconds: str
    identity_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def exact_response_reuse_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return str(env.get(ENV_EXACT_RESPONSE_REUSE) or "").strip() == "1"


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _stable_json_digest(value: Mapping[str, Any] | None) -> str:
    if value is None:
        return ""
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError) as exc:
        raise ExactResponseReuseError("native provider payload is not canonical JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _format_number(value: float | int | None) -> str:
    if value is None:
        return ""
    try:
        return format(float(value), ".17g")
    except (TypeError, ValueError) as exc:
        raise ExactResponseReuseError("request numeric identity is invalid") from exc


def build_exact_request_identity(
    *,
    run_id: str | None,
    stage: str,
    section_id: str | None,
    provider: str,
    model: str,
    request_digest: str,
    prompt_text: str,
    native_payload: Mapping[str, Any] | None,
    temperature: float,
    max_output_tokens: int,
    timeout_seconds: float | int | None,
) -> ExactRequestIdentity | None:
    """Build an identity only when a caller supplied a concrete run and scope.

    Returning ``None`` for an unbound run intentionally disables reuse.  That is
    safer than guessing from a working directory or letting two operator runs
    share raw model output.
    """
    resolved_run_id = str(run_id or "").strip()
    resolved_section_id = str(section_id or "").strip()
    if not resolved_run_id or not resolved_section_id:
        return None
    try:
        output = int(max_output_tokens)
    except (TypeError, ValueError) as exc:
        raise ExactResponseReuseError("max_output_tokens is invalid") from exc
    if output < 1:
        raise ExactResponseReuseError("max_output_tokens must be positive")
    base = {
        "run_id": resolved_run_id,
        "stage": str(stage or "").strip(),
        "section_id": resolved_section_id,
        "provider": str(provider or "").strip(),
        "model": str(model or "").strip(),
        "request_digest": str(request_digest or "").strip(),
        "prompt_sha256": _sha256_text(prompt_text),
        "native_payload_sha256": _stable_json_digest(native_payload),
        "temperature": _format_number(temperature),
        "max_output_tokens": output,
        "timeout_seconds": _format_number(timeout_seconds),
    }
    if not base["stage"] or not base["provider"] or not base["model"] or not base["request_digest"]:
        raise ExactResponseReuseError("exact-response identity fields are incomplete")
    return ExactRequestIdentity(
        **base,
        identity_sha256=hashlib.sha256(_canonical_json(base).encode("utf-8")).hexdigest(),
    )


def _cache_path(artifact_dir: Path | str | None) -> Path | None:
    return Path(artifact_dir) / EXACT_RESPONSE_CACHE_FILENAME if artifact_dir is not None else None


def _event_digest(event: Mapping[str, Any]) -> str:
    content = dict(event)
    content.pop("event_digest", None)
    return hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest()


def _read_verified_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(raw_line)
        except (TypeError, ValueError) as exc:
            raise ExactResponseReuseError(
                f"malformed exact-response cache at {path}:{line_number}"
            ) from exc
        if not isinstance(event, dict):
            raise ExactResponseReuseError(f"invalid exact-response cache entry at {path}:{line_number}")
        if event.get("schema_version") != EXACT_RESPONSE_CACHE_SCHEMA_VERSION:
            raise ExactResponseReuseError(f"invalid exact-response cache schema at {path}:{line_number}")
        expected = _event_digest(event)
        if str(event.get("event_digest") or "") != expected:
            raise ExactResponseReuseError(f"exact-response cache digest mismatch at {path}:{line_number}")
        events.append(event)
    return events


def _result_is_reusable(result: Mapping[str, Any], identity: ExactRequestIdentity) -> bool:
    return (
        result.get("provider_requested") == identity.provider
        and result.get("provider_attempted") is True
        and result.get("provider_available") is True
        and result.get("runtime_generation_status") == "REAL_LLM"
        and result.get("model") == identity.model
        and result.get("stub") is not True
        and not str(result.get("exact_provider_error") or "").strip()
        and bool(str(result.get("raw_model_output") or "").strip())
    )


def lookup_exact_response(
    *,
    artifact_dir: Path | str | None,
    identity: ExactRequestIdentity | None,
) -> tuple[dict[str, Any], str] | None:
    """Return one verified successful response and its source event digest."""
    if identity is None:
        return None
    path = _cache_path(artifact_dir)
    if path is None:
        return None
    with _cache_lock:
        for event in reversed(_read_verified_events(path)):
            if event.get("identity") != identity.to_dict():
                continue
            result = event.get("result")
            if not isinstance(result, dict) or not _result_is_reusable(result, identity):
                continue
            rendered = _canonical_json(result)
            if str(event.get("result_sha256") or "") != hashlib.sha256(rendered.encode("utf-8")).hexdigest():
                raise ExactResponseReuseError("exact-response cache result digest mismatch")
            return copy.deepcopy(result), str(event["event_digest"])
    return None


def store_exact_response(
    *,
    artifact_dir: Path | str | None,
    identity: ExactRequestIdentity | None,
    result: Mapping[str, Any],
) -> str | None:
    """Append a result only if it is eligible for exact response replay."""
    if identity is None or not _result_is_reusable(result, identity):
        return None
    path = _cache_path(artifact_dir)
    if path is None:
        return None
    try:
        result_copy = json.loads(_canonical_json(result))
    except (TypeError, ValueError) as exc:
        raise ExactResponseReuseError("successful provider result is not cache-serializable") from exc
    result_sha256 = hashlib.sha256(_canonical_json(result_copy).encode("utf-8")).hexdigest()
    event: dict[str, Any] = {
        "schema_version": EXACT_RESPONSE_CACHE_SCHEMA_VERSION,
        "event_id": uuid.uuid4().hex,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "identity": identity.to_dict(),
        "result_sha256": result_sha256,
        "result": result_copy,
    }
    event["event_digest"] = _event_digest(event)
    with _cache_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical_json(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return str(event["event_digest"])


def build_reuse_receipt(
    *,
    identity: ExactRequestIdentity,
    source_event_digest: str,
    transport_executed_this_invocation: bool,
) -> dict[str, Any]:
    """Return an explicit provenance receipt for fresh or replayed output."""
    return {
        "schema_version": EXACT_RESPONSE_REUSE_RECEIPT_SCHEMA_VERSION,
        "identity_sha256": identity.identity_sha256,
        "run_id": identity.run_id,
        "section_id": identity.section_id,
        "source_cache_event_digest": str(source_event_digest or ""),
        "transport_executed_this_invocation": bool(transport_executed_this_invocation),
        "reuse_mode": "FRESH_TRANSPORT"
        if transport_executed_this_invocation
        else "IN_RUN_EXACT_RESPONSE_REUSE",
    }


__all__ = [
    "ENV_EXACT_RESPONSE_REUSE",
    "EXACT_RESPONSE_CACHE_FILENAME",
    "EXACT_RESPONSE_CACHE_SCHEMA_VERSION",
    "EXACT_RESPONSE_REUSE_RECEIPT_SCHEMA_VERSION",
    "ExactRequestIdentity",
    "ExactResponseReuseError",
    "build_exact_request_identity",
    "build_reuse_receipt",
    "exact_response_reuse_enabled",
    "lookup_exact_response",
    "store_exact_response",
]
