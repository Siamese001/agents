"""Unit tests for canonical cache identity and Wave 6 caching guarantees."""

from __future__ import annotations

import pytest

from apps_rg.cache.cache_identity import (
    BRIEFING_CACHE_SCHEMA_VERSION,
    CACHE_IDENTITY_SCHEMA_VERSION,
    CacheIdentity,
    compute_briefing_cache_key,
    compute_cache_identity_key,
)
from apps_rg.runtime.local_provider import min_cacheable_chars
from apps_rg.runtime.model_registry import get_registry_digest


def test_cache_identity_validity_guards():
    # Empty or 'unknown' critical values must be treated as uncacheable misses.
    id_empty_snap = CacheIdentity(
        resolved_model_snapshot="",
        registry_digest="sha256:abc",
        prompt_template_hash="tmpl1",
        generation_params={},
    )
    assert not id_empty_snap.is_cacheable()
    assert id_empty_snap.compute_key() == ""

    id_unknown_snap = CacheIdentity(
        resolved_model_snapshot="unknown",
        registry_digest="sha256:abc",
        prompt_template_hash="tmpl1",
        generation_params={},
    )
    assert not id_unknown_snap.is_cacheable()
    assert id_unknown_snap.compute_key() == ""

    id_unknown_reg = CacheIdentity(
        resolved_model_snapshot="model-pinned-1",
        registry_digest="UNKNOWN",
        prompt_template_hash="tmpl1",
        generation_params={},
    )
    assert not id_unknown_reg.is_cacheable()
    assert id_unknown_reg.compute_key() == ""


def test_cache_identity_sensitivity():
    # Changing pin, template, params, schema, or inputs must force a cache miss (different key).
    base_params = {"temperature": 0.2, "max_tokens": 1024}
    reg_digest = get_registry_digest()

    key_base = compute_cache_identity_key(
        resolved_model_snapshot="model-snap-v1",
        prompt_template_hash="tmpl-sha-1",
        generation_params=base_params,
        registry_digest=reg_digest,
    )
    assert key_base != ""

    # 1. Changed model snapshot
    key_diff_model = compute_cache_identity_key(
        resolved_model_snapshot="model-snap-v2",
        prompt_template_hash="tmpl-sha-1",
        generation_params=base_params,
        registry_digest=reg_digest,
    )
    assert key_diff_model != key_base

    # 2. Changed template hash
    key_diff_tmpl = compute_cache_identity_key(
        resolved_model_snapshot="model-snap-v1",
        prompt_template_hash="tmpl-sha-2",
        generation_params=base_params,
        registry_digest=reg_digest,
    )
    assert key_diff_tmpl != key_base

    # 3. Changed generation params
    key_diff_params = compute_cache_identity_key(
        resolved_model_snapshot="model-snap-v1",
        prompt_template_hash="tmpl-sha-1",
        generation_params={"temperature": 0.7, "max_tokens": 1024},
        registry_digest=reg_digest,
    )
    assert key_diff_params != key_base

    # 4. Changed schema version
    key_diff_schema = compute_cache_identity_key(
        resolved_model_snapshot="model-snap-v1",
        prompt_template_hash="tmpl-sha-1",
        generation_params=base_params,
        registry_digest=reg_digest,
        schema_version="2026-10-custom-v2",
    )
    assert key_diff_schema != key_base


def test_briefing_cache_key_incorporates_role_pin_and_schema():
    key_base = compute_briefing_cache_key(
        company_name="Google",
        jd_hash="sha256:jd123",
        target_role="Staff Engineer",
        model_pin="pinned-model-a",
    )
    assert key_base != ""

    # Changing target_role changes key
    key_diff_role = compute_briefing_cache_key(
        company_name="Google",
        jd_hash="sha256:jd123",
        target_role="Principal Engineer",
        model_pin="pinned-model-a",
    )
    assert key_diff_role != key_base

    # Changing model_pin changes key
    key_diff_pin = compute_briefing_cache_key(
        company_name="Google",
        jd_hash="sha256:jd123",
        target_role="Staff Engineer",
        model_pin="pinned-model-b",
    )
    assert key_diff_pin != key_base

    # Changing schema changes key
    key_diff_schema = compute_briefing_cache_key(
        company_name="Google",
        jd_hash="sha256:jd123",
        target_role="Staff Engineer",
        model_pin="pinned-model-a",
        schema_version="2026-10-briefing-v3",
    )
    assert key_diff_schema != key_base


def test_min_cacheable_chars_model_aware_floor():
    assert min_cacheable_chars("mock-haiku-tier") == 8192
    assert min_cacheable_chars("mock-sonnet-tier") == 4096
    assert min_cacheable_chars("mock-opus-tier") == 4096
    assert min_cacheable_chars("generic-fallback-model") == 1024


