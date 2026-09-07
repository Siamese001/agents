"""Truthful, append-only evidence for one provider transport attempt."""

from __future__ import annotations

import contextlib
import hashlib
import http.client
import json
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping

from apps_model_telemetry.external_model_usage import append_external_model_usage
from apps_model_telemetry.otel_runtime import get_verified_tracer


ATTEMPT_STARTED = "ATTEMPT_STARTED"
ATTEMPT_FINISHED = "ATTEMPT_FINISHED"
LOCAL_DISPATCH_STARTED = "LOCAL_DISPATCH_STARTED"
REQUEST_BYTES_SENT = "REQUEST_BYTES_SENT"
RESPONSE_HEADERS_RECEIVED = "RESPONSE_HEADERS_RECEIVED"
FIRST_BYTE_RECEIVED = "FIRST_BYTE_RECEIVED"
SDK_RESPONSE_RETURNED = "SDK_RESPONSE_RETURNED"
REMOTE_OUTCOME_UNKNOWN = "REMOTE_OUTCOME_UNKNOWN"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass
class ProviderAttempt:
    artifact_dir: str | None
    run_id: str
    trace_id: str
    app_id: str
    stage: str
    section_id: str
    provider: str
    requested_model: str
    request_digest: str
    logical_attempt: int
    transport_attempt: int
    retry_reason: str = ""
    attempt_id: str = field(default_factory=lambda: f"attempt-{uuid.uuid4().hex}")
    started_at_utc: str = field(default_factory=_now)
    local_dispatch_started: bool = False
    request_bytes_sent: bool = False
    request_bytes_count: int | None = None
    request_bytes_proof: str = ""
    response_headers_received: bool = False
    first_byte_received: bool = False
    sdk_response_returned: bool = False
    observed_model: str = ""
    provider_response_id: str = ""
    http_status_code: int | None = None
    failure_phase: str = ""
    remote_outcome: str = ""
    error_class: str = ""
    _span: Any | None = field(default=None, init=False, repr=False)
    _finished: bool = field(default=False, init=False, repr=False)

    @property
    def logical_attempt_id(self) -> str:
        return f"{self.run_id or 'unbound'}:logical:{self.logical_attempt}"

    @property
    def transport_attempt_id(self) -> str:
        return (
            f"{self.run_id or 'unbound'}:logical:{self.logical_attempt}:"
            f"transport:{self.transport_attempt}"
        )

    def _event(self, phase: str, **extra: Any) -> None:
        evidence_digest = _safe_digest(
            {
                "attempt_id": self.attempt_id,
                "phase": phase,
                "request_digest": self.request_digest,
                "trace_id": self.trace_id,
                **extra,
            }
        )
        append_external_model_usage(
            artifact_dir=self.artifact_dir,
            provider=self.provider,
            model=self.observed_model or self.requested_model,
            request_digest=self.request_digest,
            outcome=phase,
            provider_status=self.remote_outcome,
            run_id=self.run_id,
            stage=self.stage,
            section_id=self.section_id,
            logical_attempt=self.logical_attempt,
            transport_attempt=self.transport_attempt,
            retry_reason=self.retry_reason,
            response_id=self.provider_response_id,
            evidence_event=phase,
            attempt_id=self.attempt_id,
            logical_attempt_id=self.logical_attempt_id,
            transport_attempt_id=self.transport_attempt_id,
            trace_id=self.trace_id,
            app_id=self.app_id,
            requested_model=self.requested_model,
            observed_model=self.observed_model,
            local_dispatch_started=self.local_dispatch_started,
            request_bytes_sent=self.request_bytes_sent,
            request_bytes_count=self.request_bytes_count,
            request_bytes_proof=self.request_bytes_proof,
            response_headers_received=self.response_headers_received,
            first_byte_received=self.first_byte_received,
            sdk_response_returned=self.sdk_response_returned,
            http_status_code=self.http_status_code,
            failure_phase=self.failure_phase,
            remote_outcome=self.remote_outcome,
            error_class=self.error_class,
            evidence_digest=evidence_digest,
        )
        if self._span is not None:
            self._span.add_event(
                phase,
                attributes={key: str(value) for key, value in extra.items()},
            )

    def mark_local_dispatch_started(self) -> None:
        if not self.local_dispatch_started:
            self.local_dispatch_started = True
            self._event(LOCAL_DISPATCH_STARTED)

    def mark_request_written(self) -> None:
        """Compatibility witness for older SDK integrations.

        This records only local dispatch, not socket-byte proof.  New transports
        must call :meth:`mark_request_bytes_sent` after a successful write.
        """

        self.local_dispatch_started = True
        self._event("REQUEST_WRITTEN")

    def mark_request_bytes_sent(self, *, byte_count: int, proof_source: str) -> None:
        """Record bytes only when a transport hook supplies explicit proof."""

        if not str(proof_source or "").strip():
            raise ValueError("REQUEST_BYTES_SENT requires a transport proof source")
        if int(byte_count) < 0:
            raise ValueError("REQUEST_BYTES_SENT byte_count must be non-negative")
        self.request_bytes_sent = True
        self.request_bytes_count = int(byte_count)
        self.request_bytes_proof = str(proof_source)
        self._event(
            REQUEST_BYTES_SENT,
            byte_count=self.request_bytes_count,
            proof_source=self.request_bytes_proof,
        )

    def mark_response_headers(
        self, *, status_code: int | None = None, provider_response_id: str = ""
    ) -> None:
        self.response_headers_received = True
        self.http_status_code = status_code
        self.provider_response_id = provider_response_id or self.provider_response_id
        self._event(RESPONSE_HEADERS_RECEIVED)

    def mark_first_byte(self) -> None:
        if not self.first_byte_received:
            self.first_byte_received = True
            self._event(FIRST_BYTE_RECEIVED)

    def mark_sdk_response(
        self, *, observed_model: str = "", provider_response_id: str = ""
    ) -> None:
        """Record SDK completion without inventing header/first-byte boundaries."""

        self.sdk_response_returned = True
        self.observed_model = observed_model or self.observed_model
        self.provider_response_id = provider_response_id or self.provider_response_id
        self._event(SDK_RESPONSE_RETURNED)

    def finish(
        self,
        *,
        observed_model: str = "",
        provider_response_id: str = "",
        http_status_code: int | None = None,
        failure_phase: str = "",
        error_class: str = "",
        remote_outcome: str = "",
    ) -> None:
        if self._finished:
            return
        self.observed_model = observed_model or self.observed_model
        self.provider_response_id = provider_response_id or self.provider_response_id
        if http_status_code is not None:
            self.http_status_code = http_status_code
        self.failure_phase = failure_phase or self.failure_phase
        self.error_class = error_class or self.error_class
        if remote_outcome:
            self.remote_outcome = remote_outcome
        elif (
            self.response_headers_received
            or self.first_byte_received
            or self.sdk_response_returned
            or self.observed_model
            or self.provider_response_id
        ):
            self.remote_outcome = "PROVIDER_RESPONDED"
        elif self.local_dispatch_started:
            self.remote_outcome = REMOTE_OUTCOME_UNKNOWN
        else:
            self.remote_outcome = "NOT_INVOKED"
        self._event(ATTEMPT_FINISHED)
        if self._span is not None:
            for key, value in self.attributes().items():
                if value is not None and value != "":
                    self._span.set_attribute(key, value)
        self._finished = True

    def attributes(self) -> dict[str, Any]:
        return {
            "attempt.id": self.attempt_id,
            "attempt.logical_id": self.logical_attempt_id,
            "attempt.transport_id": self.transport_attempt_id,
            "attempt.logical_index": self.logical_attempt,
            "attempt.transport_index": self.transport_attempt,
            "attempt.retry_reason": self.retry_reason,
            "app.id": self.app_id,
            "run.id": self.run_id,
            "trace.root": self.trace_id,
            "stage": self.stage,
            "section.id": self.section_id,
            "provider": self.provider,
            "model.requested": self.requested_model,
            "model.observed": self.observed_model,
            "request.digest": self.request_digest,
            "local.dispatch_started": self.local_dispatch_started,
            "request.bytes_sent": self.request_bytes_sent,
            "request.bytes_count": self.request_bytes_count,
            "request.bytes_proof": self.request_bytes_proof,
            "response.headers_received": self.response_headers_received,
            "response.first_byte_received": self.first_byte_received,
            "response.sdk_returned": self.sdk_response_returned,
            "response.id": self.provider_response_id,
            "http.status_code": self.http_status_code,
            "failure.phase": self.failure_phase,
            "remote.outcome": self.remote_outcome,
            "error.class": self.error_class,
        }


