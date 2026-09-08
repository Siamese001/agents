from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from apps_model_telemetry.execution_evidence import (
    REMOTE_OUTCOME_UNKNOWN,
    provider_attempt,
    urlopen_with_transport_evidence,
)
from apps_model_telemetry.external_model_usage import (
    LEDGER_FILENAME,
    external_model_usage_scope,
)
from apps_model_telemetry.otel_runtime import (
    OTEL_CHECKPOINT_FILENAME,
    OTEL_ENDPOINT_ENV,
    OTEL_SNAPSHOT_FILE_ENV,
    _trace_exporter_endpoint,
    capture_collector_snapshot,
    current_otel_runtime_status,
    initialize_collector_checkpoint,
    resolve_otel_environment,
    verify_live_collector_receipt,
)
from apps_rg.runtime.providers.external_provider import ExternalProvider
from apps_rg.runtime.providers.provider_gateway import ProviderProfile
from apps_rg.runtime.run_bundle_index import build_integrated_run_bundle_document


def _events(root: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (root / LEDGER_FILENAME).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _clear_otel_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        OTEL_ENDPOINT_ENV,
        OTEL_SNAPSHOT_FILE_ENV,
        "APPS_OTEL_EXPORTER_OTLP_ENDPOINT",
        "APPS_OTEL_COLLECTOR_FILE",
        "OTEL_COLLECTOR_SPANS_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_trace_exporter_endpoint_uses_the_otlp_trace_signal_path() -> None:
    expected = "http://collector:4318/v1/traces"
    assert _trace_exporter_endpoint("http://collector:4318") == expected
    assert _trace_exporter_endpoint("http://collector:4318/") == expected
    assert _trace_exporter_endpoint(expected) == expected


def test_environment_translates_legacy_endpoint_and_rejects_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_otel_environment(monkeypatch)
    monkeypatch.setenv("APPS_OTEL_EXPORTER_OTLP_ENDPOINT", "http://legacy/v1/traces")
    translated = resolve_otel_environment(apply_translation=True)

    assert translated.endpoint == "http://legacy/v1/traces"
    assert translated.endpoint_source == "APPS_OTEL_EXPORTER_OTLP_ENDPOINT"
    assert translated.translations == (
        "APPS_OTEL_EXPORTER_OTLP_ENDPOINT->OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    assert translated.errors == ()
    assert translated.endpoint == __import__("os").environ[OTEL_ENDPOINT_ENV]

    monkeypatch.setenv(OTEL_ENDPOINT_ENV, "http://canonical/v1/traces")
    conflict = resolve_otel_environment()
    assert conflict.errors == ("CONFLICTING_OTEL_EXPORTER_OTLP_ENDPOINT",)


def test_runtime_status_requires_the_installed_global_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_otel_environment(monkeypatch)
    monkeypatch.setenv(OTEL_ENDPOINT_ENV, "http://collector/v1/traces")
    import apps_model_telemetry.otel_runtime as runtime
    from opentelemetry import trace

    class _Processor:
        _span_processors = (object(),)

    class _Provider:
        _active_span_processor = _Processor()

    provider = _Provider()
    monkeypatch.setattr(runtime, "_provider", provider)
    monkeypatch.setattr(runtime, "_provider_endpoint", "http://collector/v1/traces")
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)

    active = current_otel_runtime_status()
    assert active.active is True
    assert active.global_provider_verified is True
    assert active.span_processor_verified is True

    monkeypatch.setattr(trace, "get_tracer_provider", lambda: _Provider())
    mismatched = current_otel_runtime_status()
    assert mismatched.active is False
    assert mismatched.reason == "GLOBAL_TRACER_PROVIDER_MISMATCH"


def test_collector_reader_uses_offsets_and_only_reads_new_documents(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_otel_environment(monkeypatch)
    source = tmp_path / "collector.jsonl"
    first = {"name": "first", "traceId": "trace-1", "spanId": "1"}
    source.write_text(json.dumps(first) + "\n", encoding="utf-8")
    monkeypatch.setenv(OTEL_SNAPSHOT_FILE_ENV, str(source))
    run = tmp_path / "run"
    initialize_collector_checkpoint(artifact_dir=run, start_at_end=False)

    initial = capture_collector_snapshot(
        artifact_dir=run,
        trace_id="trace-1",
        timeout_seconds=0,
        filename="first.json",
        boundary="preflight",
    )
    prior_end = initial["offset_end"]
    second = {"name": "second", "traceId": "trace-2", "spanId": "2"}
    with source.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(second) + "\n")

    incremental = capture_collector_snapshot(
        artifact_dir=run,
        trace_id="trace-2",
        timeout_seconds=0,
        filename="second.json",
        boundary="apps_research_handoff",
    )

    assert initial["status"] == "CAPTURED"
    assert incremental["status"] == "CAPTURED"
    assert incremental["offset_start"] == prior_end
    assert incremental["bytes_read"] < source.stat().st_size
    assert [span["name"] for span in incremental["spans"]] == ["second"]
    assert incremental["rotation_detected"] is False


def test_nested_boundaries_advance_the_run_root_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_otel_environment(monkeypatch)
    source = tmp_path / "collector.jsonl"
    source.write_text(
        json.dumps({"name": "handoff", "traceId": "trace-shared", "spanId": "1"})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(OTEL_SNAPSHOT_FILE_ENV, str(source))
    run = tmp_path / "run"
    initialize_collector_checkpoint(artifact_dir=run, start_at_end=False)

    handoff = capture_collector_snapshot(
        artifact_dir=run / "apps_research",
        trace_id="trace-shared",
        timeout_seconds=0,
        filename="handoff.json",
        boundary="apps_research_handoff",
    )
    first_end = handoff["offset_end"]
    with source.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                {"name": "closeout", "traceId": "trace-shared", "spanId": "2"}
            )
            + "\n"
        )

    closeout = capture_collector_snapshot(
        artifact_dir=run / "terminal" / "closeout",
        trace_id="trace-shared",
        timeout_seconds=0,
        filename="closeout.json",
        boundary="terminal_closeout",
    )

    checkpoint = (run / OTEL_CHECKPOINT_FILENAME).resolve()
    assert handoff["checkpoint_ref"] == str(checkpoint)
    assert closeout["checkpoint_ref"] == str(checkpoint)
    assert closeout["offset_start"] == first_end
    assert [span["name"] for span in closeout["spans"]] == ["closeout"]
    assert not (run / "apps_research" / OTEL_CHECKPOINT_FILENAME).exists()
    assert not (run / "terminal" / "closeout" / OTEL_CHECKPOINT_FILENAME).exists()


