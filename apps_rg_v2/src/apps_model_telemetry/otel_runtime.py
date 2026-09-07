"""Verified OpenTelemetry runtime and incremental collector evidence.

Configuration is not execution proof.  This module owns the one process-wide
OTel contract, verifies the actual global tracer provider, and reads collector
exports incrementally from a durable per-run checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping


OTEL_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
OTEL_SNAPSHOT_FILE_ENV = "APPS_OTEL_COLLECTOR_SPANS_FILE"
LEGACY_OTEL_ENDPOINT_ENVS = ("APPS_OTEL_EXPORTER_OTLP_ENDPOINT",)
LEGACY_OTEL_SNAPSHOT_FILE_ENVS = (
    "APPS_OTEL_COLLECTOR_FILE",
    "OTEL_COLLECTOR_SPANS_FILE",
)
OTEL_CHECKPOINT_FILENAME = "otel_collector_checkpoint.json"
OTEL_RUNTIME_RECEIPT_FILENAME = "otel_runtime_receipt.json"


@dataclass(frozen=True)
class OTelEnvironment:
    endpoint: str
    collector_file: str
    endpoint_source: str
    collector_source: str
    translations: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class OTelRuntimeStatus:
    active: bool
    endpoint: str
    reason: str
    provider_class: str
    global_provider_verified: bool
    span_processor_verified: bool
    environment_errors: tuple[str, ...] = ()


_provider: Any | None = None
_provider_endpoint = ""
_provider_service_name = ""


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{uuid.uuid4().hex[:12]}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _resolve_value(
    environ: Mapping[str, str],
    *,
    canonical: str,
    legacy: tuple[str, ...],
) -> tuple[str, str, list[str], list[str]]:
    canonical_value = str(environ.get(canonical) or "").strip()
    legacy_values = {
        name: str(environ.get(name) or "").strip()
        for name in legacy
        if str(environ.get(name) or "").strip()
    }
    translations: list[str] = []
    errors: list[str] = []
    distinct = {value for value in legacy_values.values()}
    if canonical_value:
        if any(value != canonical_value for value in distinct):
            errors.append(f"CONFLICTING_{canonical}")
        return canonical_value, canonical, translations, errors
    if len(distinct) > 1:
        errors.append(f"CONFLICTING_LEGACY_{canonical}")
        return "", "", translations, errors
    if legacy_values:
        source, value = next(iter(legacy_values.items()))
        translations.append(f"{source}->{canonical}")
        return value, source, translations, errors
    return "", "", translations, errors


def resolve_otel_environment(
    environ: Mapping[str, str] | None = None,
    *,
    apply_translation: bool = False,
) -> OTelEnvironment:
    """Resolve canonical OTel values and explicitly report legacy translation."""

    source = os.environ if environ is None else environ
    endpoint, endpoint_source, endpoint_translations, endpoint_errors = _resolve_value(
        source,
        canonical=OTEL_ENDPOINT_ENV,
        legacy=LEGACY_OTEL_ENDPOINT_ENVS,
    )
    collector, collector_source, collector_translations, collector_errors = _resolve_value(
        source,
        canonical=OTEL_SNAPSHOT_FILE_ENV,
        legacy=LEGACY_OTEL_SNAPSHOT_FILE_ENVS,
    )
    translations = tuple(endpoint_translations + collector_translations)
    errors = tuple(endpoint_errors + collector_errors)
    if apply_translation and not errors:
        if not isinstance(source, MutableMapping):
            raise TypeError("apply_translation requires a mutable environment mapping")
        if endpoint:
            source[OTEL_ENDPOINT_ENV] = endpoint
        if collector:
            source[OTEL_SNAPSHOT_FILE_ENV] = collector
    return OTelEnvironment(
        endpoint=endpoint,
        collector_file=collector,
        endpoint_source=endpoint_source,
        collector_source=collector_source,
        translations=translations,
        errors=errors,
    )


def _provider_class(provider: Any | None) -> str:
    if provider is None:
        return ""
    return f"{type(provider).__module__}.{type(provider).__name__}"


def _span_processor_present(provider: Any | None) -> bool:
    processor = getattr(provider, "_active_span_processor", None)
    if processor is None:
        return False
    processors = getattr(processor, "_span_processors", None)
    if processors is None:
        return True
    return bool(processors)


def _trace_exporter_endpoint(endpoint: str) -> str:
    """Return the OTLP/HTTP trace signal URL for a configured base endpoint."""

    normalized = str(endpoint or "").rstrip("/")
    if normalized.endswith("/v1/traces"):
        return normalized
    return f"{normalized}/v1/traces"


def current_otel_runtime_status() -> OTelRuntimeStatus:
    """Verify the installed provider instead of trusting configuration flags."""

    environment = resolve_otel_environment()
    if environment.errors:
        return OTelRuntimeStatus(
            False,
            environment.endpoint,
            "OTEL_ENVIRONMENT_CONFLICT",
            "",
            False,
            False,
            environment.errors,
        )
    try:
        from opentelemetry import trace
    except ImportError:
        return OTelRuntimeStatus(
            False,
            environment.endpoint,
            "OTEL_API_UNAVAILABLE",
            "",
            False,
            False,
        )
    installed = trace.get_tracer_provider()
    identity_verified = _provider is not None and installed is _provider
    processor_verified = identity_verified and _span_processor_present(installed)
    endpoint_verified = bool(
        environment.endpoint
        and _provider_endpoint
        and environment.endpoint == _provider_endpoint
    )
    active = bool(identity_verified and processor_verified and endpoint_verified)
    if active:
        reason = "VERIFIED_ACTIVE"
    elif _provider is None:
        reason = "RUNTIME_NOT_CONFIGURED"
    elif not identity_verified:
        reason = "GLOBAL_TRACER_PROVIDER_MISMATCH"
    elif not processor_verified:
        reason = "SPAN_PROCESSOR_NOT_INSTALLED"
    else:
        reason = "ENDPOINT_MISMATCH"
    return OTelRuntimeStatus(
        active,
        environment.endpoint,
        reason,
        _provider_class(installed),
        identity_verified,
        processor_verified,
    )


def configure_otel_runtime(
    *,
    service_name: str,
    endpoint: str | None = None,
    artifact_dir: Path | None = None,
) -> OTelRuntimeStatus:
    """Install and verify one OTLP provider for Apps Research, Apps RG and core."""

    global _provider, _provider_endpoint, _provider_service_name
    environment = resolve_otel_environment(apply_translation=True)
    target = str(endpoint or environment.endpoint or "").strip()
    if environment.errors:
        status = OTelRuntimeStatus(
            False,
            target,
            "OTEL_ENVIRONMENT_CONFLICT",
            "",
            False,
            False,
            environment.errors,
        )
        _write_runtime_receipt(artifact_dir, status, environment)
        return status
    if not target:
        status = OTelRuntimeStatus(
            False, "", "OTLP_ENDPOINT_NOT_CONFIGURED", "", False, False
        )
        _write_runtime_receipt(artifact_dir, status, environment)
        return status
    os.environ[OTEL_ENDPOINT_ENV] = target
    if _provider is not None:
        status = current_otel_runtime_status()
        _write_runtime_receipt(artifact_dir, status, environment)
        return status
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        status = OTelRuntimeStatus(
            False, target, "OTEL_SDK_UNAVAILABLE", "", False, False
        )
        _write_runtime_receipt(artifact_dir, status, environment)
        return status
    candidate = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "apps.telemetry.consumers": "apps_research,apps_rg,apps_rg",
            }
        )
    )
    candidate.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=_trace_exporter_endpoint(target)))
    )
    trace.set_tracer_provider(candidate)
    installed = trace.get_tracer_provider()
    if installed is candidate:
        _provider = candidate
        _provider_endpoint = target
        _provider_service_name = str(service_name)
    else:
        candidate.shutdown()
    status = current_otel_runtime_status()
    if installed is not candidate and not status.active:
        status = OTelRuntimeStatus(
            False,
            target,
            "GLOBAL_TRACER_PROVIDER_CONFLICT",
            _provider_class(installed),
            False,
            False,
        )
    _write_runtime_receipt(artifact_dir, status, environment)
    return status


def _write_runtime_receipt(
    artifact_dir: Path | None,
    status: OTelRuntimeStatus,
    environment: OTelEnvironment,
) -> None:
    if artifact_dir is None:
        return
    _atomic_write_json(
        Path(artifact_dir) / OTEL_RUNTIME_RECEIPT_FILENAME,
        {
            "schema_version": "apps.otel_runtime_receipt.v1",
            **asdict(status),
            "endpoint_source": environment.endpoint_source,
            "collector_source": environment.collector_source,
            "legacy_translations": list(environment.translations),
            "consumers": ["apps_research", "apps_rg", "apps_rg"],
        },
    )


def get_verified_tracer(name: str) -> Any | None:
    if not current_otel_runtime_status().active:
        return None
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    return trace.get_tracer(name)


def flush_otel_runtime(timeout_millis: int = 10_000) -> bool:
    status = current_otel_runtime_status()
    if not status.active or _provider is None:
        return False
    return bool(_provider.force_flush(timeout_millis=timeout_millis))


# Compatibility names retained for existing integrations.  Both delegate to the
# verified runtime path; neither recreates the historical implicit/no-op state.
def configure_live_otel(*, service_name: str) -> OTelRuntimeStatus:
    return configure_otel_runtime(service_name=service_name)


def flush_live_otel() -> bool:
    return flush_otel_runtime()


def _walk(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        rows = [value]
        for child in value.values():
            rows.extend(_walk(child))
        return rows
    if isinstance(value, list):
        rows: list[Mapping[str, Any]] = []
        for child in value:
            rows.extend(_walk(child))
        return rows
    return []


def _attribute_value(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return value
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return value[key]
    return value


def _attributes(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("attributes")
    if isinstance(raw, Mapping):
        return {str(key): _attribute_value(value) for key, value in raw.items()}
    if isinstance(raw, list):
        return {
            str(item.get("key") or ""): _attribute_value(item.get("value"))
            for item in raw
            if isinstance(item, Mapping) and str(item.get("key") or "")
        }
    return {}


def _source_identity(source: Path, stat: os.stat_result) -> str:
    material = "|".join(
        (
            str(source.resolve()),
            str(getattr(stat, "st_dev", "")),
            str(getattr(stat, "st_ino", "")),
            str(getattr(stat, "st_birthtime", "")),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _load_checkpoint(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _find_collector_checkpoint(artifact_dir: Path) -> Path:
    root = Path(artifact_dir).resolve()
    candidates = (root, *tuple(root.parents)[:8])
    for candidate in candidates:
        path = candidate / OTEL_CHECKPOINT_FILENAME
        if path.is_file():
            return path
    return root / OTEL_CHECKPOINT_FILENAME


def initialize_collector_checkpoint(
    *, artifact_dir: Path, start_at_end: bool = True
) -> dict[str, Any]:
    """Create the run checkpoint before emitting a fresh preflight marker."""

    environment = resolve_otel_environment()
    source_text = environment.collector_file
    checkpoint_path = Path(artifact_dir) / OTEL_CHECKPOINT_FILENAME
    checkpoint: dict[str, Any] = {
        "schema_version": "apps.otel_collector_checkpoint.v1",
        "collector_source": source_text,
        "source_identity": "",
        "offset": 0,
        "generation": 0,
    }
    if source_text:
        source = Path(source_text)
        try:
            stat = source.stat()
        except OSError:
            pass
        else:
            checkpoint.update(
                {
                    "source_identity": _source_identity(source, stat),
                    "offset": int(stat.st_size) if start_at_end else 0,
                }
            )
    _atomic_write_json(checkpoint_path, checkpoint)
    return checkpoint


def _decode_documents(data: bytes) -> tuple[list[Any], int, str]:
    if not data:
        return [], 0, ""
    text = data.decode("utf-8", errors="strict")
    try:
        return [json.loads(text)], len(data), ""
    except json.JSONDecodeError:
        pass
    documents: list[Any] = []
    consumed = 0
    cursor = 0
    for raw_line in data.splitlines(keepends=True):
        cursor += len(raw_line)
        if not raw_line.endswith((b"\n", b"\r")) and cursor == len(data):
            break
        if not raw_line.strip():
            consumed = cursor
            continue
        try:
            documents.append(json.loads(raw_line.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return documents, consumed, f"{type(exc).__name__}:{exc}"
        consumed = cursor
    return documents, consumed, ""


def capture_collector_snapshot(
    *,
    artifact_dir: Path,
    trace_id: str,
    timeout_seconds: float = 0.5,
    filename: str = "otel_trace_snapshot.json",
    boundary: str = "unspecified",
) -> dict[str, Any]:
    """Read only new collector bytes and persist exact-trace correlated spans."""

    environment = resolve_otel_environment()
    source_text = environment.collector_file
    endpoint = environment.endpoint
    target = Path(artifact_dir) / filename
    checkpoint_path = _find_collector_checkpoint(Path(artifact_dir))
    result: dict[str, Any] = {
        "schema_version": "apps.otel_trace_snapshot.v3",
        "trace_id": str(trace_id or ""),
        "boundary": str(boundary),
        "collector_source": source_text,
        "collector_source_configured": bool(source_text),
        "exporter_endpoint_configured": bool(endpoint),
        "runtime_active": current_otel_runtime_status().active,
        "status": "NOT_CONFIGURED" if not source_text else "NO_MATCH",
        "spans": [],
        "checkpoint_ref": str(checkpoint_path),
        "offset_start": 0,
        "offset_end": 0,
        "bytes_read": 0,
        "rotation_detected": False,
    }
    if environment.errors:
        result.update(
            {"status": "CONFIGURATION_CONFLICT", "configuration_errors": list(environment.errors)}
        )
    elif source_text and not trace_id:
        result.update(
            {
                "status": "TRACE_ID_UNAVAILABLE",
                "reason": "exact trace correlation cannot be attempted without a trace id",
            }
        )
    elif source_text:
        source = Path(source_text)
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        checkpoint = _load_checkpoint(checkpoint_path)
        last_error = ""
        while True:
            try:
                stat = source.stat()
                identity = _source_identity(source, stat)
                prior_identity = str(checkpoint.get("source_identity") or "")
                prior_source = str(checkpoint.get("collector_source") or "")
                offset = int(checkpoint.get("offset") or 0)
                rotated = bool(
                    (prior_source and prior_source != source_text)
                    or (prior_identity and prior_identity != identity)
                    or stat.st_size < offset
                )
                if rotated:
                    offset = 0
                with source.open("rb") as handle:
                    handle.seek(offset)
                    chunk = handle.read()
                documents, consumed, parse_error = _decode_documents(chunk)
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                last_error = f"{type(exc).__name__}:{exc}"
            else:
                end_offset = offset + consumed
                checkpoint = {
                    "schema_version": "apps.otel_collector_checkpoint.v1",
                    "collector_source": source_text,
                    "source_identity": identity,
                    "offset": end_offset,
                    "generation": int(checkpoint.get("generation") or 0)
                    + (1 if rotated else 0),
                }
                _atomic_write_json(checkpoint_path, checkpoint)
                matches: list[dict[str, Any]] = []
                for raw in documents:
                    for row in _walk(raw):
                        attrs = _attributes(row)
                        ids = {
                            str(row.get("traceId") or ""),
                            str(row.get("trace_id") or ""),
                            str(attrs.get("trace.root") or ""),
                            str(attrs.get("trace_id") or ""),
                        }
                        if trace_id in ids and ("name" in row or "spanId" in row):
                            matches.append(dict(row))
                result.update(
                    {
                        "spans": matches,
                        "status": "CAPTURED" if matches else "NO_MATCH",
                        "offset_start": offset,
                        "offset_end": end_offset,
                        "bytes_read": len(chunk),
                        "rotation_detected": rotated,
                        "collector_generation": checkpoint["generation"],
                    }
                )
                if parse_error:
                    result["partial_parse_error"] = parse_error
                if matches:
                    break
            if time.monotonic() >= deadline:
                if last_error:
                    result.update({"status": "SOURCE_UNREADABLE", "read_error": last_error})
                break
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    _atomic_write_json(target, result)
    return result


def verify_live_collector_receipt(
    *, artifact_dir: Path, timeout_seconds: float = 10.0
) -> dict[str, Any]:
    """Emit a fresh marker and prove it arrived after the preflight checkpoint."""

    marker = f"otel-preflight-{uuid.uuid4().hex}"
    status = current_otel_runtime_status()
    environment = resolve_otel_environment()
    receipt: dict[str, Any] = {
        "schema_version": "apps.otel_collector_preflight.v2",
        "marker": marker,
        "runtime_active": status.active,
        "runtime_reason": status.reason,
        "collector_source_configured": bool(environment.collector_file),
        "status": "BLOCKED",
        "reason": "OTEL_RUNTIME_NOT_ACTIVE",
    }
    target = Path(artifact_dir) / "otel_collector_preflight.json"
    if not status.active:
        _atomic_write_json(target, receipt)
        return receipt
    if not environment.collector_file:
        receipt["reason"] = "COLLECTOR_EXPORT_FILE_NOT_CONFIGURED"
        _atomic_write_json(target, receipt)
        return receipt
    initialize_collector_checkpoint(artifact_dir=artifact_dir, start_at_end=True)
    try:
        tracer = get_verified_tracer("apps.model.telemetry_preflight")
        if tracer is None:
            raise RuntimeError("verified tracer unavailable")
        with tracer.start_as_current_span("apps.model.collector_preflight") as span:
            span.set_attribute("trace.root", marker)
            span.set_attribute("evidence.kind", "collector_preflight")
        flushed = flush_otel_runtime()
    except Exception as exc:
        receipt.update(
            {
                "reason": "OTEL_MARKER_EMIT_FAILED",
                "error_class": type(exc).__name__,
            }
        )
        _atomic_write_json(target, receipt)
        return receipt
    snapshot = capture_collector_snapshot(
        artifact_dir=artifact_dir,
        trace_id=marker,
        timeout_seconds=timeout_seconds,
        filename="otel_preflight_snapshot.json",
        boundary="preflight",
    )
    passed = bool(flushed and snapshot.get("status") == "CAPTURED")
    receipt.update(
        {
            "flush_succeeded": flushed,
            "snapshot": "otel_preflight_snapshot.json",
            "matched_spans": len(snapshot.get("spans") or []),
            "status": "PASS" if passed else "BLOCKED",
            "reason": "COLLECTOR_MARKER_CAPTURED"
            if passed
            else "COLLECTOR_MARKER_NOT_CAPTURED",
        }
    )
    _atomic_write_json(target, receipt)
    return receipt


__all__ = [
    "LEGACY_OTEL_ENDPOINT_ENVS",
    "LEGACY_OTEL_SNAPSHOT_FILE_ENVS",
    "OTEL_CHECKPOINT_FILENAME",
    "OTEL_ENDPOINT_ENV",
    "OTEL_RUNTIME_RECEIPT_FILENAME",
    "OTEL_SNAPSHOT_FILE_ENV",
    "OTelEnvironment",
    "OTelRuntimeStatus",
    "capture_collector_snapshot",
    "configure_live_otel",
    "configure_otel_runtime",
    "current_otel_runtime_status",
    "flush_otel_runtime",
    "flush_live_otel",
    "get_verified_tracer",
    "initialize_collector_checkpoint",
    "resolve_otel_environment",
    "verify_live_collector_receipt",
]