def test_r1b_compatibility_checks_model_profile_hash():
    from apps_rg.cache.r1b_compatibility import assess_candidate_for_reuse
    from apps_rg.cache.r1b_constants import (
        CHUNK_TYPE_EXEC_SUMMARY,
        CHUNK_TYPE_FINAL_RESUME,
        CHUNK_TYPE_SECTION_PROOF,
    )
    from apps_rg.cache.r1b_models import HistoricalIntentRecord, HistoricalOutputChunk

    record = HistoricalIntentRecord.from_dict({
        "record_id": "rec_001",
        "app_id": "apps_rg",
        "cache_grain": "ROLE_TARGET_RUN",
        "request_intent_text": "intent",
        "normalized_intent_digest": "dig_001",
        "request_intent_vector_ref": "vectors/rec_001.json",
        "source_run_id": "run_001",
        "target_company": "Acme",
        "target_role": "SWE",
        "job_family": "Engineering",
        "jd_digest": "jd_001",
        "briefing_digest": "br_001",
        "srfs_digest": "srfs_001",
        "proof_pool_digest": "proof_001",
        "skills_ledger_digest": "skills_001",
        "base_resume_digest": "base_001",
        "final_resume_digest": "final_001",
        "prompt_profile_hash": "prompt_hash_1",
        "model_profile_hash": "model_hash_1",
        "gate_profile_hash": "gate_hash_1",
        "x3_disposition": "X3D_ALLOW_FINISH",
        "proof_eligible": True,
        "cache_admissible": True,
        "generated_at_utc": "2026-10-01T00:00:00Z",
    })

    chunks = [
        HistoricalOutputChunk.from_dict({
            "chunk_id": "chunk_final",
            "parent_intent_record_id": "rec_001",
            "chunk_type": CHUNK_TYPE_FINAL_RESUME,
            "section_id": "final",
            "chunk_text": "Full resume text content here",
            "chunk_digest": "h1",
            "chunk_vector_ref": "vectors/h1.json",
            "artifact_ref": "artifacts/h1.json",
            "artifact_digest": "a1",
            "source_fact_ids": [],
            "proof_pool_refs": [],
            "support_status": "ALLOW",
            "x2_status": "PASS",
            "x1d_status": "PASS",
            "section_prompt_hash": "p1",
            "section_model_profile_hash": "m1",
            "generated_at_utc": "2026-10-01T00:00:00Z",
        }),
        HistoricalOutputChunk.from_dict({
            "chunk_id": "chunk_proof",
            "parent_intent_record_id": "rec_001",
            "chunk_type": CHUNK_TYPE_SECTION_PROOF,
            "section_id": "proof",
            "chunk_text": "Section proof summary text here",
            "chunk_digest": "h2",
            "chunk_vector_ref": "vectors/h2.json",
            "artifact_ref": "artifacts/h2.json",
            "artifact_digest": "a2",
            "source_fact_ids": [],
            "proof_pool_refs": [],
            "support_status": "ALLOW",
            "x2_status": "PASS",
            "x1d_status": "PASS",
            "section_prompt_hash": "p1",
            "section_model_profile_hash": "m1",
            "generated_at_utc": "2026-10-01T00:00:00Z",
        }),
        HistoricalOutputChunk.from_dict({
            "chunk_id": "chunk_sec",
            "parent_intent_record_id": "rec_001",
            "chunk_type": CHUNK_TYPE_EXEC_SUMMARY,
            "section_id": "executive_summary",
            "chunk_text": "Executive summary content here",
            "chunk_digest": "h3",
            "chunk_vector_ref": "vectors/h3.json",
            "artifact_ref": "artifacts/h3.json",
            "artifact_digest": "a3",
            "source_fact_ids": [],
            "proof_pool_refs": [],
            "support_status": "ALLOW",
            "x2_status": "PASS",
            "x1d_status": "PASS",
            "section_prompt_hash": "p1",
            "section_model_profile_hash": "m1",
            "generated_at_utc": "2026-10-01T00:00:00Z",
        }),
    ]

    # Matching model hash passes
    verdict_match = assess_candidate_for_reuse(
        record,
        chunks=chunks,
        query_digest="dig_001",
        query_prompt_hash="prompt_hash_1",
        query_gate_hash="gate_hash_1",
        query_model_hash="model_hash_1",
    )
    assert verdict_match.admissible

    # Differing model hash fails
    verdict_mismatch = assess_candidate_for_reuse(
        record,
        chunks=chunks,
        query_digest="dig_001",
        query_prompt_hash="prompt_hash_1",
        query_gate_hash="gate_hash_1",
        query_model_hash="model_hash_2",
    )
    assert not verdict_mismatch.admissible
    assert "model_profile_hash_match" in verdict_mismatch.reason


def test_self_consistency_parallel_enabled_summary_and_headline():
    from apps_rg.runtime.reasoning.bullet_lane_self_consistency import (
        self_consistency_max_parallel,
        self_consistency_parallel_enabled,
    )

    assert self_consistency_parallel_enabled("executive_summary")
    assert self_consistency_parallel_enabled("headline")
    assert self_consistency_parallel_enabled("headline_l6")
    assert self_consistency_max_parallel("executive_summary", 4) == 2
    assert self_consistency_max_parallel("headline", 4) == 2


