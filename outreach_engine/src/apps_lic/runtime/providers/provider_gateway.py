"""Governed Provider Gateway & Telemetry Emitter for outreach_engine (apps_lic).

Dispatches compiled 8-slot prompts across pinned model lanes resolved from
`OutreachModelRegistry` (`outreach_engine/config/provider_profiles.yaml`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from apps_model_telemetry.pricing import price_usage
from infrastructure.config import env_loader as _env_loader

from apps_lic.runtime.model_registry import (
    OutreachModelPin,
    OutreachModelRegistry,
    OutreachModelRegistryError,
)


def get_apps_lic_test_fault_inject(default: str = "") -> str:
    """Resolve optional test fault injection token via infrastructure.config.env_loader."""
    fn = getattr(_env_loader, "get_apps_lic_test_fault_inject", None)
    if callable(fn):
        return str(fn(default=default) or "").strip()
    return str(_env_loader.get_env_str("APPS_LIC_TEST_FAULT_INJECT", default=default)).strip()

GATEWAY_SCHEMA_VERSION = "apps_lic.provider_gateway.v1"
VALID_EXECUTION_MODES = frozenset({"REAL_LLM", "OFFLINE_SMOKE"})
LOW_EFFORT_LOCKED_LANES = frozenset(
    {"rubric_judge_panel", "x1d_proof_judge_primary", "x1d_proof_judge_secondary", "handoff_judge"}
)


class OutreachProviderGatewayError(ValueError, RuntimeError):
    """Raised on model pin violations, thinking-budget cap breaches, or unrecoverable transport failures."""


@dataclass(frozen=True)
class ProviderTelemetryRecord:
    """Structured telemetry record emitted per provider gateway dispatch."""

    provider_id: str
    model_id: str
    prompt_hash: str
    input_tokens: int
    output_tokens: int
    thinking_budget_tokens: int
    cache_tier: str = "NONE"
    execution_mode: str = "REAL_LLM"
    lane: str = "executive_outreach_generator"
    reasoning_effort: str = "low"
    used_fallback: bool = False
    drafter_family: str = ""
    cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize telemetry record to a plain dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class GatewayDispatchRequest:
    """Request contract for dispatching a compiled 8-slot prompt through OutreachProviderGateway."""

    prompt_hash: str = ""
    lane: str = "executive_outreach_generator"
    execution_mode: str = "REAL_LLM"
    rendered_prompt: str = ""
    compiled_prompt: Any = None
    thinking_budget_tokens: int | None = None
    reasoning_effort: str | None = None
    max_output_tokens: int = 4096
    cache_tier: str = "NONE"
    touch_number: int = 1
    allocation_plan_digest: str = ""
    candidate_graph_db_sha256: str = ""
    strict_thinking_cap: bool = False
    fault_inject_override: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cp = self.compiled_prompt
        if cp is not None:
            for attr in ("prompt_hash", "rendered_prompt", "allocation_plan_digest", "candidate_graph_db_sha256"):
                if not getattr(self, attr) and hasattr(cp, attr):
                    object.__setattr__(self, attr, str(getattr(cp, attr) or ""))
        if not self.prompt_hash and self.rendered_prompt:
            computed = hashlib.sha256(self.rendered_prompt.encode("utf-8")).hexdigest()
            object.__setattr__(self, "prompt_hash", computed)

    @classmethod
    def from_compiled_prompt(
        cls,
        compiled_prompt: Any,
        *,
        lane: str = "executive_outreach_generator",
        execution_mode: str = "REAL_LLM",
        thinking_budget_tokens: int | None = None,
        reasoning_effort: str | None = None,
        cache_tier: str = "NONE",
        touch_number: int = 1,
        strict_thinking_cap: bool = False,
        fault_inject_override: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> GatewayDispatchRequest:
        """Build a GatewayDispatchRequest directly from a CompiledOutreachPrompt instance."""
        return cls(
            compiled_prompt=compiled_prompt,
            lane=lane,
            execution_mode=execution_mode,
            thinking_budget_tokens=thinking_budget_tokens,
            reasoning_effort=reasoning_effort,
            cache_tier=cache_tier,
            touch_number=touch_number,
            strict_thinking_cap=strict_thinking_cap,
            fault_inject_override=fault_inject_override,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class GatewayDispatchResponse:
    """Response contract returned by OutreachProviderGateway.dispatch."""

    provider_id: str
    model_id: str
    requested_model_id: str
    lane: str
    prompt_hash: str
    execution_mode: str
    reasoning_effort: str
    thinking_budget_tokens: int
    used_fallback: bool
    drafter_family: str
    proof_eligible: bool
    advisory_only: bool
    x1d_hitl_escalation_required: bool
    output_text: str
    structured_output: dict[str, Any]
    telemetry: ProviderTelemetryRecord
    receipt: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize dispatch response to a dictionary."""
        return asdict(self)


