"""Approved external-model gateway for ``apps_research``.

This module is the only Apps Research production boundary allowed to invoke the
OpenAI SDK or the Gemini HTTP transport.  It records a terminal success row
only after transport, response schema, requested model pin, and app output have
all been validated.
"""

from __future__ import annotations

import hashlib
import json
import random
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from apps_model_telemetry.execution_evidence import (
    ProviderAttempt,
    provider_attempt,
    urlopen_with_transport_evidence,
)
from apps_model_telemetry.external_model_usage import (
    allocate_provider_logical_attempt,
    append_external_model_usage,
    current_external_model_usage_context,
    normalize_usage,
)
from apps_research.config.model_pins import (
    AppsResearchModelPin,
    apps_rg_handoff_judge_pin,
    company_brief_generation_pin,
)
from apps_research.integrations.llm_client import create_openai_sync_client


GATEWAY_ID = "apps_research.provider_gateway_v1"
PROVIDER_RECEIPT_SCHEMA = "apps_research.provider_attempt_validation.v1"
_STDLIB_URLOPEN = urllib.request.urlopen


class AppsResearchProviderGatewayError(RuntimeError):
    """Fail-closed provider error carrying its safe terminal receipt."""

    def __init__(self, message: str, *, receipt: Mapping[str, Any], cause: BaseException | None = None):
        super().__init__(message)
        self.receipt = dict(receipt)
        self.cause = cause


@dataclass(frozen=True)
class ApprovedProviderResult:
    output: Any
    receipt: dict[str, Any]


