from __future__ import annotations

import ast
import io
import json
import socket
import types
import urllib.error
from pathlib import Path

import pytest

from apps_model_telemetry.external_model_usage import (
    LEDGER_FILENAME,
    external_model_usage_scope,
)
from apps_research.config.model_pins import (
    apps_rg_handoff_judge_pin,
    company_brief_generation_pin,
)
from apps_research.integrations.provider_gateway import (
    AppsResearchProviderGatewayError,
    invoke_gemini_handoff_judge,
    invoke_openai_company_brief,
)


def _ledger(root: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (root / LEDGER_FILENAME).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _openai_client(*, model: str, choices: list, usage: dict | None = None):
    response = types.SimpleNamespace(
        id="openai-response-w5",
        model=model,
        choices=choices,
        usage=usage,
    )

    class _Completions:
        def create(self, **_kwargs):
            return response

    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_Completions())
    )


def _choice(text: str):
    return types.SimpleNamespace(message=types.SimpleNamespace(content=text))


def test_openai_success_is_written_only_after_all_validations(tmp_path: Path) -> None:
    pin = company_brief_generation_pin()
    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-w5",
        trace_id="trace-w5",
        app_id="apps_research",
        stage="L2.apps_research_company_brief",
    ):
        result = invoke_openai_company_brief(
            messages=[{"role": "user", "content": "digest-only fixture"}],
            max_completion_tokens=100,
            application_validator=json.loads,
            client_factory=lambda: _openai_client(
                model=pin.model,
                choices=[_choice('{"ok": true}')],
                usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
            ),
        )

    assert result.output == {"ok": True}
    assert result.receipt["overall_success"] is True
    assert result.receipt["model_pin_valid"] is True
    terminal = [row for row in _ledger(tmp_path) if row.get("gateway_id")]
    assert len(terminal) == 1
    assert terminal[0]["outcome"] == "SUCCESS"
    assert terminal[0]["overall_success"] is True


@pytest.mark.parametrize(
    ("observed_model", "choices", "validator", "reason", "schema", "pin_valid", "app_valid"),
    [
        ("PIN", [], lambda text: text, "RESPONSE_SCHEMA_VALIDATION", False, False, False),
        ("wrong-model", [_choice("valid")], lambda text: text, "MODEL_PIN_VALIDATION", True, False, False),
        ("PIN", [_choice("not-json")], json.loads, "APPLICATION_OUTPUT_VALIDATION", True, True, False),
    ],
)
def test_openai_invalid_response_never_writes_success(
    tmp_path: Path,
    observed_model: str,
    choices: list,
    validator,
    reason: str,
    schema: bool,
    pin_valid: bool,
    app_valid: bool,
) -> None:
    pin = company_brief_generation_pin()
    resolved_model = pin.model if observed_model == "PIN" else observed_model
    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-w5-fail",
        trace_id="trace-w5-fail",
        app_id="apps_research",
        stage="L2.apps_research_company_brief",
    ):
        with pytest.raises(AppsResearchProviderGatewayError) as raised:
            invoke_openai_company_brief(
                messages=[{"role": "user", "content": "digest-only fixture"}],
                max_completion_tokens=100,
                application_validator=validator,
                client_factory=lambda: _openai_client(
                    model=resolved_model,
                    choices=choices,
                ),
            )

    receipt = raised.value.receipt
    assert receipt["validation_reason"] == reason
    assert receipt["transport_response_received"] is True
    assert receipt["response_schema_valid"] is schema
    assert receipt["model_pin_valid"] is pin_valid
    assert receipt["application_output_valid"] is app_valid
    assert receipt["overall_success"] is False
    terminal = [row for row in _ledger(tmp_path) if row.get("gateway_id")]
    assert len(terminal) == 1
    assert terminal[0]["outcome"] != "SUCCESS"
    assert terminal[0]["overall_success"] is False


def test_gemini_invalid_application_output_never_writes_success(tmp_path: Path) -> None:
    pin = apps_rg_handoff_judge_pin()
    raw = {
        "responseId": "gemini-response-w5",
        "modelVersion": pin.model,
        "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1},
        "candidates": [],
    }

    class _Response:
        status = 200
        headers = {"x-request-id": "gemini-response-w5"}

        def read(self) -> bytes:
            return json.dumps(raw).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> bool:
            return False

    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-gemini-w5",
        trace_id="trace-gemini-w5",
        app_id="apps_research",
        stage="L2.X2_research_semantic_gate",
    ):
        with pytest.raises(AppsResearchProviderGatewayError) as raised:
            invoke_gemini_handoff_judge(
                url="https://example.invalid/gemini",
                body=b"{}",
                method="POST",
                headers={},
                timeout=1.0,
                urlopen=lambda *_args, **_kwargs: _Response(),
                application_validator=lambda _response: (_ for _ in ()).throw(
                    ValueError("response had no text part")
                ),
            )

    assert raised.value.receipt["response_schema_valid"] is True
    assert raised.value.receipt["model_pin_valid"] is True
    assert raised.value.receipt["application_output_valid"] is False
    assert all(row["outcome"] != "SUCCESS" for row in _ledger(tmp_path))


