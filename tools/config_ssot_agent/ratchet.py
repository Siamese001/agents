"""Ratchet gate and monotonic regression enforcement for SSOT violations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from .scanner import ScanResult


@dataclass(frozen=True)
class SSOTRatchetThresholds:
    """Baseline thresholds that must never be exceeded."""

    max_total_violations: int
    max_hardcoded_models: int = 0
    max_hardcoded_timeouts: int = 0
    max_hardcoded_tokens: int = 0
    max_direct_env_access: int = 249

    @classmethod
    def from_dict(cls, data: Mapping[str, int]) -> SSOTRatchetThresholds:
        return cls(
            max_total_violations=data.get("max_total_violations", 249),
            max_hardcoded_models=data.get("max_hardcoded_models", 0),
            max_hardcoded_timeouts=data.get("max_hardcoded_timeouts", 0),
            max_hardcoded_tokens=data.get("max_hardcoded_tokens", 0),
            max_direct_env_access=data.get("max_direct_env_access", 249),
        )

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class SSOTRatchetGate:
    """Verifies that scan results do not exceed established baseline thresholds."""

    def __init__(self, ratchet_path: Path | str | None = None) -> None:
        self.ratchet_path = Path(ratchet_path) if ratchet_path else None
        self.thresholds = self._load_thresholds()

    def _load_thresholds(self) -> SSOTRatchetThresholds:
        if self.ratchet_path and self.ratchet_path.is_file():
            try:
                data = json.loads(self.ratchet_path.read_text(encoding="utf-8"))
                return SSOTRatchetThresholds.from_dict(data)
            except Exception:  # guardian: allow-silent-swallow -- fallback to default ratchet threshold if file is missing/unreadable
                pass
        return SSOTRatchetThresholds(max_total_violations=249)

    def evaluate(self, result: ScanResult) -> tuple[bool, list[str]]:
        """Evaluate scan results against ratchet thresholds.

        Returns (is_passed, failure_messages).
        """
        failures: list[str] = []
        stats = result.stats
        by_type = result.violations_by_type()

        # 1. Total violations check
        if stats.total_violations > self.thresholds.max_total_violations:
            failures.append(
                f"Total violations ({stats.total_violations}) exceeded ratchet baseline ceiling "
                f"({self.thresholds.max_total_violations}). Regression detected."
            )

        # 2. Hardcoded model literal check (Zero-tolerance)
        models = len(by_type.get("HARDCODED_MODEL_LITERAL", []))
        if models > self.thresholds.max_hardcoded_models:
            failures.append(
                f"Hardcoded models ({models}) exceeded zero-tolerance ceiling "
                f"({self.thresholds.max_hardcoded_models})."
            )

        # 3. Hardcoded timeouts check (Zero-tolerance)
        timeouts = len(by_type.get("HARDCODED_TIMEOUT", []))
        if timeouts > self.thresholds.max_hardcoded_timeouts:
            failures.append(
                f"Hardcoded timeouts ({timeouts}) exceeded zero-tolerance ceiling "
                f"({self.thresholds.max_hardcoded_timeouts})."
            )

        # 4. Hardcoded token limit check (Zero-tolerance)
        tokens = len(by_type.get("HARDCODED_TOKEN_LIMIT", []))
        if tokens > self.thresholds.max_hardcoded_tokens:
            failures.append(
                f"Hardcoded token limits ({tokens}) exceeded zero-tolerance ceiling "
                f"({self.thresholds.max_hardcoded_tokens})."
            )

        # 5. Direct env access check
        env_reads = len(by_type.get("DIRECT_ENV_ACCESS", []))
        if env_reads > self.thresholds.max_direct_env_access:
            failures.append(
                f"Direct environment reads ({env_reads}) exceeded ratchet ceiling "
                f"({self.thresholds.max_direct_env_access})."
            )

        return (len(failures) == 0, failures)

    def save_baseline(self, result: ScanResult, output_path: Path | str | None = None) -> None:
        """Save a new ratchet baseline from the scan results."""
        out = Path(output_path) if output_path else self.ratchet_path
        if not out:
            raise ValueError("No ratchet path specified to save baseline.")
        out.parent.mkdir(parents=True, exist_ok=True)
        stats = result.stats
        by_type = result.violations_by_type()
        new_thresholds = SSOTRatchetThresholds(
            max_total_violations=stats.total_violations,
            max_hardcoded_models=0,
            max_hardcoded_timeouts=0,
            max_hardcoded_tokens=0,
            max_direct_env_access=len(by_type.get("DIRECT_ENV_ACCESS", [])),
        )
        out.write_text(json.dumps(new_thresholds.to_dict(), indent=2), encoding="utf-8")
