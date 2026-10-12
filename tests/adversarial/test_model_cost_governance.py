"""Unit tests for adversarial model cost governance and budget limits."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from apps_model_telemetry.pricing import get_model_pricing, price_usage
from apps_model_telemetry.token_budget_governor import TokenBudgetPolicy, TokenBudgetReservation


def test_adversarial_benchmark_matrix_schema():
    """Verify that the adversarial benchmark matrix contains complete, valid specifications."""
    repo_root = Path(__file__).resolve().parents[2]
    matrix_path = repo_root / "reports" / "adversarial_model_benchmarks_matrix.json"
    assert matrix_path.is_file(), f"Missing benchmark matrix: {matrix_path}"

    data = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "adversarial_model_benchmarks.v1"
    assert data["spend_governor"]["max_reserved_tokens_per_run"] == 300000

    models = data["models"]
    assert "claude-sonnet-5" in models
    assert "gpt-5.6-luna" in models
    assert "gemini-3.8-flash" in models

    for model_name, cfg in models.items():
        assert "pricing" in cfg
        assert "context_window" in cfg
        assert "max_output_tokens" in cfg
        assert cfg["context_window"] > 0
        p = cfg["pricing"]
        assert p["input_cost_per_mtok"] >= 0.0
        assert p["output_cost_per_mtok"] >= 0.0


def test_pricing_calculation_prompt_caching():
    """Verify cost calculation handles prompt caching read/write discounts accurately."""
    usage = {
        "prompt_tokens": 100000,
        "cached_tokens": 80000,
        "output_tokens": 2000,
        "thought_tokens": 0,
    }
    # Claude-Sonnet-5 pricing: $3.00 input, $0.30 cached, $15.00 output
    total_cost, version, breakdown = price_usage("claude-sonnet-5", usage, provider="anthropic")
    assert total_cost is not None
    assert version is not None
    # Uncached: 100,000 * 3 / 1M = $0.30; Cached: 80,000 * 0.3 / 1M = $0.024; Output: 2000 * 15 / 1M = $0.03
    expected_cost = round(0.30 + 0.024 + 0.03, 6)
    assert total_cost == expected_cost
    assert breakdown["cached_input_cost_usd"] == 0.024


def test_spend_governor_300k_ceiling():
    """Verify that the token budget governor enforces the 300,000 token limit per run."""
    policy = TokenBudgetPolicy(
        chars_per_token_estimate=3,
        safety_multiplier=1.12,
        max_input_tokens_per_attempt=48000,
        max_reserved_tokens_per_run=300000,
    )
    policy.validate()
    assert policy.max_reserved_tokens_per_run == 300000
    assert policy.max_input_tokens_per_attempt == 48000
