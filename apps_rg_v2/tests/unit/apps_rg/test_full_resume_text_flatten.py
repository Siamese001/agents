"""Whole-résumé flatten text — gap placeholders for incomplete sections."""

from __future__ import annotations

from apps_rg.runtime.assembly.full_resume_text import flatten_final_resume_to_text


def test_flatten_emits_not_completed_markers_when_sections_empty() -> None:
    text = flatten_final_resume_to_text(
        {
            "candidate_identity": {"candidate_name": "Test Candidate", "header_contact": {}},
            "sections": [],
        }
    )
    assert "[NOT COMPLETED: headline — missing_or_empty_headline]" in text
    assert "[NOT COMPLETED: insurtech — missing_generated_role_section]" in text
    assert "[NOT COMPLETED: competencies —" in text


def test_generated_role_omits_bullet_that_repeats_narrative_verbatim() -> None:
    narrative = "Led AWS modernization for regulated insurance platforms."
    text = flatten_final_resume_to_text(
        {
            "candidate_identity": {"candidate_name": "Test Candidate", "header_contact": {}},
            "sections": [
                {
                    "section_id": "insurtech_narrative",
                    "assemble_order": 1,
                    "l2_output_snapshot": {
                        "insurtech_header": {"employer": "InsurTech", "title": "CTO"},
                        "narrative_sentence": narrative,
                    },
                },
                {
                    "section_id": "insurtech_bullets",
                    "assemble_order": 2,
                    "l2_output_snapshot": {
                        "bullets": [
                            {"bullet_text": narrative},
                            {"bullet_text": "Built a governed migration delivery model."},
                        ]
                    },
                },
            ],
        }
    )

    assert text.count(narrative) == 1
    assert "• Built a governed migration delivery model." in text


def test_flatten_compacts_graph_competencies_into_executive_display_clusters() -> None:
    allocation_terms = (
        "Buyer-specific solution mapping",
        "Partner AI co-sell execution",
        "Enterprise pursuit execution",
        "Partner value realization",
        "AI co-sell bundling",
        "Agentic platform route-policy dispatch",
        "Regulated DevSecOps release governance",
        "Presales-to-delivery handoff cadence",
    )
    categories = [
        ("cloud_partner_ecosystems", allocation_terms[:2]),
        ("commercial_operating_impact", allocation_terms[2:5]),
        ("ai_platform_leadership", allocation_terms[5:6]),
        ("governance_risk_compliance", allocation_terms[6:7]),
        ("llmops_reliability", ("evaluation assurance",)),
        ("tech_strategy_innovation", ("relationship-grounded retrieval",)),
        ("data_analytics_modernization", ("cloud-native data architecture",)),
        ("engineering_delivery_leadership", allocation_terms[7:8]),
    ]
    snapshot = {
        "competencies": [
            {
                "category_id": category_id,
                "terms": [
                    {
                        "text": term,
                        **(
                            {"allocation_claim_unit_id": f"skill:{index}"}
                            if term in allocation_terms
                            else {}
                        ),
                    }
                    for index, term in enumerate(terms)
                ],
            }
            for category_id, terms in categories
        ]
    }
    text = flatten_final_resume_to_text(
        {
            "candidate_identity": {"candidate_name": "Test Candidate", "header_contact": {}},
            "sections": [{"section_id": "competencies", "l2_output_snapshot": snapshot}],
        }
    )

    assert "Partner AI Architecture & Commercialization:" in text
    assert "Governed AI Platforms & Reliability:" in text
    assert "Enterprise Architecture & Delivery:" in text
    assert "Cloud & Partner Ecosystems:" not in text
    assert all(term in text for term in allocation_terms)


def test_flatten_omits_ey_not_completed_when_ey_empty_and_consolidated() -> None:
    """Verify that consolidated EY (empty narrative and bullets) does not emit gap markers."""
    text = flatten_final_resume_to_text(
        {
            "candidate_identity": {"candidate_name": "Test Candidate", "header_contact": {}},
            "sections": [
                {
                    "section_id": "ey_narrative",
                    "assemble_order": 10,
                    "l2_output_snapshot": {
                        "ey_header": {"employer": "Ernst & Young", "title": "Principal"},
                        "narrative_sentence": "",
                    },
                },
                {
                    "section_id": "ey_bullets",
                    "assemble_order": 11,
                    "l2_output_snapshot": {
                        "bullets": [],
                    },
                },
            ],
        }
    )
    assert "[NOT COMPLETED: ey" not in text
    assert "Ernst & Young" not in text

