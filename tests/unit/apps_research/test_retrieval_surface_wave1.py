"""Unit tests for Wave 1 Research & Retrieval Surface remediation."""

from __future__ import annotations

import ast
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps_research.engines.hop_research_retrieval_engine import HopResearchRetrievalEngine
from apps_research.engines.research_retrieval_engine import (
    InMemoryResearchStore,
    ResearchRetrievalEngine,
    RetrievedResearch,
)
from apps_research.integrations.evidence_lineage import materialize_research_evidence
from apps_research.integrations.reranker_adapter import rerank
from apps_research.integrations.search_retrieval import RetrievedDoc
from apps_research.provenance.ledger import ProvenanceLedger, build_ledger_from_sections
from apps_research.types.research_types import ResearchSection
from apps_research.utils.chunking import chunk_text


def test_chunk_text_rejects_invalid_overlap_and_chunk_tokens() -> None:
    with pytest.raises(ValueError, match="chunk_tokens must be positive"):
        chunk_text("hello world", chunk_tokens=0, overlap_tokens=0)

    with pytest.raises(ValueError, match="overlap_tokens must be in"):
        chunk_text("hello world", chunk_tokens=10, overlap_tokens=10)

    with pytest.raises(ValueError, match="overlap_tokens must be in"):
        chunk_text("hello world", chunk_tokens=10, overlap_tokens=-1)

    chunks = chunk_text("one two three four five six seven eight", chunk_tokens=4, overlap_tokens=1)
    assert len(chunks) >= 2


def test_rerank_coerces_nan_and_breaks_ties_deterministically() -> None:
    docs = [
        RetrievedDoc(url="https://b.example.com", title="Beta", snippet="s", score=0.85),
        RetrievedDoc(url="https://a.example.com", title="Alpha", snippet="s", score=0.85),
        RetrievedDoc(url="https://nan.example.com", title="NaN Doc", snippet="s", score=float("nan")),
    ]
    ranked = rerank("test query", docs, cutoff=3)
    assert [d.url for d in ranked] == [
        "https://a.example.com",
        "https://b.example.com",
        "https://nan.example.com",
    ]
    assert not any(math.isnan(d.score) for d in ranked)
    assert ranked[-1].score == 0.0


def test_in_memory_research_store_deterministic_tie_breaking() -> None:
    store = InMemoryResearchStore()
    same_data = {"content": "identical content", "quality_score": 0.9, "source_count": 3, "claim_types": {}}
    store.add_research("res_z", same_data, {"topic": "AI", "artifact_mode": "brief"})
    store.add_research("res_a", same_data, {"topic": "AI", "artifact_mode": "brief"})

    results = store.query_similar({"topic": "AI"}, n_results=2, filters={"artifact_mode": "brief"})
    assert [r.research_id for r in results] == ["res_a", "res_z"]

    engine = ResearchRetrievalEngine(store=store)
    store.add_research(
        "res_sources",
        same_data,
        {"topic": "AI", "artifact_mode": "brief", "sources": ["src_z", "src_a"]},
    )
    recs = engine.recommend_sources("AI", current_sources=[])
    assert [r["source"] for r in recs[:2]] == ["src_a", "src_z"]


def test_evidence_lineage_preserves_dossier_and_forensic_depth_profiles() -> None:
    captured_payloads: list[dict] = []

    class FakeCompanyBriefEngine:
        def execute(self, payload: dict) -> dict:
            captured_payloads.append(payload)
            return {
                "_c0_bundle": {
                    "source_portfolio_summary": {
                        "source_urls": ["https://example.com/dossier-source"],
                    }
                }
            }

    request = SimpleNamespace(
        topic="Acme Corp",
        depth_profile="COMPANY_BRIEF_DOSSIER",
        jd_context={"role": "Principal Architect"},
    )
    with patch(
        "apps_research.engines.company_brief_engine.CompanyBriefEngine",
        FakeCompanyBriefEngine,
    ):
        items = materialize_research_evidence(
            bundle=None,
            request=request,
            support_coverage=0.88,
            company_brief=None,
        )

    assert len(items) == 1
    assert items[0].uri == "https://example.com/dossier-source"
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["depth"] == "dossier"
    assert captured_payloads[0]["depth_profile"] == "COMPANY_BRIEF_DOSSIER"


def test_provenance_ledger_and_hop_retrieval_preserve_metadata_and_return_annotations() -> None:
    section = ResearchSection(
        section_id="sec-1",
        heading="Strategic Overview",
        body="Acme Corp expanded enterprise platform adoption by 42 percent across global regions.",
        claim_type="direct_evidence",
        sources=["src-1"],
    )
    ledger = build_ledger_from_sections([section])
    assert isinstance(ledger, ProvenanceLedger)
    assert len(ledger.claims) == 1

    fake_retrieved = [
        RetrievedResearch(
            research_id="r-1",
            topic="Acme",
            artifact_mode="brief",
            timestamp="2026-11-01T00:00:00Z",
            content_preview="preview",
            quality_score=0.91,
            source_count=4,
            claim_types={"direct_evidence": 2},
            similarity_score=0.95,
        )
    ]
    with patch("apps_research.engines.research_retrieval_engine.create_retrieval_engine") as mock_create:
        mock_create.return_value.find_similar_research.return_value = fake_retrieved
        hop_out = HopResearchRetrievalEngine().execute(
            {"research_request": SimpleNamespace(topic="Acme")}
        )
    assert hop_out["retrieved_research"][0]["source_count"] == 4
    assert hop_out["retrieved_research"][0]["timestamp"] == "2026-11-01T00:00:00Z"

    repo_root = Path(__file__).resolve().parents[3]
    for rel in ("apps_research/provenance/ledger.py", "apps_research/types/research_types.py"):
        tree = ast.parse((repo_root / rel).read_text(encoding="utf-8"))
        untyped = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_") and node.returns is None
        ]
        assert untyped == [], f"Unexpected untyped public functions in {rel}: {untyped}"