def test_gemini_response_body_transport_error_has_terminal_failure(
    tmp_path: Path,
) -> None:
    class _Response:
        status = 200
        headers = {"x-request-id": "gemini-response-read-error"}

        def read(self) -> bytes:
            raise OSError("connection reset while reading response")

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> bool:
            return False

    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-gemini-read-fail",
        trace_id="trace-gemini-read-fail",
        app_id="apps_research",
        stage="L2.X2_research_semantic_gate",
    ):
        with pytest.raises(AppsResearchProviderGatewayError) as raised:
            invoke_gemini_handoff_judge(
                url="https://example.invalid/gemini",
                body=b"{}",
                method="POST",
                headers={},
                timeout=1.0,
                urlopen=lambda *_args, **_kwargs: _Response(),
                application_validator=lambda response: response,
            )

    assert raised.value.receipt["validation_reason"] == "READ_RESPONSE_BODY"
    assert raised.value.receipt["transport_response_received"] is True
    assert raised.value.receipt["response_schema_valid"] is False
    assert raised.value.receipt["overall_success"] is False
    terminal = [row for row in _ledger(tmp_path) if row.get("gateway_id")]
    assert len(terminal) == 1
    assert terminal[0]["outcome"] == "READ_RESPONSE_BODY"


def test_gemini_retries_header_timeout_with_one_logical_attempt(tmp_path: Path) -> None:
    pin = apps_rg_handoff_judge_pin()
    calls = {"count": 0}
    delays: list[float] = []

    class _Response:
        status = 200
        headers = {"x-request-id": "gemini-retry-success"}

        def read(self) -> bytes:
            return json.dumps(
                {
                    "responseId": "gemini-retry-success",
                    "modelVersion": pin.model,
                    "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1},
                    "candidates": [{"content": {"parts": [{"text": "{\"ok\":true}"}]}}],
                }
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> bool:
            return False

    def flaky_urlopen(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise socket.timeout("injected header timeout")
        return _Response()

    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-gemini-retry",
        trace_id="trace-gemini-retry",
        app_id="apps_research",
        stage="X3",
    ):
        result = invoke_gemini_handoff_judge(
            url="https://example.invalid/gemini",
            body=b"{}",
            method="POST",
            headers={},
            timeout=1.0,
            urlopen=flaky_urlopen,
            application_validator=lambda response: response["candidates"][0]["content"]["parts"][0]["text"],
            max_transport_attempts=2,
            retry_backoff_base_seconds=1.0,
            retry_backoff_max_seconds=3.0,
            sleep=delays.append,
            uniform=lambda _low, high: high,
        )

    assert result.output == '{"ok":true}'
    assert result.receipt["transport_attempt_count"] == 2
    assert result.receipt["retry_count"] == 1
    assert calls["count"] == 2
    assert delays == [3.0]
    terminal = [row for row in _ledger(tmp_path) if row.get("gateway_id")]
    assert [row["transport_attempt"] for row in terminal] == [1, 2]
    assert len({row["logical_attempt_id"] for row in terminal}) == 1
    assert terminal[0]["remote_outcome"] == "REMOTE_OUTCOME_UNKNOWN"
    assert terminal[0]["overall_success"] is False
    assert terminal[1]["retry_reason"] == "retry_after_wait_response_headers"
    assert terminal[1]["overall_success"] is True


@pytest.mark.parametrize("status_code", [400, 401])
def test_gemini_does_not_retry_request_or_authentication_failure(
    tmp_path: Path,
    status_code: int,
) -> None:
    calls = {"count": 0}

    def unauthorized(*_args, **_kwargs):
        calls["count"] += 1
        raise urllib.error.HTTPError(
            "https://example.invalid/gemini",
            status_code,
            "Bad Request" if status_code == 400 else "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"bad credential"}'),
        )

    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-gemini-auth",
        trace_id="trace-gemini-auth",
        app_id="apps_research",
        stage="X3",
    ):
        with pytest.raises(AppsResearchProviderGatewayError) as raised:
            invoke_gemini_handoff_judge(
                url="https://example.invalid/gemini",
                body=b"{}",
                method="POST",
                headers={},
                timeout=1.0,
                urlopen=unauthorized,
                application_validator=lambda response: response,
                max_transport_attempts=2,
                sleep=lambda _delay: pytest.fail("authentication failures must not retry"),
            )

    assert calls["count"] == 1
    assert raised.value.receipt["transport_attempt_count"] == 1
    assert raised.value.receipt["retry_count"] == 0
    terminal = [row for row in _ledger(tmp_path) if row.get("gateway_id")]
    assert len(terminal) == 1
    assert terminal[0]["validation_reason"] == "HTTP_RESPONSE"


