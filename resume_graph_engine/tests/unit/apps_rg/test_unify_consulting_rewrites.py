"""Unit tests for deterministic rewriting of generic consulting phrases in unify_narrative."""
from apps_rg.runtime.sections.cross_section_signal_guards import (
    detect_generic_consulting_phrases,
    rewrite_generic_consulting_phrases,
)
from apps_rg.runtime.sections.unify_narrative_lane import (
    normalize_unify_narrative_parsed,
)


def test_unify_narrative_normalizer_rewrites_consulting_delivery():
    raw_sentence = (
        "Owned Unify Consulting's mandate to industrialize agentic AI through a governed runtime "
        "and distributed data foundation, aligning architecture, lifecycle discipline, and alliance "
        "distribution into an IP-led operating model that advanced regulated-enterprise adoption "
        "and turned consulting delivery into durable platform services."
    )
    assert "consulting delivery" in detect_generic_consulting_phrases(raw_sentence)

    cleaned = rewrite_generic_consulting_phrases(raw_sentence)
    assert not detect_generic_consulting_phrases(cleaned)
    assert "bespoke enterprise delivery" in cleaned

    parsed_doc = {
        "narrative_sentence": raw_sentence,
        "claim_ledger": [{"claim_text": raw_sentence, "source_fact_ids": ["bul_unify_001"]}],
    }
    norm = normalize_unify_narrative_parsed(
        parsed_doc,
        runtime_payload={"selected_fact_plan": {}, "allowed_fact_ids": ["bul_unify_001"]},
    )
    assert norm is not None
    assert not detect_generic_consulting_phrases(norm["narrative_sentence"])
    assert norm["narrative_sentence"] == norm["claim_ledger"][0]["claim_text"]