def test_collector_reader_detects_truncation_rotation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_otel_environment(monkeypatch)
    source = tmp_path / "collector.jsonl"
    source.write_text(
        json.dumps({"name": "old-long-span", "traceId": "old", "spanId": "1"})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(OTEL_SNAPSHOT_FILE_ENV, str(source))
    run = tmp_path / "run"
    initialize_collector_checkpoint(artifact_dir=run, start_at_end=False)
    capture_collector_snapshot(
        artifact_dir=run, trace_id="old", timeout_seconds=0, filename="old.json"
    )
    source.write_text(
        json.dumps({"name": "new", "traceId": "new", "spanId": "2"}) + "\n",
        encoding="utf-8",
    )

    rotated = capture_collector_snapshot(
        artifact_dir=run, trace_id="new", timeout_seconds=0, filename="new.json"
    )

    assert rotated["status"] == "CAPTURED"
    assert rotated["rotation_detected"] is True
    assert rotated["offset_start"] == 0
    assert rotated["collector_generation"] == 1


def test_connect_failure_never_claims_request_bytes_sent(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        with provider_attempt(
            artifact_dir=str(tmp_path),
            run_id="run-w4",
            trace_id="trace-w4",
            app_id="apps_rg",
            stage="L2.section_generation",
            section_id="competencies",
            provider="external_claude",
            requested_model="claude-test",
            request_digest="a" * 64,
            logical_attempt=1,
            transport_attempt=1,
        ) as evidence:
            evidence.mark_local_dispatch_started()
            raise OSError("DNS lookup failed")

    events = _events(tmp_path)
    assert "REQUEST_WRITTEN" not in {event["outcome"] for event in events}
    assert "REQUEST_BYTES_SENT" not in {event["outcome"] for event in events}
    assert events[-1]["remote_outcome"] == REMOTE_OUTCOME_UNKNOWN
    assert events[-1]["local_dispatch_started"] is True
    assert events[-1]["request_bytes_sent"] is False
    assert events[-1]["failure_phase"] == "CONNECT_OR_DNS"


def test_request_bytes_event_requires_an_explicit_transport_hook(tmp_path: Path) -> None:
    with provider_attempt(
        artifact_dir=str(tmp_path),
        run_id="run-w4",
        trace_id="trace-w4",
        app_id="apps_rg",
        stage="L2.section_generation",
        section_id="competencies",
        provider="external_claude",
        requested_model="claude-test",
        request_digest="b" * 64,
        logical_attempt=2,
        transport_attempt=1,
    ) as evidence:
        evidence.mark_local_dispatch_started()
        with pytest.raises(ValueError):
            evidence.mark_request_bytes_sent(byte_count=10, proof_source="")
        evidence.mark_request_bytes_sent(
            byte_count=10, proof_source="instrumented_socket.sendall"
        )

    events = _events(tmp_path)
    sent = next(event for event in events if event["outcome"] == "REQUEST_BYTES_SENT")
    assert sent["request_bytes_count"] == 10
    assert sent["request_bytes_proof"] == "instrumented_socket.sendall"
    assert sent["transport_attempt_id"].endswith(":logical:2:transport:1")


def test_real_http_socket_write_proves_bytes_sent(tmp_path: Path) -> None:
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with provider_attempt(
            artifact_dir=str(tmp_path),
            run_id="run-real-http",
            trace_id="trace-real-http",
            app_id="apps_rg",
            stage="L2.section_generation",
            section_id="competencies",
            provider="external_openai",
            requested_model="gpt-test",
            request_digest="e" * 64,
            logical_attempt=1,
            transport_attempt=1,
        ) as evidence:
            evidence.mark_local_dispatch_started()
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/v1/responses",
                data=b"{}",
                method="POST",
            )
            with urlopen_with_transport_evidence(
                request,
                timeout=2,
                evidence=evidence,
            ) as response:
                evidence.mark_response_headers(status_code=response.status)
                if response.read():
                    evidence.mark_first_byte()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    events = _events(tmp_path)
    sent = next(event for event in events if event["outcome"] == "REQUEST_BYTES_SENT")
    assert sent["request_bytes_sent"] is True
    assert sent["request_bytes_count"] > 0
    assert sent["request_bytes_proof"].endswith("send_after_socket_sendall")


def test_real_connect_refusal_does_not_claim_bytes_sent(tmp_path: Path) -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    unused_port = probe.getsockname()[1]
    probe.close()

    with pytest.raises(urllib.error.URLError):
        with provider_attempt(
            artifact_dir=str(tmp_path),
            run_id="run-connect-refused",
            trace_id="trace-connect-refused",
            app_id="apps_rg",
            stage="L2.section_generation",
            section_id="competencies",
            provider="external_openai",
            requested_model="gpt-test",
            request_digest="f" * 64,
            logical_attempt=1,
            transport_attempt=1,
        ) as evidence:
            evidence.mark_local_dispatch_started()
            request = urllib.request.Request(
                f"http://127.0.0.1:{unused_port}/v1/responses",
                data=b"{}",
                method="POST",
            )
            urlopen_with_transport_evidence(
                request,
                timeout=0.5,
                evidence=evidence,
            )

    events = _events(tmp_path)
    assert "REQUEST_BYTES_SENT" not in {event["outcome"] for event in events}
    assert events[-1]["request_bytes_sent"] is False
    assert events[-1]["remote_outcome"] == REMOTE_OUTCOME_UNKNOWN
    assert events[-1]["failure_phase"] == "CONNECT_OR_DNS"


def test_real_response_header_timeout_records_bytes_without_inventing_response(
    tmp_path: Path,
) -> None:
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            time.sleep(0.15)

        def log_message(self, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises((TimeoutError, socket.timeout)):
            with provider_attempt(
                artifact_dir=str(tmp_path),
                run_id="run-real-timeout",
                trace_id="trace-real-timeout",
                app_id="apps_rg",
                stage="L2.section_generation",
                section_id="competencies",
                provider="external_openai",
                requested_model="gpt-test",
                request_digest="1" * 64,
                logical_attempt=1,
                transport_attempt=1,
            ) as evidence:
                evidence.mark_local_dispatch_started()
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/slow",
                    data=b"{}",
                    method="POST",
                )
                urlopen_with_transport_evidence(
                    request,
                    timeout=0.03,
                    evidence=evidence,
                )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    finished = _events(tmp_path)[-1]
    assert finished["request_bytes_sent"] is True
    assert finished["response_headers_received"] is False
    assert finished["first_byte_received"] is False
    assert finished["failure_phase"] == "WAIT_RESPONSE_HEADERS"
    assert finished["remote_outcome"] == REMOTE_OUTCOME_UNKNOWN


def test_real_malformed_response_records_true_header_and_body_boundaries(
    tmp_path: Path,
) -> None:
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            payload = b"{not-json"
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(json.JSONDecodeError):
            with provider_attempt(
                artifact_dir=str(tmp_path),
                run_id="run-real-malformed",
                trace_id="trace-real-malformed",
                app_id="apps_rg",
                stage="L2.section_generation",
                section_id="competencies",
                provider="external_openai",
                requested_model="gpt-test",
                request_digest="2" * 64,
                logical_attempt=1,
                transport_attempt=1,
            ) as evidence:
                evidence.mark_local_dispatch_started()
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/malformed",
                    data=b"{}",
                    method="POST",
                )
                with urlopen_with_transport_evidence(
                    request,
                    timeout=1,
                    evidence=evidence,
                ) as response:
                    evidence.mark_response_headers(status_code=response.status)
                    payload = response.read()
                    if payload:
                        evidence.mark_first_byte()
                    json.loads(payload)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    finished = _events(tmp_path)[-1]
    assert finished["request_bytes_sent"] is True
    assert finished["response_headers_received"] is True
    assert finished["first_byte_received"] is True
    assert finished["failure_phase"] == "READ_RESPONSE_BODY"
    assert finished["error_class"] == "JSONDecodeError"