def test_gemini_exhausted_header_timeouts_remain_fail_closed(tmp_path: Path) -> None:
    calls = {"count": 0}

    def always_timeout(*_args, **_kwargs):
        calls["count"] += 1
        raise socket.timeout("injected persistent timeout")

    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-gemini-timeout",
        trace_id="trace-gemini-timeout",
        app_id="apps_research",
        stage="X3",
    ):
        with pytest.raises(AppsResearchProviderGatewayError) as raised:
            invoke_gemini_handoff_judge(
                url="https://example.invalid/gemini",
                body=b"{}",
                method="POST",
                headers={},
                timeout=1.0,
                urlopen=always_timeout,
                application_validator=lambda response: response,
                max_transport_attempts=2,
                retry_backoff_base_seconds=0.0,
                retry_backoff_max_seconds=0.0,
            )

    assert calls["count"] == 2
    assert raised.value.receipt["transport_attempt_count"] == 2
    assert raised.value.receipt["retry_count"] == 1
    terminal = [row for row in _ledger(tmp_path) if row.get("gateway_id")]
    assert [row["transport_attempt"] for row in terminal] == [1, 2]
    assert all(row["overall_success"] is False for row in terminal)
    assert all(row["remote_outcome"] == "REMOTE_OUTCOME_UNKNOWN" for row in terminal)


@pytest.mark.parametrize(
    ("raw_body", "expected_reason"),
    [
        (
            json.dumps(
                {
                    "responseId": "wrong-model",
                    "modelVersion": "unexpected-model",
                    "candidates": [{"content": {"parts": [{"text": "valid"}]}}],
                }
            ).encode("utf-8"),
            "MODEL_PIN_VALIDATION",
        ),
        (b"not-json", "RESPONSE_SCHEMA_VALIDATION"),
    ],
)
def test_gemini_never_retries_model_or_schema_validation_failure(
    tmp_path: Path,
    raw_body: bytes,
    expected_reason: str,
) -> None:
    calls = {"count": 0}

    class _Response:
        status = 200
        headers = {"x-request-id": "validation-failure"}

        def read(self) -> bytes:
            return raw_body

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> bool:
            return False

    def invalid_response(*_args, **_kwargs):
        calls["count"] += 1
        return _Response()

    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-gemini-validation",
        trace_id="trace-gemini-validation",
        app_id="apps_research",
        stage="X3",
    ):
        with pytest.raises(AppsResearchProviderGatewayError) as raised:
            invoke_gemini_handoff_judge(
                url="https://example.invalid/gemini",
                body=b"{}",
                method="POST",
                headers={},
                timeout=1.0,
                urlopen=invalid_response,
                application_validator=lambda response: response,
                max_transport_attempts=2,
                sleep=lambda _delay: pytest.fail("validation failures must not retry"),
            )

    assert calls["count"] == 1
    assert raised.value.receipt["validation_reason"] == expected_reason
    assert raised.value.receipt["transport_attempt_count"] == 1


def test_apps_research_model_calls_exist_only_in_the_approved_gateway() -> None:
    source_root = Path(__file__).resolve().parents[3] / "src" / "apps_research"
    forbidden: list[str] = []
    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [str(node.module or "")]
                )
                provider_sdk = any(
                    name == "openai"
                    or name.startswith("openai.")
                    or name == "anthropic"
                    or name.startswith("anthropic.")
                    or name.startswith("google.genai")
                    or name.startswith("google.generativeai")
                    for name in imported
                )
                if provider_sdk and relative != "integrations/llm_client.py":
                    forbidden.append(f"{relative}:{node.lineno}:provider_sdk_import")
            if not isinstance(node, ast.Call):
                continue
            rendered = ast.unparse(node.func)
            model_call = rendered.endswith(
                (
                    "chat.completions.create",
                    "responses.create",
                    "models.generate_content",
                    "generate_content",
                )
            )
            if model_call and relative != "integrations/provider_gateway.py":
                forbidden.append(f"{relative}:{node.lineno}:{rendered}")
            if rendered in {"urllib.request.urlopen", "urlopen"} and relative not in {
                "integrations/provider_gateway.py",
                "integrations/search_retrieval.py",
                "integrations/searxng_readiness.py",
            }:
                forbidden.append(f"{relative}:{node.lineno}:{rendered}")
    assert forbidden == []
