"""External API provider implementation for apps_rg Wave 10A.

External providers are selectable for parity work, but they are not the default.
This class is deliberately transport-injectable: production wiring can provide a
real HTTP transport later, while tests can prove the profile path works without
network or secrets.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import urlparse

from apps_rg.runtime.env_bootstrap import bootstrap_process_env_if_needed
from apps_rg.runtime.model_capabilities import try_model_capabilities
from apps_rg.runtime.providers.provider_gateway import ProviderGatewayError, ProviderProfile
from apps_rg.runtime.providers.provider_attempt_spans import (
    build_provider_attempt_span,
    summarize_provider_attempt_spans,
)
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_model_telemetry.execution_evidence import (
    provider_attempt,
    urlopen_with_transport_evidence,
)
from apps_model_telemetry.external_model_usage import (
    allocate_provider_logical_attempt,
    append_external_model_usage,
    current_external_model_usage_context,
)
ExternalTransport = Callable[[dict[str, Any]], dict[str, Any]]

DEFAULT_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_STDLIB_URLOPEN = urllib.request.urlopen


def _urlopen_with_attempt_evidence(
    request: urllib.request.Request,
    *,
    timeout: float,
    evidence: Any,
) -> Any:
    """Use the instrumented product transport while preserving injected tests."""

    current = urllib.request.urlopen
    if current is not _STDLIB_URLOPEN:
        return current(request, timeout=timeout)
    return urlopen_with_transport_evidence(
        request,
        timeout=timeout,
        evidence=evidence,
    )


def _openai_model_omits_temperature(model: Any) -> bool:
    capabilities = try_model_capabilities(str(model or ""))
    return bool(
        capabilities
        and capabilities.provider == "openai"
        and capabilities.temperature_parameter == "omit"
    )
DEFAULT_EXTERNAL_PROVIDER_TIMEOUT_SECONDS = 90.0
ANTHROPIC_SYSTEM_ONLY_USER_PROMPT = "Return the requested JSON object now."
# Shared upper safety bound for ANY external section provider wall-clock budget.
# The competencies lane may opt into a longer-than-default budget, but it should
# fail closed in minutes, not sit on an API call for an evaluation-era 1000s.
DEFAULT_EXTERNAL_PROVIDER_TIMEOUT_MAX_SECONDS = 300.0


def anthropic_model_omits_temperature(model: Any) -> bool:
    """Return True for Anthropic models whose Messages API rejects temperature."""
    capabilities = try_model_capabilities(str(model or ""))
    return bool(
        capabilities
        and capabilities.provider == "anthropic"
        and capabilities.temperature_parameter == "omit"
    )


def anthropic_model_uses_adaptive_thinking(model: Any) -> bool:
    """Return True for Anthropic models that need adaptive thinking effort control."""
    capabilities = try_model_capabilities(str(model or ""))
    return bool(
        capabilities
        and capabilities.provider == "anthropic"
        and capabilities.thinking_mode == "adaptive"
    )


def apply_anthropic_temperature_capability(body: dict[str, Any]) -> dict[str, Any]:
    """Remove temperature from Anthropic payloads for models that reject it."""
    if anthropic_model_omits_temperature(body.get("model")):
        body.pop("temperature", None)
    return body


def apply_anthropic_adaptive_thinking_config(
    body: dict[str, Any],
    environ: Mapping[str, str] | None = None,
    *,
    effort: Any = None,
) -> dict[str, Any]:
    """Constrain Sonnet 5 adaptive thinking so compact JSON calls leave budget for text."""
    if not anthropic_model_uses_adaptive_thinking(body.get("model")):
        return body
    env = os.environ if environ is None else environ
    resolved_effort = str(effort or env.get("APPS_RG_ANTHROPIC_EFFORT") or "low").strip().lower()
    if resolved_effort not in {"low", "medium", "high", "xhigh"}:
        resolved_effort = "low"
    body.setdefault("thinking", {"type": "adaptive", "display": "omitted"})
    output_config = body.get("output_config")
    if not isinstance(output_config, dict):
        output_config = {}
    if effort is None:
        output_config.setdefault("effort", resolved_effort)
    else:
        # The per-section provider-profile SSOT wins over payload-local or process-wide defaults.
        output_config["effort"] = resolved_effort
    body["output_config"] = output_config
    return body


def external_provider_timeout_max_s() -> float:
    """Shared ceiling (seconds) for external section provider wall-clock budgets.

    Defaults to ``DEFAULT_EXTERNAL_PROVIDER_TIMEOUT_MAX_SECONDS`` (300s); a
    malformed/empty env value falls back to that default rather than failing the
    run. Hard-bounded to [30, 300]s so neither a typo nor a hostile value can
    turn a section call into an extended hang.
    """
    raw = os.environ.get("APPS_RG_EXTERNAL_PROVIDER_TIMEOUT_MAX_SECONDS", "").strip()
    if not raw:
        return DEFAULT_EXTERNAL_PROVIDER_TIMEOUT_MAX_SECONDS
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_EXTERNAL_PROVIDER_TIMEOUT_MAX_SECONDS
    if val <= 0:
        return DEFAULT_EXTERNAL_PROVIDER_TIMEOUT_MAX_SECONDS
    return max(30.0, min(val, 300.0))


def resolve_external_section_timeout_s(
    requested: Any,
    *,
    default: float = DEFAULT_EXTERNAL_PROVIDER_TIMEOUT_SECONDS,
) -> float:
    """Resolve an external section provider call's effective wall-clock budget (seconds).

    Centralized policy: an operator-set budget is honored up to the shared
    ``external_provider_timeout_max_s`` bound. Invalid / non-positive requests
    fall back to ``default``. Replaces the prior per-call
    ``_coerce_timeout_seconds`` that defaulted-but-never-bounded.
    """
    ceiling = external_provider_timeout_max_s()
    try:
        val = float(requested)
    except (TypeError, ValueError):
        val = float(default)
    if val <= 0:
        val = float(default)
    # Small positive budgets are honored verbatim; zero/negative already fell
    # back to ``default`` above.
    return min(val, ceiling)


def _prompt_text(compiled_prompt: Any) -> str:
    blocks = getattr(compiled_prompt, "prompt_blocks", ()) or ()
    if blocks:
        return "\n".join(f"{getattr(b, 'role', '?')}: {getattr(b, 'content', '')}" for b in blocks)
    return "\n".join(
        part
        for part in (
            str(getattr(compiled_prompt, "system_preamble", "") or ""),
            str(getattr(compiled_prompt, "user_instruction", "") or ""),
        )
        if part
    ).strip()


def _prompt_messages(compiled_prompt: Any) -> list[dict[str, str]]:
    blocks = getattr(compiled_prompt, "prompt_blocks", ()) or ()
    messages: list[dict[str, str]] = []
    for block in blocks:
        role = str(getattr(block, "role", "") or "").strip().lower()
        content = str(getattr(block, "content", "") or "")
        if not content:
            continue
        if role not in {"system", "user", "assistant"}:
            role = "user"
        messages.append({"role": role, "content": content})
    return messages


def _anthropic_system_and_messages(request: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    raw_messages = request.get("messages")
    system_parts: list[str] = []
    messages: list[dict[str, str]] = []
    if isinstance(raw_messages, list):
        for item in raw_messages:
            if not isinstance(item, Mapping):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "")
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
            elif role in {"user", "assistant"}:
                messages.append({"role": role, "content": content})
            else:
                messages.append({"role": "user", "content": content})
    if not messages and system_parts:
        messages = [{"role": "user", "content": ANTHROPIC_SYSTEM_ONLY_USER_PROMPT}]
    elif not messages:
        messages = [{"role": "user", "content": str(request.get("prompt") or "")}]
    system = "\n\n".join(part for part in system_parts if part).strip()
    return system or "Return compact JSON only.", messages


def _validate_native_anthropic_payload(payload: Mapping[str, Any]) -> None:
    gateway_owned = {
        "model",
        "max_tokens",
        "temperature",
        "stream",
        "base_url",
        "timeout_seconds",
    }
    collisions = sorted(k for k in payload if str(k) in gateway_owned)
    if collisions:
        joined = ", ".join(collisions)
        raise ProviderGatewayError(f"Native Anthropic payload includes gateway-owned key(s): {joined}")


def _contains_anthropic_cache_control(value: Any) -> bool:
    """Return whether a native payload carries an Anthropic cache directive."""
    if isinstance(value, Mapping):
        if isinstance(value.get("cache_control"), Mapping):
            return True
        return any(_contains_anthropic_cache_control(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_anthropic_cache_control(item) for item in value)
    return False


def _is_direct_anthropic_messages_endpoint(url: Any) -> bool:
    """Whether ``url`` is Anthropic's native HTTPS Messages endpoint."""
    parsed = urlparse(str(url or "").strip())
    return (
        parsed.scheme.lower() == "https"
        and str(parsed.hostname or "").lower() == "api.anthropic.com"
        and parsed.path.rstrip("/") == "/v1/messages"
    )


