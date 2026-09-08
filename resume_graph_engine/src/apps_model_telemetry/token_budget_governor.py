"""Fail-closed token reservations made before an external-model request.

The governor is intentionally conservative: it reserves an estimated input
plus the maximum output allowed for a request.  Reservations are append-only,
so a provider timeout, retry, or malformed response cannot make a run look
cheaper than the capacity it was allowed to consume.  It stores no prompt or
response text.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


RESERVATION_FILENAME = "external_model_token_reservations.jsonl"
RESERVATION_SCHEMA_VERSION = "apps.external_model_token_reservation.v1"
_reservation_lock = threading.RLock()


@dataclass(frozen=True)
class TokenBudgetPolicy:
    """Static, source-controlled capacity policy for a single runtime."""

    chars_per_token_estimate: int
    safety_multiplier: float
    max_input_tokens_per_attempt: int
    max_reserved_tokens_per_run: int

    def validate(self) -> None:
        if self.chars_per_token_estimate < 1:
            raise ValueError("chars_per_token_estimate must be at least one")
        if self.safety_multiplier < 1.0:
            raise ValueError("safety_multiplier must be at least one")
        if self.max_input_tokens_per_attempt < 1:
            raise ValueError("max_input_tokens_per_attempt must be positive")
        if self.max_reserved_tokens_per_run < self.max_input_tokens_per_attempt:
            raise ValueError("max_reserved_tokens_per_run must cover one input attempt")


@dataclass(frozen=True)
class TokenBudgetReservation:
    allowed: bool
    reason: str
    estimated_input_tokens: int
    reserved_output_tokens: int
    reserved_total_tokens: int
    prior_reserved_total_tokens: int
    max_reserved_tokens_per_run: int
    event: dict[str, Any] | None


def estimate_input_tokens(text: str, *, policy: TokenBudgetPolicy) -> int:
    """Conservative local estimate; avoids an extra paid network preflight."""
    policy.validate()
    raw = max(1, (len(str(text or "")) + policy.chars_per_token_estimate - 1) // policy.chars_per_token_estimate)
    return int(raw * policy.safety_multiplier + 0.999999)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _event_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reservation_path(artifact_dir: Path | str | None) -> Path | None:
    if artifact_dir is not None:
        return Path(artifact_dir) / RESERVATION_FILENAME
    raw = str(os.environ.get("APPS_MODEL_TOKEN_BUDGET_DIR") or "").strip()
    return Path(raw) / RESERVATION_FILENAME if raw else None


def _filesystem_path(path: Path) -> Path:
    """Return a Windows extended-length path for governed append-only ledgers."""
    resolved = path.resolve(strict=False)
    if os.name != "nt":
        return resolved
    rendered = str(resolved)
    if rendered.startswith("\\\\?\\"):
        return resolved
    if rendered.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + rendered.lstrip("\\"))
    return Path("\\\\?\\" + rendered)


def _prior_reserved_total(path: Path) -> int:
    if not path.is_file():
        return 0
    total = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(raw_line)
        except (TypeError, ValueError):
            # A malformed prior ledger is not safe to ignore: fail closed at
            # the caller when the retained capacity cannot be reconstructed.
            raise ValueError(f"Malformed token reservation ledger: {path}")
        if not isinstance(row, Mapping):
            raise ValueError(f"Malformed token reservation entry: {path}")
        if row.get("decision") != "RESERVED":
            continue
        value = row.get("reserved_total_tokens")
        if isinstance(value, bool):
            raise ValueError(f"Invalid reservation amount: {path}")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid reservation amount: {path}") from exc
        if parsed < 0:
            raise ValueError(f"Invalid reservation amount: {path}")
        total += parsed
    return total


def reserve_token_budget(
    *,
    artifact_dir: Path | str | None,
    provider: str,
    model: str,
    request_digest: str,
    prompt_text: str,
    max_output_tokens: int,
    policy: TokenBudgetPolicy,
    stage: str,
    section_id: str = "",
    run_id: str = "",
) -> TokenBudgetReservation:
    """Reserve conservative capacity before a paid model request.

    With no run-artifact directory (or explicit process ledger directory), the
    call is reported as unbound and allowed.  The governor never guesses a run
    identity because that would mix independent runs and produce false blocks.
    """
    policy.validate()
    try:
        output = int(max_output_tokens)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_output_tokens must be an integer") from exc
    if output < 1:
        raise ValueError("max_output_tokens must be positive")
    estimated_input = estimate_input_tokens(prompt_text, policy=policy)
    reserved_total = estimated_input + output
    path = _reservation_path(artifact_dir)
    if path is None:
        return TokenBudgetReservation(
            allowed=True,
            reason="UNBOUND_RUN_ARTIFACT",
            estimated_input_tokens=estimated_input,
            reserved_output_tokens=output,
            reserved_total_tokens=reserved_total,
            prior_reserved_total_tokens=0,
            max_reserved_tokens_per_run=policy.max_reserved_tokens_per_run,
            event=None,
        )

    path = _filesystem_path(path)
    with _reservation_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        prior = _prior_reserved_total(path)
        if estimated_input > policy.max_input_tokens_per_attempt:
            decision = "BLOCKED"
            reason = "INPUT_ATTEMPT_CAP_EXCEEDED"
        elif prior + reserved_total > policy.max_reserved_tokens_per_run:
            decision = "BLOCKED"
            reason = "RUN_RESERVED_TOKEN_CAP_EXCEEDED"
        else:
            decision = "RESERVED"
            reason = "OK"
        event: dict[str, Any] = {
            "schema_version": RESERVATION_SCHEMA_VERSION,
            "event_id": uuid.uuid4().hex,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": str(run_id or ""),
            "stage": str(stage or ""),
            "section_id": str(section_id or ""),
            "provider": str(provider or ""),
            "model": str(model or ""),
            "request_digest": str(request_digest or ""),
            "decision": decision,
            "reason": reason,
            "estimated_input_tokens": estimated_input,
            "reserved_output_tokens": output,
            "reserved_total_tokens": reserved_total,
            "prior_reserved_total_tokens": prior,
            "max_input_tokens_per_attempt": policy.max_input_tokens_per_attempt,
            "max_reserved_tokens_per_run": policy.max_reserved_tokens_per_run,
        }
        event["event_digest"] = _event_digest(event)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical_json(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return TokenBudgetReservation(
        allowed=decision == "RESERVED",
        reason=reason,
        estimated_input_tokens=estimated_input,
        reserved_output_tokens=output,
        reserved_total_tokens=reserved_total,
        prior_reserved_total_tokens=prior,
        max_reserved_tokens_per_run=policy.max_reserved_tokens_per_run,
        event=event,
    )


__all__ = [
    "RESERVATION_FILENAME",
    "RESERVATION_SCHEMA_VERSION",
    "TokenBudgetPolicy",
    "TokenBudgetReservation",
    "estimate_input_tokens",
    "reserve_token_budget",
]
