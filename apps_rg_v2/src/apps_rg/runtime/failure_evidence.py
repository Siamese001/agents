"""Durable, fail-soft evidence for exceptions at governed runtime boundaries."""

from __future__ import annotations

import json
import os
import traceback
import uuid
from pathlib import Path
from typing import Any, Mapping


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    """Atomically replace a JSON receipt in the target directory."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Keep the temporary basename short.  Whole-run lane paths are already
    # deep; repeating the target name plus a full UUID can cross Windows'
    # legacy MAX_PATH boundary even when the final receipt path itself fits.
    temporary = target.with_name(f".{uuid.uuid4().hex[:12]}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return target


def current_span_identity() -> dict[str, str]:
    """Return the active OTel identifiers when a recording span exists."""

    try:
        from opentelemetry import trace

        span_context = trace.get_current_span().get_span_context()
        if not span_context.is_valid:
            return {"otel_trace_id": "", "otel_span_id": ""}
        return {
            "otel_trace_id": format(span_context.trace_id, "032x"),
            "otel_span_id": format(span_context.span_id, "016x"),
        }
    except Exception:  # telemetry inspection must never mask the product failure
        return {"otel_trace_id": "", "otel_span_id": ""}


def exception_failure_envelope(
    exc: BaseException,
    *,
    stage: str,
    operation: str,
    source_component: str,
    artifact_dir: Path,
    lane_id: str = "",
    sections_root: Path | None = None,
    integrated_artifact_dir: Path | None = None,
    identity: Mapping[str, Any] | None = None,
    run_id: str = "",
    provider: str = "",
    provider_resolution_source: str = "",
    dispatch_invoked: bool = False,
    logical_attempt: int = 1,
    transport_attempt: int | None = None,
) -> dict[str, Any]:
    """Build a reconstructable exception record without asserting unknown causes."""

    formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    frames = traceback.extract_tb(exc.__traceback__)
    last = frames[-1] if frames else None
    callsite = {
        "file": last.filename if last else "",
        "line": last.lineno if last else 0,
        "function": last.name if last else "",
        "source_line": last.line if last and last.line else "",
    }
    identity_doc = dict(identity) if isinstance(identity, Mapping) else {}
    span_identity = current_span_identity()
    trace_root = str(
        identity_doc.get("trace_root")
        or identity_doc.get("trace_id")
        or span_identity["otel_trace_id"]
        or ""
    )
    envelope: dict[str, Any] = {
        "schema_version": "apps_rg.runtime_failure_envelope.v1",
        "stage": str(stage),
        "lane_id": str(lane_id),
        "operation": str(operation),
        "source_component": str(source_component),
        "exception_class": type(exc).__name__,
        "exception_module": type(exc).__module__,
        "exception_message": str(exc),
        "errno": getattr(exc, "errno", None),
        "winerror": getattr(exc, "winerror", None),
        "traceback": formatted,
        "callsite": callsite,
        "artifact_dir": str(Path(artifact_dir).resolve()),
        "sections_root": str(Path(sections_root).resolve()) if sections_root else "",
        "integrated_artifact_dir": (
            str(Path(integrated_artifact_dir).resolve())
            if integrated_artifact_dir
            else ""
        ),
        "run_id": str(run_id or identity_doc.get("child_run_id") or ""),
        "request_id": str(identity_doc.get("request_id") or ""),
        "trace_root": trace_root,
        "tenant_id": str(identity_doc.get("tenant_id") or ""),
        **span_identity,
        "attempt": {
            "logical": int(logical_attempt),
            "transport": transport_attempt,
        },
        "provider_boundary": {
            "provider": str(provider),
            "resolution_source": str(provider_resolution_source),
            "canonical_dispatch_invoked": bool(dispatch_invoked),
            "provider_call_attempted": None,
            "attempt_evidence": "UNKNOWN_AT_LANE_EXCEPTION_BOUNDARY",
        },
    }
    return envelope


def capture_failure_otel_evidence(
    *,
    artifact_dir: Path,
    trace_root: str,
    stage: str,
    operation: str,
    filename: str = "failure_otel_trace_snapshot.json",
) -> dict[str, Any]:
    """Capture exact-trace collector evidence or emit an explicit absence receipt."""

    target = Path(artifact_dir) / filename
    try:
        from apps_model_telemetry.otel_runtime import capture_collector_snapshot

        result = capture_collector_snapshot(
            artifact_dir=artifact_dir,
            trace_id=str(trace_root or ""),
            timeout_seconds=0.5,
            filename=filename,
            boundary=f"failure:{stage}",
        )
        result.update({"failure_stage": stage, "failure_operation": operation})
        atomic_write_json(target, result)
        return result
    except Exception as exc:  # evidence capture cannot replace the primary failure
        fallback = {
            "schema_version": "apps.otel_trace_snapshot.v3",
            "trace_id": str(trace_root or ""),
            "boundary": f"failure:{stage}",
            "status": "CAPTURE_FAILED",
            "spans": [],
            "failure_stage": stage,
            "failure_operation": operation,
            "capture_error_class": type(exc).__name__,
            "capture_error": str(exc),
        }
        try:
            atomic_write_json(target, fallback)
        except OSError:
            pass
        return fallback


__all__ = [
    "atomic_write_json",
    "capture_failure_otel_evidence",
    "current_span_identity",
    "exception_failure_envelope",
]
