"""Unit tests for semantic research retrieval engine indexing and source recommendations."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# Ensure test harness mode allows mock embedding in InMemoryResearchStore
os.environ["APPS_RG_TEST_HARNESS"] = "1"

from apps_research.engines.research_retrieval_engine import (
    InMemoryResearchStore,
    ResearchRetrievalEngine,
    RetrievedResearch,
)


def test_index_research_same_second_generates_distinct_ids_with_content_hash():
    """Finding F-RRS-002: Same-second index_research calls with different content do not collide."""
    store = InMemoryResearchStore()
    engine = ResearchRetrievalEngine(store=store)

    fixed_time = "20261101_120000"
    with patch("apps_research.engines.research_retrieval_engine.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = fixed_time
        mock_dt.now.return_value.isoformat.return_value = "2026-11-01T12:00:00"

        id1 = engine.index_research(
            content="Alpha findings on battery density",
            topic="Clean Energy",
            artifact_mode="brief",
            quality_score=0.9,
            source_count=1,
            claim_types={"factual": 2},
            sources=["https://example.com/energy-alpha"],
        )
        id2 = engine.index_research(
            content="Beta findings on sodium-ion storage",
            topic="Clean Energy",
            artifact_mode="brief",
            quality_score=0.85,
            source_count=1,
            claim_types={"factual": 3},
            sources=["https://example.com/energy-beta"],
        )

        assert id1 != id2
        assert id1.startswith(f"research_brief_{fixed_time}_")
        assert id2.startswith(f"research_brief_{fixed_time}_")
        assert id1 in store._research
        assert id2 in store._research
        assert len(store._research) == 2


def test_index_research_persists_sources_metadata():
    """Finding F-RRS-001: index_research persists sources in metadata and updates source_count."""
    store = InMemoryResearchStore()
    engine = ResearchRetrievalEngine(store=store)

    sources = ["https://example.com/source-1", "https://example.com/source-2"]
    research_id = engine.index_research(
        content="Deep dive into semiconductor packaging",
        topic="Hardware",
        artifact_mode="deep_dive",
        quality_score=0.92,
        source_count=1,
        claim_types={"technical": 5},
        sources=sources,
    )

    item = store._research[research_id]
    assert item["metadata"]["sources"] == sources
    assert item["data"]["sources"] == sources
    assert item["data"]["source_count"] == 2


def test_recommend_sources_handles_native_list_and_stringified_sources():
    """Finding F-RRS-001: recommend_sources safely normalizes both native lists and Chroma-serialized string formats."""
    mock_store = InMemoryResearchStore()

    # Pre-populate mock store with research items returning native list and stringified list metadata
    res_native = RetrievedResearch(
        research_id="r1",
        topic="Robotics",
        artifact_mode="brief",
        timestamp="2026-11-01T10:00:00",
        content_preview="Autonomous navigation",
        quality_score=0.95,
        source_count=2,
        claim_types={},
        metadata={"sources": ["https://example.com/robotics-a", "https://example.com/robotics-b"]},
        similarity_score=0.9,
    )
    res_stringified = RetrievedResearch(
        research_id="r2",
        topic="Robotics",
        artifact_mode="brief",
        timestamp="2026-11-01T10:05:00",
        content_preview="Actuator designs",
        quality_score=0.88,
        source_count=2,
        claim_types={},
        metadata={"sources": "['https://example.com/robotics-b', 'https://example.com/robotics-c']"},
        similarity_score=0.85,
    )
    res_json_str = RetrievedResearch(
        research_id="r3",
        topic="Robotics",
        artifact_mode="brief",
        timestamp="2026-11-01T10:10:00",
        content_preview="Sensors",
        quality_score=0.87,
        source_count=1,
        claim_types={},
        metadata={"sources": '["https://example.com/robotics-d"]'},
        similarity_score=0.80,
    )

    with patch.object(mock_store, "query_similar", return_value=[res_native, res_stringified, res_json_str]):
        engine = ResearchRetrievalEngine(store=mock_store)
        recs = engine.recommend_sources(
            topic="Robotics",
            current_sources=["https://example.com/robotics-a"],
        )

        rec_urls = [r["source"] for r in recs]
        assert "https://example.com/robotics-a" not in rec_urls  # Already in current_sources
        assert "https://example.com/robotics-b" in rec_urls
        assert "https://example.com/robotics-c" in rec_urls
        assert "https://example.com/robotics-d" in rec_urls

        # Verify robotics-b has frequency 2 because it appeared in both r1 and r2
        freq_b = next(r["frequency_in_similar"] for r in recs if r["source"] == "https://example.com/robotics-b")
        assert freq_b == 2


def test_embedding_deduplication_and_catalog_model_resolution():
    """Wave 1 Tokenomics: InMemoryResearchStore deduplicates identical embeddings via SHA-256 cache and resolves model ID from catalog."""
    store = InMemoryResearchStore()
    model_id = store._resolve_embedding_model_id()
    assert model_id == "BAAI/bge-m3"

    emb1 = store._mock_embed("Enterprise AI platform architecture")
    assert len(store._digest_embedding_cache) == 1
    emb2 = store._mock_embed("Enterprise AI platform architecture")
    assert emb1 == emb2
    assert len(store._digest_embedding_cache) == 1

