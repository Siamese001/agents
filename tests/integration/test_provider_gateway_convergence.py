"""End-to-End Live LLM Enforcement — Wave 6 Final Convergence Verification Suite.

Validates:
1. LiveTokenGovernor thread-safe budget reservations and cumulative limits.
2. LiveTelemetryLock authentic token capture, non-secret key fingerprinting, and fail-closed behavior.
3. Static mock reachability audit discovering 0 violations across all production roots.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from infrastructure.live_governor import (
    LiveModelReceipt,
    LiveTelemetryLock,
    LiveTokenGovernor,
    TelemetryMissingUsageError,
    TokenBudget,
    TokenBudgetExceededError,
)
from tools.audit_mock_reachability import run_audit


class TestWave6TokenGovernor:
    """Validate thread-safe, fail-closed token reservations."""

    def test_governor_enforces_prompt_budget(self):
        budget = TokenBudget(max_prompt_tokens=500, max_completion_tokens=200, max_total_tokens=700, max_run_tokens=2000)
        governor = LiveTokenGovernor(default_budget=budget)

        with pytest.raises(TokenBudgetExceededError, match="REQUEST_PROMPT_BUDGET_EXCEEDED"):
            governor.reserve(
                provider="openai",
                model="gpt-5.6-luna",
                estimated_prompt_tokens=600,
                requested_completion_tokens=100,
            )

    def test_governor_enforces_completion_budget(self):
        budget = TokenBudget(max_prompt_tokens=500, max_completion_tokens=200, max_total_tokens=700, max_run_tokens=2000)
        governor = LiveTokenGovernor(default_budget=budget)

        with pytest.raises(TokenBudgetExceededError, match="REQUEST_COMPLETION_BUDGET_EXCEEDED"):
            governor.reserve(
                provider="anthropic",
                model="claude-3-7-sonnet",
                estimated_prompt_tokens=100,
                requested_completion_tokens=250,
            )

    def test_governor_enforces_cumulative_run_budget(self):
        budget = TokenBudget(max_prompt_tokens=1000, max_completion_tokens=500, max_total_tokens=1500, max_run_tokens=1200)
        governor = LiveTokenGovernor(default_budget=budget)

        # First request consumes 700 tokens
        res1 = governor.reserve(
            provider="openai",
            model="gpt-5.6-luna",
            estimated_prompt_tokens=500,
            requested_completion_tokens=200,
        )
        governor.reconcile(res1, actual_prompt_tokens=400, actual_completion_tokens=200)
        assert governor.cumulative_tokens_consumed == 600

        # Second request requesting 700 tokens: 600 consumed + 700 requested = 1300 > 1200 run cap
        with pytest.raises(TokenBudgetExceededError, match="RUN_TOTAL_BUDGET_EXCEEDED"):
            governor.reserve(
                provider="openai",
                model="gpt-5.6-luna",
                estimated_prompt_tokens=500,
                requested_completion_tokens=200,
            )

    def test_governor_reconciles_actual_tokens(self):
        budget = TokenBudget(max_prompt_tokens=2000, max_completion_tokens=1000, max_total_tokens=3000, max_run_tokens=5000)
        governor = LiveTokenGovernor(default_budget=budget)

        reservation = governor.reserve(
            provider="google",
            model="gemini-2.5-pro",
            estimated_prompt_tokens=800,
            requested_completion_tokens=400,
        )
        assert reservation.total_reserved == 1200

        # Reconcile with actual provider reported counts
        governor.reconcile(reservation, actual_prompt_tokens=350, actual_completion_tokens=150)
        assert governor.cumulative_tokens_consumed == 500


class TestWave6TelemetryLock:
    """Validate authentic telemetry capture and fail-closed production enforcement."""

    def test_records_authentic_receipt_with_key_fingerprint(self):
        raw_key = "live-sample-openai-credential-4321"
        receipt = LiveTelemetryLock.record_receipt(
            provider="openai",
            model="gpt-5.6-luna",
            usage={"prompt_tokens": 250, "completion_tokens": 95, "total_tokens": 345},
            raw_key=raw_key,
            production_enforce=False,
        )
        assert isinstance(receipt, LiveModelReceipt)
        assert receipt.provider == "openai"
        assert receipt.model == "gpt-5.6-luna"
        assert receipt.prompt_tokens == 250
        assert receipt.completion_tokens == 95
        assert receipt.total_tokens == 345
        assert len(receipt.key_fingerprint) == 16
        # Ensure raw key is never stored in the receipt
        assert raw_key not in repr(receipt)
        assert raw_key not in str(receipt.__dict__)

    def test_fails_closed_on_missing_usage_in_production(self):
        with mock.patch.dict(os.environ, {"APPS_RG_PRODUCTION_RUN": "1"}):
            with pytest.raises(TelemetryMissingUsageError, match="TELEMETRY_MISSING_USAGE"):
                LiveTelemetryLock.record_receipt(
                    provider="openai",
                    model="gpt-5.6-luna",
                    usage=None,
                    production_enforce=True,
                )

    def test_fails_closed_on_zero_usage_in_production(self):
        with mock.patch.dict(os.environ, {"APPS_RG_PRODUCTION_RUN": "1"}):
            with pytest.raises(TelemetryMissingUsageError, match="TELEMETRY_ZERO_USAGE"):
                LiveTelemetryLock.record_receipt(
                    provider="anthropic",
                    model="claude-3-7-sonnet",
                    usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    production_enforce=True,
                )


def test_final_convergence_mock_reachability_zero_violations():
    """Verify that tools/audit_mock_reachability.py detects zero reachable mocks across all roots."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    code, violations = run_audit(repo_root)
    assert code == 0, f"Discovered mock reachability violations: {violations}"
    assert len(violations) == 0
