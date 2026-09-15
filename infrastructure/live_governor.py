"""Live Token Governor & Model Telemetry Lock Engine.

Enforces fail-closed token budget reservation and authentic model telemetry
capture for live external LLM calls, strictly preventing unbounded expenditures,
fake/zero token accounting, and unredacted credential leakage.
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from infrastructure.live_execution import key_fingerprint


class TokenBudgetExceededError(RuntimeError):
    """Raised when an external model request exceeds the governed token budget."""


class TelemetryMissingUsageError(RuntimeError):
    """Raised when an external model call omits authentic provider usage in production."""


@dataclass(frozen=True)
class TokenBudget:
    """Configured token limits for live model requests."""

    max_prompt_tokens: int = 32000
    max_completion_tokens: int = 8192
    max_total_tokens: int = 40000
    max_run_tokens: int = 150000


@dataclass(frozen=True)
class TokenReservation:
    """Active capacity reservation granted by LiveTokenGovernor."""

    reservation_id: str
    provider: str
    model: str
    prompt_tokens_reserved: int
    completion_tokens_reserved: int
    total_reserved: int


class LiveTokenGovernor:
    """Thread-safe, fail-closed token governor for live LLM execution."""

    def __init__(self, default_budget: TokenBudget | None = None) -> None:
        self._lock = threading.RLock()
        self._budget = default_budget or self._load_budget_from_env()
        self._cumulative_tokens_reserved: int = 0
        self._cumulative_tokens_consumed: int = 0
        self._active_reservations: dict[str, TokenReservation] = {}

    @classmethod
    def _load_budget_from_env(cls) -> TokenBudget:
        def _get_int(env_var: str, default: int) -> int:
            val = os.environ.get(env_var, "").strip()
            if not val:
                return default
            try:
                parsed = int(val)
                return parsed if parsed > 0 else default
            except ValueError:
                return default

        return TokenBudget(
            max_prompt_tokens=_get_int("APPS_MAX_PROMPT_TOKENS", 32000),
            max_completion_tokens=_get_int("APPS_MAX_COMPLETION_TOKENS", 8192),
            max_total_tokens=_get_int("APPS_MAX_TOTAL_TOKENS", 40000),
            max_run_tokens=_get_int("APPS_MAX_LIVE_TOKENS_PER_RUN", 150000),
        )

    def reserve(
        self,
        *,
        provider: str,
        model: str,
        estimated_prompt_tokens: int,
        requested_completion_tokens: int,
        budget: TokenBudget | None = None,
    ) -> TokenReservation:
        """Reserve conservative capacity before a live provider request.

        Fails closed with TokenBudgetExceededError if limits are breached.
        """
        active_budget = budget or self._budget

        if estimated_prompt_tokens < 1:
            raise ValueError("estimated_prompt_tokens must be positive")
        if requested_completion_tokens < 1:
            raise ValueError("requested_completion_tokens must be positive")

        if estimated_prompt_tokens > active_budget.max_prompt_tokens:
            raise TokenBudgetExceededError(
                f"REQUEST_PROMPT_BUDGET_EXCEEDED: Estimated prompt tokens ({estimated_prompt_tokens}) "
                f"exceeds limit ({active_budget.max_prompt_tokens})"
            )

        if requested_completion_tokens > active_budget.max_completion_tokens:
            raise TokenBudgetExceededError(
                f"REQUEST_COMPLETION_BUDGET_EXCEEDED: Requested completion tokens ({requested_completion_tokens}) "
                f"exceeds limit ({active_budget.max_completion_tokens})"
            )

        requested_total = estimated_prompt_tokens + requested_completion_tokens
        if requested_total > active_budget.max_total_tokens:
            raise TokenBudgetExceededError(
                f"REQUEST_TOTAL_BUDGET_EXCEEDED: Total requested tokens ({requested_total}) "
                f"exceeds per-request limit ({active_budget.max_total_tokens})"
            )

        with self._lock:
            potential_run_total = self._cumulative_tokens_consumed + requested_total
            if potential_run_total > active_budget.max_run_tokens:
                raise TokenBudgetExceededError(
                    f"RUN_TOTAL_BUDGET_EXCEEDED: Total cumulative tokens ({potential_run_total}) "
                    f"would exceed per-run limit ({active_budget.max_run_tokens})"
                )

            res_id = uuid.uuid4().hex[:12]
            reservation = TokenReservation(
                reservation_id=res_id,
                provider=provider,
                model=model,
                prompt_tokens_reserved=estimated_prompt_tokens,
                completion_tokens_reserved=requested_completion_tokens,
                total_reserved=requested_total,
            )
            self._active_reservations[res_id] = reservation
            self._cumulative_tokens_reserved += requested_total
            return reservation

    def reconcile(
        self,
        reservation: TokenReservation,
        *,
        actual_prompt_tokens: int,
        actual_completion_tokens: int,
    ) -> None:
        """Reconcile reservation against authentic provider-reported usage."""
        with self._lock:
            self._active_reservations.pop(reservation.reservation_id, None)
            actual_total = max(0, actual_prompt_tokens) + max(0, actual_completion_tokens)
            self._cumulative_tokens_consumed += actual_total

    def reset(self) -> None:
        """Reset governor state (for testing or run isolation)."""
        with self._lock:
            self._cumulative_tokens_reserved = 0
            self._cumulative_tokens_consumed = 0
            self._active_reservations.clear()

    @property
    def cumulative_tokens_consumed(self) -> int:
        with self._lock:
            return self._cumulative_tokens_consumed


@dataclass(frozen=True)
class LiveModelReceipt:
    """Immutable audit record for authentic live model execution."""

    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    key_fingerprint: str
    recorded_at_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)


class LiveTelemetryLock:
    """Validates and locks authentic provider usage telemetry in production."""

    @staticmethod
    def _is_production_mode() -> bool:
        if os.environ.get("APPS_RG_PRODUCTION_RUN", "").strip() == "1":
            return True
        if os.environ.get("PYTEST_CURRENT_TEST") or ("pytest" in sys.modules):
            return False
        return True

    @classmethod
    def record_receipt(
        cls,
        *,
        provider: str,
        model: str,
        usage: Mapping[str, Any] | None,
        raw_key: str | None = None,
        key_fp: str | None = None,
        production_enforce: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LiveModelReceipt:
        """Record authentic model usage receipt, rejecting empty or fabricated usage."""
        is_prod = cls._is_production_mode() if production_enforce is None else production_enforce

        # Resolve safe key fingerprint (never store raw_key)
        if key_fp:
            fingerprint = key_fp
        elif raw_key:
            fingerprint = key_fingerprint(raw_key)
        else:
            fingerprint = "0000000000000000"

        # Parse provider usage
        usage_dict = dict(usage or {})
        prompt_tokens = usage_dict.get("prompt_tokens", usage_dict.get("input_tokens"))
        completion_tokens = usage_dict.get("completion_tokens", usage_dict.get("output_tokens"))
        total_tokens = usage_dict.get("total_tokens")

        if is_prod:
            if usage is None or prompt_tokens is None or completion_tokens is None:
                raise TelemetryMissingUsageError(
                    f"TELEMETRY_MISSING_USAGE: Provider '{provider}' model '{model}' call omitted authentic token usage."
                )
            try:
                p_int = int(prompt_tokens)
                c_int = int(completion_tokens)
            except (ValueError, TypeError) as exc:
                raise TelemetryMissingUsageError(
                    f"TELEMETRY_INVALID_USAGE: Invalid token counts ({prompt_tokens}, {completion_tokens})"
                ) from exc

            if p_int <= 0 and c_int <= 0:
                raise TelemetryMissingUsageError(
                    f"TELEMETRY_ZERO_USAGE: Provider '{provider}' reported zero tokens for live execution."
                )

        p_final = int(prompt_tokens) if prompt_tokens is not None else 0
        c_final = int(completion_tokens) if completion_tokens is not None else 0
        t_final = int(total_tokens) if total_tokens is not None else (p_final + c_final)

        return LiveModelReceipt(
            provider=str(provider),
            model=str(model),
            prompt_tokens=p_final,
            completion_tokens=c_final,
            total_tokens=t_final,
            key_fingerprint=fingerprint,
            recorded_at_utc=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
        )


# Global singleton governor instance
default_governor = LiveTokenGovernor()
