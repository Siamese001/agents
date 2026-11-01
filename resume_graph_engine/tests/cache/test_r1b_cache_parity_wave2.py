"""Unit tests for Wave 2 Resume Graph Traversal & Cache Invalidation Parity."""

from __future__ import annotations

from unittest.mock import patch

from apps_rg.cache import briefing_cache, cache_identity
from apps_rg.cache.r1b_constants import (
    CACHE_GRAIN_ROLE_TARGET_RUN,
    CHUNK_TYPE_FINAL_RESUME,
    CHUNK_TYPE_SECTION_PROOF,
    SECTION_CHUNK_TYPES,
)
from apps_rg.cache.r1b_intent_vector import (
    intent_text_from_request,
    normalized_intent_digest,
    pseudo_vector_from_digest,
)
from apps_rg.cache.r1b_models import HistoricalIntentRecord, HistoricalOutputChunk
from apps_rg.cache.r1b_retrieval import (
    lookup_r1b_role_target_run,
    lookup_r1b_with_compatibility_report,
)
from apps_rg.chunking.resume_chunker import ChunkerConfig, ResumeChunker


def _make_record(record_id: str, model_profile_hash: str) -> HistoricalIntentRecord:
    return HistoricalIntentRecord(
        record_id=record_id,
        app_id="apps_rg",
        cache_grain=CACHE_GRAIN_ROLE_TARGET_RUN,
        request_intent_text="apps_rg|role_target_run|acme|vp_ai|strategic_tailor|j1|b1|r1",
        normalized_intent_digest="d1",
        request_intent_vector_ref=f"vectors/{record_id}.json",
        source_run_id=f"run-{record_id}",
        target_company="Acme",
        target_role="VP AI",
        job_family="executive",
        jd_digest="jd-digest-1",
        briefing_digest="brief-digest-1",
        srfs_digest="srfs-1",
        proof_pool_digest="pool-1",
        skills_ledger_digest="skills-1",
        base_resume_digest="base-1",
        final_resume_digest="final-1",
        prompt_profile_hash="prompt-hash-v1",
        model_profile_hash=model_profile_hash,
        gate_profile_hash="gate-hash-v1",
        x3_disposition="X3D_ALLOW_FINISH",
        proof_eligible=True,
        cache_admissible=True,
        generated_at_utc="2026-11-01T00:00:00Z",
    )


def _make_chunks(record_id: str) -> list[HistoricalOutputChunk]:
    sec_type = sorted(SECTION_CHUNK_TYPES)[0]
    return [
        HistoricalOutputChunk(
            chunk_id=f"{record_id}-final",
            parent_intent_record_id=record_id,
            chunk_type=CHUNK_TYPE_FINAL_RESUME,
            section_id="final",
            chunk_text="Complete tailored executive resume content.",
            chunk_digest="cd-1",
            chunk_vector_ref="",
            artifact_ref="final.md",
            artifact_digest="ad-1",
            source_fact_ids=["f1"],
            proof_pool_refs=["p1"],
            support_status="PASS",
            x2_status="PASS",
            x1d_status="PASS",
            section_prompt_hash="prompt-hash-v1",
            section_model_profile_hash="model-hash-v1",
            generated_at_utc="2026-11-01T00:00:00Z",
        ),
        HistoricalOutputChunk(
            chunk_id=f"{record_id}-proof",
            parent_intent_record_id=record_id,
            chunk_type=CHUNK_TYPE_SECTION_PROOF,
            section_id="summary",
            chunk_text="Proof summary text for executive section.",
            chunk_digest="cd-2",
            chunk_vector_ref="",
            artifact_ref="proof.json",
            artifact_digest="ad-2",
            source_fact_ids=["f1"],
            proof_pool_refs=["p1"],
            support_status="PASS",
            x2_status="PASS",
            x1d_status="PASS",
            section_prompt_hash="prompt-hash-v1",
            section_model_profile_hash="model-hash-v1",
            generated_at_utc="2026-11-01T00:00:00Z",
        ),
        HistoricalOutputChunk(
            chunk_id=f"{record_id}-sec",
            parent_intent_record_id=record_id,
            chunk_type=sec_type,
            section_id="executive_summary",
            chunk_text="Executive summary display text with sufficient length.",
            chunk_digest="cd-3",
            chunk_vector_ref="",
            artifact_ref="sec.md",
            artifact_digest="ad-3",
            source_fact_ids=["f1"],
            proof_pool_refs=["p1"],
            support_status="PASS",
            x2_status="PASS",
            x1d_status="PASS",
            section_prompt_hash="prompt-hash-v1",
            section_model_profile_hash="model-hash-v1",
            generated_at_utc="2026-11-01T00:00:00Z",
        ),
    ]


