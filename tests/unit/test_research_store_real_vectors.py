"""Unit tests for Wave 2 1024-d L2-normalized vectors in InMemoryResearchStore."""

from __future__ import annotations

import math

from apps_research.engines.research_retrieval_engine import (
    InMemoryResearchStore,
    create_retrieval_engine,
)


def test_in_memory_research_store_produces_1024d_unit_vectors() -> None:
    engine = create_retrieval_engine(chromadb_path=None)
    rid_ai = engine.index_research(
        content="Enterprise AI platform strategy, agentic runtime governance, and BGE-M3 hybrid retrieval.",
        topic="AI Platform Strategy",
        artifact_mode="brief",
        quality_score=0.94,
        source_count=3,
        claim_types={"architecture": 4, "governance": 3},
        sources=["sec_10k", "architecture_rfc"],
    )
    rid_unrelated = engine.index_research(
        content="Oceanic container vessel hull maintenance, diesel fuel bunkering, and port crane scheduling.",
        topic="Maritime Freight Operations",
        artifact_mode="brief",
        quality_score=0.81,
        source_count=2,
        claim_types={"operations": 2},
        sources=["maritime_log"],
    )

    assert isinstance(engine.store, InMemoryResearchStore)
    for rid in (rid_ai, rid_unrelated):
        vec = engine.store._embeddings[rid]
        assert len(vec) == 1024
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) <= 1e-4

    results = engine.find_similar_research(
        current_topic="AI Platform Strategy and Agentic Governance",
        artifact_mode="brief",
        n_results=2,
    )
    assert len(results) == 2
    assert results[0].research_id == rid_ai
    assert results[0].similarity_score > results[1].similarity_score
