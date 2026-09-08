"""Append-only accounting for external model usage.

This module deliberately records only operational metadata and provider-reported
token counts.  It never stores prompt text, API keys, response text, or human
evaluation material.  The ledger is diagnostic evidence: it does not grant an
evaluation, release, or production authority.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import itertools
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


LEDGER_FILENAME = "external_model_usage_ledger.jsonl"
EVENT_SCHEMA_VERSION = "apps.external_model_usage_event.v1"


_usage_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "apps_external_model_usage_context",
    default=None,
)
_unscoped_attempt_sequence = itertools.count(1)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_int(*values: Any) -> int | None:
    for value in values:
        parsed = _nonnegative_int(value)
        if parsed is not None:
            return parsed
    return None


def normalize_usage(provider: str, usage: Mapping[str, Any] | None) -> dict[str, int | None]:
    """Normalize public provider usage metadata without estimating tokens.

    ``total_tokens`` is only derived when a provider omits it and there is no
    thinking field that could be double-counted.  Provider-reported values are
    always preferred.
    """
    raw = _mapping(usage)
    key = str(provider or "").lower()
    input_details = _mapping(raw.get("input_tokens_details") or raw.get("prompt_tokens_details"))
    output_details = _mapping(raw.get("output_tokens_details") or raw.get("completion_tokens_details"))

    if "gemini" in key or "google" in key:
        prompt = _first_int(raw.get("promptTokenCount"), raw.get("prompt_token_count"))
        output = _first_int(raw.get("candidatesTokenCount"), raw.get("candidates_token_count"))
        thought = _first_int(raw.get("thoughtsTokenCount"), raw.get("thoughts_token_count"))
        cached = _first_int(raw.get("cachedContentTokenCount"), raw.get("cached_content_token_count"))
        total = _first_int(raw.get("totalTokenCount"), raw.get("total_token_count"))
        cache_write = None
    elif "anthropic" in key or "claude" in key:
        prompt = _first_int(raw.get("input_tokens"))
        output = _first_int(raw.get("output_tokens"))
        thought = _first_int(raw.get("thinking_tokens"))
        cached = _first_int(raw.get("cache_read_input_tokens"))
        cache_write = _first_int(raw.get("cache_creation_input_tokens"))
        total = _first_int(raw.get("total_tokens"))
    else:
        prompt = _first_int(raw.get("input_tokens"), raw.get("prompt_tokens"))
        output = _first_int(raw.get("output_tokens"), raw.get("completion_tokens"))
        thought = _first_int(raw.get("reasoning_tokens"), output_details.get("reasoning_tokens"))
        cached = _first_int(raw.get("cached_tokens"), input_details.get("cached_tokens"))
        cache_write = _first_int(raw.get("cache_creation_input_tokens"))
        total = _first_int(raw.get("total_tokens"))

    if total is None and prompt is not None and output is not None and thought is None:
        total = prompt + output
    return {
        "prompt_tokens": prompt,
        "output_tokens": output,
        "thought_tokens": thought,
        "cached_tokens": cached,
        "cache_write_tokens": cache_write,
        "total_tokens": total,
    }


def _configured_ledger_dir() -> Path | None:
    raw = str(os.environ.get("APPS_MODEL_USAGE_LEDGER_DIR") or "").strip()
    return Path(raw) if raw else None


def ledger_path(artifact_dir: Path | str | None = None) -> Path | None:
    """Resolve the per-run ledger path from an explicit run artifact directory.

    An opt-in process-wide directory is available for integrations whose legacy
    call boundary has not yet been given a run artifact directory.  Without one
    of those two explicit bindings, no file is written rather than guessing a
    run identity.
    """
    if artifact_dir is not None:
        return Path(artifact_dir) / LEDGER_FILENAME
    scope = _usage_context.get()
    if scope and scope.get("artifact_dir"):
        return Path(scope["artifact_dir"]) / LEDGER_FILENAME
    configured = _configured_ledger_dir()
    return configured / LEDGER_FILENAME if configured is not None else None


@contextlib.contextmanager
def external_model_usage_scope(
    *,
    artifact_dir: Path | str | None,
    run_id: str | None = None,
    stage: str | None = None,
    section_id: str | None = None,
    trace_id: str | None = None,
    app_id: str | None = None,
) -> Iterator[None]:
    """Bind nested provider transports to one known run artifact directory."""
    fields = {
        "artifact_dir": str(artifact_dir) if artifact_dir is not None else "",
        "run_id": str(run_id or ""),
        "stage": str(stage or ""),
        "section_id": str(section_id or ""),
        "trace_id": str(trace_id or ""),
        "app_id": str(app_id or ""),
        "_logical_attempt_sequence": 0,
    }
    token = _usage_context.set(fields)
    try:
        yield
    finally:
        _usage_context.reset(token)


def current_external_model_usage_context() -> dict[str, str]:
    """Return public fields from the current explicit run binding."""

    scope = _usage_context.get() or {}
    return {
        str(key): str(value or "")
        for key, value in scope.items()
        if not str(key).startswith("_")
    }


def allocate_provider_logical_attempt() -> int:
    """Allocate a distinct logical attempt inside the current run scope."""

    scope = _usage_context.get()
    if scope is None:
        return next(_unscoped_attempt_sequence)
    next_value = int(scope.get("_logical_attempt_sequence") or 0) + 1
    scope["_logical_attempt_sequence"] = next_value
    return next_value


def append_external_model_usage(
    *,
    artifact_dir: Path | str | None = None,
    provider: str,
    model: str,
    request_digest: str,
    outcome: str,
    usage: Mapping[str, Any] | None = None,
    run_id: str | None = None,
    stage: str | None = None,
    section_id: str | None = None,
    logical_attempt: int | None = None,
    transport_attempt: int | None = None,
    retry_reason: str | None = None,
    provider_status: str | None = None,
    response_id: str | None = None,
    raw_response_ref: str | None = None,
    evidence_event: str | None = None,
    attempt_id: str | None = None,
    logical_attempt_id: str | None = None,
    transport_attempt_id: str | None = None,
    trace_id: str | None = None,
    app_id: str | None = None,
    requested_model: str | None = None,
    observed_model: str | None = None,
    local_dispatch_started: bool | None = None,
    request_bytes_sent: bool | None = None,
    request_bytes_count: int | None = None,
    request_bytes_proof: str | None = None,
    response_headers_received: bool | None = None,
    first_byte_received: bool | None = None,
    sdk_response_returned: bool | None = None,
    http_status_code: int | None = None,
    failure_phase: str | None = None,
    remote_outcome: str | None = None,
    error_class: str | None = None,
    evidence_digest: str | None = None,
    gateway_id: str | None = None,
    provider_role: str | None = None,
    transport_response_received: bool | None = None,
    response_schema_valid: bool | None = None,
    model_pin_valid: bool | None = None,
    application_output_valid: bool | None = None,
    overall_success: bool | None = None,
    validation_reason: str | None = None,
) -> dict[str, Any] | None:
    """Append one immutable provider-attempt event, returning the event.

    The absence of an artifact-dir binding is intentionally a no-op: the caller
    must not invent a run directory.  This makes any ledger row traceable to a
    known run or an explicitly configured integration sink.
    """
    path = ledger_path(artifact_dir)
    if path is None:
        return None
    scope = _usage_context.get() or {}
    normalized = normalize_usage(provider, usage)
    event: dict[str, Any] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": uuid.uuid4().hex,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": str(run_id if run_id is not None else scope.get("run_id") or ""),
        "stage": str(stage if stage is not None else scope.get("stage") or ""),
        "section_id": str(section_id if section_id is not None else scope.get("section_id") or ""),
        "provider": str(provider or ""),
        "model": str(model or ""),
        "request_digest": str(request_digest or ""),
        "outcome": str(outcome or ""),
        "provider_status": str(provider_status or ""),
        "logical_attempt": _nonnegative_int(logical_attempt),
        "transport_attempt": _nonnegative_int(transport_attempt),
        "retry_reason": str(retry_reason or ""),
        "response_id": str(response_id or ""),
        "raw_response_ref": str(raw_response_ref or ""),
        **normalized,
    }
    optional_evidence = {
        "evidence_event": evidence_event,
        "attempt_id": attempt_id,
        "logical_attempt_id": logical_attempt_id,
        "transport_attempt_id": transport_attempt_id,
        "trace_id": trace_id if trace_id is not None else scope.get("trace_id"),
        "app_id": app_id if app_id is not None else scope.get("app_id"),
        "requested_model": requested_model,
        "observed_model": observed_model,
        "local_dispatch_started": local_dispatch_started,
        "request_bytes_sent": request_bytes_sent,
        "request_bytes_count": _nonnegative_int(request_bytes_count),
        "request_bytes_proof": request_bytes_proof,
        "response_headers_received": response_headers_received,
        "first_byte_received": first_byte_received,
        "sdk_response_returned": sdk_response_returned,
        "http_status_code": _nonnegative_int(http_status_code),
        "failure_phase": failure_phase,
        "remote_outcome": remote_outcome,
        "error_class": error_class,
        "evidence_digest": evidence_digest,
        "gateway_id": gateway_id,
        "provider_role": provider_role,
        "transport_response_received": transport_response_received,
        "response_schema_valid": response_schema_valid,
        "model_pin_valid": model_pin_valid,
        "application_output_valid": application_output_valid,
        "overall_success": overall_success,
        "validation_reason": validation_reason,
    }
    event.update(
        {
            key: value
            for key, value in optional_evidence.items()
            if value is not None
        }
    )
    event["event_digest"] = _digest(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(_canonical_json(event) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


def usage_telemetry(
    *,
    provider: str,
    model: str,
    usage: Mapping[str, Any] | None,
    response_id: str | None = None,
) -> dict[str, Any]:
    """Return safe usage fields suitable for a sealed receipt or sidecar."""
    return {
        "provider": str(provider or ""),
        "model": str(model or ""),
        "response_id": str(response_id or ""),
        **normalize_usage(provider, usage),
    }


__all__ = [
    "EVENT_SCHEMA_VERSION",
    "LEDGER_FILENAME",
    "allocate_provider_logical_attempt",
    "append_external_model_usage",
    "current_external_model_usage_context",
    "external_model_usage_scope",
    "ledger_path",
    "normalize_usage",
    "usage_telemetry",
]
