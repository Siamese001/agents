"""Unit tests for governed research evidence lineage materialization."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps_research.integrations.evidence_lineage import (
    evidence_from_c0_bundle,
    evidence_from_company_brief,
    materialize_research_evidence,
)
from apps_research.types.research_types import ResearchRequest


def test_materialize_evidence_returns_c0_bundle_when_present():
    bundle = SimpleNamespace(
        ranked_chunks=[
            SimpleNamespace(
                chunk_id="c1",
                metadata={"source_url": "https://example.com/acme", "title": "Acme"},
                combined_score=0.9,
            )
        ]
    )
    items = materialize_research_evidence(
        bundle=bundle,
        request=ResearchRequest(topic="Acme"),
        support_coverage=0.9,
    )
    assert len(items) == 1
    assert items[0].uri == "https://example.com/acme"


def test_materialize_evidence_skips_redundant_engine_execution_when_brief_provided():
    """Finding F-RRS-003: If non-empty company_brief is evaluated with 0 extracted claims, do not re-run engine."""
    empty_brief = {
        "company_name": "Acme",
        "_c0_bundle": {
            "source_portfolio_summary": {"source_urls": []},
            "claim_evidence_map": {"supported_count": 0},
        },
    }
    with patch("apps_research.engines.company_brief_engine.CompanyBriefEngine") as mock_engine_cls:
        mock_instance = MagicMock()
        mock_engine_cls.return_value = mock_instance

        items = materialize_research_evidence(
            bundle=None,
            request=ResearchRequest(topic="Acme"),
            support_coverage=0.0,
            company_brief=empty_brief,
        )
        assert items == ()
        mock_instance.execute.assert_not_called()


def test_materialize_evidence_executes_fallback_engine_when_brief_is_none():
    """Standalone callers passing company_brief=None still trigger fallback CompanyBriefEngine."""
    with patch("apps_research.engines.company_brief_engine.CompanyBriefEngine") as mock_engine_cls:
        mock_instance = MagicMock()
        mock_engine_cls.return_value = mock_instance
        mock_instance.execute.return_value = {
            "company_name": "Acme",
            "_c0_bundle": {
                "source_portfolio_summary": {
                    "source_urls": ["https://example.com/source1"],
                },
            },
        }

        items = materialize_research_evidence(
            bundle=None,
            request=ResearchRequest(topic="Acme"),
            support_coverage=0.8,
            company_brief=None,
        )
        assert len(items) == 1
        assert items[0].uri == "https://example.com/source1"
        mock_instance.execute.assert_called_once()