def test_real_transport_retry_is_reconstructable_as_two_distinct_attempts(
    tmp_path: Path,
) -> None:
    class _Handler(BaseHTTPRequestHandler):
        calls = 0

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            type(self).calls += 1
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            if type(self).calls == 1:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            payload = b"{}"
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for transport_attempt in (1, 2):
            try:
                with provider_attempt(
                    artifact_dir=str(tmp_path),
                    run_id="run-real-retry",
                    trace_id="trace-real-retry",
                    app_id="apps_rg",
                    stage="L2.section_generation",
                    section_id="competencies",
                    provider="external_openai",
                    requested_model="gpt-test",
                    request_digest="3" * 64,
                    logical_attempt=1,
                    transport_attempt=transport_attempt,
                ) as evidence:
                    evidence.mark_local_dispatch_started()
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/retry",
                        data=b"{}",
                        method="POST",
                    )
                    with urlopen_with_transport_evidence(
                        request,
                        timeout=1,
                        evidence=evidence,
                    ) as response:
                        evidence.mark_response_headers(status_code=response.status)
                        if response.read():
                            evidence.mark_first_byte()
            except OSError:
                if transport_attempt == 2:
                    raise
                continue
            break
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    finished = [row for row in _events(tmp_path) if row["outcome"] == "ATTEMPT_FINISHED"]
    assert len(finished) == 2
    assert [row["transport_attempt"] for row in finished] == [1, 2]
    assert len({row["attempt_id"] for row in finished}) == 2
    assert len({row["transport_attempt_id"] for row in finished}) == 2
    assert finished[0]["request_bytes_sent"] is True
    assert finished[0]["response_headers_received"] is False
    assert finished[1]["response_headers_received"] is True
    assert finished[1]["first_byte_received"] is True