class _EvidenceHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that proves the first successful socket write."""

    def __init__(self, *args: Any, evidence: ProviderAttempt, **kwargs: Any) -> None:
        self._provider_evidence = evidence
        super().__init__(*args, **kwargs)

    def send(self, data: Any) -> None:
        # ``HTTPConnection.send`` connects (including DNS) and calls
        # ``socket.sendall`` before returning.  Recording after it returns keeps
        # DNS/connect failures from being mislabeled as bytes sent.
        super().send(data)
        if not self._provider_evidence.request_bytes_sent:
            count = len(data) if isinstance(data, (bytes, bytearray, memoryview)) else 0
            self._provider_evidence.mark_request_bytes_sent(
                byte_count=count,
                proof_source="http.client.HTTPConnection.send_after_socket_sendall",
            )


class _EvidenceHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS equivalent; proof is recorded only after TLS socket sendall."""

    def __init__(self, *args: Any, evidence: ProviderAttempt, **kwargs: Any) -> None:
        self._provider_evidence = evidence
        super().__init__(*args, **kwargs)

    def send(self, data: Any) -> None:
        super().send(data)
        if not self._provider_evidence.request_bytes_sent:
            count = len(data) if isinstance(data, (bytes, bytearray, memoryview)) else 0
            self._provider_evidence.mark_request_bytes_sent(
                byte_count=count,
                proof_source="http.client.HTTPSConnection.send_after_socket_sendall",
            )


