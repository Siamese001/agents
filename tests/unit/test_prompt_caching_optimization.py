"""Unit tests for Prompt Caching Optimization and Invariants.

Verifies:
1. Normalization of static templates.
2. Canonical JSON serialization for data payloads.
3. Prefix fingerprinting and drift detection.
4. Usage metrics extraction including cached tokens.
5. Cache-aligned slot ordering in prompt assembly compiler.
6. Stability of static system prompts for company brief and bare pipeline.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from agents.observability.prompt_cache import (
    chat_usage_metrics,
    json_text,
    normalize_static_template,
    prefix_fingerprint,
    routing_key,
)
from apps_research.engines.company_brief_engine import COMPANY_BRIEF_STATIC_SYSTEM_PROMPT
from apps_rg.bare_pipeline import BARE_PIPELINE_L2_SYSTEM_PROMPT
from apps_rg.prompt_assembly.compiler import (
    CACHE_ALIGNED_SLOT_ORDER,
    CANONICAL_SLOT_ORDER,
    PromptCompiler,
    compile_prompt,
)
from apps_rg.prompt_assembly.contracts import PromptAssemblyInput


def test_normalize_static_template() -> None:
    raw = "System prompt line 1\r\nSystem prompt line 2\r\n\r\n"
    normalized = normalize_static_template(raw)
    assert normalized == "System prompt line 1\nSystem prompt line 2\n"
    assert not normalized.endswith("\n\n")
    assert "\r" not in normalized


def test_json_text_determinism() -> None:
    data = {"z": 1, "a": 2, "m": {"nested_b": True, "nested_a": "value"}}
    serialized = json_text(data)
    expected = '{"a":2,"m":{"nested_a":"value","nested_b":true},"z":1}'
    assert serialized == expected
    assert " " not in serialized


def test_prefix_fingerprint_invariance() -> None:
    messages = [
        {"role": "system", "content": "You are an expert analyst."},
        {"role": "user", "content": "Static instructions block."},
    ]
    fp1 = prefix_fingerprint(model="gpt-5.6-luna", prefix_messages=messages)
    fp2 = prefix_fingerprint(model="gpt-5.6-luna", prefix_messages=messages)
    assert fp1 == fp2
    assert len(fp1) == 64

    # Divergence when content or model differs
    fp3 = prefix_fingerprint(model="gpt-5.6-terra", prefix_messages=messages)
    assert fp1 != fp3


def test_routing_key_format() -> None:
    key = routing_key("resume_generation", "v1", "abcdef0123456789abcdef0123456789")
    assert key == "resume_generation:v1:abcdef0123456789abcdef01"


def test_chat_usage_metrics_dict_and_object() -> None:
    # Test dictionary input
    response_dict = {
        "usage": {
            "prompt_tokens": 2048,
            "completion_tokens": 512,
            "prompt_tokens_details": {"cached_tokens": 1536},
        }
    }
    metrics = chat_usage_metrics(response_dict)
    assert metrics["input_tokens"] == 2048
    assert metrics["cached_input_tokens"] == 1536
    assert metrics["uncached_input_tokens"] == 512
    assert metrics["output_tokens"] == 512
    assert metrics["cache_read_ratio"] == 0.75

    # Test object input
    response_obj = types.SimpleNamespace(
        usage=types.SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=200,
            prompt_tokens_details=types.SimpleNamespace(cached_tokens=800),
        )
    )
    metrics_obj = chat_usage_metrics(response_obj)
    assert metrics_obj["input_tokens"] == 1000
    assert metrics_obj["cached_input_tokens"] == 800
    assert metrics_obj["uncached_input_tokens"] == 200
    assert metrics_obj["output_tokens"] == 200
    assert metrics_obj["cache_read_ratio"] == 0.80

    # Test missing usage
    empty_metrics = chat_usage_metrics(None)
    assert empty_metrics["cache_read_ratio"] == 0.0


def test_cache_aligned_slot_order_structure() -> None:
    # In canonical ordering, C0 (dynamic facts) precedes R0 (schema) and E0 (examples)
    c0_idx = CANONICAL_SLOT_ORDER.index("C0")
    r0_idx = CANONICAL_SLOT_ORDER.index("R0")
    e0_idx = CANONICAL_SLOT_ORDER.index("E0")
    assert c0_idx < r0_idx
    assert c0_idx < e0_idx

    # In cache-aligned ordering, R0 and E0 precede dynamic C0
    ca_c0_idx = CACHE_ALIGNED_SLOT_ORDER.index("C0")
    ca_r0_idx = CACHE_ALIGNED_SLOT_ORDER.index("R0")
    ca_e0_idx = CACHE_ALIGNED_SLOT_ORDER.index("E0")
    assert ca_r0_idx < ca_c0_idx
    assert ca_e0_idx < ca_c0_idx
    assert CACHE_ALIGNED_SLOT_ORDER[:3] == ["S0", "D0", "I0"]


def test_company_brief_static_system_prompt_stability() -> None:
    assert len(COMPANY_BRIEF_STATIC_SYSTEM_PROMPT) > 500
    assert "corporate intelligence analyst" in COMPANY_BRIEF_STATIC_SYSTEM_PROMPT
    assert "company_archetype" in COMPANY_BRIEF_STATIC_SYSTEM_PROMPT
    assert "strategic_priorities" in COMPANY_BRIEF_STATIC_SYSTEM_PROMPT
    assert "language_to_mirror" in COMPANY_BRIEF_STATIC_SYSTEM_PROMPT


def test_bare_pipeline_l2_system_prompt_stability() -> None:
    assert len(BARE_PIPELINE_L2_SYSTEM_PROMPT) > 500
    assert "<tailored_resume>" in BARE_PIPELINE_L2_SYSTEM_PROMPT
    assert "</tailored_resume>" in BARE_PIPELINE_L2_SYSTEM_PROMPT
    assert "<outreach_email>" in BARE_PIPELINE_L2_SYSTEM_PROMPT
    assert "CORE COMPETENCIES" in BARE_PIPELINE_L2_SYSTEM_PROMPT
    assert "PROFESSIONAL EXPERIENCE" in BARE_PIPELINE_L2_SYSTEM_PROMPT