def test_external_provider_default_transport_uses_real_write_proof(
    tmp_path: Path,
) -> None:
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            payload = json.dumps(
                {
                    "id": "resp-local",
                    "model": "gpt-test",
                    "output_text": "generated",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args) -> None:
            return

    class _Prompt:
        prompt_blocks = ()
        system_preamble = "System"
        user_instruction = "User"

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        provider = ExternalProvider(
            provider_profile=ProviderProfile.EXTERNAL_OPENAI,
            model="gpt-test",
            base_url=f"http://127.0.0.1:{server.server_port}/v1/responses",
            environ={"OPENAI_API_KEY": "test-only"},
        )
        with external_model_usage_scope(
            artifact_dir=tmp_path,
            run_id="run-provider-real-http",
            trace_id="trace-provider-real-http",
            app_id="apps_rg",
            stage="L2.section_generation",
            section_id="competencies",
        ):
            result = provider.generate(_Prompt(), token_budget=20)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.runtime_generation_status == "REAL_LLM"
    events = _events(tmp_path)
    sent = next(event for event in events if event["outcome"] == "REQUEST_BYTES_SENT")
    assert sent["request_bytes_sent"] is True
    assert sent["provider"] == "external_openai"
    finished = next(event for event in events if event["outcome"] == "ATTEMPT_FINISHED")
    assert finished["response_headers_received"] is True
    assert finished["first_byte_received"] is True
    assert finished["observed_model"] == "gpt-test"


def test_sdk_response_does_not_invent_header_or_first_byte_boundaries(
    tmp_path: Path,
) -> None:
    with provider_attempt(
        artifact_dir=str(tmp_path),
        run_id="run-sdk",
        trace_id="trace-sdk",
        app_id="apps_research",
        stage="L2.apps_research_company_brief",
        section_id="company_brief",
        provider="external_openai",
        requested_model="gpt-test",
        request_digest="d" * 64,
        logical_attempt=1,
        transport_attempt=1,
    ) as evidence:
        evidence.mark_local_dispatch_started()
        evidence.mark_sdk_response(
            observed_model="gpt-test-observed", provider_response_id="resp-sdk"
        )

    finished = _events(tmp_path)[-1]
    assert finished["remote_outcome"] == "PROVIDER_RESPONDED"
    assert finished["sdk_response_returned"] is True
    assert finished["response_headers_received"] is False
    assert finished["first_byte_received"] is False


def test_anthropic_stream_retry_has_distinct_transport_attempts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Response:
        status = 200
        headers = {"request-id": "req-2"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            rows = (
                {"type": "message_start", "message": {"model": "claude-test"}},
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "generated"},
                },
                {"type": "message_stop"},
            )
            return iter(
                [f"data: {json.dumps(row)}\n".encode("utf-8") for row in rows]
            )

    calls = 0
    observed_timeouts: list[float] = []

    def _urlopen(_request, timeout):
        nonlocal calls
        observed_timeouts.append(timeout)
        calls += 1
        if calls == 1:
            raise OSError("DNS lookup failed")
        return _Response()

    monkeypatch.setenv("APPS_RG_STREAM_ATTEMPTS", "2")
    monkeypatch.setenv("APPS_RG_STREAM_READ_TIMEOUT_S", "1")
    monkeypatch.setattr(
        "apps_rg.runtime.providers.external_provider.urllib.request.urlopen", _urlopen
    )
    monkeypatch.setattr(
        "apps_rg.runtime.providers.external_provider.time.sleep", lambda _seconds: None
    )
    provider = ExternalProvider(
        provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
        model="claude-test",
        environ={"ANTHROPIC_API_KEY": "test-only"},
    )
    state: dict = {"last_transport_attempt": 0, "attempt_ids": []}
    result = provider._anthropic_messages_transport(
        {
            "model": "claude-test",
            "prompt": "safe digest-only test",
            "max_tokens": 20,
            "temperature": 0.0,
            "timeout_seconds": 1,
            "progress_sink": {},
            "_provider_attempt_context": {
                "artifact_dir": str(tmp_path),
                "run_id": "run-retry",
                "trace_id": "trace-retry",
                "app_id": "apps_rg",
                "stage": "L2.section_generation",
                "section_id": "competencies",
                "request_digest": "c" * 64,
                "logical_attempt": 1,
            },
            "_provider_attempt_state": state,
        }
    )

    assert result["text"] == "generated"
    assert len(observed_timeouts) == 2
    assert all(0 < timeout <= 1 for timeout in observed_timeouts)
    assert state["last_transport_attempt"] == 2
    assert len(state["attempt_ids"]) == len(set(state["attempt_ids"])) == 2
    events = _events(tmp_path)
    finished = [event for event in events if event["outcome"] == "ATTEMPT_FINISHED"]
    assert [event["transport_attempt"] for event in finished] == [1, 2]
    assert finished[0]["remote_outcome"] == REMOTE_OUTCOME_UNKNOWN
    assert finished[0]["request_bytes_sent"] is False
    assert finished[1]["response_headers_received"] is True
    assert finished[1]["first_byte_received"] is True


