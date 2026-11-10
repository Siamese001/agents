"""Unit tests for compact 4-segment headline quality X2 gates (Wave 2)."""

from __future__ import annotations

from apps_rg.runtime.validators.headline_quality_x2 import (
    check_headline_compact_four_segment_format,
    check_headline_no_narrowing_it_labels,
    check_headline_positioning_families,
    check_headline_seniority_floor,
)
from apps_rg.runtime.validators.headline_x2 import has_valid_headline_prefix


def test_compact_four_segment_svp_enterprise_architecture_passes() -> None:
    hl = (
        "SVP Enterprise Architecture | Agentic AI Platforms "
        "| Cloud Data Modernization | Regulated Insurance Governance"
    )
    assert has_valid_headline_prefix(hl)
    assert check_headline_seniority_floor(hl).passed is True
    assert check_headline_no_narrowing_it_labels(hl).passed is True
    assert check_headline_positioning_families(hl).passed is True
    assert check_headline_compact_four_segment_format(hl).passed is True


def test_target_title_domain_terms_permitted_in_segment_one() -> None:
    for seg0 in ("SVP Enterprise Architecture", "SVP AI Strategy", "SVP IT Strategy"):
        hl = f"{seg0} | Agentic AI Platforms | Cloud Data Modernization | Regulated Insurance Governance"
        assert check_headline_seniority_floor(hl).passed is True
        assert check_headline_no_narrowing_it_labels(hl).passed is True
        assert check_headline_compact_four_segment_format(hl).passed is True


def test_bare_senior_vice_president_prefix_rejected() -> None:
    hl = "Senior Vice President | Three Lines Governance | Hyperscaler Alliance Ecosystem | Client Adoption Systems"
    assert has_valid_headline_prefix(hl) is False
    assert check_headline_seniority_floor(hl).passed is False
    assert check_headline_compact_four_segment_format(hl).passed is False


def test_four_word_segment_and_dollar_metrics_rejected_by_compact_format_gate() -> None:
    overlong = (
        "SVP Enterprise Architecture | Governed Agentic AI Platforms "
        "| Cloud Data Modernization | Regulated Insurance Governance"
    )
    assert check_headline_compact_four_segment_format(overlong).passed is False

    with_dollar = (
        "SVP Enterprise Architecture | $22M AI Platforms "
        "| Cloud Data Modernization | Regulated Insurance Governance"
    )
    assert check_headline_compact_four_segment_format(with_dollar).passed is False