def _anthropic_body_from_native_request(request: dict[str, Any], provider_model: str) -> dict[str, Any]:
    native = request.get("anthropic_payload")
    if not isinstance(native, Mapping):
        raise ProviderGatewayError("Native Anthropic payload must be a mapping")
    _validate_native_anthropic_payload(native)
    body = dict(native)
    body["model"] = str(request.get("model") or provider_model)
    body["max_tokens"] = int(request.get("max_tokens") or 900)
    body["temperature"] = float(request.get("temperature") or 0.0)
    body["stream"] = True
    if not isinstance(body.get("messages"), list):
        raise ProviderGatewayError("Native Anthropic payload requires a messages list")
    if not (isinstance(body.get("system"), (str, list))):
        raise ProviderGatewayError("Native Anthropic payload requires a string or block-list system field")
    return body


def _coerce_timeout_seconds(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return DEFAULT_EXTERNAL_PROVIDER_TIMEOUT_SECONDS
    if timeout <= 0:
        return DEFAULT_EXTERNAL_PROVIDER_TIMEOUT_SECONDS
    return timeout


def _format_timeout_seconds(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.3f}".rstrip("0").rstrip(".")


class ExternalProvider:
    """External API provider wrapper; functional when supplied a transport."""

    def __init__(
        self,
        *,
        provider_profile: ProviderProfile = ProviderProfile.EXTERNAL_OPENAI,
        model: str = "",
        api_key_env_var: str | None = None,
        base_url: str | None = None,
        transport: ExternalTransport | None = None,
        supports_anthropic_prompt_caching: bool | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if provider_profile not in (
            ProviderProfile.EXTERNAL_CLAUDE,
            ProviderProfile.EXTERNAL_OPENAI,
            ProviderProfile.EXTERNAL_DEFAULT,
        ):
            raise ProviderGatewayError(f"ExternalProvider cannot serve profile={provider_profile.value}")
        self.provider_profile = provider_profile
        self.environ = os.environ if environ is None else environ
        self._uses_process_environ = self.environ is os.environ
        if not str(model or "").strip():
            raise ProviderGatewayError(
                f"ExternalProvider requires an explicit model for profile={provider_profile.value}; "
                "resolve the section pin before constructing the provider."
            )
        self.model = str(model).strip()
        self.api_key_env_var = api_key_env_var or (
            "ANTHROPIC_API_KEY"
            if provider_profile == ProviderProfile.EXTERNAL_CLAUDE
            else "OPENAI_API_KEY"
        )
        self.base_url = base_url or ""
        self.transport = transport
        self._supports_anthropic_prompt_caching = supports_anthropic_prompt_caching

    def _default_transport(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.provider_profile == ProviderProfile.EXTERNAL_CLAUDE:
            return self._anthropic_messages_transport(request)
        return self._openai_responses_transport(request)

    def _native_anthropic_prompt_cache_capability(
        self,
        request: Mapping[str, Any],
    ) -> tuple[bool, str]:
        """Resolve whether cache directives may cross this provider boundary.

        The native Anthropic schema is intentionally not sent to an injected
        adapter or a non-Anthropic endpoint unless that adapter declares support.
        A normal direct Messages API request remains enabled by default.
        """
        if self.provider_profile != ProviderProfile.EXTERNAL_CLAUDE:
            return False, "provider_is_not_anthropic"
        if self._supports_anthropic_prompt_caching is not None:
            return (
                bool(self._supports_anthropic_prompt_caching),
                "explicit_adapter_capability",
            )
        if self.transport is not None:
            return False, "custom_transport_not_confirmed"
        endpoint = str(
            request.get("base_url") or self.base_url or DEFAULT_ANTHROPIC_MESSAGES_URL
        )
        if _is_direct_anthropic_messages_endpoint(endpoint):
            return True, "direct_anthropic_messages_api"
        return False, "non_anthropic_messages_endpoint"

    def _transport_attempt_evidence(
        self, request: Mapping[str, Any], *, transport_attempt: int
    ):
        context = request.get("_provider_attempt_context")
        context = context if isinstance(context, Mapping) else {}
        return provider_attempt(
            artifact_dir=str(context.get("artifact_dir") or "") or None,
            run_id=str(context.get("run_id") or ""),
            trace_id=str(context.get("trace_id") or ""),
            app_id=str(context.get("app_id") or "apps_rg"),
            stage=str(context.get("stage") or "L2.section_generation"),
            section_id=str(context.get("section_id") or ""),
            provider=self.provider_profile.value,
            requested_model=self.model,
            request_digest=str(context.get("request_digest") or ""),
            logical_attempt=int(context.get("logical_attempt") or 1),
            transport_attempt=transport_attempt,
        )

    def _anthropic_messages_transport(self, request: dict[str, Any]) -> dict[str, Any]:
        # STREAM the Messages API (SSE). Non-streaming holds the connection idle for the whole
        # server-side generation (~30s for a multi-thousand-token output); in the long-lived run
        # process that idle connection is dropped and the read hangs until timeout, while a tiny
        # output (no idle) and a fresh process both succeed. Streaming keeps tokens flowing, so the
        # connection never idles and the read returns normally. (Diagnosed 2026-06-16: in-process
        # probe — non-stream 2800-tok hangs; identical stream=True returns in ~34s/79 chunks.)
        native_payload = request.get("anthropic_payload")
        if isinstance(native_payload, Mapping):
            body = _anthropic_body_from_native_request(request, self.model)
        else:
            system, messages = _anthropic_system_and_messages(request)
            body = {
                "model": str(request.get("model") or self.model),
                "max_tokens": int(request.get("max_tokens") or 900),
                "temperature": float(request.get("temperature") or 0.0),
                "system": system,
                "messages": messages,
                "stream": True,
            }
        apply_anthropic_temperature_capability(body)
        apply_anthropic_adaptive_thinking_config(
            body,
            self.environ,
            effort=request.get("reasoning_effort"),
        )
        url = str(request.get("base_url") or self.base_url or DEFAULT_ANTHROPIC_MESSAGES_URL)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": str(self.environ.get(self.api_key_env_var) or ""),
            "anthropic-version": "2023-06-01",
        }
        data = json.dumps(body).encode("utf-8")
        # Keep one provider response alive for almost the full governed wall budget.  Replaying a
        # request after response headers or a first byte can duplicate billable remote work and,
        # for slower reasoning models, an 18-second socket timeout repeatedly discarded healthy
        # HTTP 200 streams before their first text delta.
        wall_budget = resolve_external_section_timeout_s(request.get("timeout_seconds"))
        internal_budget = max(1.0, wall_budget - min(5.0, wall_budget * 0.1))
        per_read = float(
            os.environ.get("APPS_RG_STREAM_READ_TIMEOUT_S") or internal_budget
        )
        per_read = max(1.0, min(per_read, internal_budget))
        attempts_override = os.environ.get("APPS_RG_STREAM_ATTEMPTS", "").strip()
        if attempts_override:
            _attempts = max(1, min(int(attempts_override), 2))
        else:
            _attempts = 2
        # W2 transport-progress instrumentation: a slow-but-active streamed response must be
        # observable as PROGRESSING, not indistinguishable from a stall. ``progress_sink`` (an
        # optional dict the caller owns) is mutated IN PLACE as chunks arrive, so even when the
        # wall-clock wrapper abandons this thread on timeout the caller can still read how far the
        # stream got (last_progress_at / chars received). All times: monotonic deltas from t0.
        progress = request.get("progress_sink")
        progress = progress if isinstance(progress, dict) else None
        started_wall = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        deadline = t0 + internal_budget
        if progress is not None:
            progress.update(
                {
                    "started_at": started_wall,
                    "first_byte_after_s": None,
                    "last_progress_after_s": None,
                    "chunk_count": 0,
                    "raw_output_chars": 0,
                    "completed": False,
                }
            )
        text_parts: list[str] = []
        resolved_model = str(body["model"])
        usage: dict[str, Any] = {}
        stop_reason: str | None = None
        stop_details: dict[str, Any] | None = None
        first_byte_after_s: float | None = None
        chunk_count = 0
        last_progress_after_s: float | None = None
        attempt_state = request.get("_provider_attempt_state")
        attempt_state = attempt_state if isinstance(attempt_state, dict) else {}
        for _attempt in range(_attempts):
            text_parts = []
            resolved_model = str(body["model"])
            usage = {}
            stop_reason = None
            stop_details = None
            chunk_count = 0
            first_byte_after_s = None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Anthropic stream exhausted its internal wall budget")
            try:
                with self._transport_attempt_evidence(
                    request, transport_attempt=_attempt + 1
                ) as evidence:
                    attempt_state["last_transport_attempt"] = _attempt + 1
                    attempt_state.setdefault("attempt_ids", []).append(evidence.attempt_id)
                    evidence.mark_local_dispatch_started()
                    http_req = urllib.request.Request(
                        url, data=data, headers=headers, method="POST"
                    )
                    try:
                        response_context = _urlopen_with_attempt_evidence(
                            http_req,
                            timeout=min(per_read, remaining),
                            evidence=evidence,
                        )
                    except HTTPError as exc:
                        evidence.mark_response_headers(status_code=int(exc.code))
                        evidence.failure_phase = "HTTP_RESPONSE"
                        raise
                    with response_context as resp:
                        response_headers = getattr(resp, "headers", None)
                        response_id = ""
                        if response_headers is not None:
                            response_id = str(
                                response_headers.get("request-id")
                                or response_headers.get("x-request-id")
                                or ""
                            )
                        evidence.mark_response_headers(
                            status_code=getattr(resp, "status", None),
                            provider_response_id=response_id,
                        )
                        for raw_line in resp:
                            if not evidence.first_byte_received:
                                evidence.mark_first_byte()
                            line = raw_line.decode("utf-8", errors="replace").strip()
                            if not line.startswith("data:"):
                                continue
                            payload = line[5:].strip()
                            if not payload or payload == "[DONE]":
                                continue
                            try:
                                event = json.loads(payload)
                            except json.JSONDecodeError:
                                continue
                            now_after = time.monotonic() - t0
                            if first_byte_after_s is None:
                                first_byte_after_s = now_after
                                if progress is not None:
                                    progress["first_byte_after_s"] = round(now_after, 4)
                            chunk_count += 1
                            last_progress_after_s = now_after
                            etype = event.get("type")
                            if etype == "message_start":
                                msg = event.get("message") or {}
                                resolved_model = str(msg.get("model") or resolved_model)
                                if isinstance(msg.get("usage"), dict):
                                    usage.update(msg["usage"])
                            elif etype == "content_block_delta":
                                delta = event.get("delta") or {}
                                if delta.get("type") == "text_delta":
                                    text_parts.append(str(delta.get("text") or ""))
                            elif etype == "message_delta":
                                delta = event.get("delta") or {}
                                if isinstance(delta, dict):
                                    stop_reason = (
                                        str(delta.get("stop_reason") or "") or stop_reason
                                    )
                                    raw_stop_details = delta.get("stop_details")
                                    if isinstance(raw_stop_details, dict):
                                        stop_details = dict(raw_stop_details)
                                if isinstance(event.get("usage"), dict):
                                    usage.update(event["usage"])
                            elif etype == "message_stop":
                                break
                            elif etype == "error":
                                err = event.get("error") or {}
                                raise ProviderGatewayError(
                                    "anthropic stream error: "
                                    f"{err.get('type')}: {err.get('message')}"
                                )
                            if progress is not None:
                                progress["chunk_count"] = chunk_count
                                progress["last_progress_after_s"] = round(now_after, 4)
                                progress["raw_output_chars"] = sum(len(p) for p in text_parts)
                    evidence.finish(observed_model=resolved_model)
            except HTTPError:
                raise
            except (
                TimeoutError,
                OSError,
                json.JSONDecodeError,
                ValueError,
                TypeError,
                RuntimeError,
                LookupError,
                AttributeError,
                KeyError,
                ConnectionError,
                ProviderGatewayError,
            ):
                response_started = bool(
                    evidence.response_headers_received or evidence.first_byte_received
                )
                remaining = deadline - time.monotonic()
                if not response_started and _attempt + 1 < _attempts and remaining > 0:
                    time.sleep(min(0.25 * (2 ** _attempt), 2.0, remaining))
                    continue
                raise
            break
        text = "".join(text_parts).strip()
        completed_after_s = time.monotonic() - t0
        timing = {
            "started_at": started_wall,
            "first_byte_after_s": round(first_byte_after_s, 4) if first_byte_after_s is not None else None,
            "last_progress_after_s": (
                round(last_progress_after_s, 4) if last_progress_after_s is not None else None
            ),
            "completed_after_s": round(completed_after_s, 4),
            "chunk_count": chunk_count,
            "read_iterations": chunk_count,
            "raw_output_chars": len(text),
            "stream": True,
        }
        if progress is not None:
            progress.update(
                {
                    "completed": True,
                    "completed_after_s": round(completed_after_s, 4),
                    "chunk_count": chunk_count,
                    "raw_output_chars": len(text),
                }
            )
        return {
            "text": text,
            "model": resolved_model,
            "transport_timing": timing,
            "raw_response": {
                "model": resolved_model,
                "usage": usage,
                "stop_reason": stop_reason,
                "stop_details": stop_details,
                "stream": True,
                "transport_timing": timing,
                "content": [{"type": "text", "text": text}],
            },
        }

    def _openai_responses_transport(self, request: dict[str, Any]) -> dict[str, Any]:
        prompt = str(request.get("prompt") or "")
        timeout_seconds = _coerce_timeout_seconds(request.get("timeout_seconds"))
        body = {
            "model": str(request.get("model") or self.model),
            "input": prompt,
            "max_output_tokens": int(request.get("max_tokens") or 900),
        }
        reasoning_effort = str(request.get("reasoning_effort") or "").strip().lower()
        if reasoning_effort:
            body["reasoning"] = {"effort": reasoning_effort}
        if not _openai_model_omits_temperature(body["model"]):
            body["temperature"] = float(request.get("temperature") or 0.0)
        url = str(request.get("base_url") or self.base_url or DEFAULT_OPENAI_RESPONSES_URL)
        attempt_state = request.get("_provider_attempt_state")
        attempt_state = attempt_state if isinstance(attempt_state, dict) else {}
        with self._transport_attempt_evidence(request, transport_attempt=1) as evidence:
            attempt_state["last_transport_attempt"] = 1
            attempt_state.setdefault("attempt_ids", []).append(evidence.attempt_id)
            evidence.mark_local_dispatch_started()
            http_req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.environ.get(self.api_key_env_var) or ''}",
                },
                method="POST",
            )
            try:
                response_context = _urlopen_with_attempt_evidence(
                    http_req,
                    timeout=timeout_seconds,
                    evidence=evidence,
                )
            except HTTPError as exc:
                evidence.mark_response_headers(status_code=int(exc.code))
                evidence.failure_phase = "HTTP_RESPONSE"
                raise
            with response_context as resp:
                response_headers = getattr(resp, "headers", None)
                response_id = ""
                if response_headers is not None:
                    response_id = str(
                        response_headers.get("x-request-id")
                        or response_headers.get("request-id")
                        or ""
                    )
                evidence.mark_response_headers(
                    status_code=getattr(resp, "status", None),
                    provider_response_id=response_id,
                )
                raw_body = resp.read()
                if raw_body:
                    evidence.mark_first_byte()
                data = json.loads(raw_body.decode("utf-8"))
            evidence.finish(
                observed_model=str(data.get("model") or body["model"]),
                provider_response_id=str(
                    data.get("id") or data.get("response_id") or response_id
                ),
            )
        text = str(data.get("output_text") or "")
        if not text:
            parts: list[str] = []
            for item in data.get("output") or []:
                if not isinstance(item, dict):
                    continue
                for block in item.get("content") or []:
                    if isinstance(block, dict) and block.get("type") in {"output_text", "text"}:
                        parts.append(str(block.get("text") or ""))
            text = "\n".join(p for p in parts if p).strip()
        return {
            "text": text,
            "model": data.get("model") or body["model"],
            "raw_response": data,
        }

    def _transport_with_wall_clock_timeout(
        self,
        transport: ExternalTransport,
        request: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        # Optional global wall-clock floor (env). Workaround for a per-process download throttle
        # seen in the long-lived run where streamed generations trickle far slower than in a fresh
        # process; a larger budget lets them complete. Unset by default (no behavior change).
        _floor = float(os.environ.get("APPS_RG_PROVIDER_WALLCLOCK_FLOOR_S") or 0.0)
        if _floor > float(timeout_seconds):
            timeout_seconds = _floor
        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def _runner() -> None:
            try:
                result_queue.put(("ok", transport(request)), block=False)
            except HTTPError as exc:
                result_queue.put(("http_error", exc), block=False)
            except (
                TimeoutError,
                OSError,
                json.JSONDecodeError,
                ValueError,
                TypeError,
                RuntimeError,
                LookupError,
                AttributeError,
                KeyError,
                ConnectionError,
                ProviderGatewayError,
            ) as exc:
                result_queue.put(("error", exc), block=False)

        worker = threading.Thread(
            target=_runner,
            name=f"apps-rg-{self.provider_profile.value}-provider-call",
            daemon=True,
        )
        worker.start()
        worker.join(timeout_seconds)
        if worker.is_alive():
            formatted = _format_timeout_seconds(timeout_seconds)
            raise TimeoutError(f"External provider wall-clock timeout after {formatted}s")
        try:
            kind, payload = result_queue.get_nowait()
        except queue.Empty as exc:
            raise TimeoutError("External provider returned without a transport result") from exc
        if kind == "http_error":
            raise payload
        if kind == "error":
            raise ProviderGatewayError(f"{type(payload).__name__}: {payload}") from payload
        return payload

    def generate(
        self,
        compiled_prompt: Any,
        *,
        token_budget: int,
        temperature: float = 0.7,
        timeout_seconds: int | float | None = None,
    ) -> ProviderResult:
        attempt_started_at_utc = datetime.now(timezone.utc).isoformat()
        usage_context = current_external_model_usage_context()
        logical_attempt = allocate_provider_logical_attempt()
        attempt_state: dict[str, Any] = {
            "last_transport_attempt": 0,
            "attempt_ids": [],
        }
        cache_transport_state: dict[str, Any] | None = None
        reasoning_effort = str(getattr(compiled_prompt, "reasoning_effort", None) or "").strip().lower()
        capabilities = try_model_capabilities(self.model)
        if reasoning_effort and capabilities and not capabilities.supports_reasoning_effort(
            reasoning_effort
        ):
            raise ProviderGatewayError(f"Invalid section generation reasoning effort: {reasoning_effort!r}")

        def _provider_response_with_attempt(
            payload: dict[str, Any] | None,
            *,
            provider_attempted: bool,
            provider_available: bool,
            runtime_generation_status: str,
            exact_provider_error: str | None,
            model: str | None = None,
        ) -> dict[str, Any]:
            response = dict(payload or {})
            if cache_transport_state is not None:
                response.setdefault(
                    "anthropic_prompt_cache_transport",
                    dict(cache_transport_state),
                )
            if reasoning_effort:
                response.setdefault("reasoning_effort", reasoning_effort)
            response.setdefault("attempt_started_at_utc", attempt_started_at_utc)
            response["attempt_completed_at_utc"] = datetime.now(timezone.utc).isoformat()
            transport_response = response.get("transport_response")
            nested_timing = (
                transport_response.get("transport_timing")
                if isinstance(transport_response, Mapping)
                else None
            )
            span = build_provider_attempt_span(
                attempt_kind="requested",
                attempt_index=logical_attempt,
                provider=self.provider_profile.value,
                model=str(model or self.model),
                provider_attempted=provider_attempted,
                provider_available=provider_available,
                runtime_generation_status=runtime_generation_status,
                started_at_utc=str(response.get("attempt_started_at_utc") or ""),
                completed_at_utc=str(response.get("attempt_completed_at_utc") or ""),
                exact_provider_error=exact_provider_error,
                timeout_seconds=provider_timeout_seconds,
                token_budget=int(token_budget),
                temperature=float(temperature),
                request_digest=str(response.get("request_digest") or ""),
                transport_progress=response.get("transport_progress")
                if isinstance(response.get("transport_progress"), Mapping)
                else None,
                transport_timing=response.get("transport_timing")
                if isinstance(response.get("transport_timing"), Mapping)
                else nested_timing,
            )
            response["provider_attempt_spans"] = [span]
            response["provider_attempt_timing_summary"] = summarize_provider_attempt_spans([span])
            response["logical_attempt"] = logical_attempt
            response["transport_attempt"] = int(
                attempt_state.get("last_transport_attempt") or 0
            )
            response["transport_attempt_ids"] = list(
                attempt_state.get("attempt_ids") or []
            )
            return response

        prompt = _prompt_text(compiled_prompt)
        messages = _prompt_messages(compiled_prompt)
        request_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        def _record_usage(
            *,
            outcome: str,
            provider_status: str,
            raw_usage: Mapping[str, Any] | None = None,
            response_id: str | None = None,
            model_name: str | None = None,
        ) -> None:
            """Do not let observability storage alter the generation outcome."""
            try:
                append_external_model_usage(
                    provider=self.provider_profile.value,
                    model=str(model_name or self.model),
                    request_digest=request_digest,
                    outcome=outcome,
                    provider_status=provider_status,
                    usage=raw_usage,
                    response_id=response_id,
                    logical_attempt=logical_attempt,
                    transport_attempt=int(
                        attempt_state.get("last_transport_attempt") or 0
                    ),
                )
            except OSError:
                # A full or unavailable artifact volume must not turn a completed
                # model call into a different resume-generation outcome.
                return
        # W1: resolve the effective wall-clock budget through the shared policy.
        provider_timeout_seconds = resolve_external_section_timeout_s(timeout_seconds)
        # W2: a caller-owned progress sink the streamed transport mutates in place, so a timeout
        # error can report how far the (now-abandoned) stream actually got.
        progress_sink: dict[str, Any] = {}
        request = {
            "provider_profile": self.provider_profile.value,
            "model": self.model,
            "prompt": prompt,
            "messages": messages,
            "max_tokens": int(token_budget),
            "temperature": float(temperature),
            "base_url": self.base_url,
            "timeout_seconds": provider_timeout_seconds,
            "progress_sink": progress_sink,
            "_provider_attempt_context": {
                **usage_context,
                "app_id": usage_context.get("app_id") or "apps_rg",
                "stage": usage_context.get("stage") or "L2.section_generation",
                "request_digest": request_digest,
                "logical_attempt": logical_attempt,
            },
            "_provider_attempt_state": attempt_state,
        }
        native_cache_seed: Mapping[str, Any] | None = None
        if reasoning_effort:
            request["reasoning_effort"] = reasoning_effort
        if self.provider_profile == ProviderProfile.EXTERNAL_CLAUDE:
            native_anthropic_payload = getattr(compiled_prompt, "anthropic_payload", None)
            if isinstance(native_anthropic_payload, Mapping):
                if _contains_anthropic_cache_control(native_anthropic_payload):
                    cache_supported, cache_reason = self._native_anthropic_prompt_cache_capability(
                        request
                    )
                    cache_transport_state = {
                        "cache_directives_requested": True,
                        "cache_directives_transmitted": cache_supported,
                        "capability_source": cache_reason,
                    }
                    if cache_supported:
                        request["anthropic_payload"] = dict(native_anthropic_payload)
                else:
                    request["anthropic_payload"] = dict(native_anthropic_payload)
            candidate_cache_seed = getattr(compiled_prompt, "anthropic_cache_receipt_seed", None)
            if isinstance(candidate_cache_seed, Mapping):
                native_cache_seed = dict(candidate_cache_seed)
        if self._uses_process_environ:
            bootstrap_process_env_if_needed(self.environ)
        if not str(self.environ.get(self.api_key_env_var) or "").strip():
            error = f"External provider credential unavailable: {self.api_key_env_var}"
            return ProviderResult(
                provider_requested=self.provider_profile.value,
                provider_attempted=False,
                provider_available=False,
                exact_provider_error=error,
                runtime_generation_status="BLOCKED",
                model=self.model,
                raw_model_output="",
                provider_response=_provider_response_with_attempt(
                    {
                        "provider_profile": self.provider_profile.value,
                        "anthropic_cache_receipt_seed": native_cache_seed,
                    },
                    provider_attempted=False,
                    provider_available=False,
                    runtime_generation_status="BLOCKED",
                    exact_provider_error=error,
                ),
            )
        transport = self.transport or self._default_transport
        try:
            if self.transport is None:
                response = self._transport_with_wall_clock_timeout(
                    transport,
                    request,
                    timeout_seconds=provider_timeout_seconds,
                )
            else:
                with self._transport_attempt_evidence(
                    request, transport_attempt=1
                ) as evidence:
                    attempt_state["last_transport_attempt"] = 1
                    attempt_state["attempt_ids"].append(evidence.attempt_id)
                    evidence.mark_local_dispatch_started()
                    transport_request = {
                        key: value
                        for key, value in request.items()
                        if not str(key).startswith("_")
                    }
                    response = self._transport_with_wall_clock_timeout(
                        transport,
                        transport_request,
                        timeout_seconds=provider_timeout_seconds,
                    )
                    raw_response = (
                        response.get("raw_response")
                        if isinstance(response.get("raw_response"), Mapping)
                        else {}
                    )
                    evidence.mark_sdk_response(
                        observed_model=str(response.get("model") or self.model),
                        provider_response_id=str(
                            raw_response.get("id")
                            or raw_response.get("response_id")
                            or ""
                        ),
                    )
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            error = f"External provider HTTP {exc.code}: {detail or exc.reason}"
            _record_usage(outcome=f"HTTP_{exc.code}", provider_status="BLOCKED")
            return ProviderResult(
                provider_requested=self.provider_profile.value,
                provider_attempted=True,
                provider_available=False,
                exact_provider_error=error,
                runtime_generation_status="BLOCKED",
                model=self.model,
                raw_model_output="",
                provider_response=_provider_response_with_attempt(
                    {"transport_progress": dict(progress_sink)} if progress_sink else {},
                    provider_attempted=True,
                    provider_available=False,
                    runtime_generation_status="BLOCKED",
                    exact_provider_error=error,
                ),
            )
        except (ProviderGatewayError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            # Surface last-observed progress so a timeout reads as "slow, got N chars at +Ms",
            # not an opaque stall. progress_sink is populated in place by the streamed transport.
            prog = dict(progress_sink)
            progress_note = ""
            if prog:
                progress_note = (
                    f" [last_progress_after_s={prog.get('last_progress_after_s')}"
                    f", chars_received={prog.get('raw_output_chars')}"
                    f", chunk_count={prog.get('chunk_count')}]"
                )
            error = f"External provider call failed: {type(exc).__name__}: {exc}{progress_note}"
            _record_usage(outcome=type(exc).__name__.upper(), provider_status="BLOCKED")
            return ProviderResult(
                provider_requested=self.provider_profile.value,
                provider_attempted=True,
                provider_available=False,
                exact_provider_error=error,
                runtime_generation_status="BLOCKED",
                model=self.model,
                raw_model_output="",
                provider_response=_provider_response_with_attempt(
                    {"transport_progress": prog} if prog else {},
                    provider_attempted=True,
                    provider_available=False,
                    runtime_generation_status="BLOCKED",
                    exact_provider_error=error,
                ),
            )
        text = str(response.get("text") or response.get("content") or "")
        resolved_model = str(response.get("model") or self.model)
        if not text.strip():
            raw_response = response.get("raw_response") if isinstance(response.get("raw_response"), Mapping) else {}
            usage = raw_response.get("usage") if isinstance(raw_response, Mapping) else {}
            _record_usage(
                outcome="EMPTY_RESPONSE",
                provider_status="BLOCKED",
                raw_usage=usage if isinstance(usage, Mapping) else None,
                response_id=str(raw_response.get("id") or raw_response.get("response_id") or ""),
                model_name=resolved_model,
            )
            output_details = usage.get("output_tokens_details") if isinstance(usage, Mapping) else None
            stop_reason = raw_response.get("stop_reason") if isinstance(raw_response, Mapping) else None
            detail_parts = []
            if stop_reason:
                detail_parts.append(f"stop_reason={stop_reason}")
            if isinstance(output_details, Mapping):
                detail_parts.append(
                    "output_tokens_details="
                    + json.dumps(dict(output_details), sort_keys=True, separators=(",", ":"))
                )
            detail = f" ({'; '.join(detail_parts)})" if detail_parts else ""
            error = f"External provider returned empty text{detail}"
            return ProviderResult(
                provider_requested=self.provider_profile.value,
                provider_attempted=True,
                provider_available=False,
                exact_provider_error=error,
                runtime_generation_status="BLOCKED",
                model=resolved_model,
                raw_model_output="",
                provider_response=_provider_response_with_attempt(
                    {
                        "provider_profile": self.provider_profile.value,
                        "model": resolved_model,
                        "request_digest": request_digest,
                        "effective_timeout_seconds": provider_timeout_seconds,
                        "transport_timing": response.get("transport_timing"),
                        "transport_response": response,
                        "anthropic_cache_receipt_seed": request.get("anthropic_cache_receipt_seed"),
                    },
                    provider_attempted=True,
                    provider_available=False,
                    runtime_generation_status="BLOCKED",
                    exact_provider_error=error,
                    model=resolved_model,
                ),
            )
        raw_response = response.get("raw_response") if isinstance(response.get("raw_response"), Mapping) else {}
        raw_usage = raw_response.get("usage") if isinstance(raw_response, Mapping) else {}
        _record_usage(
            outcome="SUCCESS",
            provider_status="REAL_LLM",
            raw_usage=raw_usage if isinstance(raw_usage, Mapping) else None,
            response_id=str(raw_response.get("id") or raw_response.get("response_id") or ""),
            model_name=resolved_model,
        )
        return ProviderResult(
            provider_requested=self.provider_profile.value,
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model=resolved_model,
            raw_model_output=text,
            provider_response=_provider_response_with_attempt(
                {
                    "provider_profile": self.provider_profile.value,
                    "model": resolved_model,
                    "request_digest": request_digest,
                    "effective_timeout_seconds": provider_timeout_seconds,
                    "transport_timing": response.get("transport_timing"),
                    "transport_response": response,
                    "anthropic_cache_receipt_seed": request.get("anthropic_cache_receipt_seed"),
                },
                provider_attempted=True,
                provider_available=True,
                runtime_generation_status="REAL_LLM",
                exact_provider_error=None,
                model=resolved_model,
            ),
        )


__all__ = [
    "ExternalProvider",
    "ExternalTransport",
    "anthropic_model_omits_temperature",
    "anthropic_model_uses_adaptive_thinking",
    "apply_anthropic_adaptive_thinking_config",
    "apply_anthropic_temperature_capability",
    "external_provider_timeout_max_s",
    "resolve_external_section_timeout_s",
]