def test_repeated_provider_calls_allocate_distinct_logical_attempts(
    tmp_path: Path,
) -> None:
    class _Prompt:
        prompt_blocks = ()
        system_preamble = "System"
        user_instruction = "User"

    provider = ExternalProvider(
        provider_profile=ProviderProfile.EXTERNAL_OPENAI,
        model="gpt-test",
        transport=lambda _request: {
            "text": "generated",
            "model": "gpt-test-observed",
        },
        environ={"OPENAI_API_KEY": "test-only"},
    )
    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-logical-retry",
        trace_id="trace-logical-retry",
        app_id="apps_rg",
        stage="L2.section_generation",
        section_id="competencies",
    ):
        provider.generate(_Prompt(), token_budget=20)
        provider.generate(_Prompt(), token_budget=20)

    started = [
        event for event in _events(tmp_path) if event["outcome"] == "ATTEMPT_STARTED"
    ]
    assert [event["logical_attempt"] for event in started] == [1, 2]
    assert len({event["logical_attempt_id"] for event in started}) == 2
    assert len({event["transport_attempt_id"] for event in started}) == 2


def test_run_bundle_reconciles_runtime_and_collector_activation(tmp_path: Path) -> None:
    run = tmp_path / "artifacts" / "apps_rg" / "runs" / "run-w4"
    run.mkdir(parents=True)
    (run / "otel_runtime_receipt.json").write_text(
        json.dumps(
            {
                "active": True,
                "reason": "VERIFIED_ACTIVE",
                "global_provider_verified": True,
            }
        ),
        encoding="utf-8",
    )
    (run / "otel_collector_preflight.json").write_text(
        json.dumps({"status": "PASS", "reason": "COLLECTOR_MARKER_CAPTURED"}),
        encoding="utf-8",
    )

    consistent = build_integrated_run_bundle_document(
        tmp_path, run, run_id="run-w4", correlation_id="trace-w4"
    )
    assert consistent["telemetry_activation"] == {
        "status": "CONSISTENT",
        "runtime_active": True,
        "runtime_reason": "VERIFIED_ACTIVE",
        "global_provider_verified": True,
        "collector_preflight_status": "PASS",
        "collector_preflight_reason": "COLLECTOR_MARKER_CAPTURED",
    }

    (run / "otel_collector_preflight.json").write_text(
        json.dumps({"status": "BLOCKED", "reason": "COLLECTOR_MARKER_NOT_CAPTURED"}),
        encoding="utf-8",
    )
    inconsistent = build_integrated_run_bundle_document(
        tmp_path, run, run_id="run-w4", correlation_id="trace-w4"
    )
    assert inconsistent["telemetry_activation"]["status"] == "INCONSISTENT"


