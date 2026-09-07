"""Provider-neutral section-lane model calls.

Older apps_rg lanes still build OpenAI-compatible ``messages`` payloads for the
local PROVIDER_MODEL slice. This helper keeps the payload shape intact while letting the
same requests route through ``ProviderGateway`` for external profiles.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.providers.availability_fallback import (
    maybe_retry_claude_availability_same_provider,
)
from apps_rg.runtime.providers.anthropic_prompt_cache import (
    anthropic_prompt_cache_enabled,
    anthropic_prompt_cache_telemetry_enabled,
    build_cache_receipt_from_usage,
    build_disabled_cache_receipt,
)
from apps_rg.runtime.providers.anthropic_section_cache_payload import (
    build_anthropic_section_cache_payload,
)
from apps_rg.runtime.providers.external_provider import ExternalProvider
from apps_rg.runtime.providers.provider_gateway import ProviderGateway, ProviderProfile, normalize_provider_profile
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.section_model_limits import (
    external_openai_generation_model,
    resolve_section_generation_effort,
    resolve_section_generation_model,
)
from apps_rg.runtime.model_token_governor import reserve_apps_rg_model_tokens
from apps_model_telemetry.external_model_usage import (
    append_external_model_usage,
    external_model_usage_scope,
)
from apps_model_telemetry.exact_response_reuse import (
    ExactResponseReuseError,
    build_exact_request_identity,
    build_reuse_receipt,
    exact_response_reuse_enabled,
    lookup_exact_response,
    store_exact_response,
)


@dataclass(frozen=True)
class _PromptBlock:
    role: str
    content: str


@dataclass(frozen=True)
class _CompiledMessagesPrompt:
    prompt_blocks: tuple[_PromptBlock, ...]
    compilation_hash: str
    request_id: str
    run_id: str
    trace_id: str
    anthropic_payload: dict[str, Any] | None = None
    anthropic_cache_receipt_seed: dict[str, Any] | None = None
    anthropic_cache_strategy: str | None = None
    reasoning_effort: str | None = None


def build_section_provider_gateway(
    claude_model: str | None = None,
    openai_model: str | None = None,
) -> ProviderGateway:
    """Section provider gateway.

    ``claude_model`` pins the EXTERNAL_CLAUDE provider's generation model for this call.
    ``openai_model`` mirrors that for section-specific OpenAI generation pins. At least one
    explicit model must be supplied; there is no provider-level model fallback.
    """
    providers: dict[ProviderProfile, ExternalProvider] = {}
    if str(claude_model or "").strip():
        providers[ProviderProfile.EXTERNAL_CLAUDE] = ExternalProvider(
            provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
            model=str(claude_model).strip(),
        )
    if str(openai_model or "").strip():
        providers[ProviderProfile.EXTERNAL_OPENAI] = ExternalProvider(
            provider_profile=ProviderProfile.EXTERNAL_OPENAI,
            model=str(openai_model).strip(),
        )
    if not providers:
        raise ValueError("build_section_provider_gateway requires at least one explicit model")
    return ProviderGateway(providers)


def _compiled_prompt_from_payload(
    provider_payload: dict[str, Any],
    *,
    run_id: str | None,
    anthropic_payload: dict[str, Any] | None = None,
    anthropic_cache_receipt_seed: dict[str, Any] | None = None,
    anthropic_cache_strategy: str | None = None,
    reasoning_effort: str | None = None,
) -> _CompiledMessagesPrompt:
    messages = provider_payload.get("messages") or []
    blocks: list[_PromptBlock] = []
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "user")
            content = str(msg.get("content") or "")
            if content:
                blocks.append(_PromptBlock(role=role, content=content))
    if not blocks:
        blocks.append(_PromptBlock(role="user", content=str(provider_payload.get("prompt") or "")))
    return _CompiledMessagesPrompt(
        prompt_blocks=tuple(blocks),
        compilation_hash=str(provider_payload.get("prompt_hash") or ""),
        request_id=str(provider_payload.get("request_id") or ""),
        run_id=str(run_id or provider_payload.get("run_id") or ""),
        trace_id=str(
            provider_payload.get("trace_root")
            or provider_payload.get("trace_id")
            or ""
        ),
        anthropic_payload=anthropic_payload,
        anthropic_cache_receipt_seed=anthropic_cache_receipt_seed,
        anthropic_cache_strategy=anthropic_cache_strategy,
        reasoning_effort=reasoning_effort,
    )


def _extract_anthropic_usage(result: ProviderResult) -> Mapping[str, Any] | None:
    response = result.provider_response if isinstance(result.provider_response, Mapping) else {}
    transport_response = (
        response.get("transport_response")
        if isinstance(response.get("transport_response"), Mapping)
        else {}
    )
    raw_response = (
        transport_response.get("raw_response")
        if isinstance(transport_response.get("raw_response"), Mapping)
        else {}
    )
    usage = raw_response.get("usage") if isinstance(raw_response.get("usage"), Mapping) else None
    return usage


def _resolve_anthropic_cache_payload(
    provider_payload: dict[str, Any],
    *,
    profile: ProviderProfile,
    model: str | None,
    section_id: str | None,
    run_id: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    if profile != ProviderProfile.EXTERNAL_CLAUDE or not anthropic_prompt_cache_enabled():
        return None, None, None
    explicit_payload = provider_payload.get("anthropic_payload")
    explicit_seed = provider_payload.get("anthropic_cache_receipt_seed")
    explicit_strategy = provider_payload.get("anthropic_cache_strategy")
    if isinstance(explicit_payload, Mapping):
        seed = dict(explicit_seed) if isinstance(explicit_seed, Mapping) else {}
        seed.setdefault("provider", ProviderProfile.EXTERNAL_CLAUDE.value)
        seed.setdefault("model", str(model or provider_payload.get("model") or ""))
        seed.setdefault("section_id", str(section_id or ""))
        seed.setdefault("cache_enabled", True)
        seed.setdefault("cache_strategy", str(explicit_strategy or "explicit_native_anthropic_payload"))
        return dict(explicit_payload), seed, str(seed.get("cache_strategy") or explicit_strategy or "")

    compiled_artifact = provider_payload.get("compiled_prompt_artifact")
    source_messages = provider_payload.get("messages")
    messages = source_messages if isinstance(source_messages, list) else None
    if compiled_artifact is None and not messages:
        return None, None, None
    rendered = build_anthropic_section_cache_payload(
        section_id=str(section_id or ""),
        model=str(model or provider_payload.get("model") or ""),
        compiled_prompt_artifact=compiled_artifact,
        messages=messages,
        workload_kind=provider_payload.get("anthropic_workload_kind"),
        run_id=run_id or provider_payload.get("run_id"),
        prompt_hash=str(provider_payload.get("prompt_hash") or ""),
        input_payload_hash=str(provider_payload.get("input_payload_hash") or ""),
    )
    return rendered.anthropic_payload, rendered.cache_receipt_seed, rendered.cache_strategy


def _write_provider_cache_receipt(
    artifact_dir: Path | None,
    receipt: Mapping[str, Any],
) -> None:
    if artifact_dir is None:
        return
    if not (anthropic_prompt_cache_enabled() or anthropic_prompt_cache_telemetry_enabled()):
        return
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "provider_cache_receipt.json").write_text(
        json.dumps(dict(receipt), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _cache_directive_suppression_reason(result: ProviderResult) -> str | None:
    """Return the native-adapter reason when cache directives never left Apps RG."""
    response = result.provider_response if isinstance(result.provider_response, Mapping) else {}
    state = response.get("anthropic_prompt_cache_transport")
    if not isinstance(state, Mapping):
        return None
    if (
        state.get("cache_directives_requested") is True
        and state.get("cache_directives_transmitted") is False
    ):
        return str(state.get("capability_source") or "native_cache_transport_not_confirmed")
    return None


def _with_cache_receipt(
    result: ProviderResult,
    *,
    profile: ProviderProfile,
    model: str | None,
    section_id: str | None,
    seed: Mapping[str, Any] | None = None,
    artifact_dir: Path | None = None,
) -> ProviderResult:
    suppression_reason = _cache_directive_suppression_reason(result)
    if seed is not None and anthropic_prompt_cache_enabled() and suppression_reason is None:
        receipt = build_cache_receipt_from_usage(
            seed=seed,
            provider=profile.value,
            model=str(result.model or model or ""),
            section_id=section_id,
            usage=_extract_anthropic_usage(result),
        )
    else:
        receipt = build_disabled_cache_receipt(
            provider=profile.value,
            model=str(model or result.model or ""),
            section_id=section_id,
        )
        if suppression_reason is not None:
            receipt["cache_requested"] = True
            receipt["cache_suppressed_reason"] = suppression_reason
    response = dict(result.provider_response or {})
    response.setdefault("provider_cache_receipt", receipt)
    result.provider_response = response
    result.prompt_cache_receipt = receipt
    _write_provider_cache_receipt(artifact_dir, receipt)
    return result


def _exact_response_reuse_requested(provider_payload: Mapping[str, Any]) -> bool:
    """Whether this caller declares one response interchangeable with a retry.

    Self-consistency and other sampling paths must never set this flag: their
    multiple requests are intentionally independent even when much of the
    surrounding context is shared.
    """
    workload = str(provider_payload.get("anthropic_workload_kind") or "").strip().upper()
    # These calls are intentional independent samples.  A repeat is signal for
    # the selector, not an accidental replay, even if another field happens to
    # be byte-for-byte identical.
    if workload == "SELF_CONSISTENCY" or "sc_path_index" in provider_payload:
        return False
    raw = provider_payload.get("exact_response_reuse")
    return raw is True or str(raw or "").strip().upper() == "IDEMPOTENT"


def _blocked_exact_response_reuse_result(
    *,
    profile: ProviderProfile,
    model: str | None,
    request_digest: str,
    detail: str,
) -> ProviderResult:
    return ProviderResult(
        provider_requested=profile.value,
        provider_attempted=False,
        provider_available=False,
        exact_provider_error=f"Exact-response reuse cache invalid: {detail}",
        runtime_generation_status="BLOCKED",
        model=str(model or ""),
        raw_model_output="",
        provider_response={"request_digest": request_digest},
    )


def _restore_exact_response_result(
    cached_result: Mapping[str, Any],
    *,
    identity: Any,
    source_event_digest: str,
) -> ProviderResult:
    """Restore a cached result without obscuring that no transport ran now."""
    try:
        result = ProviderResult(**dict(cached_result))
    except TypeError as exc:
        raise ExactResponseReuseError("cached provider result does not match the provider contract") from exc
    response = dict(result.provider_response or {})
    response["exact_response_reuse"] = build_reuse_receipt(
        identity=identity,
        source_event_digest=source_event_digest,
        transport_executed_this_invocation=False,
    )
    result.provider_response = response
    return result


def _write_fresh_exact_response_reuse_receipt(
    result: ProviderResult,
    *,
    identity: Any,
    source_event_digest: str | None,
    store_error: str | None = None,
) -> ProviderResult:
    response = dict(result.provider_response or {})
    receipt = build_reuse_receipt(
        identity=identity,
        source_event_digest=source_event_digest or "",
        transport_executed_this_invocation=True,
    )
    receipt["cache_store_status"] = "STORED" if source_event_digest else "NOT_STORED"
    if store_error:
        receipt["cache_store_error"] = store_error
    response["exact_response_reuse"] = receipt
    result.provider_response = response
    return result


def call_section_model_provider(
    provider_profile: str | ProviderProfile | None,
    provider_payload: dict[str, Any],
    *,
    artifact_dir: Path | None = None,
    run_id: str | None = None,
    temperature_override: float | None = None,
    token_budget: int | None = None,
    section_id: str | None = None,
) -> ProviderResult:
    profile = normalize_provider_profile(provider_profile)
    budget = int(token_budget or provider_payload.get("max_tokens") or provider_payload.get("max_output_tokens") or 900)
    timeout_seconds = provider_payload.get("timeout_seconds")
    temperature = float(
        temperature_override
        if temperature_override is not None
        else provider_payload.get("temperature", 0.45)
    )
    sid = str(section_id or provider_payload.get("_reasoning_section_lane") or "").strip()
    claude_model: str | None = None
    openai_model: str | None = None
    if profile == ProviderProfile.EXTERNAL_CLAUDE:
        claude_model = resolve_section_generation_model(
            sid or None, provider_profile=profile
        )
    elif profile == ProviderProfile.EXTERNAL_OPENAI:
        openai_model = external_openai_generation_model(section_id=sid or None)
    requested_model = claude_model or openai_model
    reasoning_effort = resolve_section_generation_effort(
        sid or None, provider_profile=profile
    )
    anthropic_payload, anthropic_cache_seed, anthropic_cache_strategy = _resolve_anthropic_cache_payload(
        provider_payload,
        profile=profile,
        model=requested_model,
        section_id=sid or None,
        run_id=run_id,
    )
    compiled = _compiled_prompt_from_payload(
        provider_payload,
        run_id=run_id,
        anthropic_payload=anthropic_payload,
        anthropic_cache_receipt_seed=anthropic_cache_seed,
        anthropic_cache_strategy=anthropic_cache_strategy,
        reasoning_effort=reasoning_effort,
    )
    prompt_text = "\n".join(block.content for block in compiled.prompt_blocks)
    request_digest = compiled.compilation_hash or hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    exact_identity = None
    reuse_requested = _exact_response_reuse_requested(provider_payload)
    if reuse_requested and exact_response_reuse_enabled():
        try:
            exact_identity = build_exact_request_identity(
                run_id=compiled.run_id,
                stage="L2.section_generation",
                section_id=sid or None,
                provider=profile.value,
                model=str(requested_model or ""),
                request_digest=request_digest,
                prompt_text=prompt_text,
                native_payload=anthropic_payload,
                temperature=temperature,
                max_output_tokens=budget,
                timeout_seconds=timeout_seconds,
            )
            cached = lookup_exact_response(
                artifact_dir=artifact_dir,
                identity=exact_identity,
            )
            if cached is not None:
                cached_result, source_event_digest = cached
                result = _restore_exact_response_result(
                    cached_result,
                    identity=exact_identity,
                    source_event_digest=source_event_digest,
                )
                append_external_model_usage(
                    artifact_dir=artifact_dir,
                    provider=profile.value,
                    model=str(requested_model or ""),
                    request_digest=request_digest,
                    outcome="REUSED_EXACT_RESPONSE",
                    provider_status="IN_RUN_EXACT_RESPONSE_REUSE",
                    run_id=compiled.run_id,
                    stage="L2.section_generation",
                    section_id=sid or None,
                    raw_response_ref=f"exact-response-cache:{source_event_digest}",
                )
                return result
        except (ExactResponseReuseError, OSError) as exc:
            return _blocked_exact_response_reuse_result(
                profile=profile,
                model=requested_model,
                request_digest=request_digest,
                detail=str(exc),
            )
    try:
        reservation = reserve_apps_rg_model_tokens(
            artifact_dir=artifact_dir,
            provider=profile.value,
            model=str(requested_model or ""),
            request_digest=request_digest,
            prompt_text=prompt_text,
            max_output_tokens=budget,
            stage="L2.section_generation",
            section_id=sid,
            run_id=compiled.run_id,
        )
    except ValueError as exc:
        return ProviderResult(
            provider_requested=profile.value,
            provider_attempted=False,
            provider_available=False,
            exact_provider_error=f"External-model token budget ledger invalid: {exc}",
            runtime_generation_status="BLOCKED",
            model=str(requested_model or ""),
            raw_model_output="",
            provider_response={"request_digest": request_digest},
        )
    if not reservation.allowed:
        return ProviderResult(
            provider_requested=profile.value,
            provider_attempted=False,
            provider_available=False,
            exact_provider_error=(
                "External-model token budget preflight blocked: "
                f"{reservation.reason}; estimated_input_tokens={reservation.estimated_input_tokens}; "
                f"prior_reserved_total_tokens={reservation.prior_reserved_total_tokens}; "
                f"max_reserved_tokens_per_run={reservation.max_reserved_tokens_per_run}"
            ),
            runtime_generation_status="BLOCKED",
            model=str(requested_model or ""),
            raw_model_output="",
            provider_response={
                "token_budget_reservation": dict(reservation.event or {}),
                "request_digest": request_digest,
            },
        )
    with external_model_usage_scope(
        artifact_dir=artifact_dir,
        run_id=compiled.run_id,
        stage="L2.section_generation",
        section_id=sid or None,
        trace_id=compiled.trace_id,
        app_id="apps_rg",
    ):
        result = build_section_provider_gateway(
            claude_model=claude_model,
            openai_model=openai_model,
        ).generate(
            profile,
            compiled,
            token_budget=budget,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )
        result = maybe_retry_claude_availability_same_provider(
            result,
            compiled,
            token_budget=budget,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            section_id=sid or None,
        )
        result = _with_cache_receipt(
            result,
            profile=profile,
            model=requested_model,
            section_id=sid or None,
            seed=anthropic_cache_seed,
            artifact_dir=artifact_dir,
        )
        if exact_identity is not None:
            try:
                source_event_digest = store_exact_response(
                    artifact_dir=artifact_dir,
                    identity=exact_identity,
                    result=result.to_dict(),
                )
            except (ExactResponseReuseError, OSError) as exc:
                # The live output is already valid.  Do not discard it after a
                # paid call because an optional reuse artifact could not persist;
                # make the absence explicit in its receipt instead.
                return _write_fresh_exact_response_reuse_receipt(
                    result,
                    identity=exact_identity,
                    source_event_digest=None,
                    store_error=str(exc),
                )
            return _write_fresh_exact_response_reuse_receipt(
                result,
                identity=exact_identity,
                source_event_digest=source_event_digest,
            )
        return result


__all__ = [
    "build_section_provider_gateway",
    "call_section_model_provider",
]
