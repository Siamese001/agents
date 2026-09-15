"""Unit tests for apps_rg prompt caching contracts and segment classifications."""

import pytest
from apps_rg.prompt_assembly.prompt_segment import (
    PromptScope,
    PromptSegment,
    canonical_prompt_json,
    classify_slot_scope,
    compute_stable_prefix_hash,
)
from apps_rg.prompt_assembly.contracts import SlotAuthority


def test_prompt_scope_values():
    assert PromptScope.GLOBAL_STATIC.value == "global_static"
    assert PromptScope.JOB_SCOPED.value == "job_scoped"
    assert PromptScope.CANDIDATE_SCOPED.value == "candidate_scoped"
    assert PromptScope.REQUEST_SCOPED.value == "request_scoped"


def test_classify_slot_scope():
    # Global static instructions, schemas, fences
    for slot in ["S0", "D0", "I0", "E0", "Y0", "R0", "M0"]:
        assert classify_slot_scope(slot) == PromptScope.GLOBAL_STATIC

    # Job-scoped evidence and context
    assert classify_slot_scope("C0") == PromptScope.JOB_SCOPED

    # Request-scoped dynamic elements
    assert classify_slot_scope("U0") == PromptScope.REQUEST_SCOPED
    assert classify_slot_scope("H0") == PromptScope.REQUEST_SCOPED


def test_canonical_prompt_json_is_deterministic():
    obj1 = {"b": 2, "a": 1, "nested": {"z": 9, "y": 8}}
    obj2 = {"nested": {"y": 8, "z": 9}, "a": 1, "b": 2}
    
    assert canonical_prompt_json(obj1) == canonical_prompt_json(obj2)
    assert canonical_prompt_json(obj1) == '{"a":1,"b":2,"nested":{"y":8,"z":9}}'


def test_prompt_segment_creation_and_hash():
    seg = PromptSegment(
        name="S0_SYSTEM",
        scope=PromptScope.GLOBAL_STATIC,
        text="You are an expert executive resume writer.",
        cache_breakpoint=True,
    )
    assert seg.content_hash != ""
    assert seg.token_estimate > 0
    assert seg.cache_breakpoint is True
    
    anthropic_block = seg.to_anthropic_block()
    assert anthropic_block["type"] == "text"
    assert anthropic_block["text"] == seg.text
    assert anthropic_block.get("cache_control") == {"type": "ephemeral"}


def test_compute_stable_prefix_hash_invariance():
    seg_static1 = PromptSegment(name="S0", scope=PromptScope.GLOBAL_STATIC, text="Static rule 1")
    seg_static2 = PromptSegment(name="I0", scope=PromptScope.GLOBAL_STATIC, text="Static rule 2")
    seg_job_a = PromptSegment(name="C0", scope=PromptScope.JOB_SCOPED, text="Company A JD")
    seg_job_b = PromptSegment(name="C0", scope=PromptScope.JOB_SCOPED, text="Company B JD")

    # Global static prefix hash must be identical regardless of downstream job changes
    prefix_a = compute_stable_prefix_hash([seg_static1, seg_static2, seg_job_a], max_scope=PromptScope.GLOBAL_STATIC)
    prefix_b = compute_stable_prefix_hash([seg_static1, seg_static2, seg_job_b], max_scope=PromptScope.GLOBAL_STATIC)
    
    assert prefix_a == prefix_b
    assert len(prefix_a) == 16