def test_preflight_marker_is_captured_only_after_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_otel_environment(monkeypatch)
    source = tmp_path / "collector.jsonl"
    source.write_text(
        json.dumps({"name": "stale", "traceId": "old", "spanId": "0"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(OTEL_SNAPSHOT_FILE_ENV, str(source))
    monkeypatch.setenv(OTEL_ENDPOINT_ENV, "http://collector/v1/traces")
    import apps_model_telemetry.otel_runtime as runtime

    class _Span:
        marker = ""

        def set_attribute(self, key, value):
            if key == "trace.root":
                self.marker = str(value)

    class _SpanContext:
        def __init__(self):
            self.span = _Span()

        def __enter__(self):
            return self.span

        def __exit__(self, *_args):
            with source.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    json.dumps(
                        {
                            "name": "apps.model.collector_preflight",
                            "spanId": "1",
                            "attributes": {"trace.root": self.span.marker},
                        }
                    )
                    + "\n"
                )
            return False

    class _Tracer:
        def start_as_current_span(self, _name):
            return _SpanContext()

    verified = runtime.OTelRuntimeStatus(
        True,
        "http://collector/v1/traces",
        "VERIFIED_ACTIVE",
        "test.Provider",
        True,
        True,
    )
    monkeypatch.setattr(runtime, "current_otel_runtime_status", lambda: verified)
    monkeypatch.setattr(runtime, "get_verified_tracer", lambda _name: _Tracer())
    monkeypatch.setattr(runtime, "flush_otel_runtime", lambda: True)

    receipt = verify_live_collector_receipt(
        artifact_dir=tmp_path / "run", timeout_seconds=0
    )
    snapshot = json.loads(
        (tmp_path / "run" / "otel_preflight_snapshot.json").read_text(
            encoding="utf-8"
        )
    )

    assert receipt["status"] == "PASS"
    assert snapshot["offset_start"] > 0
    assert [span["name"] for span in snapshot["spans"]] == [
        "apps.model.collector_preflight"
    ]