def _should_fault_inject_primary(fault_token: str, pin: OutreachModelPin) -> bool:
    token = str(fault_token or "").strip().lower()
    if not token or token in {"0", "false", "no", "off", "none"}:
        return False
    fault_keywords = {
        "1", "true", "yes", "on", "primary_fail", "fail_primary", "drafter_primary_fail",
        "anthropic_fail", "timeout", "rate_limit", "503", "both_fail", "all_fail",
    }
    if token in fault_keywords:
        return True
    return pin.model.lower() in token or pin.provider.lower() in token or "primary" in token or "fail" in token


class OutreachProviderGateway:
    """Governed model dispatch gateway enforcing model pins, thinking caps, and cross-family failover."""

    def __init__(
        self,
        config_path: Path | str | None = None,
        transport_fn: Callable[[GatewayDispatchRequest, OutreachModelPin, str, str], dict[str, Any] | str]
        | None = None,
    ) -> None:
        self._config_path = config_path
        self._transport_fn = transport_fn
        self._telemetry_ledger: list[ProviderTelemetryRecord] = []

    @property
    def telemetry_ledger(self) -> list[ProviderTelemetryRecord]:
        """Return a copy of emitted telemetry records."""
        return list(self._telemetry_ledger)

    def clear_telemetry(self) -> None:
        """Clear accumulated telemetry records."""
        self._telemetry_ledger.clear()

    def resolve_lane_pin(self, lane: str) -> OutreachModelPin:
        """Resolve the governed OutreachModelPin for a functional lane."""
        try:
            return OutreachModelRegistry.get_model_pin(lane, self._config_path)
        except OutreachModelRegistryError as exc:
            raise OutreachProviderGatewayError(str(exc)) from exc

    def validate_thinking_budget(self, lane: str | OutreachModelPin, requested_tokens: int) -> int:
        """Strictly validate a requested thinking_budget_tokens value against the lane cap."""
        pin = lane if isinstance(lane, OutreachModelPin) else self.resolve_lane_pin(lane)
        if int(requested_tokens) <= 0:
            raise OutreachProviderGatewayError(
                f"thinking_budget_tokens must be positive for lane '{pin.role}', got {requested_tokens}"
            )
        if int(requested_tokens) > pin.thinking_budget_tokens:
            raise OutreachProviderGatewayError(
                f"Requested thinking_budget_tokens ({requested_tokens}) exceeds cap "
                f"({pin.thinking_budget_tokens}) for lane '{pin.role}' ({pin.model})"
            )
        return int(requested_tokens)

    def enforce_thinking_budget(
        self,
        lane: str | OutreachModelPin,
        requested_tokens: int | None = None,
        *,
        strict: bool = False,
    ) -> int:
        """Resolve and cap thinking_budget_tokens for a lane (or raise if strict=True)."""
        pin = lane if isinstance(lane, OutreachModelPin) else self.resolve_lane_pin(lane)
        if requested_tokens is None:
            return pin.thinking_budget_tokens
        if int(requested_tokens) <= 0 or (strict and int(requested_tokens) > pin.thinking_budget_tokens):
            return self.validate_thinking_budget(pin, int(requested_tokens))
        return min(int(requested_tokens), pin.thinking_budget_tokens)

    def resolve_reasoning_effort(
        self, lane: str | OutreachModelPin, requested_effort: str | None = None
    ) -> str:
        """Resolve reasoning effort, locking judge and selector lanes to 'low'."""
        pin = lane if isinstance(lane, OutreachModelPin) else self.resolve_lane_pin(lane)
        if pin.role in LOW_EFFORT_LOCKED_LANES or pin.advisory_only or pin.proof_eligible:
            return "low"
        if not requested_effort:
            return pin.reasoning_effort or "low"
        eff = str(requested_effort).strip().lower()
        return eff if eff in {"low", "medium"} else (pin.reasoning_effort or "low")

    def verify_x1d_judge_orthogonality(
        self, drafter_family: str, judge_lane: str = "x1d_proof_judge_primary"
    ) -> bool:
        """Check whether a judge lane is proof-eligible and cross-family orthogonal to drafter_family."""
        pin = self.resolve_lane_pin(judge_lane)
        return OutreachModelRegistry.verify_cross_family_orthogonality(
            drafter_family, pin, self._config_path
        )

    def dispatch(
        self,
        request: GatewayDispatchRequest | Any,
        *,
        lane: str | None = None,
        execution_mode: str | None = None,
        thinking_budget_tokens: int | None = None,
    ) -> GatewayDispatchResponse:
        """Dispatch a compiled 8-slot prompt with automatic primary->backup failover and telemetry."""
        if not isinstance(request, GatewayDispatchRequest):
            req = GatewayDispatchRequest.from_compiled_prompt(
                request,
                lane=lane or "executive_outreach_generator",
                execution_mode=execution_mode or "REAL_LLM",
                thinking_budget_tokens=thinking_budget_tokens,
            )
        elif lane or execution_mode or thinking_budget_tokens is not None:
            tb = thinking_budget_tokens if thinking_budget_tokens is not None else request.thinking_budget_tokens
            req = GatewayDispatchRequest(
                **{
                    **asdict(request),
                    "lane": lane or request.lane,
                    "execution_mode": execution_mode or request.execution_mode,
                    "thinking_budget_tokens": tb,
                }
            )
        else:
            req = request

        if not req.prompt_hash:
            raise OutreachProviderGatewayError(
                "GatewayDispatchRequest requires a non-empty prompt_hash or rendered_prompt"
            )
        mode = str(req.execution_mode or "REAL_LLM").strip().upper()
        if mode not in VALID_EXECUTION_MODES:
            raise OutreachProviderGatewayError(f"Unsupported execution_mode: {req.execution_mode!r}")

        pin = self.resolve_lane_pin(req.lane)
        effective_thinking = self.enforce_thinking_budget(
            pin, req.thinking_budget_tokens, strict=req.strict_thinking_cap
        )
        thinking_cap_enforced = (
            req.thinking_budget_tokens is not None and int(req.thinking_budget_tokens) > pin.thinking_budget_tokens
        )
        effective_effort = self.resolve_reasoning_effort(pin, req.reasoning_effort)

        fault_token = (
            req.fault_inject_override if req.fault_inject_override is not None else get_apps_lic_test_fault_inject()
        )
        active_provider, active_model = pin.provider, pin.model
        used_fallback, fallback_reason = False, ""
        primary_faulted = _should_fault_inject_primary(fault_token, pin)
        raw_result: dict[str, Any] | str | None = None

        if not primary_faulted and self._transport_fn is not None:
            try:
                raw_result = self._transport_fn(req, pin, active_provider, active_model)
            except Exception as exc:
                primary_faulted = True
                fallback_reason = f"primary_transport_error:{type(exc).__name__}"

        if primary_faulted:
            if str(fault_token or "").strip().lower() in {"both_fail", "all_fail"}:
                raise OutreachProviderGatewayError(
                    f"Both primary ({pin.model}) and backup ({pin.backup_model}) faulted for lane '{pin.role}'"
                )
            if not pin.backup_model:
                raise OutreachProviderGatewayError(
                    f"Primary model '{pin.model}' faulted on lane '{pin.role}' and no backup_model is configured"
                )
            active_provider = pin.backup_provider or OutreachModelRegistry.normalize_provider_family(pin.backup_model)
            active_model = pin.backup_model
            used_fallback = True
            fallback_reason = fallback_reason or f"fault_inject:{fault_token or 'primary_fail'}"
            if self._transport_fn is not None:
                raw_result = self._transport_fn(req, pin, active_provider, active_model)

        drafter_family = OutreachModelRegistry.normalize_provider_family(active_provider or active_model)
        structured_output, output_text = self._normalize_output(raw_result, req=req, model_id=active_model)

        input_tokens = max(64, len(req.rendered_prompt or req.prompt_hash) // 4)
        output_tokens = max(32, len(output_text) // 4)
        cost_usd, pricing_version, _ = price_usage(
            active_model,
            {"prompt_tokens": input_tokens, "output_tokens": output_tokens},
            provider=active_provider,
        )
        x1d_hitl_escalation_required = bool(
            used_fallback
            and drafter_family == "openai"
            and pin.role in {"executive_outreach_generator", "recruiter_outreach_generator"}
        )

        telemetry = ProviderTelemetryRecord(
            provider_id=active_provider,
            model_id=active_model,
            prompt_hash=req.prompt_hash,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_budget_tokens=effective_thinking,
            cache_tier=req.cache_tier,
            execution_mode=mode,
            lane=pin.role,
            reasoning_effort=effective_effort,
            used_fallback=used_fallback,
            drafter_family=drafter_family,
            cost_usd=cost_usd,
        )
        self._telemetry_ledger.append(telemetry)

        receipt = {
            "schema_version": GATEWAY_SCHEMA_VERSION,
            "lane": pin.role,
            "provider_id": active_provider,
            "model_id": active_model,
            "requested_model_id": pin.model,
            "primary_model": pin.model,
            "fallback_model": pin.backup_model,
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
            "drafter_family": drafter_family,
            "reasoning_effort": effective_effort,
            "thinking_budget_tokens": effective_thinking,
            "thinking_budget_cap": pin.thinking_budget_tokens,
            "thinking_cap_enforced": thinking_cap_enforced,
            "proof_eligible": pin.proof_eligible,
            "advisory_only": pin.advisory_only,
            "x1d_hitl_escalation_required": x1d_hitl_escalation_required,
            "prompt_hash": req.prompt_hash,
            "allocation_plan_digest": req.allocation_plan_digest,
            "candidate_graph_db_sha256": req.candidate_graph_db_sha256,
            "cache_tier": req.cache_tier,
            "execution_mode": mode,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "pricing_version": pricing_version,
        }
        return GatewayDispatchResponse(
            provider_id=active_provider,
            model_id=active_model,
            requested_model_id=pin.model,
            lane=pin.role,
            prompt_hash=req.prompt_hash,
            execution_mode=mode,
            reasoning_effort=effective_effort,
            thinking_budget_tokens=effective_thinking,
            used_fallback=used_fallback,
            drafter_family=drafter_family,
            proof_eligible=pin.proof_eligible,
            advisory_only=pin.advisory_only,
            x1d_hitl_escalation_required=x1d_hitl_escalation_required,
            output_text=output_text,
            structured_output=structured_output,
            telemetry=telemetry,
            receipt=receipt,
        )

    @staticmethod
    def _normalize_output(
        raw_result: dict[str, Any] | str | None,
        *,
        req: GatewayDispatchRequest,
        model_id: str,
    ) -> tuple[dict[str, Any], str]:
        if isinstance(raw_result, dict):
            text = json.dumps(raw_result, sort_keys=True, separators=(",", ":"))
            return dict(raw_result), text
        if isinstance(raw_result, str) and raw_result.strip():
            try:
                parsed = json.loads(raw_result)
                if isinstance(parsed, dict):
                    return parsed, raw_result
            except ValueError:
                pass
            return {"raw_text": raw_result}, raw_result

        default_payload: dict[str, Any] = {
            "touch_number": int(req.touch_number),
            "subject": f"Executive briefing alignment ({req.touch_number})",
            "body": f"Grounded outreach synthesis for prompt {req.prompt_hash[:12]}.",
            "cited_fact_ids": list(req.metadata.get("cited_fact_ids", [])),
            "metric_bindings": dict(req.metadata.get("metric_bindings", {})),
            "model_id": model_id,
        }
        rendered = json.dumps(default_payload, sort_keys=True, separators=(",", ":"))
        return default_payload, rendered


__all__ = [
    "GATEWAY_SCHEMA_VERSION",
    "LOW_EFFORT_LOCKED_LANES",
    "VALID_EXECUTION_MODES",
    "GatewayDispatchRequest",
    "GatewayDispatchResponse",
    "OutreachProviderGateway",
    "OutreachProviderGatewayError",
    "ProviderTelemetryRecord",
]
