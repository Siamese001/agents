"""Unified telemetry facade for external model invocations.

Emits both:
1. An OpenTelemetry GenAI semantic conventions span (gen_ai.* and app.* attributes)
2. An append-only usage ledger event (external_model_usage_ledger.jsonl)
from the same invocation record.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from apps_model_telemetry.external_model_usage import (
    append_external_model_usage,
    normalize_usage,
)
from apps_model_telemetry.otel_runtime import get_verified_tracer
from apps_model_telemetry.pricing import price_usage


def record_llm_call(
    *,
    artifact_dir: Path | str | None = None,
    provider: str,
    model: str,
    request_digest: str = "",
    outcome: str = "SUCCESS",
    usage: Mapping[str, Any] | None = None,
    role: str = "",
    stage: str = "",
    section_id: str = "",
    run_id: str = "",
    latency_ms: float | None = None,
    ttft_ms: float | None = None,
    cache_hit: bool = False,
    cost_usd: float | None = None,
    logical_attempt: int | None = None,
    transport_attempt: int | None = None,
    retry_reason: str | None = None,
    provider_status: str | None = None,
    response_id: str | None = None,
    raw_response_ref: str | None = None,
    requested_model: str | None = None,
    observed_model: str | None = None,
    span_attributes: Mapping[str, Any] | None = None,
    **extra_evidence: Any,
) -> dict[str, Any]:
    """Record an LLM call to both the OpenTelemetry span pipeline and the usage ledger."""
    norm_usage = normalize_usage(provider, usage)
    pricing_version = None
    if cost_usd is None:
        try:
            computed_cost, p_ver, _ = price_usage(model, norm_usage, provider=provider)
            cost_usd = computed_cost
            pricing_version = p_ver
        except Exception:
            cost_usd = None

    ledger_event = append_external_model_usage(
        artifact_dir=artifact_dir,
        provider=provider,
        model=model,
        request_digest=request_digest,
        outcome=outcome,
        usage=usage,
        run_id=run_id or None,
        stage=stage or None,
        section_id=section_id or None,
        logical_attempt=logical_attempt,
        transport_attempt=transport_attempt,
        retry_reason=retry_reason,
        provider_status=provider_status,
        response_id=response_id,
        raw_response_ref=raw_response_ref,
        requested_model=requested_model,
        observed_model=observed_model,
        **extra_evidence,
    )

    tracer = get_verified_tracer("apps_model_telemetry.llm_call")
    if tracer is not None:
        span_name = f"gen_ai.{provider}.{role or stage or 'call'}"
        try:
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("gen_ai.system", str(provider))
                span.set_attribute("gen_ai.request.model", str(requested_model or model))
                if observed_model:
                    span.set_attribute("gen_ai.response.model", str(observed_model))
                if norm_usage.get("prompt_tokens") is not None:
                    span.set_attribute("gen_ai.usage.input_tokens", int(norm_usage["prompt_tokens"]))
                if norm_usage.get("output_tokens") is not None:
                    span.set_attribute("gen_ai.usage.output_tokens", int(norm_usage["output_tokens"]))
                if norm_usage.get("cached_tokens") is not None:
                    span.set_attribute("gen_ai.usage.cached_tokens", int(norm_usage["cached_tokens"]))
                if norm_usage.get("total_tokens") is not None:
                    span.set_attribute("gen_ai.usage.total_tokens", int(norm_usage["total_tokens"]))

                if stage:
                    span.set_attribute("app.stage", str(stage))
                if role:
                    span.set_attribute("app.role", str(role))
                if section_id:
                    span.set_attribute("app.section_id", str(section_id))
                if cost_usd is not None:
                    span.set_attribute("app.cost_usd", float(cost_usd))
                span.set_attribute("app.cache_hit", bool(cache_hit))
                if latency_ms is not None:
                    span.set_attribute("app.latency_ms", float(latency_ms))
                if ttft_ms is not None:
                    span.set_attribute("app.ttft_ms", float(ttft_ms))
                if span_attributes:
                    for k, v in span_attributes.items():
                        if v is not None:
                            span.set_attribute(str(k), v)
        except Exception:
            pass

    return ledger_event or {
        "provider": provider,
        "model": model,
        "cost_usd": cost_usd,
        "pricing_version": pricing_version,
        **norm_usage,
    }


__all__ = ["record_llm_call"]