def _request_digest(value: bytes | str) -> str:
    rendered = value if isinstance(value, bytes) else str(value).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _openai_usage(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if isinstance(usage, Mapping):
        return dict(usage)
    dump = getattr(usage, "model_dump", None)
    if callable(dump):
        rendered = dump()
        return dict(rendered) if isinstance(rendered, Mapping) else None
    return None


def _attempt_context(*, role: str) -> dict[str, str]:
    context = current_external_model_usage_context()
    return {
        "artifact_dir": context.get("artifact_dir") or "",
        "run_id": context.get("run_id") or "",
        "trace_id": context.get("trace_id") or "",
        "app_id": context.get("app_id") or "apps_research",
        "stage": context.get("stage") or "L2.apps_research_company_brief",
        "section_id": context.get("section_id") or role,
    }


def _terminal_receipt(
    *,
    pin: AppsResearchModelPin,
    attempt: ProviderAttempt,
    response_schema_valid: bool,
    model_pin_valid: bool,
    application_output_valid: bool,
    validation_reason: str,
    usage: Mapping[str, Any] | None = None,
    transport_attempt_count: int = 1,
    retry_count: int = 0,
) -> dict[str, Any]:
    transport_response_received = bool(
        attempt.sdk_response_returned
        or attempt.response_headers_received
        or attempt.first_byte_received
    )
    overall_success = bool(
        transport_response_received
        and response_schema_valid
        and model_pin_valid
        and application_output_valid
    )
    outcome = "SUCCESS" if overall_success else str(validation_reason or "VALIDATION_FAILED")
    event = append_external_model_usage(
        artifact_dir=attempt.artifact_dir,
        provider=pin.provider,
        model=attempt.observed_model or pin.model,
        requested_model=pin.model,
        observed_model=attempt.observed_model,
        request_digest=attempt.request_digest,
        outcome=outcome,
        provider_status="VALIDATED_SUCCESS" if overall_success else outcome,
        usage=usage,
        response_id=attempt.provider_response_id,
        run_id=attempt.run_id,
        trace_id=attempt.trace_id,
        app_id=attempt.app_id,
        stage=attempt.stage,
        section_id=attempt.section_id,
        logical_attempt=attempt.logical_attempt,
        transport_attempt=attempt.transport_attempt,
        retry_reason=attempt.retry_reason,
        attempt_id=attempt.attempt_id,
        logical_attempt_id=attempt.logical_attempt_id,
        transport_attempt_id=attempt.transport_attempt_id,
        local_dispatch_started=attempt.local_dispatch_started,
        request_bytes_sent=attempt.request_bytes_sent,
        request_bytes_count=attempt.request_bytes_count,
        request_bytes_proof=attempt.request_bytes_proof,
        response_headers_received=attempt.response_headers_received,
        first_byte_received=attempt.first_byte_received,
        sdk_response_returned=attempt.sdk_response_returned,
        http_status_code=attempt.http_status_code,
        failure_phase=attempt.failure_phase,
        remote_outcome=attempt.remote_outcome,
        error_class=attempt.error_class,
        gateway_id=GATEWAY_ID,
        provider_role=pin.role,
        transport_response_received=transport_response_received,
        response_schema_valid=response_schema_valid,
        model_pin_valid=model_pin_valid,
        application_output_valid=application_output_valid,
        overall_success=overall_success,
        validation_reason=validation_reason,
    )
    return {
        "schema_version": PROVIDER_RECEIPT_SCHEMA,
        "gateway_id": GATEWAY_ID,
        "role": pin.role,
        "provider": pin.provider,
        "requested_model": pin.model,
        "observed_model": attempt.observed_model,
        "reasoning_effort": pin.reasoning_effort,
        "attempt_id": attempt.attempt_id,
        "logical_attempt_id": attempt.logical_attempt_id,
        "transport_attempt_id": attempt.transport_attempt_id,
        "transport_attempt": attempt.transport_attempt,
        "transport_attempt_count": max(1, int(transport_attempt_count)),
        "retry_count": max(0, int(retry_count)),
        "retry_reason": attempt.retry_reason,
        "run_id": attempt.run_id,
        "trace_id": attempt.trace_id,
        "request_digest": attempt.request_digest,
        "provider_response_id": attempt.provider_response_id,
        "lifecycle": {
            "local_dispatch_started": attempt.local_dispatch_started,
            "request_bytes_sent": attempt.request_bytes_sent,
            "response_headers_received": attempt.response_headers_received,
            "first_byte_received": attempt.first_byte_received,
            "sdk_response_returned": attempt.sdk_response_returned,
            "remote_outcome": attempt.remote_outcome,
        },
        "transport_response_received": transport_response_received,
        "response_schema_valid": response_schema_valid,
        "model_pin_valid": model_pin_valid,
        "application_output_valid": application_output_valid,
        "overall_success": overall_success,
        "terminal_status": "SUCCESS" if overall_success else "FAIL",
        "validation_reason": validation_reason,
        "ledger_event_digest": str((event or {}).get("event_digest") or ""),
        "ledger_event": dict(event or {}),
        "usage": normalize_usage(pin.provider, usage),
    }


def _raise_gateway_error(
    message: str,
    *,
    pin: AppsResearchModelPin,
    attempt: ProviderAttempt,
    response_schema_valid: bool,
    model_pin_valid: bool,
    application_output_valid: bool,
    validation_reason: str,
    usage: Mapping[str, Any] | None = None,
    cause: BaseException | None = None,
) -> None:
    receipt = _terminal_receipt(
        pin=pin,
        attempt=attempt,
        response_schema_valid=response_schema_valid,
        model_pin_valid=model_pin_valid,
        application_output_valid=application_output_valid,
        validation_reason=validation_reason,
        usage=usage,
    )
    raise AppsResearchProviderGatewayError(message, receipt=receipt, cause=cause) from cause


def _is_retryable_gemini_transport_error(error: AppsResearchProviderGatewayError) -> bool:
    """Allow only bounded retries whose remote outcome is safely classified.

    A timeout before response headers is not proof that Gemini did not process
    the request, so the first attempt remains recorded as
    ``REMOTE_OUTCOME_UNKNOWN``. X3 is read-only evaluation, however, and the
    caller explicitly budgets one retry for this transient class. Response
    schema, model-pin, auth, and application-validation errors are never
    retried here.
    """

    receipt = error.receipt
    lifecycle = receipt.get("lifecycle") if isinstance(receipt.get("lifecycle"), Mapping) else {}
    phase = str(receipt.get("validation_reason") or "")
    cause = error.cause or error.__cause__ or error.__context__
    if isinstance(cause, urllib.error.HTTPError):
        return cause.code == 429 or 500 <= int(cause.code) <= 599
    if phase not in {"WAIT_RESPONSE_HEADERS", "CONNECT_OR_DNS"}:
        return False
    if bool(lifecycle.get("response_headers_received")):
        return False
    return isinstance(cause, (socket.timeout, urllib.error.URLError, OSError))


def _gemini_retry_reason(error: AppsResearchProviderGatewayError) -> str:
    receipt = error.receipt
    phase = str(receipt.get("validation_reason") or "TRANSPORT_ERROR")
    cause = error.cause or error.__cause__ or error.__context__
    if isinstance(cause, urllib.error.HTTPError):
        return f"retry_after_http_{cause.code}"
    return "retry_after_" + phase.lower()


def _gemini_retry_delay_seconds(
    *,
    transport_attempt: int,
    base_seconds: float,
    max_seconds: float,
    uniform: Callable[[float, float], float],
) -> float:
    """Return a bounded exponential delay with small positive jitter."""

    base = max(0.0, float(base_seconds))
    maximum = max(base, float(max_seconds))
    exponential = min(maximum, base * (2 ** max(0, transport_attempt - 1)))
    jitter_ceiling = max(0.0, maximum - exponential)
    return min(maximum, exponential + uniform(0.0, jitter_ceiling))


def invoke_openai_company_brief(
    *,
    messages: list[dict[str, str]],
    max_completion_tokens: int,
    application_validator: Callable[[str], Any],
    client_factory: Callable[[], Any] | None = None,
) -> ApprovedProviderResult:
    """Invoke the single approved OpenAI lane and validate before success."""

    pin = company_brief_generation_pin()
    resolved_client_factory = client_factory or create_openai_sync_client
    context = _attempt_context(role=pin.role)
    logical_attempt = allocate_provider_logical_attempt()
    request_bytes = json.dumps(messages, sort_keys=True, separators=(",", ":"))
    response_schema_valid = False
    model_pin_valid = False
    application_output_valid = False
    usage: Mapping[str, Any] | None = None
    attempt: ProviderAttempt
    try:
        with provider_attempt(
            artifact_dir=context["artifact_dir"] or None,
            run_id=context["run_id"],
            trace_id=context["trace_id"],
            app_id=context["app_id"],
            stage=context["stage"],
            section_id=context["section_id"],
            provider=pin.provider,
            requested_model=pin.model,
            request_digest=_request_digest(request_bytes),
            logical_attempt=logical_attempt,
            transport_attempt=1,
        ) as attempt:
            try:
                client = resolved_client_factory()
            except Exception as exc:
                attempt.failure_phase = "CLIENT_SETUP"
                raise AppsResearchProviderGatewayError(
                    f"OpenAI client unavailable: {type(exc).__name__}: {exc}",
                    receipt={},
                    cause=exc,
                ) from exc
            attempt.mark_local_dispatch_started()
            try:
                response = client.chat.completions.create(
                    model=pin.model,
                    messages=messages,
                    reasoning_effort=pin.reasoning_effort,
                    max_completion_tokens=max_completion_tokens,
                )
            except Exception as exc:
                attempt.failure_phase = "SDK_CALL"
                raise AppsResearchProviderGatewayError(
                    f"OpenAI transport failed: {type(exc).__name__}: {exc}",
                    receipt={},
                    cause=exc,
                ) from exc
            observed_model = str(getattr(response, "model", "") or "").strip()
            response_id = str(getattr(response, "id", "") or "")
            attempt.mark_sdk_response(
                observed_model=observed_model,
                provider_response_id=response_id,
            )
            usage = _openai_usage(response)
            choices = getattr(response, "choices", None)
            if not observed_model or not choices:
                attempt.failure_phase = "RESPONSE_SCHEMA_VALIDATION"
                raise AppsResearchProviderGatewayError(
                    "OpenAI response missing model identity or choices",
                    receipt={},
                )
            try:
                text = str(choices[0].message.content or "").strip()
            except (AttributeError, IndexError, TypeError, ValueError) as exc:
                attempt.failure_phase = "RESPONSE_SCHEMA_VALIDATION"
                raise AppsResearchProviderGatewayError(
                    "OpenAI response content is malformed",
                    receipt={},
                    cause=exc,
                ) from exc
            if not text:
                attempt.failure_phase = "RESPONSE_SCHEMA_VALIDATION"
                raise AppsResearchProviderGatewayError(
                    "OpenAI response content is empty",
                    receipt={},
                )
            response_schema_valid = True
            if observed_model != pin.model:
                attempt.failure_phase = "MODEL_PIN_VALIDATION"
                raise AppsResearchProviderGatewayError(
                    f"OpenAI model pin mismatch: requested={pin.model} observed={observed_model}",
                    receipt={},
                )
            model_pin_valid = True
            try:
                output = application_validator(text)
            except Exception as exc:
                attempt.failure_phase = "APPLICATION_OUTPUT_VALIDATION"
                raise AppsResearchProviderGatewayError(
                    f"OpenAI application output invalid: {type(exc).__name__}: {exc}",
                    receipt={},
                    cause=exc,
                ) from exc
            application_output_valid = True
    except AppsResearchProviderGatewayError as exc:
        _raise_gateway_error(
            str(exc),
            pin=pin,
            attempt=attempt,
            response_schema_valid=response_schema_valid,
            model_pin_valid=model_pin_valid,
            application_output_valid=application_output_valid,
            validation_reason=attempt.failure_phase or "PROVIDER_GATEWAY_ERROR",
            usage=usage,
            cause=exc.cause or exc,
        )

    receipt = _terminal_receipt(
        pin=pin,
        attempt=attempt,
        response_schema_valid=True,
        model_pin_valid=True,
        application_output_valid=True,
        validation_reason="ALL_VALIDATIONS_PASSED",
        usage=usage,
    )
    return ApprovedProviderResult(output=output, receipt=receipt)


def invoke_gemini_handoff_judge(
    *,
    url: str,
    body: bytes,
    method: str,
    headers: Mapping[str, str],
    timeout: float,
    application_validator: Callable[[Mapping[str, Any]], Any],
    urlopen: Callable[..., Any] | None = None,
    artifact_dir: str | None = None,
    stage: str = "L2.X2_research_semantic_gate",
    section_id: str = "X2",
    max_transport_attempts: int = 1,
    retry_backoff_base_seconds: float = 0.0,
    retry_backoff_max_seconds: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
    uniform: Callable[[float, float], float] = random.uniform,
) -> ApprovedProviderResult:
    """Invoke the approved Gemini judge lane and validate before success.

    ``stage`` and ``section_id`` default to the historical X2 values so
    existing callers retain their records.  Callers whose Gemini invocation is
    an actual X3 evaluation can now report that truthfully.
    """

    pin = apps_rg_handoff_judge_pin()
    resolved_urlopen = urlopen
    if resolved_urlopen is None and urllib.request.urlopen is not _STDLIB_URLOPEN:
        resolved_urlopen = urllib.request.urlopen
    context = _attempt_context(role=pin.role)
    if artifact_dir:
        context["artifact_dir"] = str(artifact_dir)
    try:
        allowed_attempts = max(1, min(2, int(max_transport_attempts)))
    except (TypeError, ValueError) as exc:
        raise ValueError("max_transport_attempts must be an integer") from exc
    logical_attempt = allocate_provider_logical_attempt()
    request = urllib.request.Request(
        url=url,
        data=body,
        method=method,
        headers=dict(headers),
    )
    retry_reason = ""
    for transport_attempt in range(1, allowed_attempts + 1):
        response_schema_valid = False
        model_pin_valid = False
        application_output_valid = False
        usage: Mapping[str, Any] | None = None
        attempt: ProviderAttempt
        try:
            with provider_attempt(
                artifact_dir=context["artifact_dir"] or None,
                run_id=context["run_id"],
                trace_id=context["trace_id"],
                app_id=context["app_id"],
                stage=str(stage),
                section_id=str(section_id),
                provider=pin.provider,
                requested_model=pin.model,
                request_digest=_request_digest(body),
                logical_attempt=logical_attempt,
                transport_attempt=transport_attempt,
                retry_reason=retry_reason,
            ) as attempt:
                attempt.mark_local_dispatch_started()
                try:
                    response_context = (
                        resolved_urlopen(request, timeout=timeout)
                        if resolved_urlopen is not None
                        else urlopen_with_transport_evidence(
                            request,
                            timeout=timeout,
                            evidence=attempt,
                        )
                    )
                    with response_context as response:
                        response_headers = getattr(response, "headers", None)
                        response_id = ""
                        if response_headers is not None:
                            response_id = str(
                                response_headers.get("x-request-id")
                                or response_headers.get("request-id")
                                or ""
                            )
                        attempt.mark_response_headers(
                            status_code=getattr(response, "status", None),
                            provider_response_id=response_id,
                        )
                        response_body = response.read()
                        if response_body:
                            attempt.mark_first_byte()
                except socket.timeout as exc:
                    attempt.failure_phase = "WAIT_RESPONSE_HEADERS"
                    raise AppsResearchProviderGatewayError(
                        f"Gemini HTTP timeout after {timeout}s: {exc}",
                        receipt={},
                        cause=exc,
                    ) from exc
                except urllib.error.HTTPError as exc:
                    attempt.mark_response_headers(status_code=int(exc.code))
                    attempt.failure_phase = "HTTP_RESPONSE"
                    detail = exc.read().decode("utf-8", errors="ignore")[:500]
                    raise AppsResearchProviderGatewayError(
                        f"Gemini HTTP {exc.code} {exc.reason}: {detail}",
                        receipt={},
                        cause=exc,
                    ) from exc
                except urllib.error.URLError as exc:
                    attempt.failure_phase = "WAIT_RESPONSE_HEADERS"
                    raise AppsResearchProviderGatewayError(
                        f"Gemini HTTP URLError: {exc.reason}",
                        receipt={},
                        cause=exc,
                    ) from exc
                except OSError as exc:
                    attempt.failure_phase = (
                        "READ_RESPONSE_BODY"
                        if attempt.response_headers_received
                        else "WAIT_RESPONSE_HEADERS"
                    )
                    raise AppsResearchProviderGatewayError(
                        f"Gemini transport failed: {type(exc).__name__}: {exc}",
                        receipt={},
                        cause=exc,
                    ) from exc
                try:
                    parsed = json.loads(response_body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    attempt.failure_phase = "RESPONSE_SCHEMA_VALIDATION"
                    raise AppsResearchProviderGatewayError(
                        f"Gemini response was not JSON: {exc}",
                        receipt={},
                        cause=exc,
                    ) from exc
                if not isinstance(parsed, Mapping):
                    attempt.failure_phase = "RESPONSE_SCHEMA_VALIDATION"
                    raise AppsResearchProviderGatewayError(
                        "Gemini response JSON was not an object",
                        receipt={},
                    )
                observed_model = str(parsed.get("modelVersion") or "").strip()
                parsed_response_id = str(parsed.get("responseId") or "")
                attempt.provider_response_id = parsed_response_id or attempt.provider_response_id
                attempt.observed_model = observed_model
                usage_raw = parsed.get("usageMetadata")
                usage = dict(usage_raw) if isinstance(usage_raw, Mapping) else None
                if not observed_model:
                    attempt.failure_phase = "RESPONSE_SCHEMA_VALIDATION"
                    raise AppsResearchProviderGatewayError(
                        "Gemini response did not report modelVersion",
                        receipt={},
                    )
                response_schema_valid = True
                if observed_model != pin.model:
                    attempt.failure_phase = "MODEL_PIN_VALIDATION"
                    raise AppsResearchProviderGatewayError(
                        f"Gemini model pin mismatch: requested={pin.model} observed={observed_model}",
                        receipt={},
                    )
                model_pin_valid = True
                try:
                    output = application_validator(parsed)
                except Exception as exc:
                    attempt.failure_phase = "APPLICATION_OUTPUT_VALIDATION"
                    raise AppsResearchProviderGatewayError(
                        f"Gemini application output invalid: {type(exc).__name__}: {exc}",
                        receipt={},
                        cause=exc,
                    ) from exc
                application_output_valid = True
        except AppsResearchProviderGatewayError as exc:
            receipt = _terminal_receipt(
                pin=pin,
                attempt=attempt,
                response_schema_valid=response_schema_valid,
                model_pin_valid=model_pin_valid,
                application_output_valid=application_output_valid,
                validation_reason=attempt.failure_phase or "PROVIDER_GATEWAY_ERROR",
                usage=usage,
                transport_attempt_count=transport_attempt,
                retry_count=transport_attempt - 1,
            )
            terminal_error = AppsResearchProviderGatewayError(
                str(exc),
                receipt=receipt,
                cause=exc.cause or exc,
            )
            if transport_attempt < allowed_attempts and _is_retryable_gemini_transport_error(terminal_error):
                retry_reason = _gemini_retry_reason(terminal_error)
                delay = _gemini_retry_delay_seconds(
                    transport_attempt=transport_attempt,
                    base_seconds=retry_backoff_base_seconds,
                    max_seconds=retry_backoff_max_seconds,
                    uniform=uniform,
                )
                if delay > 0:
                    sleep(delay)
                continue
            receipt["transport_attempt_count"] = transport_attempt
            receipt["retry_count"] = transport_attempt - 1
            raise terminal_error from (exc.cause or exc)

        receipt = _terminal_receipt(
            pin=pin,
            attempt=attempt,
            response_schema_valid=True,
            model_pin_valid=True,
            application_output_valid=True,
            validation_reason="ALL_VALIDATIONS_PASSED",
            usage=usage,
            transport_attempt_count=transport_attempt,
            retry_count=transport_attempt - 1,
        )
        return ApprovedProviderResult(output=output, receipt=receipt)

    raise AssertionError("Gemini transport retry loop exited without a terminal result")


__all__ = [
    "GATEWAY_ID",
    "PROVIDER_RECEIPT_SCHEMA",
    "AppsResearchProviderGatewayError",
    "ApprovedProviderResult",
    "invoke_gemini_handoff_judge",
    "invoke_openai_company_brief",
]
