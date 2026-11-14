"""Wave 1 unit tests for Stage-Aware Query Diversity and C0.3 FactAnchor resolution."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.c0.c0_fact_anchor import (
    PARTNER_THEME_PATTERNS,
    build_fact_anchor,
    extract_content_word_stems,
    extract_numeric_tokens,
    extract_partner_theme_tags,
    resolve_raw_chunk_text,
)
from apps_rg.runtime.c0.c0_perf_sync_helpers import _ARCHETYPE_ROOT_BOOSTS
from apps_rg.runtime.c0.resume_graph_allocation import (
    ALL_CLAIM_BEARING_SECTIONS,
    build_whole_resume_graph_allocation,
    slice_section_plan_for_allocation,
)
from apps_rg.runtime.sections.graph_role_episode_selector import (
    _CANONICAL_REQUIREMENT_PATTERNS,
    _TARGET_TERMS,
)


def _apps_rg_root() -> Path:
    return Path(__file__).resolve().parents[3] / "resume_graph_engine"


def test_stage_aware_query_diversity_tokens_and_archetype_boosts() -> None:
    required_partner_tokens = {
        "gcp",
        "google cloud",
        "vertex ai",
        "model armor",
        "anthropic",
        "claude",
        "openai",
        "codex",
        "aws",
    }
    required_action_verbs = {
        "architected",
        "directed",
        "engineered",
        "scaled",
        "compressed",
        "automated",
        "commercialized",
        "delivered",
    }
    target_terms_set = set(_TARGET_TERMS)
    assert required_partner_tokens.issubset(target_terms_set)
    assert required_action_verbs.issubset(target_terms_set)

    hyperscaler_patterns = set(_CANONICAL_REQUIREMENT_PATTERNS["hyperscaler_alliance"])
    assert {"gcp", "google cloud", "vertex ai", "model armor", "anthropic", "claude", "openai", "codex"}.issubset(
        hyperscaler_patterns
    )

    all_boost_triggers = {
        trigger
        for triggers, _ in _ARCHETYPE_ROOT_BOOSTS.values()
        for trigger in triggers
    }
    assert required_partner_tokens.issubset(all_boost_triggers)


def test_build_fact_anchor_extracts_numeric_stems_partner_tags_and_18_word_raw_chunk() -> None:
    sample_row = {
        "root_id": "reb_slalom_ecosystem_accelerators",
        "fact_id": "fact_partnerships_gtm_001",
        "skill_id": "skill_hyperscaler_alliance_cosell",
        "skill_label": "Hyperscaler Co-Sell & Partner GTM",
        "employer_lane": "slalom",
        "metric_text": "$120M+ total contract value across 50+ enterprise accounts",
        "metric_value": "120",
        "metric_unit": "USD_M",
        "root_claim_text": "Directed multi-partner AI ecosystem expansion across Google Cloud, Vertex AI, Model Armor, Anthropic Claude, OpenAI Codex, and AWS",
    }
    anchor = build_fact_anchor(sample_row, repo_root=_apps_rg_root())
    assert set(anchor.keys()) >= {
        "numeric_tokens",
        "content_word_stems",
        "resolved_raw_chunk",
        "partner_theme_tags",
    }
    raw_words = anchor["resolved_raw_chunk"].split()
    assert len(raw_words) >= 18
    assert any("120" in tok for tok in anchor["numeric_tokens"])
    assert len(anchor["content_word_stems"]) >= 8
    assert {"gcp", "google_cloud", "vertex_ai", "model_armor", "anthropic", "claude", "openai", "codex", "aws"}.issubset(
        set(anchor["partner_theme_tags"])
    )


def test_whole_resume_allocation_attaches_fact_anchor_and_18_word_raw_chunk_to_all_assignments_and_slices() -> None:
    repo_root = _apps_rg_root()
    bundle = build_whole_resume_graph_allocation(
        repo_root=repo_root,
        target_role="SVP Agentic Engineering and Cloud Alliances",
        jd_text=(
            "Lead agentic AI platform architecture, multi-agent runtime governance, and hyperscaler co-sell "
            "across Google Cloud, Vertex AI, Model Armor, Anthropic Claude, OpenAI Codex, and AWS."
        ),
    )
    plan = bundle["allocation_plan"]
    contracts = bundle["section_final_evidence_contracts"]
    section_plans = bundle["section_plans"]

    assignments = plan["assignments"]
    assert len(assignments) == 48
    for row in assignments:
        anchor = row.get("fact_anchor")
        assert isinstance(anchor, dict), f"Missing fact_anchor on {row.get('claim_unit_id')}"
        resolved = str(anchor.get("resolved_raw_chunk") or "")
        assert len(resolved.split()) >= 18, f"Short resolved_raw_chunk ({len(resolved.split())} words) on {row.get('claim_unit_id')}"
        assert str(row.get("raw_chunk") or "") == resolved
        assert isinstance(anchor.get("content_word_stems"), list) and len(anchor["content_word_stems"]) >= 5
        assert isinstance(anchor.get("numeric_tokens"), list)
        assert isinstance(anchor.get("partner_theme_tags"), list)
        if row.get("metric_value"):
            assert any(str(row["metric_value"]) in tok for tok in anchor["numeric_tokens"])

    for section_id in ALL_CLAIM_BEARING_SECTIONS:
        if section_id in ("ey_bullets", "ey_narrative"):
            continue
        sliced = slice_section_plan_for_allocation(
            section_plan=section_plans[section_id],
            allocation_plan=plan,
            final_evidence_contract=contracts[section_id],
            section_id=section_id,
        )
        assert sliced["facts"], f"Expected non-empty sliced facts for {section_id}"
        for fact in sliced["facts"]:
            f_anchor = fact.get("fact_anchor")
            assert isinstance(f_anchor, dict), f"Missing fact_anchor on sliced fact {fact.get('fact_id')} in {section_id}"
            assert len(str(f_anchor.get("resolved_raw_chunk") or "").split()) >= 18
            assert len(str(fact.get("raw_chunk") or "").split()) >= 18