class _FakeR1BStore:
    def __init__(self, records: dict[str, HistoricalIntentRecord], vec: list[float]) -> None:
        self._records = records
        self._vec = vec

    def list_intent_record_ids(self) -> list[str]:
        return list(self._records.keys())

    def load_intent(self, rid: str) -> HistoricalIntentRecord | None:
        return self._records.get(rid)

    def load_intent_vector(self, record: HistoricalIntentRecord) -> list[float]:  # noqa: ARG002
        return self._vec

    def load_chunks(self, record_id: str) -> list[HistoricalOutputChunk]:
        return _make_chunks(record_id)


def test_r1b_lookup_enforces_query_model_hash_and_tie_breaks_deterministically() -> None:
    raw_req = {
        "target_company": "Acme",
        "target_role": "VP AI",
        "jd_hash": "j1",
        "brief_hash": "b1",
        "resume_hash": "r1",
    }
    intent_text = intent_text_from_request(raw_req)
    q_digest = normalized_intent_digest(intent_text)
    vec = pseudo_vector_from_digest(q_digest)

    records = {
        "rec_z": _make_record("rec_z", "model-pin-v1"),
        "rec_a": _make_record("rec_a", "model-pin-v1"),
    }
    fake_store = _FakeR1BStore(records, vec)

    with patch(
        "apps_rg.cache.r1b_bge_embedding.resolve_query_vector",
        return_value=(vec, "pseudo"),
    ):
        hit = lookup_r1b_role_target_run(
            raw_req,
            store=fake_store,  # type: ignore[arg-type]
            query_model_hash="model-pin-v1",
        )
        assert hit is not None
        assert hit.record.record_id == "rec_a"

        miss = lookup_r1b_role_target_run(
            raw_req,
            store=fake_store,  # type: ignore[arg-type]
            query_model_hash="model-pin-v2-mismatch",
        )
        assert miss is None

        report_hit, report_rows = lookup_r1b_with_compatibility_report(
            raw_req,
            store=fake_store,  # type: ignore[arg-type]
            query_model_hash="model-pin-v2-mismatch",
        )
        assert report_hit is None
        assert len(report_rows) == 2
        assert all(not row["admissible"] for row in report_rows)


def test_briefing_cache_key_default_schema_matches_cache_identity() -> None:
    k_brief = briefing_cache.compute_briefing_cache_key(
        company_name="Acme",
        jd_hash="abc123",
        target_role="VP Engineering",
        model_pin="pin-1",
    )
    k_id = cache_identity.compute_briefing_cache_key(
        company_name="Acme",
        jd_hash="abc123",
        target_role="VP Engineering",
        model_pin="pin-1",
    )
    assert k_brief == k_id


def test_resume_chunker_enforces_forward_progress_when_overlap_exceeds_max_tokens() -> None:
    cfg = ChunkerConfig(
        max_tokens_per_chunk=5,
        overlap_tokens=10,
        chars_per_token_ratio=4.0,
    )
    chunker = ResumeChunker(config=cfg)
    text = "A" * 50
    chunks = chunker.chunk_section("experience", text)
    assert len(chunks) >= 2
    assert chunks[0].chunk_id == "experience_0"
    assert chunks[-1].is_last_chunk