class _EvidenceHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, evidence: ProviderAttempt) -> None:
        super().__init__()
        self._provider_evidence = evidence

    def http_open(self, request: urllib.request.Request) -> Any:
        evidence = self._provider_evidence

        def connection(host: str, **kwargs: Any) -> _EvidenceHTTPConnection:
            return _EvidenceHTTPConnection(host, evidence=evidence, **kwargs)

        return self.do_open(connection, request)


class _EvidenceHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, evidence: ProviderAttempt) -> None:
        super().__init__()
        self._provider_evidence = evidence

    def https_open(self, request: urllib.request.Request) -> Any:
        evidence = self._provider_evidence

        def connection(host: str, **kwargs: Any) -> _EvidenceHTTPSConnection:
            return _EvidenceHTTPSConnection(host, evidence=evidence, **kwargs)

        return self.do_open(
            connection,
            request,
            context=self._context,
        )


def urlopen_with_transport_evidence(
    request: urllib.request.Request,
    *,
    timeout: float,
    evidence: ProviderAttempt,
) -> Any:
    """Open one URL with request-byte proof bound to ``evidence``.

    Response headers and body boundaries remain the caller's responsibility;
    this function proves only a successful lower-level request write.
    """

    opener = urllib.request.build_opener(
        _EvidenceHTTPHandler(evidence),
        _EvidenceHTTPSHandler(evidence),
    )
    return opener.open(request, timeout=timeout)


@contextlib.contextmanager
def provider_attempt(
    *,
    artifact_dir: str | None,
    run_id: str,
    trace_id: str,
    app_id: str,
    stage: str,
    section_id: str,
    provider: str,
    requested_model: str,
    request_digest: str,
    logical_attempt: int = 1,
    transport_attempt: int = 1,
    retry_reason: str = "",
) -> Iterator[ProviderAttempt]:
    attempt = ProviderAttempt(
        artifact_dir=artifact_dir,
        run_id=run_id,
        trace_id=trace_id,
        app_id=app_id,
        stage=stage,
        section_id=section_id,
        provider=provider,
        requested_model=requested_model,
        request_digest=request_digest,
        logical_attempt=logical_attempt,
        transport_attempt=transport_attempt,
        retry_reason=str(retry_reason or ""),
    )
    tracer = get_verified_tracer("apps_model_telemetry.provider_attempt")
    cm = (
        tracer.start_as_current_span("apps.model.provider_attempt")
        if tracer is not None
        else contextlib.nullcontext(None)
    )
    with cm as span:
        attempt._span = span
        if span is not None:
            for key, value in attempt.attributes().items():
                if value is not None and value != "":
                    span.set_attribute(key, value)
        attempt._event(ATTEMPT_STARTED)
        try:
            yield attempt
        except BaseException as exc:
            inferred_phase = "CLIENT_EXCEPTION"
            if attempt.first_byte_received:
                inferred_phase = "READ_RESPONSE_BODY"
            elif attempt.response_headers_received:
                inferred_phase = "READ_RESPONSE_BODY"
            elif attempt.request_bytes_sent:
                inferred_phase = "WAIT_RESPONSE_HEADERS"
            elif attempt.local_dispatch_started:
                inferred_phase = "CONNECT_OR_DNS"
            attempt.finish(
                failure_phase=attempt.failure_phase or inferred_phase,
                error_class=type(exc).__name__,
            )
            raise
        else:
            attempt.finish()


__all__ = [
    "ATTEMPT_FINISHED",
    "ATTEMPT_STARTED",
    "FIRST_BYTE_RECEIVED",
    "LOCAL_DISPATCH_STARTED",
    "ProviderAttempt",
    "REMOTE_OUTCOME_UNKNOWN",
    "REQUEST_BYTES_SENT",
    "RESPONSE_HEADERS_RECEIVED",
    "SDK_RESPONSE_RETURNED",
    "provider_attempt",
    "urlopen_with_transport_evidence",
]
