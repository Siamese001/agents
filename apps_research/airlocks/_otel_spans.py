"""OTEL span helper for apps_research airlock boundary observability.

Pattern: apps_rg/airlocks/_otel_spans.py, apps_qna/airlocks/_otel_spans.py
Plan: apps-research-pa-spine-hardening-a28ea8 W3
"""

from __future__ import annotations

import contextlib
from typing import Any, Iterator

try:
    import opentelemetry  # noqa: F401

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


@contextlib.contextmanager
def airlock_span(
    name: str,
    *,
    airlock: str,
    request_id: str = "",
    run_id: str = "",
    trace_id: str = "",
    **attributes: Any,
) -> Iterator[Any]:
    """Context manager for apps_research airlock OTEL spans."""
    if not OTEL_AVAILABLE:
        yield None
        return

    from apps_model_telemetry.otel_runtime import get_verified_tracer

    tracer = get_verified_tracer("apps_research.airlocks")
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(name) as span:
        span.set_attribute("airlock", airlock)
        if request_id:
            span.set_attribute("request_id", request_id)
        if run_id:
            span.set_attribute("run_id", run_id)
        if trace_id:
            span.set_attribute("trace_id", trace_id)
        for key, value in attributes.items():
            span.set_attribute(key, str(value))
        yield span


def emit_airlock_event(span: Any, event_name: str, **attributes: Any) -> None:
    """Add an event to an active OTEL span."""
    if span is None or not OTEL_AVAILABLE:
        return
    string_attrs = {k: str(v) for k, v in attributes.items()}
    try:
        span.add_event(event_name, attributes=string_attrs)
    except (AttributeError, TypeError):  # guardian: allow-otel-optional -- span API drift  # guardian: allow-silent-swallow -- P2 burndown: fail-soft optional boundary
        pass


__all__ = ["OTEL_AVAILABLE", "airlock_span", "emit_airlock_event"]
