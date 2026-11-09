"""Unit tests for Research Retrieval Challenger Service and Research Service Integration.

Part of Monorepo-Wide Swarm Integration (Wave 2).
Verifies source attribution, cross-examination against knowledge graph assertions,
rejection of ungrounded extrapolations, and durable receipt generation.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from apps_research.reasoning.retrieval_challenger import (
    EvidenceAttribution,
    RetrievalChallenger,
    RetrievalDisposition,
    RetrievalDeliberationReceipt,
)
from apps_research.services.research_service import (
    CertifiedResearchResult,
    ResearchService,
)


def test_retrieval_challenger_certifies_grounded_claims() -> None:
    """Claims supported by sources should be verified and attributed."""
    challenger = RetrievalChallenger()
    query = "Enterprise cloud migration benefits"
    claims = (
        "Cloud modernization reduced infrastructure operational overhead.",
        "Container orchestration improved deployment velocity across engineering teams.",
    )
    sources = (
        {
            "id": "doc_01",
            "title": "Cloud Modernization Strategy",
            "content": "Enterprise cloud modernization reduced infrastructure operational overhead significantly.",
        },
        {
            "id": "doc_02",
            "title": "Container Architecture Review",
            "content": "Adopting container orchestration improved deployment velocity across all engineering teams.",
        },
    )

    receipt = challenger.cross_examine(
        query=query,
        claims=claims,
        sources=sources,
    )

    assert receipt.final_disposition == RetrievalDisposition.VERIFIED
    assert len(receipt.certified_claims) == 2
    assert len(receipt.rejected_claims) == 0
    assert receipt.groundedness_score == 1.0
    assert receipt.calibrated_confidence >= 0.85
    assert all(a.is_corroborated for a in receipt.attributions)


def test_retrieval_challenger_rejects_unsupported_extrapolations() -> None:
    """Ungrounded extrapolations lacking evidence must be rejected with repair directives."""
    challenger = RetrievalChallenger()
    query = "AI governance cost impact"
    claims = (
        "Strict governance reduced API retry waste.",
        "System tripled enterprise valuation within ninety days.",  # Ungrounded extrapolation
    )
    sources = (
        {
            "id": "audit_doc",
            "title": "Platform Token Economics",
            "content": "Strict governance reduced API retry waste by enforcing bounded socratic loops.",
        },
    )

    receipt = challenger.cross_examine(
        query=query,
        claims=claims,
        sources=sources,
    )

    assert receipt.final_disposition == RetrievalDisposition.NEEDS_CORROBORATION
    assert len(receipt.certified_claims) == 1
    assert len(receipt.rejected_claims) == 1
    assert "System tripled enterprise valuation within ninety days." in receipt.rejected_claims
    assert receipt.groundedness_score == 0.50


def test_retrieval_challenger_corroborates_with_knowledge_graph_assertions() -> None:
    """Canonical assertion graphs should corroborate claims even if source documents lack them."""
    challenger = RetrievalChallenger()
    query = "Factual assertions governance"
    claims = (
        "Core assertion graph contains 38 verified enterprise clusters.",
    )
    sources = ()  # No raw sources
    graph_assertions = (
        "Factual assertion graph maintains exactly 38 verified enterprise clusters for domain derivation.",
    )

    receipt = challenger.cross_examine(
        query=query,
        claims=claims,
        sources=sources,
        canonical_graph_assertions=graph_assertions,
    )

    assert receipt.final_disposition == RetrievalDisposition.VERIFIED
    assert len(receipt.certified_claims) == 1
    assert receipt.attributions[0].source_title == "Canonical Assertion Graph"
    assert receipt.attributions[0].is_corroborated is True


def test_retrieval_deliberation_receipt_serialization(tmp_path: Path) -> None:
    """Receipt should serialize cleanly to disk with all provenance fields."""
    challenger = RetrievalChallenger()
    receipt = challenger.cross_examine(
        query="Provenance serialization test",
        claims=("Verified architectural boundary enforcement.",),
        sources=({"id": "s1", "title": "Boundary Spec", "content": "Verified architectural boundary enforcement."},),
    )

    receipt_dict = receipt.to_dict()
    assert receipt_dict["query"] == "Provenance serialization test"
    assert receipt_dict["final_disposition"] == "VERIFIED"
    assert len(receipt_dict["attributions"]) == 1

    target_file = tmp_path / "wave2_receipt_test.json"
    written_path = receipt.write_to_path(target_file)
    assert written_path.is_file()

    loaded = json.loads(written_path.read_text(encoding="utf-8"))
    assert loaded["query"] == "Provenance serialization test"
    assert loaded["final_disposition"] == "VERIFIED"


def test_research_service_end_to_end_synthesis() -> None:
    """ResearchService must filter ungrounded claims and output certified findings."""
    service = ResearchService()
    query = "Autonomous agent verification"
    candidate_claims = (
        "Autonomous agents require fail-closed execution bounds.",
        "Unbounded retry loops always achieve optimal convergence.",  # Ungrounded / false
    )
    sources = (
        {
            "id": "gov_spec",
            "title": "Agentic Governance Invariants",
            "content": "Autonomous agents require fail-closed execution bounds to prevent runaway cost.",
        },
    )

    result = service.synthesize_research(
        query=query,
        candidate_claims=candidate_claims,
        sources=sources,
    )

    assert len(result.certified_findings) == 1
    assert "Autonomous agents require fail-closed execution bounds." in result.certified_findings
    assert len(result.unverified_findings_rejected) == 1
    assert "Unbounded retry loops always achieve optimal convergence." in result.unverified_findings_rejected
    assert result.is_fully_grounded is False
    assert result.receipt.groundedness_score == 0.50
