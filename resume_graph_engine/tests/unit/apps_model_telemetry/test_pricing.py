"""Unit tests for pricing service and run cost rollup."""

from __future__ import annotations

import pytest

from apps_rg.runtime.model_registry import resolve_model_role
from apps_model_telemetry.pricing import (
    get_model_pricing,
    price_usage,
    compute_run_cost_rollup,
)


def test_get_model_pricing_from_registry():
    model_id = resolve_model_role("generation.executive_summary").pinned_model_id
    pricing, version = get_model_pricing(model_id)
    assert pricing is not None
    assert "input_cost_per_mtok" in pricing
    assert "output_cost_per_mtok" in pricing
    assert version == "2.0.0"


def test_price_usage_known_model():
    role = resolve_model_role("generation.executive_summary")
    usage = {
        "prompt_tokens": 1000,
        "output_tokens": 500,
        "thought_tokens": 0,
        "cached_tokens": 200,
        "cache_write_tokens": 0,
    }
    cost, version, breakdown = price_usage(role.pinned_model_id, usage, provider=role.provider)
    assert cost is not None
    assert cost > 0.0
    assert version == "2.0.0"
    assert breakdown["input_cost_usd"] > 0
    assert breakdown["output_cost_usd"] > 0


def test_price_usage_unpriced_model_returns_none():
    usage = {"prompt_tokens": 100, "output_tokens": 50}
    cost, version, breakdown = price_usage("non-existent-fantasy-model-xyz", usage)
    assert cost is None
    assert version == "unpriced"
    assert "unpriced_model" in breakdown


def test_compute_run_cost_rollup():
    role_a = resolve_model_role("generation.executive_summary")
    role_b = resolve_model_role("generation.competencies")
    records = [
        {
            "model": role_a.pinned_model_id,
            "provider": role_a.provider,
            "prompt_tokens": 1000,
            "output_tokens": 200,
            "cached_tokens": 500,
            "cache_write_tokens": 100,
            "cost_usd": 0.005,
        },
        {
            "model": role_b.pinned_model_id,
            "provider": role_b.provider,
            "prompt_tokens": 2000,
            "output_tokens": 400,
            "cached_tokens": 1000,
            "cache_write_tokens": 0,
            "cost_usd": 0.008,
        },
    ]
    rollup = compute_run_cost_rollup(records)
    assert rollup["total_cost_usd"] == pytest.approx(0.013, rel=1e-3)
    assert rollup["total_input_tokens"] == 3000
    assert rollup["total_output_tokens"] == 600
    assert rollup["total_cached_tokens"] == 1500
    assert rollup["cache_hit_ratio"] > 0
    assert not rollup["has_unpriced_models"]
