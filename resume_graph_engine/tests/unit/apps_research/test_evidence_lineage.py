"""Tests for Apps Research evidence lineage at the Apps RG handoff seam."""

from __future__ import annotations

from apps_research.integrations.evidence_lineage import materialize_research_evidence


def test_materialize_reuses_the_sealed_company_brief_source_portfolio() -> None:
    """A hop-produced brief must carry its own source URLs into the handoff."""

    company_brief = {
        "company": "Brown & Brown",
        "_c0_bundle": {
            "source_portfolio_summary": {
                "source_urls": [
                    "https://us.bbrown.com/about/",
                    "https://investor.bbrown.com/news-events/news-releases",
                ]
            }
        },
    }

    evidence = materialize_research_evidence(
        bundle=None,
        request=object(),
        support_coverage=0.0,
        company_brief=company_brief,
    )

    assert [(item.source_id, item.uri) for item in evidence] == [
        ("brief-url-0", "https://us.bbrown.com/about/"),
        ("brief-url-1", "https://investor.bbrown.com/news-events/news-releases"),
    ]
    assert all(item.source_type == "web" for item in evidence)
    assert all(item.field_ref == "company_brief_ref" for item in evidence)


def test_materialize_prefers_substrate_c0_evidence_over_company_brief_fallback() -> None:
    """The normal substrate C0 evidence remains the first-choice lineage."""

    class Chunk:
        chunk_id = "chunk-1"
        content = "Grounded source"
        combined_score = 0.9
        metadata = {
            "source_url": "https://example.com/grounded",
            "title": "Grounded source",
            "source_type": "web",
        }

    class Bundle:
        ranked_chunks = [Chunk()]

    evidence = materialize_research_evidence(
        bundle=Bundle(),
        request=object(),
        support_coverage=0.0,
        company_brief={
            "_c0_bundle": {
                "source_portfolio_summary": {
                    "source_urls": ["https://fallback.example/"]
                }
            }
        },
    )

    assert [(item.source_id, item.uri) for item in evidence] == [
        ("chunk-1", "https://example.com/grounded")
    ]
