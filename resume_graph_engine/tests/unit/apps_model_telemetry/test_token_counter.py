"""Unit tests for TokenCounterService and token estimation across families."""

from __future__ import annotations

import pytest

from apps_model_telemetry.token_counter import (
    TokenCounterService,
    count_tokens,
    estimate_tokens,
    context_window_for,
)


def test_token_counter_empty_string():
    assert count_tokens("") == 0
    assert estimate_tokens("") == 0


def test_token_counter_families_positive():
    sample = "The quick brown fox jumps over the lazy dog."
    # Different families should provide positive estimates
    for fam in ("o200k_base", "claude_bpe", "gemini_tokenizer", "bert_bge"):
        tokens = estimate_tokens(sample, tokenizer_family=fam)
        assert tokens > 0
        assert isinstance(tokens, int)


def test_token_counter_safety_multiplier():
    sample = "Software Engineering Architecture Leadership"
    base = estimate_tokens(sample, safety_multiplier=1.0)
    elevated = estimate_tokens(sample, safety_multiplier=1.5)
    assert elevated >= base


def test_context_window_resolution():
    cw = context_window_for(role="executive_summary", section_context_window=64000)
    assert cw > 0
    assert cw <= 64000


def test_token_counter_service_singleton():
    svc1 = TokenCounterService.get_instance()
    svc2 = TokenCounterService.get_instance()
    assert svc1 is svc2
