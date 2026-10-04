"""Canonical pricing and cost accounting for external model requests.

Prices usage from the Model Registry v2 SSOT pricing table.
- Distinct pricing for non-cached input, cached input, cache creation, and output.
- Provider-specific cached-token subtraction rules (Anthropic vs OpenAI/Gemini).
- Unpriced models return None (never 0.0) so missing pricing is detectable.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


def get_model_pricing(model: str) -> tuple[dict[str, float] | None, str | None]:
    """Look up pricing configuration and registry version for a given model or snapshot ID."""
    try:
        from apps_rg.runtime.model_registry import _load_registry_data

        data, _ = _load_registry_data()
        version = data.get("version", "2.0.0")
        models = data.get("models", {})

        # 1. Direct model key match
        if model in models and models[model].get("pricing"):
            return models[model]["pricing"], version

        # 2. Match by snapshot_id
        for m_id, m_def in models.items():
            if isinstance(m_def, dict) and m_def.get("snapshot_id") == model and m_def.get("pricing"):
                return m_def["pricing"], version

        # 3. Match by role
        roles = data.get("roles", {})
        if model in roles:
            m_id = roles[model].get("model")
            if m_id and m_id in models and models[m_id].get("pricing"):
                return models[m_id]["pricing"], version
    except Exception:
        pass

    return None, None


def price_usage(
    model: str,
    normalized_usage: Mapping[str, Any] | None,
    *,
    provider: str | None = None,
) -> tuple[float | None, str | None, dict[str, Any]]:
    """Compute USD cost for normalized token usage.

    Returns:
        (total_cost_usd, pricing_version, breakdown_dict)
        If model has no pricing, total_cost_usd is None.
    """
    pricing, version = get_model_pricing(model)
    if pricing is None:
        return None, "unpriced", {"unpriced_model": model}

    raw = normalized_usage if isinstance(normalized_usage, Mapping) else {}
    prompt_tokens = int(raw.get("prompt_tokens") or 0)
    output_tokens = int(raw.get("output_tokens") or 0)
    thought_tokens = int(raw.get("thought_tokens") or 0)
    cached_tokens = int(raw.get("cached_tokens") or 0)
    cache_write_tokens = int(raw.get("cache_write_tokens") or 0)

    # Provider cached-token subtraction:
    # - Anthropic: input_tokens does NOT include cache_read_input_tokens.
    # - OpenAI / Gemini: prompt tokens includes cached tokens.
    prov_key = str(provider or "").lower()
    if "anthropic" in prov_key or "claude" in prov_key:
        uncached_input = max(0, prompt_tokens)
    else:
        uncached_input = max(0, prompt_tokens - cached_tokens)

    effective_output = output_tokens + thought_tokens

    input_cost_per_mtok = float(pricing.get("input_cost_per_mtok", 0.0))
    output_cost_per_mtok = float(pricing.get("output_cost_per_mtok", 0.0))
    cached_cost_per_mtok = float(pricing.get("cached_input_cost_per_mtok", 0.0))
    cache_write_mult = float(pricing.get("cache_write_multiplier", 1.0))

    input_cost = (uncached_input / 1_000_000.0) * input_cost_per_mtok
    cached_cost = (cached_tokens / 1_000_000.0) * cached_cost_per_mtok
    cache_write_cost = (cache_write_tokens / 1_000_000.0) * input_cost_per_mtok * cache_write_mult
    output_cost = (effective_output / 1_000_000.0) * output_cost_per_mtok

    total_cost = round(input_cost + cached_cost + cache_write_cost + output_cost, 6)
    breakdown = {
        "uncached_input_tokens": uncached_input,
        "cached_tokens": cached_tokens,
        "cache_write_tokens": cache_write_tokens,
        "output_tokens": effective_output,
        "input_cost_usd": round(input_cost, 6),
        "cached_input_cost_usd": round(cached_cost, 6),
        "cache_write_cost_usd": round(cache_write_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": total_cost,
    }
    return total_cost, version or "2.0.0", breakdown


def compute_run_cost_rollup(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute run-level cost and token rollup from usage ledger records."""
    total_input = 0
    total_output = 0
    total_cached = 0
    total_cache_write = 0
    total_tokens = 0
    total_cost: float = 0.0
    has_unpriced = False
    model_breakdowns: dict[str, dict[str, Any]] = {}

    for row in records:
        model = str(row.get("model") or "unknown")
        prompt = int(row.get("prompt_tokens") or 0)
        output = int(row.get("output_tokens") or 0)
        thought = int(row.get("thought_tokens") or 0)
        cached = int(row.get("cached_tokens") or 0)
        cwrite = int(row.get("cache_write_tokens") or 0)
        tot = int(row.get("total_tokens") or (prompt + output + thought))

        total_input += prompt
        total_output += output + thought
        total_cached += cached
        total_cache_write += cwrite
        total_tokens += tot

        row_cost = row.get("cost_usd")
        if row_cost is None:
            # Attempt to price if missing
            priced, _, _ = price_usage(model, row, provider=row.get("provider"))
            if priced is None:
                has_unpriced = True
            else:
                total_cost += priced
        else:
            total_cost += float(row_cost)

        m_entry = model_breakdowns.setdefault(
            model,
            {"calls": 0, "tokens": 0, "cost_usd": 0.0, "has_unpriced": False},
        )
        m_entry["calls"] += 1
        m_entry["tokens"] += tot
        if row_cost is not None:
            m_entry["cost_usd"] = round(m_entry["cost_usd"] + float(row_cost), 6)
        else:
            m_entry["has_unpriced"] = True

    cache_read_denom = total_cached + total_cache_write
    cache_hit_ratio = round(total_cached / cache_read_denom, 4) if cache_read_denom > 0 else 0.0

    return {
        "total_cost_usd": None if has_unpriced and total_cost == 0.0 else round(total_cost, 6),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cached_tokens": total_cached,
        "total_cache_write_tokens": total_cache_write,
        "total_tokens": total_tokens,
        "cache_hit_ratio": cache_hit_ratio,
        "has_unpriced_models": has_unpriced,
        "per_model_summary": model_breakdowns,
    }