def test_r1b_bge_embedding_content_cache(monkeypatch):
    from unittest.mock import MagicMock
    from apps_rg.cache import r1b_bge_embedding

    mock_runtime = MagicMock()
    mock_runtime.revision = "rev1"
    mock_runtime.dtype = "float32"
    dummy_vec = [1.0] + [0.0] * 1023
    mock_runtime.encode.return_value = [dummy_vec, dummy_vec]

    monkeypatch.setattr(r1b_bge_embedding, "_get_bge_runtime", lambda: mock_runtime)
    r1b_bge_embedding.clear_embed_content_cache()

    # 1st call: cache miss, encode called
    res1 = r1b_bge_embedding.embed_texts_bge(["hello world", "test resume"])
    assert mock_runtime.encode.call_count == 1
    assert len(res1) == 2
    assert res1[0] == dummy_vec

    # 2nd call: cache hit, encode NOT called again
    res2 = r1b_bge_embedding.embed_texts_bge(["hello world", "test resume"])
    assert mock_runtime.encode.call_count == 1
    assert res2 == res1

    # Clear cache, next call should hit runtime.encode again
    mock_runtime.encode.return_value = [dummy_vec]
    r1b_bge_embedding.clear_embed_content_cache()
    res3 = r1b_bge_embedding.embed_texts_bge(["hello world"])
    assert mock_runtime.encode.call_count == 2
    assert res3[0] == dummy_vec


def test_r1b_store_load_intent_vector_dimension_mismatch(tmp_path):
    import json
    from apps_rg.cache.r1b_models import HistoricalIntentRecord
    from apps_rg.cache.r1b_store import R1BSemanticCacheStore

    store = R1BSemanticCacheStore(tmp_path)

    # Create dummy vector file with mismatched dimensions (declared 1024, actual 2)
    vec_path = tmp_path / "vectors" / "mismatch.json"
    vec_path.parent.mkdir(parents=True, exist_ok=True)
    vec_path.write_text(
        json.dumps({"dimensions": 1024, "values": [0.1, 0.2]}),
        encoding="utf-8",
    )

    record = HistoricalIntentRecord.from_dict({
        "record_id": "rec_dim_test",
        "app_id": "apps_rg",
        "cache_grain": "ROLE_TARGET_RUN",
        "request_intent_text": "intent",
        "normalized_intent_digest": "dig_dim",
        "request_intent_vector_ref": "vectors/mismatch.json",
        "source_run_id": "run_001",
        "target_company": "Acme",
        "target_role": "SWE",
        "job_family": "Engineering",
        "jd_digest": "jd_001",
        "briefing_digest": "br_001",
        "srfs_digest": "srfs_001",
        "proof_pool_digest": "proof_001",
        "skills_ledger_digest": "skills_001",
        "base_resume_digest": "base_001",
        "final_resume_digest": "final_001",
        "prompt_profile_hash": "p1",
        "model_profile_hash": "m1",
        "gate_profile_hash": "g1",
        "x3_disposition": "X3D_ALLOW_FINISH",
        "proof_eligible": True,
        "cache_admissible": True,
        "generated_at_utc": "2026-10-01T00:00:00Z",
    })

    with pytest.raises(RuntimeError, match="DIMENSION_MISMATCH"):
        store.load_intent_vector(record)

    # Matching dimensions succeeds
    vec_path_ok = tmp_path / "vectors" / "ok.json"
    vec_path_ok.write_text(
        json.dumps({"dimensions": 3, "values": [0.1, 0.2, 0.3]}),
        encoding="utf-8",
    )
    record_ok = HistoricalIntentRecord.from_dict({
        **record.to_dict(),
        "record_id": "rec_dim_ok",
        "request_intent_vector_ref": "vectors/ok.json",
    })
    vals = store.load_intent_vector(record_ok)
    assert vals == [0.1, 0.2, 0.3]


def test_s0_d0_prefix_byte_identity():
    from apps_rg.runtime.dispatch.unify_ibm_pa_common import load_w7_shell_slot_bodies
    from apps_rg.runtime.providers.anthropic_section_cache_payload import TIER1_SLOTS

    shell_slots = load_w7_shell_slot_bodies()
    s0 = shell_slots.get("S0", "")
    d0 = shell_slots.get("D0", "")

    # Non-empty and contains required oaths
    assert len(s0) > 50
    assert "NO FABRICATION" in s0
    assert len(d0) > 30
    assert "untrusted_data_fence" in d0

    # Ensure stable across repeated loads (deterministic byte identity for Anthropic cache)
    repeat_slots = load_w7_shell_slot_bodies()
    assert s0 == repeat_slots["S0"]
    assert d0 == repeat_slots["D0"]

    # Verify TIER1_SLOTS treats S0 and D0 as prompt-cache tier 1 slots
    assert "S0" in TIER1_SLOTS
    assert "D0" in TIER1_SLOTS
